import pytest
from PyQt6.QtWidgets import QApplication, QRadioButton, QScrollArea, QWidget
from unittest.mock import Mock

from src.core.processors.combat_audio import AudioStreamInfo
from src.gui.components.preview_start_cell import PreviewStartCell
from src.gui.task_panels import combat_audio_panel


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def panel(monkeypatch, qapp):
    class DummyAudioPlayerBar(QWidget):
        def __init__(self, *args, **kwargs):
            super().__init__()

    monkeypatch.setattr(combat_audio_panel, "AudioPlayerBar", DummyAudioPlayerBar)

    widget = combat_audio_panel.CombatAudioPanel()
    widget.show()
    return widget


def _make_stream(index: int, audio_position: int, codec: str, language: str | None = None) -> AudioStreamInfo:
    return AudioStreamInfo(
        index=index,
        audio_position=audio_position,
        codec=codec,
        sample_rate=48_000,
        channels=2,
        channel_layout="stereo",
        language=language,
    )


def _radio_for_row(panel, row: int) -> QRadioButton:
    return panel._tracks_table.cellWidget(row, 0).findChild(QRadioButton)


def _preview_cell(panel, row: int) -> PreviewStartCell:
    return panel._tracks_table.cellWidget(row, 3)


def test_tracks_table_adds_preview_start_column_and_activates_only_selected_row(panel):
    panel._input_duration = 123.4
    panel._input_streams = [
        _make_stream(index=1, audio_position=0, codec="aac"),
        _make_stream(index=2, audio_position=1, codec="mp3"),
    ]

    panel._refresh_tracks_table()

    assert panel._tracks_table.columnCount() == 7
    assert isinstance(_preview_cell(panel, 0), PreviewStartCell)
    assert isinstance(_preview_cell(panel, 1), PreviewStartCell)
    assert _preview_cell(panel, 0).duration_ms() == 123_400
    assert _preview_cell(panel, 1).duration_ms() == 123_400
    assert _preview_cell(panel, 0).value_ms() == 0
    assert _preview_cell(panel, 1).value_ms() == 0
    assert _preview_cell(panel, 0).is_active()
    assert not _preview_cell(panel, 1).is_active()


def test_preview_start_state_follows_selected_track_and_refreshes_active_cell(panel):
    panel._input_duration = 90.0
    panel._input_streams = [
        _make_stream(index=1, audio_position=0, codec="aac"),
        _make_stream(index=2, audio_position=1, codec="mp3"),
    ]

    panel._refresh_tracks_table()

    first_cell = _preview_cell(panel, 0)
    second_cell = _preview_cell(panel, 1)

    first_cell._slider.setValue(17_000)

    assert panel._preview_start_ms == 17_000
    assert first_cell.value_ms() == 17_000

    _radio_for_row(panel, 1).click()

    assert panel._track_radio_group.checkedId() == 1
    assert not first_cell.is_active()
    assert second_cell.is_active()
    assert second_cell.duration_ms() == 90_000
    assert second_cell.value_ms() == 17_000


def test_refresh_tracks_table_preserves_nondefault_selection_when_still_available(panel):
    panel._input_duration = 60.0
    panel._input_streams = [
        _make_stream(index=1, audio_position=0, codec="aac"),
        _make_stream(index=2, audio_position=1, codec="mp3"),
    ]

    panel._refresh_tracks_table()
    _radio_for_row(panel, 1).click()

    panel._refresh_tracks_table()

    assert panel._track_radio_group.checkedId() == 1
    assert _radio_for_row(panel, 1).isChecked()
    assert not _radio_for_row(panel, 0).isChecked()


def test_reconcile_bg_order_after_drop_keeps_table_order(panel):
    class DummyItem:
        def __init__(self, path: str):
            self._path = path

        def data(self, role):
            return self._path

    class DummyTable:
        def __init__(self, paths: list[str]):
            self._paths = paths

        def rowCount(self):
            return len(self._paths)

        def item(self, row: int, column: int):
            if column != 1:
                return None
            return DummyItem(self._paths[row])

    panel._bg_files = [
        type("Bg", (), {"path": "/music/01.aac", "filename": "01.aac"})(),
        type("Bg", (), {"path": "/music/02.aac", "filename": "02.aac"})(),
        type("Bg", (), {"path": "/music/03.aac", "filename": "03.aac"})(),
    ]
    panel._bg_table = DummyTable(["/music/02.aac", "/music/03.aac", "/music/01.aac"])
    panel._refresh_bg_table = Mock()

    panel._reconcile_bg_order_after_drop()

    assert [item.path for item in panel._bg_files] == [
        "/music/02.aac",
        "/music/03.aac",
        "/music/01.aac",
    ]
    panel._refresh_bg_table.assert_called_once_with()


def test_reconcile_bg_order_after_drop_uses_visual_header_order(panel):
    class DummyItem:
        def __init__(self, path: str):
            self._path = path

        def data(self, role):
            return self._path

    class DummyHeader:
        def __init__(self, visual_to_logical: list[int]):
            self._visual_to_logical = visual_to_logical

        def logicalIndex(self, visual_index: int):
            return self._visual_to_logical[visual_index]

    class DummyTable:
        def __init__(self, paths: list[str], visual_to_logical: list[int]):
            self._paths = paths
            self._header = DummyHeader(visual_to_logical)

        def rowCount(self):
            return len(self._paths)

        def item(self, row: int, column: int):
            if column != 1:
                return None
            return DummyItem(self._paths[row])

        def verticalHeader(self):
            return self._header

    panel._bg_files = [
        type("Bg", (), {"path": "/music/01.aac", "filename": "01.aac"})(),
        type("Bg", (), {"path": "/music/02.aac", "filename": "02.aac"})(),
        type("Bg", (), {"path": "/music/03.aac", "filename": "03.aac"})(),
    ]
    panel._bg_table = DummyTable(
        ["/music/01.aac", "/music/02.aac", "/music/03.aac"],
        [1, 2, 0],
    )
    panel._refresh_bg_table = Mock()

    panel._reconcile_bg_order_after_drop()

    assert [item.path for item in panel._bg_files] == [
        "/music/02.aac",
        "/music/03.aac",
        "/music/01.aac",
    ]
    panel._refresh_bg_table.assert_called_once_with()


def test_tracks_table_shows_language_tag_or_und(panel):
    panel._input_duration = 30.0
    panel._input_streams = [
        _make_stream(index=1, audio_position=0, codec="aac", language="jpn"),
        _make_stream(index=2, audio_position=1, codec="ac3", language=None),
    ]

    panel._refresh_tracks_table()

    assert panel._tracks_table.horizontalHeaderItem(5).text() == "语言"
    assert panel._tracks_table.item(0, 5).text() == "jpn"
    assert panel._tracks_table.item(1, 5).text() == "und"


def test_secondary_group_stays_disabled_without_input_even_when_boxed_checked(panel):
    panel._is_pure_audio = False
    panel._boxed_checkbox.setChecked(False)
    panel._update_param_states()

    assert not panel._boxed_checkbox.isEnabled()
    assert not panel._boxed_checkbox.isChecked()
    assert not panel._secondary_group.isEnabled()

    panel._boxed_checkbox.setChecked(True)
    panel._update_param_states()

    assert not panel._boxed_checkbox.isEnabled()
    assert not panel._boxed_checkbox.isChecked()
    assert not panel._secondary_group.isEnabled()


def test_secondary_group_disables_when_input_path_is_cleared(panel, tmp_path):
    input_path = tmp_path / "main.mkv"
    input_path.write_bytes(b"")
    panel._input_selector._edit.setText(str(input_path))
    panel._is_pure_audio = False
    panel._boxed_checkbox.setChecked(True)
    panel._update_param_states()

    assert panel._boxed_checkbox.isEnabled()
    assert panel._secondary_group.isEnabled()

    panel._input_selector._edit.setText("")
    panel._update_param_states()

    assert not panel._boxed_checkbox.isEnabled()
    assert not panel._boxed_checkbox.isChecked()
    assert not panel._secondary_group.isEnabled()


def test_secondary_group_disables_when_input_path_is_missing(panel):
    panel._input_selector._edit.setText("/video/missing-main.mkv")
    panel._is_pure_audio = False
    panel._boxed_checkbox.setChecked(True)
    panel._update_param_states()

    assert not panel._boxed_checkbox.isEnabled()
    assert not panel._boxed_checkbox.isChecked()
    assert not panel._secondary_group.isEnabled()


def test_secondary_group_enabled_only_for_boxed_video_input(panel, tmp_path):
    input_path = tmp_path / "main.mkv"
    input_path.write_bytes(b"")
    panel._input_selector._edit.setText(str(input_path))
    panel._is_pure_audio = False
    panel._boxed_checkbox.setChecked(True)
    panel._update_param_states()

    assert panel._boxed_checkbox.isEnabled()
    assert panel._boxed_checkbox.isChecked()
    assert panel._secondary_group.isEnabled()

    panel._is_pure_audio = True
    panel._update_param_states()

    assert not panel._boxed_checkbox.isEnabled()
    assert not panel._secondary_group.isEnabled()
    assert not panel._boxed_checkbox.isChecked()


def test_secondary_video_order_is_written_to_config_in_current_order(panel, tmp_path):
    input_path = tmp_path / "main.mkv"
    input_path.write_bytes(b"")
    panel._input_selector._edit.setText(str(input_path))
    panel._audio_dir_selector._edit.setText("/audio")
    panel._is_pure_audio = False
    panel._boxed_checkbox.setChecked(True)
    panel._secondary_video_paths = [
        "/video/part2.mkv",
        "/video/part3.mkv",
    ]

    config = panel.build_config()

    assert config.secondary_video_paths == [
        "/video/part2.mkv",
        "/video/part3.mkv",
    ]


def test_secondary_video_config_clears_when_not_boxed_or_pure_audio(panel):
    panel._input_selector._edit.setText("/video/main.mkv")
    panel._audio_dir_selector._edit.setText("/audio")
    panel._secondary_video_paths = ["/video/part2.mkv"]

    panel._is_pure_audio = False
    panel._boxed_checkbox.setChecked(False)

    assert panel.build_config().secondary_video_paths == []

    panel._is_pure_audio = True
    panel._boxed_checkbox.setChecked(True)
    panel._update_param_states()

    assert panel.build_config().secondary_video_paths == []


def test_set_mux_settings_values_are_included_in_config(panel):
    panel._input_selector._edit.setText("/video/main.mkv")
    panel._audio_dir_selector._edit.setText("/audio")

    panel.set_mux_settings(mkvmerge_path="/opt/bin/mkvmerge", mux_backend="mkvmerge")

    config = panel.build_config()

    assert config.mkvmerge_path == "/opt/bin/mkvmerge"
    assert config.mux_backend == "mkvmerge"


def test_secondary_video_move_remove_and_clear_helpers_update_list(panel):
    panel._secondary_video_paths = [
        "/video/part1.mkv",
        "/video/part2.mkv",
        "/video/part3.mkv",
    ]

    panel._move_secondary_video(2, -1)
    assert panel._secondary_video_paths == [
        "/video/part1.mkv",
        "/video/part3.mkv",
        "/video/part2.mkv",
    ]

    panel._move_secondary_video(0, -1)
    assert panel._secondary_video_paths == [
        "/video/part1.mkv",
        "/video/part3.mkv",
        "/video/part2.mkv",
    ]

    panel._remove_secondary_video(1)
    assert panel._secondary_video_paths == [
        "/video/part1.mkv",
        "/video/part2.mkv",
    ]

    panel._clear_secondary_videos()
    assert panel._secondary_video_paths == []


def test_file_info_stays_above_scroll_limited_secondary_video_list(panel):
    upper_layout = panel.layout().itemAt(0).layout()
    left_layout = upper_layout.itemAt(0).layout()

    assert isinstance(panel._secondary_scroll, QScrollArea)
    assert panel._secondary_scroll.maximumHeight() > 0
    assert panel._secondary_scroll.maximumHeight() <= 180
    assert left_layout.indexOf(panel._info_group) < left_layout.indexOf(panel._secondary_group)


def test_validate_boxed_video_reports_missing_secondary_video(panel, tmp_path, monkeypatch):
    input_path = tmp_path / "main.mkv"
    input_path.write_bytes(b"")
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    audio_path = audio_dir / "song.aac"
    audio_path.write_bytes(b"")
    missing_secondary = tmp_path / "missing-secondary.mkv"

    panel._input_selector._edit.setText(str(input_path))
    panel._audio_dir_selector._edit.setText(str(audio_dir))
    panel._is_pure_audio = False
    panel._boxed_checkbox.setChecked(True)
    panel._secondary_video_paths = [str(missing_secondary)]
    panel._bg_files = [type("Bg", (), {"path": str(audio_path), "filename": "song.aac", "duration": 0.0})()]
    original_is_pure_audio = combat_audio_panel.combat_audio.is_pure_audio
    monkeypatch.setattr(
        combat_audio_panel.combat_audio,
        "is_pure_audio",
        lambda path: original_is_pure_audio(path) and path != str(input_path),
    )

    ok, count, err = panel.validate()

    assert not ok
    assert count == 0
    assert err == f"副视频不存在: {missing_secondary}"


def test_validate_boxed_video_reports_non_video_secondary(panel, tmp_path, monkeypatch):
    input_path = tmp_path / "main.mkv"
    input_path.write_bytes(b"")
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    audio_path = audio_dir / "song.aac"
    audio_path.write_bytes(b"")
    secondary_path = tmp_path / "secondary.txt"
    secondary_path.write_text("not video")

    panel._input_selector._edit.setText(str(input_path))
    panel._audio_dir_selector._edit.setText(str(audio_dir))
    panel._is_pure_audio = False
    panel._boxed_checkbox.setChecked(True)
    panel._secondary_video_paths = [str(secondary_path)]
    panel._bg_files = [type("Bg", (), {"path": str(audio_path), "filename": "song.aac", "duration": 0.0})()]
    original_is_pure_audio = combat_audio_panel.combat_audio.is_pure_audio
    monkeypatch.setattr(
        combat_audio_panel.combat_audio,
        "is_pure_audio",
        lambda path: original_is_pure_audio(path) and path != str(input_path),
    )
    monkeypatch.setattr(combat_audio_panel.combat_audio, "has_video_stream", lambda path: False)

    ok, count, err = panel.validate()

    assert not ok
    assert count == 0
    assert err == f"副视频不是视频文件: {secondary_path}"


def test_validate_boxed_video_counts_mkv_outputs(panel, tmp_path, monkeypatch):
    input_path = tmp_path / "main.mkv"
    input_path.write_bytes(b"")
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    audio_path = audio_dir / "song.aac"
    audio_path.write_bytes(b"")
    secondaries = [tmp_path / "secondary-1.mkv", tmp_path / "secondary-2.mkv"]
    for path in secondaries:
        path.write_bytes(b"")

    panel._input_selector._edit.setText(str(input_path))
    panel._audio_dir_selector._edit.setText(str(audio_dir))
    panel._is_pure_audio = False
    panel._boxed_checkbox.setChecked(True)
    panel._secondary_video_paths = [str(path) for path in secondaries]
    panel._bg_files = [type("Bg", (), {"path": str(audio_path), "filename": "song.aac", "duration": 0.0})()]
    original_is_pure_audio = combat_audio_panel.combat_audio.is_pure_audio
    monkeypatch.setattr(
        combat_audio_panel.combat_audio,
        "is_pure_audio",
        lambda path: original_is_pure_audio(path) and path != str(input_path),
    )
    monkeypatch.setattr(combat_audio_panel.combat_audio, "has_video_stream", lambda path: True)

    ok, count, err = panel.validate()

    assert ok
    assert count == 3
    assert err is None


def test_validate_non_boxed_uses_audio_count(panel, tmp_path):
    input_path = tmp_path / "main.mkv"
    input_path.write_bytes(b"")
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    audio_paths = [audio_dir / "song-1.aac", audio_dir / "song-2.aac"]
    for path in audio_paths:
        path.write_bytes(b"")

    panel._input_selector._edit.setText(str(input_path))
    panel._audio_dir_selector._edit.setText(str(audio_dir))
    panel._is_pure_audio = False
    panel._boxed_checkbox.setChecked(False)
    panel._bg_files = [
        type("Bg", (), {"path": str(path), "filename": path.name, "duration": 0.0})()
        for path in audio_paths
    ]

    ok, count, err = panel.validate()

    assert ok
    assert count == 2
    assert err is None
