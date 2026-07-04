"""Post-training optimization.

Prunes gaussians that contribute nothing to the render — near-transparent splats and
extreme-scale outliers ("floaters") far outside the scene bounds. Operates directly on
the 3DGS PLY, so it works identically for every training backend.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from plyfile import PlyData, PlyElement

from ..models import StageName
from .base import PipelineStage, StageContext, StageError

OPACITY_PRUNE = 0.005     # sigmoid(opacity) below this is invisible
OUTLIER_SIGMA = 4.0       # distance from centroid, in std deviations


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def prune_ply(src: Path, dst: Path) -> dict[str, int]:
    ply = PlyData.read(str(src))
    v = ply["vertex"].data
    n = len(v)

    opacity = sigmoid(np.asarray(v["opacity"]))
    xyz = np.stack([v["x"], v["y"], v["z"]], axis=1)
    center = np.median(xyz, axis=0)
    dist = np.linalg.norm(xyz - center, axis=1)
    sigma = float(dist.std()) or 1.0

    keep = (opacity > OPACITY_PRUNE) & (dist < dist.mean() + OUTLIER_SIGMA * sigma)
    pruned = v[keep]
    PlyData([PlyElement.describe(pruned, "vertex")]).write(str(dst))
    return {"before": n, "after": int(keep.sum()), "pruned": int(n - keep.sum())}


class OptimizeStage(PipelineStage):
    name = StageName.optimizing

    def run(self, ctx: StageContext) -> dict[str, Any]:
        splat_dir = ctx.project_dir / "splat"
        src = splat_dir / "point_cloud.ply"
        if not src.exists():
            raise StageError("No trained splat found to optimize.")
        ctx.report_progress(0.2, "Pruning transparent splats and floaters")
        stats = prune_ply(src, splat_dir / "point_cloud_optimized.ply")
        # The optimized model becomes the canonical artifact; keep the raw one around.
        src.replace(splat_dir / "point_cloud_raw.ply")
        (splat_dir / "point_cloud_optimized.ply").replace(src)
        ctx.report_progress(1.0, f"Pruned {stats['pruned']} of {stats['before']} gaussians")
        return stats
