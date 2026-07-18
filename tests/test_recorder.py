"""Recorder tests: segmenting, split sessions, readback."""

import cv2
import numpy as np

from elp_console.recorder import RecordingSession, VideoRecorder


def frame_of(width, height, value=90):
    return np.full((height, width, 3), value, np.uint8)


class TestVideoRecorder:
    def test_segments_on_size_change(self, tmp_path):
        rec = VideoRecorder(tmp_path, fps=30)
        opened = [p for p in (rec.write(frame_of(320, 120)) for _ in range(3)) if p]
        assert len(opened) == 1
        assert rec.write(frame_of(240, 160)) is not None  # size change -> new segment
        rec.close()
        assert len(list(tmp_path.glob("*.mp4"))) == 2

    def test_readback(self, tmp_path):
        rec = VideoRecorder(tmp_path, fps=30)
        for _ in range(10):
            rec.write(frame_of(320, 120))
        path = rec.close()
        cap = cv2.VideoCapture(str(path))
        assert cap.isOpened()
        count = 0
        while cap.read()[0]:
            count += 1
        cap.release()
        assert count == 10


class TestRecordingSession:
    def test_split_creates_left_right_files(self, tmp_path):
        session = RecordingSession(tmp_path, fps=30, split=True)
        for _ in range(5):
            session.write(frame_of(320, 120))
        paths = session.close()
        names = sorted(p.name for p in paths)
        assert any("_left" in n for n in names)
        assert any("_right" in n for n in names)
        # each file holds one eye — half the SBS width
        cap = cv2.VideoCapture(str(paths[0]))
        assert int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) == 160
        cap.release()

    def test_single_mode_one_file(self, tmp_path):
        session = RecordingSession(tmp_path, fps=30, split=False)
        for _ in range(5):
            session.write(frame_of(320, 120))
        paths = session.close()
        assert len(paths) == 1
