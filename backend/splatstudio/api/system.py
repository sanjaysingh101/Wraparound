"""System status: hardware, external tools, available backends."""

from __future__ import annotations

from fastapi import APIRouter

from ..hardware import detect_hardware, detect_tools, training_available
from ..models import SystemStatus
from ..pipeline.base import export_backends, pose_backends, train_backends

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status")
def system_status() -> SystemStatus:
    return SystemStatus(
        hardware=detect_hardware(),
        tools=detect_tools(),
        training_available=training_available(),
        backends={
            "poses": pose_backends.names(),
            "train": train_backends.names(),
            "export": export_backends.names(),
        },
    )


@router.get("/health")
def health() -> dict:
    return {"ok": True}
