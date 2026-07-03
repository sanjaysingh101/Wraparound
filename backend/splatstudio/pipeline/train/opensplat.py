"""OpenSplat training backend — C++ 3DGS trainer with Metal (Apple Silicon), CUDA,
ROCm and CPU support. The only backend that trains on macOS, where gsplat/nerfstudio
require CUDA. Consumes the project's COLMAP output directly.

Binary resolution order: explicit setting → vendor build (vendor/OpenSplat/build) → PATH.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from ...config import settings
from ...models import TrainingConfig
from ..base import StageContext, StageError, train_backends
from . import TrainBackend

STEP_RX = re.compile(r"^Step (\d+): ([\d.eE+-]+)")
CHECKPOINT_RX = re.compile(r"^point_cloud_(\d+)\.ply$")


def find_latest_checkpoint(splat_dir: Path) -> tuple[Path | None, int]:
    """Return the highest-step OpenSplat checkpoint (point_cloud_<step>.ply) and its step."""
    best: tuple[Path | None, int] = (None, 0)
    for p in splat_dir.glob("point_cloud_*.ply"):
        m = CHECKPOINT_RX.match(p.name)
        if m and int(m.group(1)) > best[1]:
            best = (p, int(m.group(1)))
    return best


def find_opensplat() -> Path | None:
    configured = getattr(settings, "opensplat_path", None)
    if configured and Path(configured).exists():
        return Path(configured)
    # repo layout: <repo>/vendor/OpenSplat/build/opensplat
    repo_root = Path(__file__).resolve().parents[4]
    vendored = repo_root / "vendor" / "OpenSplat" / "build" / "opensplat"
    if vendored.exists():
        return vendored
    which = shutil.which("opensplat")
    return Path(which) if which else None


@train_backends.register("opensplat")
class OpenSplatBackend(TrainBackend):
    @classmethod
    def available(cls) -> tuple[bool, str]:
        if find_opensplat() is None:
            return False, ("The OpenSplat binary was not found. Build it with "
                           "scripts/build-opensplat.sh or install it on PATH.")
        return True, ""

    def train(self, ctx: StageContext, cfg: TrainingConfig) -> dict[str, Any]:
        binary = find_opensplat()
        assert binary is not None
        splat_dir = ctx.project_dir / "splat"
        splat_dir.mkdir(exist_ok=True)
        out_ply = splat_dir / "point_cloud.ply"

        # OpenSplat's colmap reader wants <root>/sparse/0 (we have it) and
        # <root>/images/<name>; expose frames/ under that name via symlink.
        images_link = ctx.project_dir / "images"
        if not images_link.exists():
            images_link.symlink_to(ctx.project_dir / "frames", target_is_directory=True)

        # reset-alpha-every counts *refinements* (one per refine-every=100 steps)
        reset_alpha_every = max(1, cfg.opacity_reset_interval // 100)
        # Checkpoint periodically so an interruption (crash, app close, machine sleep)
        # never loses more than one interval of work — OpenSplat embeds the step in the
        # PLY and can --resume from it. ~15 checkpoints across the run.
        save_every = max(1000, cfg.iterations // 15)
        cmd = [
            str(binary), str(ctx.project_dir),
            "-o", str(out_ply),
            "-n", str(cfg.iterations),
            "--save-every", str(save_every),
            "--sh-degree", str(max(1, cfg.sh_degree)),  # opensplat requires > 0
            "--warmup-length", str(cfg.densify_from_iter),
            "--densify-grad-thresh", str(cfg.densify_grad_threshold),
            "--reset-alpha-every", str(reset_alpha_every),
        ]

        # Resume from the latest checkpoint if a previous run was interrupted.
        checkpoint, ckpt_step = find_latest_checkpoint(splat_dir)
        if checkpoint is not None and ckpt_step < cfg.iterations:
            cmd += ["--resume", str(checkpoint)]
            ctx.report_progress(ckpt_step / cfg.iterations,
                                f"Resuming from checkpoint at step {ckpt_step}")

        for key, value in cfg.extra.items():
            cmd += [f"--{key}", str(value)]

        last_loss: list[float] = []

        def on_line(line: str) -> None:
            m = STEP_RX.match(line.strip())
            if m:
                step, loss = int(m.group(1)), float(m.group(2))
                last_loss.append(loss)
                ctx.report_progress(
                    min(step / cfg.iterations, 0.99),
                    f"Training step {step}/{cfg.iterations} · loss {loss:.4f}",
                )

        if checkpoint is None:
            ctx.report_progress(0.0, "Starting OpenSplat training (Metal/CPU)")
        ctx.run_subprocess(cmd, cwd=ctx.project_dir, on_line=on_line)

        if not out_ply.exists():
            raise StageError("OpenSplat finished but produced no output PLY.")
        # Training finished — drop intermediate checkpoints, keep the final model.
        for p in splat_dir.glob("point_cloud_*.ply"):
            if CHECKPOINT_RX.match(p.name):
                p.unlink(missing_ok=True)
        ctx.report_progress(1.0, "Training complete")
        return {
            "backend": "opensplat",
            "iterations": cfg.iterations,
            "final_loss": last_loss[-1] if last_loss else None,
        }
