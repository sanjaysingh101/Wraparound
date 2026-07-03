"""Gaussian Splat training stage — backend-pluggable (Splatfacto default, gsplat alt).

A trainer consumes frames/ + sparse/0 (COLMAP model) and must produce
splat/point_cloud.ply — a 3DGS PLY with the standard attribute layout
(xyz, f_dc_*, f_rest_*, opacity, scale_*, rot_*). Exporters and the viewer
work off that single artifact, keeping trainers fully interchangeable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ...models import StageName, TrainingConfig
from ..base import PipelineStage, StageContext, StageError, train_backends


class TrainBackend(ABC):
    @abstractmethod
    def train(self, ctx: StageContext, cfg: TrainingConfig) -> dict[str, Any]:
        """Train and write <project>/splat/point_cloud.ply; return stats."""

    @classmethod
    def available(cls) -> tuple[bool, str]:
        """(is_available, reason_if_not) — checked before dispatch."""
        return True, ""


# When the configured backend can't run on this machine, fall back in this order.
FALLBACK_ORDER = ["splatfacto", "gsplat", "opensplat"]


class TrainStage(PipelineStage):
    name = StageName.training

    def should_skip(self, ctx: StageContext) -> bool:
        return (ctx.project_dir / "splat" / "point_cloud.ply").exists()

    def run(self, ctx: StageContext) -> dict[str, Any]:
        cfg = ctx.config.training
        backend_cls, chosen = self._resolve_backend(cfg.backend)
        if chosen != cfg.backend:
            ctx.report_progress(0.0, f"Backend '{cfg.backend}' unavailable here — using '{chosen}'")
        result = backend_cls().train(ctx, cfg)
        ply = ctx.project_dir / "splat" / "point_cloud.ply"
        if not ply.exists():
            raise StageError(f"Training backend '{cfg.backend}' did not produce point_cloud.ply")
        result["ply_bytes"] = ply.stat().st_size
        return result

    @staticmethod
    def _resolve_backend(name: str):
        """Return (backend_cls, actual_name); falls back when `name` can't run here."""
        requested = train_backends.get(name)
        ok, reason = requested.available()
        if ok:
            return requested, name
        reasons = [f"'{name}': {reason}"]
        for alt in FALLBACK_ORDER:
            if alt == name or alt not in train_backends.names():
                continue
            cls = train_backends.get(alt)
            alt_ok, alt_reason = cls.available()
            if alt_ok:
                return cls, alt
            reasons.append(f"'{alt}': {alt_reason}")
        raise StageError(
            "No training backend can run on this machine:\n" +
            "\n".join(f"• {r}" for r in reasons)
        )


from . import splatfacto, gsplat_backend, opensplat  # noqa: E402,F401  — register backends
