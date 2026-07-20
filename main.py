"""Entry point for the stereo camera console."""

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from elp_console import __version__
from elp_console.styles import QSS, dark_palette
from elp_console.window import MainWindow

APP_NAME = "ELP Stereo Camera App"


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
    print(f"{APP_NAME} v{__version__} started in a separate process.", flush=True)


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


def entrypoint(argv: list[str] | None = None) -> None:
    """Run the foreground GUI only when explicitly requested.

    Normal source launches return the calling shell immediately, while
    ``--foreground`` remains available for debugging and ``--child`` is used
    internally by the detached launcher.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if "--version" in args:
        print(f"{APP_NAME} v{__version__}")
    elif "--child" in args or "--foreground" in args:
        main()
    else:
        launch_detached()


if __name__ == "__main__":
    entrypoint()
