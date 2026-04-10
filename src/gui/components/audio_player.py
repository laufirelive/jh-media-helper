# src/gui/components/audio_player.py
import os
import tempfile
import shutil

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
)

from src.core.preview_cache import PreviewCacheSession, build_input_track_cache_key
from src.core.processors import combat_audio


def _format_time(ms: int) -> str:
    """Format milliseconds as MM:SS."""
    s = max(0, ms // 1000)
    return f"{s // 60:02d}:{s % 60:02d}"


class AudioPlayerBar(QWidget):
    """Shared audio playback bar based on QMediaPlayer."""

    def __init__(self, parent=None, preview_cache: PreviewCacheSession | None = None):
        super().__init__(parent)
        self._preview_cache = preview_cache
        self._temp_dir = tempfile.mkdtemp(prefix="jh_player_")
        self._current_temp: str | None = None
        self._fixed_duration_ms: int | None = None

        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)

        self._init_ui()
        self._connect_signals()
        # 始终显示条；无有效媒体时控件禁用（见 _apply_idle_state）
        self._apply_idle_state()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(8)

        self._btn_play = QPushButton("\u25B6")
        self._btn_play.setFixedWidth(32)
        self._btn_play.clicked.connect(self._toggle_play)
        layout.addWidget(self._btn_play)

        self._name_label = QLabel("")
        self._name_label.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(self._name_label)

        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setStyleSheet("color: gray; font-size: 12px;")
        self._time_label.setFixedWidth(90)
        layout.addWidget(self._time_label)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.sliderMoved.connect(self._on_slider_moved)
        layout.addWidget(self._slider, 1)

        self._btn_stop = QPushButton("\u25A0")
        self._btn_stop.setFixedWidth(32)
        self._btn_stop.clicked.connect(self.stop)
        layout.addWidget(self._btn_stop)

    def _connect_signals(self):
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)

    def _apply_idle_state(self) -> None:
        """无加载媒体：条可见，播放/停止/进度条不可用。"""
        self._name_label.setText("暂未选择试听内容")
        self._time_label.setText("00:00 / 00:00")
        self._slider.setRange(0, 0)
        self._slider.setValue(0)
        self._btn_play.setText("\u25B6")
        self._btn_play.setEnabled(False)
        self._btn_stop.setEnabled(False)
        self._slider.setEnabled(False)

    def _enable_transport_controls(self) -> None:
        """已加载有效媒体后可操作播放控件。"""
        self._btn_play.setEnabled(True)
        self._btn_stop.setEnabled(True)
        self._slider.setEnabled(True)

    def _reset_player_track(self) -> None:
        """停止解码并清空媒体源，不重置条上的提示文案（由后续逻辑设置）。"""
        self._player.stop()
        self._player.setSource(QUrl())

    def _is_usable_preview_cache(self, cache_path: str) -> bool:
        """Return True when a cached preview can be played safely."""
        if not os.path.isfile(cache_path):
            return False
        try:
            if os.path.getsize(cache_path) <= 0:
                return False
            if not os.access(cache_path, os.R_OK):
                return False
            return bool(combat_audio.probe_audio_streams(cache_path))
        except OSError:
            return False

    def _discard_stale_preview_cache(self, cache_path: str) -> None:
        """Best-effort removal for broken cache files before regeneration."""
        try:
            if os.path.isdir(cache_path):
                shutil.rmtree(cache_path)
            else:
                os.remove(cache_path)
        except OSError:
            pass

    def _play_file(self, file_path: str, display_name: str, *, fixed_duration_ms: int | None) -> None:
        """播放本地音频文件；文件无效则保持不可播状态。"""
        self._reset_player_track()
        self._fixed_duration_ms = fixed_duration_ms
        name = display_name or os.path.basename(file_path)
        self._name_label.setText(name)
        if not os.path.isfile(file_path):
            self._apply_idle_state()
            return
        url = QUrl.fromLocalFile(file_path)
        if not url.isValid():
            self._apply_idle_state()
            return
        self._player.setSource(url)
        self._enable_transport_controls()
        self._player.play()

    def play_file(self, file_path: str, display_name: str = "") -> None:
        self._play_file(file_path, display_name, fixed_duration_ms=None)

    def play_preview_file(
        self,
        file_path: str,
        display_name: str = "",
        *,
        fixed_duration_ms: int | None = None,
    ) -> None:
        duration_ms = fixed_duration_ms if fixed_duration_ms is not None else int(combat_audio.PREVIEW_DURATION_SECONDS * 1000)
        self._play_file(file_path, display_name, fixed_duration_ms=max(0, int(duration_ms)))

    @staticmethod
    def _build_preview_extract_command(
        file_path: str,
        stream_index: int,
        output_path: str,
        *,
        start_seconds: float,
        duration_seconds: float,
    ) -> list[str]:
        """Build the ffmpeg command for preview extraction without mutating a base command."""
        if start_seconds < 0:
            raise ValueError("start_seconds must be >= 0")
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be > 0")

        cmd = ["ffmpeg", "-y"]
        if start_seconds > 0.0:
            cmd += ["-ss", f"{start_seconds}"]
        cmd += ["-i", file_path]
        cmd += [
            "-t", f"{duration_seconds}",
            "-map", f"0:a:{stream_index}",
            "-c:a", "aac",
            output_path,
        ]
        return cmd

    def play_stream(
        self,
        file_path: str,
        stream_index: int,
        display_name: str = "",
        *,
        preview_start_ms: int = 0,
    ) -> str | None:
        """从视频中抽取指定音轨试听（约 10 秒）。失败时返回错误信息。"""
        self.stop()
        preview_start_ms = max(0, int(preview_start_ms))
        cache_path: str | None = None
        if self._preview_cache is not None:
            try:
                cache_key = build_input_track_cache_key(
                    file_path,
                    stream_index,
                    start_ms=preview_start_ms,
                )
                cache_path = self._preview_cache.get_cache_path(cache_key)
            except RuntimeError:
                cache_path = None

        temp_path = cache_path or os.path.join(self._temp_dir, f"stream_{stream_index}.aac")
        if cache_path is not None and os.path.exists(cache_path):
            if not self._is_usable_preview_cache(cache_path):
                self._discard_stale_preview_cache(cache_path)
            else:
                self._current_temp = cache_path
                self.play_preview_file(cache_path, display_name)
                return None

        cmd = self._build_preview_extract_command(
            file_path,
            stream_index,
            temp_path,
            start_seconds=preview_start_ms / 1000.0,
            duration_seconds=combat_audio.PREVIEW_DURATION_SECONDS,
        )
        err = combat_audio.run_ffmpeg_command(
            cmd,
            timeout=30,
            default_message="输入音轨试听失败",
        )
        if err is not None:
            return err
        if not os.path.exists(temp_path):
            return "输入音轨试听失败"
        self._current_temp = temp_path
        self.play_preview_file(temp_path, display_name)
        return None

    def stop(self) -> None:
        """停止播放并清空当前媒体，回到不可播状态。"""
        self._reset_player_track()
        self._current_temp = None
        self._fixed_duration_ms = None
        self._apply_idle_state()

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def _toggle_play(self):
        # 无源时按钮已禁用，此处兜底
        if not self._player.source().isValid():
            return
        if self.is_playing():
            self._player.pause()
        else:
            self._player.play()

    def _on_position_changed(self, position: int):
        display_position = position
        display_duration = self._player.duration()
        if self._fixed_duration_ms is not None:
            display_duration = self._fixed_duration_ms
            display_position = min(position, self._fixed_duration_ms)

        if not self._slider.isSliderDown():
            self._slider.setValue(display_position)
        self._time_label.setText(f"{_format_time(display_position)} / {_format_time(display_duration)}")

    def _on_duration_changed(self, duration: int):
        if self._fixed_duration_ms is not None:
            self._slider.setRange(0, self._fixed_duration_ms)
            self._time_label.setText(f"{_format_time(0)} / {_format_time(self._fixed_duration_ms)}")
            return
        self._slider.setRange(0, duration)

    def _on_slider_moved(self, position: int):
        if not self._slider.isEnabled():
            return
        self._player.setPosition(position)

    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._btn_play.setText("\u23F8")
        else:
            self._btn_play.setText("\u25B6")
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self._slider.setValue(0)

    def cleanup(self) -> None:
        """Clean up temporary files."""
        self.stop()
        import shutil
        try:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        except Exception:
            pass
