# src/gui/components/audio_player.py
import os
import tempfile
import subprocess

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
)


def _format_time(ms: int) -> str:
    """Format milliseconds as MM:SS."""
    s = max(0, ms // 1000)
    return f"{s // 60:02d}:{s % 60:02d}"


class AudioPlayerBar(QWidget):
    """Shared audio playback bar based on QMediaPlayer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._temp_dir = tempfile.mkdtemp(prefix="jh_player_")
        self._current_temp: str | None = None

        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)

        self._init_ui()
        self._connect_signals()
        self.setVisible(False)

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

    def play_file(self, file_path: str, display_name: str = "") -> None:
        """Play a local audio file."""
        self.stop()
        name = display_name or os.path.basename(file_path)
        self._name_label.setText(name)
        self._player.setSource(QUrl.fromLocalFile(file_path))
        self._player.play()
        self.setVisible(True)

    def play_stream(self, file_path: str, stream_index: int, display_name: str = "") -> None:
        """Extract and play a specific audio stream from a video file."""
        self.stop()
        temp_path = os.path.join(self._temp_dir, f"stream_{stream_index}.aac")
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", file_path,
                    "-map", f"0:a:{stream_index}",
                    "-t", "10",
                    "-c:a", "aac",
                    temp_path,
                ],
                capture_output=True, timeout=30,
            )
        except Exception:
            return
        if not os.path.exists(temp_path):
            return
        self._current_temp = temp_path
        self.play_file(temp_path, display_name)

    def stop(self) -> None:
        """Stop playback."""
        self._player.stop()
        self._player.setSource(QUrl())

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def _toggle_play(self):
        if self.is_playing():
            self._player.pause()
        else:
            self._player.play()

    def _on_position_changed(self, position: int):
        if not self._slider.isSliderDown():
            self._slider.setValue(position)
        duration = self._player.duration()
        self._time_label.setText(f"{_format_time(position)} / {_format_time(duration)}")

    def _on_duration_changed(self, duration: int):
        self._slider.setRange(0, duration)

    def _on_slider_moved(self, position: int):
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
