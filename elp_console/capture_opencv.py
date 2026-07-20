"""OpenCV fallback capture path.

OpenCV silently decodes truncated MJPEG frames into gray/green-filled images,
so this path is only tried when FFmpeg(PyAV) cannot open the device.
OpenCV DSHOW must set size BEFORE fourcc or the camera falls back to YUY2."""

import time
from dataclasses import dataclass

# camera.py sets OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS before cv2 loads —
# import it first so a direct import of this module keeps that guarantee.
from .camera import EMIT_INTERVAL

import cv2

from .frames import fourcc_code, fourcc_to_str

WARMUP_READS = 5
DEAD_MEAN_THRESHOLD = 0.5
MAX_CONSECUTIVE_FAILS = 30


@dataclass(frozen=True)
class Strategy:
    name: str
    backend: int
    steps: tuple[str, ...]


OPENCV_STRATEGIES = {
    "Auto": (
        Strategy("MSMF size-first", cv2.CAP_MSMF, ("size", "fps", "fourcc")),
        Strategy("DSHOW size-first", cv2.CAP_DSHOW, ("size", "fps", "fourcc")),
    ),
    "MSMF": (
        Strategy("MSMF size-first", cv2.CAP_MSMF, ("size", "fps", "fourcc")),
        Strategy("MSMF fourcc-first", cv2.CAP_MSMF, ("fourcc", "size", "fps")),
    ),
    "DSHOW": (
        Strategy("DSHOW size-first", cv2.CAP_DSHOW, ("size", "fps", "fourcc")),
        Strategy("DSHOW fourcc-first", cv2.CAP_DSHOW, ("fourcc", "size", "fps")),
    ),
}


def _apply_steps(worker, cap: cv2.VideoCapture, steps: tuple[str, ...]) -> None:
    for step in steps:
        if step == "fourcc":
            cap.set(cv2.CAP_PROP_FOURCC, fourcc_code("MJPG"))
        elif step == "size":
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, worker._width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, worker._height)
        elif step == "fps":
            cap.set(cv2.CAP_PROP_FPS, worker._fps)


def candidate_indices(selected_index: int, indices: tuple[int, ...]) -> tuple[int, ...]:
    """Return each candidate once, preserving the selected item as first try."""
    return tuple(dict.fromkeys((selected_index, *indices)))


def _try_strategy(worker, strategy: Strategy, capture_index: int):
    worker.log.emit(f"Trying {strategy.name} on OpenCV index {capture_index}...")
    cap = cv2.VideoCapture(capture_index, strategy.backend)
    if not cap.isOpened():
        worker.log.emit(f"{strategy.name}: device open failed")
        cap.release()
        return None

    _apply_steps(worker, cap, strategy.steps)

    last_mean = 0.0
    for _ in range(WARMUP_READS):
        if worker._stop_requested:
            cap.release()
            return None
        ok, frame = cap.read()
        if ok and frame is not None:
            last_mean = float(frame.mean())
            if last_mean > DEAD_MEAN_THRESHOLD:
                break

    if last_mean <= DEAD_MEAN_THRESHOLD:
        worker.log.emit(f"{strategy.name}: no frames or black screen — trying next strategy")
        cap.release()
        return None

    info = {
        "strategy": strategy.name,
        "capture_index": capture_index,
        "fourcc": fourcc_to_str(cap),
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fps": cap.get(cv2.CAP_PROP_FPS),
    }
    if (info["width"], info["height"]) != (worker._width, worker._height):
        worker.log.emit(
            f"{strategy.name} index {capture_index}: negotiated {info['width']}x{info['height']}, "
            f"expected {worker._width}x{worker._height} — rejecting a different camera"
        )
        cap.release()
        return None
    worker.log.emit(
        f"{strategy.name} index {capture_index}: connected — {info['width']}x{info['height']} "
        f"fourcc {info['fourcc']} (note: corrupt frames may appear gray)"
    )
    return cap, info


def run_opencv(worker) -> None:
    result = None
    indices = candidate_indices(worker._index, worker._opencv_indices)
    for strategy in OPENCV_STRATEGIES[worker._backend_mode if worker._backend_mode in OPENCV_STRATEGIES else "Auto"]:
        if worker._stop_requested:
            return
        for capture_index in indices:
            if worker._stop_requested:
                return
            result = _try_strategy(worker, strategy, capture_index)
            if result is not None:
                break
        if result is not None:
            break

    if result is None:
        if not worker._stop_requested:
            worker.failed.emit(
                f"Could not open {worker._width}x{worker._height} stream for the selected device. "
                "No OpenCV device matched the requested resolution; try FFmpeg or another mode."
            )
        return

    cap, info = result
    worker.opened.emit(info)

    fps_ema = 0.0
    last_frame_time = time.perf_counter()
    last_emit_time = 0.0
    consecutive_fails = 0

    while not worker._stop_requested:
        ok, frame = cap.read()
        now = time.perf_counter()
        if not ok or frame is None:
            consecutive_fails += 1
            if consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                worker.failed.emit("Frame reception failed repeatedly. Check the device connection.")
                break
            time.sleep(0.01)
            continue
        consecutive_fails = 0

        dt = now - last_frame_time
        last_frame_time = now
        if dt > 0:
            inst = 1.0 / dt
            fps_ema = inst if fps_ema == 0 else fps_ema * 0.9 + inst * 0.1

        frame = worker._process(frame)

        if now - last_emit_time < EMIT_INTERVAL:
            continue
        last_emit_time = now

        worker._emit_frame(frame, fps_ema, info["fourcc"], None)

    cap.release()
