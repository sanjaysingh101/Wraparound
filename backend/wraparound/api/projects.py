"""Project CRUD + video upload + file serving (frames, previews, splat model)."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

import uuid

from ..jobs import runner
from ..models import CameraKeyframe, Flyaround, PipelineConfig, ProjectMeta, ValidationReport
from ..pipeline.base import StageError
from ..pipeline.validate import validate_video
from ..pipeline.video import SUPPORTED_EXTENSIONS
from ..projects import ProjectError, store

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProject(BaseModel):
    name: str


class UpdateConfig(BaseModel):
    config: PipelineConfig


@router.get("")
def list_projects() -> list[ProjectMeta]:
    return store.list()


@router.post("")
def create_project(body: CreateProject) -> ProjectMeta:
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Project name is required")
    return store.create(name)


@router.get("/{project_id}")
def get_project(project_id: str) -> ProjectMeta:
    try:
        return store.load(project_id)
    except ProjectError as e:
        raise HTTPException(404, str(e))


@router.post("/{project_id}/duplicate")
def duplicate_project(project_id: str) -> ProjectMeta:
    try:
        return store.duplicate(project_id)
    except ProjectError as e:
        raise HTTPException(404, str(e))


@router.delete("/{project_id}")
def delete_project(project_id: str) -> dict:
    if runner.is_running(project_id):
        raise HTTPException(409, "Stop the running job before deleting this project.")
    store.delete(project_id)
    return {"deleted": project_id}


@router.put("/{project_id}/config")
def update_config(project_id: str, body: UpdateConfig) -> ProjectMeta:
    try:
        meta = store.load(project_id)
    except ProjectError as e:
        raise HTTPException(404, str(e))
    meta.config = body.config
    store.save(meta)
    return meta


class SaveFlyaround(BaseModel):
    name: str
    keyframes: list[CameraKeyframe]
    duration: float = 8.0
    loop: bool = False


@router.post("/{project_id}/flyarounds")
def add_flyaround(project_id: str, body: SaveFlyaround) -> list[Flyaround]:
    try:
        meta = store.load(project_id)
    except ProjectError as e:
        raise HTTPException(404, str(e))
    if len(body.keyframes) < 2:
        raise HTTPException(422, "A fly-around needs at least two keyframes.")
    meta.flyarounds.append(
        Flyaround(
            id=uuid.uuid4().hex[:8],
            name=body.name.strip() or f"Fly-around {len(meta.flyarounds) + 1}",
            keyframes=body.keyframes,
            duration=body.duration,
            loop=body.loop,
        )
    )
    store.save(meta)
    return meta.flyarounds


@router.delete("/{project_id}/flyarounds/{flyaround_id}")
def delete_flyaround(project_id: str, flyaround_id: str) -> list[Flyaround]:
    try:
        meta = store.load(project_id)
    except ProjectError as e:
        raise HTTPException(404, str(e))
    meta.flyarounds = [f for f in meta.flyarounds if f.id != flyaround_id]
    store.save(meta)
    return meta.flyarounds


@router.post("/{project_id}/video")
async def upload_video(project_id: str, file: UploadFile) -> ValidationReport:
    """Store the uploaded video and run validation immediately so the UI can give
    capture feedback before any heavy processing starts."""
    try:
        meta = store.load(project_id)
    except ProjectError as e:
        raise HTTPException(404, str(e))

    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(422, f"Unsupported format '{suffix}'. Use MP4, MOV, or M4V.")

    dest = store.path(project_id) / "video.mp4"
    with dest.open("wb") as out:
        while chunk := await file.read(4 * 1024 * 1024):
            out.write(chunk)

    try:
        report = validate_video(dest)
    except StageError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, str(e))

    meta.video_file = "video.mp4"
    meta.validation = report
    store.save(meta)
    return report


@router.post("/{project_id}/video/path")
def register_video_path(project_id: str, body: dict) -> ValidationReport:
    """Register a video already on disk (used by the Tauri file-picker — avoids
    streaming multi-GB files through HTTP)."""
    src = Path(body.get("path", ""))
    if not src.exists():
        raise HTTPException(422, f"File not found: {src}")
    if src.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(422, f"Unsupported format '{src.suffix}'. Use MP4, MOV, or M4V.")
    try:
        meta = store.load(project_id)
    except ProjectError as e:
        raise HTTPException(404, str(e))
    dest = store.path(project_id) / "video.mp4"
    shutil.copy2(src, dest)
    try:
        report = validate_video(dest)
    except StageError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, str(e))
    meta.video_file = "video.mp4"
    meta.validation = report
    store.save(meta)
    return report


@router.get("/{project_id}/files/{file_path:path}")
def get_file(project_id: str, file_path: str) -> FileResponse:
    """Serve project artifacts (thumbnail, turntable, point_cloud.ply) to the UI."""
    try:
        root = store.path(project_id).resolve()
    except ProjectError as e:
        raise HTTPException(404, str(e))
    target = (root / file_path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(target)
