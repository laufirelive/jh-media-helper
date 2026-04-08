from PyQt6.QtWidgets import QGroupBox, QLabel, QVBoxLayout, QWidget


class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        group = QGroupBox("数据目录")
        group_layout = QVBoxLayout(group)
        from src.core.data_dir import resolve_data_dir
        group_layout.addWidget(QLabel(f"路径: {resolve_data_dir()}"))
        layout.addWidget(group)
        layout.addStretch()
