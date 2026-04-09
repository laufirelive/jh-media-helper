from PyQt6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

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

    def reset(self) -> None:
        self._progress_bar.setVisible(False)
        self._progress_bar.setValue(0)
        self._status_label.setText("")
