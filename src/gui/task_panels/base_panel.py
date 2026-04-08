from abc import abstractmethod

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.gui.components.progress_section import ProgressSection


def _create_separator() -> QFrame:
    """Create a horizontal line separator."""
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setFrameShadow(QFrame.Shadow.Sunken)
    return sep


class BaseTaskPanel(QWidget):
    """Base class for all task panels. Provides a left-right split layout
    with a scrollable settings sidebar on the right."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = ProgressSection()
        self._init_base_layout()

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
        container = QWidget()
        settings_layout = QVBoxLayout(container)
        settings_layout.setSpacing(12)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        self._build_settings_panel(settings_layout)
        settings_layout.addStretch()
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
