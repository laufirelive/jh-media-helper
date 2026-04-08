import os

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.config import PicSeqConfig, TaskStatus, TaskType
from src.core.encoder_registry import EncoderRegistry
from src.core.queue_manager import QueueManager
from src.core.processors.pic_seq import validate
from src.worker.ffmpeg_worker import FFmpegWorker

_TYPE_LABELS = {
    TaskType.PIC_SEQ: "图片序列",
    TaskType.COMBAT_AUDIO: "音视频混合",
    TaskType.MKV_EXTRACT: "MKV解包",
}

_STATUS_LABELS = {
    TaskStatus.PENDING: "等待中",
    TaskStatus.PROCESSING: "▶ 处理中",
    TaskStatus.COMPLETED: "✓ 完成",
    TaskStatus.FAILED: "✕ 失败",
    TaskStatus.CANCELLED: "已取消",
}


class QueueTab(QWidget):
    task_count_changed = pyqtSignal(int)

    def __init__(self, queue_manager: QueueManager, encoder_registry: EncoderRegistry, parent=None):
        super().__init__(parent)
        self._queue_manager = queue_manager
        self._encoder_registry = encoder_registry
        self._worker: FFmpegWorker | None = None
        self._running = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self._btn_start = QPushButton("开始队列")
        self._btn_start.clicked.connect(self._on_start)
        self._btn_cancel = QPushButton("取消当前")
        self._btn_cancel.clicked.connect(self._on_cancel_current)
        self._btn_cancel.setEnabled(False)
        self._btn_clear = QPushButton("清空")
        self._btn_clear.clicked.connect(self._on_clear)
        controls.addWidget(self._btn_start)
        controls.addWidget(self._btn_cancel)
        controls.addWidget(self._btn_clear)
        controls.addStretch()
        layout.addLayout(controls)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["#", "类型", "输入", "状态", "操作"])
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)
        self.refresh()

    def refresh(self):
        tasks = self._queue_manager.tasks
        self._table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            self._table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self._table.setItem(row, 1, QTableWidgetItem(_TYPE_LABELS.get(task.task_type, "?")))
            input_name = os.path.basename(task.input_path)
            self._table.setItem(row, 2, QTableWidgetItem(input_name))
            self._table.setItem(row, 3, QTableWidgetItem(_STATUS_LABELS.get(task.status, "?")))
            btn_del = QPushButton("✕")
            btn_del.setFixedWidth(30)
            btn_del.clicked.connect(lambda checked, tid=task.id: self._delete_task(tid))
            self._table.setCellWidget(row, 4, btn_del)
        self.task_count_changed.emit(len(tasks))

    def _delete_task(self, task_id: str):
        self._queue_manager.remove_task(task_id)
        self._queue_manager.save()
        self.refresh()

    def _on_start(self):
        self._running = True
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._run_next()

    def _run_next(self):
        if not self._running:
            self._on_queue_stopped()
            return
        task = self._queue_manager.next_pending()
        if task is None:
            self._on_queue_stopped()
            return

        task.status = TaskStatus.PROCESSING
        self._queue_manager.save()
        self.refresh()

        count = 0
        if task.task_type == TaskType.PIC_SEQ:
            cfg = PicSeqConfig.from_dict(task.config)
            ok, count, err = validate(cfg)
            if not ok:
                task.status = TaskStatus.FAILED
                task.error = err
                self._queue_manager.save()
                self.refresh()
                self._run_next()
                return

        self._worker = FFmpegWorker(
            task_type=task.task_type,
            config=task.config,
            encoder_registry=self._encoder_registry,
            total_frames=count,
        )
        self._worker.progress.connect(
            lambda cur, tot, desc, tid=task.id: self._on_task_progress(tid, cur, tot)
        )
        self._worker.finished.connect(
            lambda path, tid=task.id: self._on_task_finished(tid)
        )
        self._worker.error.connect(
            lambda msg, tid=task.id: self._on_task_error(tid, msg)
        )
        self._worker.start()

    def _on_task_progress(self, task_id: str, current: int, total: int):
        task = self._queue_manager.get_task(task_id)
        if task:
            task.progress = current
            task.total = total
        self.refresh()

    def _on_task_finished(self, task_id: str):
        task = self._queue_manager.get_task(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
        self._queue_manager.save()
        self.refresh()
        self._worker = None
        self._run_next()

    def _on_task_error(self, task_id: str, message: str):
        task = self._queue_manager.get_task(task_id)
        if task:
            task.status = TaskStatus.FAILED
            task.error = message
        self._queue_manager.save()
        self.refresh()
        self._worker = None
        self._run_next()

    def _on_cancel_current(self):
        if self._worker:
            self._worker.cancel()

    def _on_clear(self):
        reply = QMessageBox.question(self, "确认", "确定清空所有队列任务？")
        if reply == QMessageBox.StandardButton.Yes:
            self._queue_manager.clear_all()
            self._queue_manager.save()
            self.refresh()

    def _on_queue_stopped(self):
        self._running = False
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)

    def stop(self):
        self._running = False
        if self._worker:
            self._worker.cancel()
            self._worker.wait(3000)
