"""gsplat training backend — a compact in-process 3DGS training loop.

Uses gsplat's rasterizer + DefaultStrategy (densification / splitting / opacity reset)
directly, reading the COLMAP model with pycolmap (bundled with nerfstudio) or gsplat's
own parser. Lighter than Splatfacto and useful for quick previews or when nerfstudio
is not installed; requires CUDA for gsplat's kernels.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from ...models import TrainingConfig
from ..base import StageCancelled, StageContext, StageError, train_backends
from . import TrainBackend
from .colmap_io import load_colmap_scene


@train_backends.register("gsplat")
class GsplatBackend(TrainBackend):
    @classmethod
    def available(cls) -> tuple[bool, str]:
        try:
            import torch
        except ImportError:
            return False, "PyTorch is not installed — run scripts/setup.sh."
        if not torch.cuda.is_available():
            return False, "gsplat requires a CUDA GPU. Use the 'splatfacto' backend or a CUDA machine."
        try:
            import gsplat  # noqa: F401
        except ImportError:
            return False, "gsplat is not installed — run scripts/setup.sh with the training extra."
        return True, ""

    def train(self, ctx: StageContext, cfg: TrainingConfig) -> dict[str, Any]:
        import torch
        import torch.nn.functional as F
        from gsplat import rasterization
        from gsplat.strategy import DefaultStrategy

        device = torch.device("cuda")
        scene = load_colmap_scene(ctx.project_dir / "sparse" / "0", ctx.project_dir / "frames")
        ctx.report_progress(0.02, f"Loaded {len(scene.cameras)} cameras, "
                                  f"{len(scene.points)} seed points")

        # --- initialize gaussians from the sparse point cloud
        n = len(scene.points)
        means = torch.tensor(scene.points, dtype=torch.float32, device=device)
        rgbs = torch.tensor(scene.colors / 255.0, dtype=torch.float32, device=device)
        dists = self._knn_mean_dist(scene.points)
        scales = torch.log(torch.tensor(dists, dtype=torch.float32, device=device))[:, None].repeat(1, 3)
        quats = torch.zeros((n, 4), device=device)
        quats[:, 0] = 1.0
        opacities = torch.logit(torch.full((n,), 0.1, device=device))

        sh_dim = (cfg.sh_degree + 1) ** 2
        sh0 = ((rgbs - 0.5) / 0.28209479177387814)[:, None, :]  # RGB → SH DC
        shN = torch.zeros((n, sh_dim - 1, 3), device=device)

        params = torch.nn.ParameterDict({
            "means": torch.nn.Parameter(means),
            "scales": torch.nn.Parameter(scales),
            "quats": torch.nn.Parameter(quats),
            "opacities": torch.nn.Parameter(opacities),
            "sh0": torch.nn.Parameter(sh0),
            "shN": torch.nn.Parameter(shN),
        }).to(device)

        scene_scale = float(np.linalg.norm(scene.points - scene.points.mean(0), axis=1).mean())
        lrs = {
            "means": cfg.learning_rate * scene_scale,
            "scales": 5e-3, "quats": 1e-3, "opacities": 5e-2,
            "sh0": 2.5e-3, "shN": 2.5e-3 / 20,
        }
        optimizers = {
            k: torch.optim.Adam([{"params": params[k], "lr": lr, "name": k}], eps=1e-15)
            for k, lr in lrs.items()
        }
        strategy = DefaultStrategy(
            refine_start_iter=cfg.densify_from_iter,
            refine_stop_iter=cfg.densify_until_iter,
            grow_grad2d=cfg.densify_grad_threshold,
            reset_every=cfg.opacity_reset_interval,
            verbose=False,
        )
        strategy_state = strategy.initialize_state(scene_scale=scene_scale)

        bg = {"black": 0.0, "white": 1.0}.get(cfg.background_color)
        images = [torch.tensor(im / 255.0, dtype=torch.float32) for im in scene.images]
        losses: list[float] = []

        for step in range(cfg.iterations):
            if ctx.cancel_event.is_set():
                raise StageCancelled()
            i = step % len(scene.cameras)
            cam = scene.cameras[i]
            gt = images[i].to(device)
            viewmat = torch.tensor(cam.world_to_cam, dtype=torch.float32, device=device)[None]
            K = torch.tensor(cam.K, dtype=torch.float32, device=device)[None]

            sh_degree_now = min(step // 1000, cfg.sh_degree)
            colors = torch.cat([params["sh0"], params["shN"]], dim=1)
            bg_val = torch.rand(1, 3, device=device) if bg is None else torch.full((1, 3), bg, device=device)

            render, alpha, info = rasterization(
                means=params["means"],
                quats=F.normalize(params["quats"], dim=-1),
                scales=torch.exp(params["scales"]),
                opacities=torch.sigmoid(params["opacities"]),
                colors=colors,
                viewmats=viewmat, Ks=K,
                width=cam.width, height=cam.height,
                sh_degree=sh_degree_now,
                backgrounds=bg_val,
                packed=False,
            )
            strategy.step_pre_backward(params, optimizers, strategy_state, step, info)
            l1 = (render[0] - gt).abs().mean()
            loss = l1  # SSIM term omitted deliberately: keeps deps light, quality is close
            loss.backward()
            strategy.step_post_backward(params, optimizers, strategy_state, step, info)
            for opt in optimizers.values():
                opt.step()
                opt.zero_grad(set_to_none=True)

            if step % 50 == 0:
                losses.append(float(loss))
                ctx.report_progress(
                    min(step / cfg.iterations, 0.98),
                    f"Training step {step}/{cfg.iterations} · loss {float(loss):.4f} "
                    f"· {len(params['means'])} gaussians",
                )

        ctx.report_progress(0.99, "Writing point_cloud.ply")
        out = ctx.project_dir / "splat" / "point_cloud.ply"
        self._write_ply(params, out)
        return {
            "backend": "gsplat",
            "iterations": cfg.iterations,
            "num_gaussians": int(len(params["means"])),
            "final_loss": losses[-1] if losses else None,
        }

    @staticmethod
    def _knn_mean_dist(points: np.ndarray, k: int = 3) -> np.ndarray:
        """Mean distance to k nearest neighbours — initial gaussian scale."""
        from scipy.spatial import cKDTree

        tree = cKDTree(points)
        d, _ = tree.query(points, k=k + 1)
        return np.clip(d[:, 1:].mean(axis=1), 1e-4, None)

    @staticmethod
    def _write_ply(params, path: Path) -> None:
        """Write the standard 3DGS PLY attribute layout (INRIA convention)."""
        import torch

        with torch.no_grad():
            means = params["means"].cpu().numpy()
            sh0 = params["sh0"].cpu().numpy()          # (N,1,3)
            shN = params["shN"].cpu().numpy()          # (N,K-1,3)
            opac = params["opacities"].cpu().numpy()
            scales = params["scales"].cpu().numpy()
            quats = params["quats"].cpu().numpy()

        n = means.shape[0]
        f_dc = sh0.reshape(n, 3)
        f_rest = shN.transpose(0, 2, 1).reshape(n, -1)  # channel-major, matching INRIA

        names = (["x", "y", "z", "nx", "ny", "nz"]
                 + [f"f_dc_{i}" for i in range(3)]
                 + [f"f_rest_{i}" for i in range(f_rest.shape[1])]
                 + ["opacity"]
                 + [f"scale_{i}" for i in range(3)]
                 + [f"rot_{i}" for i in range(4)])
        data = np.concatenate(
            [means, np.zeros((n, 3), np.float32), f_dc, f_rest, opac[:, None], scales, quats],
            axis=1,
        ).astype(np.float32)

        from plyfile import PlyData, PlyElement

        arr = np.empty(n, dtype=[(name, "f4") for name in names])
        for i, name in enumerate(names):
            arr[name] = data[:, i]
        path.parent.mkdir(parents=True, exist_ok=True)
        PlyData([PlyElement.describe(arr, "vertex")]).write(str(path))
