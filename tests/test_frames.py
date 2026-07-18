"""Frame operation tests: transforms, view composition, exposure analysis."""

import numpy as np
import pytest

from elp_console.frames import (
    apply_stereo_transform,
    compose_view,
    exposure_overlay,
    frame_is_filled,
    split_sbs,
)


def make_sbs(width=320, height=120):
    """Left eye solid 40s, right eye solid 200s — trivially distinguishable."""
    frame = np.zeros((height, width, 3), np.uint8)
    frame[:, : width // 2] = 40
    frame[:, width // 2 :] = 200
    return frame


class TestApplyStereoTransform:
    def test_identity_returns_input(self):
        frame = make_sbs()
        assert apply_stereo_transform(frame, False, 0) is frame

    def test_360_wraps_to_identity(self):
        frame = make_sbs()
        assert apply_stereo_transform(frame, False, 360) is frame

    def test_swap_exchanges_eyes(self):
        out = apply_stereo_transform(make_sbs(), True, 0)
        left, right = split_sbs(out)
        assert left.mean() == 200
        assert right.mean() == 40

    def test_rotation_90_swaps_eye_dimensions(self):
        out = apply_stereo_transform(make_sbs(320, 120), False, 90)
        # each eye 160x120 -> rotated 120x160, recombined 240x160
        assert out.shape == (160, 240, 3)

    def test_input_not_mutated(self):
        frame = make_sbs()
        original = frame.copy()
        apply_stereo_transform(frame, True, 180)
        np.testing.assert_array_equal(frame, original)


class TestComposeView:
    def test_sbs_passthrough(self):
        frame = make_sbs()
        assert compose_view(frame, "sbs") is frame

    def test_left_right_crop(self):
        frame = make_sbs()
        assert compose_view(frame, "left").mean() == 40
        assert compose_view(frame, "right").mean() == 200

    def test_crops_are_contiguous(self):
        # QImage wraps the raw buffer — non-contiguous views must not leak out.
        frame = make_sbs()
        for mode in ("left", "right", "anaglyph"):
            assert compose_view(frame, mode).flags["C_CONTIGUOUS"]

    def test_anaglyph_channels(self):
        out = compose_view(make_sbs(), "anaglyph")
        assert out.shape == (120, 160, 3)
        assert (out[:, :, 2] == 40).all()  # red from left eye
        assert (out[:, :, 0] == 200).all()  # blue from right eye
        assert (out[:, :, 1] == 200).all()  # green from right eye


class TestExposureOverlay:
    def test_clip_percentages(self):
        frame = np.full((100, 100, 3), 128, np.uint8)
        frame[:10] = 255  # 10% blown
        frame[90:] = 0  # 10% crushed
        _, hist, clip_low, clip_high = exposure_overlay(frame)
        assert clip_low == pytest.approx(10.0, abs=0.5)
        assert clip_high == pytest.approx(10.0, abs=0.5)
        assert len(hist) == 64
        assert hist.max() == pytest.approx(1.0)

    def test_clipped_pixels_tinted(self):
        frame = np.full((10, 10, 3), 255, np.uint8)
        out, _, _, _ = exposure_overlay(frame)
        assert tuple(out[0, 0]) == (60, 60, 255)  # highlight tint (BGR red)

    def test_input_not_mutated(self):
        frame = np.full((10, 10, 3), 255, np.uint8)
        exposure_overlay(frame)
        assert (frame == 255).all()


class TestFrameIsFilled:
    def test_uniform_fill_detected(self):
        assert frame_is_filled(np.full((100, 200, 3), 128, np.uint8))

    def test_noisy_frame_passes(self):
        frame = np.random.default_rng(1).integers(0, 255, (100, 200, 3), np.uint8)
        assert not frame_is_filled(frame)
