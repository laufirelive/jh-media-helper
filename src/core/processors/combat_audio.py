import json
import os
import subprocess
import time
from dataclasses import dataclass

from src.core.config import CombatAudioConfig

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


def probe_duration(file_path: str) -> float:
    """Probe file duration using ffprobe. Returns 0.0 on failure."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_entries", "format=duration",
                file_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        duration_str = data.get("format", {}).get("duration")
        if duration_str:
            return float(duration_str)
        return 0.0
    except Exception:
        return 0.0


def probe_audio_streams(file_path: str) -> list[AudioStreamInfo]:
    """Probe audio streams using ffprobe. Returns [] on failure."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                "-select_streams", "a",
                file_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        streams = []
        for stream in data.get("streams", []):
            streams.append(
                AudioStreamInfo(
                    index=stream["index"],
                    codec=stream["codec_name"],
                    sample_rate=int(stream["sample_rate"]),
                    channels=stream["channels"],
                    channel_layout=stream["channel_layout"],
                )
            )
        return streams
    except Exception:
        return []


_LOUDNORM = "loudnorm=I=-14:TP=-1.0:LRA=15"


def build_extract_command(input_path: str, stream_index: int, output_path: str) -> list[str]:
    """Build ffmpeg command to extract audio stream."""
    return [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-map", f"0:a:{stream_index}",
        "-c:a", "copy",
        output_path,
    ]


def build_duration_adjust_command(
    audio_path: str, target_duration: float, bg_duration: float, output_path: str
) -> list[str]:
    """Build ffmpeg command to adjust audio duration (trim or loop)."""
    if bg_duration >= target_duration:
        filter_complex = f"atrim=0:{target_duration}"
    else:
        filter_complex = f"aloop=-1:1,atrim=0:{target_duration}"

    return [
        "ffmpeg",
        "-y",
        "-i", audio_path,
        "-af", filter_complex,
        "-c:a", "aac",
        output_path,
    ]


def build_mix_command(
    base_audio: str, bg_audio: str, volume: float, output_path: str
) -> list[str]:
    """Build ffmpeg command to mix base and background audio with loudnorm."""
    filter_complex = (
        f"[0:a]{_LOUDNORM}[main];"
        f"[1:a]{_LOUDNORM}[bg];"
        f"[main][bg]amix=inputs=2:weights={volume} 1,volume=2,{_LOUDNORM}"
    )

    return [
        "ffmpeg",
        "-y",
        "-i", base_audio,
        "-i", bg_audio,
        "-filter_complex", filter_complex,
        "-c:a", "aac",
        "-b:a", "192k",
        output_path,
    ]


def build_mux_command(
    video_path: str, mixed_audios: list[str], output_path: str
) -> list[str]:
    """Build ffmpeg command to mux video with multiple audio tracks."""
    cmd = ["ffmpeg", "-y", "-i", video_path]

    for audio in mixed_audios:
        cmd += ["-i", audio]

    cmd += ["-map", "0:v", "-map", "0:s?"]

    for i in range(len(mixed_audios)):
        cmd += ["-map", f"{i+1}:a"]

    cmd += ["-map", "0:a", "-c", "copy", output_path]

    return cmd


def build_preview_command(
    base_audio: str, bg_audio: str, volume: float, output_path: str
) -> list[str]:
    """Build ffmpeg command to create 5-second preview mix."""
    filter_complex = (
        f"[0:a]atrim=0:5,{_LOUDNORM}[main];"
        f"[1:a]atrim=0:5,{_LOUDNORM}[bg];"
        f"[main][bg]amix=inputs=2:weights={volume} 1,volume=2,{_LOUDNORM}"
    )

    return [
        "ffmpeg",
        "-y",
        "-i", base_audio,
        "-i", bg_audio,
        "-filter_complex", filter_complex,
        "-c:a", "aac",
        "-b:a", "192k",
        output_path,
    ]


def validate(config: CombatAudioConfig) -> tuple[bool, str | None]:
    """Validate config before processing. Returns (ok, error_message)."""
    if not os.path.exists(config.input_path):
        return False, f"输入文件不存在: {config.input_path}"

    if not os.path.isdir(config.audio_dir):
        return False, f"音频文件夹不存在: {config.audio_dir}"

    audio_files = scan_audio_dir(config.audio_dir)
    if not audio_files:
        return False, f"音频文件夹为空: {config.audio_dir}"

    return True, None


def resolve_output_path(config: CombatAudioConfig, audio_count: int) -> list[str]:
    """Resolve output file paths based on config."""
    input_stem = os.path.splitext(os.path.basename(config.input_path))[0]

    if config.output_dir:
        output_dir = config.output_dir
    else:
        output_dir = os.path.dirname(config.input_path)

    if config.boxed:
        return [os.path.join(output_dir, f"{input_stem}.mkv")]

    suffix = "mixed" if config.mix_enabled else "aligned"
    paths = []
    for i in range(audio_count):
        filename = f"{input_stem}_{suffix}_{i:02d}.aac"
        paths.append(os.path.join(output_dir, filename))

    return paths
