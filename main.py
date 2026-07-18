"""Entry point for the stereo camera console."""

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from elp_console.styles import QSS, dark_palette
from elp_console.window import MainWindow


def launch_detached() -> None:
    """Start the GUI as an independent Python process and return immediately."""
    script = Path(__file__).resolve()
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpreter = pythonw if os.name == "nt" and pythonw.is_file() else Path(sys.executable)
    kwargs = {"cwd": str(script.parent), "close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    subprocess.Popen([str(interpreter), str(script), "--child"], **kwargs)


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
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    if "--detach" in sys.argv:
        launch_detached()
    else:
        if "--child" in sys.argv:
            sys.argv.remove("--child")
        main()
