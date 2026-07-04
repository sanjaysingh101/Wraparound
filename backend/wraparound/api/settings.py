"""Settings read/update — persisted to the app-data settings.json."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config

router = APIRouter(prefix="/api/settings", tags=["settings"])

EDITABLE = {
    "projects_dir", "cache_dir", "temp_dir",
    "ffmpeg_path", "ffprobe_path", "colmap_path", "node_path", "opensplat_path",
    "gpu_index", "cpu_threads", "frame_quality",
    "auto_save", "auto_delete_intermediates",
    "default_pose_backend", "default_train_backend",
}


class SettingsPatch(BaseModel):
    model_config = {"extra": "allow"}


@router.get("")
def get_settings() -> dict:
    return config.settings.model_dump(mode="json")


@router.patch("")
def update_settings(patch: SettingsPatch) -> dict:
    data = patch.model_dump(exclude_unset=True)
    unknown = set(data) - EDITABLE
    if unknown:
        raise HTTPException(422, f"Not editable: {', '.join(sorted(unknown))}")
    current = config.settings.model_dump()
    current.update(data)
    try:
        new_settings = config.Settings(**current)
    except ValueError as e:
        raise HTTPException(422, str(e))
    new_settings.save()
    config.settings = new_settings
    return new_settings.model_dump(mode="json")
