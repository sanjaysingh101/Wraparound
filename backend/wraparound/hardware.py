"""Hardware and external-tool detection.

Torch is imported lazily so the API server starts instantly and works on machines where
the training stack isn't installed yet.
"""

from __future__ import annotations

import functools
import os
import platform
import re
import shutil
import subprocess

import psutil

from .config import settings
from .models import GPUInfo, HardwareInfo, ToolStatus


@functools.lru_cache(maxsize=1)
def detect_hardware() -> HardwareInfo:
    info = HardwareInfo(
        platform=f"{platform.system()} {platform.release()} ({platform.machine()})",
        cpu_cores=os.cpu_count() or 1,
        ram_mb=int(psutil.virtual_memory().total / 1024 / 1024),
    )
    try:
        import torch

        info.torch_version = torch.__version__
        info.cuda_available = torch.cuda.is_available()
        info.mps_available = bool(getattr(torch.backends, "mps", None)) and torch.backends.mps.is_available()
        if info.cuda_available:
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                info.gpus.append(
                    GPUInfo(name=props.name, vram_mb=int(props.total_memory / 1024 / 1024), cuda=True)
                )
    except ImportError:
        info.warnings.append(
            "PyTorch is not installed — training is unavailable. Run scripts/setup.sh to install the training stack."
        )
    if not info.cuda_available:
        from .pipeline.train.opensplat import find_opensplat

        has_opensplat = find_opensplat() is not None
        if info.mps_available:
            msg = "No CUDA GPU detected. Training uses the OpenSplat backend on Apple's Metal GPU — " \
                  "slower than CUDA but fully local." if has_opensplat else \
                  "No CUDA GPU detected and OpenSplat is not built — run scripts/build-opensplat.sh " \
                  "to enable training on Apple Silicon (Metal)."
            info.warnings.append(msg)
        else:
            info.warnings.append(
                "No GPU acceleration detected. Training will run on CPU and may take many hours; "
                "a CUDA GPU with 6 GB+ VRAM is recommended."
            )
    return info


def _tool_version(cmd: list[str], pattern: str) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        m = re.search(pattern, out.stdout + out.stderr)
        return m.group(1) if m else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def check_tool(name: str, configured_path: str, version_args: list[str], pattern: str) -> ToolStatus:
    path = shutil.which(configured_path)
    if not path:
        return ToolStatus(name=name, found=False)
    return ToolStatus(name=name, found=True, path=path, version=_tool_version([path, *version_args], pattern))


def detect_tools() -> list[ToolStatus]:
    return [
        check_tool("ffmpeg", settings.ffmpeg_path, ["-version"], r"ffmpeg version (\S+)"),
        check_tool("ffprobe", settings.ffprobe_path, ["-version"], r"ffprobe version (\S+)"),
        check_tool("colmap", settings.colmap_path, ["--help"], r"COLMAP (\S+)"),
        check_tool("node", settings.node_path, ["--version"], r"v?(\S+)"),
    ]


def training_available() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


def cpu_threads() -> int:
    return settings.cpu_threads or (os.cpu_count() or 4)
