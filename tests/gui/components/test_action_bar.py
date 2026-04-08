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


def test_primary_role(bar):
    btn = bar.add_button("开始", role="primary")
    ss = btn.styleSheet()
    assert "#33aa66" in ss or "#3a6" in ss or "33aa66" in ss


def test_danger_role(bar):
    btn = bar.add_button("取消", role="danger")
    ss = btn.styleSheet()
    assert "#cc4444" in ss or "#c44" in ss or "cc4444" in ss


def test_secondary_role_is_default(bar):
    btn = bar.add_button("清空")
    # Secondary has no special stylesheet (uses Qt default)
    assert btn.styleSheet() == ""


def test_disabled_button(bar):
    btn = bar.add_button("不可用", enabled=False)
    assert not btn.isEnabled()
