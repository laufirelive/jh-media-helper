import json

from src.core.app_settings import AppSettings, load_settings, save_settings


def test_app_settings_defaults():
    settings = AppSettings()

    assert settings.mkvmerge_path is None


def test_app_settings_round_trip(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings = AppSettings(mkvmerge_path="/opt/bin/mkvmerge")

    save_settings(settings, path=str(settings_path))
    restored = load_settings(path=str(settings_path))

    assert restored == settings


def test_load_settings_returns_defaults_when_file_missing(tmp_path):
    settings_path = tmp_path / "missing.json"

    settings = load_settings(path=str(settings_path))

    assert settings == AppSettings()


def test_load_settings_ignores_unknown_keys(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"mkvmerge_path": "/bin/mkvmerge", "unknown": "ignored"}),
        encoding="utf-8",
    )

    settings = load_settings(path=str(settings_path))

    assert settings == AppSettings(mkvmerge_path="/bin/mkvmerge")


def test_load_settings_treats_empty_mkvmerge_path_as_none(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"mkvmerge_path": ""}), encoding="utf-8")

    settings = load_settings(path=str(settings_path))

    assert settings == AppSettings(mkvmerge_path=None)
