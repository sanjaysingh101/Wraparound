"""Preview generation: project thumbnail + (when CUDA is available) a turntable video
rendered from the trained splat with gsplat. Falls back gracefully to a video-frame
thumbnail so the stage never blocks pipeline completion.
"""

from __future__ import annotations

import shutil
from typing import Any

import cv2
import numpy as np

from ..config import settings
from ..models import StageName
from .base import PipelineStage, StageContext


class PreviewStage(PipelineStage):
    name = StageName.generating_preview

    def run(self, ctx: StageContext) -> dict[str, Any]:
        preview_dir = ctx.project_dir / "preview"
        preview_dir.mkdir(exist_ok=True)
        out: dict[str, Any] = {}

        ctx.report_progress(0.1, "Creating thumbnail")
        frames = sorted((ctx.project_dir / "frames").glob("*.jpg"))
        if frames:
            img = cv2.imread(str(frames[len(frames) // 2]))
            h, w = img.shape[:2]
            scale = 512.0 / max(h, w)
            thumb = cv2.resize(img, (int(w * scale), int(h * scale)))
            cv2.imwrite(str(preview_dir / "thumbnail.jpg"), thumb, [cv2.IMWRITE_JPEG_QUALITY, 85])
            out["thumbnail"] = "preview/thumbnail.jpg"

        try:
            ctx.report_progress(0.3, "Rendering turntable preview")
            video = self._render_turntable(ctx, preview_dir)
            if video:
                out["turntable"] = video
        except Exception as e:  # preview is best-effort — never fail the pipeline over it
            out["turntable_error"] = str(e)[:300]

        ctx.report_progress(1.0, "Preview ready")
        return out

    def _render_turntable(self, ctx: StageContext, preview_dir) -> str | None:
        try:
            import torch
            from gsplat import rasterization
        except ImportError:
            return None
        if not torch.cuda.is_available():
            return None

        from plyfile import PlyData

        ply = PlyData.read(str(ctx.project_dir / "splat" / "point_cloud.ply"))
        v = ply["vertex"].data
        device = torch.device("cuda")

        def col(*names):
            return torch.tensor(np.stack([np.asarray(v[n]) for n in names], 1),
                                dtype=torch.float32, device=device)

        means = col("x", "y", "z")
        scales = torch.exp(col("scale_0", "scale_1", "scale_2"))
        quats = col("rot_0", "rot_1", "rot_2", "rot_3")
        opac = torch.sigmoid(torch.tensor(np.asarray(v["opacity"]), dtype=torch.float32, device=device))
        colors = torch.sigmoid(col("f_dc_0", "f_dc_1", "f_dc_2") * 0.28209479177387814 + 0.5)

        center = means.median(0).values
        radius = (means - center).norm(dim=1).quantile(0.9).item() * 1.8
        W, H, n_frames = 960, 720, 90
        K = torch.tensor([[[800.0, 0, W / 2], [0, 800.0, H / 2], [0, 0, 1]]], device=device)

        tmp = preview_dir / "turntable_frames"
        tmp.mkdir(exist_ok=True)
        for i in range(n_frames):
            ctx.check_cancelled()
            a = 2 * np.pi * i / n_frames
            eye = center.cpu().numpy() + radius * np.array([np.sin(a), -0.25, np.cos(a)])
            viewmat = torch.tensor(look_at(eye, center.cpu().numpy()), dtype=torch.float32,
                                   device=device)[None]
            render, _, _ = rasterization(
                means=means, quats=torch.nn.functional.normalize(quats, dim=-1),
                scales=scales, opacities=opac, colors=colors,
                viewmats=viewmat, Ks=K, width=W, height=H,
            )
            frame = (render[0].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
            cv2.imwrite(str(tmp / f"{i:04d}.jpg"), cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
            if i % 10 == 0:
                ctx.report_progress(0.3 + 0.6 * i / n_frames, "Rendering turntable preview")

        ctx.run_subprocess([
            settings.ffmpeg_path, "-y", "-v", "error", "-framerate", "30",
            "-i", str(tmp / "%04d.jpg"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(preview_dir / "turntable.mp4"),
        ])
        shutil.rmtree(tmp)
        return "preview/turntable.mp4"


def look_at(eye: np.ndarray, target: np.ndarray, up=(0.0, -1.0, 0.0)) -> np.ndarray:
    """World-to-camera matrix, COLMAP/OpenCV convention (x right, y down, z forward)."""
    f = target - eye
    f = f / np.linalg.norm(f)
    r = np.cross(f, np.array(up))
    r = r / np.linalg.norm(r)
    d = np.cross(f, r)
    w2c = np.eye(4)
    w2c[:3, :3] = np.stack([r, d, f])
    w2c[:3, 3] = -w2c[:3, :3] @ eye
    return w2c
