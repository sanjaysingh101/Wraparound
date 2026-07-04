"""Minimal COLMAP binary model reader (no pycolmap dependency).

Reads cameras.bin / images.bin / points3D.bin and produces posed cameras with their
images loaded — everything the gsplat trainer needs.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..base import StageError


@dataclass
class Camera:
    name: str
    K: np.ndarray          # 3x3 intrinsics
    world_to_cam: np.ndarray  # 4x4
    width: int
    height: int


@dataclass
class Scene:
    cameras: list[Camera]
    images: list[np.ndarray]  # RGB float-ready uint8 arrays, aligned with cameras
    points: np.ndarray        # (N,3)
    colors: np.ndarray        # (N,3) uint8


def _read(fh, fmt: str):
    return struct.unpack(fmt, fh.read(struct.calcsize(fmt)))


def _qvec_to_rot(q: np.ndarray) -> np.ndarray:
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def _read_cameras_bin(path: Path) -> dict[int, tuple[np.ndarray, int, int]]:
    cams: dict[int, tuple[np.ndarray, int, int]] = {}
    # param counts per COLMAP camera model id
    n_params = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8, 5: 8, 6: 12, 7: 5, 8: 4, 9: 5, 10: 12}
    with path.open("rb") as fh:
        (count,) = _read(fh, "<Q")
        for _ in range(count):
            cam_id, model, w, h = _read(fh, "<iiQQ")
            params = np.array(_read(fh, f"<{n_params[model]}d"))
            if model in (0, 1):        # SIMPLE_PINHOLE / PINHOLE
                fx = params[0]
                fy = params[1] if model == 1 else params[0]
                cx, cy = params[-2], params[-1]
            elif model in (2, 3, 4):   # SIMPLE_RADIAL / RADIAL / OPENCV
                fx = params[0]
                fy = params[1] if model == 4 else params[0]
                cx, cy = (params[2], params[3]) if model == 4 else (params[1], params[2])
            else:
                fx = fy = params[0]
                cx, cy = w / 2, h / 2
            K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
            cams[cam_id] = (K, int(w), int(h))
    return cams


def _read_images_bin(path: Path) -> list[tuple[str, np.ndarray, int]]:
    out = []
    with path.open("rb") as fh:
        (count,) = _read(fh, "<Q")
        for _ in range(count):
            _img_id = _read(fh, "<I")[0]
            qvec = np.array(_read(fh, "<4d"))
            tvec = np.array(_read(fh, "<3d"))
            (cam_id,) = _read(fh, "<i")
            name = b""
            while (c := fh.read(1)) != b"\x00":
                name += c
            (n_pts,) = _read(fh, "<Q")
            fh.seek(n_pts * 24, 1)  # skip 2D points (x,y,point3D_id)
            w2c = np.eye(4)
            w2c[:3, :3] = _qvec_to_rot(qvec)
            w2c[:3, 3] = tvec
            out.append((name.decode(), w2c, cam_id))
    return out


def _read_points_bin(path: Path) -> tuple[np.ndarray, np.ndarray]:
    pts, cols = [], []
    with path.open("rb") as fh:
        (count,) = _read(fh, "<Q")
        for _ in range(count):
            _pid = _read(fh, "<Q")[0]
            xyz = _read(fh, "<3d")
            rgb = _read(fh, "<3B")
            _err = _read(fh, "<d")
            (track_len,) = _read(fh, "<Q")
            fh.seek(track_len * 8, 1)
            pts.append(xyz)
            cols.append(rgb)
    return np.array(pts, dtype=np.float64), np.array(cols, dtype=np.uint8)


def load_colmap_scene(model_dir: Path, images_dir: Path, max_dim: int = 1600) -> Scene:
    for f in ("cameras.bin", "images.bin", "points3D.bin"):
        if not (model_dir / f).exists():
            raise StageError(f"COLMAP model incomplete: missing {f} in {model_dir}")
    intrinsics = _read_cameras_bin(model_dir / "cameras.bin")
    image_entries = _read_images_bin(model_dir / "images.bin")
    points, colors = _read_points_bin(model_dir / "points3D.bin")

    cameras, images = [], []
    for name, w2c, cam_id in sorted(image_entries):
        img_path = images_dir / name
        if not img_path.exists():
            continue
        K, w, h = intrinsics[cam_id]
        img = cv2.cvtColor(cv2.imread(str(img_path)), cv2.COLOR_BGR2RGB)
        scale = min(max_dim / max(img.shape[:2]), 1.0)
        if scale < 1.0:
            img = cv2.resize(img, (int(img.shape[1] * scale), int(img.shape[0] * scale)))
            K = K.copy()
            K[:2] *= scale
        cameras.append(Camera(name=name, K=K, world_to_cam=w2c,
                              width=img.shape[1], height=img.shape[0]))
        images.append(img)

    if not cameras:
        raise StageError("No registered images matched files on disk.")
    return Scene(cameras=cameras, images=images, points=points, colors=colors)
