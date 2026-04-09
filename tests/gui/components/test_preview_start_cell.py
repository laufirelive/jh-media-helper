import pytest
from PyQt6.QtWidgets import QApplication

from src.gui.components.preview_start_cell import PreviewStartCell


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def cell(qapp):
    return PreviewStartCell()


def test_format_time_returns_mm_ss(cell):
    assert cell.format_time(0) == "00:00:00"
    assert cell.format_time(1_000) == "00:00:01"
    assert cell.format_time(61_000) == "00:01:01"
    assert cell.format_time(3_723_000) == "01:02:03"


def test_initial_state_is_inactive(cell):
    assert not cell.is_active()
    assert not cell.is_slider_enabled()
    assert cell.start_time_text() == "00:00:00"


def test_set_duration_and_value_updates_slider_and_label(cell):
    cell.set_duration_ms(90_000)
    cell.set_value_ms(23_000)

    assert cell.duration_ms() == 90_000
    assert cell.value_ms() == 23_000
    assert cell.start_time_text() == "00:00:23"
    assert cell._slider.maximum() == 90_000
    assert cell._slider.value() == 23_000


def test_active_state_controls_slider_enabled(cell):
    cell.set_duration_ms(10_000)

    cell.set_active(True)
    assert cell.is_active()
    assert cell.is_slider_enabled()

    cell.set_active(False)
    assert not cell.is_active()
    assert not cell.is_slider_enabled()


def test_slider_movement_updates_value_and_label(cell):
    cell.set_duration_ms(120_000)
    cell.set_active(True)

    cell._slider.setValue(45_000)

    assert cell.value_ms() == 45_000
    assert cell.start_time_text() == "00:00:45"
