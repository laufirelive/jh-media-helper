from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget


class ActionBar(QWidget):
    """居中按钮行。不设置 QSS，按钮使用系统原生样式（与 birefnet-gui 一致）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(16, 8, 16, 8)
        self._layout.setSpacing(10)
        self._layout.addStretch()
        self._layout.addStretch()

    def add_button(
        self,
        text: str,
        role: str = "secondary",
        enabled: bool = True,
    ) -> QPushButton:
        # role 仅保留兼容调用方（primary / danger / secondary），外观由系统主题决定
        btn = QPushButton(text)
        btn.setEnabled(enabled)
        self._layout.insertWidget(self._layout.count() - 1, btn)
        return btn
