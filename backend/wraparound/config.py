"""Application settings.

Settings are persisted to a JSON file in the user's app-data directory and can be
overridden with WRAPAROUND_* environment variables (useful for development and tests).
"""

from __future__ import annotations

import json
import platform
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Path:
    home = Path.home()
    if platform.system() == "Darwin":
        return home / "Library" / "Application Support" / "Wraparound"
    if platform.system() == "Windows":
        return home / "AppData" / "Roaming" / "Wraparound"
    return home / ".local" / "share" / "wraparound"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WRAPAROUND_")

    host: str = "127.0.0.1"
    port: int = 7345

    data_dir: Path = Field(default_factory=default_data_dir)
    projects_dir: Path | None = None  # defaults to data_dir / "projects"
    cache_dir: Path | None = None  # defaults to data_dir / "cache"
    temp_dir: Path | None = None  # defaults to data_dir / "tmp"

    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    colmap_path: str = "colmap"
    node_path: str = "node"
    opensplat_path: str | None = None  # auto-detected (vendor build / PATH) when unset

    gpu_index: int = 0
    cpu_threads: int = 0  # 0 = auto
    frame_quality: int = 95  # JPEG quality for extracted frames
    auto_save: bool = True
    auto_delete_intermediates: bool = False

    default_pose_backend: str = "colmap"
    default_train_backend: str = "splatfacto"

    @property
    def projects_path(self) -> Path:
        return self.projects_dir or self.data_dir / "projects"

    @property
    def cache_path(self) -> Path:
        return self.cache_dir or self.data_dir / "cache"

    @property
    def temp_path(self) -> Path:
        return self.temp_dir or self.data_dir / "tmp"

    @property
    def settings_file(self) -> Path:
        return self.data_dir / "settings.json"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.projects_path, self.cache_path, self.temp_path):
            p.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        self.ensure_dirs()
        data = self.model_dump(mode="json", exclude={"host", "port"})
        self.settings_file.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls) -> "Settings":
        base = cls()
        if base.settings_file.exists():
            try:
                stored = json.loads(base.settings_file.read_text())
                base = cls(**{**stored, "host": base.host, "port": base.port})
            except (json.JSONDecodeError, ValueError):
                pass  # corrupt settings file — fall back to defaults
        base.ensure_dirs()
        return base


settings = Settings.load()
