import os

from PyQt6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.config import TaskType
from src.core.data_dir import get_queue_path
from src.core.encoder_registry import EncoderRegistry
from src.core.processors.pic_seq import _resolve_output_path
from src.core.queue_manager import QueueManager
from src.core.queue_task import QueueTask
from src.gui.components.action_bar import ActionBar
from src.gui.confirm_dialog import confirm_action
from src.gui.queue_tab import QueueTab
from src.gui.settings_tab import SettingsTab
from src.gui.task_panels.base_panel import BaseTaskPanel
from src.gui.task_panels.combat_audio_panel import CombatAudioPanel
from src.gui.task_panels.pic_seq_panel import PicSeqPanel
from src.worker.ffmpeg_worker import FFmpegWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("jh-media-helper")
        self.setMinimumSize(800, 550)
        self.resize(1100, 750)

        self._encoder_registry = EncoderRegistry()
        self._queue_manager = QueueManager(get_queue_path())
        self._queue_manager.load()
        self._worker: FFmpegWorker | None = None
        self._running_task_display_name = ""

        self._init_ui()
        self._connect_signals()
        self._check_queue_recovery()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        # 与 QueueTab 内列表与底部按钮的间距一致：仅任务面板底部操作条与 Tab 内容区分开
        outer.setSpacing(12)

        self._tabs = QTabWidget()
        # macOS 下 tab 内容区（pane）默认可能为浅白底，与左侧区域不一致
        self._tabs.setStyleSheet(
            """
            QTabWidget::pane {
                border: none;
                background: palette(window);
            }
            """
        )
        outer.addWidget(self._tabs)

        # PicSeq tab
        self._pic_seq_panel = PicSeqPanel(self._encoder_registry)
        self._tabs.addTab(self._pic_seq_panel, "图片序列转视频")

        # CombatAudio tab
        self._combat_panel = CombatAudioPanel()
        self._tabs.addTab(self._combat_panel, "音视频混合")

        # Queue tab
        self._queue_tab = QueueTab(self._queue_manager, self._encoder_registry)
        self._tabs.addTab(self._queue_tab, f"批量队列 ({len(self._queue_manager.tasks)})")

        # Settings tab
        self._settings_tab = SettingsTab()
        self._tabs.addTab(self._settings_tab, "设置")

        # Bottom action bar（外包一层底边距，避免贴窗口底；队列/设置页不显示该区域）
        self._action_bar = ActionBar()
        self._btn_cancel = self._action_bar.add_button("取消", role="secondary", enabled=False)
        self._btn_enqueue = self._action_bar.add_button("加入队列", role="secondary")
        self._btn_start = self._action_bar.add_button("开始处理", role="primary")
        self._btn_preview = self._action_bar.add_button("试听混合", role="secondary", enabled=False)
        self._action_bar_wrap = QWidget()
        _abl = QVBoxLayout(self._action_bar_wrap)
        _abl.setContentsMargins(0, 0, 0, 20)
        _abl.setSpacing(0)
        _abl.addWidget(self._action_bar)
        outer.addWidget(self._action_bar_wrap)

        self._tabs.currentChanged.connect(self._on_tab_changed)

    def _connect_signals(self):
        self._btn_start.clicked.connect(self._on_start)
        self._btn_cancel.clicked.connect(self._on_cancel)
        self._btn_enqueue.clicked.connect(self._on_enqueue)
        self._btn_preview.clicked.connect(self._on_preview)
        self._queue_tab.task_count_changed.connect(self._update_queue_badge)
        self._combat_panel.preview_enabled_changed.connect(self._btn_preview.setEnabled)

    def _on_tab_changed(self, index: int):
        current_widget = self._tabs.widget(index)
        show = isinstance(current_widget, BaseTaskPanel)
        self._action_bar_wrap.setVisible(show)
        self._btn_preview.setVisible(isinstance(current_widget, CombatAudioPanel))

    def _on_preview(self):
        panel = self._get_active_panel()
        if isinstance(panel, CombatAudioPanel):
            panel.preview_mix()

    def _get_active_panel(self) -> BaseTaskPanel | None:
        widget = self._tabs.currentWidget()
        if isinstance(widget, BaseTaskPanel):
            return widget
        return None

    def _update_queue_badge(self, count: int):
        idx = self._tabs.indexOf(self._queue_tab)
        self._tabs.setTabText(idx, f"批量队列 ({count})")

    @staticmethod
    def _display_name_from_config(config) -> str:
        """从任务配置取简短展示名（用于取消确认文案）。"""
        input_dir = getattr(config, "input_dir", None)
        input_path = getattr(config, "input_path", None)
        path = input_dir or input_path
        if path:
            return os.path.basename(path.rstrip(os.sep)) or path
        return "当前任务"

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

        self._running_task_display_name = self._display_name_from_config(config)

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
        if not self._worker:
            return
        name = self._running_task_display_name or "当前任务"
        if not confirm_action(
            self,
            "确认取消",
            f"确定取消任务「{name}」吗？",
            default_confirm=False,
        ):
            return
        self._worker.cancel()
        # 等 worker 发出 error/finished（含「已取消」）后再由 _on_error 恢复「开始处理」
        self._btn_cancel.setEnabled(False)

    def _on_finished(self, output_path: str):
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._worker = None
        self._running_task_display_name = ""
        panel = self._get_active_panel()
        if panel:
            panel.on_finished(output_path)

    def _on_error(self, message: str):
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._worker = None
        self._running_task_display_name = ""
        # 用户主动取消不弹错误框
        if message != "已取消":
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

        # Resolve output path based on task type
        task_type = panel.get_task_type()
        if task_type == TaskType.PIC_SEQ:
            output_path = _resolve_output_path(config)
            input_path = config.input_dir
        elif task_type == TaskType.COMBAT_AUDIO:
            from src.core.processors.combat_audio import resolve_output_path as combat_resolve
            paths = combat_resolve(config, audio_count=count)
            output_path = paths[0] if paths else ""
            input_path = config.input_path
        else:
            output_path = ""
            input_path = ""

        task = QueueTask.create(
            task_type=task_type,
            config=config,
            input_path=input_path,
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
        self._combat_panel.cleanup()
        event.accept()
