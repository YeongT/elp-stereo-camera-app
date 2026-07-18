"""End-to-end selftest: run the real MainWindow against the real camera, hidden,
then capture what the window actually shows.

Usage: uv run python tools/selftest_live.py [seconds]
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from elp_console.styles import QSS, dark_palette
from elp_console.window import MainWindow
from elp_console.paths import UI_ARTIFACTS_DIR

DURATION_MS = int(float(sys.argv[1]) * 1000) if len(sys.argv) > 1 else 8000
OUT = UI_ARTIFACTS_DIR / "ui_live.png"


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    font = QFont()
    font.setFamilies(["Segoe UI", "Malgun Gothic"])
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(QSS)

    window = MainWindow()
    window.resize(1500, 960)
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.show()

    window._start_stream()

    def finish():
        OUT.parent.mkdir(exist_ok=True)
        window.grab().save(str(OUT))
        print(f"saved {OUT}", flush=True)
        print("log panel contents:", flush=True)
        print(window.log_panel.toPlainText(), flush=True)
        window.close()
        app.quit()

    QTimer.singleShot(DURATION_MS, finish)
    app.exec()


if __name__ == "__main__":
    main()
