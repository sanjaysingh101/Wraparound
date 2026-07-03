"""Video validation stage.

Probes the container with ffprobe, then samples ~40 frames with OpenCV to measure
sharpness, exposure, shakiness and camera parallax. Produces a ValidationReport with
human-readable reject/warn issues so users learn how to capture better footage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..models import StageName, ValidationIssue, ValidationReport
from .base import PipelineStage, StageContext, StageError
from .video import probe_video

MIN_DURATION_S = 5.0
MIN_RESOLUTION = 480
SAMPLE_COUNT = 40

BLUR_REJECT = 40.0      # variance of Laplacian on the grayscale frame
BLUR_WARN = 100.0
DARK_REJECT = 35.0      # mean luma (0..255)
DARK_WARN = 60.0
BRIGHT_REJECT = 235.0
OVEREXPOSED_FRACTION = 0.25   # fraction of pixels at >250 luma
SHAKE_WARN = 18.0       # median per-sample flow jitter, px (residual after global motion)
SHAKE_REJECT = 40.0
MIN_MOTION_PX = 4.0     # median inter-sample feature displacement — parallax proxy


def _sample_metrics(video_path: Path, rotation: int) -> dict[str, float]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise StageError("OpenCV could not open this video (unsupported codec?).")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    indices = np.linspace(0, max(total - 1, 0), min(SAMPLE_COUNT, total)).astype(int)

    sharpness, brightness, over_frac = [], [], []
    motions, jitters, floor_motions = [], [], []
    prev_gray = None

    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if not ok:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # analysis is rotation-invariant, so we ignore `rotation` here
        h, w = gray.shape
        scale = 640.0 / max(h, w)
        if scale < 1.0:
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)))

        sharpness.append(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness.append(float(gray.mean()))
        over_frac.append(float((gray > 250).mean()))

        if prev_gray is not None and prev_gray.shape == gray.shape:
            pts = cv2.goodFeaturesToTrack(prev_gray, maxCorners=200, qualityLevel=0.01, minDistance=12)
            if pts is not None and len(pts) >= 8:
                nxt, status, _ = cv2.calcOpticalFlowPyrLK(prev_gray, gray, pts, None)
                good = status.reshape(-1).astype(bool)
                if good.sum() >= 8:
                    d = (nxt - pts).reshape(-1, 2)[good]
                    mag = np.linalg.norm(d, axis=1)
                    motions.append(float(np.median(mag)))
                    # jitter = spread of motion vectors around the dominant (camera) motion
                    jitters.append(float(np.linalg.norm(d - d.mean(axis=0), axis=1).mean()))
                    # 25th percentile ≈ background motion: if the camera moves, *everything*
                    # moves; a near-zero floor with high median = static camera, moving subject
                    floor_motions.append(float(np.percentile(mag, 25)))
        prev_gray = gray

    cap.release()
    if not sharpness:
        raise StageError("Could not decode any frames from this video.")
    return {
        "sharpness": float(np.median(sharpness)),
        "brightness": float(np.median(brightness)),
        "overexposed": float(np.mean(over_frac)),
        "motion": float(np.median(motions)) if motions else 0.0,
        "shakiness": float(np.median(jitters)) if jitters else 0.0,
        "background_motion": float(np.median(floor_motions)) if floor_motions else 0.0,
    }


def validate_video(video_path: Path) -> ValidationReport:
    info = probe_video(video_path)
    issues: list[ValidationIssue] = []

    def issue(code: str, severity: str, message: str) -> None:
        issues.append(ValidationIssue(code=code, severity=severity, message=message))

    if info.duration_s < MIN_DURATION_S:
        issue("too_short", "reject",
              f"The video is only {info.duration_s:.1f}s long. Capture at least {MIN_DURATION_S:.0f} "
              "seconds (ideally 20–60s) while moving slowly around the subject.")
    if min(info.width, info.height) < MIN_RESOLUTION:
        issue("low_resolution", "reject",
              f"Resolution {info.width}×{info.height} is too low. Use at least 720p; 1080p–4K works best.")

    m = _sample_metrics(video_path, info.rotation)

    if m["sharpness"] < BLUR_REJECT:
        issue("too_blurry", "reject",
              "Most frames are blurry. Move the camera more slowly, lock focus on the subject, "
              "and shoot in good light so the shutter speed stays high.")
    elif m["sharpness"] < BLUR_WARN:
        issue("soft_focus", "warn",
              "Frames are on the soft side; reconstruction quality may suffer. Slower, steadier "
              "movement and better lighting will help.")

    if m["brightness"] < DARK_REJECT:
        issue("too_dark", "reject",
              "The footage is too dark for reliable feature matching. Re-shoot with more light.")
    elif m["brightness"] < DARK_WARN:
        issue("dim", "warn", "The footage is dim; expect more noise in the reconstruction.")
    if m["brightness"] > BRIGHT_REJECT or m["overexposed"] > OVEREXPOSED_FRACTION:
        issue("overexposed", "reject",
              "Large parts of the image are blown out. Lower the exposure and avoid pointing "
              "directly at bright light sources or windows.")

    if m["shakiness"] > SHAKE_REJECT:
        issue("too_shaky", "reject",
              "The camera shake is too strong — motion blur and rolling shutter will break pose "
              "estimation. Hold the phone with both hands or use a gimbal, and walk smoothly.")
    elif m["shakiness"] > SHAKE_WARN:
        issue("shaky", "warn", "Noticeable camera shake detected; a steadier capture would improve results.")

    if m["motion"] < MIN_MOTION_PX:
        issue("low_motion", "reject",
              "The camera barely moves, so there is not enough parallax to reconstruct 3D. "
              "Orbit around the subject — aim to cover it from many angles.")
    elif m["background_motion"] < 0.5:
        # Subject moves but the background is frozen → fixed camera (tripod/turntable).
        issue("static_camera", "reject",
              "The camera appears to be fixed while the subject moves (a turntable-style video). "
              "Reconstruction needs the CAMERA to move through the scene: hold the camera and "
              "walk a slow circle around a stationary subject instead.")

    return ValidationReport(
        video=info,
        issues=issues,
        sharpness=round(m["sharpness"], 1),
        brightness=round(m["brightness"], 1),
        shakiness=round(m["shakiness"], 2),
        motion_coverage=round(m["motion"], 2),
    )


class ValidateStage(PipelineStage):
    name = StageName.preparing

    def run(self, ctx: StageContext) -> dict[str, Any]:
        ctx.report_progress(0.1, "Analyzing video")
        video = ctx.project_dir / "video.mp4"
        if not video.exists():
            candidates = [p for p in ctx.project_dir.iterdir()
                          if p.suffix.lower() in {".mp4", ".mov", ".m4v"}]
            if not candidates:
                raise StageError("No video found in the project. Upload a video first.")
            video = candidates[0]
        report = validate_video(video)
        ctx.report_progress(1.0, "Video analyzed")
        if not report.ok:
            rejects = "\n".join(f"• {i.message}" for i in report.issues if i.severity == "reject")
            raise StageError(f"This video is not suitable for reconstruction:\n{rejects}")
        return {"validation": report.model_dump(mode="json"), "video": str(video)}
