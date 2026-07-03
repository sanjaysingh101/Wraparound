"""PLY / SPLAT / KSPLAT exporters.

- PLY: the canonical artifact, copied (optionally re-pruned) as-is.
- SPLAT: antimatter15 format — 32 bytes per gaussian:
    float32 x,y,z · float32 sx,sy,sz · uint8 rgba · uint8 quat(wxyz, biased) —
  gaussians sorted by opacity·volume as web viewers expect.
- KSPLAT: produced by the @mkkellogg/gaussian-splats-3d converter via a small Node
  script (tools/convert-ksplat.mjs), since the format is defined by that library.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
from plyfile import PlyData

from ...config import settings
from ..base import StageError, export_backends
from . import Exporter

SH_C0 = 0.28209479177387814


def load_gaussians(ply_path: Path) -> dict[str, np.ndarray]:
    v = PlyData.read(str(ply_path))["vertex"].data
    return {
        "xyz": np.stack([v["x"], v["y"], v["z"]], 1).astype(np.float32),
        "scales": np.exp(np.stack([v["scale_0"], v["scale_1"], v["scale_2"]], 1)).astype(np.float32),
        "quats": np.stack([v["rot_0"], v["rot_1"], v["rot_2"], v["rot_3"]], 1).astype(np.float32),
        "opacity": (1 / (1 + np.exp(-np.asarray(v["opacity"])))).astype(np.float32),
        "rgb": np.clip(
            np.stack([v["f_dc_0"], v["f_dc_1"], v["f_dc_2"]], 1) * SH_C0 + 0.5, 0, 1
        ).astype(np.float32),
    }


@export_backends.register("ply")
class PlyExporter(Exporter):
    extension = ".ply"

    def export(self, ply_path: Path, out_path: Path) -> dict:
        shutil.copy2(ply_path, out_path)
        return {"format": "ply", "bytes": out_path.stat().st_size}


@export_backends.register("splat")
class SplatExporter(Exporter):
    extension = ".splat"

    def export(self, ply_path: Path, out_path: Path) -> dict:
        g = load_gaussians(ply_path)
        n = len(g["xyz"])

        importance = g["opacity"] * g["scales"].prod(axis=1)
        order = np.argsort(-importance)

        buf = np.empty(n, dtype=[("pos", "3f4"), ("scale", "3f4"),
                                 ("rgba", "4u1"), ("quat", "4u1")])
        buf["pos"] = g["xyz"][order]
        buf["scale"] = g["scales"][order]
        buf["rgba"][:, :3] = (g["rgb"][order] * 255).astype(np.uint8)
        buf["rgba"][:, 3] = (g["opacity"][order] * 255).astype(np.uint8)
        q = g["quats"][order]
        q = q / np.linalg.norm(q, axis=1, keepdims=True)
        buf["quat"] = np.clip(q * 128 + 128, 0, 255).astype(np.uint8)

        out_path.write_bytes(buf.tobytes())
        return {"format": "splat", "gaussians": n, "bytes": out_path.stat().st_size}


@export_backends.register("ksplat")
class KsplatExporter(Exporter):
    extension = ".ksplat"

    @classmethod
    def available(cls) -> tuple[bool, str]:
        if not shutil.which(settings.node_path):
            return False, "KSPLAT export needs Node.js (used to run the official converter)."
        return True, ""

    def export(self, ply_path: Path, out_path: Path) -> dict:
        script = Path(__file__).resolve().parents[4] / "tools" / "convert-ksplat.mjs"
        if not script.exists():
            raise StageError(f"Converter script missing: {script}")
        proc = subprocess.run(
            [settings.node_path, str(script), str(ply_path), str(out_path)],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0 or not out_path.exists():
            raise StageError(f"ksplat conversion failed: {(proc.stderr or proc.stdout)[-400:]}")
        return {"format": "ksplat", "bytes": out_path.stat().st_size}
