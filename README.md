# Wraparound

![Wraparound](docs/hero.png)

A local-first desktop application that turns a video into a high-quality 3D Gaussian Splat.
Everything — frame extraction, camera pose estimation, training, preview, export — runs on
your machine. No cloud, no remote GPU, no telemetry.

```
Video → Validate → Extract Frames (FFmpeg) → Filter Frames (OpenCV)
      → Camera Poses (COLMAP) → Train (Splatfacto / gsplat) → Preview → Export
```

## Repository layout

```
backend/          Python pipeline service (FastAPI, runs as a local sidecar)
  wraparound/
    api/          REST + WebSocket routes
    pipeline/     Pipeline stages — every stage is a replaceable module
      poses/      Pose-estimation backends (COLMAP today; VGGT/MASt3R-ready)
      train/      Training backends (Splatfacto, gsplat)
      export/     PLY / SPLAT / KSPLAT exporters
app/              Tauri + React + TypeScript desktop shell
  src/            React UI (project manager, wizard, progress, 3D viewer)
  src-tauri/      Rust shell; spawns the Python backend as a sidecar
scripts/          Setup and development helpers
tools/            Auxiliary converters (ksplat)
```

## Prerequisites

- **Python 3.10+** and [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Node.js 20+** and npm
- **Rust** (for the Tauri shell): `curl https://sh.rustup.rs -sSf | sh`
- **FFmpeg** — `brew install ffmpeg` (auto-detected; a bundled copy is also supported)
- **COLMAP** — `brew install colmap` (auto-detected)
- A CUDA GPU is strongly recommended for training (Splatfacto/gsplat backends). On machines
  without CUDA — including Apple Silicon — training runs through the bundled **OpenSplat**
  backend (C++, Metal/CPU), built automatically by `scripts/setup.sh` / `scripts/build-opensplat.sh`.

`scripts/setup.sh` checks and installs everything it can.

## Development

```bash
./scripts/setup.sh          # one-time: venv, deps, tool checks
./scripts/dev.sh            # backend (uvicorn, :7345) + frontend (vite, :5173)
# or the full desktop shell:
cd app && npm run tauri dev
```

Backend API docs while running: http://127.0.0.1:7345/docs

### Long training runs — persistent daemon

Gaussian Splat training runs for 1–2 hours (longer on CPU/Metal than CUDA), and the
training subprocess is a child of the backend. A dev server that idles out or is closed
would take training down with it, so for real runs use the **detached daemon**:

```bash
npm --prefix app run build   # build the UI once (served by the backend)
./scripts/serve.sh start     # backend as an orphaned daemon (survives shell/editor exit)
./scripts/serve.sh status    # running on :7345
./scripts/serve.sh stop
```

The daemon serves the full app at a single stable URL — **http://127.0.0.1:7345** — so the
UI never depends on a separate server. Training is additionally **checkpointed**
(`splat/point_cloud_<step>.ply`, every ~1/15 of the run) and **auto-resumes** from the last
checkpoint, so even a hard kill or reboot only loses one interval of work. Jobs left running
by a killed process are marked "Interrupted — press Resume" on the next start.

## Design principles

- **Every pipeline stage is a module** implementing `PipelineStage`; pose estimation and
  training additionally sit behind backend registries so COLMAP can be swapped for
  VGGT/MASt3R/DUSt3R and Splatfacto for gsplat (or future backends) without touching the
  orchestrator.
- **Projects are plain folders** (`video.mp4`, `frames/`, `colmap/`, `splat/`, `exports/`,
  `metadata.json`) — portable, resumable, inspectable.
- **Jobs are resumable**: each stage records its status in `metadata.json`; a failed job
  restarts from the first incomplete stage.
- **Plugins**: third-party stages/backends register through the `wraparound.plugins`
  entry-point group.
