import os
import shutil
from enum import Enum


class MuxBackend(Enum):
    MKVMERGE = "mkvmerge"
    FFMPEG = "ffmpeg"


def _is_executable_file(path: str | None) -> bool:
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def resolve_mkvmerge_path(manual_path: str | None = None) -> str | None:
    if _is_executable_file(manual_path):
        return manual_path

    return shutil.which("mkvmerge")


def resolve_mux_backend(
    requested: str = "auto",
    mkvmerge_path: str | None = None,
) -> tuple[MuxBackend, str | None]:
    if requested == "ffmpeg":
        return MuxBackend.FFMPEG, None

    resolved_path = resolve_mkvmerge_path(mkvmerge_path)
    if requested in {"auto", "mkvmerge"} and resolved_path:
        return MuxBackend.MKVMERGE, resolved_path

    return MuxBackend.FFMPEG, None
