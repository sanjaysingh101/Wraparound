#!/usr/bin/env bash
# Build OpenSplat (vendor/OpenSplat) — the training backend used on machines without
# CUDA. On Apple Silicon it builds with the Metal (MPS) runtime; elsewhere CPU/CUDA.
# Links against the libtorch bundled with the backend venv's PyTorch.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d vendor/OpenSplat ]; then
  git clone --depth 1 https://github.com/pierotofy/OpenSplat vendor/OpenSplat
fi

command -v cmake >/dev/null || { echo "cmake missing — brew install cmake"; exit 1; }

# Prefer Homebrew's libtorch: it shares one OpenMP runtime with Homebrew OpenCV.
# (Mixing pip-torch's bundled libomp with brew OpenCV's libomp crashes at runtime.)
if TORCH_BREW="$(brew --prefix pytorch 2>/dev/null)"; then
  TORCH_CMAKE="$TORCH_BREW/share/cmake"
else
  TORCH_CMAKE="$(backend/.venv/bin/python -c 'import torch.utils; print(torch.utils.cmake_prefix_path)')"
fi
OPENCV_PREFIX="$(brew --prefix opencv 2>/dev/null || echo /usr/local)"

RUNTIME="CPU"
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
  RUNTIME="MPS"
elif command -v nvcc >/dev/null; then
  RUNTIME="CUDA"
fi
echo "Building OpenSplat with GPU_RUNTIME=$RUNTIME"

cmake -S vendor/OpenSplat -B vendor/OpenSplat/build \
  -DCMAKE_BUILD_TYPE=Release \
  -DGPU_RUNTIME="$RUNTIME" \
  -DCMAKE_PREFIX_PATH="$TORCH_CMAKE;$OPENCV_PREFIX"
cmake --build vendor/OpenSplat/build -j "$(sysctl -n hw.ncpu 2>/dev/null || nproc)"

echo "Built: vendor/OpenSplat/build/opensplat"
vendor/OpenSplat/build/opensplat --version || true
