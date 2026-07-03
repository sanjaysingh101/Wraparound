"""FastAPI application entry point (runs as a local sidecar of the desktop shell)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import exports, jobs, projects, settings as settings_api, system
from .config import settings
from .events import bus
from .plugins import load_plugins

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    bus.bind_loop(asyncio.get_running_loop())
    load_plugins()
    settings.ensure_dirs()
    from .jobs import recover_interrupted_jobs

    n = recover_interrupted_jobs()
    if n:
        logging.getLogger(__name__).info("Recovered %d interrupted job(s)", n)
    yield


app = FastAPI(title="Splat Studio", version=__version__, lifespan=lifespan)

# Local-only service; CORS covers the Vite dev server and the Tauri webview origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "tauri://localhost", "http://tauri.localhost"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(projects.router)
app.include_router(jobs.router)
app.include_router(settings_api.router)
app.include_router(exports.router)

# Serve the built frontend from the same (persistent) process, so the UI lives at a
# single stable URL — http://127.0.0.1:7345 — and does not depend on a separate dev
# server that can idle out. Mounted last so /api/* routes take precedence. In active
# development the Vite dev server on :5173 is used instead (this mount is a no-op when
# app/dist has not been built).
_frontend_dist = Path(__file__).resolve().parents[2] / "app" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")


def run() -> None:
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    run()
