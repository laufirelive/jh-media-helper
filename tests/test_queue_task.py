from src.core.config import OutputFormat, PicSeqConfig, TaskStatus, TaskType
from src.core.queue_task import QueueTask


def test_create_pic_seq_task():
    cfg = PicSeqConfig(input_dir="/tmp/seq", scan_format="%06d.png")
    task = QueueTask.create(
        task_type=TaskType.PIC_SEQ,
        config=cfg,
        input_path="/tmp/seq",
        output_path="/tmp/sseq.mov",
    )
    assert task.task_type == TaskType.PIC_SEQ
    assert task.status == TaskStatus.PENDING
    assert task.progress == 0
    assert task.error is None
    assert len(task.id) == 8
    assert task.created_at != ""


def test_round_trip():
    cfg = PicSeqConfig(
        input_dir="/tmp/seq",
        fps=60,
        output_format=OutputFormat.MP4_HEVC,
    )
    task = QueueTask.create(
        task_type=TaskType.PIC_SEQ,
        config=cfg,
        input_path="/tmp/seq",
        output_path="/tmp/sseq.mp4",
    )
    task.status = TaskStatus.COMPLETED
    task.progress = 100
    task.total = 100

    d = task.to_dict()
    restored = QueueTask.from_dict(d)

    assert restored.id == task.id
    assert restored.task_type == TaskType.PIC_SEQ
    assert restored.status == TaskStatus.COMPLETED
    assert restored.progress == 100
    assert restored.total == 100
    assert restored.config["fps"] == 60
    assert restored.config["output_format"] == "mp4_hevc"


def test_from_dict_handles_missing_optional_fields():
    d = {
        "id": "abcd1234",
        "task_type": "pic_seq",
        "config": {"input_dir": "/tmp", "output_format": "mov_prores"},
        "input_path": "/tmp",
        "output_path": "/tmp/out.mov",
        "status": "pending",
        "created_at": "2026-04-08T00:00:00",
    }
    task = QueueTask.from_dict(d)
    assert task.progress == 0
    assert task.total == 0
    assert task.error is None
