"""FFmpeg(PyAV) capture path: validates each MJPEG packet and drops corrupt
frames instead of letting them decode into gray/green-filled images."""

import time

from .camera import EMIT_INTERVAL
from .frames import frame_is_filled

FFMPEG_PROBE_PACKETS = 60


def run_ffmpeg(worker) -> bool:
    """Returns True if the stream ran (even if it later failed), False if it
    could not be opened at all (caller may fall back to OpenCV)."""
    try:
        import av
    except ImportError:
        worker.log.emit("PyAV 미설치 — OpenCV 경로로 폴백")
        return False

    options = {
        "video_size": f"{worker._width}x{worker._height}",
        "framerate": str(worker._fps),
        "vcodec": "mjpeg",
        "rtbufsize": "256M",
    }
    worker.log.emit(f"FFmpeg DSHOW 시도 중... ({worker._width}x{worker._height}@{worker._fps})")
    container = None
    for attempt in range(2):
        try:
            container = av.open(f"video={worker._device_name}", format="dshow", options=options)
            break
        except Exception as exc:  # noqa: BLE001 — device may need settle time
            worker.log.emit(f"FFmpeg DSHOW 열기 실패 (시도 {attempt + 1}/2): {exc}")
            if attempt == 0 and not worker._stop_requested:
                time.sleep(2.0)
    if container is None:
        return False

    stream = container.streams.video[0]
    good = 0
    drops = 0
    emitted_open = False
    fps_ema = 0.0
    last_frame_time = time.perf_counter()
    last_emit_time = 0.0

    try:
        for packet in container.demux(stream):
            if worker._stop_requested:
                break
            if packet.size == 0:
                continue

            # ffmpeg decodes truncated JPEGs without error and fills the
            # missing area green — validate SOI/EOI markers on raw bytes
            # so only complete payloads reach the decoder.
            data = bytes(packet)
            complete = data[:2] == b"\xff\xd8" and data.rfind(b"\xff\xd9") >= len(data) - 4
            if not complete:
                drops += 1
                if not emitted_open and drops >= FFMPEG_PROBE_PACKETS:
                    worker.failed.emit("모든 프레임이 손상 상태입니다. USB 포트/케이블을 바꿔 보세요.")
                    return True
                continue

            try:
                frames = packet.decode()
            except Exception:  # noqa: BLE001 — corrupt despite markers, drop it
                drops += 1
                continue

            for av_frame in frames:
                frame = av_frame.to_ndarray(format="bgr24")
                if frame_is_filled(frame):
                    drops += 1
                    continue
                good += 1

                if not emitted_open:
                    emitted_open = True
                    worker.log.emit(
                        f"FFmpeg DSHOW: 연결됨 — {frame.shape[1]}x{frame.shape[0]} "
                        f"MJPG (손상 프레임 자동 드롭)"
                    )
                    worker.opened.emit(
                        {
                            "strategy": "FFmpeg DSHOW",
                            "fourcc": "MJPG",
                            "width": frame.shape[1],
                            "height": frame.shape[0],
                            "fps": float(worker._fps),
                        }
                    )

                now = time.perf_counter()
                dt = now - last_frame_time
                last_frame_time = now
                if dt > 0:
                    inst = 1.0 / dt
                    fps_ema = inst if fps_ema == 0 else fps_ema * 0.9 + inst * 0.1

                frame = worker._process(frame)

                if now - last_emit_time < EMIT_INTERVAL:
                    continue
                last_emit_time = now

                total = good + drops
                worker._emit_frame(frame, fps_ema, "MJPG", drops / total * 100 if total else 0.0)
    except Exception as exc:  # noqa: BLE001 — device unplugged mid-stream etc.
        if not worker._stop_requested:
            worker.failed.emit(f"FFmpeg 스트림 중단: {exc}")
    finally:
        container.close()

    if not emitted_open and not worker._stop_requested:
        worker.failed.emit("FFmpeg 경로에서 유효한 프레임을 받지 못했습니다.")
    return True
