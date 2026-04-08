import json
import os
from datetime import datetime

from src.core.config import TaskStatus
from src.core.queue_task import QueueTask


class QueueManager:
    """Manages a list of QueueTasks with JSON persistence."""

    def __init__(self, path: str):
        self._path = path
        self._tasks: list[QueueTask] = []

    @property
    def tasks(self) -> list[QueueTask]:
        return list(self._tasks)

    def add_task(self, task: QueueTask) -> None:
        self._tasks.append(task)

    def remove_task(self, task_id: str) -> None:
        self._tasks = [t for t in self._tasks if t.id != task_id]

    def get_task(self, task_id: str) -> QueueTask | None:
        for t in self._tasks:
            if t.id == task_id:
                return t
        return None

    def move_task(self, task_id: str, new_index: int) -> None:
        task = self.get_task(task_id)
        if task is None:
            return
        self._tasks.remove(task)
        new_index = max(0, min(new_index, len(self._tasks)))
        self._tasks.insert(new_index, task)

    def reorder_tasks(self, ordered_ids: list[str]) -> bool:
        """按 ordered_ids 重排任务列表；集合不一致时返回 False 且不修改。"""
        if len(ordered_ids) != len(self._tasks):
            return False
        by_id = {t.id: t for t in self._tasks}
        if set(ordered_ids) != set(by_id.keys()):
            return False
        self._tasks = [by_id[i] for i in ordered_ids]
        return True

    def clear_all(self) -> None:
        self._tasks.clear()

    def next_pending(self) -> QueueTask | None:
        for t in self._tasks:
            if t.status == TaskStatus.PENDING:
                return t
        return None

    def save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        data = {
            "version": 1,
            "updated_at": datetime.now().isoformat(),
            "tasks": [],
        }
        for task in self._tasks:
            d = task.to_dict()
            if d["status"] == TaskStatus.PROCESSING.value:
                d["status"] = TaskStatus.PENDING.value
            data["tasks"].append(d)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load(self) -> None:
        if not os.path.exists(self._path):
            return
        with open(self._path, encoding="utf-8") as f:
            data = json.load(f)
        self._tasks = [QueueTask.from_dict(d) for d in data.get("tasks", [])]
