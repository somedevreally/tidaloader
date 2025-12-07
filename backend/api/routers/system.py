from fastapi import APIRouter

router = APIRouter()

@router.get("/api")
async def api_root():
    return {"status": "ok", "message": "Troi Tidal Downloader API"}

@router.get("/api/health")
async def health_check():
    return {"status": "healthy"}
