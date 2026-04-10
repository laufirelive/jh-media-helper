import os
import re
import time

from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.config import CombatAudioConfig, PicSeqConfig, TaskStatus, TaskType
from src.core.encoder_registry import EncoderRegistry
from src.core.processors import combat_audio
from src.core.processors.pic_seq import (
    detect_resolution,
    detect_scan_format,
    validate,
    _resolve_output_path,
)
from src.core.queue_manager import QueueManager
from src.core.queue_task import QueueTask
from src.gui.components.action_bar import ActionBar
from src.gui.confirm_dialog import confirm_action
from src.gui.components.progress_section import ProgressSection
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

_STATUS_COLORS = {
    TaskStatus.COMPLETED: "#33aa66",
    TaskStatus.PROCESSING: "#6699cc",
    TaskStatus.FAILED: "#cc4444",
    TaskStatus.CANCELLED: "#cc4444",
    TaskStatus.PENDING: "#888888",
}

_TABLE_QSS = """
QHeaderView::section {
    border: none;
    border-bottom: 1px solid palette(mid);
    padding: 6px 8px;
    font-weight: bold;
}
"""

_PHASE_RE = re.compile(r"^\[(\d+)/(\d+)\]\s*")


class QueueTab(QWidget):
    task_count_changed = pyqtSignal(int)

    def __init__(self, queue_manager: QueueManager, encoder_registry: EncoderRegistry, parent=None):
        super().__init__(parent)
        self._queue_manager = queue_manager
        self._encoder_registry = encoder_registry
        self._worker: FFmpegWorker | None = None
        self._cancelling_task_id: str | None = None
        self._running = False
        self._last_refresh_time = 0.0
        self.setAcceptDrops(True)
        self._init_ui()
        self._table.viewport().installEventFilter(self)
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
        self._table.verticalHeader().setVisible(True)
        self._table.verticalHeader().setSectionsMovable(True)
        self._table.verticalHeader().sectionMoved.connect(self._on_row_moved)
        self._table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._table.setAlternatingRowColors(False)
        self._table.setStyleSheet(_TABLE_QSS)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._table)

        # Empty state overlay
        self._empty_widget = QWidget(self._table)
        empty_layout = QVBoxLayout(self._empty_widget)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon = QLabel("📋")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)
        empty_title = QLabel("队列为空")
        empty_title.setStyleSheet("color: gray;")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_hint = QLabel("在任务面板中点击「加入队列」添加任务，或拖入文件夹")
        empty_hint.setStyleSheet("color: gray; font-size: 11px;")
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_hint)

        # Current task progress
        progress_group = QGroupBox("当前任务")
        progress_layout = QVBoxLayout(progress_group)

        info_row = QHBoxLayout()
        self._current_label = QLabel("")
        info_row.addWidget(self._current_label)
        info_row.addStretch()
        self._task_count_label = QLabel("")
        self._task_count_label.setStyleSheet("color: gray;")
        info_row.addWidget(self._task_count_label)
        progress_layout.addLayout(info_row)

        self._progress = ProgressSection()
        progress_layout.addWidget(self._progress)

        self._total_label = QLabel("")
        self._total_label.setStyleSheet("color: gray;")
        self._total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        progress_layout.addWidget(self._total_label)

        layout.addWidget(progress_group)

        # Control buttons
        self._action_bar = ActionBar()
        self._btn_start = self._action_bar.add_button("开始队列", role="primary")
        self._btn_start.clicked.connect(self._on_start)
        self._btn_cancel = self._action_bar.add_button("取消当前", role="danger", enabled=False)
        self._btn_cancel.clicked.connect(self._on_cancel_current)
        self._table.itemSelectionChanged.connect(self._update_cancel_button_state)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._btn_clear = self._action_bar.add_button("清空队列", role="secondary")
        self._btn_clear.clicked.connect(self._on_clear)
        layout.addWidget(self._action_bar)

    # --- Table ---

    def _refresh_table(self):
        tasks = self._queue_manager.tasks
        self._table.setRowCount(0)
        self._empty_widget.setVisible(len(tasks) == 0)

        for task in tasks:
            row = self._table.rowCount()
            self._table.insertRow(row)

            display_name = os.path.basename(task.input_path.rstrip(os.sep)) or task.input_path
            name_item = QTableWidgetItem(display_name)
            # 供拖放后对账顺序，避免与 QueueManager 脱节
            name_item.setData(Qt.ItemDataRole.UserRole, task.id)
            if task.status == TaskStatus.PROCESSING:
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)
            self._table.setItem(row, 0, name_item)

            type_item = QTableWidgetItem(_TYPE_LABELS.get(task.task_type, "?"))
            type_item.setForeground(Qt.GlobalColor.gray)
            self._table.setItem(row, 1, type_item)

            if task.task_type == TaskType.COMBAT_AUDIO:
                if task.config.get("boxed"):
                    fmt_label = "MKV 封装"
                elif task.config.get("mix_enabled", True):
                    fmt_label = "混合音频"
                else:
                    fmt_label = "时长对齐"
            else:
                fmt_label = _FORMAT_LABELS.get(task.config.get("output_format", ""), "?")
            fmt_item = QTableWidgetItem(fmt_label)
            fmt_item.setForeground(Qt.GlobalColor.gray)
            self._table.setItem(row, 2, fmt_item)

            status_text = self._status_text(task)
            status_item = QTableWidgetItem(status_text)
            color = _STATUS_COLORS.get(task.status, "#888")
            status_item.setForeground(QColor(color))
            if task.error:
                status_item.setToolTip(task.error)
            self._table.setItem(row, 3, status_item)

        self.task_count_changed.emit(len(tasks))
        self._update_cancel_button_state()

    def _update_cancel_button_state(self):
        """有 worker 时可取消当前编码；无 worker 时可取消（移除）表格中选中的非进行中任务。"""
        if self._worker:
            self._btn_cancel.setText("取消当前")
            self._btn_cancel.setEnabled(True)
            return
        self._btn_cancel.setText("取消所选")
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            self._btn_cancel.setEnabled(False)
            return
        row = rows[0].row()
        tasks = self._queue_manager.tasks
        if row < 0 or row >= len(tasks):
            self._btn_cancel.setEnabled(False)
            return
        task = tasks[row]
        # 进行中应由 worker 分支处理；无 worker 时若仍为 PROCESSING 则禁止误删
        if task.status == TaskStatus.PROCESSING:
            self._btn_cancel.setEnabled(False)
            return
        self._btn_cancel.setEnabled(True)

    def _status_text(self, task) -> str:
        if task.status == TaskStatus.COMPLETED:
            return "完成"
        if task.status == TaskStatus.FAILED:
            summary, _ = FFmpegWorker.split_error_message(task.error)
            if not summary:
                return "失败"
            text = f"失败：{summary}"
            return text if len(text) <= 28 else f"{text[:27]}…"
        if task.status == TaskStatus.CANCELLED:
            return "已取消"
        if task.status == TaskStatus.PROCESSING:
            if task.progress_desc and task.total > 0:
                return f"{task.progress_desc} {task.progress}/{task.total}"
            if task.total > 0:
                return f"编码中 {task.progress}/{task.total}"
            return "编码中..."
        return "等待"

    @staticmethod
    def _task_completion_fraction(task) -> float:
        if task.status == TaskStatus.COMPLETED:
            return 1.0
        if task.status != TaskStatus.PROCESSING or task.total <= 0:
            return 0.0

        progress_fraction = max(0.0, min(task.progress / task.total, 1.0))
        match = _PHASE_RE.match(task.progress_desc or "")
        if not match:
            return progress_fraction

        phase_index = int(match.group(1))
        phase_total = int(match.group(2))
        if phase_total <= 0:
            return progress_fraction
        completed_phases = max(0, min(phase_index - 1, phase_total))
        return min((completed_phases + progress_fraction) / phase_total, 1.0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_empty_widget'):
            self._empty_widget.setGeometry(self._table.rect())

    def eventFilter(self, obj, event):
        # 表格内部拖放落到空白处时，sectionMoved 可能不触发；在 Drop 之后按行内 task id 与队列对账
        if obj is self._table.viewport() and event.type() == QEvent.Type.Drop:
            QTimer.singleShot(0, self._reconcile_order_after_drop)
        return super().eventFilter(obj, event)

    # --- Drag and drop ---

    def _on_row_moved(self, logical: int, old_visual: int, new_visual: int):
        tasks = self._queue_manager.tasks
        if old_visual < len(tasks):
            task_id = tasks[old_visual].id
            self._queue_manager.move_task(task_id, new_visual)
            self._queue_manager.save()
            self._refresh_table()

    def _reconcile_order_after_drop(self):
        """根据表格当前行顺序与 QueueManager 对齐（修复内部拖放未同步导致丢失/错位）。"""
        tasks = self._queue_manager.tasks
        if self._table.rowCount() != len(tasks):
            self._refresh_table()
            return
        ids: list[str] = []
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            tid = item.data(Qt.ItemDataRole.UserRole) if item else None
            if not tid:
                self._refresh_table()
                return
            ids.append(tid)
        if ids == [t.id for t in tasks]:
            return
        if self._queue_manager.reorder_tasks(ids):
            self._queue_manager.save()
        self._refresh_table()

    def dragEnterEvent(self, event):
        # 仅接受 Finder 等外部文件拖入；无 URL 的拖放交给子控件（表格内部排序）处理
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isdir(path):
                self._add_folder_as_task(path)
        event.acceptProposedAction()

    def _add_folder_as_task(self, folder: str):
        result = detect_scan_format(folder)
        if result is None:
            return
        fmt, count = result
        try:
            w, h = detect_resolution(folder, fmt)
        except FileNotFoundError:
            w, h = 3840, 2160

        config = PicSeqConfig(
            input_dir=folder,
            fps=120,
            bitrate_mbps=32,
            width=w,
            height=h,
            scan_format=fmt,
        )
        ok, frame_count, err = validate(config)
        if not ok:
            return

        output_path = _resolve_output_path(config)
        task = QueueTask.create(
            task_type=TaskType.PIC_SEQ,
            config=config,
            input_path=folder,
            output_path=output_path,
        )
        self._queue_manager.add_task(task)
        self._queue_manager.save()
        self._refresh_table()

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
        self._btn_clear.setEnabled(False)
        self._run_next()
        self._update_cancel_button_state()

    def _run_next(self):
        if not self._running:
            self._on_queue_stopped()
            return
        task = self._queue_manager.next_pending()
        if task is None:
            self._on_queue_finished()
            return

        task.status = TaskStatus.PROCESSING
        task.error = None
        self._queue_manager.save()
        self._refresh_table()

        self._current_label.setText(os.path.basename(task.input_path))
        self._progress.reset()

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
        elif task.task_type == TaskType.COMBAT_AUDIO:
            cfg = CombatAudioConfig.from_dict(task.config)
            ok, err = combat_audio.validate(cfg)
            if not ok:
                task.status = TaskStatus.FAILED
                task.error = err
                self._queue_manager.save()
                self._refresh_table()
                self._run_next()
                return
            audio_files = cfg.audio_order or [f.filename for f in combat_audio.scan_audio_dir(cfg.audio_dir)]
            count = len(audio_files)

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
        self._cancelling_task_id = None

    def _on_task_progress(self, task_id: str, current: int, total: int, desc: str):
        task = self._queue_manager.get_task(task_id)
        if task:
            task.progress = current
            task.total = total
            task.progress_desc = desc

        self._progress.update_progress(current, total, desc)
        self._update_total_progress()

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
        self._task_count_label.setText(f"任务 {current_idx}/{task_count}")

        total_work = 0
        completed_work = 0
        for t in tasks:
            total_work += 1
            completed_work += self._task_completion_fraction(t)

        pct = int(completed_work / total_work * 100) if total_work > 0 else 0
        self._total_label.setText(f"总进度 {pct}%")

    def _on_selection_changed(self):
        self._sync_selected_task_details()

    def _sync_selected_task_details(self):
        if self._worker is not None:
            return
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        tasks = self._queue_manager.tasks
        if row < 0 or row >= len(tasks):
            return
        task = tasks[row]
        display_name = os.path.basename(task.input_path.rstrip(os.sep)) or task.input_path
        self._current_label.setText(display_name)
        if task.status == TaskStatus.FAILED and task.error:
            summary, details = FFmpegWorker.split_error_message(task.error)
            self._progress.set_error(summary or "任务失败", details or None)
            return
        if task.status == TaskStatus.COMPLETED:
            self._progress.set_finished("任务已完成")
            return
        if task.status == TaskStatus.CANCELLED:
            self._progress.set_finished("任务已取消")
            return
        self._progress.reset()

    def _on_task_finished(self, task_id: str):
        task = self._queue_manager.get_task(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            task.error = None
            task.progress_desc = ""
        self._cancelling_task_id = None
        self._queue_manager.save()
        self._refresh_table()
        self._worker = None
        self._sync_selected_task_details()
        self._run_next()

    def _on_task_error(self, task_id: str, message: str):
        # 用户取消：从队列中移除该条，避免列表里仍占一行
        is_cancel = message == "已取消" or self._cancelling_task_id == task_id
        if is_cancel:
            self._queue_manager.remove_task(task_id)
        else:
            task = self._queue_manager.get_task(task_id)
            if task:
                task.status = TaskStatus.FAILED
                task.error = message
                task.progress_desc = ""
        self._cancelling_task_id = None
        self._queue_manager.save()
        self._refresh_table()
        self._worker = None
        if not is_cancel:
            summary, details = FFmpegWorker.split_error_message(message)
            self._progress.set_error(summary or "任务失败", details or None)
        self._sync_selected_task_details()
        self._run_next()

    def _on_cancel_current(self):
        # 队列正在跑 FFmpeg：终止当前进程并从队列移除该条
        if self._worker:
            task = next((t for t in self._queue_manager.tasks if t.status == TaskStatus.PROCESSING), None)
            display_name = (
                os.path.basename(task.input_path.rstrip(os.sep)) or task.input_path
                if task
                else "当前任务"
            )
            if not confirm_action(
                self,
                "确认取消",
                f"确定取消任务「{display_name}」并从队列中移除吗？",
                default_confirm=False,
            ):
                return
            self._cancelling_task_id = task.id if task else None
            self._worker.cancel()
            return

        # 未运行：按选中行从队列移除（等待中 / 已完成等均可清理）
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        tasks = self._queue_manager.tasks
        if row < 0 or row >= len(tasks):
            return
        task = tasks[row]
        if task.status == TaskStatus.PROCESSING:
            return
        display_name = os.path.basename(task.input_path.rstrip(os.sep)) or task.input_path
        if not confirm_action(
            self,
            "确认取消",
            f"确定从队列中移除任务「{display_name}」吗？",
            default_confirm=False,
        ):
            return
        self._queue_manager.remove_task(task.id)
        self._queue_manager.save()
        self._refresh_table()

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
            self._task_count_label.setText("")
            self._total_label.setText("")
            self._progress.reset()

    def _on_queue_finished(self):
        self._on_queue_stopped()
        self._current_label.setText("队列完成")
        self._progress.set_finished("所有任务已完成")
        QApplication.beep()

    def _on_queue_stopped(self):
        self._running = False
        self._btn_start.setEnabled(True)
        self._btn_clear.setEnabled(True)
        self._update_cancel_button_state()

    def refresh(self):
        self._refresh_table()
        self._sync_selected_task_details()

    def stop(self):
        self._running = False
        if self._worker:
            self._worker.cancel()
            self._worker.wait(3000)
