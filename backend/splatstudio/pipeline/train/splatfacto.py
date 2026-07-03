"""Splatfacto (Nerfstudio) training backend.

Drives `ns-train splatfacto` as a subprocess against the project's COLMAP output, then
`ns-export gaussian-splat` to produce the canonical splat/point_cloud.ply. Running out
of process keeps the heavyweight nerfstudio import chain out of the API server and lets
us hard-kill training on cancel.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from ...models import TrainingConfig
from ..base import StageContext, StageError, train_backends
from . import TrainBackend

STEP_RX = re.compile(r"^\s*(\d+)\s*\(")  # nerfstudio progress rows: "  4200 (14.00%) ..."


@train_backends.register("splatfacto")
class SplatfactoBackend(TrainBackend):
    @classmethod
    def available(cls) -> tuple[bool, str]:
        if not shutil.which("ns-train"):
            return False, ("Nerfstudio is not installed. Run scripts/setup.sh with the training "
                           "extra, or switch to the 'gsplat' backend in project settings.")
        return True, ""

    def train(self, ctx: StageContext, cfg: TrainingConfig) -> dict[str, Any]:
        splat_dir = ctx.project_dir / "splat"
        run_dir = splat_dir / "runs"
        bg = {"black": "0 0 0", "white": "1 1 1"}.get(cfg.background_color)

        # Nerfstudio's colmap dataparser expects images + colmap/sparse/0 under --data;
        # our layout already matches via the sparse/ symlink convention below.
        data_dir = self._prepare_data_layout(ctx.project_dir)

        cmd = [
            "ns-train", "splatfacto",
            "--data", str(data_dir),
            "--output-dir", str(run_dir),
            "--experiment-name", "splat",
            "--timestamp", "run",
            "--max-num-iterations", str(cfg.iterations),
            "--viewer.quit-on-train-completion", "True",
            "--vis", "tensorboard",
            "--pipeline.model.sh-degree", str(cfg.sh_degree),
            "--pipeline.model.means-lr", str(cfg.learning_rate),
            "--pipeline.model.densify-grad-thresh", str(cfg.densify_grad_threshold),
            "--pipeline.model.stop-split-at", str(cfg.densify_until_iter),
            "--pipeline.model.warmup-length", str(cfg.densify_from_iter),
            "--pipeline.model.reset-alpha-every",
            str(max(1, cfg.opacity_reset_interval // max(cfg.densify_from_iter, 1))),
        ]
        if cfg.background_color == "random":
            cmd += ["--pipeline.model.background-color", "random"]
        elif bg:
            cmd += ["--pipeline.model.background-color", cfg.background_color]
        for key, value in cfg.extra.items():
            cmd += [f"--{key}", str(value)]
        cmd += ["colmap", "--data", str(data_dir), "--colmap-path", "colmap/sparse/0"]

        def on_line(line: str) -> None:
            m = STEP_RX.match(line)
            if m:
                step = int(m.group(1))
                ctx.report_progress(
                    min(step / cfg.iterations, 0.99) * 0.9,
                    f"Training step {step}/{cfg.iterations}",
                )

        ctx.report_progress(0.0, "Starting Splatfacto training")
        ctx.run_subprocess(cmd, cwd=ctx.project_dir, on_line=on_line)

        config_yml = run_dir / "splat" / "splatfacto" / "run" / "config.yml"
        if not config_yml.exists():
            found = list(run_dir.rglob("config.yml"))
            if not found:
                raise StageError("Splatfacto finished but no run config was found.")
            config_yml = found[0]

        ctx.report_progress(0.92, "Exporting Gaussian Splat PLY")
        ctx.run_subprocess([
            "ns-export", "gaussian-splat",
            "--load-config", str(config_yml),
            "--output-dir", str(splat_dir),
        ])
        # ns-export writes splat.ply; normalize to our canonical name.
        exported = splat_dir / "splat.ply"
        target = splat_dir / "point_cloud.ply"
        if exported.exists():
            exported.replace(target)
        ctx.report_progress(1.0, "Training complete")
        return {"backend": "splatfacto", "iterations": cfg.iterations}

    @staticmethod
    def _prepare_data_layout(project_dir: Path) -> Path:
        """Expose our layout the way nerfstudio's colmap parser expects it.

        Parser wants <data>/images and <data>/colmap/sparse/0. We keep the project dir
        itself as <data> with 'images' → frames and colmap/sparse/0 → sparse/0 links.
        """
        images_link = project_dir / "images"
        if not images_link.exists():
            images_link.symlink_to(project_dir / "frames", target_is_directory=True)
        colmap_sparse = project_dir / "colmap" / "sparse"
        colmap_sparse.mkdir(parents=True, exist_ok=True)
        model_link = colmap_sparse / "0"
        if not model_link.exists():
            model_link.symlink_to(project_dir / "sparse" / "0", target_is_directory=True)
        return project_dir
