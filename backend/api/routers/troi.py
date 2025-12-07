import uuid
import json
import asyncio
from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse

from api.models import TroiGenerateRequest
from api.auth import require_auth
from api.state import troi_progress_queues
from api.services.troi import troi_generate_with_progress

router = APIRouter()

@router.post("/api/troi/generate")
async def generate_troi_playlist(
    request: TroiGenerateRequest,
    background_tasks: BackgroundTasks,
    username: str = Depends(require_auth)
):
    progress_id = str(uuid.uuid4())
    
    background_tasks.add_task(
        troi_generate_with_progress,
        request.username,
        request.playlist_type,
        progress_id
    )
    
    return {"progress_id": progress_id}

@router.get("/api/troi/progress/{progress_id}")
async def troi_progress_stream(
    progress_id: str,
    username: str = Depends(require_auth)
):
    async def event_generator():
        if progress_id not in troi_progress_queues:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Invalid progress ID'})}\n\n"
            return
        
        queue = troi_progress_queues[progress_id]
        
        try:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    
                    if message is None:
                        break
                    
                    yield f"data: {json.dumps(message, ensure_ascii=False)}\n\n"
                    
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
                    
        finally:
            if progress_id in troi_progress_queues:
                del troi_progress_queues[progress_id]
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Type": "text/event-stream; charset=utf-8"
        }
    )
