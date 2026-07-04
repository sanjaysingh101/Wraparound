"""Video probing via ffprobe."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..config import settings
from ..models import VideoInfo
from .base import StageError

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".m4v"}


def probe_video(path: Path) -> VideoInfo:
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise StageError(
            f"Unsupported format '{path.suffix}'. Supported formats: MP4, MOV, M4V."
        )
    cmd = [
        settings.ffprobe_path,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,nb_frames,bit_rate,codec_name,duration:stream_side_data=rotation:format=duration,bit_rate",
        "-of", "json",
        str(path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        raise StageError("ffprobe not found. Install FFmpeg or set its path in Settings.")
    if out.returncode != 0:
        raise StageError(f"Could not read video file: {out.stderr.strip()[:400]}")

    data = json.loads(out.stdout)
    streams = data.get("streams") or []
    if not streams:
        raise StageError("No video stream found in this file.")
    s = streams[0]
    fmt = data.get("format", {})

    num, _, den = (s.get("r_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    duration = float(s.get("duration") or fmt.get("duration") or 0)
    bitrate = int(s.get("bit_rate") or fmt.get("bit_rate") or 0) // 1000

    rotation = 0
    for sd in s.get("side_data_list") or []:
        if "rotation" in sd:
            rotation = int(sd["rotation"]) % 360

    frame_count = int(s.get("nb_frames") or 0) or int(duration * fps)

    return VideoInfo(
        path=str(path),
        width=int(s.get("width") or 0),
        height=int(s.get("height") or 0),
        fps=round(fps, 3),
        duration_s=round(duration, 3),
        frame_count=frame_count,
        bitrate_kbps=bitrate,
        rotation=rotation,
        codec=s.get("codec_name") or "",
    )
