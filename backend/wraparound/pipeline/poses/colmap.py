"""COLMAP pose-estimation backend.

Runs feature extraction → matching (sequential by default — frames come from video,
so temporal neighbours overlap) → incremental mapping (bundle adjustment included).
Writes the sparse model to sparse/0 and reports how many frames were registered.
"""

from __future__ import annotations

import functools
import re
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Any

from ...config import settings
from ...hardware import cpu_threads, detect_hardware
from ..base import StageContext, StageError, pose_backends
from . import PoseBackend


@functools.lru_cache(maxsize=4)
def option_prefixes(colmap: str) -> tuple[str, str]:
    """(extraction_prefix, matching_prefix) for the installed COLMAP.

    COLMAP ≥3.12 renamed --SiftExtraction.*/--SiftMatching.* to
    --FeatureExtraction.*/--FeatureMatching.*; probe --help once to adapt.
    """
    try:
        out = subprocess.run([colmap, "feature_extractor", "--help"],
                             capture_output=True, text=True, timeout=30)
        if "FeatureExtraction.use_gpu" in out.stdout + out.stderr:
            return "FeatureExtraction", "FeatureMatching"
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "SiftExtraction", "SiftMatching"


def read_registered_count(model_dir: Path) -> int:
    """Count registered images in a COLMAP binary model without pycolmap."""
    f = model_dir / "images.bin"
    if not f.exists():
        return 0
    with f.open("rb") as fh:
        return struct.unpack("<Q", fh.read(8))[0]


@pose_backends.register("colmap")
class ColmapBackend(PoseBackend):
    def estimate(self, ctx: StageContext) -> dict[str, Any]:
        colmap = shutil.which(settings.colmap_path)
        if not colmap:
            raise StageError(
                "COLMAP was not found. Install it (macOS: `brew install colmap`) or set its "
                "path in Settings."
            )
        frames_dir = ctx.project_dir / "frames"
        n_frames = len(list(frames_dir.glob("*.jpg")))
        if n_frames < 20:
            raise StageError("Not enough frames for pose estimation.")

        work = ctx.project_dir / "colmap"
        sparse = ctx.project_dir / "sparse"
        for d in (work, sparse):
            if d.exists():
                shutil.rmtree(d)
            d.mkdir(parents=True)
        db = work / "database.db"

        use_gpu = "1" if detect_hardware().cuda_available else "0"
        threads = str(cpu_threads())
        ext_prefix, match_prefix = option_prefixes(colmap)

        ctx.report_progress(0.02, "COLMAP: extracting features")
        ctx.run_subprocess([
            colmap, "feature_extractor",
            "--database_path", str(db),
            "--image_path", str(frames_dir),
            "--ImageReader.camera_model", "OPENCV",
            "--ImageReader.single_camera", "1",   # one physical camera → shared intrinsics
            f"--{ext_prefix}.use_gpu", use_gpu,
            f"--{ext_prefix}.num_threads", threads,
        ], on_line=self._progress_parser(ctx, 0.02, 0.25, n_frames, r"Processed file \[(\d+)/(\d+)\]"))

        matcher = ctx.config.poses.matcher
        ctx.report_progress(0.25, f"COLMAP: matching features ({matcher})")
        if matcher == "exhaustive":
            match_cmd = [colmap, "exhaustive_matcher"]
        else:
            # Note: loop_detection stays off — it requires a vocabulary-tree file.
            match_cmd = [
                colmap, "sequential_matcher",
                "--SequentialMatching.overlap", "15",
            ]
        ctx.run_subprocess([
            *match_cmd,
            "--database_path", str(db),
            f"--{match_prefix}.use_gpu", use_gpu,
        ], on_line=self._progress_parser(ctx, 0.25, 0.45, n_frames, r"Matching block \[.*?(\d+)/(\d+)"))

        ctx.report_progress(0.45, "COLMAP: sparse reconstruction (bundle adjustment)")
        try:
            ctx.run_subprocess([
                colmap, "mapper",
                "--database_path", str(db),
                "--image_path", str(frames_dir),
                "--output_path", str(sparse),
                "--Mapper.num_threads", threads,
                "--Mapper.ba_global_function_tolerance", "1e-6",
            ], on_line=self._mapper_progress(ctx, n_frames))
        except StageError:
            diagnosis = self._diagnose_matches(db)
            if diagnosis:
                raise StageError(f"COLMAP could not reconstruct camera poses.\n\n{diagnosis}")
            raise

        model = self._pick_best_model(sparse)
        registered = read_registered_count(model)
        if registered < max(20, int(0.3 * n_frames)):
            raise StageError(
                f"COLMAP registered only {registered}/{n_frames} frames — the reconstruction is "
                "unreliable. Typical causes: textureless surfaces, reflections, or too-fast "
                "camera motion. Re-capture with more overlap between viewpoints."
            )
        ctx.report_progress(1.0, f"Poses estimated for {registered}/{n_frames} frames")
        return {"registered": registered, "total_frames": n_frames, "model_dir": str(model)}

    @staticmethod
    def _diagnose_matches(db: Path) -> str | None:
        """Explain a mapper failure in capture terms by classifying the verified pairs.

        COLMAP labels each verified image pair (two_view_geometries.config):
        2/3 = real camera motion (usable), 4/5/6 = planar or pure-rotation (no parallax),
        7 = 'watermark' — matches consistent with a static overlay or a frozen background.
        """
        import sqlite3

        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            rows = con.execute(
                "SELECT config, COUNT(*) FROM two_view_geometries WHERE rows > 0 GROUP BY config"
            ).fetchall()
            con.close()
        except sqlite3.Error:
            return None

        counts = dict(rows)
        total = sum(counts.values())
        if total == 0:
            return ("No image pairs could be matched at all. The scene likely lacks texture "
                    "(blank walls, reflective or transparent surfaces) or the frames don't "
                    "overlap. Re-capture with slower movement and a more textured subject.")
        usable = counts.get(2, 0) + counts.get(3, 0)
        static = counts.get(7, 0)
        rotation_only = counts.get(4, 0) + counts.get(5, 0) + counts.get(6, 0)

        if static / total > 0.4:
            return ("Most frame pairs show a frozen background — the camera appears to be "
                    "FIXED while the subject moves or rotates (e.g. a turntable video), or a "
                    "large watermark/overlay dominates the image. Structure-from-motion needs "
                    "the camera itself to move: hold the camera and walk a slow circle around "
                    "a stationary subject.")
        if rotation_only / total > 0.5:
            return ("The camera only rotates in place (panning) without moving through the "
                    "scene, so there is no parallax to triangulate 3D from. Physically walk "
                    "around the subject while recording instead of panning from one spot.")
        if usable < 15:
            return ("Too few usable image pairs survived geometric verification "
                    f"({usable}/{total}). Typical causes: motion blur, reflective/textureless "
                    "surfaces, or too little overlap between viewpoints. Move more slowly and "
                    "keep the subject fully in frame.")
        return None

    @staticmethod
    def _pick_best_model(sparse: Path) -> Path:
        """COLMAP may output several disconnected models; keep the largest as sparse/0."""
        models = sorted([d for d in sparse.iterdir() if d.is_dir() and d.name.isdigit()])
        if not models:
            raise StageError("COLMAP produced no reconstruction. The capture likely lacks "
                             "texture or viewpoint overlap.")
        best = max(models, key=read_registered_count)
        target = sparse / "0"
        if best != target:
            tmp = sparse / "_best"
            best.rename(tmp)
            for m in sparse.iterdir():
                if m.is_dir() and m.name.isdigit():
                    shutil.rmtree(m)
            tmp.rename(target)
        return target

    @staticmethod
    def _progress_parser(ctx: StageContext, lo: float, hi: float, total: int, pattern: str):
        rx = re.compile(pattern)

        def on_line(line: str) -> None:
            m = rx.search(line)
            if m:
                cur, tot = int(m.group(1)), int(m.group(2))
                if tot:
                    ctx.report_progress(lo + (hi - lo) * cur / tot, line.strip()[:120])

        return on_line

    @staticmethod
    def _mapper_progress(ctx: StageContext, n_frames: int):
        rx = re.compile(r"Registering image #\d+ \((\d+)\)")

        def on_line(line: str) -> None:
            m = rx.search(line)
            if m:
                ctx.report_progress(
                    0.45 + 0.5 * min(int(m.group(1)) / max(n_frames, 1), 1.0),
                    f"COLMAP: registered {m.group(1)}/{n_frames} images",
                )

        return on_line
