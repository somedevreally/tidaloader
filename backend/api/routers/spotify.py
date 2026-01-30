import uuid
import json
import asyncio
import re
import logging
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.models import SpotifyGenerateRequest, SpotifyM3U8Request
from api.auth import require_auth, require_auth_stream
from api.state import lb_progress_queues
from api.services.spotify import process_spotify_playlist, generate_spotify_m3u8

router = APIRouter()
logger = logging.getLogger(__name__)

from api.clients.spotify import SpotifyClient

@router.get("/api/spotify/search")
async def search_spotify_playlists(
    query: str,
    user: str = Depends(require_auth)
):
    """Search for Spotify playlists"""
    client = SpotifyClient()
    try:
        # Check if query is a direct URL/URI
        if "spotify.com" in query or "spotify:playlist:" in query:
            # It's likely a URL/URI
            playlist_id = extract_spotify_id(query)
            if playlist_id and len(playlist_id) > 5: # Basic sanity check
                specific_playlist = await client.get_playlist_metadata(playlist_id)
                if specific_playlist:
                    return {"items": [specific_playlist]}
                # If specific fetch fails or returns None, fallback to empty or search? 
                # Let's return empty to avoid searching for the URL string which gives garbage.
                return {"items": []}

        playlists = await client.search_playlists(query)
        return {"items": playlists}
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await client.close()

@router.get("/api/spotify/playlist/{playlist_id}")
async def get_spotify_playlist_tracks(
    playlist_id: str,
    user: str = Depends(require_auth)
):
    """Get tracks from a Spotify playlist"""
    client = SpotifyClient()
    try:
        tracks, _ = await client.get_playlist_tracks(playlist_id)
        return {"items": tracks}
    except Exception as e:
        logger.error(f"Failed to fetch playlist tracks: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await client.close()

def extract_spotify_id(url: str) -> str:
    # Match playlist ID from various formats
    # https://open.spotify.com/playlist/37i9dQZF1DX5Ejj077clxu
    # spotify:playlist:37i9dQZF1DX5Ejj077clxu
    
    # Try Regex
    match = re.search(r'playlist[:/]([a-zA-Z0-9]+)', url)
    if match:
        return match.group(1)
    
    # If it looks like a clean ID (22 chars alphanumeric usually)
    if re.match(r'^[a-zA-Z0-9]{22}$', url):
        return url
        
    return url.split('/')[-1].split('?')[0] # Fallback basic split

@router.post("/api/spotify/generate")
async def generate_spotify_playlist(
    request: SpotifyGenerateRequest,
    background_tasks: BackgroundTasks,
    username: str = Depends(require_auth)
):
    playlist_id = extract_spotify_id(request.playlist_url)
    if not playlist_id:
         raise HTTPException(status_code=400, detail="Invalid Spotify Playlist URL")

    progress_id = str(uuid.uuid4())
    
    background_tasks.add_task(
        process_spotify_playlist,
        playlist_id,
        progress_id,
        request.should_validate
    )
    
    return {"progress_id": progress_id}

@router.get("/api/spotify/progress/{progress_id}")
async def get_spotify_progress(
    progress_id: str,
    user: str = Depends(require_auth)
):
    """
    Polling endpoint for progress updates.
    Returns the current state from memory.
    """
    from api.state import import_states
    from fastapi.responses import JSONResponse
    
    headers = {"Cache-Control": "no-store, max-age=0"}
    
    if progress_id not in import_states:
        logger.warning(f"POLL MISS: {progress_id} not found in {list(import_states.keys())}")
        return JSONResponse(content={
            "status": "pending",
            "messages": [],
            "current": 0,
            "total": 0,
            "matches": 0
        }, headers=headers)
    
    state = import_states[progress_id]
    logger.info(f"POLL HIT: {progress_id} -> Status={state.get('status')} MsgCount={len(state.get('messages', []))}")
    return JSONResponse(content=state, headers=headers)


@router.post("/api/spotify/generate-m3u8")
async def create_spotify_m3u8(
    request: SpotifyM3U8Request,
    username: str = Depends(require_auth)
):
    """
    Generate an m3u8 playlist file from validated Spotify tracks.
    Only includes tracks that have been validated and exist on Tidal.
    """
    try:
        result = await generate_spotify_m3u8(
            playlist_name=request.playlist_name,
            tracks=request.tracks
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate m3u8: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate playlist: {str(e)}")
