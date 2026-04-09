from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget


class PreviewStartCell(QWidget):
    """Small slider cell for choosing a preview start time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration_ms = 0
        self._value_ms = 0
        self._active = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.setEnabled(False)
        self._slider.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self._slider, 1)

        self._time_label = QLabel(self.format_time(0))
        self._time_label.setFixedWidth(72)
        self._time_label.setStyleSheet("color: gray; font-size: 12px;")
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._time_label)

    @staticmethod
    def format_time(ms: int) -> str:
        """Format milliseconds as HH:MM:SS."""
        total_seconds = max(0, ms // 1000)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _on_value_changed(self, value: int) -> None:
        self._value_ms = value
        self._time_label.setText(self.format_time(value))

    def set_duration_ms(self, duration_ms: int) -> None:
        self._duration_ms = max(0, duration_ms)
        self._slider.setRange(0, self._duration_ms)
        self.set_value_ms(min(self._value_ms, self._duration_ms))

    def duration_ms(self) -> int:
        return self._duration_ms

    def set_value_ms(self, value_ms: int) -> None:
        value_ms = max(0, min(value_ms, self._duration_ms))
        if self._slider.value() != value_ms:
            self._slider.setValue(value_ms)
        else:
            self._on_value_changed(value_ms)

    def value_ms(self) -> int:
        return self._value_ms

    def set_active(self, active: bool) -> None:
        self._active = active
        self._slider.setEnabled(active)

    def is_active(self) -> bool:
        return self._active

    def is_slider_enabled(self) -> bool:
        return self._slider.isEnabled()

    def start_time_text(self) -> str:
        return self._time_label.text()
