"""Project store — each project is a plain, portable folder.

Project/
  video.mp4        original upload
  frames/          filtered frames used for reconstruction
  frames_raw/      extracted candidates (deleted if auto_delete_intermediates)
  colmap/          COLMAP database + workspace
  sparse/          sparse reconstruction (COLMAP model)
  splat/           training workspace + trained model (point_cloud.ply)
  preview/         thumbnail + turntable preview
  exports/         user exports (.ply/.splat/.ksplat)
  metadata.json    ProjectMeta
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from .config import settings
from .models import ProjectMeta, utcnow

SUBDIRS = ["frames", "frames_raw", "colmap", "sparse", "splat", "preview", "exports"]


class ProjectError(Exception):
    pass


class ProjectStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.projects_path
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, project_id: str) -> Path:
        p = (self.root / project_id).resolve()
        if p.parent != self.root.resolve():  # guard against path traversal in ids
            raise ProjectError(f"Invalid project id: {project_id}")
        return p

    def _meta_file(self, project_id: str) -> Path:
        return self.path(project_id) / "metadata.json"

    def create(self, name: str) -> ProjectMeta:
        project_id = uuid.uuid4().hex[:12]
        p = self.path(project_id)
        for sub in SUBDIRS:
            (p / sub).mkdir(parents=True, exist_ok=True)
        meta = ProjectMeta(id=project_id, name=name)
        self.save(meta)
        return meta

    def load(self, project_id: str) -> ProjectMeta:
        f = self._meta_file(project_id)
        if not f.exists():
            raise ProjectError(f"Project not found: {project_id}")
        return ProjectMeta.model_validate_json(f.read_text())

    def save(self, meta: ProjectMeta) -> None:
        meta.updated_at = utcnow()
        f = self._meta_file(meta.id)
        tmp = f.with_suffix(".json.tmp")
        tmp.write_text(meta.model_dump_json(indent=2))
        tmp.replace(f)  # atomic — a crash never corrupts metadata

    def list(self) -> list[ProjectMeta]:
        metas = []
        for d in sorted(self.root.iterdir()):
            f = d / "metadata.json"
            if f.exists():
                try:
                    metas.append(ProjectMeta.model_validate_json(f.read_text()))
                except ValueError:
                    continue  # skip unreadable projects rather than failing the listing
        return sorted(metas, key=lambda m: m.updated_at, reverse=True)

    def duplicate(self, project_id: str, new_name: str | None = None) -> ProjectMeta:
        src_meta = self.load(project_id)
        dst_meta = self.create(new_name or f"{src_meta.name} (copy)")
        src, dst = self.path(project_id), self.path(dst_meta.id)
        for item in src.iterdir():
            if item.name == "metadata.json":
                continue
            if item.is_dir():
                shutil.copytree(item, dst / item.name, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst / item.name)
        dst_meta.video_file = src_meta.video_file
        dst_meta.validation = src_meta.validation
        dst_meta.config = src_meta.config
        dst_meta.job = src_meta.job
        dst_meta.stats = dict(src_meta.stats)
        self.save(dst_meta)
        return dst_meta

    def delete(self, project_id: str) -> None:
        p = self.path(project_id)
        if p.exists():
            shutil.rmtree(p)

    def video_path(self, project_id: str) -> Path | None:
        meta = self.load(project_id)
        if not meta.video_file:
            return None
        return self.path(project_id) / meta.video_file


store = ProjectStore()
