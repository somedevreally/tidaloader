"""
SQLite Database Layer for Tidaloader

Provides normalized storage for artists, albums, tracks, and download queue.
Replaces all JSON file persistence with efficient SQLite + FTS5 search.
Uses WAL mode for concurrent read access during downloads.
"""

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

from api.utils.logging import log_info, log_error, log_warning, log_success


class StaleSettingsError(Exception):
    """Raised when a settings update conflicts with a newer version."""
    def __init__(self, current_version: int):
        self.current_version = current_version
        super().__init__(f"Settings version conflict: current version is {current_version}")

DB_PATH = Path(__file__).parent / "tidaloader.db"

# Thread-local storage for connections
_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """Get a thread-local database connection."""
    if not hasattr(_local, "connection") or _local.connection is None:
        conn = sqlite3.connect(str(DB_PATH), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        _local.connection = conn
    return _local.connection


@contextmanager
def get_db():
    """Context manager for database operations with auto-commit/rollback."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# Default settings values — used to seed the settings table
_DEFAULT_SETTINGS = {
    "quality": "LOSSLESS",
    "sync_time": "04:00",
    "organization_template": "{Artist}/{Album}/{TrackNumber} - {Title}",
    "active_downloads": "3",
    "use_musicbrainz": "true",
    "run_beets": "false",
    "embed_lyrics": "false",
    "group_compilations": "true",
    "jellyfin_url": "",
    "jellyfin_api_key": "",
}


def init_db():
    """Initialize the database schema. Safe to call multiple times."""
    with get_db() as conn:
        conn.executescript(_SCHEMA_SQL)
    _seed_default_settings()
    log_success("Database initialized")


def _seed_default_settings():
    """Insert default settings if tables are empty."""
    with get_db() as conn:
        # Seed settings_meta if empty
        row = conn.execute("SELECT version FROM settings_meta WHERE id = 1").fetchone()
        if not row:
            conn.execute("INSERT INTO settings_meta (id, version) VALUES (1, 1)")

        # Seed each default setting if not already present
        for key, value in _DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS artists (
    tidal_id    INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    picture     TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS albums (
    tidal_id     INTEGER PRIMARY KEY,
    title        TEXT NOT NULL,
    artist_id    INTEGER REFERENCES artists(tidal_id),
    cover_url    TEXT,
    release_date TEXT,
    total_tracks INTEGER,
    total_discs  INTEGER,
    album_type   TEXT,
    created_at   TEXT DEFAULT (datetime('now')),
    updated_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tracks (
    tidal_id              INTEGER PRIMARY KEY,
    title                 TEXT NOT NULL,
    artist_id             INTEGER REFERENCES artists(tidal_id),
    album_id              INTEGER REFERENCES albums(tidal_id),
    track_number          INTEGER,
    disc_number           INTEGER,
    duration              INTEGER,
    file_path             TEXT,
    file_format           TEXT,
    quality               TEXT,
    musicbrainz_track_id  TEXT,
    downloaded_at         TEXT DEFAULT (datetime('now')),
    status                TEXT DEFAULT 'completed'
);

CREATE TABLE IF NOT EXISTS queue_items (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id               INTEGER NOT NULL,
    title                  TEXT NOT NULL,
    artist                 TEXT NOT NULL,
    album                  TEXT DEFAULT '',
    album_id               INTEGER,
    track_number           INTEGER,
    cover                  TEXT,
    quality                TEXT DEFAULT 'HIGH',
    status                 TEXT DEFAULT 'queued',
    progress               INTEGER DEFAULT 0,
    error                  TEXT,
    added_at               TEXT DEFAULT (datetime('now')),
    completed_at           TEXT,
    added_by               TEXT DEFAULT 'unknown',
    target_format          TEXT,
    bitrate_kbps           INTEGER,
    run_beets              INTEGER DEFAULT 0,
    embed_lyrics           INTEGER DEFAULT 0,
    organization_template  TEXT DEFAULT '{Artist}/{Album}/{TrackNumber} - {Title}',
    group_compilations     INTEGER DEFAULT 1,
    use_musicbrainz        INTEGER DEFAULT 1,
    auto_clean             INTEGER DEFAULT 0,
    tidal_track_id         TEXT,
    tidal_artist_id        TEXT,
    tidal_album_id         TEXT,
    album_artist           TEXT,
    filename               TEXT,
    metadata_json          TEXT
);

-- Index for fast queue status queries
CREATE INDEX IF NOT EXISTS idx_queue_status ON queue_items(status);
CREATE INDEX IF NOT EXISTS idx_queue_track_id ON queue_items(track_id);

-- Index for track lookups
CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album_id);
CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist_id);
CREATE INDEX IF NOT EXISTS idx_tracks_status ON tracks(status);

-- FTS5 for fast text search
CREATE VIRTUAL TABLE IF NOT EXISTS tracks_fts USING fts5(
    title, artist_name, album_title,
    content='',
    tokenize='unicode61'
);

-- Settings key-value store
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Single-row version tracker for optimistic concurrency
CREATE TABLE IF NOT EXISTS settings_meta (
    id      INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER DEFAULT 1
);
"""


# --------------------------------------------------------------------------
# Artist CRUD
# --------------------------------------------------------------------------

def upsert_artist(tidal_id: int, name: str, picture: str = None) -> None:
    """Insert or update an artist."""
    with get_db() as conn:
        conn.execute(
            """INSERT INTO artists (tidal_id, name, picture, updated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(tidal_id) DO UPDATE SET
                   name = COALESCE(excluded.name, name),
                   picture = COALESCE(excluded.picture, picture),
                   updated_at = datetime('now')""",
            (tidal_id, name, picture),
        )


def get_artist(tidal_id: int) -> Optional[Dict]:
    """Get an artist by Tidal ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM artists WHERE tidal_id = ?", (tidal_id,)
        ).fetchone()
        return dict(row) if row else None


def get_all_artists() -> List[Dict]:
    """Get all artists."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM artists ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Album CRUD
# --------------------------------------------------------------------------

def upsert_album(
    tidal_id: int,
    title: str,
    artist_id: int = None,
    cover_url: str = None,
    release_date: str = None,
    total_tracks: int = None,
    total_discs: int = None,
    album_type: str = None,
) -> None:
    """Insert or update an album."""
    with get_db() as conn:
        conn.execute(
            """INSERT INTO albums (tidal_id, title, artist_id, cover_url, release_date,
                                   total_tracks, total_discs, album_type, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(tidal_id) DO UPDATE SET
                   title = COALESCE(excluded.title, title),
                   artist_id = COALESCE(excluded.artist_id, artist_id),
                   cover_url = COALESCE(excluded.cover_url, cover_url),
                   release_date = COALESCE(excluded.release_date, release_date),
                   total_tracks = COALESCE(excluded.total_tracks, total_tracks),
                   total_discs = COALESCE(excluded.total_discs, total_discs),
                   album_type = COALESCE(excluded.album_type, album_type),
                   updated_at = datetime('now')""",
            (tidal_id, title, artist_id, cover_url, release_date, total_tracks, total_discs, album_type),
        )


def get_album(tidal_id: int) -> Optional[Dict]:
    """Get an album by Tidal ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM albums WHERE tidal_id = ?", (tidal_id,)
        ).fetchone()
        return dict(row) if row else None


def get_albums_by_artist(artist_id: int) -> List[Dict]:
    """Get all albums for an artist."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM albums WHERE artist_id = ? ORDER BY release_date DESC",
            (artist_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Track CRUD
# --------------------------------------------------------------------------

def upsert_track(
    tidal_id: int,
    title: str,
    artist_id: int = None,
    album_id: int = None,
    track_number: int = None,
    disc_number: int = None,
    duration: int = None,
    file_path: str = None,
    file_format: str = None,
    quality: str = None,
    musicbrainz_track_id: str = None,
) -> None:
    """Insert or update a track."""
    with get_db() as conn:
        conn.execute(
            """INSERT INTO tracks (tidal_id, title, artist_id, album_id, track_number,
                                   disc_number, duration, file_path, file_format, quality,
                                   musicbrainz_track_id, downloaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(tidal_id) DO UPDATE SET
                   title = COALESCE(excluded.title, title),
                   artist_id = COALESCE(excluded.artist_id, artist_id),
                   album_id = COALESCE(excluded.album_id, album_id),
                   track_number = COALESCE(excluded.track_number, track_number),
                   disc_number = COALESCE(excluded.disc_number, disc_number),
                   duration = COALESCE(excluded.duration, duration),
                   file_path = COALESCE(excluded.file_path, file_path),
                   file_format = COALESCE(excluded.file_format, file_format),
                   quality = COALESCE(excluded.quality, quality),
                   musicbrainz_track_id = COALESCE(excluded.musicbrainz_track_id, musicbrainz_track_id),
                   status = 'completed'""",
            (tidal_id, title, artist_id, album_id, track_number, disc_number,
             duration, file_path, file_format, quality, musicbrainz_track_id),
        )
        # Update FTS index
        _update_fts(conn, tidal_id, title, artist_id, album_id)


def get_track(tidal_id: int) -> Optional[Dict]:
    """Get a track by Tidal ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM tracks WHERE tidal_id = ?", (tidal_id,)
        ).fetchone()
        return dict(row) if row else None


def get_tracks_by_album(album_id: int) -> List[Dict]:
    """Get all tracks for an album."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM tracks WHERE album_id = ?
               ORDER BY disc_number, track_number""",
            (album_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_tracks_by_artist(artist_id: int) -> List[Dict]:
    """Get all tracks for an artist."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tracks WHERE artist_id = ? ORDER BY downloaded_at DESC",
            (artist_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def search_tracks_fts(query: str, limit: int = 50) -> List[Dict]:
    """Full-text search across tracks."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT t.* FROM tracks_fts fts
               JOIN tracks t ON fts.rowid = t.tidal_id
               WHERE tracks_fts MATCH ?
               LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def _update_fts(conn: sqlite3.Connection, tidal_id: int, title: str,
                artist_id: int = None, album_id: int = None):
    """Update the FTS index for a track."""
    # Look up artist and album names for the FTS entry
    artist_name = ""
    album_title = ""
    if artist_id:
        row = conn.execute("SELECT name FROM artists WHERE tidal_id = ?", (artist_id,)).fetchone()
        if row:
            artist_name = row["name"]
    if album_id:
        row = conn.execute("SELECT title FROM albums WHERE tidal_id = ?", (album_id,)).fetchone()
        if row:
            album_title = row["title"]

    # Delete old entry if exists, then insert new
    conn.execute("DELETE FROM tracks_fts WHERE rowid = ?", (tidal_id,))
    conn.execute(
        "INSERT INTO tracks_fts(rowid, title, artist_name, album_title) VALUES (?, ?, ?, ?)",
        (tidal_id, title, artist_name, album_title),
    )


# --------------------------------------------------------------------------
# Queue CRUD
# --------------------------------------------------------------------------

def add_queue_item(
    track_id: int,
    title: str,
    artist: str,
    album: str = "",
    album_id: int = None,
    track_number: int = None,
    cover: str = None,
    quality: str = "HIGH",
    added_by: str = "unknown",
    target_format: str = None,
    bitrate_kbps: int = None,
    run_beets: bool = False,
    embed_lyrics: bool = False,
    organization_template: str = "{Artist}/{Album}/{TrackNumber} - {Title}",
    group_compilations: bool = True,
    use_musicbrainz: bool = True,
    auto_clean: bool = False,
    tidal_track_id: str = None,
    tidal_artist_id: str = None,
    tidal_album_id: str = None,
    album_artist: str = None,
) -> Optional[int]:
    """Add an item to the download queue. Returns the row id or None if duplicate."""
    with get_db() as conn:
        # Check for duplicates (same track_id that's queued or active)
        existing = conn.execute(
            "SELECT id FROM queue_items WHERE track_id = ? AND status IN ('queued', 'active')",
            (track_id,),
        ).fetchone()
        if existing:
            return None

        cursor = conn.execute(
            """INSERT INTO queue_items (
                track_id, title, artist, album, album_id, track_number, cover,
                quality, added_by, target_format, bitrate_kbps, run_beets,
                embed_lyrics, organization_template, group_compilations,
                use_musicbrainz, auto_clean, tidal_track_id, tidal_artist_id,
                tidal_album_id, album_artist, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued')""",
            (
                track_id, title, artist, album, album_id, track_number, cover,
                quality, added_by, target_format, bitrate_kbps,
                1 if run_beets else 0, 1 if embed_lyrics else 0,
                organization_template, 1 if group_compilations else 0,
                1 if use_musicbrainz else 0, 1 if auto_clean else 0,
                tidal_track_id, tidal_artist_id, tidal_album_id, album_artist,
            ),
        )
        return cursor.lastrowid


def get_queue_items(
    status: str = None,
    limit: int = None,
    offset: int = 0,
    order: str = 'asc'
) -> List[Dict]:
    """Get queue items with optional pagination.
    
    Args:
        status: Filter by status ('queued', 'active', 'completed', 'failed')
        limit: Maximum number of items to return
        offset: Number of items to skip
        order: Sort order ('asc' or 'desc')
    """
    with get_db() as conn:
        order_clause = "DESC" if order == 'desc' else "ASC"
        
        if status:
            query = f"SELECT * FROM queue_items WHERE status = ? ORDER BY completed_at {order_clause}, added_at {order_clause}"
            params = [status]
        else:
            query = f"SELECT * FROM queue_items ORDER BY added_at {order_clause}"
            params = []
        
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_queue_items_count(status: str = None) -> int:
    """Get total count of queue items by status."""
    with get_db() as conn:
        if status:
            result = conn.execute(
                "SELECT COUNT(*) as count FROM queue_items WHERE status = ?",
                (status,)
            ).fetchone()
        else:
            result = conn.execute(
                "SELECT COUNT(*) as count FROM queue_items"
            ).fetchone()
        return result['count'] if result else 0


def update_queue_item_status(
    track_id: int,
    status: str,
    error: str = None,
    filename: str = None,
    metadata_json: str = None,
) -> bool:
    """Update the status of a queue item by track_id."""
    with get_db() as conn:
        completed_at = "datetime('now')" if status in ("completed", "failed") else None
        if completed_at:
            cursor = conn.execute(
                """UPDATE queue_items SET status = ?, error = ?, filename = ?,
                   metadata_json = ?, completed_at = datetime('now')
                   WHERE track_id = ? AND status IN ('queued', 'active')""",
                (status, error, filename, metadata_json, track_id),
            )
        else:
            cursor = conn.execute(
                """UPDATE queue_items SET status = ?, error = ?, filename = ?,
                   metadata_json = ?
                   WHERE track_id = ? AND status IN ('queued', 'active')""",
                (status, error, filename, metadata_json, track_id),
            )
        return cursor.rowcount > 0


def pop_queued_items(count: int) -> List[Dict]:
    """Atomically fetch and mark N queued items as 'active'."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM queue_items WHERE status = 'queued' ORDER BY added_at LIMIT ?",
            (count,),
        ).fetchall()
        items = [dict(r) for r in rows]
        if items:
            ids = [item["id"] for item in items]
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"UPDATE queue_items SET status = 'active' WHERE id IN ({placeholders})",
                ids,
            )
        return items


def delete_queue_item(track_id: int) -> bool:
    """Remove a queued item by track_id."""
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM queue_items WHERE track_id = ? AND status = 'queued'",
            (track_id,),
        )
        return cursor.rowcount > 0


def clear_queue_items(status: str) -> int:
    """Clear all queue items with the given status. Returns count deleted."""
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM queue_items WHERE status = ?", (status,))
        return cursor.rowcount


def requeue_failed_items() -> int:
    """Move all failed items back to queued. Returns count."""
    with get_db() as conn:
        cursor = conn.execute(
            """UPDATE queue_items SET status = 'queued', error = NULL,
               progress = 0, completed_at = NULL
               WHERE status = 'failed'"""
        )
        return cursor.rowcount


def requeue_single_failed(track_id: int) -> bool:
    """Move a single failed item back to queued."""
    with get_db() as conn:
        cursor = conn.execute(
            """UPDATE queue_items SET status = 'queued', error = NULL,
               progress = 0, completed_at = NULL
               WHERE track_id = ? AND status = 'failed'""",
            (track_id,),
        )
        return cursor.rowcount > 0


def get_queue_counts() -> Dict[str, int]:
    """Get counts of queue items by status."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM queue_items GROUP BY status"
        ).fetchall()
        return {row["status"]: row["cnt"] for row in rows}


# --------------------------------------------------------------------------
# Library queries
# --------------------------------------------------------------------------

def get_library_stats() -> Dict[str, int]:
    """Get total counts for the library."""
    with get_db() as conn:
        artists = conn.execute("SELECT COUNT(*) FROM artists").fetchone()[0]
        albums = conn.execute("SELECT COUNT(*) FROM albums").fetchone()[0]
        tracks = conn.execute("SELECT COUNT(*) FROM tracks WHERE status = 'completed'").fetchone()[0]
        return {"artists": artists, "albums": albums, "tracks": tracks}


def get_artist_with_albums(tidal_id: int) -> Optional[Dict]:
    """Get an artist with all their albums and track counts."""
    artist = get_artist(tidal_id)
    if not artist:
        return None

    with get_db() as conn:
        albums = conn.execute(
            """SELECT a.*, COUNT(t.tidal_id) as track_count
               FROM albums a
               LEFT JOIN tracks t ON t.album_id = a.tidal_id AND t.status = 'completed'
               WHERE a.artist_id = ?
               GROUP BY a.tidal_id
               ORDER BY a.release_date DESC""",
            (tidal_id,),
        ).fetchall()
        artist["albums"] = [dict(a) for a in albums]

    return artist


def get_album_with_tracks(tidal_id: int) -> Optional[Dict]:
    """Get an album with all its tracks."""
    album = get_album(tidal_id)
    if not album:
        return None
    album["tracks"] = get_tracks_by_album(tidal_id)
    return album


# --------------------------------------------------------------------------
# Settings CRUD
# --------------------------------------------------------------------------

def get_all_settings() -> Dict[str, Any]:
    """Get all settings as a dict plus current version."""
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        settings = {row["key"]: row["value"] for row in rows}

        version_row = conn.execute(
            "SELECT version FROM settings_meta WHERE id = 1"
        ).fetchone()
        version = version_row["version"] if version_row else 1

    # Cast booleans and integers for API consumers
    result = {}
    for k, v in settings.items():
        if v in ("true", "false"):
            result[k] = v == "true"
        elif v.isdigit():
            result[k] = int(v)
        else:
            result[k] = v
    result["version"] = version
    return result


def get_setting(key: str) -> Optional[str]:
    """Get a single setting value by key."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None


def update_settings(updates: Dict[str, Any], expected_version: int) -> int:
    """Update settings with optimistic concurrency.

    Args:
        updates: dict of key/value pairs to upsert
        expected_version: the version the client last saw

    Returns:
        The new version number.

    Raises:
        StaleSettingsError: if expected_version != current version
    """
    with get_db() as conn:
        # Check current version
        row = conn.execute(
            "SELECT version FROM settings_meta WHERE id = 1"
        ).fetchone()
        current_version = row["version"] if row else 1

        if current_version != expected_version:
            raise StaleSettingsError(current_version)

        # Upsert each setting
        for key, value in updates.items():
            if key == "version":
                continue  # skip the meta field
            # Normalize booleans to "true"/"false" strings
            if isinstance(value, bool):
                value = "true" if value else "false"
            else:
                value = str(value)
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

        # Bump version
        new_version = current_version + 1
        conn.execute(
            "UPDATE settings_meta SET version = ? WHERE id = 1",
            (new_version,),
        )
        return new_version


def get_settings_version() -> int:
    """Get the current settings version."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT version FROM settings_meta WHERE id = 1"
        ).fetchone()
        return row["version"] if row else 1


# --------------------------------------------------------------------------
# JSON Migration
# --------------------------------------------------------------------------

def migrate_json_to_sqlite():
    """One-time migration of existing JSON state files to SQLite."""
    backend_dir = Path(__file__).parent

    # Migrate queue_state.json
    queue_file = backend_dir / "queue_state.json"
    if queue_file.exists():
        try:
            with open(queue_file, "r") as f:
                data = json.load(f)

            migrated = 0
            # Migrate queued items
            for item in data.get("queue", []):
                result = add_queue_item(
                    track_id=item["track_id"],
                    title=item.get("title", ""),
                    artist=item.get("artist", ""),
                    album=item.get("album", ""),
                    album_id=item.get("album_id"),
                    track_number=item.get("track_number"),
                    cover=item.get("cover"),
                    quality=item.get("quality", "HIGH"),
                    added_by=item.get("added_by", "migration"),
                    target_format=item.get("target_format"),
                    bitrate_kbps=item.get("bitrate_kbps"),
                    run_beets=item.get("run_beets", False),
                    embed_lyrics=item.get("embed_lyrics", False),
                    organization_template=item.get("organization_template", "{Artist}/{Album}/{TrackNumber} - {Title}"),
                    group_compilations=item.get("group_compilations", True),
                    use_musicbrainz=item.get("use_musicbrainz", True),
                    auto_clean=item.get("auto_clean", False),
                    tidal_track_id=item.get("tidal_track_id"),
                    tidal_artist_id=item.get("tidal_artist_id"),
                    tidal_album_id=item.get("tidal_album_id"),
                    album_artist=item.get("album_artist"),
                )
                if result:
                    migrated += 1

            # Migrate completed items
            for item in data.get("completed", []):
                with get_db() as conn:
                    conn.execute(
                        """INSERT OR IGNORE INTO queue_items (
                            track_id, title, artist, album, filename,
                            status, completed_at, metadata_json
                        ) VALUES (?, ?, ?, ?, ?, 'completed', ?, ?)""",
                        (
                            item.get("track_id", 0),
                            item.get("title", ""),
                            item.get("artist", ""),
                            item.get("album", ""),
                            item.get("filename", ""),
                            item.get("completed_at", ""),
                            json.dumps(item.get("metadata", {})) if item.get("metadata") else None,
                        ),
                    )
                    migrated += 1

            # Migrate failed items
            for item in data.get("failed", []):
                with get_db() as conn:
                    conn.execute(
                        """INSERT OR IGNORE INTO queue_items (
                            track_id, title, artist, album, error, quality,
                            target_format, bitrate_kbps, run_beets, embed_lyrics,
                            status, completed_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'failed', ?)""",
                        (
                            item.get("track_id", 0),
                            item.get("title", ""),
                            item.get("artist", ""),
                            item.get("album", ""),
                            item.get("error", ""),
                            item.get("quality", "HIGH"),
                            item.get("target_format"),
                            item.get("bitrate_kbps"),
                            1 if item.get("run_beets") else 0,
                            1 if item.get("embed_lyrics") else 0,
                            item.get("failed_at", ""),
                        ),
                    )
                    migrated += 1

            # Rename original file
            queue_file.rename(queue_file.with_suffix(".json.bak"))
            log_success(f"Migrated queue_state.json → SQLite ({migrated} items)")
        except Exception as e:
            log_error(f"Failed to migrate queue_state.json: {e}")

    # Migrate download_state.json
    dl_file = backend_dir / "download_state.json"
    if dl_file.exists():
        try:
            with open(dl_file, "r") as f:
                data = json.load(f)

            migrated = 0
            # Completed downloads
            for track_id_str, info in data.get("completed", {}).items():
                with get_db() as conn:
                    conn.execute(
                        """INSERT OR IGNORE INTO queue_items (
                            track_id, title, artist, filename, status,
                            metadata_json
                        ) VALUES (?, ?, ?, ?, 'completed', ?)""",
                        (
                            int(track_id_str),
                            info.get("metadata", {}).get("title", ""),
                            info.get("metadata", {}).get("artist", ""),
                            info.get("filename", ""),
                            json.dumps(info.get("metadata", {})) if info.get("metadata") else None,
                        ),
                    )
                    migrated += 1

            # Failed downloads
            for track_id_str, info in data.get("failed", {}).items():
                with get_db() as conn:
                    conn.execute(
                        """INSERT OR IGNORE INTO queue_items (
                            track_id, title, artist, error, status
                        ) VALUES (?, ?, ?, ?, 'failed')""",
                        (
                            int(track_id_str),
                            info.get("metadata", {}).get("title", ""),
                            info.get("metadata", {}).get("artist", ""),
                            info.get("error", ""),
                        ),
                    )
                    migrated += 1

            dl_file.rename(dl_file.with_suffix(".json.bak"))
            log_success(f"Migrated download_state.json → SQLite ({migrated} items)")
        except Exception as e:
            log_error(f"Failed to migrate download_state.json: {e}")

    # Migrate config.json → settings table
    from api.settings import DOWNLOAD_DIR
    config_file = DOWNLOAD_DIR / "config.json"
    if config_file.exists():
        try:
            with open(config_file, "r") as f:
                data = json.load(f)

            # Map config.json keys to settings table keys
            key_map = {
                "sync_time": "sync_time",
                "organization_template": "organization_template",
                "active_downloads": "active_downloads",
                "use_musicbrainz": "use_musicbrainz",
                "run_beets": "run_beets",
                "embed_lyrics": "embed_lyrics",
                "group_compilations": "group_compilations",
                "jellyfin_url": "jellyfin_url",
                "jellyfin_api_key": "jellyfin_api_key",
                "quality": "quality",
            }

            updates = {}
            for json_key, db_key in key_map.items():
                if json_key in data:
                    val = data[json_key]
                    if isinstance(val, bool):
                        updates[db_key] = "true" if val else "false"
                    else:
                        updates[db_key] = str(val)

            # Handle legacy sync_hour
            if "sync_hour" in data and "sync_time" not in data:
                updates["sync_time"] = f"{data['sync_hour']:02d}:00"

            if updates:
                with get_db() as conn:
                    for key, value in updates.items():
                        conn.execute(
                            "INSERT INTO settings (key, value) VALUES (?, ?) "
                            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                            (key, value),
                        )

            config_file.rename(config_file.with_suffix(".json.bak"))
            log_success(f"Migrated config.json → SQLite settings ({len(updates)} keys)")
        except Exception as e:
            log_error(f"Failed to migrate config.json: {e}")
