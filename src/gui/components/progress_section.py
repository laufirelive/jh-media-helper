from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

_PROGRESS_QSS = """
QProgressBar {
    border-radius: 3px;
    max-height: 6px;
    text-align: center;
}
QProgressBar::chunk {
    background: #33aa66;
    border-radius: 3px;
}
"""

_ERROR_CARD_QSS = """
QFrame {
    background: #f6f7f8;
    border: 1px solid #d9dde3;
    border-radius: 8px;
}
QPlainTextEdit {
    background: transparent;
    border: none;
    color: #4a5568;
    font-family: Menlo, Monaco, 'Courier New', monospace;
    font-size: 12px;
}
"""


class ProgressSection(QWidget):
    """Reusable progress bar + status label widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._progress_bar = QProgressBar()
        self._progress_bar.setStyleSheet(_PROGRESS_QSS)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: gray;")
        layout.addWidget(self._status_label)

        self._error_frame = QFrame()
        self._error_frame.setStyleSheet(_ERROR_CARD_QSS)
        self._error_frame.setVisible(False)
        error_layout = QVBoxLayout(self._error_frame)
        error_layout.setContentsMargins(10, 10, 10, 10)
        error_layout.setSpacing(6)

        self._error_toggle = QToolButton()
        self._error_toggle.setText("错误详情")
        self._error_toggle.setCheckable(True)
        self._error_toggle.setChecked(False)
        self._error_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._error_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._error_toggle.toggled.connect(self._toggle_error_details)
        error_layout.addWidget(self._error_toggle)

        self._error_summary_label = QLabel("")
        self._error_summary_label.setWordWrap(True)
        self._error_summary_label.setStyleSheet("color: #8b2f2f; font-weight: 600;")
        error_layout.addWidget(self._error_summary_label)

        self._error_details = QPlainTextEdit()
        self._error_details.setReadOnly(True)
        self._error_details.setVisible(False)
        self._error_details.setMaximumBlockCount(200)
        self._error_details.setMinimumHeight(110)
        error_layout.addWidget(self._error_details)

        layout.addWidget(self._error_frame)

    def update_progress(self, current: int, total: int, desc: str = "") -> None:
        self._progress_bar.setVisible(True)
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        if desc:
            self._status_label.setText(f"{desc}... {current}/{total}")
        else:
            self._status_label.setText(f"{current}/{total}")

    def set_finished(self, message: str) -> None:
        self._progress_bar.setVisible(False)
        self._status_label.setText(message)
        self.clear_error()

    def set_error(self, summary: str, details: str | None = None) -> None:
        self._progress_bar.setVisible(False)
        self._status_label.setText(summary)
        self._error_summary_label.setText(summary)
        self._error_details.setPlainText(details or "")
        has_details = bool((details or "").strip())
        self._error_toggle.setVisible(has_details)
        self._error_toggle.setChecked(False)
        self._error_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._error_details.setVisible(False)
        self._error_frame.setVisible(True)

    def clear_error(self) -> None:
        self._error_frame.setVisible(False)
        self._error_summary_label.clear()
        self._error_details.clear()
        self._error_toggle.setChecked(False)
        self._error_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._error_details.setVisible(False)

    def reset(self) -> None:
        self._progress_bar.setVisible(False)
        self._progress_bar.setValue(0)
        self._status_label.setText("")
        self.clear_error()

    def _toggle_error_details(self, checked: bool) -> None:
        self._error_toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self._error_details.setVisible(checked)
