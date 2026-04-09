# src/gui/components/file_selector.py
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class FileSelector(QWidget):
    """Reusable file/folder selector: label + read-only edit + browse button."""

    path_changed = pyqtSignal(str)

    def __init__(
        self,
        label: str,
        placeholder: str = "",
        dialog_mode: str = "directory",
        file_filter: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._dialog_mode = dialog_mode
        self._file_filter = file_filter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._label = QLabel(label)
        layout.addWidget(self._label)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._edit = QLineEdit()
        self._edit.setReadOnly(True)
        if placeholder:
            self._edit.setPlaceholderText(placeholder)
        row.addWidget(self._edit)

        self._btn = QPushButton("浏览...")
        self._btn.clicked.connect(self._browse)
        row.addWidget(self._btn)

        layout.addLayout(row)

    def path(self) -> str:
        return self._edit.text()

    def set_path(self, path: str) -> None:
        self._edit.setText(path)
        self.path_changed.emit(path)

    def _browse(self) -> None:
        if self._dialog_mode == "directory":
            path = QFileDialog.getExistingDirectory(self, self._label.text())
        elif self._dialog_mode == "file":
            path, _ = QFileDialog.getOpenFileName(
                self, self._label.text(), "", self._file_filter
            )
        elif self._dialog_mode == "save":
            path, _ = QFileDialog.getSaveFileName(
                self, self._label.text(), "", self._file_filter
            )
        else:
            return
        if path:
            self.set_path(path)
