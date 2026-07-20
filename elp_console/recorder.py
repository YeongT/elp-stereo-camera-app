"""MP4 recording with automatic segmentation when the frame size changes
(rotation 90°/270° mid-recording changes dimensions; VideoWriter cannot)."""

import time
from pathlib import Path

import cv2

from .frames import split_sbs


class VideoRecorder:
    def __init__(self, directory: str, fps: float, suffix: str = ""):
        self.directory = Path(directory)
        self._fps = max(1.0, float(fps))
        self._suffix = suffix
        self._writer: cv2.VideoWriter | None = None
        self._size: tuple[int, int] | None = None
        self.path: Path | None = None

    def write(self, frame) -> Path | None:
        """Write one BGR frame. Returns the file path when a new segment opens."""
        size = (frame.shape[1], frame.shape[0])
        opened = None
        if self._writer is None or size != self._size:
            self.close()
            self.directory.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            stem = f"{stamp}_{self._suffix}" if self._suffix else stamp
            path = self.directory / f"{stem}.mp4"
            n = 2
            while path.exists():  # same-second segment switch must not overwrite
                path = self.directory / f"{stem}_{n}.mp4"
                n += 1
            self.path = path
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self._writer = cv2.VideoWriter(str(self.path), fourcc, self._fps, size)
            if not self._writer.isOpened():
                self._writer = None
                raise RuntimeError(f"VideoWriter open failed: {self.path}")
            self._size = size
            opened = self.path
        self._writer.write(frame)
        return opened

    def close(self) -> Path | None:
        """Release the writer. Returns the finished file path, if any."""
        if self._writer is None:
            return None
        self._writer.release()
        self._writer = None
        self._size = None
        return self.path


class RecordingSession:
    """One recording run: a single composite MP4, or a left/right MP4 pair."""

    def __init__(self, directory: str, fps: float, split: bool):
        self.directory = Path(directory)
        self.split = split
        if split:
            self._recorders = {
                "left": VideoRecorder(directory, fps, "left"),
                "right": VideoRecorder(directory, fps, "right"),
            }
        else:
            self._recorders = {"": VideoRecorder(directory, fps)}

    def write(self, frame) -> list[Path]:
        """Write one SBS frame. Returns paths of newly opened segments."""
        if self.split:
            left, right = split_sbs(frame)
            parts = {"left": left, "right": right}
        else:
            parts = {"": frame}
        opened = []
        for key, recorder in self._recorders.items():
            path = recorder.write(parts[key])
            if path is not None:
                opened.append(path)
        return opened

    def close(self) -> list[Path]:
        """Release all writers. Returns the finished file paths."""
        paths = [recorder.close() for recorder in self._recorders.values()]
        return [p for p in paths if p is not None]
