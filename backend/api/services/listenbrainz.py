import asyncio
import json
from api.state import lb_progress_queues
from api.utils.logging import log_info, log_error, log_success
from api.utils.text import fix_unicode
from api.services.search import search_track_with_fallback
from api.clients.listenbrainz import ListenBrainzClient

async def listenbrainz_generate_with_progress(username: str, playlist_type: str, progress_id: str, validate: bool = True):
    queue = asyncio.Queue()
    lb_progress_queues[progress_id] = queue
    
    client = ListenBrainzClient()
    
    try:
        display_name = playlist_type.replace("-", " ").title()
        await queue.put({
            "type": "info",
            "message": f"Fetching {display_name} for {username}...",
            "progress": 0,
            "total": 0
        })
        
        # Use the requested playlist type
        tracks = await client.get_playlist_by_type(username, playlist_type)
        
        if not tracks:
            # Fallback for old 'weekly-jams' request potentially checking exploration? 
            # No, let's be strict now or the UI selector doesn't mean much.
            if playlist_type == "weekly-jams":
                 # If weekly jams specifically requested and not found, check exploration?
                 # Nah, let user select it.
                 pass
            
            raise Exception(f"No playlist found for type '{display_name}' for this user.")

        for track in tracks:
            track.title = fix_unicode(track.title)
            track.artist = fix_unicode(track.artist)
            if track.album:
                track.album = fix_unicode(track.album)
        
        await queue.put({
            "type": "info",
            "message": f"Found {len(tracks)} tracks from ListenBrainz",
            "progress": 0,
            "total": len(tracks)
        })
        
        validated_tracks = []
        if validate:
            for i, track in enumerate(tracks, 1):
                display_text = f"{track.artist} - {track.title}"
                
                await queue.put({
                    "type": "validating",
                    "message": f"Validating: {display_text}",
                    "progress": i,
                    "total": len(tracks),
                    "current_track": {
                        "artist": track.artist,
                        "title": track.title
                    }
                })
                
                log_info(f"[{i}/{len(tracks)}] Validating: {display_text}")
                
                await search_track_with_fallback(track.artist, track.title, track)
                
                validated_tracks.append({
                    "title": track.title,
                    "artist": track.artist,
                    "mbid": track.mbid,
                    "tidal_id": track.tidal_id,
                    "tidal_artist_id": track.tidal_artist_id,
                    "tidal_album_id": track.tidal_album_id,
                    "tidal_exists": track.tidal_exists,
                    "album": track.album,
                    "cover": getattr(track, 'cover', None)
                })
                
                await asyncio.sleep(0.1)
        else:
             for track in tracks:
                validated_tracks.append({
                    "title": track.title,
                    "artist": track.artist,
                    "mbid": track.mbid,
                    "tidal_id": None,
                    "tidal_artist_id": None,
                    "tidal_album_id": None,
                    "tidal_exists": False,
                    "album": track.album,
                    "cover": None
                })
             
             await queue.put({
                "type": "info",
                "message": "Skipping validation as requested.",
                "progress": len(tracks),
                "total": len(tracks)
             })
        
        found_count = sum(1 for t in validated_tracks if t.get("tidal_exists"))
        
        log_info(f"Validation complete: {found_count}/{len(validated_tracks)} found on Tidal")
        
        await queue.put({
            "type": "complete",
            "message": f"Validation complete: {found_count}/{len(validated_tracks)} found on Tidal",
            "progress": len(tracks),
            "total": len(tracks),
            "tracks": validated_tracks,
            "found_count": found_count
        })
        
    except Exception as e:
        log_error(f"ListenBrainz generation error: {str(e)}")
        await queue.put({
            "type": "error",
            "message": str(e),
            "progress": 0,
            "total": 0
        })
    finally:
        await client.close()
        await queue.put(None)
