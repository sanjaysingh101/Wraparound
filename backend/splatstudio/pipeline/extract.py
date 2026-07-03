"""Adaptive frame extraction.

Two passes:
1. FFmpeg decodes the video into candidate frames at a capped sampling rate
   (bounded by ~3× the target so pass 2 has room to choose).
2. Optical-flow analysis over the candidates accumulates camera motion; frames are
   selected each time accumulated motion crosses a step, giving an even *spatial*
   (not temporal) distribution — dense where the camera moves, sparse where it lingers.

Output: frames_raw/ with the selected candidates for the filtering stage.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..config import settings
from ..models import StageName
from .base import PipelineStage, StageContext, StageError
from .video import probe_video


def _flow_magnitude(prev_gray: np.ndarray, gray: np.ndarray) -> float:
    pts = cv2.goodFeaturesToTrack(prev_gray, maxCorners=150, qualityLevel=0.01, minDistance=16)
    if pts is None or len(pts) < 8:
        return 0.0
    nxt, status, _ = cv2.calcOpticalFlowPyrLK(prev_gray, gray, pts, None)
    good = status.reshape(-1).astype(bool)
    if good.sum() < 8:
        return 0.0
    d = (nxt - pts).reshape(-1, 2)[good]
    return float(np.median(np.linalg.norm(d, axis=1)))


def select_by_motion(motions: list[float], target: int) -> list[int]:
    """Pick `target` indices from candidates so cumulative motion between picks is even."""
    n = len(motions)
    if n <= target:
        return list(range(n))
    cumulative = np.concatenate([[0.0], np.cumsum(np.maximum(motions, 1e-3))])
    total = cumulative[-1]
    step = total / (target - 1)
    picks, next_threshold = [0], step
    for i in range(1, n):
        if cumulative[i] >= next_threshold:
            picks.append(i)
            next_threshold += step
            if len(picks) == target:
                break
    if picks[-1] != n - 1 and len(picks) < target:
        picks.append(n - 1)
    return picks


class ExtractFramesStage(PipelineStage):
    name = StageName.extracting_frames

    def should_skip(self, ctx: StageContext) -> bool:
        raw = ctx.project_dir / "frames_raw"
        return raw.exists() and len(list(raw.glob("*.jpg"))) >= ctx.config.extraction.target_min_frames

    def run(self, ctx: StageContext) -> dict[str, Any]:
        cfg = ctx.config.extraction
        video = ctx.project_dir / "video.mp4"
        if not video.exists():
            video = Path(ctx.outputs.get("video", ""))
        if not video.exists():
            raise StageError("Project video is missing.")
        info = probe_video(video)

        raw_dir = ctx.project_dir / "frames_raw"
        cand_dir = ctx.project_dir / "frames_candidates"
        for d in (raw_dir, cand_dir):
            if d.exists():
                shutil.rmtree(d)
            d.mkdir(parents=True)

        # Pass 1 — FFmpeg decodes candidates at a rate bounded by 3× the max target.
        candidate_cap = cfg.target_max_frames * 3
        sample_fps = min(info.fps or 30.0, max(candidate_cap / max(info.duration_s, 1.0), 1.0))
        ctx.report_progress(0.05, f"Decoding candidates at {sample_fps:.1f} fps")
        vf = f"fps={sample_fps:.4f}"
        if info.height > 2160 or info.width > 2160:  # cap 4K+ inputs to keep COLMAP tractable
            vf += ",scale='min(2160,iw)':'min(2160,ih)':force_original_aspect_ratio=decrease"
        ctx.run_subprocess([
            settings.ffmpeg_path, "-y", "-v", "error", "-i", str(video),
            "-vf", vf,
            "-q:v", str(max(2, 31 - cfg.quality * 29 // 100)),
            str(cand_dir / "%05d.jpg"),
        ])
        candidates = sorted(cand_dir.glob("*.jpg"))
        if len(candidates) < 10:
            raise StageError("FFmpeg produced too few frames — the video may be corrupt.")

        # Pass 2 — accumulate motion and pick frames evenly in *motion* space.
        ctx.report_progress(0.35, "Measuring camera motion")
        motions: list[float] = []
        prev_gray = None
        for i, f in enumerate(candidates):
            ctx.check_cancelled()
            img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
            h, w = img.shape
            scale = 480.0 / max(h, w)
            small = cv2.resize(img, (int(w * scale), int(h * scale))) if scale < 1 else img
            if prev_gray is not None:
                motions.append(_flow_magnitude(prev_gray, small))
            prev_gray = small
            if i % 20 == 0:
                ctx.report_progress(0.35 + 0.45 * i / len(candidates), "Measuring camera motion")

        # Scene complexity scales the target: more total motion → more frames.
        total_motion = float(np.sum(motions))
        richness = np.clip((total_motion - 200) / 2000, 0.0, 1.0)
        target = int(cfg.target_min_frames + richness * (cfg.target_max_frames - cfg.target_min_frames))
        target = min(target, len(candidates))

        picks = select_by_motion(motions, target)
        ctx.report_progress(0.85, f"Selecting {len(picks)} of {len(candidates)} frames")
        for out_idx, cand_idx in enumerate(picks):
            shutil.copy2(candidates[cand_idx], raw_dir / f"{out_idx:05d}.jpg")
        shutil.rmtree(cand_dir)

        ctx.report_progress(1.0, f"Extracted {len(picks)} frames")
        return {"extracted": len(picks), "candidates": len(candidates), "target": target}
