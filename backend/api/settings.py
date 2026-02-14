from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    """Environment-based settings (.env file).

    Only auth and infrastructure settings live here.
    Dynamic settings (quality, templates, etc.) live in the SQLite
    settings table and are accessed via database.get_all_settings().
    """
    music_dir: str = str(Path.home() / "music")
    auth_username: Optional[str] = None
    auth_password: Optional[str] = None

    model_config = ConfigDict(
        env_file=str(Path(__file__).parent.parent.parent / ".env"),
        case_sensitive=False,
        extra="ignore",
    )

settings = Settings()

DOWNLOAD_DIR = Path(settings.music_dir)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

PLAYLISTS_DIR = DOWNLOAD_DIR / "tidaloader_playlists"
PLAYLISTS_DIR.mkdir(parents=True, exist_ok=True)

MP3_QUALITY_MAP = {
    "MP3_128": 128,
    "MP3_256": 256,
}

OPUS_QUALITY_MAP = {
    "OPUS_192VBR": 192,
}


class _DBSettingsProxy:
    """A proxy object that reads dynamic settings from SQLite.

    This lets existing code like `settings.organization_template` keep
    working without modification — it transparently reads from the DB.
    Attribute writes are also forwarded to the DB (for backwards compat).
    """

    # Fields that live in SQLite
    _DB_FIELDS = {
        "quality", "sync_time", "organization_template", "active_downloads",
        "use_musicbrainz", "run_beets", "embed_lyrics", "group_compilations",
        "jellyfin_url", "jellyfin_api_key",
    }

    # Type casting hints for DB values
    _BOOL_FIELDS = {
        "use_musicbrainz", "run_beets", "embed_lyrics", "group_compilations",
    }
    _INT_FIELDS = {"active_downloads"}

    # Defaults in case DB isn't initialized yet
    _DEFAULTS = {
        "quality": "LOSSLESS",
        "sync_time": "04:00",
        "organization_template": "{Artist}/{Album}/{TrackNumber} - {Title}",
        "active_downloads": 3,
        "use_musicbrainz": True,
        "run_beets": False,
        "embed_lyrics": False,
        "group_compilations": True,
        "jellyfin_url": "",
        "jellyfin_api_key": "",
    }

    def __getattr__(self, name: str):
        if name.startswith("_") or name not in self._DB_FIELDS:
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

        try:
            import database as db
            val = db.get_setting(name)
            if val is None:
                return self._DEFAULTS.get(name)

            if name in self._BOOL_FIELDS:
                return val == "true"
            if name in self._INT_FIELDS:
                try:
                    return int(val)
                except ValueError:
                    return self._DEFAULTS.get(name)
            return val
        except Exception:
            # DB not initialized yet (startup)
            return self._DEFAULTS.get(name)

    def __setattr__(self, name: str, value):
        if name.startswith("_") or name not in self._DB_FIELDS:
            super().__setattr__(name, value)
            return

        try:
            import database as db
            version = db.get_settings_version()
            db.update_settings({name: value}, version)
        except Exception:
            pass  # Silently fail during startup


# Replace the plain settings object with a combined proxy
# .env settings stay on the BaseSettings object, DB settings go through the proxy
settings = type("CombinedSettings", (), {
    "_env": Settings(),
    "_db": _DBSettingsProxy(),
    "__getattr__": lambda self, name: (
        getattr(self._env, name) if hasattr(type(self._env), name) or name in self._env.model_fields
        else getattr(self._db, name)
    ),
    "__setattr__": lambda self, name, value: (
        object.__setattr__(self, name, value) if name.startswith("_")
        else (
            setattr(self._env, name, value) if name in self._env.model_fields
            else setattr(self._db, name, value)
        )
    ),
})()
