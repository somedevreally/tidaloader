import logging
from typing import List, Optional, Literal, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel

from api.auth import require_auth
from api.clients import tidal_client
from playlist_manager import playlist_manager

router = APIRouter()
logger = logging.getLogger(__name__)

# Models
class MonitorPlaylistRequest(BaseModel):
    uuid: str
    name: str # Name to be used for the playlist file/display
    frequency: Literal["manual", "daily", "weekly", "monthly", "yearly"] = "manual"
    quality: Literal["LOW", "HIGH", "LOSSLESS", "HI_RES"] = "LOSSLESS"
    source: Literal["tidal", "listenbrainz", "spotify"] = "tidal"
    extra_config: Optional[Dict[str, Any]] = None
    use_playlist_folder: bool = False
    initial_sync_progress_id: Optional[str] = None
    skip_download: bool = False

class DeleteFilesRequest(BaseModel):
    files: List[str]

# Endpoints
@router.get("/api/playlists/search")
async def search_playlists_proxy(
    query: str,
    limit: int = 10,
    offset: int = 0,
    user: str = Depends(require_auth)
):
    """Proxy to Tidal search for playlists"""
    try:
        # Using tidal_client native search method
        results = tidal_client.search_playlists(query) 
        return results
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/playlists/monitored")
async def get_monitored_playlists(user: str = Depends(require_auth)):
    return playlist_manager.get_monitored_playlists()

@router.post("/api/playlists/monitor")
async def monitor_playlist(
    request: MonitorPlaylistRequest,
    background_tasks: BackgroundTasks,
    user: str = Depends(require_auth)
):
    """Add a playlist to monitoring and start initial sync"""
    try:
        playlist, created = playlist_manager.add_monitored_playlist(
            request.uuid, 
            request.name, 
            request.frequency, 
            request.quality,
            request.source,
            request.extra_config,
        )
        
        logger.info(f"MONITOR REQUEST: UUID={request.uuid}, Name={request.name}, Skip={request.skip_download}, ProgressID={request.initial_sync_progress_id}")

        
        # Start initial sync in background only if new
        if created:
            logger.info(f"New playlist monitored {request.uuid}, triggering initial sync.")
            
            # Initialize progress queue if requested
            # Initialize progress queue if requested
            if request.initial_sync_progress_id:
                import asyncio
                from api.state import lb_progress_queues, import_states
                
                # Initialize Legacy Queue
                lb_progress_queues[request.initial_sync_progress_id] = asyncio.Queue()
                
                # Initialize New Polling State
                import_states[request.initial_sync_progress_id] = {
                    "status": "active",
                    "messages": [{"text": "Initializing analysis...", "type": "info", "timestamp": 0}], # will be overwritten or appended
                    "current": 0,
                    "total": 0,
                    "matches": 0
                }
                
                # Give frontend a moment to connect to SSE stream (legacy) and ensure Polling picks up readiness
                async def delayed_start():
                    await asyncio.sleep(0.5)
                    await playlist_manager.sync_playlist(
                        request.uuid, 
                        progress_id=request.initial_sync_progress_id,
                        skip_download=request.skip_download
                    )
                
                background_tasks.add_task(delayed_start)
            else:
                background_tasks.add_task(
                    playlist_manager.sync_playlist, 
                    request.uuid, 
                    progress_id=None,
                    skip_download=request.skip_download
                )
        else:
            logger.info(f"Playlist {request.uuid} updated, skipping auto-sync.")
        
        return {"status": "success", "playlist": playlist}
    except Exception as e:
        logger.error(f"Failed to monitor playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/playlists/{uuid}")
async def stop_monitoring(uuid: str, user: str = Depends(require_auth)):
    playlist_manager.remove_monitored_playlist(uuid)
    return {"status": "success"}

@router.post("/api/playlists/{uuid}/sync")
async def sync_playlist_manual(
    uuid: str, 
    background_tasks: BackgroundTasks,
    progress_id: Optional[str] = Query(None, description="Progress ID to use for cached analysis results"),
    user: str = Depends(require_auth)
):
    """Trigger a manual sync/download"""
    try:
        # Check existence
        if not playlist_manager.get_playlist(uuid):
            raise HTTPException(status_code=404, detail="Playlist not monitored")
            
        # Run synchronously for manual trigger to provide feedback
        # Pass progress_id to enable cache usage
        result = await playlist_manager.sync_playlist(uuid, progress_id=progress_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/playlists/{uuid}/files")
async def get_playlist_files_endpoint(uuid: str, user: str = Depends(require_auth)):
    try:
        files = playlist_manager.get_playlist_files(uuid)
        return {"status": "success", "files": files}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get playlist files: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/playlists/{uuid}/delete-files")
async def delete_playlist_files_endpoint(
    uuid: str, 
    request: DeleteFilesRequest,
    user: str = Depends(require_auth)
):
    try:
        result = playlist_manager.delete_playlist_files(uuid, request.files)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete playlist files: {e}")
        raise HTTPException(status_code=500, detail=str(e))
