from abc import abstractmethod

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.gui.components.progress_section import ProgressSection

# 右侧设置区：macOS 原生 QGroupBox 常为纯白圆角卡片，与外侧灰底对比刺眼；与窗口 palette 对齐
_SETTINGS_SIDEBAR_QSS = """
QGroupBox {
    background-color: palette(window);
    border: 1px solid palette(mid);
    border-radius: 8px;
    margin-top: 14px;
    padding: 16px 12px 12px 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 4px;
}
"""


def _settings_scroll_shell_qss(window_bg_hex: str) -> str:
    """macOS 原生样式下 QScrollArea/viewport 常忽略 palette，仍显示浅白底；用实色强制对齐窗口背景。"""
    c = window_bg_hex
    return f"""
#settings_scroll {{
    background-color: {c};
    border: none;
}}
#settings_scroll_viewport {{
    background-color: {c};
    border: none;
}}
"""


def _create_separator() -> QFrame:
    """Create a horizontal line separator."""
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setFrameShadow(QFrame.Shadow.Sunken)
    return sep


class BaseTaskPanel(QWidget):
    """Base class for all task panels. Provides a left-right split layout
    with a scrollable settings sidebar on the right."""

    def __init__(self, parent=None, *, init_layout: bool = True):
        super().__init__(parent)
        self._progress = ProgressSection()
        self._settings_scroll: QScrollArea | None = None
        self._settings_sidebar_root: QWidget | None = None
        if init_layout:
            self._init_base_layout()

    def _window_bg_color(self):
        """构造阶段可能尚未挂到主窗口，self.palette() 的 Window 仍是默认白；优先用应用级调色板。"""
        app = QApplication.instance()
        pal = app.palette() if app is not None else self.palette()
        return pal.color(QPalette.ColorRole.Window)

    def _apply_settings_sidebar_colors(self) -> None:
        """同步右侧滚动区/容器与真实窗口底色（浅色主题下避免误用 #ffffff）。"""
        if self._settings_scroll is None or self._settings_sidebar_root is None:
            return
        win_col = self._window_bg_color()
        win_hex = win_col.name(QColor.NameFormat.HexRgb)
        self._settings_scroll.setStyleSheet(_settings_scroll_shell_qss(win_hex))
        pal_vp = self._settings_scroll.viewport().palette()
        pal_vp.setColor(QPalette.ColorRole.Base, win_col)
        pal_vp.setColor(QPalette.ColorRole.Window, win_col)
        self._settings_scroll.viewport().setPalette(pal_vp)
        self._settings_scroll.viewport().setAutoFillBackground(True)
        pal_c = self._settings_sidebar_root.palette()
        pal_c.setColor(QPalette.ColorRole.Base, win_col)
        pal_c.setColor(QPalette.ColorRole.Window, win_col)
        self._settings_sidebar_root.setPalette(pal_c)
        self._settings_sidebar_root.setAutoFillBackground(True)
        self._settings_sidebar_root.setStyleSheet(
            f"#settings_sidebar_root {{ background-color: {win_hex}; }}\n" + _SETTINGS_SIDEBAR_QSS
        )

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_settings_sidebar_colors()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.PaletteChange:
            self._apply_settings_sidebar_colors()
        super().changeEvent(event)

    def _init_base_layout(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Left panel (stretch=2): subclass content + separator + progress
        left = QVBoxLayout()
        left.setSpacing(10)
        self._build_left_panel(left)
        left.addWidget(_create_separator())
        left.addWidget(self._progress)
        left.addStretch()
        main_layout.addLayout(left, 2)

        # Right panel (stretch=1): scrollable settings sidebar
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setObjectName("settings_scroll")
        scroll.viewport().setObjectName("settings_scroll_viewport")
        scroll.setBackgroundRole(QPalette.ColorRole.Window)
        scroll.viewport().setBackgroundRole(QPalette.ColorRole.Window)
        container = QWidget()
        container.setObjectName("settings_sidebar_root")
        self._settings_scroll = scroll
        self._settings_sidebar_root = container
        self._apply_settings_sidebar_colors()
        settings_layout = QVBoxLayout(container)
        settings_layout.setSpacing(16)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        self._build_settings_panel(settings_layout)
        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

    @abstractmethod
    def _build_left_panel(self, layout: QVBoxLayout):
        """Subclass: add file selectors, info, etc. to the left panel."""

    @abstractmethod
    def _build_settings_panel(self, layout: QVBoxLayout):
        """Subclass: add QGroupBox sections to the settings sidebar."""

    @abstractmethod
    def validate(self) -> tuple[bool, int, str | None]:
        """Validate config. Returns (ok, frame_count, error_message)."""

    @abstractmethod
    def build_config(self) -> object:
        """Build and return the task config object."""

    @abstractmethod
    def get_task_type(self):
        """Return the TaskType enum value."""

    def on_progress(self, current: int, total: int, desc: str):
        self._progress.update_progress(current, total, desc)

    def on_finished(self, output_path: str):
        self._progress.set_finished(f"完成: {output_path}")
