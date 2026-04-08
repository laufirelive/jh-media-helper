import os
import tempfile

import pytest
from PyQt6.QtWidgets import QApplication

from src.core.config import PicSeqConfig, TaskStatus, TaskType
from src.core.queue_manager import QueueManager
from src.core.queue_task import QueueTask
from src.gui.main_window import MainWindow
from src.gui.queue_tab import QueueTab


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _FakeWorker:
    def __init__(self):
        self.cancel_called = False

    def cancel(self):
        self.cancel_called = True


class _FakeEncoderRegistry:
    def get_best_hevc(self):
        return None

    def get_fallback(self):
        return "libx264"


def _make_processing_task(input_path: str = "/tmp/seq") -> QueueTask:
    task = QueueTask.create(
        task_type=TaskType.PIC_SEQ,
        config=PicSeqConfig(input_dir=input_path),
        input_path=input_path,
        output_path="/tmp/out.mov",
    )
    task.status = TaskStatus.PROCESSING
    return task


def test_queue_cancel_current_requires_confirmation_no(qapp, monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        mgr = QueueManager(os.path.join(d, "queue.json"))
        mgr.add_task(_make_processing_task())
        tab = QueueTab(mgr, _FakeEncoderRegistry())
        fake = _FakeWorker()
        tab._worker = fake
        monkeypatch.setattr(
            "src.gui.queue_tab.confirm_action",
            lambda *args, **kwargs: False,
        )
        tab._on_cancel_current()
        assert fake.cancel_called is False


def test_queue_cancel_current_requires_confirmation_yes(qapp, monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        mgr = QueueManager(os.path.join(d, "queue.json"))
        task = _make_processing_task()
        mgr.add_task(task)
        tab = QueueTab(mgr, _FakeEncoderRegistry())
        fake = _FakeWorker()
        tab._worker = fake
        monkeypatch.setattr(
            "src.gui.queue_tab.confirm_action",
            lambda *args, **kwargs: True,
        )
        tab._on_cancel_current()
        assert fake.cancel_called is True
        assert tab._cancelling_task_id == task.id


def test_queue_cancel_selected_requires_confirmation_no(qapp, monkeypatch):
    """未运行时：取消所选需确认，点否不移除。"""
    with tempfile.TemporaryDirectory() as d:
        mgr = QueueManager(os.path.join(d, "queue.json"))
        task = QueueTask.create(
            task_type=TaskType.PIC_SEQ,
            config=PicSeqConfig(input_dir="/tmp/seq"),
            input_path="/tmp/seq",
            output_path="/tmp/out.mov",
        )
        mgr.add_task(task)
        tab = QueueTab(mgr, _FakeEncoderRegistry())
        tab._table.selectRow(0)
        monkeypatch.setattr(
            "src.gui.queue_tab.confirm_action",
            lambda *args, **kwargs: False,
        )
        tab._on_cancel_current()
        assert mgr.get_task(task.id) is not None


def test_queue_cancel_selected_requires_confirmation_yes(qapp, monkeypatch):
    """未运行时：确认后从队列移除选中任务。"""
    with tempfile.TemporaryDirectory() as d:
        mgr = QueueManager(os.path.join(d, "queue.json"))
        task = QueueTask.create(
            task_type=TaskType.PIC_SEQ,
            config=PicSeqConfig(input_dir="/tmp/seq"),
            input_path="/tmp/seq",
            output_path="/tmp/out.mov",
        )
        mgr.add_task(task)
        tab = QueueTab(mgr, _FakeEncoderRegistry())
        tab._table.selectRow(0)
        monkeypatch.setattr(
            "src.gui.queue_tab.confirm_action",
            lambda *args, **kwargs: True,
        )
        tab._on_cancel_current()
        assert mgr.get_task(task.id) is None


def test_main_cancel_requires_confirmation_no(qapp, monkeypatch):
    monkeypatch.setattr(MainWindow, "_check_queue_recovery", lambda self: None)
    monkeypatch.setattr("src.gui.main_window.EncoderRegistry._probe", lambda self: None)
    win = MainWindow()
    fake = _FakeWorker()
    win._worker = fake
    monkeypatch.setattr(
        "src.gui.main_window.confirm_action",
        lambda *args, **kwargs: False,
    )
    win._on_cancel()
    assert fake.cancel_called is False


def test_main_cancel_requires_confirmation_yes(qapp, monkeypatch):
    monkeypatch.setattr(MainWindow, "_check_queue_recovery", lambda self: None)
    monkeypatch.setattr("src.gui.main_window.EncoderRegistry._probe", lambda self: None)
    win = MainWindow()
    fake = _FakeWorker()
    win._worker = fake
    monkeypatch.setattr(
        "src.gui.main_window.confirm_action",
        lambda *args, **kwargs: True,
    )
    win._on_cancel()
    assert fake.cancel_called is True
