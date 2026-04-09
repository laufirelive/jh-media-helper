import uuid
from dataclasses import dataclass
from datetime import datetime

from src.core.config import TaskStatus, TaskType


@dataclass
class QueueTask:
    id: str
    task_type: TaskType
    config: dict
    input_path: str
    output_path: str
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    total: int = 0
    progress_desc: str = ""
    error: str | None = None
    created_at: str = ""

    @classmethod
    def create(cls, task_type: TaskType, config, input_path: str, output_path: str) -> "QueueTask":
        config_dict = config.to_dict() if hasattr(config, "to_dict") else config
        return cls(
            id=uuid.uuid4().hex[:8],
            task_type=task_type,
            config=config_dict,
            input_path=input_path,
            output_path=output_path,
            status=TaskStatus.PENDING,
            progress=0,
            total=0,
            progress_desc="",
            error=None,
            created_at=datetime.now().isoformat(),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_type": self.task_type.value,
            "config": self.config,
            "input_path": self.input_path,
            "output_path": self.output_path,
            "status": self.status.value,
            "progress": self.progress,
            "total": self.total,
            "progress_desc": self.progress_desc,
            "error": self.error,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "QueueTask":
        return cls(
            id=d["id"],
            task_type=TaskType(d["task_type"]),
            config=d["config"],
            input_path=d["input_path"],
            output_path=d["output_path"],
            status=TaskStatus(d["status"]),
            progress=d.get("progress", 0),
            total=d.get("total", 0),
            progress_desc=d.get("progress_desc", ""),
            error=d.get("error"),
            created_at=d["created_at"],
        )
