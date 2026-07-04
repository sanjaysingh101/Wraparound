"""Plugin loading.

Third-party packages extend the pipeline through the `wraparound.plugins` entry-point
group. A plugin exposes a `register(api)` callable receiving this module's PluginAPI,
through which it can add pose/train/export backends or wrap the stage list (e.g. insert
a background-removal stage before pose estimation, or a mesh-extraction stage after
training).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import Callable

from .pipeline.base import PipelineStage, export_backends, pose_backends, train_backends

log = logging.getLogger(__name__)

StageListHook = Callable[[list[PipelineStage]], list[PipelineStage]]


@dataclass
class PluginAPI:
    pose_backends = pose_backends
    train_backends = train_backends
    export_backends = export_backends
    stage_hooks: list[StageListHook] = field(default_factory=list)

    def add_stage_hook(self, hook: StageListHook) -> None:
        self.stage_hooks.append(hook)


api = PluginAPI()
_loaded = False


def load_plugins() -> list[str]:
    global _loaded
    if _loaded:
        return []
    _loaded = True
    names = []
    for ep in entry_points(group="wraparound.plugins"):
        try:
            register = ep.load()
            register(api)
            names.append(ep.name)
            log.info("Loaded plugin: %s", ep.name)
        except Exception:
            log.exception("Plugin %s failed to load — skipping", ep.name)
    return names


def extra_stages(stages: list[PipelineStage]) -> list[PipelineStage]:
    for hook in api.stage_hooks:
        stages = hook(stages)
    return stages
