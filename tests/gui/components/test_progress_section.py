import pytest
from PyQt6.QtWidgets import QApplication

from src.gui.components.progress_section import ProgressSection

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture
def section(qapp):
    s = ProgressSection()
    s.show()  # show parent so child isVisible() works correctly
    return s


def test_initial_state_hidden(section):
    assert not section._progress_bar.isVisible()
    assert section._status_label.text() == ""


def test_update_progress_shows_bar(section):
    section.update_progress(50, 100, "编码中")
    assert section._progress_bar.isVisible()
    assert section._progress_bar.value() == 50
    assert section._progress_bar.maximum() == 100
    assert "50/100" in section._status_label.text()


def test_set_finished(section):
    section.set_finished("完成: /tmp/out.mov")
    assert not section._progress_bar.isVisible()
    assert "完成" in section._status_label.text()


def test_reset(section):
    section.update_progress(50, 100, "编码中")
    section.reset()
    assert not section._progress_bar.isVisible()
    assert section._status_label.text() == ""
    assert section._progress_bar.value() == 0
