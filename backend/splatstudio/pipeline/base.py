"""Pipeline framework.

Every stage of the reconstruction pipeline implements `PipelineStage` and communicates
only through the `StageContext` (project folder + config + progress callback). Pose
estimation and training are additionally pluggable *within* their stage via backend
registries, so e.g. COLMAP can be replaced by VGGT/MASt3R without touching orchestration.

Stages run in a worker thread (they call blocking subprocesses like ffmpeg/colmap);
progress is forwarded thread-safely to the asyncio event bus.
"""

from __future__ import annotations

import subprocess
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Type

from ..models import PipelineConfig, StageName


class StageCancelled(Exception):
    pass


class StageError(Exception):
    """Raised for expected, user-explainable failures (bad input, missing tool …)."""


@dataclass
class StageContext:
    project_id: str
    project_dir: Path
    config: PipelineConfig
    report_progress: Callable[[float, str], None]  # (0..1, message)
    cancel_event: threading.Event
    outputs: dict[str, Any] = field(default_factory=dict)  # accumulated stage outputs

    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise StageCancelled()

    def run_subprocess(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
        on_line: Callable[[str], None] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """Run an external tool, streaming output and honouring cancellation."""
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        tail: list[str] = []
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                line = line.rstrip()
                tail.append(line)
                if len(tail) > 40:
                    tail.pop(0)
                if on_line:
                    on_line(line)
                if self.cancel_event.is_set():
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    raise StageCancelled()
        finally:
            proc.stdout.close()
        proc.wait()
        if proc.returncode != 0:
            raise StageError(
                f"`{cmd[0]}` exited with code {proc.returncode}:\n" + "\n".join(tail[-15:])
            )


class PipelineStage(ABC):
    name: StageName

    @abstractmethod
    def run(self, ctx: StageContext) -> dict[str, Any]:
        """Execute the stage; return outputs to persist in the stage state."""

    def should_skip(self, ctx: StageContext) -> bool:
        """Return True when a previous run's outputs are still valid (resume support)."""
        return False


class Registry:
    """Named registry used for stage backends (poses, train, export) and plugins."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._items: dict[str, Type] = {}

    def register(self, name: str, cls: Type | None = None):
        if cls is not None:
            self._items[name] = cls
            return cls

        def deco(c: Type) -> Type:
            self._items[name] = c
            return c

        return deco

    def get(self, name: str) -> Type:
        if name not in self._items:
            raise StageError(
                f"Unknown {self.kind} backend '{name}'. Available: {', '.join(self._items) or 'none'}"
            )
        return self._items[name]

    def names(self) -> list[str]:
        return sorted(self._items)


pose_backends = Registry("pose")
train_backends = Registry("train")
export_backends = Registry("export")
