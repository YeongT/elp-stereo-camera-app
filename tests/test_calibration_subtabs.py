"""Calibration tab container: sub-tab structure and preview routing surface."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from elp_console.calibration import BoardSpec
from elp_console.calibration_tab import CalibrationTab
import elp_console.calibration_tab as calibration_tab_module


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_calibration_tab_has_three_subtabs(qapp):
    tab = CalibrationTab()
    assert tab.sub_tabs.count() == 3
    assert [tab.sub_tabs.tabText(i) for i in range(3)] == ["Capture", "Align", "Depth"]


def test_every_calibration_subtab_receives_continuous_preview(qapp):
    tab = CalibrationTab()
    assert tab.wants_preview()
    tab.sub_tabs.setCurrentIndex(1)
    assert tab.wants_preview()
    tab.sub_tabs.setCurrentIndex(2)
    assert tab.wants_preview()
    tab.sub_tabs.setCurrentIndex(0)
    assert tab.wants_preview()


def test_depth_preview_shows_rectified_source_and_depth_surfaces(qapp):
    tab = CalibrationTab()
    assert tab.depth.source_view is not None
    assert "Rectified SBS" in tab.depth.source_caption.text()
    assert tab.depth.preview_splitter.count() == 2
    assert tab.depth.view.minimumWidth() >= 460
    assert tab.depth.profile_combo.count() >= 5


def test_depth_reference_stacks_eyes_in_a_narrow_panel(qapp):
    tab = CalibrationTab()
    depth = tab.depth
    depth.source_view.resize(360, 500)
    depth._last_rectified = np.zeros((24, 48, 3), dtype=np.uint8)  # noqa: SLF001 — layout contract
    depth._render_source_reference()  # noqa: SLF001 — layout contract

    assert depth.source_view._view_mode == "sbs_vertical"  # noqa: SLF001 — render contract
    assert "above" in depth.source_caption.text()


def test_capture_subtab_renders_preview_without_triggering_detection(qapp):
    tab = CalibrationTab()
    tab.on_preview_frame(np.zeros((24, 48, 3), dtype=np.uint8))
    assert tab.capture.preview._pixmap is not None  # noqa: SLF001 — render contract


def test_auto_capture_scans_immediately_then_waits_after_a_capture(qapp):
    tab = CalibrationTab()
    tab.set_streaming(True)
    tab.capture.auto_button.setChecked(True)
    assert tab.capture._auto_ready  # noqa: SLF001 — capture lifecycle contract
    assert not tab.capture._auto_timer.isActive()  # noqa: SLF001 — timer starts after capture
    assert "Auto Capture on" in tab.status_label.text()

    frame = np.zeros((24, 48, 3), dtype=np.uint8)
    corners = np.zeros((9 * 6, 2), dtype=np.float32)
    tab.capture._on_detected(  # noqa: SLF001 — result lifecycle
        frame,
        (corners, corners),
        BoardSpec(),
        (Path("left.png"), Path("right.png")),
        "",
    )
    assert not tab.capture._auto_ready  # noqa: SLF001 — capture lifecycle contract
    assert tab.capture._auto_timer.isActive()  # noqa: SLF001 — cooldown lifecycle contract

    tab.capture._on_auto_interval_elapsed()  # noqa: SLF001 — cooldown lifecycle contract
    assert tab.capture._auto_ready  # noqa: SLF001 — capture lifecycle contract
    tab.capture.auto_button.setChecked(False)
    assert not tab.capture._auto_timer.isActive()  # noqa: SLF001 — timer lifecycle contract


def test_calibration_pairs_are_saved_as_separate_left_and_right_images(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(calibration_tab_module, "CALIBRATION_PAIRS_DIR", tmp_path)
    tab = CalibrationTab()
    frame = np.zeros((24, 48, 3), dtype=np.uint8)
    left_path, right_path = tab.capture._save_pair_images(frame, 1)  # noqa: SLF001 — persistence contract
    assert left_path.is_file()
    assert right_path.is_file()
    assert cv2.imread(str(left_path)).shape[:2] == (24, 24)
    assert cv2.imread(str(right_path)).shape[:2] == (24, 24)


def test_container_keeps_capture_compat_surface(qapp):
    tab = CalibrationTab()
    for name in ("request_frame", "calibrated", "log", "status_label", "pair_list"):
        assert hasattr(tab, name), name
    tab.set_streaming(True)
    tab.set_streaming(False)
    tab.set_design_baseline(60.85)
    tab.set_calibration(None)  # no calibration loaded — must not crash
