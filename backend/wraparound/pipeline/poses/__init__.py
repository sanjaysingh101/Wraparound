"""Pose estimation stage — backend-pluggable (COLMAP today; VGGT/MASt3R/DUSt3R later).

A pose backend consumes `frames/` and must produce a COLMAP-format sparse model at
`sparse/0/` (cameras.bin, images.bin, points3D.bin). COLMAP's model format is the
de-facto interchange format every downstream trainer understands, so alternative
backends (learned or COLMAP-free) simply write their poses in the same format.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ...models import StageName
from ..base import PipelineStage, StageContext, pose_backends


class PoseBackend(ABC):
    """Estimate camera poses; write a COLMAP-format model to <project>/sparse/0."""

    @abstractmethod
    def estimate(self, ctx: StageContext) -> dict[str, Any]: ...


class EstimatePosesStage(PipelineStage):
    name = StageName.estimating_poses

    def should_skip(self, ctx: StageContext) -> bool:
        model = ctx.project_dir / "sparse" / "0"
        return (model / "images.bin").exists() or (model / "images.txt").exists()

    def run(self, ctx: StageContext) -> dict[str, Any]:
        backend_cls = pose_backends.get(ctx.config.poses.backend)
        return backend_cls().estimate(ctx)


from . import colmap  # noqa: E402,F401  — registers the default backend
