from PyQt6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.data_dir import get_queue_path
from src.core.encoder_registry import EncoderRegistry
from src.core.processors.pic_seq import _resolve_output_path
from src.core.queue_manager import QueueManager
from src.core.queue_task import QueueTask
from src.gui.components.action_bar import ActionBar
from src.gui.queue_tab import QueueTab
from src.gui.settings_tab import SettingsTab
from src.gui.task_panels.base_panel import BaseTaskPanel
from src.gui.task_panels.pic_seq_panel import PicSeqPanel
from src.worker.ffmpeg_worker import FFmpegWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("jh-media-helper")
        self.setMinimumSize(800, 600)

        self._encoder_registry = EncoderRegistry()
        self._queue_manager = QueueManager(get_queue_path())
        self._queue_manager.load()
        self._worker: FFmpegWorker | None = None

        self._init_ui()
        self._connect_signals()
        self._check_queue_recovery()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._tabs = QTabWidget()
        outer.addWidget(self._tabs)

        # PicSeq tab
        self._pic_seq_panel = PicSeqPanel(self._encoder_registry)
        self._tabs.addTab(self._pic_seq_panel, "图片序列转视频")

        # Future: M2/M3 tabs will be added here

        # Queue tab
        self._queue_tab = QueueTab(self._queue_manager, self._encoder_registry)
        self._tabs.addTab(self._queue_tab, f"批量队列 ({len(self._queue_manager.tasks)})")

        # Settings tab
        self._settings_tab = SettingsTab()
        self._tabs.addTab(self._settings_tab, "设置")

        # Bottom action bar (centered)
        self._action_bar = ActionBar()
        self._btn_cancel = self._action_bar.add_button("取消", role="secondary", enabled=False)
        self._btn_enqueue = self._action_bar.add_button("加入队列", role="secondary")
        self._btn_start = self._action_bar.add_button("开始处理", role="primary")
        outer.addWidget(self._action_bar)

        self._tabs.currentChanged.connect(self._on_tab_changed)

    def _connect_signals(self):
        self._btn_start.clicked.connect(self._on_start)
        self._btn_cancel.clicked.connect(self._on_cancel)
        self._btn_enqueue.clicked.connect(self._on_enqueue)
        self._queue_tab.task_count_changed.connect(self._update_queue_badge)

    def _on_tab_changed(self, index: int):
        current_widget = self._tabs.widget(index)
        self._action_bar.setVisible(isinstance(current_widget, BaseTaskPanel))

    def _get_active_panel(self) -> BaseTaskPanel | None:
        widget = self._tabs.currentWidget()
        if isinstance(widget, BaseTaskPanel):
            return widget
        return None

    def _update_queue_badge(self, count: int):
        idx = self._tabs.indexOf(self._queue_tab)
        self._tabs.setTabText(idx, f"批量队列 ({count})")

    def _on_start(self):
        panel = self._get_active_panel()
        if panel is None:
            return
        ok, count, err = panel.validate()
        if not ok:
            QMessageBox.warning(self, "校验失败", err)
            return
        config = panel.build_config()
        if config is None:
            return

        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)

        self._worker = FFmpegWorker(
            task_type=panel.get_task_type(),
            config=config.to_dict(),
            encoder_registry=self._encoder_registry,
            total_frames=count,
        )
        self._worker.progress.connect(panel.on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_cancel(self):
        if self._worker:
            self._worker.cancel()
            self._worker = None
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)

    def _on_finished(self, output_path: str):
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._worker = None
        panel = self._get_active_panel()
        if panel:
            panel.on_finished(output_path)

    def _on_error(self, message: str):
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._worker = None
        QMessageBox.critical(self, "错误", message)

    def _on_enqueue(self):
        panel = self._get_active_panel()
        if panel is None:
            return
        ok, count, err = panel.validate()
        if not ok:
            QMessageBox.warning(self, "校验失败", err)
            return
        config = panel.build_config()
        if config is None:
            return

        output_path = _resolve_output_path(config)
        task = QueueTask.create(
            task_type=panel.get_task_type(),
            config=config,
            input_path=config.input_dir,
            output_path=output_path,
        )
        self._queue_manager.add_task(task)
        self._queue_manager.save()
        self._queue_tab.refresh()

    def _check_queue_recovery(self):
        pending = [t for t in self._queue_manager.tasks if t.status.value == "pending"]
        if not pending:
            return
        reply = QMessageBox.question(
            self,
            "队列恢复",
            f"发现 {len(pending)} 个未完成任务，是否继续执行？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Discard,
        )
        if reply == QMessageBox.StandardButton.Discard:
            self._queue_manager.clear_all()
            self._queue_manager.save()

    def closeEvent(self, event):
        if self._worker:
            self._worker.cancel()
            self._worker.wait(3000)
        self._queue_tab.stop()
        self._queue_manager.save()
        event.accept()
