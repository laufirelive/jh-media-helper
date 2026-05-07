# src/gui/settings_tab.py
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.app_settings import AppSettings, load_settings, save_settings
from src.core.data_dir import resolve_data_dir
from src.core.external_tools import resolve_mkvmerge_path


class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = load_settings()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Data directory group
        data_group = QGroupBox("数据目录")
        data_layout = QVBoxLayout(data_group)
        data_layout.setSpacing(8)

        dir_row = QHBoxLayout()
        dir_label = QLabel(f"路径: {resolve_data_dir()}")
        dir_row.addWidget(dir_label)
        dir_row.addStretch()
        open_btn = QPushButton("打开")
        open_btn.clicked.connect(self._open_data_dir)
        dir_row.addWidget(open_btn)
        data_layout.addLayout(dir_row)

        hint = QLabel("队列持久化、日志等数据存储在此目录")
        hint.setStyleSheet("color: gray; font-size: 11px;")
        data_layout.addWidget(hint)

        layout.addWidget(data_group)

        # External tools group
        tools_group = QGroupBox("外部工具")
        tools_layout = QVBoxLayout(tools_group)
        tools_layout.setSpacing(8)

        mkvmerge_row = QHBoxLayout()
        mkvmerge_label = QLabel("mkvmerge 路径")
        mkvmerge_row.addWidget(mkvmerge_label)

        self._mkvmerge_edit = QLineEdit()
        self._mkvmerge_edit.setText(self._settings.mkvmerge_path or "")
        self._mkvmerge_edit.editingFinished.connect(self._save_mkvmerge_path)
        mkvmerge_row.addWidget(self._mkvmerge_edit, 1)

        detect_btn = QPushButton("自动检测")
        detect_btn.clicked.connect(self._detect_mkvmerge)
        mkvmerge_row.addWidget(detect_btn)

        choose_btn = QPushButton("选择...")
        choose_btn.clicked.connect(self._choose_mkvmerge)
        mkvmerge_row.addWidget(choose_btn)
        tools_layout.addLayout(mkvmerge_row)

        self._mkvmerge_status = QLabel()
        self._mkvmerge_status.setStyleSheet("color: gray; font-size: 11px;")
        tools_layout.addWidget(self._mkvmerge_status)
        self._update_mkvmerge_status()

        layout.addWidget(tools_group)

        # About group
        about_group = QGroupBox("关于")
        about_layout = QVBoxLayout(about_group)
        about_layout.setSpacing(4)

        name_label = QLabel("jh-media-helper v0.1")
        about_layout.addWidget(name_label)

        desc_label = QLabel("影视后期媒体处理工具")
        desc_label.setStyleSheet("color: gray; font-size: 11px;")
        about_layout.addWidget(desc_label)

        layout.addWidget(about_group)

        layout.addStretch()

    def _open_data_dir(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(resolve_data_dir()))

    def _current_mkvmerge_path(self) -> str | None:
        return self._mkvmerge_edit.text().strip() or None

    def _save_mkvmerge_path(self):
        path = self._current_mkvmerge_path()
        self._settings = AppSettings(mkvmerge_path=path)
        save_settings(self._settings)
        self._update_mkvmerge_status()

    def _detect_mkvmerge(self):
        detected = resolve_mkvmerge_path(None)
        if detected:
            self._mkvmerge_edit.setText(detected)
            self._save_mkvmerge_path()
            return

        self._update_mkvmerge_status()

    def _choose_mkvmerge(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 mkvmerge")
        if not path:
            return

        self._mkvmerge_edit.setText(path)
        self._save_mkvmerge_path()

    def _update_mkvmerge_status(self):
        path = self._current_mkvmerge_path()
        resolved = resolve_mkvmerge_path(path)
        if resolved:
            self._mkvmerge_status.setText(f"已检测：{resolved}")
        elif path:
            self._mkvmerge_status.setText("路径不可用，将自动检测；未检测到时回退 FFmpeg")
        else:
            self._mkvmerge_status.setText("未检测到 mkvmerge 时将回退 FFmpeg")
