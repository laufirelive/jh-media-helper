# src/gui/components/file_selector.py
import os

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
        *,
        drop_enabled: bool = False,
        drop_kind: str | None = None,
        drop_file_filter: set[str] | None = None,
    ):
        super().__init__(parent)
        self._dialog_mode = dialog_mode
        self._file_filter = file_filter
        self._drop_enabled = drop_enabled
        self._drop_kind = drop_kind
        self._drop_file_filter = {ext.lower() for ext in drop_file_filter or set()}
        self.setAcceptDrops(drop_enabled)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._label = QLabel(label)
        layout.addWidget(self._label)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._edit = QLineEdit()
        self._edit.setAcceptDrops(False)
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

    def _resolve_drop_path(self, paths: list[str]) -> str | None:
        if not self._drop_enabled or len(paths) != 1:
            return None
        path = paths[0]
        if self._drop_kind == "directory":
            return path if os.path.isdir(path) else None
        if self._drop_kind == "file":
            if not os.path.isfile(path):
                return None
            if self._drop_file_filter:
                ext = os.path.splitext(path)[1].lower()
                if ext not in self._drop_file_filter:
                    return None
            return path
        return None

    def dragEnterEvent(self, event):
        if not self.isEnabled() or not event.mimeData().hasUrls():
            event.ignore()
            return
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if self._resolve_drop_path(paths):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not self.isEnabled() or not event.mimeData().hasUrls():
            event.ignore()
            return
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        path = self._resolve_drop_path(paths)
        if path:
            self.set_path(path)
            event.acceptProposedAction()
        else:
            event.ignore()

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
