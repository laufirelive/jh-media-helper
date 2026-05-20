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


def test_drop_disabled_by_default_rejects_path(qapp, tmp_path):
    folder = tmp_path / "seq"
    folder.mkdir()
    selector = FileSelector(label="Dir:")

    assert selector._resolve_drop_path([str(folder)]) is None


def test_directory_drop_accepts_single_directory(qapp, tmp_path):
    folder = tmp_path / "seq"
    folder.mkdir()
    selector = FileSelector(label="Dir:", drop_enabled=True, drop_kind="directory")

    assert selector._resolve_drop_path([str(folder)]) == str(folder)


def test_directory_drop_rejects_file(qapp, tmp_path):
    file_path = tmp_path / "frame.png"
    file_path.write_bytes(b"")
    selector = FileSelector(label="Dir:", drop_enabled=True, drop_kind="directory")

    assert selector._resolve_drop_path([str(file_path)]) is None


def test_file_drop_accepts_single_file(qapp, tmp_path):
    file_path = tmp_path / "clip.mkv"
    file_path.write_bytes(b"")
    selector = FileSelector(label="File:", drop_enabled=True, drop_kind="file")

    assert selector._resolve_drop_path([str(file_path)]) == str(file_path)


def test_file_drop_rejects_directory(qapp, tmp_path):
    folder = tmp_path / "audio"
    folder.mkdir()
    selector = FileSelector(label="File:", drop_enabled=True, drop_kind="file")

    assert selector._resolve_drop_path([str(folder)]) is None


def test_file_drop_filter_rejects_unlisted_extension(qapp, tmp_path):
    file_path = tmp_path / "notes.txt"
    file_path.write_text("not media")
    selector = FileSelector(
        label="File:",
        drop_enabled=True,
        drop_kind="file",
        drop_file_filter={".mkv", ".mp4"},
    )

    assert selector._resolve_drop_path([str(file_path)]) is None


def test_file_drop_filter_accepts_case_insensitive_extension(qapp, tmp_path):
    file_path = tmp_path / "CAPTION.SRT"
    file_path.write_text("1")
    selector = FileSelector(
        label="Subtitle:",
        drop_enabled=True,
        drop_kind="file",
        drop_file_filter={".srt", ".ass"},
    )

    assert selector._resolve_drop_path([str(file_path)]) == str(file_path)


def test_single_value_drop_rejects_multiple_paths(qapp, tmp_path):
    first = tmp_path / "one.mkv"
    second = tmp_path / "two.mkv"
    first.write_bytes(b"")
    second.write_bytes(b"")
    selector = FileSelector(label="File:", drop_enabled=True, drop_kind="file")
    selector.set_path("/existing.mkv")

    assert selector._resolve_drop_path([str(first), str(second)]) is None
    assert selector.path() == "/existing.mkv"
