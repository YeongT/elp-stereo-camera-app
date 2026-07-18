"""Calibration tab container: sub-tab structure and preview routing surface."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from elp_console.calibration_tab import CalibrationTab


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_calibration_tab_has_three_subtabs(qapp):
    tab = CalibrationTab()
    assert tab.sub_tabs.count() == 3
    assert [tab.sub_tabs.tabText(i) for i in range(3)] == ["수집·실행", "정렬 검증", "뎁스"]


def test_wants_preview_only_on_verify_and_depth_subtabs(qapp):
    tab = CalibrationTab()
    assert not tab.wants_preview()
    tab.sub_tabs.setCurrentIndex(1)
    assert tab.wants_preview()
    tab.sub_tabs.setCurrentIndex(2)
    assert tab.wants_preview()
    tab.sub_tabs.setCurrentIndex(0)
    assert not tab.wants_preview()


def test_container_keeps_capture_compat_surface(qapp):
    tab = CalibrationTab()
    for name in ("request_frame", "calibrated", "log", "status_label", "pair_list"):
        assert hasattr(tab, name), name
    tab.set_streaming(True)
    tab.set_streaming(False)
    tab.set_design_baseline(60.85)
    tab.set_calibration(None)  # no calibration loaded — must not crash
