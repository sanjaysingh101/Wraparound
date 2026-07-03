"""Job control + WebSocket progress stream."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..events import bus
from ..jobs import runner
from ..models import JobState
from ..pipeline.base import StageError
from ..projects import ProjectError, store

router = APIRouter(prefix="/api", tags=["jobs"])


class StartJob(BaseModel):
    resume: bool = True
    retrain: bool = False


@router.post("/projects/{project_id}/job")
def start_job(project_id: str, body: StartJob) -> JobState:
    try:
        return runner.start(project_id, resume=body.resume, retrain=body.retrain)
    except ProjectError as e:
        raise HTTPException(404, str(e))
    except StageError as e:
        raise HTTPException(409, str(e))


@router.delete("/projects/{project_id}/job")
def cancel_job(project_id: str) -> dict:
    runner.cancel(project_id)
    return {"cancelling": project_id}


@router.get("/projects/{project_id}/job")
def job_state(project_id: str) -> JobState | None:
    try:
        return store.load(project_id).job
    except ProjectError as e:
        raise HTTPException(404, str(e))


@router.websocket("/ws/projects/{project_id}")
async def job_events(ws: WebSocket, project_id: str) -> None:
    await ws.accept()
    q = bus.subscribe(project_id)
    try:
        # Send current state immediately so late subscribers render instantly.
        try:
            meta = store.load(project_id)
            if meta.job:
                await ws.send_json({"type": "progress", "job": meta.job.model_dump(mode="json")})
        except ProjectError:
            pass
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=20)
                await ws.send_json(event)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(project_id, q)
