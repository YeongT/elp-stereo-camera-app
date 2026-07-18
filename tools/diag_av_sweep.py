"""Measure complete-frame ratio per mode via ffmpeg/dshow.

A frame counts as complete only if: SOI+EOI markers present, decode succeeds,
and sampled rows contain real variance (no green/gray fill).

Usage: uv run python tools/diag_av_sweep.py
"""

import numpy as np
import av

DEVICE = "video=3D USB Camera"
PACKETS_PER_MODE = 40

MODES = [
    ("3200x1200", "30"),
    ("3200x1200", "15"),
    ("2560x720", "30"),
    ("1600x600", "30"),
    ("1280x480", "30"),
    ("640x240", "30"),
]


def frame_is_filled(img: np.ndarray) -> bool:
    h = img.shape[0]
    for frac in (0.35, 0.6, 0.85):
        row = img[int(h * frac)]
        if row.std() < 2.0:
            return True
    return False


def probe(size: str, fps: str) -> None:
    options = {"video_size": size, "framerate": fps, "vcodec": "mjpeg", "rtbufsize": "256M"}
    try:
        container = av.open(DEVICE, format="dshow", options=options)
    except Exception as exc:  # noqa: BLE001
        print(f"{size}@{fps}: open fail — {exc}", flush=True)
        return

    stream = container.streams.video[0]
    total = complete = marker_ok = 0
    sizes = []
    try:
        for packet in container.demux(stream):
            if packet.size == 0:
                continue
            total += 1
            data = bytes(packet)
            sizes.append(len(data))
            markers = data[:2] == b"\xff\xd8" and data.rfind(b"\xff\xd9") >= len(data) - 4
            if markers:
                marker_ok += 1
                try:
                    frames = packet.decode()
                    if frames:
                        img = frames[0].to_ndarray(format="bgr24")
                        if not frame_is_filled(img):
                            complete += 1
                except Exception:  # noqa: BLE001
                    pass
            if total >= PACKETS_PER_MODE:
                break
    finally:
        container.close()

    avg_kb = sum(sizes) / len(sizes) / 1024 if sizes else 0
    print(
        f"{size}@{fps}: packets {total} marker_ok {marker_ok} complete {complete} "
        f"({complete / total * 100 if total else 0:.0f}%) avg {avg_kb:.0f}KB",
        flush=True,
    )


def main() -> None:
    for size, fps in MODES:
        probe(size, fps)


if __name__ == "__main__":
    main()
