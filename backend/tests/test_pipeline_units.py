"""Unit tests for the pure-logic parts of the pipeline."""

import numpy as np
import pytest

from wraparound.pipeline.extract import select_by_motion
from wraparound.pipeline.filter import dhash, hamming, frame_metrics


class TestSelectByMotion:
    def test_returns_all_when_under_target(self):
        assert select_by_motion([1.0] * 5, 10) == [0, 1, 2, 3, 4]

    def test_respects_target_count(self):
        picks = select_by_motion([1.0] * 300, 100)
        assert len(picks) <= 100
        assert picks[0] == 0

    def test_dense_where_motion_is(self):
        # No motion for 100 frames, then strong motion for 100 frames:
        # picks should concentrate in the moving half.
        motions = [0.001] * 100 + [10.0] * 100
        picks = select_by_motion(motions, 50)
        in_moving_half = sum(1 for p in picks if p >= 100)
        assert in_moving_half > len(picks) * 0.8

    def test_monotonic_and_unique(self):
        picks = select_by_motion(list(np.random.default_rng(0).random(500)), 120)
        assert picks == sorted(set(picks))


class TestFrameQuality:
    def test_dhash_identical_images_match(self):
        img = (np.random.default_rng(1).random((64, 64)) * 255).astype(np.uint8)
        assert hamming(dhash(img), dhash(img)) == 0

    def test_dhash_different_images_differ(self):
        rng = np.random.default_rng(2)
        a = (rng.random((64, 64)) * 255).astype(np.uint8)
        b = (rng.random((64, 64)) * 255).astype(np.uint8)
        assert hamming(dhash(a), dhash(b)) > 4

    def test_metrics_flag_dark_frame(self):
        dark = np.zeros((100, 100), dtype=np.uint8)
        m = frame_metrics(dark)
        assert m["brightness"] < 30
        assert m["clipped_low"] > 0.9

    def test_metrics_flag_overexposed_frame(self):
        bright = np.full((100, 100), 255, dtype=np.uint8)
        m = frame_metrics(bright)
        assert m["brightness"] > 235
        assert m["clipped_high"] > 0.9

    def test_sharp_vs_flat(self):
        rng = np.random.default_rng(3)
        textured = (rng.random((100, 100)) * 255).astype(np.uint8)
        flat = np.full((100, 100), 128, dtype=np.uint8)
        assert frame_metrics(textured)["sharpness"] > frame_metrics(flat)["sharpness"]


class TestOptimize:
    def test_prune_removes_transparent_and_floaters(self, tmp_path):
        from plyfile import PlyData, PlyElement

        from wraparound.pipeline.optimize import prune_ply

        n = 100
        rng = np.random.default_rng(4)
        names = (["x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2", "opacity"]
                 + [f"scale_{i}" for i in range(3)] + [f"rot_{i}" for i in range(4)])
        arr = np.zeros(n, dtype=[(name, "f4") for name in names])
        for axis in "xyz":
            arr[axis] = rng.normal(0, 1, n)
        arr["opacity"] = 5.0            # sigmoid ≈ 0.99 → visible
        arr["opacity"][:10] = -10.0     # sigmoid ≈ 0 → pruned
        arr["x"][10] = 1000.0           # extreme floater → pruned
        src, dst = tmp_path / "in.ply", tmp_path / "out.ply"
        PlyData([PlyElement.describe(arr, "vertex")]).write(str(src))

        stats = prune_ply(src, dst)
        assert stats["before"] == n
        assert stats["pruned"] >= 11
        assert stats["after"] == n - stats["pruned"]


class TestProjectStore:
    def test_create_load_duplicate_delete(self, tmp_path):
        from wraparound.projects import ProjectStore

        store = ProjectStore(root=tmp_path)
        meta = store.create("Test Scene")
        assert (tmp_path / meta.id / "frames").is_dir()
        assert store.load(meta.id).name == "Test Scene"

        copy = store.duplicate(meta.id)
        assert copy.name == "Test Scene (copy)"
        assert len(store.list()) == 2

        store.delete(meta.id)
        assert len(store.list()) == 1

    def test_rejects_path_traversal(self, tmp_path):
        from wraparound.projects import ProjectError, ProjectStore

        store = ProjectStore(root=tmp_path)
        with pytest.raises(ProjectError):
            store.path("../evil")
