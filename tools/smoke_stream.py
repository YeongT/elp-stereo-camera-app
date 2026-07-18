"""Headless smoke test: run CaptureWorker against the real camera for a few seconds.

Usage: uv run python tools/smoke_stream.py [seconds]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QCoreApplication, QTimer

from elp_console.camera import CaptureWorker
from elp_console.devices import list_devices

DURATION_MS = int(float(sys.argv[1]) * 1000) if len(sys.argv) > 1 else 5000


def main() -> None:
    app = QCoreApplication(sys.argv)
    device_name = list_devices()[0]
    print(f"[device] {device_name}", flush=True)
    worker = CaptureWorker(
        device_name=device_name, index=0, width=3200, height=1200, fps=60, backend_mode="Auto"
    )

    frames = {"count": 0, "last_stats": None}

    worker.log.connect(lambda msg: print(f"[log] {msg}", flush=True))
    worker.opened.connect(lambda info: print(f"[opened] {info}", flush=True))
    worker.failed.connect(lambda msg: print(f"[failed] {msg}", flush=True))

    def on_frame(frame, stats):
        frames["count"] += 1
        frames["last_stats"] = stats

    worker.frame_ready.connect(on_frame)

    def finish():
        worker.stop()
        worker.wait(3000)
        print(f"[result] frames_emitted={frames['count']} last_stats={frames['last_stats']}", flush=True)
        app.quit()

    QTimer.singleShot(DURATION_MS, finish)
    worker.start()
    app.exec()


if __name__ == "__main__":
    main()
