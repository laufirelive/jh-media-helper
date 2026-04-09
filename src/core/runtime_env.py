import shutil
import sys


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_missing_ffmpeg_tools() -> list[str]:
    missing: list[str] = []
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            missing.append(tool)
    return missing


def has_required_ffmpeg_tools() -> bool:
    return get_missing_ffmpeg_tools() == []
