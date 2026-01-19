import asyncio
import logging
import aiofiles
from pathlib import Path
from typing import List, Dict, Any
from api.state import lb_progress_queues
from api.utils.logging import log_info, log_error, log_success
from api.utils.text import fix_unicode
from api.services.search import search_track_with_fallback
from api.services.files import get_output_relative_path, sanitize_path_component
from api.settings import DOWNLOAD_DIR, PLAYLISTS_DIR
from api.clients.spotify import SpotifyClient

logger = logging.getLogger(__name__)

from typing import List, Dict, Any, Optional, Callable, Awaitable

async def fetch_and_validate_spotify_playlist(
    spotify_id: str,
    progress_callback: Optional[Callable[[Dict], Awaitable[None]]] = None,
    validate: bool = True
) -> List[Dict]:
    """
    Reusable function to fetch and optionally validate Spotify playlist.
    Returns a list of normalized track dictionaries.
    """
    client = SpotifyClient()
    
    import time
    from api.state import import_states

    # Initialize state if ID provided
    progress_id = None
    # We need progress_id to update state. 
    # But this function signature doesn't accept progress_id except via callback closure?
    # Refactor: pass update_state callback instead of progress_callback?
    # Or keep callback but inside the callback update state.
    
    async def report(data: Dict):
        # Add timestamp
        data['timestamp'] = time.time()
        
        # Call legacy callback (queue) if present
        if progress_callback:
            await progress_callback(data)
            
    # NOTE: The caller (playlist_manager) defines the callback.
    # We should update playlist_manager to update the state within the callback.
    # This keeps service clean.


    try:
        await report({
            "type": "info",
            "message": f"Fetching Spotify playlist {spotify_id}...",
            "progress": 0,
            "total": 0
        })
        
        # specific to spotify: get tracks
        spotify_tracks, is_limited = await client.get_playlist_tracks(spotify_id)
        
        if not spotify_tracks:
            raise Exception("No tracks found or playlist is private/invalid.")

        total_tracks = len(spotify_tracks)
        limit_msg = " [Truncated to 100 due to guest limit]" if is_limited else ""
        
        msg = f"Found {total_tracks} tracks{limit_msg}. "
        msg += "Starting validation..." if validate else "Processing..."
        
        await report({
            "type": "info",
            "message": msg,
            "progress": 0,
            "total": total_tracks
        })
        
        validated_tracks = []
        matches_found = 0
        
        for i, s_track in enumerate(spotify_tracks, 1):
            # Clean up text
            title = fix_unicode(s_track.title)
            artist = fix_unicode(s_track.artist)
            album = fix_unicode(s_track.album) if s_track.album else None
            
            # Mutable container for search results
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
                    self.track_number = None # Initialize track_number

            track_obj = TrackContainer()
            
            # Perform search
            if validate:
                await search_track_with_fallback(artist, title, track_obj)
                
                # Check match and increment counter
                if track_obj.tidal_exists:
                    matches_found += 1
                
                display_text = f"{artist} - {title}"
                await report({
                    "type": "validating",
                    "message": f"Validating: {display_text}",
                    "progress": i,
                    "total": total_tracks,
                    "matches_found": matches_found,
                    "current_track": {
                        "artist": artist,
                        "title": title,
                        "matched": track_obj.tidal_exists
                    }
                })
                # Small delay
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
                "track_number": getattr(track_obj, 'track_number', None),
                "db_id": s_track.spotify_id
            })

        found_count = sum(1 for t in validated_tracks if t["tidal_exists"])
        
        await report({
            "type": "analysis_complete",
            "message": f"Process complete: {found_count}/{total_tracks} matched" if validate else f"Fetched {total_tracks} from Spotify",
            "progress": total_tracks,
            "total": total_tracks,
            "tracks": validated_tracks,
            "found_count": found_count,
            "is_limited": is_limited
        })
        
        return validated_tracks

    except Exception as e:
        log_error(f"Spotify processing error: {str(e)}")
        await report({
            "type": "error",
            "message": str(e),
            "progress": 0,
            "total": 0
        })
        raise
    finally:
        await client.close()

async def process_spotify_playlist(playlist_uuid: str, progress_id: str, should_validate: bool = False):
    """
    Process spotify playlist and update in-memory state for polling.
    """
    from api.state import import_states
    import time
    
    # Initialize state
    import_states[progress_id] = {
        "status": "active",
        "messages": [],
        "current": 0,
        "total": 0,
        "matches": 0,
        "tracks": []
    }
    
    async def progress_adapter(data):
        if progress_id not in import_states:
            return

        state = import_states[progress_id]
        
        # Append message if present
        if data.get("message"):
            state["messages"].append({
                "text": data["message"],
                "type": data.get("type", "info"),
                "timestamp": data.get("timestamp", time.time())
            })
            
        # Update progress stats
        if "progress" in data:
            state["current"] = data["progress"]
        if "total" in data:
            state["total"] = data["total"]
        if "matches_found" in data:
            state["matches"] = data["matches_found"]
            
        # Handle completion states
        msg_type = data.get("type")
        
        if msg_type == "analysis_complete":
            state["status"] = "waiting_confirmation"
            if "tracks" in data:
                state["tracks"] = data["tracks"]
                
        elif msg_type == "error":
            state["status"] = "error"
            
    try:
        await fetch_and_validate_spotify_playlist(
            playlist_uuid,
            progress_callback=progress_adapter,
            validate=should_validate
        )
    except Exception as e:
        # Ensure error state is set even if fetch_and_validate raises before reporting
        if progress_id in import_states:
            import_states[progress_id]["status"] = "error"
            import_states[progress_id]["messages"].append({
                "text": str(e),
                "type": "error",
                "timestamp": time.time()
            })



async def generate_spotify_m3u8(playlist_name: str, tracks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate an m3u8 playlist file from validated Spotify tracks.
    Only includes tracks that:
    1. Have tidal_exists = True (validated on Tidal)
    2. Actually exist as downloaded files on disk
    
    Returns info about the generated playlist.
    """
    if not playlist_name or not playlist_name.strip():
        raise ValueError("Playlist name is required")
    
    if not tracks:
        raise ValueError("No tracks provided")
    
    # Filter to only tracks that exist on Tidal
    valid_tracks = [t for t in tracks if t.get('tidal_exists') and t.get('tidal_id')]
    
    if not valid_tracks:
        raise ValueError("No validated tracks found. Please check tracks on Tidal first.")
    
    logger.info(f"Generating m3u8 for '{playlist_name}' with {len(valid_tracks)}/{len(tracks)} validated tracks")
    
    # Sanitize playlist name for folder/file
    safe_name = sanitize_path_component(playlist_name.strip())
    
    # Create playlist folder structure (same as Tidal playlists)
    playlist_folder = PLAYLISTS_DIR / safe_name
    playlist_folder.mkdir(parents=True, exist_ok=True)
    
    m3u8_filename = f"{safe_name}.m3u8"
    playlist_file = playlist_folder / m3u8_filename
    
    # Build m3u8 content
    m3u8_lines = ["#EXTM3U", "# Source: Spotify"]
    included_count = 0
    skipped_count = 0
    
    for track in valid_tracks:
        title = track.get('title', 'Unknown Title')
        artist = track.get('artist', 'Unknown Artist')
        album = track.get('album', 'Unknown Album')
        
        # Build metadata to find the file path
        metadata = {
            'artist': artist,
            'album': album,
            'title': title,
            'track_number': None,  # We don't have this from Spotify data
            'album_artist': None,
            'compilation': False
        }
        
        found_rel_path = None
        
        # Check for existing files in various formats
        for ext in ['.flac', '.m4a', '.mp3', '.opus']:
            metadata['file_ext'] = ext
            rel_path = get_output_relative_path(metadata)
            full_path = DOWNLOAD_DIR / rel_path
            
            if full_path.exists():
                found_rel_path = rel_path
                logger.debug(f"Found file: {rel_path}")
                break
        
        if found_rel_path:
            # Duration is optional (we might not have it)
            duration = track.get('duration_ms', -1000) // 1000 if track.get('duration_ms') else -1
            m3u8_lines.append(f"#EXTINF:{duration},{artist} - {title}")
            # Use ../../ because m3u8 is in tidaloader_playlists/{PlaylistName}/
            m3u8_lines.append(f"../../{found_rel_path}")
            included_count += 1
        else:
            # File not downloaded yet - skip it
            logger.debug(f"File not found for: {artist} - {title}")
            skipped_count += 1
    
    if included_count == 0:
        raise ValueError("No downloaded tracks found. Please download tracks first before generating the playlist.")
    
    # Write the m3u8 file
    try:
        async with aiofiles.open(playlist_file, 'w', encoding='utf-8') as f:
            await f.write("\n".join(m3u8_lines))
        
        log_success(f"M3U8 written to {playlist_file} with {included_count} tracks")
        
        return {
            "status": "success",
            "message": f"Playlist '{playlist_name}' created with {included_count} tracks",
            "path": str(playlist_file.relative_to(PLAYLISTS_DIR)),
            "included_count": included_count,
            "skipped_count": skipped_count,
            "total_validated": len(valid_tracks)
        }
        
    except Exception as e:
        logger.error(f"Failed to write m3u8: {e}")
        raise
