import asyncio
import logging
from api.state import lb_progress_queues
from api.utils.logging import log_info, log_error, log_success
from api.utils.text import fix_unicode
from api.services.search import search_track_with_fallback
from api.clients.spotify import SpotifyClient

logger = logging.getLogger(__name__)

async def process_spotify_playlist(playlist_uuid: str, progress_id: str, should_validate: bool = False):
    queue = asyncio.Queue()
    lb_progress_queues[progress_id] = queue
    
    client = SpotifyClient()
    
    try:
        await queue.put({
            "type": "info",
            "message": f"Fetching Spotify playlist {playlist_uuid}...",
            "progress": 0,
            "total": 0
        })
        
        # specific to spotify: get tracks
        # Returns (tracks, is_limited)
        spotify_tracks, is_limited = await client.get_playlist_tracks(playlist_uuid)
        
        if not spotify_tracks:
            raise Exception("No tracks found or playlist is private/invalid.")

        total_tracks = len(spotify_tracks)
        
        limit_msg = " [Truncated to 100 due to guest limit]" if is_limited else ""
        
        # If validating, show starting validation message
        if should_validate:
             await queue.put({
                "type": "info",
                "message": f"Found {total_tracks} tracks{limit_msg}. Starting validation...",
                "progress": 0,
                "total": total_tracks
            })
        else:
            await queue.put({
                "type": "info",
                "message": f"Found {total_tracks} tracks{limit_msg}. Processing...",
                "progress": 0,
                "total": total_tracks
            })
        
        validated_tracks = []
        
        for i, s_track in enumerate(spotify_tracks, 1):
            # Clean up text
            title = fix_unicode(s_track.title)
            artist = fix_unicode(s_track.artist)
            album = fix_unicode(s_track.album) if s_track.album else None
            
            # Create a mutable object to hold results, similar to PlaylistTrack
            # We use a simple class or dict wrapper for compatibility with search_track_with_fallback
            class TrackContainer:
                def __init__(self):
                    self.title = title
                    self.artist = artist
                    self.album = album
                    self.tidal_id = None
                    self.tidal_artist_id = None
                    self.tidal_album_id = None
                    self.tidal_exists = False
                    self.cover = None
            
            track_obj = TrackContainer()
            
            if should_validate:
                display_text = f"{artist} - {title}"
                await queue.put({
                    "type": "validating",
                    "message": f"Validating: {display_text}",
                    "progress": i,
                    "total": total_tracks,
                    "current_track": {
                        "artist": artist,
                        "title": title
                    }
                })
                # Perform search
                await search_track_with_fallback(artist, title, track_obj)
                # Small delay to prevent rate limit hammering (internal queue)
                await asyncio.sleep(0.05)
            
            validated_tracks.append({
                "title": track_obj.title,
                "artist": track_obj.artist,
                "album": track_obj.album,
                "tidal_id": track_obj.tidal_id,
                "tidal_artist_id": track_obj.tidal_artist_id,
                "tidal_album_id": track_obj.tidal_album_id,
                "tidal_exists": track_obj.tidal_exists,
                "cover": track_obj.cover,
                "db_id": s_track.spotify_id # Keep original ID for reference
            })

        found_count = sum(1 for t in validated_tracks if t["tidal_exists"])
        
        await queue.put({
            "type": "complete",
            "message": f"Process complete: {found_count}/{total_tracks} matched" if should_validate else f"Fetched {total_tracks} from Spotify",
            "progress": total_tracks,
            "total": total_tracks,
            "tracks": validated_tracks,
            "found_count": found_count,
            "is_limited": is_limited
        })

    except Exception as e:
        log_error(f"Spotify processing error: {str(e)}")
        await queue.put({
            "type": "error",
            "message": str(e),
            "progress": 0,
            "total": 0
        })
    finally:
        await client.close()
        await queue.put(None) # Signal end of stream
