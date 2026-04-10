import hashlib
import importlib
import os
import sys
import types
from unittest.mock import Mock, call

import pytest

from src.core.preview_cache import (
    PreviewCacheSession,
    build_base_audio_cache_key,
    build_input_track_cache_key,
    build_mix_preview_cache_key,
)


def _ensure_pyqt6_stub():
    try:
        import PyQt6  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    class _DummyNamespace:
        def __getattr__(self, name):
            return 0

    class _DummySignal:
        def connect(self, *args, **kwargs):
            return None

        def emit(self, *args, **kwargs):
            return None

    class _DummyMeta(type):
        def __getattr__(cls, name):
            return _DummyNamespace()

    class _DummyQtObject(metaclass=_DummyMeta):
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, name):
            if name in {
                "horizontalHeader",
                "verticalHeader",
                "selectionModel",
                "viewport",
                "palette",
            }:
                return lambda *args, **kwargs: _DummyQtObject()
            if name in {
                "buttonClicked",
                "clicked",
                "currentChanged",
                "path_changed",
                "preview_enabled_changed",
                "selectionChanged",
                "sectionMoved",
                "task_count_changed",
                "toggled",
                "sliderMoved",
                "positionChanged",
                "durationChanged",
                "playbackStateChanged",
            }:
                return _DummySignal()

            def _noop(*args, **kwargs):
                return None

            return _noop

    class QApplication(_DummyQtObject):
        _instance = None

        def __init__(self, *args, **kwargs):
            QApplication._instance = self

        @classmethod
        def instance(cls):
            return cls._instance

    class QMessageBox(_DummyQtObject):
        class StandardButton:
            Yes = 0
            No = 1
            Discard = 2

        @staticmethod
        def warning(*args, **kwargs):
            return None

        @staticmethod
        def critical(*args, **kwargs):
            return None

        @staticmethod
        def question(*args, **kwargs):
            return QMessageBox.StandardButton.Yes

    qt_package = types.ModuleType("PyQt6")
    qtcore = types.ModuleType("PyQt6.QtCore")
    qtgui = types.ModuleType("PyQt6.QtGui")
    qtwidgets = types.ModuleType("PyQt6.QtWidgets")
    qtmultimedia = types.ModuleType("PyQt6.QtMultimedia")

    qtcore.pyqtSignal = lambda *args, **kwargs: _DummySignal()
    qtcore.Qt = _DummyNamespace()
    qtcore.Qt.Orientation = types.SimpleNamespace(Horizontal=0, Vertical=1)
    qtcore.QEvent = _DummyQtObject
    qtgui.QColor = _DummyQtObject
    qtgui.QPalette = _DummyQtObject

    for name in [
        "QApplication",
        "QButtonGroup",
        "QCheckBox",
        "QDoubleSpinBox",
        "QFrame",
        "QGroupBox",
        "QHBoxLayout",
        "QHeaderView",
        "QLabel",
        "QMainWindow",
        "QMessageBox",
        "QPushButton",
        "QRadioButton",
        "QScrollArea",
        "QSizePolicy",
        "QSpinBox",
        "QTabWidget",
        "QTableWidget",
        "QTableWidgetItem",
        "QVBoxLayout",
        "QWidget",
    ]:
        setattr(qtwidgets, name, QApplication if name == "QApplication" else _DummyQtObject)
    qtwidgets.QMessageBox = QMessageBox

    qtcore.__getattr__ = lambda name: _DummyQtObject
    qtgui.__getattr__ = lambda name: _DummyQtObject
    qtwidgets.__getattr__ = lambda name: _DummyQtObject
    qtmultimedia.__getattr__ = lambda name: _DummyQtObject

    pil_package = types.ModuleType("PIL")
    pil_image = types.ModuleType("PIL.Image")

    class _DummyImageContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    pil_image.open = lambda *args, **kwargs: _DummyImageContext()
    pil_package.Image = pil_image

    sys.modules["PyQt6"] = qt_package
    sys.modules["PyQt6.QtCore"] = qtcore
    sys.modules["PyQt6.QtGui"] = qtgui
    sys.modules["PyQt6.QtWidgets"] = qtwidgets
    sys.modules["PyQt6.QtMultimedia"] = qtmultimedia
    sys.modules["PIL"] = pil_package
    sys.modules["PIL.Image"] = pil_image


def _ensure_main_window_dependency_stubs():
    sys.modules.pop("src.gui.main_window", None)
    from PyQt6.QtWidgets import QWidget

    class _DummySignal:
        def connect(self, *args, **kwargs):
            return None

        def emit(self, *args, **kwargs):
            return None

    class _DummyQtObject(QWidget):
        def __init__(self, *args, **kwargs):
            super().__init__()

        def __getattr__(self, name):
            if name in {"clicked", "preview_enabled_changed", "task_count_changed"}:
                return _DummySignal()

            def _noop(*args, **kwargs):
                return None

            return _noop

    base_panel = types.ModuleType("src.gui.task_panels.base_panel")

    class BaseTaskPanel(_DummyQtObject):
        def validate(self):
            return True, 0, None

        def build_config(self):
            return None

        def get_task_type(self):
            return None

        def on_progress(self, *args, **kwargs):
            return None

        def on_finished(self, *args, **kwargs):
            return None

    base_panel.BaseTaskPanel = BaseTaskPanel

    action_bar = types.ModuleType("src.gui.components.action_bar")

    class _Button(_DummyQtObject):
        clicked = _DummySignal()

    class ActionBar(_DummyQtObject):
        def add_button(self, *args, **kwargs):
            return _Button()

    action_bar.ActionBar = ActionBar

    queue_tab = types.ModuleType("src.gui.queue_tab")

    class QueueTab(_DummyQtObject):
        task_count_changed = _DummySignal()

        def stop(self):
            return None

        def refresh(self):
            return None

    queue_tab.QueueTab = QueueTab

    settings_tab = types.ModuleType("src.gui.settings_tab")
    settings_tab.SettingsTab = type("SettingsTab", (_DummyQtObject,), {})

    pic_seq_panel = types.ModuleType("src.gui.task_panels.pic_seq_panel")
    pic_seq_panel.PicSeqPanel = type("PicSeqPanel", (BaseTaskPanel,), {})

    combat_audio_panel = types.ModuleType("src.gui.task_panels.combat_audio_panel")

    class CombatAudioPanel(BaseTaskPanel):
        preview_enabled_changed = _DummySignal()

        def __init__(self, *args, **kwargs):
            super().__init__()
            self.init_kwargs = kwargs

        def cleanup(self):
            return None

        def preview_mix(self):
            return None

    combat_audio_panel.CombatAudioPanel = CombatAudioPanel

    confirm_dialog = types.ModuleType("src.gui.confirm_dialog")
    confirm_dialog.confirm_action = lambda *args, **kwargs: True

    pic_seq_processor = types.ModuleType("src.core.processors.pic_seq")
    pic_seq_processor._resolve_output_path = lambda config: ""

    sys.modules["src.gui.task_panels.base_panel"] = base_panel
    sys.modules["src.gui.components.action_bar"] = action_bar
    sys.modules["src.gui.queue_tab"] = queue_tab
    sys.modules["src.gui.settings_tab"] = settings_tab
    sys.modules["src.gui.task_panels.pic_seq_panel"] = pic_seq_panel
    sys.modules["src.gui.task_panels.combat_audio_panel"] = combat_audio_panel
    sys.modules["src.gui.confirm_dialog"] = confirm_dialog
    sys.modules["src.core.processors.pic_seq"] = pic_seq_processor


_ensure_pyqt6_stub()

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_start_cleans_old_preview_sessions(tmp_path):
    root = tmp_path / "cache" / "preview"
    old_dir = root / "old-session"
    old_dir.mkdir(parents=True)
    (old_dir / "old.aac").write_text("stale")

    session = PreviewCacheSession(root_dir=str(root))
    started_path = session.start()

    assert os.path.isdir(started_path)
    assert os.path.basename(started_path) != "old-session"
    assert not old_dir.exists()


def test_get_cache_path_returns_stable_hashed_aac_path(tmp_path):
    session = PreviewCacheSession(root_dir=str(tmp_path / "preview"))
    session.start()

    cache_key = "kind=input_track|input=/a.mp4|stream=0|version=v1"
    expected_name = f"{hashlib.sha256(cache_key.encode('utf-8')).hexdigest()}.aac"

    path1 = session.get_cache_path(cache_key)
    path2 = session.get_cache_path(cache_key)

    assert path1 == path2
    assert os.path.basename(path1) == expected_name
    assert os.path.dirname(path1) == session.session_dir


def test_cleanup_removes_only_current_session_dir(tmp_path):
    root = tmp_path / "cache" / "preview"
    session = PreviewCacheSession(root_dir=str(root))
    session.start()
    current_dir = session.session_dir
    keep_dir = root / "keep-me"
    keep_dir.mkdir(parents=True)

    session.cleanup()

    assert not os.path.exists(current_dir)
    assert keep_dir.exists()


def test_build_input_track_cache_key_is_stable():
    key1 = build_input_track_cache_key("/tmp/a.mp4", 0, start_ms=0)
    key2 = build_input_track_cache_key("/tmp/a.mp4", 0, start_ms=0)
    key3 = build_input_track_cache_key("/tmp/a.mp4", 0, start_ms=5000)
    key4 = build_input_track_cache_key("/tmp/a.mp4", 1, start_ms=0)
    key5 = build_input_track_cache_key("/tmp/a.mp4", 0)

    assert key1 == key2
    assert key1 != key3
    assert key1 != key4
    assert key1 == key5


def test_build_input_track_cache_key_changes_when_source_file_changes_in_place(tmp_path):
    input_path = tmp_path / "input.aac"
    input_path.write_bytes(b"aaaa")

    key1 = build_input_track_cache_key(str(input_path), 0, start_ms=0)

    input_path.write_bytes(b"bbbb")
    os.utime(input_path, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))

    key2 = build_input_track_cache_key(str(input_path), 0, start_ms=0)

    assert key1 != key2


def test_build_input_track_cache_key_changes_when_preview_start_changes(tmp_path):
    input_path = tmp_path / "input.aac"
    input_path.write_bytes(b"stable-source")

    key1 = build_input_track_cache_key(str(input_path), 0, start_ms=0)
    key2 = build_input_track_cache_key(str(input_path), 0, start_ms=2500)

    assert key1 != key2


def test_build_base_audio_cache_key_is_stable(tmp_path):
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"stable-source")

    key1 = build_base_audio_cache_key(str(input_path), 0, start_ms=0)
    key2 = build_base_audio_cache_key(str(input_path), 0, start_ms=0)
    key3 = build_base_audio_cache_key(str(input_path), 0, start_ms=5000)
    key4 = build_base_audio_cache_key(str(input_path), 1, start_ms=0)
    key5 = build_base_audio_cache_key(str(input_path), 0)

    assert key1 == key2
    assert key1 != key3
    assert key1 != key4
    assert key1 == key5


def test_build_base_audio_cache_key_changes_when_preview_start_changes(tmp_path):
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"stable-source")

    key1 = build_base_audio_cache_key(str(input_path), 0, start_ms=0)
    key2 = build_base_audio_cache_key(str(input_path), 0, start_ms=2500)

    assert key1 != key2


def test_build_mix_preview_cache_key_changes_for_bg_path_and_volume(tmp_path):
    input_path = tmp_path / "input.mp4"
    bg1_path = tmp_path / "bg1.aac"
    bg2_path = tmp_path / "bg2.aac"
    input_path.write_bytes(b"input")
    bg1_path.write_bytes(b"bg-one")
    bg2_path.write_bytes(b"bg-two")

    key1 = build_mix_preview_cache_key(str(input_path), 0, str(bg1_path), 0.6, start_ms=0)
    key2 = build_mix_preview_cache_key(str(input_path), 0, str(bg1_path), 0.6, start_ms=0)
    key3 = build_mix_preview_cache_key(str(input_path), 0, str(bg2_path), 0.6, start_ms=0)
    key4 = build_mix_preview_cache_key(str(input_path), 0, str(bg1_path), 0.7, start_ms=0)
    key5 = build_mix_preview_cache_key(str(input_path), 0, str(bg1_path), 0.6, start_ms=2500)
    key6 = build_mix_preview_cache_key(str(input_path), 1, str(bg1_path), 0.6, start_ms=0)
    key7 = build_mix_preview_cache_key(str(input_path), 0, str(bg1_path), 0.6)

    assert key1 == key2
    assert key1 != key3
    assert key1 != key4
    assert key1 != key5
    assert key1 != key6
    assert key1 == key7


def test_play_stream_uses_cached_file_when_present(qapp, monkeypatch, tmp_path):
    _ensure_pyqt6_stub()
    from src.gui.components.audio_player import AudioPlayerBar

    session = PreviewCacheSession(root_dir=str(tmp_path / "preview"))
    session.start()
    cache_key = build_input_track_cache_key("/tmp/a.mp4", 0)
    cache_path = session.get_cache_path(cache_key)
    with open(cache_path, "wb") as f:
        f.write(b"cached")

    played = {}

    def fake_play_preview_file(file_path, display_name=""):
        played["file_path"] = file_path
        played["display_name"] = display_name

    mock_run = Mock()
    monkeypatch.setattr(
        "src.gui.components.audio_player.combat_audio.probe_audio_streams",
        lambda path: [object()] if path == cache_path else [],
    )
    monkeypatch.setattr("src.core.processors.combat_audio.run_ffmpeg_command", mock_run)

    player = AudioPlayerBar(preview_cache=session)
    monkeypatch.setattr(player, "play_preview_file", fake_play_preview_file)

    err = player.play_stream("/tmp/a.mp4", 0, "输入 #1 AAC")

    assert err is None
    assert played["file_path"] == cache_path
    assert played["display_name"] == "输入 #1 AAC"
    mock_run.assert_not_called()


def test_play_stream_uses_preview_start_in_cache_key_for_cached_hits(qapp, monkeypatch, tmp_path):
    _ensure_pyqt6_stub()
    from src.gui.components.audio_player import AudioPlayerBar

    session = PreviewCacheSession(root_dir=str(tmp_path / "preview"))
    session.start()
    zero_start_path = session.get_cache_path(build_input_track_cache_key("/tmp/a.mp4", 0, start_ms=0))
    non_zero_start_key = build_input_track_cache_key("/tmp/a.mp4", 0, start_ms=2500)
    non_zero_start_path = session.get_cache_path(non_zero_start_key)
    with open(non_zero_start_path, "wb") as f:
        f.write(b"cached")

    played = {}

    def fake_play_preview_file(file_path, display_name=""):
        played["file_path"] = file_path
        played["display_name"] = display_name

    mock_run = Mock()
    monkeypatch.setattr(
        "src.gui.components.audio_player.combat_audio.probe_audio_streams",
        lambda path: [object()] if path == non_zero_start_path else [],
    )
    monkeypatch.setattr("src.core.processors.combat_audio.run_ffmpeg_command", mock_run)

    player = AudioPlayerBar(preview_cache=session)
    monkeypatch.setattr(player, "play_preview_file", fake_play_preview_file)

    err = player.play_stream("/tmp/a.mp4", 0, "输入 #1 AAC", preview_start_ms=2500)

    assert err is None
    assert played["file_path"] == non_zero_start_path
    assert played["display_name"] == "输入 #1 AAC"
    assert zero_start_path != non_zero_start_path
    mock_run.assert_not_called()


def test_play_stream_with_preview_cache_miss_writes_to_session_cache_path_and_invokes_ffmpeg(qapp, monkeypatch, tmp_path):
    _ensure_pyqt6_stub()
    from src.gui.components.audio_player import AudioPlayerBar

    session = PreviewCacheSession(root_dir=str(tmp_path / "preview"))
    session.start()
    cache_key = build_input_track_cache_key("/tmp/a.mp4", 0)
    cache_path = session.get_cache_path(cache_key)

    played = {}

    def fake_play_preview_file(file_path, display_name=""):
        played["file_path"] = file_path
        played["display_name"] = display_name

    monkeypatch.setattr(
        "src.gui.components.audio_player.combat_audio.probe_audio_streams",
        lambda path: [],
    )

    def fake_run_ffmpeg_command(cmd, timeout, default_message):
        with open(cmd[-1], "wb") as f:
            f.write(b"generated")
        return None

    mock_run = Mock(side_effect=fake_run_ffmpeg_command)
    monkeypatch.setattr("src.core.processors.combat_audio.run_ffmpeg_command", mock_run)

    player = AudioPlayerBar(preview_cache=session)
    monkeypatch.setattr(player, "play_preview_file", fake_play_preview_file)

    err = player.play_stream("/tmp/a.mp4", 0, "输入 #1 AAC")

    assert err is None
    assert played["file_path"] == cache_path
    assert played["display_name"] == "输入 #1 AAC"
    mock_run.assert_called_once()
    assert mock_run.call_args.args[0][-1] == cache_path


def test_play_stream_with_preview_cache_miss_builds_explicit_preview_command_with_start_and_duration(qapp, monkeypatch, tmp_path):
    _ensure_pyqt6_stub()
    from src.gui.components.audio_player import AudioPlayerBar

    session = PreviewCacheSession(root_dir=str(tmp_path / "preview"))
    session.start()
    cache_key = build_input_track_cache_key("/tmp/a.mp4", 0, start_ms=2500)
    cache_path = session.get_cache_path(cache_key)

    played = {}

    def fake_play_preview_file(file_path, display_name=""):
        played["file_path"] = file_path
        played["display_name"] = display_name

    monkeypatch.setattr(
        "src.gui.components.audio_player.combat_audio.probe_audio_streams",
        lambda path: [],
    )

    def fake_run_ffmpeg_command(cmd, timeout, default_message):
        with open(cmd[-1], "wb") as f:
            f.write(b"generated")
        played["cmd"] = cmd
        return None

    mock_run = Mock(side_effect=fake_run_ffmpeg_command)
    monkeypatch.setattr("src.core.processors.combat_audio.run_ffmpeg_command", mock_run)
    monkeypatch.setattr("src.core.processors.combat_audio.build_extract_command", Mock(side_effect=AssertionError("should not be called")))

    player = AudioPlayerBar(preview_cache=session)
    monkeypatch.setattr(player, "play_preview_file", fake_play_preview_file)

    err = player.play_stream("/tmp/a.mp4", 0, "输入 #1 AAC", preview_start_ms=2500)

    assert err is None
    assert played["file_path"] == cache_path
    assert played["display_name"] == "输入 #1 AAC"
    mock_run.assert_called_once()
    assert mock_run.call_args.args[0][-1] == cache_path
    assert played["cmd"][0] == "ffmpeg"
    assert played["cmd"][1:5] == ["-y", "-ss", "2.5", "-i"]
    assert "-ss" in played["cmd"]
    assert "2.5" in played["cmd"]
    assert "-t" in played["cmd"]
    assert "10.0" in played["cmd"]
    assert "-c:a" in played["cmd"]
    assert "aac" in played["cmd"]
    assert "copy" not in played["cmd"]


def test_play_stream_recovers_from_non_empty_invalid_preview_cache_by_deleting_and_regenerating(qapp, monkeypatch, tmp_path):
    _ensure_pyqt6_stub()
    from src.gui.components.audio_player import AudioPlayerBar

    session = PreviewCacheSession(root_dir=str(tmp_path / "preview"))
    session.start()
    cache_key = build_input_track_cache_key("/tmp/a.mp4", 0)
    cache_path = session.get_cache_path(cache_key)
    with open(cache_path, "wb") as f:
        f.write(b"not-an-aac-preview")

    played = {}

    def fake_play_preview_file(file_path, display_name=""):
        played["file_path"] = file_path
        played["display_name"] = display_name

    def fake_run_ffmpeg_command(cmd, timeout, default_message):
        with open(cmd[-1], "wb") as f:
            f.write(b"generated")
        return None

    mock_run = Mock(side_effect=fake_run_ffmpeg_command)
    monkeypatch.setattr("src.core.processors.combat_audio.run_ffmpeg_command", mock_run)

    player = AudioPlayerBar(preview_cache=session)
    monkeypatch.setattr(player, "play_preview_file", fake_play_preview_file)

    err = player.play_stream("/tmp/a.mp4", 0, "输入 #1 AAC")

    assert err is None
    assert played["file_path"] == cache_path
    assert played["display_name"] == "输入 #1 AAC"
    mock_run.assert_called_once()
    assert mock_run.call_args.args[0][-1] == cache_path
    assert not os.path.exists(cache_path) or os.path.getsize(cache_path) > 0


def test_fixed_preview_duration_does_not_force_pause_or_seek(qapp):
    _ensure_pyqt6_stub()
    from src.gui.components.audio_player import AudioPlayerBar

    player = AudioPlayerBar()
    pause_mock = Mock()
    seek_mock = Mock()
    player._player = types.SimpleNamespace(
        duration=lambda: 12_000,
        pause=pause_mock,
        setPosition=seek_mock,
    )
    player._fixed_duration_ms = 10_000

    player._on_position_changed(10_500)

    pause_mock.assert_not_called()
    seek_mock.assert_not_called()


def test_play_input_stream_preview_passes_shared_preview_start_ms(qapp, monkeypatch):
    sys.modules.pop("src.gui.task_panels.combat_audio_panel", None)

    audio_player = types.ModuleType("src.gui.components.audio_player")
    audio_player.AudioPlayerBar = type("AudioPlayerBar", (), {})
    monkeypatch.setitem(sys.modules, "src.gui.components.audio_player", audio_player)

    combat_audio_panel = importlib.import_module("src.gui.task_panels.combat_audio_panel")

    play_stream = Mock(return_value=None)
    panel = types.SimpleNamespace(
        _preview_start_ms=2500,
        _player=types.SimpleNamespace(play_stream=play_stream),
    )

    combat_audio_panel.CombatAudioPanel._play_input_stream_preview(panel, "/tmp/a.mp4", 0, "输入 #1 AAC")

    play_stream.assert_called_once_with("/tmp/a.mp4", 0, "输入 #1 AAC", preview_start_ms=2500)


def test_play_input_track_preview_uses_shared_preview_start_ms_for_pure_audio(qapp, monkeypatch):
    sys.modules.pop("src.gui.task_panels.combat_audio_panel", None)

    audio_player = types.ModuleType("src.gui.components.audio_player")
    audio_player.AudioPlayerBar = type("AudioPlayerBar", (), {})
    monkeypatch.setitem(sys.modules, "src.gui.components.audio_player", audio_player)

    combat_audio_panel = importlib.import_module("src.gui.task_panels.combat_audio_panel")

    play_stream = Mock(return_value=None)
    panel = types.SimpleNamespace(
        _is_pure_audio=True,
        _preview_start_ms=2500,
        _player=types.SimpleNamespace(play_stream=play_stream),
    )

    combat_audio_panel.CombatAudioPanel._play_input_track_preview(panel, "/tmp/a.wav", 0, "输入 AAC")

    play_stream.assert_called_once_with("/tmp/a.wav", 0, "输入 AAC", preview_start_ms=2500)


def test_session_dir_requires_start(tmp_path):
    session = PreviewCacheSession(root_dir=str(tmp_path / "preview"))

    with pytest.raises(RuntimeError):
        _ = session.session_dir


def test_main_window_starts_and_cleans_preview_cache(qapp, monkeypatch):
    _ensure_main_window_dependency_stubs()
    from src.gui.main_window import MainWindow

    fake_cache = Mock()
    fake_cache.start = Mock(return_value=None)
    fake_cache.cleanup = Mock(return_value=None)

    monkeypatch.setattr("src.gui.main_window.PreviewCacheSession", lambda: fake_cache)
    monkeypatch.setattr("src.gui.main_window.EncoderRegistry._probe", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_queue_recovery", lambda self: None)

    window = MainWindow()

    assert fake_cache.start.call_count == 1
    assert window._combat_panel.init_kwargs["preview_cache"] is fake_cache

    class DummyEvent:
        def accept(self):
            self.accepted = True

    event = DummyEvent()
    window.closeEvent(event)

    assert fake_cache.cleanup.call_count == 1


def test_main_window_passes_preview_cache_to_combat_panel(qapp, monkeypatch):
    _ensure_main_window_dependency_stubs()
    from src.gui.main_window import MainWindow

    fake_cache = Mock()
    fake_cache.start = Mock(return_value=None)
    fake_cache.cleanup = Mock(return_value=None)

    monkeypatch.setattr("src.gui.main_window.PreviewCacheSession", lambda: fake_cache)
    monkeypatch.setattr("src.gui.main_window.EncoderRegistry._probe", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_queue_recovery", lambda self: None)

    window = MainWindow()

    assert window._combat_panel.init_kwargs["preview_cache"] is fake_cache


def test_main_window_falls_back_to_no_cache_when_preview_cache_start_fails(qapp, monkeypatch):
    _ensure_main_window_dependency_stubs()
    from src.gui.main_window import MainWindow

    fake_cache = Mock()
    fake_cache.start = Mock(side_effect=RuntimeError("cache init failed"))
    fake_cache.cleanup = Mock(return_value=None)

    monkeypatch.setattr("src.gui.main_window.PreviewCacheSession", lambda: fake_cache)
    monkeypatch.setattr("src.gui.main_window.EncoderRegistry._probe", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_queue_recovery", lambda self: None)

    window = MainWindow()

    assert window._preview_cache is None
    assert window._combat_panel.init_kwargs["preview_cache"] is None


def test_combat_audio_panel_accepts_preview_cache_without_breaking_construction(qapp, monkeypatch):
    sys.modules.pop("src.gui.task_panels.combat_audio_panel", None)
    sys.modules.pop("src.gui.task_panels.base_panel", None)

    player_calls: list[dict[str, object]] = []
    audio_player = types.ModuleType("src.gui.components.audio_player")

    class AudioPlayerBar(QWidget):
        def __init__(self, *args, **kwargs):
            player_calls.append(dict(kwargs))
            if "preview_cache" in kwargs:
                raise TypeError("AudioPlayerBar() got an unexpected keyword argument 'preview_cache'")
            super().__init__()

    audio_player.AudioPlayerBar = AudioPlayerBar
    monkeypatch.setitem(sys.modules, "src.gui.components.audio_player", audio_player)

    combat_audio_panel = importlib.import_module("src.gui.task_panels.combat_audio_panel")
    preview_cache = Mock()

    panel = combat_audio_panel.CombatAudioPanel(preview_cache=preview_cache)

    assert panel._preview_cache is preview_cache
    assert player_calls == [{"preview_cache": preview_cache}, {}]


def test_combat_audio_panel_re_raises_unrelated_audio_player_typeerrors(qapp, monkeypatch):
    sys.modules.pop("src.gui.task_panels.combat_audio_panel", None)
    sys.modules.pop("src.gui.task_panels.base_panel", None)

    audio_player = types.ModuleType("src.gui.components.audio_player")

    class AudioPlayerBar(QWidget):
        def __init__(self, *args, **kwargs):
            raise TypeError("boom")

    audio_player.AudioPlayerBar = AudioPlayerBar
    monkeypatch.setitem(sys.modules, "src.gui.components.audio_player", audio_player)

    combat_audio_panel = importlib.import_module("src.gui.task_panels.combat_audio_panel")

    with pytest.raises(TypeError, match="boom"):
        combat_audio_panel.CombatAudioPanel(preview_cache=Mock())


def test_combat_audio_panel_emits_preview_state_after_input_and_audio_dir_changes(qapp, monkeypatch):
    sys.modules.pop("src.gui.task_panels.combat_audio_panel", None)

    audio_player = types.ModuleType("src.gui.components.audio_player")
    audio_player.AudioPlayerBar = type("AudioPlayerBar", (), {})
    monkeypatch.setitem(sys.modules, "src.gui.components.audio_player", audio_player)

    combat_audio_panel = importlib.import_module("src.gui.task_panels.combat_audio_panel")

    emit = Mock()
    panel = types.SimpleNamespace(
        preview_enabled_changed=types.SimpleNamespace(emit=emit),
        _info_label=types.SimpleNamespace(setText=Mock(), text=Mock(return_value="")),
        _refresh_tracks_table=Mock(),
        _update_param_states=Mock(),
        _refresh_bg_table=Mock(),
        _update_info_bg_count=Mock(),
        _format_duration=lambda seconds: "00:12",
        get_preview_btn_enabled=Mock(return_value=True),
    )
    panel._emit_preview_state = lambda: combat_audio_panel.CombatAudioPanel._emit_preview_state(panel)

    monkeypatch.setattr(combat_audio_panel.os.path, "exists", lambda path: True)
    monkeypatch.setattr(combat_audio_panel.os.path, "isdir", lambda path: True)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "is_pure_audio", lambda path: True)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "probe_duration", lambda path: 12.3)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "probe_audio_streams", lambda path: [])
    monkeypatch.setattr(
        combat_audio_panel.combat_audio,
        "scan_audio_dir",
        lambda path: [types.SimpleNamespace(path="/music/bg.wav", filename="bg.wav", duration=0.0)],
    )

    combat_audio_panel.CombatAudioPanel._on_input_changed(panel, "/input/video.mp4")
    combat_audio_panel.CombatAudioPanel._on_audio_dir_changed(panel, "/input/music")
    combat_audio_panel.CombatAudioPanel._on_input_changed(panel, "")

    assert emit.call_args_list == [call(True), call(True), call(True)]


def test_preview_mix_cleans_created_temp_dir_on_preview_generation_error(qapp, monkeypatch, tmp_path):
    sys.modules.pop("src.gui.task_panels.combat_audio_panel", None)

    audio_player = types.ModuleType("src.gui.components.audio_player")
    audio_player.AudioPlayerBar = type("AudioPlayerBar", (), {})
    monkeypatch.setitem(sys.modules, "src.gui.components.audio_player", audio_player)

    combat_audio_panel = importlib.import_module("src.gui.task_panels.combat_audio_panel")

    temp_dir = tmp_path / "preview-temp"

    def fake_mkdtemp(prefix):
        temp_dir.mkdir()
        return str(temp_dir)

    panel = types.SimpleNamespace(
        _preview_temp_dir=None,
        _is_pure_audio=True,
        _input_selector=types.SimpleNamespace(path=lambda: "/input.wav"),
        _track_radio_group=types.SimpleNamespace(checkedId=lambda: 0),
        _bg_table=types.SimpleNamespace(currentRow=lambda: 0),
        _bg_files=[types.SimpleNamespace(path="/music.wav")],
        _volume_spin=types.SimpleNamespace(value=lambda: 0.6),
        _player=types.SimpleNamespace(play_file=Mock(), play_preview_file=Mock()),
        get_preview_btn_enabled=lambda: True,
    )
    panel._cleanup_preview_temp = lambda: combat_audio_panel.CombatAudioPanel._cleanup_preview_temp(panel)

    monkeypatch.setattr(combat_audio_panel.tempfile, "mkdtemp", fake_mkdtemp)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "build_preview_command", lambda *args, **kwargs: ["ffmpeg"])
    monkeypatch.setattr(
        combat_audio_panel.combat_audio,
        "run_ffmpeg_command",
        lambda *args, **kwargs: "preview failed",
    )
    monkeypatch.setattr(combat_audio_panel.QMessageBox, "critical", lambda *args, **kwargs: None)

    combat_audio_panel.CombatAudioPanel.preview_mix(panel)

    assert panel._preview_temp_dir is None
    assert not temp_dir.exists()


def test_preview_mix_uses_cached_mix_preview_when_present(qapp, monkeypatch, tmp_path):
    sys.modules.pop("src.gui.task_panels.combat_audio_panel", None)

    audio_player = types.ModuleType("src.gui.components.audio_player")
    audio_player.AudioPlayerBar = type("AudioPlayerBar", (), {})
    monkeypatch.setitem(sys.modules, "src.gui.components.audio_player", audio_player)

    combat_audio_panel = importlib.import_module("src.gui.task_panels.combat_audio_panel")

    input_path = tmp_path / "input.mp4"
    bg_path = tmp_path / "bg.aac"
    input_path.write_bytes(b"input")
    bg_path.write_bytes(b"bg")

    session = PreviewCacheSession(root_dir=str(tmp_path / "preview"))
    session.start()
    zero_start_path = session.get_cache_path(
        build_mix_preview_cache_key(str(input_path), 0, str(bg_path), 0.6, start_ms=0)
    )
    preview_key = build_mix_preview_cache_key(str(input_path), 0, str(bg_path), 0.6, start_ms=2500)
    preview_path = session.get_cache_path(preview_key)
    with open(preview_path, "wb") as f:
        f.write(b"cached-preview")
    monkeypatch.setattr(
        combat_audio_panel.combat_audio,
        "probe_audio_streams",
        lambda path: [object()] if path == preview_path else [],
    )

    panel = types.SimpleNamespace(
        _preview_cache=session,
        _preview_temp_dir=None,
        _is_pure_audio=False,
        _preview_start_ms=2500,
        _input_selector=types.SimpleNamespace(path=lambda: str(input_path)),
        _track_radio_group=types.SimpleNamespace(checkedId=lambda: 0),
        _bg_table=types.SimpleNamespace(currentRow=lambda: 0),
        _bg_files=[types.SimpleNamespace(path=str(bg_path))],
        _volume_spin=types.SimpleNamespace(value=lambda: 0.6),
        _player=types.SimpleNamespace(play_file=Mock(), play_preview_file=Mock()),
        get_preview_btn_enabled=lambda: True,
    )
    panel._cleanup_preview_temp = lambda: combat_audio_panel.CombatAudioPanel._cleanup_preview_temp(panel)

    build_extract = Mock(return_value=["ffmpeg", "extract"])
    def fake_build_preview_command(base_audio, bg_audio, volume, output_path, **kwargs):
        return ["ffmpeg", "preview", output_path]

    build_preview = Mock(side_effect=fake_build_preview_command)
    run_ffmpeg = Mock()
    monkeypatch.setattr(combat_audio_panel.combat_audio, "build_extract_command", build_extract)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "build_preview_command", build_preview)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "run_ffmpeg_command", run_ffmpeg)

    combat_audio_panel.CombatAudioPanel.preview_mix(panel)

    panel._player.play_preview_file.assert_called_once_with(preview_path, "试听混合")
    panel._player.play_file.assert_not_called()
    build_extract.assert_not_called()
    build_preview.assert_not_called()
    run_ffmpeg.assert_not_called()
    assert panel._preview_temp_dir is None
    assert zero_start_path != preview_path


def test_preview_mix_rebuilds_corrupted_cached_mix_preview(qapp, monkeypatch, tmp_path):
    sys.modules.pop("src.gui.task_panels.combat_audio_panel", None)

    audio_player = types.ModuleType("src.gui.components.audio_player")
    audio_player.AudioPlayerBar = type("AudioPlayerBar", (), {})
    monkeypatch.setitem(sys.modules, "src.gui.components.audio_player", audio_player)

    combat_audio_panel = importlib.import_module("src.gui.task_panels.combat_audio_panel")

    input_path = tmp_path / "input.aac"
    bg_path = tmp_path / "bg.aac"
    input_path.write_bytes(b"input")
    bg_path.write_bytes(b"bg")

    session = PreviewCacheSession(root_dir=str(tmp_path / "preview"))
    session.start()
    preview_key = build_mix_preview_cache_key(str(input_path), 0, str(bg_path), 0.6)
    preview_path = session.get_cache_path(preview_key)
    with open(preview_path, "wb") as f:
        f.write(b"broken-preview")

    original_remove = combat_audio_panel.os.remove
    remove_mock = Mock(side_effect=lambda path: original_remove(path))
    monkeypatch.setattr(combat_audio_panel.os, "remove", remove_mock)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "probe_audio_streams", lambda path: [])

    panel = types.SimpleNamespace(
        _preview_cache=session,
        _preview_temp_dir=None,
        _is_pure_audio=True,
        _input_selector=types.SimpleNamespace(path=lambda: str(input_path)),
        _track_radio_group=types.SimpleNamespace(checkedId=lambda: 0),
        _bg_table=types.SimpleNamespace(currentRow=lambda: 0),
        _bg_files=[types.SimpleNamespace(path=str(bg_path))],
        _volume_spin=types.SimpleNamespace(value=lambda: 0.6),
        _player=types.SimpleNamespace(play_file=Mock(), play_preview_file=Mock()),
        get_preview_btn_enabled=lambda: True,
    )
    panel._cleanup_preview_temp = lambda: combat_audio_panel.CombatAudioPanel._cleanup_preview_temp(panel)

    def fake_build_preview_command(base_audio, bg_audio, volume, output_path, **kwargs):
        return ["ffmpeg", "preview", output_path]

    build_preview = Mock(side_effect=fake_build_preview_command)

    def fake_run_ffmpeg_command(cmd, timeout, default_message):
        with open(cmd[-1], "wb") as f:
            f.write(b"rebuilt")
        return None

    run_ffmpeg = Mock(side_effect=fake_run_ffmpeg_command)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "build_preview_command", build_preview)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "run_ffmpeg_command", run_ffmpeg)

    combat_audio_panel.CombatAudioPanel.preview_mix(panel)

    remove_mock.assert_called_once_with(preview_path)
    build_preview.assert_called_once()
    run_ffmpeg.assert_called_once()
    panel._player.play_preview_file.assert_called_once_with(preview_path, "试听混合")
    panel._player.play_file.assert_not_called()
    assert os.path.exists(preview_path)
    with open(preview_path, "rb") as f:
        assert f.read() == b"rebuilt"


def test_preview_mix_rebuilds_corrupted_cached_base_audio_before_preview_generation(qapp, monkeypatch, tmp_path):
    sys.modules.pop("src.gui.task_panels.combat_audio_panel", None)

    audio_player = types.ModuleType("src.gui.components.audio_player")
    audio_player.AudioPlayerBar = type("AudioPlayerBar", (), {})
    monkeypatch.setitem(sys.modules, "src.gui.components.audio_player", audio_player)

    combat_audio_panel = importlib.import_module("src.gui.task_panels.combat_audio_panel")

    input_path = tmp_path / "input.mp4"
    bg_path = tmp_path / "bg.aac"
    input_path.write_bytes(b"input")
    bg_path.write_bytes(b"bg")

    session = PreviewCacheSession(root_dir=str(tmp_path / "preview"))
    session.start()
    preview_key = build_mix_preview_cache_key(str(input_path), 0, str(bg_path), 0.6, start_ms=2500)
    preview_path = session.get_cache_path(preview_key)
    zero_start_base_path = session.get_cache_path(build_base_audio_cache_key(str(input_path), 0, start_ms=0))
    base_key = build_base_audio_cache_key(str(input_path), 0, start_ms=2500)
    base_path = session.get_cache_path(base_key)
    with open(base_path, "wb") as f:
        f.write(b"broken-base")

    original_remove = combat_audio_panel.os.remove
    remove_mock = Mock(side_effect=lambda path: original_remove(path))
    monkeypatch.setattr(combat_audio_panel.os, "remove", remove_mock)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "probe_audio_streams", lambda path: [])

    panel = types.SimpleNamespace(
        _preview_cache=session,
        _preview_temp_dir=None,
        _is_pure_audio=False,
        _preview_start_ms=2500,
        _input_selector=types.SimpleNamespace(path=lambda: str(input_path)),
        _track_radio_group=types.SimpleNamespace(checkedId=lambda: 0),
        _bg_table=types.SimpleNamespace(currentRow=lambda: 0),
        _bg_files=[types.SimpleNamespace(path=str(bg_path))],
        _volume_spin=types.SimpleNamespace(value=lambda: 0.6),
        _player=types.SimpleNamespace(play_file=Mock(), play_preview_file=Mock()),
        get_preview_btn_enabled=lambda: True,
    )
    panel._cleanup_preview_temp = lambda: combat_audio_panel.CombatAudioPanel._cleanup_preview_temp(panel)

    def fake_build_extract_command(input_audio, stream_index, output_path, **kwargs):
        return ["ffmpeg", "extract", output_path]

    def fake_build_preview_command(base_audio, bg_audio, volume, output_path, **kwargs):
        return ["ffmpeg", "preview", output_path]

    build_extract = Mock(side_effect=fake_build_extract_command)
    build_preview = Mock(side_effect=fake_build_preview_command)

    def fake_run_ffmpeg_command(cmd, timeout, default_message):
        with open(cmd[-1], "wb") as f:
            f.write(cmd[-1].encode("utf-8"))
        return None

    run_ffmpeg = Mock(side_effect=fake_run_ffmpeg_command)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "build_extract_command", build_extract)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "build_preview_command", build_preview)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "run_ffmpeg_command", run_ffmpeg)

    combat_audio_panel.CombatAudioPanel.preview_mix(panel)

    remove_mock.assert_called_once_with(base_path)
    build_extract.assert_called_once()
    build_preview.assert_called_once()
    assert run_ffmpeg.call_count == 2
    panel._player.play_preview_file.assert_called_once_with(preview_path, "试听混合")
    panel._player.play_file.assert_not_called()
    assert os.path.exists(preview_path)
    assert os.path.exists(base_path)
    assert zero_start_base_path != base_path
    assert build_extract.call_args.kwargs == {
        "start_seconds": 2.5,
        "duration_seconds": combat_audio_panel.combat_audio.PREVIEW_DURATION_SECONDS,
    }
    assert build_preview.call_args.kwargs == {
        "start_seconds": 2.5,
        "base_start_seconds": 0.0,
        "bg_start_seconds": 2.5,
        "duration_seconds": combat_audio_panel.combat_audio.PREVIEW_DURATION_SECONDS,
    }
    with open(base_path, "rb") as f:
        assert f.read() == base_path.encode("utf-8")


def test_preview_mix_for_pure_audio_passes_preview_window_to_mix_helper(qapp, monkeypatch, tmp_path):
    sys.modules.pop("src.gui.task_panels.combat_audio_panel", None)

    audio_player = types.ModuleType("src.gui.components.audio_player")
    audio_player.AudioPlayerBar = type("AudioPlayerBar", (), {})
    monkeypatch.setitem(sys.modules, "src.gui.components.audio_player", audio_player)

    combat_audio_panel = importlib.import_module("src.gui.task_panels.combat_audio_panel")

    input_path = tmp_path / "input.aac"
    bg_path = tmp_path / "bg.aac"
    input_path.write_bytes(b"input")
    bg_path.write_bytes(b"bg")

    session = PreviewCacheSession(root_dir=str(tmp_path / "preview"))
    session.start()
    preview_path = session.get_cache_path(
        build_mix_preview_cache_key(str(input_path), 0, str(bg_path), 0.6, start_ms=2500)
    )

    monkeypatch.setattr(combat_audio_panel.combat_audio, "probe_audio_streams", lambda path: [])
    build_extract = Mock(side_effect=AssertionError("pure audio preview should not extract base audio"))

    def fake_build_preview_command(base_audio, bg_audio, volume, output_path, **kwargs):
        return ["ffmpeg", "preview", output_path]

    build_preview = Mock(side_effect=fake_build_preview_command)

    def fake_run_ffmpeg_command(cmd, timeout, default_message):
        with open(cmd[-1], "wb") as f:
            f.write(b"preview")
        return None

    run_ffmpeg = Mock(side_effect=fake_run_ffmpeg_command)

    panel = types.SimpleNamespace(
        _preview_cache=session,
        _preview_temp_dir=None,
        _is_pure_audio=True,
        _preview_start_ms=2500,
        _input_selector=types.SimpleNamespace(path=lambda: str(input_path)),
        _track_radio_group=types.SimpleNamespace(checkedId=lambda: 0),
        _bg_table=types.SimpleNamespace(currentRow=lambda: 0),
        _bg_files=[types.SimpleNamespace(path=str(bg_path))],
        _volume_spin=types.SimpleNamespace(value=lambda: 0.6),
        _player=types.SimpleNamespace(play_file=Mock(), play_preview_file=Mock()),
        get_preview_btn_enabled=lambda: True,
    )
    panel._cleanup_preview_temp = lambda: combat_audio_panel.CombatAudioPanel._cleanup_preview_temp(panel)

    monkeypatch.setattr(combat_audio_panel.combat_audio, "build_extract_command", build_extract)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "build_preview_command", build_preview)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "run_ffmpeg_command", run_ffmpeg)

    combat_audio_panel.CombatAudioPanel.preview_mix(panel)

    build_extract.assert_not_called()
    build_preview.assert_called_once_with(
        str(input_path),
        str(bg_path),
        0.6,
        preview_path,
        start_seconds=2.5,
        base_start_seconds=2.5,
        bg_start_seconds=2.5,
        duration_seconds=combat_audio_panel.combat_audio.PREVIEW_DURATION_SECONDS,
    )
    run_ffmpeg.assert_called_once()
    panel._player.play_preview_file.assert_called_once_with(preview_path, "试听混合")
    panel._player.play_file.assert_not_called()


def test_preview_mix_wraps_bg_start_when_preview_offset_exceeds_bg_duration(qapp, monkeypatch, tmp_path):
    sys.modules.pop("src.gui.task_panels.combat_audio_panel", None)

    audio_player = types.ModuleType("src.gui.components.audio_player")
    audio_player.AudioPlayerBar = type("AudioPlayerBar", (), {})
    monkeypatch.setitem(sys.modules, "src.gui.components.audio_player", audio_player)

    combat_audio_panel = importlib.import_module("src.gui.task_panels.combat_audio_panel")

    input_path = tmp_path / "input.mp4"
    bg_path = tmp_path / "bg.aac"
    input_path.write_bytes(b"input")
    bg_path.write_bytes(b"bg")

    session = PreviewCacheSession(root_dir=str(tmp_path / "preview"))
    session.start()
    preview_path = session.get_cache_path(
        build_mix_preview_cache_key(str(input_path), 0, str(bg_path), 0.6, start_ms=125_000)
    )
    base_path = session.get_cache_path(
        build_base_audio_cache_key(str(input_path), 0, start_ms=125_000)
    )

    monkeypatch.setattr(combat_audio_panel.combat_audio, "probe_audio_streams", lambda path: [])

    def fake_build_extract_command(input_audio, stream_index, output_path, **kwargs):
        return ["ffmpeg", "extract", output_path]

    def fake_build_preview_command(base_audio, bg_audio, volume, output_path, **kwargs):
        return ["ffmpeg", "preview", output_path]

    build_extract = Mock(side_effect=fake_build_extract_command)
    build_preview = Mock(side_effect=fake_build_preview_command)

    def fake_run_ffmpeg_command(cmd, timeout, default_message):
        with open(cmd[-1], "wb") as f:
            f.write(b"preview")
        return None

    run_ffmpeg = Mock(side_effect=fake_run_ffmpeg_command)

    panel = types.SimpleNamespace(
        _preview_cache=session,
        _preview_temp_dir=None,
        _is_pure_audio=False,
        _preview_start_ms=125_000,
        _input_selector=types.SimpleNamespace(path=lambda: str(input_path)),
        _track_radio_group=types.SimpleNamespace(checkedId=lambda: 0),
        _bg_table=types.SimpleNamespace(currentRow=lambda: 0),
        _bg_files=[types.SimpleNamespace(path=str(bg_path), duration=60.0)],
        _volume_spin=types.SimpleNamespace(value=lambda: 0.6),
        _player=types.SimpleNamespace(play_file=Mock(), play_preview_file=Mock()),
        get_preview_btn_enabled=lambda: True,
    )
    panel._cleanup_preview_temp = lambda: combat_audio_panel.CombatAudioPanel._cleanup_preview_temp(panel)

    monkeypatch.setattr(combat_audio_panel.combat_audio, "build_extract_command", build_extract)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "build_preview_command", build_preview)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "run_ffmpeg_command", run_ffmpeg)

    combat_audio_panel.CombatAudioPanel.preview_mix(panel)

    build_extract.assert_called_once_with(
        str(input_path),
        0,
        base_path,
        start_seconds=125.0,
        duration_seconds=combat_audio_panel.combat_audio.PREVIEW_DURATION_SECONDS,
    )
    build_preview.assert_called_once_with(
        base_path,
        str(bg_path),
        0.6,
        preview_path,
        start_seconds=125.0,
        base_start_seconds=0.0,
        bg_start_seconds=5.0,
        duration_seconds=combat_audio_panel.combat_audio.PREVIEW_DURATION_SECONDS,
    )
    run_ffmpeg.assert_called()
    panel._player.play_preview_file.assert_called_once_with(preview_path, "试听混合")
    panel._player.play_file.assert_not_called()


def test_preview_mix_reuses_cached_base_audio_across_different_bgm_selections(qapp, monkeypatch, tmp_path):
    sys.modules.pop("src.gui.task_panels.combat_audio_panel", None)

    audio_player = types.ModuleType("src.gui.components.audio_player")
    audio_player.AudioPlayerBar = type("AudioPlayerBar", (), {})
    monkeypatch.setitem(sys.modules, "src.gui.components.audio_player", audio_player)

    combat_audio_panel = importlib.import_module("src.gui.task_panels.combat_audio_panel")

    input_path = tmp_path / "input.mp4"
    bg1_path = tmp_path / "bg1.aac"
    bg2_path = tmp_path / "bg2.aac"
    input_path.write_bytes(b"input")
    bg1_path.write_bytes(b"bg-one")
    bg2_path.write_bytes(b"bg-two")

    session = PreviewCacheSession(root_dir=str(tmp_path / "preview"))
    session.start()
    base_path = session.get_cache_path(build_base_audio_cache_key(str(input_path), 0))

    current_row = {"value": 0}
    panel = types.SimpleNamespace(
        _preview_cache=session,
        _preview_temp_dir=None,
        _is_pure_audio=False,
        _input_selector=types.SimpleNamespace(path=lambda: str(input_path)),
        _track_radio_group=types.SimpleNamespace(checkedId=lambda: 0),
        _bg_table=types.SimpleNamespace(currentRow=lambda: current_row["value"]),
        _bg_files=[
            types.SimpleNamespace(path=str(bg1_path)),
            types.SimpleNamespace(path=str(bg2_path)),
        ],
        _volume_spin=types.SimpleNamespace(value=lambda: 0.6),
        _player=types.SimpleNamespace(play_file=Mock(), play_preview_file=Mock()),
        get_preview_btn_enabled=lambda: True,
    )
    panel._cleanup_preview_temp = lambda: combat_audio_panel.CombatAudioPanel._cleanup_preview_temp(panel)

    extract_outputs: list[str] = []
    preview_outputs: list[str] = []

    monkeypatch.setattr(
        combat_audio_panel.combat_audio,
        "probe_audio_streams",
        lambda path: [object()] if path == base_path and os.path.exists(path) else [],
    )

    def fake_build_extract_command(src, stream_index, output_path, **kwargs):
        extract_outputs.append(output_path)
        return ["ffmpeg", "extract", output_path]

    def fake_build_preview_command(base_audio, bg_audio, volume, output_path, **kwargs):
        preview_outputs.append(output_path)
        return ["ffmpeg", "preview", base_audio, bg_audio, str(volume), output_path]

    def fake_run_ffmpeg_command(cmd, timeout, default_message):
        output_path = cmd[-1]
        with open(output_path, "wb") as f:
            f.write(output_path.encode("utf-8"))
        return None

    build_extract = Mock(side_effect=fake_build_extract_command)
    build_preview = Mock(side_effect=fake_build_preview_command)
    run_ffmpeg = Mock(side_effect=fake_run_ffmpeg_command)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "build_extract_command", build_extract)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "build_preview_command", build_preview)
    monkeypatch.setattr(combat_audio_panel.combat_audio, "run_ffmpeg_command", run_ffmpeg)

    combat_audio_panel.CombatAudioPanel.preview_mix(panel)
    current_row["value"] = 1
    combat_audio_panel.CombatAudioPanel.preview_mix(panel)

    assert build_extract.call_count == 1
    assert build_preview.call_count == 2
    assert run_ffmpeg.call_count == 3
    assert len(extract_outputs) == 1
    assert len(preview_outputs) == 2
    assert os.path.dirname(extract_outputs[0]) == session.session_dir
    assert os.path.dirname(preview_outputs[0]) == session.session_dir
    assert os.path.dirname(preview_outputs[1]) == session.session_dir
    assert preview_outputs[0] != preview_outputs[1]
