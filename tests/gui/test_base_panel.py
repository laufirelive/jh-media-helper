import pytest
from PyQt6.QtWidgets import QApplication, QGroupBox, QLabel, QVBoxLayout

from src.gui.task_panels.base_panel import BaseTaskPanel
from src.gui.components.progress_section import ProgressSection


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class ConcretePanel(BaseTaskPanel):
    """Minimal concrete subclass for testing."""

    def _build_left_panel(self, layout: QVBoxLayout):
        layout.addWidget(QLabel("Left content"))

    def _build_settings_panel(self, layout: QVBoxLayout):
        group = QGroupBox("Settings")
        layout.addWidget(group)

    def validate(self):
        return True, 10, None

    def build_config(self):
        return {"test": True}

    def get_task_type(self):
        return "test"


@pytest.fixture
def panel(qapp):
    p = ConcretePanel()
    p.show()  # needed for isVisible() checks on child widgets
    return p


def test_panel_has_progress_section(panel):
    assert isinstance(panel._progress, ProgressSection)


def test_layout_is_horizontal(panel):
    from PyQt6.QtWidgets import QHBoxLayout
    assert isinstance(panel.layout(), QHBoxLayout)


def test_margins_are_20px(panel):
    m = panel.layout().contentsMargins()
    assert m.left() == 20
    assert m.right() == 20
    assert m.top() == 20
    assert m.bottom() == 20


def test_spacing_is_16(panel):
    assert panel.layout().spacing() == 16


def test_on_progress_updates_progress_section(panel):
    panel.on_progress(5, 10, "测试")
    assert panel._progress._progress_bar.isVisible()
    assert panel._progress._progress_bar.value() == 5


def test_on_finished_updates_status(panel):
    panel.on_finished("/tmp/output.mov")
    assert "完成" in panel._progress._status_label.text()


def test_validate_returns_tuple(panel):
    ok, count, err = panel.validate()
    assert ok is True
    assert count == 10


def test_build_config(panel):
    cfg = panel.build_config()
    assert cfg == {"test": True}
