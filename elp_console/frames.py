"""Pure frame operations: SBS split, corruption detection, view transforms."""

import cv2
import numpy as np


def split_sbs(frame):
    """Split a side-by-side stereo frame into (left, right) views."""
    half = frame.shape[1] // 2
    return frame[:, :half], frame[:, half:]


ROTATE_CODES = {
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def apply_stereo_transform(frame, swap_lr: bool, rotation: int):
    """Swap and/or rotate each eye of a side-by-side frame.

    Rotation is applied per eye (rotating the whole composite would break the
    SBS layout). Returns the input unchanged when no transform is active."""
    rotation %= 360
    if not swap_lr and rotation == 0:
        return frame
    left, right = split_sbs(frame)
    if swap_lr:
        left, right = right, left
    code = ROTATE_CODES.get(rotation)
    if code is not None:
        left = cv2.rotate(left, code)
        right = cv2.rotate(right, code)
    return cv2.hconcat([left, right])


def compose_view(frame, mode: str):
    """Compose the display image for a view mode.

    'sbs' passes through; 'left'/'right' crop one eye; 'anaglyph' builds a
    red-cyan 3D image (left eye red channel, right eye green+blue)."""
    if mode == "sbs":
        return frame
    left, right = split_sbs(frame)
    # Column slices are non-contiguous views; downstream QImage wraps the raw
    # buffer, so single-eye crops must be materialized as contiguous copies.
    if mode == "left":
        return np.ascontiguousarray(left)
    if mode == "right":
        return np.ascontiguousarray(right)
    out = right.copy()
    out[:, :, 2] = left[:, :, 2]  # BGR: red from left eye
    return out


CLIP_HIGH = 250
CLIP_LOW = 5


def exposure_overlay(display):
    """Exposure check for a display frame.

    Returns (tinted copy, 64-bin luminance histogram normalized to its peak,
    crushed-shadow %, blown-highlight %). Clipped pixels are tinted solid so
    they stand out: highlights red, shadows blue."""
    gray = cv2.cvtColor(display, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([gray], [0], None, [64], [0, 256]).ravel()
    high = gray >= CLIP_HIGH
    low = gray <= CLIP_LOW
    out = display.copy()
    out[high] = (60, 60, 255)
    out[low] = (255, 80, 40)
    peak = hist.max()
    if peak > 0:
        hist = hist / peak
    return out, hist, float(low.mean() * 100), float(high.mean() * 100)


def frame_is_filled(frame) -> bool:
    """True if the frame contains decoder fill (uniform green/gray rows) from a
    truncated JPEG. Fill rows are one constant color, so every CHANNEL is flat;
    a whole-row std would miss colored fills (green fill has high cross-channel
    variance) — check per-channel std instead."""
    height = frame.shape[0]
    for frac in (0.35, 0.6, 0.85):
        row = frame[int(height * frac)]
        if (row.std(axis=0) < 2.0).all():
            return True
    return False


def fourcc_to_str(cap: cv2.VideoCapture) -> str:
    code = int(cap.get(cv2.CAP_PROP_FOURCC))
    text = "".join(chr((code >> 8 * i) & 0xFF) for i in range(4)).strip("\x00")
    return text if text.isprintable() and len(text) >= 3 else "RAW"


def fourcc_code(code: str) -> int:
    factory = getattr(cv2, "VideoWriter_fourcc", None) or cv2.VideoWriter.fourcc
    return factory(*code)
