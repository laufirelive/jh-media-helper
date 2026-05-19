# src/gui/task_panels/combat_audio_panel.py
import os
import tempfile

import shutil

from PyQt6.QtCore import QEvent, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from src.core.config import CombatAudioConfig, TaskType
from src.core.preview_cache import (
    PreviewCacheSession,
    build_base_audio_cache_key,
    build_mix_preview_cache_key,
)
from src.core.processors import combat_audio
from src.gui.components.audio_player import AudioPlayerBar
from src.gui.components.file_selector import FileSelector
from src.gui.components.preview_start_cell import PreviewStartCell
from src.gui.task_panels.base_panel import BaseTaskPanel

_MEDIA_FILTER = "媒体文件 (*.mp4 *.mkv *.mov *.avi *.aac *.mp3 *.wav *.flac);;所有文件 (*)"
_SUBTITLE_FILTER = "字幕文件 (*.srt *.ass);;所有文件 (*)"


class CombatAudioPanel(BaseTaskPanel):
    preview_enabled_changed = pyqtSignal(bool)

    def __init__(
        self,
        preview_cache: PreviewCacheSession | None = None,
        parent=None,
    ):
        self._input_streams: list[combat_audio.AudioStreamInfo] = []
        self._bg_files: list[combat_audio.AudioFileInfo] = []
        self._is_pure_audio = False
        self._input_duration = 0.0
        self._preview_start_ms = 0
        self._preview_temp_dir: str | None = None
        self._preview_cache = preview_cache
        self._secondary_video_paths: list[str] = []
        self._subtitle_path: str | None = None
        self._mkvmerge_path: str | None = None
        self._mux_backend = "auto"
        super().__init__(parent, init_layout=False)
        self._init_custom_layout()

    # --- Abstract method stubs (not used since init_layout=False) ---
    def _build_left_panel(self, layout):
        pass

    def _build_settings_panel(self, layout):
        pass

    # --- Custom 4-zone layout ---

    def _init_custom_layout(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(20, 20, 20, 20)
        main.setSpacing(12)

        # Upper zone: file selectors (left) + params (right)
        upper = QHBoxLayout()
        upper.setSpacing(16)
        self._build_upper_left(upper)
        self._build_upper_right(upper)
        main.addLayout(upper)

        # Middle zone: 表格区纵向可伸展，贴近下方播放器；底部不再 addStretch，避免空白堆在进度条下
        self._build_middle_zone(main)

        # Lower zone: progress
        main.addWidget(self._progress)

        # Connect signals for preview button auto-enable
        self._track_radio_group.buttonClicked.connect(self._on_selected_track_changed)
        self._bg_table.selectionModel().selectionChanged.connect(lambda *_: self._emit_preview_state())
        self._update_param_states()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_info_group_height_with_output()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_info_group_height_with_output()

    def _sync_info_group_height_with_output(self) -> None:
        """左侧「文件信息」高度与右侧「输出设置」一致，便于与右栏区块上下沿对齐。"""
        og = getattr(self, "_out_group", None)
        ig = getattr(self, "_info_group", None)
        if og is None or ig is None:
            return
        h = og.height()
        if h <= 0:
            h = og.sizeHint().height()
        if h > 0:
            ig.setFixedHeight(h)

    def _build_upper_left(self, parent_layout: QHBoxLayout):
        left = QVBoxLayout()
        left.setSpacing(10)

        self._input_selector = FileSelector(
            label="输入视频/音频:",
            placeholder="选择文件...",
            dialog_mode="file",
            file_filter=_MEDIA_FILTER,
        )
        self._input_selector.path_changed.connect(self._on_input_changed)
        left.addWidget(self._input_selector)

        self._audio_dir_selector = FileSelector(
            label="音频目录:",
            placeholder="选择背景音乐文件夹...",
            dialog_mode="directory",
        )
        self._audio_dir_selector.path_changed.connect(self._on_audio_dir_changed)
        left.addWidget(self._audio_dir_selector)

        self._info_group = QGroupBox("文件信息")
        info_layout = QVBoxLayout(self._info_group)
        self._info_label = QLabel("未选择文件")
        self._info_label.setStyleSheet("color: gray;")
        # 高度与右侧「输出设置」拉齐后，长文案在框内换行
        self._info_label.setWordWrap(True)
        info_layout.addWidget(self._info_label)
        left.addWidget(self._info_group)

        self._build_secondary_video_group(left)

        left.addStretch()
        parent_layout.addLayout(left, 2)

    def _build_upper_right(self, parent_layout: QHBoxLayout):
        right = QVBoxLayout()
        right.setSpacing(16)

        # Mix params group
        mix_group = QGroupBox("混音参数")
        mix_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        mix_layout = QVBoxLayout(mix_group)
        mix_layout.setSpacing(12)

        self._mix_checkbox = QCheckBox("混合原始音轨")
        self._mix_checkbox.setChecked(True)
        self._mix_checkbox.toggled.connect(self._on_mix_toggled)
        mix_layout.addWidget(self._mix_checkbox)

        thread_row = QHBoxLayout()
        thread_row.addWidget(QLabel("并行线程数"))
        self._thread_spin = QSpinBox()
        self._thread_spin.setRange(1, 16)
        self._thread_spin.setValue(1)
        thread_row.addWidget(self._thread_spin, 1)
        mix_layout.addLayout(thread_row)

        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("原视频响度"))
        self._volume_spin = QDoubleSpinBox()
        self._volume_spin.setRange(0.0, 1.0)
        self._volume_spin.setSingleStep(0.1)
        self._volume_spin.setValue(0.6)
        vol_row.addWidget(self._volume_spin, 1)
        mix_layout.addLayout(vol_row)

        right.addWidget(mix_group)

        # 保留引用：与左侧「文件信息」做等高对齐
        self._out_group = QGroupBox("输出设置")
        out_group = self._out_group
        out_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        out_layout = QVBoxLayout(out_group)
        out_layout.setSpacing(12)

        self._boxed_checkbox = QCheckBox("封装为 MKV")
        self._boxed_checkbox.toggled.connect(self._update_param_states)
        out_layout.addWidget(self._boxed_checkbox)

        subtitle_row = QHBoxLayout()
        subtitle_row.setSpacing(6)
        self._subtitle_selector = FileSelector(
            label="字幕文件:",
            placeholder="可选，仅封装 MKV 时使用",
            dialog_mode="file",
            file_filter=_SUBTITLE_FILTER,
        )
        self._subtitle_selector.path_changed.connect(self._on_subtitle_changed)
        subtitle_row.addWidget(self._subtitle_selector, 1)

        self._clear_subtitle_btn = QPushButton("清空")
        self._clear_subtitle_btn.clicked.connect(self._clear_subtitle)
        subtitle_row.addWidget(self._clear_subtitle_btn)
        out_layout.addLayout(subtitle_row)

        self._output_selector = FileSelector(
            label="输出目录:",
            placeholder="与输入文件同级",
            dialog_mode="directory",
        )
        out_layout.addWidget(self._output_selector)

        right.addWidget(out_group)
        right.addStretch()
        parent_layout.addLayout(right, 1)

    def _build_secondary_video_group(self, parent_layout: QVBoxLayout) -> None:
        self._secondary_group = QGroupBox("副视频（仅封装 MKV 时可用）")
        self._secondary_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        group_layout = QVBoxLayout(self._secondary_group)
        group_layout.setSpacing(6)

        self._secondary_list_widget = QWidget()
        self._secondary_list_layout = QVBoxLayout(self._secondary_list_widget)
        self._secondary_list_layout.setContentsMargins(0, 0, 0, 0)
        self._secondary_list_layout.setSpacing(4)

        self._secondary_scroll = QScrollArea()
        self._secondary_scroll.setWidgetResizable(True)
        self._secondary_scroll.setMaximumHeight(160)
        self._secondary_scroll.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        self._secondary_scroll.setWidget(self._secondary_list_widget)
        group_layout.addWidget(self._secondary_scroll)

        button_row = QHBoxLayout()
        button_row.setSpacing(6)
        self._add_secondary_btn = QPushButton("添加副视频")
        self._add_secondary_btn.clicked.connect(self._add_secondary_video)
        button_row.addWidget(self._add_secondary_btn)

        self._clear_secondary_btn = QPushButton("清空")
        self._clear_secondary_btn.clicked.connect(self._clear_secondary_videos)
        button_row.addWidget(self._clear_secondary_btn)
        button_row.addStretch()
        group_layout.addLayout(button_row)

        parent_layout.addWidget(self._secondary_group)
        self._refresh_secondary_videos()
        self._secondary_group.setEnabled(False)

    # --- Middle zone ---

    def _build_middle_zone(self, parent_layout: QVBoxLayout):
        # 包裹一层并给 stretch=1，使双表占据「顶部设置区」与「播放器」之间的全部剩余高度
        self._tables_host = QWidget()
        self._tables_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        mid = QHBoxLayout(self._tables_host)
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(12)
        self._build_input_tracks_table(mid)
        self._build_bg_music_table(mid)
        parent_layout.addWidget(self._tables_host, 1)

        try:
            self._player = AudioPlayerBar(preview_cache=self._preview_cache)
        except TypeError as exc:
            message = str(exc)
            if "preview_cache" not in message or "unexpected keyword argument" not in message:
                raise
            self._player = AudioPlayerBar()
        parent_layout.addWidget(self._player, 0)

    def _build_input_tracks_table(self, parent_layout: QHBoxLayout):
        group = QGroupBox("输入音轨")
        group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(group)
        self._tracks_table = QTableWidget(0, 7)
        self._tracks_table.setHorizontalHeaderLabels(["", "索引", "编码", "试听起点", "采样率", "语言", ""])
        self._tracks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._tracks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tracks_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._tracks_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._tracks_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._tracks_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self._tracks_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self._tracks_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._tracks_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tracks_table.verticalHeader().setVisible(False)
        self._tracks_table.setMinimumHeight(160)
        self._tracks_table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self._tracks_table, 1)

        self._track_play_buttons: list[QPushButton] = []
        self._track_radio_group = QButtonGroup(self)

        parent_layout.addWidget(group, 1)

    def _build_bg_music_table(self, parent_layout: QHBoxLayout):
        group = QGroupBox("背景音乐")
        group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(group)
        self._bg_table = QTableWidget(0, 4)
        self._bg_table.setHorizontalHeaderLabels(["序号", "文件名", "时长", ""])
        self._bg_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._bg_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._bg_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._bg_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._bg_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._bg_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._bg_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._bg_table.verticalHeader().setVisible(True)
        self._bg_table.verticalHeader().setSectionsMovable(True)
        self._bg_table.verticalHeader().sectionMoved.connect(self._on_bg_row_moved)
        self._bg_table.setDragDropMode(QTableWidget.DragDropMode.InternalMove)
        self._bg_table.viewport().installEventFilter(self)
        self._bg_table.setMinimumHeight(160)
        self._bg_table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self._bg_table, 1)

        self._bg_play_buttons: list[QPushButton] = []

        parent_layout.addWidget(group, 1)

    # --- Signal handlers ---

    def _on_input_changed(self, path: str):
        self._preview_start_ms = 0
        if not path or not os.path.exists(path):
            self._input_streams = []
            self._is_pure_audio = False
            self._input_duration = 0.0
            self._info_label.setText("未选择文件")
            self._refresh_tracks_table()
            self._update_param_states()
            self._emit_preview_state()
            return

        self._is_pure_audio = combat_audio.is_pure_audio(path)
        self._input_duration = combat_audio.probe_duration(path)

        if self._is_pure_audio:
            ext = os.path.splitext(path)[1].upper().lstrip(".")
            self._input_streams = [combat_audio.AudioStreamInfo(
                index=0, audio_position=0, codec=ext, sample_rate=0, channels=0, channel_layout="", language=None,
            )]
        else:
            self._input_streams = combat_audio.probe_audio_streams(path)

        dur_str = self._format_duration(self._input_duration)
        file_type = "纯音频" if self._is_pure_audio else os.path.splitext(path)[1].upper().lstrip(".")
        self._info_label.setText(
            f"类型: {file_type}\n时长: {dur_str}\n音轨数: {len(self._input_streams)}"
        )

        self._refresh_tracks_table()
        self._update_param_states()
        self._emit_preview_state()

    def _on_audio_dir_changed(self, path: str):
        if not path or not os.path.isdir(path):
            self._bg_files = []
            self._refresh_bg_table()
            self._emit_preview_state()
            return

        self._bg_files = combat_audio.scan_audio_dir(path)
        # Probe durations
        for f in self._bg_files:
            f.duration = combat_audio.probe_duration(f.path)
        self._refresh_bg_table()
        self._update_info_bg_count()
        self._emit_preview_state()

    def _on_mix_toggled(self, checked: bool):
        self._volume_spin.setEnabled(checked)
        self._update_param_states()
        self._emit_preview_state()

    def _on_selected_track_changed(self, *_args):
        self._refresh_preview_start_cells()
        self._emit_preview_state()

    def _on_preview_start_changed(self, audio_position: int, value_ms: int) -> None:
        if audio_position != self._track_radio_group.checkedId():
            return
        clamped_value = max(0, min(value_ms, self._input_duration_ms()))
        if self._preview_start_ms == clamped_value:
            return
        self._preview_start_ms = clamped_value
        self._refresh_preview_start_cells()

    def _update_param_states(self):
        """Update parameter enable/disable states based on current selections."""
        input_path = self._input_selector.path()
        has_valid_input = bool(input_path) and os.path.exists(input_path)
        is_audio = self._is_pure_audio
        is_video_input = has_valid_input and not is_audio
        has_audio_streams = len(self._input_streams) > 0

        # 无音轨视频无法与原片混音：自动关闭选项并禁用，避免误选
        if not is_audio and not has_audio_streams:
            self._mix_checkbox.setChecked(False)
            self._mix_checkbox.setEnabled(False)
            self._mix_checkbox.setToolTip("当前输入无音轨，仅支持将背景音乐裁剪对齐片长，无法与原片混音")
        else:
            self._mix_checkbox.setEnabled(True)
            self._mix_checkbox.setToolTip("")

        mix_on = self._mix_checkbox.isChecked()
        self._volume_spin.setEnabled(mix_on)

        # Boxed only available for video input
        self._boxed_checkbox.setEnabled(is_video_input)
        if not is_video_input:
            self._boxed_checkbox.setChecked(False)

        self._secondary_group.setEnabled(is_video_input and self._boxed_checkbox.isChecked())
        if hasattr(self, "_subtitle_selector") and hasattr(self, "_clear_subtitle_btn"):
            subtitle_enabled = is_video_input and self._boxed_checkbox.isChecked()
            self._subtitle_selector.setEnabled(subtitle_enabled)
            self._clear_subtitle_btn.setEnabled(subtitle_enabled)

    def _emit_preview_state(self):
        self.preview_enabled_changed.emit(self.get_preview_btn_enabled())

    def _update_info_bg_count(self):
        text = self._info_label.text()
        lines = text.split("\n")
        # Remove old bg count line if present
        lines = [l for l in lines if not l.startswith("背景音乐:")]
        lines.append(f"背景音乐: {len(self._bg_files)} 个文件")
        self._info_label.setText("\n".join(lines))

    # --- Table refresh ---

    def _refresh_tracks_table(self):
        selected_audio_position = self._track_radio_group.checkedId()
        self._tracks_table.setRowCount(0)
        self._track_play_buttons.clear()
        # Clear old radio buttons from group
        for btn in self._track_radio_group.buttons():
            self._track_radio_group.removeButton(btn)

        for stream in self._input_streams:
            row = self._tracks_table.rowCount()
            self._tracks_table.insertRow(row)

            # Radio button column
            radio = QRadioButton()
            self._track_radio_group.addButton(radio, stream.audio_position)
            radio_widget = QWidget()
            radio_layout = QHBoxLayout(radio_widget)
            radio_layout.addWidget(radio)
            radio_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            radio_layout.setContentsMargins(0, 0, 0, 0)
            self._tracks_table.setCellWidget(row, 0, radio_widget)

            self._tracks_table.setItem(row, 1, QTableWidgetItem(f"#{stream.index}"))
            self._tracks_table.setItem(row, 2, QTableWidgetItem(stream.codec.upper()))

            preview_cell = PreviewStartCell(self._tracks_table)
            preview_cell.set_duration_ms(self._input_duration_ms())
            preview_cell.set_value_ms(self._preview_start_ms)
            preview_cell._slider.valueChanged.connect(
                lambda value, audio_position=stream.audio_position: self._on_preview_start_changed(audio_position, value)
            )
            self._tracks_table.setCellWidget(row, 3, preview_cell)

            sr = f"{stream.sample_rate // 1000}kHz" if stream.sample_rate else "?"
            self._tracks_table.setItem(row, 4, QTableWidgetItem(sr))

            language = self._language_label(stream)
            self._tracks_table.setItem(row, 5, QTableWidgetItem(language))

            # Play button column
            btn = QPushButton("\u25B6")
            btn.setFixedWidth(32)
            if self._is_pure_audio:
                btn.clicked.connect(
                    lambda checked, p=self._input_selector.path(), si=stream.index, n=stream.codec:
                        self._play_input_track_preview(p, si, f"输入 {n}")
                )
            else:
                btn.clicked.connect(
                    lambda checked, p=self._input_selector.path(), si=stream.audio_position, n=f"输入 #{stream.index} {stream.codec}":
                        self._play_input_track_preview(p, si, n)
                )
            self._tracks_table.setCellWidget(row, 6, btn)
            self._track_play_buttons.append(btn)

        restored_radio = None
        if selected_audio_position >= 0:
            restored_radio = self._track_radio_group.button(selected_audio_position)

        # Fall back to the first track only when the previous selection no longer exists.
        if restored_radio:
            restored_radio.setChecked(True)
        elif self._input_streams:
            first_radio = self._track_radio_group.button(self._input_streams[0].audio_position)
            if first_radio:
                first_radio.setChecked(True)

        self._refresh_preview_start_cells()

    def _refresh_preview_start_cells(self) -> None:
        selected_audio_position = self._track_radio_group.checkedId()
        duration_ms = self._input_duration_ms()

        for row, stream in enumerate(self._input_streams):
            preview_cell = self._tracks_table.cellWidget(row, 3)
            if not isinstance(preview_cell, PreviewStartCell):
                continue
            preview_cell.set_duration_ms(duration_ms)
            preview_cell.set_value_ms(self._preview_start_ms)
            preview_cell.set_active(stream.audio_position == selected_audio_position)

    def _refresh_bg_table(self):
        self._bg_table.setRowCount(0)
        self._bg_play_buttons.clear()

        for i, f in enumerate(self._bg_files):
            row = self._bg_table.rowCount()
            self._bg_table.insertRow(row)

            num_item = QTableWidgetItem(f"{i + 1:02d}")
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._bg_table.setItem(row, 0, num_item)

            name_item = QTableWidgetItem(f.filename)
            name_item.setData(Qt.ItemDataRole.UserRole, f.path)
            self._bg_table.setItem(row, 1, name_item)

            dur_str = self._format_duration(f.duration)
            self._bg_table.setItem(row, 2, QTableWidgetItem(dur_str))

            btn = QPushButton("\u25B6")
            btn.setFixedWidth(32)
            btn.clicked.connect(
                lambda checked, path=f.path, name=f.filename:
                    self._player.play_file(path, name)
            )
            self._bg_table.setCellWidget(row, 3, btn)
            self._bg_play_buttons.append(btn)

    def _on_bg_row_moved(self, logical: int, old_visual: int, new_visual: int):
        """Internal row-move signal fires before drop fully settles; defer reconciliation to drop handling."""
        return

    def eventFilter(self, obj, event):
        viewport = getattr(self._bg_table, "viewport", lambda: None)()
        if obj is viewport and event.type() == QEvent.Type.Drop:
            QTimer.singleShot(0, self._reconcile_bg_order_after_drop)
        return super().eventFilter(obj, event)

    def _reconcile_bg_order_after_drop(self) -> None:
        """Rebuild `_bg_files` from the current table row order after internal drop."""
        if self._bg_table.rowCount() != len(self._bg_files):
            self._refresh_bg_table()
            return

        by_path = {item.path: item for item in self._bg_files}
        reordered = []
        header = getattr(self._bg_table, "verticalHeader", lambda: None)()
        for visual_row in range(self._bg_table.rowCount()):
            logical_row = header.logicalIndex(visual_row) if header is not None else visual_row
            item = self._bg_table.item(logical_row, 1)
            path = item.data(Qt.ItemDataRole.UserRole) if item else None
            if not path or path not in by_path:
                self._refresh_bg_table()
                return
            reordered.append(by_path[path])

        if [item.path for item in reordered] == [item.path for item in self._bg_files]:
            return

        self._bg_files = reordered
        self._refresh_bg_table()

    def _add_secondary_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择副视频", "", _MEDIA_FILTER)
        if not path:
            return
        self._secondary_video_paths.append(path)
        self._refresh_secondary_videos()

    def _clear_secondary_videos(self) -> None:
        self._secondary_video_paths.clear()
        self._refresh_secondary_videos()

    def _on_subtitle_changed(self, path: str) -> None:
        self._subtitle_path = path or None

    def _clear_subtitle(self) -> None:
        self._subtitle_selector.set_path("")

    def _move_secondary_video(self, index: int, delta: int) -> None:
        new_index = index + delta
        if index < 0 or index >= len(self._secondary_video_paths):
            return
        if new_index < 0 or new_index >= len(self._secondary_video_paths):
            return

        self._secondary_video_paths[index], self._secondary_video_paths[new_index] = (
            self._secondary_video_paths[new_index],
            self._secondary_video_paths[index],
        )
        self._refresh_secondary_videos()

    def _remove_secondary_video(self, index: int) -> None:
        if index < 0 or index >= len(self._secondary_video_paths):
            return
        del self._secondary_video_paths[index]
        self._refresh_secondary_videos()

    def _refresh_secondary_videos(self) -> None:
        while self._secondary_list_layout.count():
            item = self._secondary_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not self._secondary_video_paths:
            empty_label = QLabel("未添加副视频")
            empty_label.setStyleSheet("color: gray;")
            self._secondary_list_layout.addWidget(empty_label)
            return

        for index, path in enumerate(self._secondary_video_paths):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)

            idx_label = QLabel(f"{index + 1:02d}")
            idx_label.setFixedWidth(24)
            idx_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_layout.addWidget(idx_label)

            name_label = QLabel(os.path.basename(path) or path)
            name_label.setToolTip(path)
            row_layout.addWidget(name_label, 1)

            up_btn = QPushButton("↑")
            up_btn.setFixedWidth(28)
            up_btn.setEnabled(index > 0)
            up_btn.clicked.connect(lambda checked=False, i=index: self._move_secondary_video(i, -1))
            row_layout.addWidget(up_btn)

            down_btn = QPushButton("↓")
            down_btn.setFixedWidth(28)
            down_btn.setEnabled(index < len(self._secondary_video_paths) - 1)
            down_btn.clicked.connect(lambda checked=False, i=index: self._move_secondary_video(i, 1))
            row_layout.addWidget(down_btn)

            remove_btn = QPushButton("移除")
            remove_btn.setFixedWidth(48)
            remove_btn.clicked.connect(lambda checked=False, i=index: self._remove_secondary_video(i))
            row_layout.addWidget(remove_btn)

            self._secondary_list_layout.addWidget(row_widget)

    # --- Preview mix ---

    def get_preview_btn_enabled(self) -> bool:
        """Check if preview mix button should be enabled."""
        if not self._mix_checkbox.isChecked():
            return False
        if self._track_radio_group.checkedId() < 0:
            return False
        if not self._bg_table.selectionModel().hasSelection():
            return False
        return True

    def preview_mix(self) -> None:
        """Generate and play a 5-second preview mix."""
        if not self.get_preview_btn_enabled():
            return

        input_path = self._input_selector.path()
        stream_idx = self._track_radio_group.checkedId()
        bg_row = self._bg_table.currentRow()
        if bg_row < 0 or bg_row >= len(self._bg_files):
            return
        bg_path = self._bg_files[bg_row].path
        bg_duration = float(getattr(self._bg_files[bg_row], "duration", 0.0) or 0.0)
        volume = self._volume_spin.value()
        preview_cache = getattr(self, "_preview_cache", None)
        preview_start_ms = max(0, int(getattr(self, "_preview_start_ms", 0)))
        preview_start_seconds = preview_start_ms / 1000.0
        preview_duration_seconds = combat_audio.PREVIEW_DURATION_SECONDS
        mix_base_start_seconds = 0.0 if not self._is_pure_audio else preview_start_seconds
        mix_bg_start_seconds = preview_start_seconds
        if bg_duration > 0:
            mix_bg_start_seconds = preview_start_seconds % bg_duration

        # Clean up previous temp preview outputs before generating a new fallback preview.
        self._cleanup_preview_temp()
        if preview_cache is not None:
            self._preview_temp_dir = None
            preview_path = preview_cache.get_cache_path(
                build_mix_preview_cache_key(
                    input_path,
                    stream_idx,
                    bg_path,
                    volume,
                    start_ms=preview_start_ms,
                )
            )
            if CombatAudioPanel._is_usable_preview_file(preview_path):
                self._player.play_preview_file(preview_path, "试听混合")
                return
            if os.path.exists(preview_path):
                CombatAudioPanel._discard_stale_preview_file(preview_path)

            base_audio = input_path
            if not self._is_pure_audio:
                base_audio = preview_cache.get_cache_path(
                    build_base_audio_cache_key(
                        input_path,
                        stream_idx,
                        start_ms=preview_start_ms,
                    )
                )
                if not os.path.exists(base_audio):
                    cmd = combat_audio.build_extract_command(
                        input_path,
                        stream_idx,
                        base_audio,
                        start_seconds=preview_start_seconds,
                        duration_seconds=preview_duration_seconds,
                    )
                    err = combat_audio.run_ffmpeg_command(
                        cmd, timeout=30, default_message="试听混合失败：提取原始音轨时出错"
                    )
                    if err is not None:
                        QMessageBox.critical(self, "错误", err)
                        return
                elif not CombatAudioPanel._is_usable_preview_file(base_audio):
                    CombatAudioPanel._discard_stale_preview_file(base_audio)
                    cmd = combat_audio.build_extract_command(
                        input_path,
                        stream_idx,
                        base_audio,
                        start_seconds=preview_start_seconds,
                        duration_seconds=preview_duration_seconds,
                    )
                    err = combat_audio.run_ffmpeg_command(
                        cmd, timeout=30, default_message="试听混合失败：提取原始音轨时出错"
                    )
                    if err is not None:
                        QMessageBox.critical(self, "错误", err)
                        return
        else:
            self._preview_temp_dir = tempfile.mkdtemp(prefix="jh_preview_")

            # If video input, extract selected audio track first.
            if not self._is_pure_audio:
                base_audio = os.path.join(self._preview_temp_dir, "base.aac")
                cmd = combat_audio.build_extract_command(
                    input_path,
                    stream_idx,
                    base_audio,
                    start_seconds=preview_start_seconds,
                    duration_seconds=preview_duration_seconds,
                )
                err = combat_audio.run_ffmpeg_command(
                    cmd, timeout=30, default_message="试听混合失败：提取原始音轨时出错"
                )
                if err is not None:
                    QMessageBox.critical(self, "错误", err)
                    self._cleanup_preview_temp()
                    return
            else:
                base_audio = input_path

            preview_path = os.path.join(self._preview_temp_dir, "preview.aac")
        cmd = combat_audio.build_preview_command(
            base_audio,
            bg_path,
            volume,
            preview_path,
            start_seconds=preview_start_seconds,
            base_start_seconds=mix_base_start_seconds,
            bg_start_seconds=mix_bg_start_seconds,
            duration_seconds=preview_duration_seconds,
        )
        err = combat_audio.run_ffmpeg_command(
            cmd, timeout=30, default_message="试听混合失败：生成预览音频时出错"
        )
        if err is not None:
            QMessageBox.critical(self, "错误", err)
            self._cleanup_preview_temp()
            return

        if os.path.exists(preview_path):
            self._player.play_preview_file(preview_path, "试听混合")
        else:
            QMessageBox.critical(self, "错误", "试听混合失败：未生成预览音频")
            self._cleanup_preview_temp()

    @staticmethod
    def _is_usable_preview_file(file_path: str) -> bool:
        if not os.path.isfile(file_path):
            return False
        try:
            if os.path.getsize(file_path) <= 0:
                return False
            if not os.access(file_path, os.R_OK):
                return False
            return bool(combat_audio.probe_audio_streams(file_path))
        except OSError:
            return False

    @staticmethod
    def _discard_stale_preview_file(file_path: str) -> None:
        try:
            if os.path.isdir(file_path):
                shutil.rmtree(file_path)
            else:
                os.remove(file_path)
        except OSError:
            pass

    def _play_input_track_preview(self, file_path: str, stream_index: int, display_name: str) -> None:
        err = self._player.play_stream(
            file_path,
            stream_index,
            display_name,
            preview_start_ms=self._preview_start_ms,
        )
        if err is not None:
            QMessageBox.critical(self, "错误", err)

    def _play_input_stream_preview(self, file_path: str, stream_index: int, display_name: str) -> None:
        err = self._player.play_stream(
            file_path,
            stream_index,
            display_name,
            preview_start_ms=self._preview_start_ms,
        )
        if err is not None:
            QMessageBox.critical(self, "错误", err)

    # --- Helpers ---

    @staticmethod
    def _format_duration(seconds: float) -> str:
        s = int(seconds)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _input_duration_ms(self) -> int:
        return max(0, int(self._input_duration * 1000))

    @staticmethod
    def _language_label(stream: combat_audio.AudioStreamInfo) -> str:
        language = (stream.language or "").strip()
        return language if language else "und"

    # --- BaseTaskPanel abstract methods ---

    def validate(self) -> tuple[bool, int, str | None]:
        input_path = self._input_selector.path()
        if not input_path:
            return False, 0, "请先选择输入文件"
        audio_dir = self._audio_dir_selector.path()
        if not audio_dir:
            return False, 0, "请先选择音频目录"

        config = self._build_combat_config()
        if config is None:
            return False, 0, "配置无效"

        ok, err = combat_audio.validate(config)
        if not ok:
            return False, 0, err
        audio_count = len(self._bg_files) if self._bg_files else len(combat_audio.scan_audio_dir(audio_dir))
        if config.boxed and not self._is_pure_audio:
            return True, 1 + len(config.secondary_video_paths or []), None
        return True, audio_count, None

    def build_config(self) -> CombatAudioConfig | None:
        return self._build_combat_config()

    def get_task_type(self) -> TaskType:
        return TaskType.COMBAT_AUDIO

    def set_mux_settings(self, *, mkvmerge_path: str | None, mux_backend: str = "auto") -> None:
        self._mkvmerge_path = mkvmerge_path
        self._mux_backend = mux_backend

    def _build_combat_config(self) -> CombatAudioConfig | None:
        input_path = self._input_selector.path()
        audio_dir = self._audio_dir_selector.path()
        if not input_path or not audio_dir:
            return None

        selected_track = self._track_radio_group.checkedId()
        if selected_track < 0:
            selected_track = 0

        self._reconcile_bg_order_after_drop()
        audio_order = [f.filename for f in self._bg_files]

        # 与界面逻辑一致：无音轨视频禁止混原片（防止旧配置或异常状态下仍上报 mix_enabled）
        mix_on = self._mix_checkbox.isChecked()
        if not self._is_pure_audio and len(self._input_streams) == 0:
            mix_on = False

        boxed = self._boxed_checkbox.isChecked()
        secondary_video_paths = list(self._secondary_video_paths) if boxed and not self._is_pure_audio else []
        subtitle_path = self._subtitle_selector.path() or None
        if not boxed or self._is_pure_audio:
            subtitle_path = None

        return CombatAudioConfig(
            input_path=input_path,
            audio_dir=audio_dir,
            output_dir=self._output_selector.path() or None,
            mix_enabled=mix_on,
            volume=self._volume_spin.value(),
            boxed=boxed,
            thread_count=self._thread_spin.value(),
            audio_stream_index=selected_track,
            audio_order=audio_order,
            secondary_video_paths=secondary_video_paths,
            subtitle_path=subtitle_path,
            mkvmerge_path=self._mkvmerge_path,
            mux_backend=self._mux_backend,
        )

    def _cleanup_preview_temp(self):
        if self._preview_temp_dir and os.path.isdir(self._preview_temp_dir):
            shutil.rmtree(self._preview_temp_dir, ignore_errors=True)
            self._preview_temp_dir = None

    def cleanup(self):
        """Clean up player and preview temp files."""
        self._player.cleanup()
        self._cleanup_preview_temp()
