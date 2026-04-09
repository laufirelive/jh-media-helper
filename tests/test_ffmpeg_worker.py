import subprocess

from src.core.config import TaskType
from src.worker.ffmpeg_worker import FFmpegWorker, parse_progress


class TestParseProgress:
    def test_parse_frame_number(self):
        line = "frame=  810 fps=120 q=28.0 size=   25600kB time=00:00:06.75"
        assert parse_progress(line) == 810

    def test_parse_frame_no_spaces(self):
        line = "frame=1247 fps=95.2 q=31.0 Lsize=  102400kB time=00:00:10.39"
        assert parse_progress(line) == 1247

    def test_no_frame_returns_none(self):
        line = "Press [q] to stop, [?] for help"
        assert parse_progress(line) is None

    def test_empty_line(self):
        assert parse_progress("") is None


class _FakeProcess:
    def __init__(self, raise_timeout: bool):
        self.raise_timeout = raise_timeout
        self.terminated = 0
        self.killed = 0
        self._polled = None

    def poll(self):
        return self._polled

    def terminate(self):
        self.terminated += 1

    def wait(self, timeout=None):
        if self.raise_timeout and timeout is not None and self.killed == 0:
            raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=timeout)
        self._polled = 0
        return 0

    def kill(self):
        self.killed += 1
        self._polled = -9


class TestWorkerCancel:
    def test_cancel_terminates_process(self):
        worker = FFmpegWorker(TaskType.PIC_SEQ, {}, encoder_registry=None)
        fake = _FakeProcess(raise_timeout=False)
        worker._process = fake
        worker.cancel()
        assert fake.terminated == 1
        assert fake.killed == 0

    def test_cancel_kills_process_when_terminate_timeout(self):
        worker = FFmpegWorker(TaskType.PIC_SEQ, {}, encoder_registry=None)
        fake = _FakeProcess(raise_timeout=True)
        worker._process = fake
        worker.cancel()
        assert fake.terminated == 1
        assert fake.killed == 1
