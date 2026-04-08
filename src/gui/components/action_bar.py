from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget

_ROLE_STYLES = {
    "primary": "QPushButton { background-color: #33aa66; color: white; border: none; padding: 5px 16px; border-radius: 3px; }",
    "danger": "QPushButton { background-color: #cc4444; color: white; border: none; padding: 5px 16px; border-radius: 3px; }",
}


class ActionBar(QWidget):
    """Centered button row with role-based styling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(16, 8, 16, 8)
        self._layout.addStretch()
        # Buttons will be inserted before the trailing stretch
        self._layout.addStretch()

    def add_button(
        self,
        text: str,
        role: str = "secondary",
        enabled: bool = True,
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setEnabled(enabled)
        style = _ROLE_STYLES.get(role, "")
        if style:
            btn.setStyleSheet(style)
        # Insert before the trailing stretch
        self._layout.insertWidget(self._layout.count() - 1, btn)
        return btn
