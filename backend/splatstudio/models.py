"""Shared pydantic schemas: project metadata, job state, pipeline configuration."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- video / validation


class VideoInfo(BaseModel):
    path: str
    width: int
    height: int
    fps: float
    duration_s: float
    frame_count: int
    bitrate_kbps: int
    rotation: int = 0
    codec: str = ""


class ValidationIssue(BaseModel):
    code: str  # e.g. "too_blurry", "too_short", "low_motion"
    severity: str  # "reject" | "warn"
    message: str  # human-readable explanation with capture advice


class ValidationReport(BaseModel):
    video: VideoInfo
    issues: list[ValidationIssue] = []
    sharpness: float = 0.0
    brightness: float = 0.0
    shakiness: float = 0.0
    motion_coverage: float = 0.0

    @property
    def ok(self) -> bool:
        return not any(i.severity == "reject" for i in self.issues)


# ---------------------------------------------------------------- pipeline / jobs


class StageName(str, Enum):
    preparing = "preparing"
    extracting_frames = "extracting_frames"
    filtering_frames = "filtering_frames"
    estimating_poses = "estimating_poses"
    training = "training"
    optimizing = "optimizing"
    generating_preview = "generating_preview"
    completed = "completed"


class StageStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class StageState(BaseModel):
    name: StageName
    status: StageStatus = StageStatus.pending
    progress: float = 0.0  # 0..1 within the stage
    message: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    outputs: dict[str, Any] = {}


class JobState(BaseModel):
    project_id: str
    status: StageStatus = StageStatus.pending
    current_stage: StageName | None = None
    stages: list[StageState] = []
    started_at: datetime | None = None
    finished_at: datetime | None = None
    elapsed_s: float = 0.0
    eta_s: float | None = None
    error: str | None = None


# ---------------------------------------------------------------- configuration


class TrainingConfig(BaseModel):
    backend: str = "splatfacto"
    iterations: int = 30000
    learning_rate: float = 1.6e-4  # means (position) lr; backends scale the rest
    sh_degree: int = 3
    background_color: str = "black"  # "black" | "white" | "random"
    densify_from_iter: int = 500
    densify_until_iter: int = 15000
    densify_grad_threshold: float = 0.0002
    opacity_reset_interval: int = 3000
    extra: dict[str, Any] = {}


class ExtractionConfig(BaseModel):
    target_min_frames: int = 150
    target_max_frames: int = 500
    quality: int = 95


class PoseConfig(BaseModel):
    backend: str = "colmap"
    matcher: str = "sequential"  # sequential | exhaustive
    extra: dict[str, Any] = {}


class PipelineConfig(BaseModel):
    extraction: ExtractionConfig = ExtractionConfig()
    poses: PoseConfig = PoseConfig()
    training: TrainingConfig = TrainingConfig()


# ---------------------------------------------------------------- project


class ProjectMeta(BaseModel):
    id: str
    name: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    video_file: str | None = None
    validation: ValidationReport | None = None
    config: PipelineConfig = PipelineConfig()
    job: JobState | None = None
    exports: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}  # splat count, PSNR, file sizes …


# ---------------------------------------------------------------- system


class GPUInfo(BaseModel):
    name: str
    vram_mb: int
    cuda: bool


class HardwareInfo(BaseModel):
    platform: str
    cpu_cores: int
    ram_mb: int
    gpus: list[GPUInfo] = []
    cuda_available: bool = False
    mps_available: bool = False
    torch_version: str | None = None
    warnings: list[str] = []


class ToolStatus(BaseModel):
    name: str
    found: bool
    path: str | None = None
    version: str | None = None


class SystemStatus(BaseModel):
    hardware: HardwareInfo
    tools: list[ToolStatus]
    training_available: bool
    backends: dict[str, list[str]]  # {"poses": [...], "train": [...], "export": [...]}
