import json
import os
from dataclasses import dataclass

from src.core.data_dir import get_settings_path


@dataclass
class AppSettings:
    mkvmerge_path: str | None = None

    def to_dict(self) -> dict[str, str]:
        return {"mkvmerge_path": self.mkvmerge_path or ""}

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        mkvmerge_path = data.get("mkvmerge_path") or None
        return cls(mkvmerge_path=mkvmerge_path)


def load_settings(path: str | None = None) -> AppSettings:
    settings_path = path or get_settings_path()

    try:
        with open(settings_path, "r", encoding="utf-8") as settings_file:
            data = json.load(settings_file)
    except (OSError, json.JSONDecodeError):
        return AppSettings()

    if not isinstance(data, dict):
        return AppSettings()

    return AppSettings.from_dict(data)


def save_settings(settings: AppSettings, path: str | None = None) -> None:
    settings_path = path or get_settings_path()
    parent_dir = os.path.dirname(settings_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with open(settings_path, "w", encoding="utf-8") as settings_file:
        json.dump(settings.to_dict(), settings_file, ensure_ascii=False, indent=2)
