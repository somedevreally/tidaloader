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

def load_persistent_settings():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                if 'sync_time' in data:
                    settings.sync_time = data['sync_time']
                elif 'sync_hour' in data:
                    # Migration from old format
                    settings.sync_time = f"{data['sync_hour']:02d}:00"
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
        "sync_time": settings.sync_time
    }

@router.post("/api/system/settings")
async def update_settings(new_settings: SystemSettings):
    settings.sync_time = new_settings.sync_time
    
    # Persist
    try:
        data = {}
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
        
        data['sync_time'] = new_settings.sync_time
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
        
    return {"status": "updated", "sync_time": settings.sync_time}
        

