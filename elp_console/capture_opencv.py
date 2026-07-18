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


def _try_strategy(worker, strategy: Strategy):
    worker.log.emit(f"{strategy.name} 시도 중...")
    cap = cv2.VideoCapture(worker._index, strategy.backend)
    if not cap.isOpened():
        worker.log.emit(f"{strategy.name}: 장치 열기 실패")
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
        worker.log.emit(f"{strategy.name}: 프레임 없음 또는 검은 화면 — 다음 전략으로")
        cap.release()
        return None

    info = {
        "strategy": strategy.name,
        "fourcc": fourcc_to_str(cap),
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fps": cap.get(cv2.CAP_PROP_FPS),
    }
    worker.log.emit(
        f"{strategy.name}: 연결됨 — {info['width']}x{info['height']} "
        f"fourcc {info['fourcc']} (주의: 손상 프레임이 회색으로 표시될 수 있음)"
    )
    return cap, info


def run_opencv(worker) -> None:
    result = None
    for strategy in OPENCV_STRATEGIES[worker._backend_mode if worker._backend_mode in OPENCV_STRATEGIES else "Auto"]:
        if worker._stop_requested:
            return
        result = _try_strategy(worker, strategy)
        if result is not None:
            break

    if result is None:
        if not worker._stop_requested:
            worker.failed.emit(
                f"장치 {worker._index}에서 {worker._width}x{worker._height} 스트림을 열지 못했습니다. "
                "다른 해상도나 백엔드로 다시 시도하세요."
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
                worker.failed.emit("프레임 수신이 반복 실패했습니다. 장치 연결을 확인하세요.")
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
