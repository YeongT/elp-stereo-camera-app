"""Probe UVC devices for a working MJPG negotiation recipe.

Usage:
    uv run python tools/probe_camera.py            # enumerate + probe all devices
    uv run python tools/probe_camera.py --index 1  # probe one device only
"""

import argparse
import os
import sys
import time

os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")

import cv2


def fourcc_of(code: str) -> int:
    factory = getattr(cv2, "VideoWriter_fourcc", None) or cv2.VideoWriter.fourcc
    return factory(*code)


def fourcc_str(cap: cv2.VideoCapture) -> str:
    code = int(cap.get(cv2.CAP_PROP_FOURCC))
    return "".join(chr((code >> 8 * i) & 0xFF) for i in range(4)).strip("\x00")


def list_device_names() -> list[str]:
    try:
        from pygrabber.dshow_graph import FilterGraph

        return FilterGraph().get_input_devices()
    except Exception as exc:  # noqa: BLE001 — enumeration is best-effort
        print(f"pygrabber enumeration failed: {exc}", flush=True)
        return []


STRATEGIES = [
    ("DSHOW fourcc-first", cv2.CAP_DSHOW, ["fourcc", "size", "fps"]),
    ("DSHOW size-first", cv2.CAP_DSHOW, ["size", "fps", "fourcc"]),
    ("MSMF fourcc-first", cv2.CAP_MSMF, ["fourcc", "size", "fps"]),
    ("MSMF size-first", cv2.CAP_MSMF, ["size", "fps", "fourcc"]),
]


def apply_steps(cap: cv2.VideoCapture, steps: list[str], width: int, height: int, fps: int) -> None:
    for step in steps:
        if step == "fourcc":
            cap.set(cv2.CAP_PROP_FOURCC, fourcc_of("MJPG"))
        elif step == "size":
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        elif step == "fps":
            cap.set(cv2.CAP_PROP_FPS, fps)


def probe_strategy(index: int, backend: int, steps: list[str], width: int, height: int, fps: int) -> dict:
    t0 = time.perf_counter()
    cap = cv2.VideoCapture(index, backend)
    result = {"opened": cap.isOpened()}
    if not cap.isOpened():
        cap.release()
        return result

    apply_steps(cap, steps, width, height, fps)

    result["fourcc"] = fourcc_str(cap)
    result["actual_w"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    result["actual_h"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    result["actual_fps"] = cap.get(cv2.CAP_PROP_FPS)

    means = []
    grab_t0 = time.perf_counter()
    for _ in range(5):
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        means.append(float(frame.mean()))
    result["frames_read"] = len(means)
    result["last_mean"] = means[-1] if means else None
    result["grab_seconds"] = round(time.perf_counter() - grab_t0, 2)
    result["total_seconds"] = round(time.perf_counter() - t0, 2)
    cap.release()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=int, default=None)
    parser.add_argument("--width", type=int, default=3200)
    parser.add_argument("--height", type=int, default=1200)
    parser.add_argument("--fps", type=int, default=60)
    args = parser.parse_args()

    names = list_device_names()
    print(f"devices ({len(names)}):", flush=True)
    for i, name in enumerate(names):
        print(f"  [{i}] {name}", flush=True)

    indices = [args.index] if args.index is not None else list(range(max(len(names), 1)))

    for idx in indices:
        label = names[idx] if idx < len(names) else "?"
        print(f"\n=== device {idx} ({label}) @ {args.width}x{args.height} fps {args.fps} ===", flush=True)
        for strat_name, backend, steps in STRATEGIES:
            result = probe_strategy(idx, backend, steps, args.width, args.height, args.fps)
            print(f"  {strat_name}: {result}", flush=True)

    sys.exit(0)


if __name__ == "__main__":
    main()
