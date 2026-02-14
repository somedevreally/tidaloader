"""
Global Queue Manager for Universal Download Queue

This module manages a shared download queue across all clients.
It provides thread-safe operations backed by SQLite for persistence.
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from threading import Lock

from api.utils.logging import log_info, log_error, log_warning, log_step
import database as db


MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3"))
QUEUE_AUTO_PROCESS = os.getenv("QUEUE_AUTO_PROCESS", "true").lower() == "true"


@dataclass
class QueueItem:
    """Represents a track in the download queue"""
    track_id: int
    title: str
    artist: str
    album: str = ""
    album_id: Optional[int] = None
    track_number: Optional[int] = None
    cover: Optional[str] = None
    quality: str = "HIGH"
    added_at: str = ""
    added_by: str = "unknown"

    tidal_track_id: Optional[str] = None
    tidal_artist_id: Optional[str] = None
    tidal_album_id: Optional[str] = None

    album_artist: Optional[str] = None

    target_format: Optional[str] = None
    bitrate_kbps: Optional[int] = None
    run_beets: bool = False
    embed_lyrics: bool = False
    organization_template: str = "{Artist}/{Album}/{TrackNumber} - {Title}"
    group_compilations: bool = True
    use_musicbrainz: bool = True
    auto_clean: bool = False

    def __post_init__(self):
        if not self.added_at:
            self.added_at = datetime.now().isoformat()


class QueueManager:
    """
    Singleton manager for the global download queue.
    Backed by SQLite for fast, unlimited persistence.

    Provides:
    - Thread-safe queue operations
    - Persistence via SQLite
    - Auto-processing with configurable concurrency
    - Manual start/stop mode option
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._active: Dict[int, Dict[str, Any]] = {}  # track_id -> {progress, status, item}

        self._processing = False
        self._process_task: Optional[asyncio.Task] = None
        self._queue_lock = asyncio.Lock()

        log_info(f"Queue Manager initialized (SQLite): max_concurrent={MAX_CONCURRENT_DOWNLOADS}, auto_process={QUEUE_AUTO_PROCESS}")

    def get_state(self) -> Dict[str, Any]:
        """Get current queue state for API response"""
        queued = db.get_queue_items("queued")
        completed_items = db.get_queue_items("completed")
        failed_items = db.get_queue_items("failed")

        return {
            'queue': [self._db_row_to_queue_dict(row) for row in queued],
            'active': [
                {
                    'track_id': tid,
                    'progress': info.get('progress', 0),
                    'status': info.get('status', 'downloading'),
                    **asdict(info.get('item', QueueItem(track_id=tid, title='', artist='')))
                }
                for tid, info in self._active.items()
            ],
            'completed': [self._db_row_to_result_dict(row) for row in completed_items[-50:]],
            'completed_total': len(completed_items),  # Total count for accurate display
            'failed': [self._db_row_to_failed_dict(row) for row in failed_items],
            'settings': {
                'max_concurrent': MAX_CONCURRENT_DOWNLOADS,
                'auto_process': QUEUE_AUTO_PROCESS,
                'is_processing': self._processing
            }
        }

    async def add_to_queue(self, item: QueueItem) -> bool:
        """Add a track to the queue"""
        async with self._queue_lock:
            # Check if already active in memory
            if item.track_id in self._active:
                log_warning(f"Track {item.track_id} already downloading")
                return False

            # Try to add to DB (handles queued/active duplicate check)
            row_id = db.add_queue_item(
                track_id=item.track_id,
                title=item.title,
                artist=item.artist,
                album=item.album,
                album_id=item.album_id,
                track_number=item.track_number,
                cover=item.cover,
                quality=item.quality,
                added_by=item.added_by,
                target_format=item.target_format,
                bitrate_kbps=item.bitrate_kbps,
                run_beets=item.run_beets,
                embed_lyrics=item.embed_lyrics,
                organization_template=item.organization_template,
                group_compilations=item.group_compilations,
                use_musicbrainz=item.use_musicbrainz,
                auto_clean=item.auto_clean,
                tidal_track_id=item.tidal_track_id,
                tidal_artist_id=item.tidal_artist_id,
                tidal_album_id=item.tidal_album_id,
                album_artist=item.album_artist,
            )

            if row_id is None:
                log_warning(f"Track {item.track_id} already in queue")
                return False

            log_info(f"Added to queue: {item.title} by {item.artist}")

            # Auto-trigger processing if enabled
            if QUEUE_AUTO_PROCESS and not self._processing:
                asyncio.create_task(self.start_processing())

            return True

    async def add_many_to_queue(self, items: List[QueueItem]) -> Dict[str, Any]:
        """Add multiple tracks to the queue"""
        added = 0
        skipped = 0

        for item in items:
            if await self.add_to_queue(item):
                added += 1
            else:
                skipped += 1

        return {'added': added, 'skipped': skipped}

    async def remove_from_queue(self, track_id: int) -> bool:
        """Remove a track from the queue"""
        async with self._queue_lock:
            return db.delete_queue_item(track_id)

    async def clear_queue(self) -> int:
        """Clear all queued items (not active)"""
        async with self._queue_lock:
            return db.clear_queue_items("queued")

    async def clear_completed(self) -> int:
        """Clear completed items"""
        return db.clear_queue_items("completed")

    async def clear_failed(self) -> int:
        """Clear failed items"""
        return db.clear_queue_items("failed")

    async def retry_failed(self) -> int:
        """Move all failed items back to queue"""
        count = db.requeue_failed_items()
        if count > 0 and QUEUE_AUTO_PROCESS and not self._processing:
            asyncio.create_task(self.start_processing())
        return count

    async def retry_single(self, track_id: int) -> bool:
        """Retry a single failed item"""
        success = db.requeue_single_failed(track_id)
        if success and QUEUE_AUTO_PROCESS and not self._processing:
            asyncio.create_task(self.start_processing())
        return success

    def update_active_progress(self, track_id: int, progress: int, status: str = 'downloading'):
        """Update progress of an active download"""
        if track_id in self._active:
            self._active[track_id]['progress'] = progress
            self._active[track_id]['status'] = status

    def mark_completed(self, track_id: int, filename: str, metadata: Dict = None):
        """Mark a download as completed"""
        if track_id in self._active:
            item = self._active[track_id].get('item')

            # Skip history if auto_clean is enabled
            if item and item.auto_clean:
                log_info(f"Auto-cleaning completed item: {item.title}")
                db.update_queue_item_status(track_id, "completed",
                                           filename=filename,
                                           metadata_json=json.dumps(metadata) if metadata else None)
                # Then delete the completed entry
                db.clear_queue_items("completed")
            else:
                db.update_queue_item_status(track_id, "completed",
                                           filename=filename,
                                           metadata_json=json.dumps(metadata) if metadata else None)

            # Record in tracks/artists/albums tables for the library
            if metadata:
                self._record_download(track_id, metadata, filename)

            del self._active[track_id]

    def mark_failed(self, track_id: int, error: str):
        """Mark a download as failed"""
        if track_id in self._active:
            db.update_queue_item_status(track_id, "failed", error=error)
            del self._active[track_id]

    def _record_download(self, track_id: int, metadata: Dict, filename: str):
        """Record a completed download in the normalized library tables."""
        try:
            # Extract IDs, converting to int safely
            artist_id = self._safe_int(metadata.get('tidal_artist_id'))
            album_id = self._safe_int(metadata.get('tidal_album_id'))
            tidal_track_id = self._safe_int(metadata.get('tidal_track_id')) or track_id

            # Upsert artist
            if artist_id:
                artist_name = metadata.get('album_artist') or metadata.get('artist', 'Unknown Artist')
                db.upsert_artist(artist_id, artist_name)

            # Upsert album (cover_url stored per-album, not per-track)
            if album_id:
                album_artist = metadata.get('album_artist') or metadata.get('artist')
                album_artist_id = artist_id
                # If album artist differs from track artist, we might create a separate artist entry
                # but for now we link to the same artist_id

                # Determine album type
                album_type = None
                if metadata.get('compilation'):
                    album_type = 'COMPILATION'

                db.upsert_album(
                    tidal_id=album_id,
                    title=metadata.get('album', 'Unknown Album'),
                    artist_id=album_artist_id,
                    cover_url=metadata.get('cover_url'),
                    release_date=metadata.get('date'),
                    total_tracks=metadata.get('total_tracks'),
                    total_discs=metadata.get('total_discs'),
                    album_type=album_type,
                )

            # Upsert track
            db.upsert_track(
                tidal_id=tidal_track_id,
                title=metadata.get('title', 'Unknown'),
                artist_id=artist_id,
                album_id=album_id,
                track_number=metadata.get('track_number'),
                disc_number=metadata.get('disc_number'),
                duration=metadata.get('duration'),
                file_path=metadata.get('final_path') or filename,
                file_format=(metadata.get('file_ext') or '.flac').lstrip('.'),
                quality=metadata.get('quality'),
                musicbrainz_track_id=metadata.get('musicbrainz_trackid'),
            )
        except Exception as e:
            log_warning(f"Failed to record download in library: {e}")

    @staticmethod
    def _safe_int(value) -> Optional[int]:
        """Safely convert a value to int, returning None on failure."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    async def start_processing(self):
        """Start the queue processing loop"""
        if self._processing:
            log_info("Queue already processing")
            return

        self._processing = True
        log_info("Starting queue processing...")

        try:
            while self._processing:
                # Check if there's work to do
                queued_items = db.get_queue_items("queued")
                if not queued_items and not self._active:
                    break

                # Fill up to max concurrent
                async with self._queue_lock:
                    slots_available = MAX_CONCURRENT_DOWNLOADS - len(self._active)
                    if slots_available > 0 and queued_items:
                        items_to_start = db.pop_queued_items(slots_available)
                        for row in items_to_start:
                            item = self._db_row_to_queue_item(row)
                            self._active[item.track_id] = {
                                'progress': 0,
                                'status': 'starting',
                                'item': item
                            }
                            # Start download task
                            asyncio.create_task(self._process_item(item))

                # Wait a bit before checking again
                await asyncio.sleep(1)
        except Exception as e:
            log_error(f"Queue processing error: {e}")
        finally:
            self._processing = False
            log_info("Queue processing stopped")

    async def stop_processing(self):
        """Stop the queue processing loop (won't cancel active downloads)"""
        self._processing = False
        log_info("Queue processing stop requested")

    async def _process_item(self, item: QueueItem):
        """Process a single queue item - actual download logic"""
        from api.routers.downloads import process_queue_item

        try:
            await process_queue_item(item)
        except Exception as e:
            log_error(f"Failed to process queue item {item.track_id}: {e}")
            self.mark_failed(item.track_id, str(e))

    # ----- Helper conversions -----

    @staticmethod
    def _db_row_to_queue_item(row: Dict) -> QueueItem:
        """Convert a database row to a QueueItem dataclass."""
        return QueueItem(
            track_id=row["track_id"],
            title=row.get("title", ""),
            artist=row.get("artist", ""),
            album=row.get("album", ""),
            album_id=row.get("album_id"),
            track_number=row.get("track_number"),
            cover=row.get("cover"),
            quality=row.get("quality", "HIGH"),
            added_at=row.get("added_at", ""),
            added_by=row.get("added_by", "unknown"),
            tidal_track_id=row.get("tidal_track_id"),
            tidal_artist_id=row.get("tidal_artist_id"),
            tidal_album_id=row.get("tidal_album_id"),
            album_artist=row.get("album_artist"),
            target_format=row.get("target_format"),
            bitrate_kbps=row.get("bitrate_kbps"),
            run_beets=bool(row.get("run_beets", 0)),
            embed_lyrics=bool(row.get("embed_lyrics", 0)),
            organization_template=row.get("organization_template", "{Artist}/{Album}/{TrackNumber} - {Title}"),
            group_compilations=bool(row.get("group_compilations", 1)),
            use_musicbrainz=bool(row.get("use_musicbrainz", 1)),
            auto_clean=bool(row.get("auto_clean", 0)),
        )

    @staticmethod
    def _db_row_to_queue_dict(row: Dict) -> Dict:
        """Convert a DB row to the dict format expected by the API."""
        return {
            'track_id': row['track_id'],
            'title': row.get('title', ''),
            'artist': row.get('artist', ''),
            'album': row.get('album', ''),
            'album_id': row.get('album_id'),
            'track_number': row.get('track_number'),
            'cover': row.get('cover'),
            'quality': row.get('quality', 'HIGH'),
            'added_at': row.get('added_at', ''),
            'added_by': row.get('added_by', 'unknown'),
            'tidal_track_id': row.get('tidal_track_id'),
            'tidal_artist_id': row.get('tidal_artist_id'),
            'tidal_album_id': row.get('tidal_album_id'),
            'album_artist': row.get('album_artist'),
            'target_format': row.get('target_format'),
            'bitrate_kbps': row.get('bitrate_kbps'),
            'run_beets': bool(row.get('run_beets', 0)),
            'embed_lyrics': bool(row.get('embed_lyrics', 0)),
            'organization_template': row.get('organization_template', '{Artist}/{Album}/{TrackNumber} - {Title}'),
            'group_compilations': bool(row.get('group_compilations', 1)),
            'use_musicbrainz': bool(row.get('use_musicbrainz', 1)),
            'auto_clean': bool(row.get('auto_clean', 0)),
        }

    @staticmethod
    def _db_row_to_result_dict(row: Dict) -> Dict:
        """Convert a completed DB row to the API result dict."""
        return {
            'track_id': row['track_id'],
            'title': row.get('title', ''),
            'artist': row.get('artist', ''),
            'album': row.get('album', ''),
            'filename': row.get('filename', ''),
            'completed_at': row.get('completed_at', ''),
            'metadata': json.loads(row['metadata_json']) if row.get('metadata_json') else {},
        }

    @staticmethod
    def _db_row_to_failed_dict(row: Dict) -> Dict:
        """Convert a failed DB row to the API result dict."""
        return {
            'track_id': row['track_id'],
            'title': row.get('title', ''),
            'artist': row.get('artist', ''),
            'album': row.get('album', ''),
            'error': row.get('error', ''),
            'failed_at': row.get('completed_at', ''),
            'quality': row.get('quality', 'HIGH'),
            'target_format': row.get('target_format'),
            'bitrate_kbps': row.get('bitrate_kbps'),
            'run_beets': bool(row.get('run_beets', 0)),
            'embed_lyrics': bool(row.get('embed_lyrics', 0)),
        }


queue_manager = QueueManager()
