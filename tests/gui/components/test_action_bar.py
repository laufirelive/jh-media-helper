import pytest
from PyQt6.QtWidgets import QApplication

from src.gui.components.action_bar import ActionBar

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture
def bar(qapp):
    return ActionBar()


def test_add_button_returns_qpushbutton(bar):
    btn = bar.add_button("测试")
    assert btn.text() == "测试"


def test_buttons_centered(bar):
    """Layout should have stretch-buttons-stretch pattern."""
    bar.add_button("A")
    bar.add_button("B")
    layout = bar._layout
    # First item is stretch, last item is stretch
    assert layout.itemAt(0).widget() is None  # stretch
    assert layout.itemAt(layout.count() - 1).widget() is None  # stretch


def test_roles_use_native_style(bar):
    """与 birefnet-gui 一致：不套 QSS，由系统绘制按钮。"""
    for role in ("primary", "danger", "secondary"):
        btn = bar.add_button("x", role=role)
        assert btn.styleSheet() == ""


def test_disabled_button(bar):
    btn = bar.add_button("不可用", enabled=False)
    assert not btn.isEnabled()
