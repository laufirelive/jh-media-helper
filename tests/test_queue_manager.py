import json
import os
import tempfile

from src.core.config import PicSeqConfig, TaskStatus, TaskType
from src.core.queue_manager import QueueManager
from src.core.queue_task import QueueTask


def _make_task(input_path: str = "/tmp/seq") -> QueueTask:
    cfg = PicSeqConfig(input_dir=input_path)
    return QueueTask.create(
        task_type=TaskType.PIC_SEQ,
        config=cfg,
        input_path=input_path,
        output_path=f"/tmp/s{os.path.basename(input_path)}.mov",
    )


class TestQueueManager:
    def test_add_and_get(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = QueueManager(os.path.join(d, "queue.json"))
            task = _make_task()
            mgr.add_task(task)
            assert mgr.get_task(task.id) is task
            assert len(mgr.tasks) == 1

    def test_remove(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = QueueManager(os.path.join(d, "queue.json"))
            task = _make_task()
            mgr.add_task(task)
            mgr.remove_task(task.id)
            assert len(mgr.tasks) == 0

    def test_move_task(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = QueueManager(os.path.join(d, "queue.json"))
            t1 = _make_task("/tmp/a")
            t2 = _make_task("/tmp/b")
            t3 = _make_task("/tmp/c")
            mgr.add_task(t1)
            mgr.add_task(t2)
            mgr.add_task(t3)
            mgr.move_task(t3.id, 0)
            assert mgr.tasks[0].id == t3.id

    def test_reorder_tasks(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = QueueManager(os.path.join(d, "queue.json"))
            t1 = _make_task("/tmp/a")
            t2 = _make_task("/tmp/b")
            t3 = _make_task("/tmp/c")
            mgr.add_task(t1)
            mgr.add_task(t2)
            mgr.add_task(t3)
            assert mgr.reorder_tasks([t3.id, t1.id, t2.id])
            assert [t.id for t in mgr.tasks] == [t3.id, t1.id, t2.id]

    def test_reorder_tasks_rejects_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = QueueManager(os.path.join(d, "queue.json"))
            t1 = _make_task("/tmp/a")
            t2 = _make_task("/tmp/b")
            mgr.add_task(t1)
            mgr.add_task(t2)
            assert not mgr.reorder_tasks([t1.id])
            assert [t.id for t in mgr.tasks] == [t1.id, t2.id]

    def test_next_pending(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = QueueManager(os.path.join(d, "queue.json"))
            t1 = _make_task("/tmp/a")
            t2 = _make_task("/tmp/b")
            t1.status = TaskStatus.COMPLETED
            mgr.add_task(t1)
            mgr.add_task(t2)
            nxt = mgr.next_pending()
            assert nxt.id == t2.id

    def test_next_pending_returns_none_when_empty(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = QueueManager(os.path.join(d, "queue.json"))
            assert mgr.next_pending() is None

    def test_clear_all(self):
        with tempfile.TemporaryDirectory() as d:
            mgr = QueueManager(os.path.join(d, "queue.json"))
            mgr.add_task(_make_task())
            mgr.add_task(_make_task())
            mgr.clear_all()
            assert len(mgr.tasks) == 0

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "queue.json")
            mgr = QueueManager(path)
            t1 = _make_task("/tmp/a")
            t1.status = TaskStatus.COMPLETED
            t1.progress_desc = "[1/2] 提取音频"
            t2 = _make_task("/tmp/b")
            mgr.add_task(t1)
            mgr.add_task(t2)
            mgr.save()
            mgr2 = QueueManager(path)
            mgr2.load()
            assert len(mgr2.tasks) == 2
            assert mgr2.tasks[0].status == TaskStatus.COMPLETED
            assert mgr2.tasks[0].progress_desc == "[1/2] 提取音频"
            assert mgr2.tasks[1].status == TaskStatus.PENDING

    def test_save_converts_processing_to_pending(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "queue.json")
            mgr = QueueManager(path)
            task = _make_task()
            task.status = TaskStatus.PROCESSING
            mgr.add_task(task)
            mgr.save()
            with open(path) as f:
                data = json.load(f)
            assert data["tasks"][0]["status"] == "pending"

    def test_load_nonexistent_file(self):
        mgr = QueueManager("/nonexistent/queue.json")
        mgr.load()
        assert len(mgr.tasks) == 0
