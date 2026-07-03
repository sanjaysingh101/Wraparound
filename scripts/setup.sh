#!/usr/bin/env bash
# One-time development setup: Python venv + deps, Node deps, external tool checks.
set -euo pipefail
cd "$(dirname "$0")/.."

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
warn() { printf "\033[33m%s\033[0m\n" "$*"; }

# --- uv (Python package manager)
if ! command -v uv >/dev/null; then
  bold "Installing uv…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# --- Python backend
bold "Setting up Python backend…"
(cd backend && uv venv .venv --allow-existing && uv pip install -e ".[dev]" --python .venv/bin/python)

# Training stack (torch + gsplat + nerfstudio) — heavy; best effort.
if [ "${SPLATSTUDIO_SKIP_TRAINING:-0}" != "1" ]; then
  bold "Installing training stack (torch/gsplat/nerfstudio) — this can take a while…"
  (cd backend && uv pip install -e ".[training]" --python .venv/bin/python) \
    || warn "Training stack install failed — the app will run, but training is disabled. Re-run later or install manually."
fi

# On machines without CUDA (e.g. Apple Silicon), gsplat/nerfstudio cannot train.
# OpenSplat (C++, Metal/CPU) fills that gap — build it when no CUDA is present.
if ! command -v nvcc >/dev/null; then
  bold "No CUDA detected — building OpenSplat (Metal/CPU training backend)…"
  ./scripts/build-opensplat.sh || warn "OpenSplat build failed — training unavailable on this machine."
fi

# --- Node frontend
if command -v npm >/dev/null; then
  bold "Installing frontend dependencies…"
  (cd app && npm install)
else
  warn "npm not found — install Node.js 20+ to build the frontend."
fi

# --- External tools
for tool in ffmpeg colmap; do
  if command -v "$tool" >/dev/null; then
    bold "✓ $tool found: $(command -v "$tool")"
  else
    case "$(uname -s)" in
      Darwin) warn "✗ $tool missing — install with: brew install $tool" ;;
      Linux)  warn "✗ $tool missing — install with your package manager (apt install $tool)" ;;
      *)      warn "✗ $tool missing — download from the official site and add to PATH" ;;
    esac
  fi
done

bold "Setup complete. Start developing with: ./scripts/dev.sh"
