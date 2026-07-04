"""In-process event bus bridging pipeline progress to WebSocket subscribers.

Pipeline stages run in worker threads / subprocesses and publish thread-safely via
`publish_threadsafe`; WebSocket handlers subscribe per-project with asyncio queues.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, project_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers[project_id].add(q)
        return q

    def unsubscribe(self, project_id: str, q: asyncio.Queue) -> None:
        self._subscribers[project_id].discard(q)
        if not self._subscribers[project_id]:
            del self._subscribers[project_id]

    def publish(self, project_id: str, event: dict[str, Any]) -> None:
        for q in list(self._subscribers.get(project_id, ())):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow consumer — drop rather than stall the pipeline

    def publish_threadsafe(self, project_id: str, event: dict[str, Any]) -> None:
        if self._loop is None or self._loop.is_closed():
            return
        self._loop.call_soon_threadsafe(self.publish, project_id, event)


bus = EventBus()
