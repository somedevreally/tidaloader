"""Tests for the SQLite database layer."""
import os
import sys
from pathlib import Path

os.environ["AUTH_USERNAME"] = "test"
os.environ["AUTH_PASSWORD"] = "test"

sys.path.append(str(Path(__file__).parent.parent))

import database as db

# Override DB path for tests
db.DB_PATH = Path(__file__).parent / "test_tidaloader.db"


class TestDatabaseSchema:
    """Test schema creation and basic operations."""

    def setup_method(self):
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()
        if hasattr(db._local, 'connection') and db._local.connection:
            db._local.connection.close()
            db._local.connection = None
        db.init_db()

    def teardown_method(self):
        if hasattr(db._local, 'connection') and db._local.connection:
            db._local.connection.close()
            db._local.connection = None
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()

    def test_init_db_creates_tables(self):
        conn = db.get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row['name'] for row in tables}
        assert 'artists' in table_names
        assert 'albums' in table_names
        assert 'tracks' in table_names
        assert 'queue_items' in table_names

    def test_init_db_idempotent(self):
        """Calling init_db multiple times should not error."""
        db.init_db()
        db.init_db()

    def test_wal_mode_enabled(self):
        conn = db.get_connection()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == 'wal'


class TestArtistCRUD:
    def setup_method(self):
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()
        if hasattr(db._local, 'connection') and db._local.connection:
            db._local.connection.close()
            db._local.connection = None
        db.init_db()

    def teardown_method(self):
        if hasattr(db._local, 'connection') and db._local.connection:
            db._local.connection.close()
            db._local.connection = None
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()

    def test_upsert_and_get_artist(self):
        db.upsert_artist(12345, "Test Artist", "pic-123")
        artist = db.get_artist(12345)
        assert artist is not None
        assert artist['name'] == "Test Artist"
        assert artist['picture'] == "pic-123"

    def test_upsert_updates_existing(self):
        db.upsert_artist(12345, "Original Name")
        db.upsert_artist(12345, "Updated Name", "new-pic")
        artist = db.get_artist(12345)
        assert artist['name'] == "Updated Name"
        assert artist['picture'] == "new-pic"

    def test_get_nonexistent_artist(self):
        result = db.get_artist(99999)
        assert result is None

    def test_get_all_artists(self):
        db.upsert_artist(1, "Alpha Artist")
        db.upsert_artist(2, "Beta Artist")
        db.upsert_artist(3, "Charlie Artist")
        artists = db.get_all_artists()
        assert len(artists) == 3
        # Should be sorted by name (case-insensitive)
        assert artists[0]['name'] == "Alpha Artist"


class TestAlbumCRUD:
    def setup_method(self):
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()
        if hasattr(db._local, 'connection') and db._local.connection:
            db._local.connection.close()
            db._local.connection = None
        db.init_db()

    def teardown_method(self):
        if hasattr(db._local, 'connection') and db._local.connection:
            db._local.connection.close()
            db._local.connection = None
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()

    def test_upsert_and_get_album(self):
        db.upsert_artist(100, "The Artist")
        db.upsert_album(200, "Test Album", artist_id=100, cover_url="http://cover.jpg")
        album = db.get_album(200)
        assert album is not None
        assert album['title'] == "Test Album"
        assert album['cover_url'] == "http://cover.jpg"

    def test_get_albums_by_artist(self):
        db.upsert_artist(100, "Artist A")
        db.upsert_album(201, "Album One", artist_id=100)
        db.upsert_album(202, "Album Two", artist_id=100)
        albums = db.get_albums_by_artist(100)
        assert len(albums) == 2

    def test_cover_url_per_album(self):
        """Cover URL is stored per album, not per track."""
        db.upsert_artist(100, "Artist")
        db.upsert_album(200, "Album", artist_id=100, cover_url="http://cover.jpg")
        album = db.get_album(200)
        assert album['cover_url'] == "http://cover.jpg"


class TestTrackCRUD:
    def setup_method(self):
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()
        if hasattr(db._local, 'connection') and db._local.connection:
            db._local.connection.close()
            db._local.connection = None
        db.init_db()

    def teardown_method(self):
        if hasattr(db._local, 'connection') and db._local.connection:
            db._local.connection.close()
            db._local.connection = None
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()

    def test_upsert_and_get_track(self):
        db.upsert_artist(100, "Artist")
        db.upsert_album(200, "Album", artist_id=100)
        db.upsert_track(
            tidal_id=300,
            title="Test Track",
            artist_id=100,
            album_id=200,
            track_number=1,
            file_path="/music/test.flac",
            file_format="flac",
            quality="LOSSLESS"
        )
        track = db.get_track(300)
        assert track is not None
        assert track['title'] == "Test Track"
        assert track['file_path'] == "/music/test.flac"

    def test_get_tracks_by_album(self):
        db.upsert_artist(100, "Artist")
        db.upsert_album(200, "Album", artist_id=100)
        db.upsert_track(301, "Track 1", artist_id=100, album_id=200, track_number=1)
        db.upsert_track(302, "Track 2", artist_id=100, album_id=200, track_number=2)
        tracks = db.get_tracks_by_album(200)
        assert len(tracks) == 2
        assert tracks[0]['track_number'] == 1


class TestQueueCRUD:
    def setup_method(self):
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()
        if hasattr(db._local, 'connection') and db._local.connection:
            db._local.connection.close()
            db._local.connection = None
        db.init_db()

    def teardown_method(self):
        if hasattr(db._local, 'connection') and db._local.connection:
            db._local.connection.close()
            db._local.connection = None
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()

    def test_add_queue_item(self):
        row_id = db.add_queue_item(track_id=1001, title="Song", artist="Singer")
        assert row_id is not None
        items = db.get_queue_items("queued")
        assert len(items) == 1
        assert items[0]['title'] == "Song"

    def test_duplicate_queued_rejected(self):
        db.add_queue_item(track_id=1001, title="Song", artist="Singer")
        result = db.add_queue_item(track_id=1001, title="Song", artist="Singer")
        assert result is None  # duplicate

    def test_pop_queued_items(self):
        db.add_queue_item(track_id=1001, title="Song 1", artist="A")
        db.add_queue_item(track_id=1002, title="Song 2", artist="B")
        db.add_queue_item(track_id=1003, title="Song 3", artist="C")

        popped = db.pop_queued_items(2)
        assert len(popped) == 2
        # Should now be 'active' status
        active = db.get_queue_items("active")
        assert len(active) == 2
        queued = db.get_queue_items("queued")
        assert len(queued) == 1

    def test_update_status(self):
        db.add_queue_item(track_id=1001, title="Song", artist="A")
        # Simulate pop
        db.pop_queued_items(1)
        # Mark completed
        db.update_queue_item_status(1001, "completed", filename="song.flac")
        completed = db.get_queue_items("completed")
        assert len(completed) == 1
        assert completed[0]['filename'] == "song.flac"

    def test_clear_queue_items(self):
        db.add_queue_item(track_id=1001, title="Song 1", artist="A")
        db.add_queue_item(track_id=1002, title="Song 2", artist="B")
        cleared = db.clear_queue_items("queued")
        assert cleared == 2
        assert len(db.get_queue_items("queued")) == 0

    def test_requeue_failed(self):
        db.add_queue_item(track_id=1001, title="Song", artist="A")
        db.pop_queued_items(1)
        db.update_queue_item_status(1001, "failed", error="timeout")
        failed = db.get_queue_items("failed")
        assert len(failed) == 1

        count = db.requeue_failed_items()
        assert count == 1
        queued = db.get_queue_items("queued")
        assert len(queued) == 1

    def test_delete_queue_item(self):
        db.add_queue_item(track_id=1001, title="Song", artist="A")
        deleted = db.delete_queue_item(1001)
        assert deleted is True
        assert len(db.get_queue_items("queued")) == 0

    def test_queue_counts(self):
        db.add_queue_item(track_id=1001, title="S1", artist="A")
        db.add_queue_item(track_id=1002, title="S2", artist="A")
        db.pop_queued_items(1)
        counts = db.get_queue_counts()
        assert counts.get("queued", 0) == 1
        assert counts.get("active", 0) == 1

    def test_no_queue_size_limit(self):
        """SQLite should handle hundreds of items without issue."""
        for i in range(200):
            db.add_queue_item(track_id=i, title=f"Track {i}", artist="Artist")
        items = db.get_queue_items("queued")
        assert len(items) == 200


class TestFTS:
    def setup_method(self):
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()
        if hasattr(db._local, 'connection') and db._local.connection:
            db._local.connection.close()
            db._local.connection = None
        db.init_db()

    def teardown_method(self):
        if hasattr(db._local, 'connection') and db._local.connection:
            db._local.connection.close()
            db._local.connection = None
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()

    def test_fts_search(self):
        db.upsert_artist(100, "Radiohead")
        db.upsert_album(200, "OK Computer", artist_id=100)
        db.upsert_track(300, "Paranoid Android", artist_id=100, album_id=200)
        db.upsert_track(301, "Karma Police", artist_id=100, album_id=200)

        results = db.search_tracks_fts("Paranoid")
        assert len(results) == 1
        assert results[0]['title'] == "Paranoid Android"

    def test_fts_search_by_artist(self):
        db.upsert_artist(100, "Radiohead")
        db.upsert_album(200, "Album", artist_id=100)
        db.upsert_track(300, "Track One", artist_id=100, album_id=200)

        results = db.search_tracks_fts("Radiohead")
        assert len(results) == 1


class TestLibraryQueries:
    def setup_method(self):
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()
        if hasattr(db._local, 'connection') and db._local.connection:
            db._local.connection.close()
            db._local.connection = None
        db.init_db()

    def teardown_method(self):
        if hasattr(db._local, 'connection') and db._local.connection:
            db._local.connection.close()
            db._local.connection = None
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()

    def test_library_stats(self):
        db.upsert_artist(100, "Artist")
        db.upsert_album(200, "Album", artist_id=100)
        db.upsert_track(300, "Track", artist_id=100, album_id=200)
        stats = db.get_library_stats()
        assert stats['artists'] == 1
        assert stats['albums'] == 1
        assert stats['tracks'] == 1

    def test_artist_with_albums(self):
        db.upsert_artist(100, "Artist")
        db.upsert_album(200, "Album A", artist_id=100)
        db.upsert_album(201, "Album B", artist_id=100)
        db.upsert_track(300, "Track 1", artist_id=100, album_id=200)
        db.upsert_track(301, "Track 2", artist_id=100, album_id=200)

        result = db.get_artist_with_albums(100)
        assert result is not None
        assert len(result['albums']) == 2
        # Album 200 should have 2 tracks
        album_200 = next(a for a in result['albums'] if a['tidal_id'] == 200)
        assert album_200['track_count'] == 2

    def test_album_with_tracks(self):
        db.upsert_artist(100, "Artist")
        db.upsert_album(200, "Album", artist_id=100)
        db.upsert_track(300, "Track 1", artist_id=100, album_id=200, track_number=1)
        db.upsert_track(301, "Track 2", artist_id=100, album_id=200, track_number=2)

        result = db.get_album_with_tracks(200)
        assert result is not None
        assert len(result['tracks']) == 2


class TestSettings:
    """Test the settings table CRUD and optimistic concurrency."""

    def setup_method(self):
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()
        if hasattr(db._local, 'connection') and db._local.connection:
            db._local.connection.close()
            db._local.connection = None
        db.init_db()

    def teardown_method(self):
        if hasattr(db._local, 'connection') and db._local.connection:
            db._local.connection.close()
            db._local.connection = None
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()

    def test_settings_table_exists(self):
        conn = db.get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row['name'] for row in tables}
        assert 'settings' in table_names
        assert 'settings_meta' in table_names

    def test_defaults_seeded(self):
        settings = db.get_all_settings()
        assert settings['quality'] == 'LOSSLESS'
        assert settings['sync_time'] == '04:00'
        assert settings['active_downloads'] == 3
        assert settings['use_musicbrainz'] is True
        assert settings['run_beets'] is False
        assert settings['embed_lyrics'] is False
        assert 'version' in settings

    def test_get_all_settings_types(self):
        """Booleans should be Python bools, ints should be Python ints."""
        settings = db.get_all_settings()
        assert isinstance(settings['use_musicbrainz'], bool)
        assert isinstance(settings['active_downloads'], int)
        assert isinstance(settings['quality'], str)

    def test_update_settings_bumps_version(self):
        v1 = db.get_settings_version()
        v2 = db.update_settings({'quality': 'HI_RES_LOSSLESS'}, v1)
        assert v2 == v1 + 1
        assert db.get_settings_version() == v2

    def test_update_settings_conflict(self):
        """Updating with a stale version should raise StaleSettingsError."""
        v1 = db.get_settings_version()
        db.update_settings({'quality': 'MP3_256'}, v1)

        import pytest
        with pytest.raises(db.StaleSettingsError) as exc_info:
            db.update_settings({'quality': 'LOW'}, v1)  # stale

        assert exc_info.value.current_version == v1 + 1

    def test_update_settings_applies_values(self):
        v1 = db.get_settings_version()
        db.update_settings({
            'quality': 'MP3_256',
            'use_musicbrainz': False,
            'active_downloads': 5,
        }, v1)

        settings = db.get_all_settings()
        assert settings['quality'] == 'MP3_256'
        assert settings['use_musicbrainz'] is False
        assert settings['active_downloads'] == 5

    def test_get_setting(self):
        assert db.get_setting('quality') == 'LOSSLESS'
        assert db.get_setting('nonexistent_key') is None

    def test_seed_defaults_idempotent(self):
        """Re-seeding should not overwrite existing values."""
        v1 = db.get_settings_version()
        db.update_settings({'quality': 'MP3_256'}, v1)
        db._seed_default_settings()  # re-seed
        assert db.get_setting('quality') == 'MP3_256'  # should NOT be overwritten

