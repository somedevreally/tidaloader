from pathlib import Path
import json
from fastapi import APIRouter
from pydantic import BaseModel
from api.settings import settings, DOWNLOAD_DIR
from scheduler import PlaylistScheduler

router = APIRouter()

CONFIG_FILE = DOWNLOAD_DIR / "config.json"

class SystemSettings(BaseModel):
    sync_time: str
    organization_template: str = "{Artist}/{Album}/{TrackNumber} - {Title}"
    group_compilations: bool = True
    active_downloads: int = 3
    run_beets: bool = False
    embed_lyrics: bool = False

def load_persistent_settings():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                if 'sync_time' in data:
                    settings.sync_time = data['sync_time']
                elif 'sync_hour' in data:
                    settings.sync_time = f"{data['sync_hour']:02d}:00"
                
                settings.organization_template = data.get('organization_template', settings.organization_template)
                settings.group_compilations = data.get('group_compilations', settings.group_compilations)
                settings.active_downloads = data.get('active_downloads', settings.active_downloads)
                settings.run_beets = data.get('run_beets', settings.run_beets)
                settings.embed_lyrics = data.get('embed_lyrics', settings.embed_lyrics)
        except Exception:
            pass

# Load on module import (or startup)
load_persistent_settings()

@router.get("/api")
async def api_root():
    return {"status": "ok", "message": "Tidaloader API"}

@router.get("/api/health")
async def health_check():
    return {"status": "healthy"}

@router.get("/api/system/settings")
async def get_settings():
    return {
        "sync_time": settings.sync_time,
        "organization_template": settings.organization_template,
        "group_compilations": settings.group_compilations,
        "active_downloads": settings.active_downloads,
        "run_beets": settings.run_beets,
        "embed_lyrics": settings.embed_lyrics
    }

@router.post("/api/system/settings")
async def update_settings(new_settings: SystemSettings):
    settings.sync_time = new_settings.sync_time
    settings.organization_template = new_settings.organization_template
    settings.group_compilations = new_settings.group_compilations
    settings.active_downloads = new_settings.active_downloads
    settings.run_beets = new_settings.run_beets
    settings.embed_lyrics = new_settings.embed_lyrics
    
    # Persist
    try:
        data = {}
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
        
        data['sync_time'] = new_settings.sync_time
        data['organization_template'] = new_settings.organization_template
        data['group_compilations'] = new_settings.group_compilations
        data['active_downloads'] = new_settings.active_downloads
        data['run_beets'] = new_settings.run_beets
        data['embed_lyrics'] = new_settings.embed_lyrics
        
        # Cleanup old key if exists
        if 'sync_hour' in data:
             del data['sync_hour']
        
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=2)
            
        # Update scheduler
        scheduler = PlaylistScheduler()
        scheduler.reschedule_job(new_settings.sync_time)
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
        
    return {"status": "updated", "settings": new_settings.dict()}
        

