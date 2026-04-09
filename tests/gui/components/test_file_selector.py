# tests/gui/components/test_file_selector.py
import pytest
from PyQt6.QtWidgets import QApplication

from src.gui.components.file_selector import FileSelector

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture
def selector(qapp):
    return FileSelector(label="测试目录:", placeholder="选择...")


def test_initial_path_is_empty(selector):
    assert selector.path() == ""


def test_set_path(selector):
    selector.set_path("/tmp/test")
    assert selector.path() == "/tmp/test"


def test_placeholder(selector):
    assert selector._edit.placeholderText() == "选择..."


def test_label_text(selector):
    assert selector._label.text() == "测试目录:"


def test_edit_is_readonly(selector):
    assert selector._edit.isReadOnly()


def test_path_changed_signal(selector, qtbot):
    """Signal emits when set_path is called."""
    with qtbot.waitSignal(selector.path_changed, timeout=1000) as blocker:
        selector.set_path("/tmp/new")
    assert blocker.args == ["/tmp/new"]


def test_directory_mode_default(qapp):
    s = FileSelector(label="Dir:", dialog_mode="directory")
    assert s._dialog_mode == "directory"


def test_file_mode(qapp):
    s = FileSelector(label="File:", dialog_mode="file", file_filter="Videos (*.mp4)")
    assert s._dialog_mode == "file"
    assert s._file_filter == "Videos (*.mp4)"
