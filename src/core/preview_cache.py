import hashlib
import os
import shutil
import uuid

from src.core.data_dir import resolve_data_dir


def _build_file_fingerprint(input_path: str) -> str:
    try:
        stat_result = os.stat(input_path)
    except OSError:
        return "fingerprint=missing"

    return f"fingerprint=mtime_ns={stat_result.st_mtime_ns},size={stat_result.st_size}"


def build_input_track_cache_key(input_path: str, audio_position: int) -> str:
    return "|".join([
        "kind=input_track",
        f"input={input_path}",
        _build_file_fingerprint(input_path),
        f"stream={audio_position}",
        "version=v2",
    ])


def build_base_audio_cache_key(input_path: str, audio_position: int) -> str:
    return "|".join([
        "kind=base_audio",
        f"input={input_path}",
        _build_file_fingerprint(input_path),
        f"stream={audio_position}",
        "version=v1",
    ])


def build_mix_preview_cache_key(
    input_path: str,
    audio_position: int,
    bg_path: str,
    volume: float,
) -> str:
    return "|".join([
        "kind=mix_preview",
        f"input={input_path}",
        _build_file_fingerprint(input_path),
        f"stream={audio_position}",
        f"bg={bg_path}",
        _build_file_fingerprint(bg_path),
        f"volume={volume!r}",
        "version=v1",
    ])


class PreviewCacheSession:
    def __init__(self, root_dir: str | None = None):
        self._root_dir = root_dir or os.path.join(resolve_data_dir(), "cache", "preview")
        self._session_dir: str | None = None

    @property
    def session_dir(self) -> str:
        if self._session_dir is None:
            raise RuntimeError("Preview cache session has not been started")
        return self._session_dir

    def start(self) -> str:
        os.makedirs(self._root_dir, exist_ok=True)
        for entry in os.listdir(self._root_dir):
            entry_path = os.path.join(self._root_dir, entry)
            if os.path.isdir(entry_path):
                shutil.rmtree(entry_path)
        self._session_dir = os.path.join(self._root_dir, uuid.uuid4().hex)
        os.makedirs(self._session_dir, exist_ok=True)
        return self._session_dir

    def get_cache_path(self, cache_key: str, suffix: str = ".aac") -> str:
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return os.path.join(self.session_dir, f"{digest}{suffix}")

    def cleanup(self) -> None:
        if self._session_dir and os.path.isdir(self._session_dir):
            shutil.rmtree(self._session_dir)
        self._session_dir = None
