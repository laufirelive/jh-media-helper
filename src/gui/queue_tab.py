import os
import time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
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

_FORMAT_LABELS = {
    "mov_prores": "MOV ProRes 4444",
    "mp4_hevc": "MP4 H.265",
    "mp4_h264": "MP4 H.264",
}


class QueueTab(QWidget):
    task_count_changed = pyqtSignal(int)

    def __init__(self, queue_manager: QueueManager, encoder_registry: EncoderRegistry, parent=None):
        super().__init__(parent)
        self._queue_manager = queue_manager
        self._encoder_registry = encoder_registry
        self._worker: FFmpegWorker | None = None
        self._running = False
        self._last_refresh_time = 0.0
        self._init_ui()
        self._refresh_table()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Task table
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["文件名", "类型", "输出格式", "状态"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._table)

        # Current task progress
        progress_group = QGroupBox("当前任务")
        progress_layout = QVBoxLayout(progress_group)

        self._current_label = QLabel("")
        self._current_label.setStyleSheet("color: gray;")
        progress_layout.addWidget(self._current_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        progress_layout.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: gray;")
        progress_layout.addWidget(self._status_label)

        self._total_label = QLabel("")
        self._total_label.setStyleSheet("color: gray;")
        progress_layout.addWidget(self._total_label)

        layout.addWidget(progress_group)

        # Control buttons (centered)
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._btn_start = QPushButton("开始队列")
        self._btn_start.clicked.connect(self._on_start)
        btn_row.addWidget(self._btn_start)

        self._btn_cancel = QPushButton("取消当前")
        self._btn_cancel.clicked.connect(self._on_cancel_current)
        self._btn_cancel.setEnabled(False)
        btn_row.addWidget(self._btn_cancel)

        self._btn_clear = QPushButton("清空队列")
        self._btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(self._btn_clear)

        btn_row.addStretch()
        layout.addLayout(btn_row)

    # --- Table ---

    def _refresh_table(self):
        tasks = self._queue_manager.tasks
        self._table.setRowCount(0)
        for task in tasks:
            row = self._table.rowCount()
            self._table.insertRow(row)
            display_name = os.path.basename(task.input_path.rstrip(os.sep)) or task.input_path
            self._table.setItem(row, 0, QTableWidgetItem(display_name))
            self._table.setItem(row, 1, QTableWidgetItem(_TYPE_LABELS.get(task.task_type, "?")))
            fmt_label = _FORMAT_LABELS.get(task.config.get("output_format", ""), "?")
            self._table.setItem(row, 2, QTableWidgetItem(fmt_label))
            self._table.setItem(row, 3, QTableWidgetItem(self._status_text(task)))
        self.task_count_changed.emit(len(tasks))

    def _status_text(self, task) -> str:
        if task.status == TaskStatus.COMPLETED:
            return "完成"
        if task.status == TaskStatus.FAILED:
            return "失败"
        if task.status == TaskStatus.CANCELLED:
            return "已取消"
        if task.status == TaskStatus.PROCESSING:
            if task.total > 0:
                return f"编码中 {task.progress}/{task.total}"
            return "编码中..."
        return "等待"

    # --- Context menu ---

    def _show_context_menu(self, pos):
        row = self._table.rowAt(pos.y())
        tasks = self._queue_manager.tasks
        if row < 0 or row >= len(tasks):
            return
        task = tasks[row]
        if task.status == TaskStatus.PROCESSING:
            return

        menu = QMenu(self)
        menu.addAction("删除", lambda: self._remove_task(task.id))
        if row > 0:
            menu.addAction("移到顶部", lambda: self._move_to(task.id, 0))
        if row < len(tasks) - 1:
            menu.addAction("移到底部", lambda: self._move_to(task.id, len(tasks) - 1))
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _remove_task(self, task_id: str):
        self._queue_manager.remove_task(task_id)
        self._queue_manager.save()
        self._refresh_table()

    def _move_to(self, task_id: str, new_index: int):
        self._queue_manager.move_task(task_id, new_index)
        self._queue_manager.save()
        self._refresh_table()

    # --- Queue execution ---

    def _on_start(self):
        self._running = True
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._btn_clear.setEnabled(False)
        self._run_next()

    def _run_next(self):
        if not self._running:
            self._on_queue_stopped()
            return
        task = self._queue_manager.next_pending()
        if task is None:
            self._on_queue_finished()
            return

        task.status = TaskStatus.PROCESSING
        self._queue_manager.save()
        self._refresh_table()

        self._current_label.setText(f"当前: {os.path.basename(task.input_path)}")
        self._progress_bar.setValue(0)
        self._status_label.setText("准备中...")

        count = 0
        if task.task_type == TaskType.PIC_SEQ:
            cfg = PicSeqConfig.from_dict(task.config)
            ok, count, err = validate(cfg)
            if not ok:
                task.status = TaskStatus.FAILED
                task.error = err
                self._queue_manager.save()
                self._refresh_table()
                self._run_next()
                return

        self._worker = FFmpegWorker(
            task_type=task.task_type,
            config=task.config,
            encoder_registry=self._encoder_registry,
            total_frames=count,
        )
        self._worker.progress.connect(
            lambda cur, tot, desc, tid=task.id: self._on_task_progress(tid, cur, tot, desc)
        )
        self._worker.finished.connect(
            lambda path, tid=task.id: self._on_task_finished(tid)
        )
        self._worker.error.connect(
            lambda msg, tid=task.id: self._on_task_error(tid, msg)
        )
        self._worker.start()

    def _on_task_progress(self, task_id: str, current: int, total: int, desc: str):
        task = self._queue_manager.get_task(task_id)
        if task:
            task.progress = current
            task.total = total

        # Update progress bar and status label (always)
        percent = int(current / total * 100) if total > 0 else 0
        self._progress_bar.setValue(percent)
        if total > 0:
            self._status_label.setText(f"编码中: {current}/{total}")
        self._update_total_progress()

        # Throttle table refresh to every 2s or every 100 frames
        now = time.time()
        if now - self._last_refresh_time >= 2.0 or current % 100 == 0:
            self._queue_manager.save()
            self._refresh_table()
            self._last_refresh_time = now

    def _update_total_progress(self):
        tasks = self._queue_manager.tasks
        task_count = len(tasks)
        if task_count == 0:
            return
        completed_count = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        current_idx = completed_count + 1

        total_work = 0
        completed_work = 0
        for t in tasks:
            weight = max(t.total, 1)
            total_work += weight
            if t.status == TaskStatus.COMPLETED:
                completed_work += weight
            elif t.status == TaskStatus.PROCESSING:
                completed_work += t.progress

        pct = int(completed_work / total_work * 100) if total_work > 0 else 0
        self._total_label.setText(f"队列: 任务 {current_idx}/{task_count} — 总进度 {pct}%")

    def _on_task_finished(self, task_id: str):
        task = self._queue_manager.get_task(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
        self._queue_manager.save()
        self._refresh_table()
        self._worker = None
        self._run_next()

    def _on_task_error(self, task_id: str, message: str):
        task = self._queue_manager.get_task(task_id)
        if task:
            task.status = TaskStatus.FAILED
            task.error = message
        self._queue_manager.save()
        self._refresh_table()
        self._worker = None
        self._run_next()

    def _on_cancel_current(self):
        if self._worker:
            self._worker.cancel()

    def _on_clear(self):
        reply = QMessageBox.question(
            self, "确认", "确定清空所有队列任务？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._queue_manager.clear_all()
            self._queue_manager.save()
            self._refresh_table()
            self._current_label.setText("")
            self._status_label.setText("")
            self._total_label.setText("")
            self._progress_bar.setValue(0)

    def _on_queue_finished(self):
        self._on_queue_stopped()
        self._current_label.setText("队列完成")
        self._status_label.setText("")
        self._progress_bar.setValue(100)
        QApplication.beep()

    def _on_queue_stopped(self):
        self._running = False
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._btn_clear.setEnabled(True)

    def refresh(self):
        self._refresh_table()

    def stop(self):
        self._running = False
        if self._worker:
            self._worker.cancel()
            self._worker.wait(3000)
