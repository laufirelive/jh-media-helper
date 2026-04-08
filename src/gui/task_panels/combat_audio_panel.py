# src/gui/task_panels/combat_audio_panel.py
import os
import subprocess
import tempfile

import shutil

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.config import CombatAudioConfig, TaskType
from src.core.processors import combat_audio
from src.gui.components.audio_player import AudioPlayerBar
from src.gui.components.file_selector import FileSelector
from src.gui.task_panels.base_panel import BaseTaskPanel

_MEDIA_FILTER = "媒体文件 (*.mp4 *.mkv *.mov *.avi *.aac *.mp3 *.wav *.flac);;所有文件 (*)"


class CombatAudioPanel(BaseTaskPanel):
    preview_enabled_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        self._input_streams: list[combat_audio.AudioStreamInfo] = []
        self._bg_files: list[combat_audio.AudioFileInfo] = []
        self._is_pure_audio = False
        self._input_duration = 0.0
        self._preview_temp_dir: str | None = None
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

        # Middle zone: tables + player
        self._build_middle_zone(main)

        # Lower zone: progress
        main.addWidget(self._progress)

        main.addStretch()

        # Connect signals for preview button auto-enable
        self._track_radio_group.buttonClicked.connect(lambda _: self._emit_preview_state())
        self._bg_table.selectionModel().selectionChanged.connect(lambda *_: self._emit_preview_state())

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
        info_layout.addWidget(self._info_label)
        left.addWidget(self._info_group)

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

        # Output settings group
        out_group = QGroupBox("输出设置")
        out_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        out_layout = QVBoxLayout(out_group)
        out_layout.setSpacing(12)

        self._boxed_checkbox = QCheckBox("封装为 MKV")
        out_layout.addWidget(self._boxed_checkbox)

        self._output_selector = FileSelector(
            label="输出目录:",
            placeholder="与输入文件同级",
            dialog_mode="directory",
        )
        out_layout.addWidget(self._output_selector)

        right.addWidget(out_group)
        right.addStretch()
        parent_layout.addLayout(right, 1)

    # --- Middle zone ---

    def _build_middle_zone(self, parent_layout: QVBoxLayout):
        mid = QHBoxLayout()
        mid.setSpacing(12)
        self._build_input_tracks_table(mid)
        self._build_bg_music_table(mid)
        parent_layout.addLayout(mid)

        self._player = AudioPlayerBar()
        parent_layout.addWidget(self._player)

    def _build_input_tracks_table(self, parent_layout: QHBoxLayout):
        group = QGroupBox("输入音轨")
        layout = QVBoxLayout(group)
        self._tracks_table = QTableWidget(0, 6)
        self._tracks_table.setHorizontalHeaderLabels(["", "索引", "编码", "采样率", "声道", ""])
        self._tracks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._tracks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tracks_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._tracks_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._tracks_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._tracks_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self._tracks_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._tracks_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tracks_table.verticalHeader().setVisible(False)
        self._tracks_table.setMaximumHeight(150)
        layout.addWidget(self._tracks_table)

        self._track_play_buttons: list[QPushButton] = []
        self._track_radio_group = QButtonGroup(self)

        parent_layout.addWidget(group, 1)

    def _build_bg_music_table(self, parent_layout: QHBoxLayout):
        group = QGroupBox("背景音乐")
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
        self._bg_table.setMaximumHeight(200)
        layout.addWidget(self._bg_table)

        self._bg_play_buttons: list[QPushButton] = []

        parent_layout.addWidget(group, 1)

    # --- Signal handlers ---

    def _on_input_changed(self, path: str):
        if not path or not os.path.exists(path):
            self._input_streams = []
            self._is_pure_audio = False
            self._input_duration = 0.0
            self._info_label.setText("未选择文件")
            self._refresh_tracks_table()
            self._update_param_states()
            return

        self._is_pure_audio = combat_audio.is_pure_audio(path)
        self._input_duration = combat_audio.probe_duration(path)

        if self._is_pure_audio:
            ext = os.path.splitext(path)[1].upper().lstrip(".")
            self._input_streams = [combat_audio.AudioStreamInfo(
                index=0, codec=ext, sample_rate=0, channels=0, channel_layout="",
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

    def _on_audio_dir_changed(self, path: str):
        if not path or not os.path.isdir(path):
            self._bg_files = []
            self._refresh_bg_table()
            return

        self._bg_files = combat_audio.scan_audio_dir(path)
        # Probe durations
        for f in self._bg_files:
            f.duration = combat_audio.probe_duration(f.path)
        self._refresh_bg_table()
        self._update_info_bg_count()

    def _on_mix_toggled(self, checked: bool):
        self._volume_spin.setEnabled(checked)
        self._update_param_states()
        self._emit_preview_state()

    def _update_param_states(self):
        """Update parameter enable/disable states based on current selections."""
        is_audio = self._is_pure_audio
        mix_on = self._mix_checkbox.isChecked()

        self._volume_spin.setEnabled(mix_on)
        # Boxed only available for video input
        self._boxed_checkbox.setEnabled(not is_audio)
        if is_audio:
            self._boxed_checkbox.setChecked(False)

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
            self._track_radio_group.addButton(radio, stream.index)
            radio_widget = QWidget()
            radio_layout = QHBoxLayout(radio_widget)
            radio_layout.addWidget(radio)
            radio_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            radio_layout.setContentsMargins(0, 0, 0, 0)
            self._tracks_table.setCellWidget(row, 0, radio_widget)

            self._tracks_table.setItem(row, 1, QTableWidgetItem(f"#{stream.index}"))
            self._tracks_table.setItem(row, 2, QTableWidgetItem(stream.codec.upper()))

            sr = f"{stream.sample_rate // 1000}kHz" if stream.sample_rate else "?"
            self._tracks_table.setItem(row, 3, QTableWidgetItem(sr))

            ch = self._channel_label(stream)
            self._tracks_table.setItem(row, 4, QTableWidgetItem(ch))

            # Play button column
            btn = QPushButton("\u25B6")
            btn.setFixedWidth(32)
            if self._is_pure_audio:
                btn.clicked.connect(
                    lambda checked, p=self._input_selector.path(), n=stream.codec:
                        self._player.play_file(p, f"输入 {n}")
                )
            else:
                btn.clicked.connect(
                    lambda checked, p=self._input_selector.path(), si=stream.index, n=f"输入 #{stream.index} {stream.codec}":
                        self._player.play_stream(p, si, n)
                )
            self._tracks_table.setCellWidget(row, 5, btn)
            self._track_play_buttons.append(btn)

        # Auto-select first track
        if self._input_streams:
            first_radio = self._track_radio_group.button(self._input_streams[0].index)
            if first_radio:
                first_radio.setChecked(True)

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
        """Reorder _bg_files after drag-drop and refresh numbering."""
        if old_visual < 0 or old_visual >= len(self._bg_files):
            return
        if new_visual < 0 or new_visual >= len(self._bg_files):
            return
        # Build the new order from visual → logical mapping
        order = list(range(len(self._bg_files)))
        item = order.pop(old_visual)
        order.insert(new_visual, item)
        self._bg_files = [self._bg_files[i] for i in order]
        self._refresh_bg_table()

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
        volume = self._volume_spin.value()

        # Clean up previous preview temp dir
        self._cleanup_preview_temp()
        self._preview_temp_dir = tempfile.mkdtemp(prefix="jh_preview_")

        # If video input, extract selected audio track first
        if not self._is_pure_audio:
            base_audio = os.path.join(self._preview_temp_dir, "base.aac")
            cmd = combat_audio.build_extract_command(input_path, stream_idx, base_audio)
            subprocess.run(cmd, capture_output=True, timeout=30)
        else:
            base_audio = input_path

        preview_path = os.path.join(self._preview_temp_dir, "preview.aac")
        cmd = combat_audio.build_preview_command(base_audio, bg_path, volume, preview_path)
        subprocess.run(cmd, capture_output=True, timeout=30)

        if os.path.exists(preview_path):
            self._player.play_file(preview_path, "试听混合")

    # --- Helpers ---

    @staticmethod
    def _format_duration(seconds: float) -> str:
        s = int(seconds)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    @staticmethod
    def _channel_label(stream: combat_audio.AudioStreamInfo) -> str:
        if stream.channel_layout:
            labels = {"stereo": "立体声", "mono": "单声道", "5.1": "5.1声道", "5.1(side)": "5.1声道"}
            return labels.get(stream.channel_layout, stream.channel_layout)
        if stream.channels == 1:
            return "单声道"
        if stream.channels == 2:
            return "立体声"
        if stream.channels == 6:
            return "5.1声道"
        return f"{stream.channels}声道" if stream.channels else "?"

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
        return True, audio_count, None

    def build_config(self) -> CombatAudioConfig | None:
        return self._build_combat_config()

    def get_task_type(self) -> TaskType:
        return TaskType.COMBAT_AUDIO

    def _build_combat_config(self) -> CombatAudioConfig | None:
        input_path = self._input_selector.path()
        audio_dir = self._audio_dir_selector.path()
        if not input_path or not audio_dir:
            return None

        selected_track = self._track_radio_group.checkedId()
        if selected_track < 0:
            selected_track = 0

        audio_order = [f.filename for f in self._bg_files]

        return CombatAudioConfig(
            input_path=input_path,
            audio_dir=audio_dir,
            output_dir=self._output_selector.path() or None,
            mix_enabled=self._mix_checkbox.isChecked(),
            volume=self._volume_spin.value(),
            boxed=self._boxed_checkbox.isChecked(),
            thread_count=self._thread_spin.value(),
            audio_stream_index=selected_track,
            audio_order=audio_order,
        )

    def _cleanup_preview_temp(self):
        if self._preview_temp_dir and os.path.isdir(self._preview_temp_dir):
            shutil.rmtree(self._preview_temp_dir, ignore_errors=True)
            self._preview_temp_dir = None

    def cleanup(self):
        """Clean up player and preview temp files."""
        self._player.cleanup()
        self._cleanup_preview_temp()

