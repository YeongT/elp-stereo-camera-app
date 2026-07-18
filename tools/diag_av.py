"""Capture raw MJPEG packets via ffmpeg/dshow (PyAV), bypassing OpenCV entirely.

Checks whether the camera itself delivers complete JPEG payloads.

Usage: uv run python tools/diag_av.py [width height fps]
"""

import sys

import av

WIDTH = sys.argv[1] if len(sys.argv) > 3 else "3200"
HEIGHT = sys.argv[2] if len(sys.argv) > 3 else "1200"
FPS = sys.argv[3] if len(sys.argv) > 3 else "30"

DEVICE = "video=3D USB Camera"


def main() -> None:
    options = {
        "video_size": f"{WIDTH}x{HEIGHT}",
        "framerate": FPS,
        "vcodec": "mjpeg",
        "rtbufsize": "512M",
    }
    print(f"opening dshow {DEVICE} @ {WIDTH}x{HEIGHT} fps {FPS}", flush=True)
    container = av.open(DEVICE, format="dshow", options=options)
    stream = container.streams.video[0]
    print(f"stream: {stream.codec_context.name} {stream.width}x{stream.height}", flush=True)

    count = 0
    for packet in container.demux(stream):
        if packet.size == 0:
            continue
        data = bytes(packet)
        soi = data[:2] == b"\xff\xd8"
        eoi = data[-2:] == b"\xff\xd9"
        decoded_h = None
        try:
            frames = packet.decode()
            if frames:
                decoded_h = frames[0].height
        except Exception as exc:  # noqa: BLE001 — diagnostic, want the message
            decoded_h = f"decode-error {type(exc).__name__}"
        print(
            f"packet {count}: {packet.size / 1024:.0f}KB soi={soi} eoi={eoi} decoded_h={decoded_h}",
            flush=True,
        )
        count += 1
        if count >= 8:
            break
    container.close()


if __name__ == "__main__":
    main()
