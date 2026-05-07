import os

import pytest
from PyQt6.QtWidgets import QApplication

from src.core.config import CombatAudioConfig, TaskType
from src.core.queue_manager import QueueManager
from src.core.queue_task import QueueTask
from src.gui import queue_tab
from src.gui.queue_tab import QueueTab


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _FakeEncoderRegistry:
    def get_best_hevc(self):
        return None

    def get_fallback(self):
        return "libx264"


class _Signal:
    def connect(self, callback):
        self.callback = callback


class _FakeWorker:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.progress = _Signal()
        self.finished = _Signal()
        self.error = _Signal()
        self.started = False
        self.__class__.instances.append(self)

    def start(self):
        self.started = True

    @staticmethod
    def split_error_message(message):
        return message, ""


def _make_task(cfg: CombatAudioConfig) -> QueueTask:
    return QueueTask.create(
        task_type=TaskType.COMBAT_AUDIO,
        config=cfg,
        input_path=cfg.input_path,
        output_path=os.path.join(cfg.output_dir or os.path.dirname(cfg.input_path), "out.mkv"),
    )


def test_run_next_boxed_combat_audio_counts_secondary_mkv_outputs(qapp, tmp_path, monkeypatch):
    input_path = tmp_path / "main.mkv"
    input_path.write_bytes(b"")
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "song.aac").write_bytes(b"")
    secondaries = [tmp_path / "secondary-1.mkv", tmp_path / "secondary-2.mkv"]
    for path in secondaries:
        path.write_bytes(b"")

    cfg = CombatAudioConfig(
        input_path=str(input_path),
        audio_dir=str(audio_dir),
        boxed=True,
        secondary_video_paths=[str(path) for path in secondaries],
    )
    mgr = QueueManager(str(tmp_path / "queue.json"))
    mgr.add_task(_make_task(cfg))
    _FakeWorker.instances = []
    monkeypatch.setattr(queue_tab, "FFmpegWorker", _FakeWorker)
    original_is_pure_audio = queue_tab.combat_audio.is_pure_audio
    monkeypatch.setattr(
        queue_tab.combat_audio,
        "is_pure_audio",
        lambda path: original_is_pure_audio(path) and path != str(input_path),
    )

    tab = QueueTab(mgr, _FakeEncoderRegistry())
    tab._running = True
    tab._run_next()

    assert _FakeWorker.instances[0].kwargs["total_frames"] == 3
    assert _FakeWorker.instances[0].started


def test_run_next_non_boxed_combat_audio_uses_audio_order_count(qapp, tmp_path, monkeypatch):
    input_path = tmp_path / "main.mkv"
    input_path.write_bytes(b"")
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "song-1.aac").write_bytes(b"")
    (audio_dir / "song-2.aac").write_bytes(b"")

    cfg = CombatAudioConfig(
        input_path=str(input_path),
        audio_dir=str(audio_dir),
        boxed=False,
        audio_order=["song-1.aac", "song-2.aac"],
    )
    mgr = QueueManager(str(tmp_path / "queue.json"))
    mgr.add_task(_make_task(cfg))
    _FakeWorker.instances = []
    monkeypatch.setattr(queue_tab, "FFmpegWorker", _FakeWorker)

    tab = QueueTab(mgr, _FakeEncoderRegistry())
    tab._running = True
    tab._run_next()

    assert _FakeWorker.instances[0].kwargs["total_frames"] == 2
