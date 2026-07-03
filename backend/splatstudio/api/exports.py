"""Export endpoints — convert the trained splat into delivery formats."""

from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..models import utcnow
from ..pipeline import export as _export  # noqa: F401 — registers ply/splat/ksplat exporters
from ..pipeline.base import StageError, export_backends
from ..projects import ProjectError, store

router = APIRouter(prefix="/api/projects/{project_id}/exports", tags=["exports"])


class ExportRequest(BaseModel):
    format: str = "ply"


@router.get("/formats")
def formats() -> list[dict]:
    out = []
    for name in export_backends.names():
        cls = export_backends.get(name)
        ok, reason = cls.available()
        out.append({"format": name, "available": ok, "reason": reason})
    return out


@router.get("")
def list_exports(project_id: str) -> list[dict]:
    try:
        return store.load(project_id).exports
    except ProjectError as e:
        raise HTTPException(404, str(e))


@router.post("")
async def create_export(project_id: str, body: ExportRequest) -> dict:
    try:
        meta = store.load(project_id)
    except ProjectError as e:
        raise HTTPException(404, str(e))
    ply = store.path(project_id) / "splat" / "point_cloud.ply"
    if not ply.exists():
        raise HTTPException(409, "No trained splat yet — run the pipeline first.")

    try:
        exporter_cls = export_backends.get(body.format)
    except StageError as e:
        raise HTTPException(422, str(e))
    ok, reason = exporter_cls.available()
    if not ok:
        raise HTTPException(409, reason)

    exporter = exporter_cls()
    safe_name = re.sub(r"[^\w\-]+", "_", meta.name).strip("_") or "scene"
    out_name = f"{safe_name}_{int(time.time())}{exporter.extension}"
    out_path = store.path(project_id) / "exports" / out_name
    try:
        result = await run_in_threadpool(exporter.export, ply, out_path)
    except StageError as e:
        raise HTTPException(500, str(e))

    record = {"file": f"exports/{out_name}", "created_at": utcnow().isoformat(), **result}
    meta.exports.append(record)
    store.save(meta)
    return record


@router.get("/download/{file_name}")
def download(project_id: str, file_name: str) -> FileResponse:
    try:
        root = store.path(project_id)
    except ProjectError as e:
        raise HTTPException(404, str(e))
    target = (root / "exports" / file_name).resolve()
    if not str(target).startswith(str((root / "exports").resolve())) or not target.is_file():
        raise HTTPException(404, "Export not found")
    return FileResponse(target, filename=Path(file_name).name)
