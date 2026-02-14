from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from api.settings import DOWNLOAD_DIR
from scheduler import PlaylistScheduler

from typing import Optional, Dict, Any
from api.clients.jellyfin_client import jellyfin_client
import database as db

router = APIRouter()


class SettingsUpdate(BaseModel):
    """Settings payload from the frontend. All fields optional for partial updates."""
    quality: Optional[str] = None
    sync_time: Optional[str] = None
    organization_template: Optional[str] = None
    active_downloads: Optional[int] = None
    use_musicbrainz: Optional[bool] = None
    run_beets: Optional[bool] = None
    embed_lyrics: Optional[bool] = None
    group_compilations: Optional[bool] = None
    jellyfin_url: Optional[str] = None
    jellyfin_api_key: Optional[str] = None
    version: int  # required for optimistic concurrency


@router.get("/api")
async def api_root():
    return {"status": "ok", "message": "Tidaloader API"}

@router.get("/api/health")
async def health_check():
    return {"status": "healthy"}


@router.get("/api/system/settings")
async def get_settings():
    """Return all settings + version for concurrency control."""
    settings = db.get_all_settings()
    return settings


@router.post("/api/system/settings")
async def update_settings(payload: SettingsUpdate):
    """Update settings with optimistic concurrency.

    Returns 409 Conflict if the version doesn't match (another user changed settings).
    """
    # Build updates dict from non-None fields (excluding version)
    updates: Dict[str, Any] = {}
    for field_name in payload.model_fields:
        if field_name == "version":
            continue
        value = getattr(payload, field_name)
        if value is not None:
            updates[field_name] = value

    if not updates:
        return {"status": "unchanged", "version": payload.version}

    try:
        new_version = db.update_settings(updates, payload.version)
    except db.StaleSettingsError as e:
        # Return 409 with current settings so frontend can reconcile
        current = db.get_all_settings()
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Settings were changed by another user",
                "current_settings": current,
            },
        )

    # Reschedule sync job if sync_time changed
    if "sync_time" in updates:
        try:
            scheduler = PlaylistScheduler()
            scheduler.reschedule_job(updates["sync_time"])
        except Exception:
            pass  # Non-critical

    # Return updated settings
    result = db.get_all_settings()
    result["status"] = "updated"
    return result


class TestConnectionRequest(BaseModel):
    url: Optional[str] = None
    api_key: Optional[str] = None

@router.post("/api/system/jellyfin/test")
async def test_jellyfin_connection(request: TestConnectionRequest = None):
    try:
        # Use provided values from request body, or default to stored settings if empty
        url = request.url if request and request.url else None
        api_key = request.api_key if request and request.api_key else None

        info = jellyfin_client.get_system_info(url=url, api_key=api_key)
        return {"status": "success", "info": info}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/api/system/jellyfin/users")
async def get_jellyfin_users():
    try:
        users = jellyfin_client.get_users()
        return {"status": "success", "users": users}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/api/system/jellyfin/users/{user_id}/image")
async def get_jellyfin_user_image(user_id: str):
    from fastapi.responses import Response
    try:
        image_data = jellyfin_client.get_user_image(user_id)
        if image_data:
            return Response(content=image_data, media_type="image/jpeg")
        # Return 404 or empty to trigger fallback on frontend
        return Response(status_code=404)
    except Exception as e:
        return Response(status_code=500)

@router.post("/api/system/jellyfin/sync-covers")
async def sync_jellyfin_covers(background_tasks: BackgroundTasks):
    # Late import to avoid circular dependency if system imported by scheduler/playlist_manager
    from playlist_manager import playlist_manager

    background_tasks.add_task(playlist_manager.force_sync_covers)
    return {"status": "started", "message": "Global cover sync started in background"}
