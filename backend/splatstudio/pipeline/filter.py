"""Frame quality filtering.

Removes near-duplicates (perceptual dhash), motion-blurred / out-of-focus frames
(variance of Laplacian, relative to the batch), and badly exposed frames. Thresholds
are adaptive — computed from the batch's own distribution — so a slightly soft video
still keeps its best frames instead of losing everything.

Writes survivors to frames/ with sequential names (COLMAP-friendly).
"""

from __future__ import annotations

import shutil
from typing import Any

import cv2
import numpy as np

from ..models import StageName
from .base import PipelineStage, StageContext, StageError

MIN_KEEP = 60  # below this COLMAP rarely converges


def dhash(gray: np.ndarray, size: int = 8) -> int:
    small = cv2.resize(gray, (size + 1, size))
    diff = small[:, 1:] > small[:, :-1]
    return int(np.packbits(diff.flatten()).tobytes().hex() or "0", 16)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def frame_metrics(gray: np.ndarray) -> dict[str, float]:
    return {
        "sharpness": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "brightness": float(gray.mean()),
        "clipped_high": float((gray > 250).mean()),
        "clipped_low": float((gray < 5).mean()),
    }


class FilterFramesStage(PipelineStage):
    name = StageName.filtering_frames

    def should_skip(self, ctx: StageContext) -> bool:
        frames = ctx.project_dir / "frames"
        return frames.exists() and len(list(frames.glob("*.jpg"))) >= MIN_KEEP

    def run(self, ctx: StageContext) -> dict[str, Any]:
        raw_dir = ctx.project_dir / "frames_raw"
        out_dir = ctx.project_dir / "frames"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)

        files = sorted(raw_dir.glob("*.jpg"))
        if not files:
            raise StageError("No extracted frames found — run frame extraction first.")

        metrics, hashes = [], []
        for i, f in enumerate(files):
            ctx.check_cancelled()
            gray = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
            h, w = gray.shape
            scale = 640.0 / max(h, w)
            small = cv2.resize(gray, (int(w * scale), int(h * scale))) if scale < 1 else gray
            metrics.append(frame_metrics(small))
            hashes.append(dhash(small))
            if i % 25 == 0:
                ctx.report_progress(0.6 * i / len(files), "Scoring frames")

        sharp = np.array([m["sharpness"] for m in metrics])
        # Adaptive blur threshold: drop the clearly-soft tail, capped so we never
        # discard everything in an overall-soft video.
        blur_cutoff = min(np.percentile(sharp, 20), 60.0)

        removed = {"blurry": 0, "dark": 0, "overexposed": 0, "duplicate": 0}
        kept: list[int] = []
        last_hash: int | None = None
        for i, m in enumerate(metrics):
            if m["sharpness"] < blur_cutoff:
                removed["blurry"] += 1
            elif m["brightness"] < 30 or m["clipped_low"] > 0.5:
                removed["dark"] += 1
            elif m["brightness"] > 235 or m["clipped_high"] > 0.3:
                removed["overexposed"] += 1
            elif last_hash is not None and hamming(hashes[i], last_hash) <= 4:
                removed["duplicate"] += 1
            else:
                kept.append(i)
                last_hash = hashes[i]

        # Never filter below the viability floor — put back the sharpest rejects.
        if len(kept) < min(MIN_KEEP, len(files)):
            rejected = [i for i in range(len(files)) if i not in set(kept)]
            rejected.sort(key=lambda i: -metrics[i]["sharpness"])
            need = min(MIN_KEEP, len(files)) - len(kept)
            kept = sorted(kept + rejected[:need])

        ctx.report_progress(0.8, f"Keeping {len(kept)} of {len(files)} frames")
        for out_idx, i in enumerate(kept):
            shutil.copy2(files[i], out_dir / f"frame_{out_idx:05d}.jpg")

        if len(kept) < 20:
            raise StageError(
                "Fewer than 20 usable frames survived quality filtering. The capture is too "
                "blurry or poorly exposed for reconstruction — please re-shoot."
            )

        ctx.report_progress(1.0, f"{len(kept)} frames ready")
        return {"kept": len(kept), "removed": removed, "blur_cutoff": round(float(blur_cutoff), 1)}
