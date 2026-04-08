import os
from dataclasses import dataclass

PURE_AUDIO_EXTENSIONS = {".aac", ".mp3", ".wav", ".flac"}


@dataclass
class AudioStreamInfo:
    index: int
    codec: str
    sample_rate: int
    channels: int
    channel_layout: str


@dataclass
class AudioFileInfo:
    filename: str
    path: str
    duration: float


def is_pure_audio(file_path: str) -> bool:
    """Check if file is a pure audio file based on extension."""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in PURE_AUDIO_EXTENSIONS


def scan_audio_dir(dir_path: str) -> list[AudioFileInfo]:
    """Scan directory for audio files, sorted by filename.
    Duration is set to 0.0 (caller should fill with probe_duration).
    """
    entries = os.listdir(dir_path)
    audio_files = []

    for name in sorted(entries):
        file_path = os.path.join(dir_path, name)
        if os.path.isfile(file_path) and is_pure_audio(file_path):
            audio_files.append(
                AudioFileInfo(
                    filename=name,
                    path=file_path,
                    duration=0.0,
                )
            )

    return audio_files
