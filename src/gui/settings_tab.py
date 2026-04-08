# src/gui/settings_tab.py
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.data_dir import resolve_data_dir


class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Data directory group
        data_group = QGroupBox("数据目录")
        data_layout = QVBoxLayout(data_group)
        data_layout.setSpacing(8)

        dir_row = QHBoxLayout()
        dir_label = QLabel(f"路径: {resolve_data_dir()}")
        dir_label.setStyleSheet("color: #ccc;")
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

        # About group
        about_group = QGroupBox("关于")
        about_layout = QVBoxLayout(about_group)
        about_layout.setSpacing(4)

        name_label = QLabel("jh-media-helper v0.1")
        name_label.setStyleSheet("color: #ccc; font-weight: bold;")
        about_layout.addWidget(name_label)

        desc_label = QLabel("影视后期媒体处理工具")
        desc_label.setStyleSheet("color: gray; font-size: 11px;")
        about_layout.addWidget(desc_label)

        layout.addWidget(about_group)

        layout.addStretch()

    def _open_data_dir(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(resolve_data_dir()))
