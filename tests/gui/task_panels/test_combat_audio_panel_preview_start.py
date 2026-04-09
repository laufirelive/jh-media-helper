import pytest
from PyQt6.QtWidgets import QApplication, QRadioButton, QWidget
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


def _make_stream(index: int, audio_position: int, codec: str) -> AudioStreamInfo:
    return AudioStreamInfo(
        index=index,
        audio_position=audio_position,
        codec=codec,
        sample_rate=48_000,
        channels=2,
        channel_layout="stereo",
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
