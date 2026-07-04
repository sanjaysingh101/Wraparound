"""Export backends: convert the canonical splat/point_cloud.ply into delivery formats.

Each exporter is registered in `export_backends`; future formats (GLB, OBJ, mesh
extraction) plug in the same way.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class Exporter(ABC):
    extension: str

    @abstractmethod
    def export(self, ply_path: Path, out_path: Path) -> dict: ...

    @classmethod
    def available(cls) -> tuple[bool, str]:
        return True, ""


from . import formats  # noqa: E402,F401  — registers ply/splat/ksplat
