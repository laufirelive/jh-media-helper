import pytest
from PyQt6.QtWidgets import QApplication

from src.core.app_settings import AppSettings
from src.gui import settings_tab
from src.gui.settings_tab import SettingsTab


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_loads_saved_mkvmerge_path_and_shows_detected_status(qapp, monkeypatch):
    monkeypatch.setattr(
        settings_tab,
        "load_settings",
        lambda: AppSettings(mkvmerge_path="/opt/bin/mkvmerge"),
        raising=False,
    )
    monkeypatch.setattr(
        settings_tab,
        "resolve_mkvmerge_path",
        lambda path: "/opt/bin/mkvmerge",
        raising=False,
    )

    tab = SettingsTab()

    assert tab._mkvmerge_edit.text() == "/opt/bin/mkvmerge"
    assert tab._mkvmerge_status.text() == "已检测：/opt/bin/mkvmerge"


def test_detect_mkvmerge_sets_edit_text_and_saves_settings(qapp, monkeypatch):
    saved = []
    monkeypatch.setattr(settings_tab, "load_settings", lambda: AppSettings(), raising=False)
    monkeypatch.setattr(
        settings_tab,
        "save_settings",
        lambda settings: saved.append(settings),
        raising=False,
    )
    monkeypatch.setattr(
        settings_tab,
        "resolve_mkvmerge_path",
        lambda path: "/usr/local/bin/mkvmerge",
        raising=False,
    )

    tab = SettingsTab()
    tab._detect_mkvmerge()

    assert tab._mkvmerge_edit.text() == "/usr/local/bin/mkvmerge"
    assert saved == [AppSettings(mkvmerge_path="/usr/local/bin/mkvmerge")]
    assert tab._mkvmerge_status.text() == "已检测：/usr/local/bin/mkvmerge"


def test_manual_edit_save_trims_path_and_updates_status(qapp, monkeypatch):
    saved = []
    monkeypatch.setattr(settings_tab, "load_settings", lambda: AppSettings(), raising=False)
    monkeypatch.setattr(
        settings_tab,
        "save_settings",
        lambda settings: saved.append(settings),
        raising=False,
    )
    monkeypatch.setattr(
        settings_tab,
        "resolve_mkvmerge_path",
        lambda path: "/tools/mkvmerge" if path == "/tools/mkvmerge" else None,
        raising=False,
    )

    tab = SettingsTab()
    tab._mkvmerge_edit.setText("  /tools/mkvmerge  ")
    tab._save_mkvmerge_path()

    assert tab._mkvmerge_edit.text() == "  /tools/mkvmerge  "
    assert saved == [AppSettings(mkvmerge_path="/tools/mkvmerge")]
    assert tab._mkvmerge_status.text() == "已检测：/tools/mkvmerge"


def test_choose_mkvmerge_saves_selected_path(qapp, monkeypatch):
    saved = []
    monkeypatch.setattr(settings_tab, "load_settings", lambda: AppSettings(), raising=False)
    monkeypatch.setattr(
        settings_tab,
        "save_settings",
        lambda settings: saved.append(settings),
        raising=False,
    )
    monkeypatch.setattr(
        settings_tab,
        "resolve_mkvmerge_path",
        lambda path: "/Applications/MKVToolNix.app/mkvmerge"
        if path == "/Applications/MKVToolNix.app/mkvmerge"
        else None,
        raising=False,
    )
    monkeypatch.setattr(
        settings_tab.QFileDialog,
        "getOpenFileName",
        lambda *args: ("/Applications/MKVToolNix.app/mkvmerge", ""),
        raising=False,
    )

    tab = SettingsTab()
    tab._choose_mkvmerge()

    assert tab._mkvmerge_edit.text() == "/Applications/MKVToolNix.app/mkvmerge"
    assert saved == [AppSettings(mkvmerge_path="/Applications/MKVToolNix.app/mkvmerge")]
    assert tab._mkvmerge_status.text() == "已检测：/Applications/MKVToolNix.app/mkvmerge"
