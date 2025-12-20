import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass
from itertools import chain
import asyncio
from concurrent.futures import ThreadPoolExecutor

from spotapi import Public

logger = logging.getLogger(__name__)

@dataclass
class SpotifyTrack:
    title: str
    artist: str
    album: Optional[str] = None
    duration_ms: Optional[int] = None
    spotify_id: Optional[str] = None

class SpotifyClient:
    """
    Client for accessing Spotify playlist data without user credentials.
    Uses SpotAPI library which accesses Spotify's partner API for full playlist access.
    """
    
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=2)

    async def close(self):
        self._executor.shutdown(wait=False)

    def _fetch_playlist_sync(self, playlist_id: str) -> List[SpotifyTrack]:
        """
        Synchronous method to fetch all tracks using SpotAPI.
        SpotAPI uses the partner API which has no 100 track limit.
        """
        tracks = []
        
        try:
            # Get all chunks from SpotAPI (handles pagination internally, up to 343 per chunk)
            chunks = list(Public.playlist_info(playlist_id))
            all_items = list(chain.from_iterable([chunk['items'] for chunk in chunks]))
            
            for item in all_items:
                track_data = item.get('itemV2', {}).get('data', {})
                typename = track_data.get('__typename')
                
                # Skip non-track items (LocalTrack, RestrictedContent, NotFound, Episode)
                if typename != 'Track':
                    continue
                
                # Extract track info
                name = track_data.get('name', 'Unknown Title')
                
                # Get artists
                artists_data = track_data.get('artists', {}).get('items', [])
                if artists_data:
                    artist_names = [a.get('profile', {}).get('name', '') for a in artists_data]
                    artist_str = ", ".join(filter(None, artist_names)) or "Unknown Artist"
                else:
                    artist_str = "Unknown Artist"
                
                # Get album
                album_data = track_data.get('albumOfTrack', {})
                album_name = album_data.get('name')
                
                # Get duration
                duration_data = track_data.get('trackDuration', {})
                duration_ms = duration_data.get('totalMilliseconds')
                if duration_ms:
                    duration_ms = int(duration_ms)
                
                # Get Spotify ID from URI (format: spotify:track:XXXXX)
                uri = track_data.get('uri', '')
                spotify_id = uri.split(':')[-1] if uri.startswith('spotify:track:') else None
                
                tracks.append(SpotifyTrack(
                    title=name,
                    artist=artist_str,
                    album=album_name,
                    duration_ms=duration_ms,
                    spotify_id=spotify_id
                ))
                
            logger.info(f"Fetched {len(tracks)} tracks from Spotify via SpotAPI")
            return tracks
            
        except Exception as e:
            logger.error(f"Error fetching playlist with SpotAPI: {e}")
            raise

    async def get_playlist_tracks(self, playlist_id: str) -> Tuple[List[SpotifyTrack], bool]:
        """
        Fetch all tracks from a playlist using SpotAPI.
        Returns: (tracks, is_limited)
        is_limited is always False with SpotAPI as it has no practical limit.
        """
        loop = asyncio.get_event_loop()
        
        try:
            tracks = await loop.run_in_executor(
                self._executor,
                self._fetch_playlist_sync,
                playlist_id
            )
            return tracks, False
        except Exception as e:
            logger.error(f"Failed to fetch playlist: {e}")
            return [], False
