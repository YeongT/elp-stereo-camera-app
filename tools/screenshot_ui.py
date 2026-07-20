"""Render the UI offscreen with a synthetic stereo frame and save screenshots.

Usage: uv run python tools/screenshot_ui.py [output_dir]
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from elp_console.styles import QSS, dark_palette
from elp_console.window import MainWindow
from elp_console.paths import UI_ARTIFACTS_DIR


def make_synthetic_sbs(width: int = 1560, height: int = 585) -> np.ndarray:
    """Fake stereo scene: gradient sky, ground plane, circles offset per eye."""
    half = width // 2
    frame = np.zeros((height, width, 3), dtype=np.uint8)

    sky = np.linspace(60, 160, height, dtype=np.uint8)[:, None]
    for eye, x0 in enumerate((0, half)):
        view = frame[:, x0 : x0 + half]
        view[:, :, 0] = sky + (20 if eye == 0 else 0)
        view[:, :, 1] = sky // 2 + 40
        view[:, :, 2] = sky // 3 + (0 if eye == 0 else 30)

        horizon = int(height * 0.62)
        view[horizon:, :] = (38, 46, 58)

        import cv2

        disparity = 18 if eye == 0 else -18
        cx = half // 2 + disparity
        cv2.circle(view, (cx, int(height * 0.45)), 70, (90, 170, 250), -1)
        cv2.circle(view, (cx, int(height * 0.45)), 70, (30, 60, 110), 4)
        cv2.rectangle(
            view,
            (cx - 190, horizon - 90),
            (cx - 110, horizon),
            (80, 200, 160),
            -1,
        )
        for gx in range(0, half, 60):
            cv2.line(view, (gx, horizon), (half // 2, height), (55, 66, 82), 1)

    return frame


def grab(window: MainWindow, app: QApplication, path: Path) -> None:
    for _ in range(4):
        app.processEvents()
    window.grab().save(str(path))
    print(f"saved {path}", flush=True)


def make_synthetic_calibration(eye_w: int, eye_h: int):
    """Ideal stereo geometry scaled to the synthetic frame — for sub-tab shots."""
    import cv2

    from elp_console.calibration import BoardSpec, calibrate_stereo

    board = BoardSpec(9, 6, 25.0)
    f = 858.0 * eye_w / 1600.0
    k = np.array([[f, 0, eye_w / 2], [0, f, eye_h / 2], [0, 0, 1.0]])
    t_lr = np.array([-60.85, 0.0, 0.0])
    poses = [
        (0.0, 0.0, 0.0, -100.0, -60.0, 500.0),
        (0.2, 0.0, 0.0, -100.0, -80.0, 550.0),
        (-0.2, 0.0, 0.0, -100.0, -40.0, 520.0),
        (0.0, 0.25, 0.0, -140.0, -60.0, 560.0),
        (0.0, -0.25, 0.0, -60.0, -60.0, 540.0),
        (0.15, 0.15, 0.1, -120.0, -70.0, 600.0),
        (-0.15, 0.2, -0.1, -80.0, -50.0, 480.0),
    ]
    obj = board.object_points()
    pairs = []
    for rx, ry, rz, tx, ty, tz in poses:
        rvec = np.array([rx, ry, rz])
        tvec = np.array([tx, ty, tz])
        left, _ = cv2.projectPoints(obj, rvec, tvec, k, None)
        right, _ = cv2.projectPoints(obj, rvec, tvec + t_lr, k, None)
        pairs.append((left.reshape(-1, 2).astype(np.float32), right.reshape(-1, 2).astype(np.float32)))
    return calibrate_stereo(board, (eye_w, eye_h), pairs)


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else UI_ARTIFACTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    app.setStyleSheet(QSS)

    window = MainWindow()
    window.resize(1500, 960)
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.show()

    grab(window, app, out_dir / "ui_idle.png")

    window._on_opened({"strategy": "MSMF size-first", "fourcc": "MJPG", "width": 3200, "height": 1200, "fps": 60.0})
    window.header.start_button.setEnabled(False)
    window.header.stop_button.setEnabled(True)
    frame = make_synthetic_sbs()
    base_stats = {"fps": 14.8, "mean": float(frame.mean()), "width": 3200, "height": 1200, "fourcc": "MJPG"}
    window._on_frame(frame, base_stats)
    window._append_log("MSMF size-first: connected — 3200x1200 fourcc MJPG requested fps 60 mean 118.1")
    grab(window, app, out_dir / "ui_streaming.png")

    from elp_console.frames import compose_view, exposure_overlay

    display, hist, clip_low, clip_high = exposure_overlay(frame)
    window._on_frame(display, {**base_stats, "hist": hist, "clip": (clip_low, clip_high)})
    grab(window, app, out_dir / "ui_exposure.png")

    ana = compose_view(frame, "anaglyph")
    window._on_frame(ana, {**base_stats, "view_mode": "anaglyph"})
    grab(window, app, out_dir / "ui_anaglyph.png")

    window.panel.guide_button.setChecked(True)
    window._on_frame(frame, base_stats)
    grab(window, app, out_dir / "ui_guides.png")
    window.panel.guide_button.setChecked(False)

    import time

    import cv2

    from elp_console.calibration import BoardSpec, render_board

    window.header.nav.setCurrentIndex(1)  # Calibration
    board_img = render_board(BoardSpec(), square_px=40, margin=60)
    eye = cv2.cvtColor(cv2.resize(board_img, (800, 600), interpolation=cv2.INTER_AREA), cv2.COLOR_GRAY2BGR)
    sbs_board = cv2.hconcat([eye, eye])
    window.calibration_tab.set_streaming(True)
    window.calibration_tab.on_preview_frame(sbs_board)
    window.calibration_tab.on_frame(sbs_board)
    for _ in range(60):  # detection runs in a helper thread — pump until the pair lands
        app.processEvents()
        if window.calibration_tab.pair_list.count():
            break
        time.sleep(0.05)
    grab(window, app, out_dir / "ui_calibration.png")

    # 정렬 검증·뎁스 서브탭 — 합성 캘리브레이션 + 합성 스테레오 프레임
    calib = make_synthetic_calibration(frame.shape[1] // 2, frame.shape[0])
    window.calibration_tab.set_calibration(calib)
    window.calibration_tab.sub_tabs.setCurrentWidget(window.calibration_tab.verify)
    window.calibration_tab.on_preview_frame(frame)
    grab(window, app, out_dir / "ui_verify.png")

    window.calibration_tab.sub_tabs.setCurrentWidget(window.calibration_tab.depth)
    window.calibration_tab.on_preview_frame(frame)
    for _ in range(100):  # SGBM runs in a helper thread — pump until the map lands
        app.processEvents()
        if window.calibration_tab.depth.view._pixmap is not None:
            break
        time.sleep(0.05)
    grab(window, app, out_dir / "ui_depth.png")

    # Narrow reference panel: the same rectified pair must switch to a
    # vertical LEFT / RIGHT arrangement so each eye remains inspectable.
    window.calibration_tab.depth.preview_splitter.setSizes([1050, 340])
    window.calibration_tab.depth._render_source_reference()  # noqa: SLF001 — screenshot state contract
    grab(window, app, out_dir / "ui_depth_narrow_reference.png")

    window.header.nav.setCurrentIndex(2)  # Library
    grab(window, app, out_dir / "ui_library.png")
    window.header.nav.setCurrentIndex(0)  # Live

    from elp_console.profile_dialog import ProfileDialog

    dialog = ProfileDialog(window._profiles)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    dialog.show()
    for _ in range(4):
        app.processEvents()
    dialog.grab().save(str(out_dir / "ui_profiles.png"))
    print(f"saved {out_dir / 'ui_profiles.png'}", flush=True)
    dialog.close()

    window._on_failed("Could not open 3200x1200 stream on device 0. Try a different resolution or backend.")
    grab(window, app, out_dir / "ui_error.png")

    print("done", flush=True)


if __name__ == "__main__":
    main()
