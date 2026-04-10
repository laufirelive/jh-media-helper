import json
import os
import subprocess
import time
from dataclasses import dataclass

from src.core.config import CombatAudioConfig

PURE_AUDIO_EXTENSIONS = {".aac", ".m4a", ".mp3", ".wav", ".flac"}
PREVIEW_DURATION_SECONDS = 10.0


@dataclass
class AudioStreamInfo:
    index: int
    audio_position: int
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
                "-show_entries", "format=duration:stream=duration",
                file_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)

        durations: list[float] = []

        duration_str = data.get("format", {}).get("duration")
        if duration_str:
            try:
                value = float(duration_str)
                if value > 0:
                    durations.append(value)
            except (TypeError, ValueError):
                pass

        for stream in data.get("streams", []):
            stream_duration = stream.get("duration")
            if not stream_duration:
                continue
            try:
                value = float(stream_duration)
                if value > 0:
                    durations.append(value)
            except (TypeError, ValueError):
                continue

        return max(durations) if durations else 0.0
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
        for audio_position, stream in enumerate(data.get("streams", [])):
            streams.append(
                AudioStreamInfo(
                    index=stream["index"],
                    audio_position=audio_position,
                    codec=stream.get("codec_name", "unknown"),
                    sample_rate=int(stream.get("sample_rate", 0)),
                    channels=stream.get("channels", 0),
                    channel_layout=stream.get("channel_layout", ""),
                )
            )
        return streams
    except Exception:
        return []


def run_ffmpeg_command(cmd: list[str], *, timeout: int, default_message: str) -> str | None:
    """Run ffmpeg command and return a user-facing error message on failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return f"{default_message}\n\n{exc}"

    if result.returncode == 0:
        return None

    stderr = (result.stderr or "").strip()
    if not stderr:
        return default_message

    tail = "\n".join(stderr.splitlines()[-3:])
    return f"{default_message}\n\n{tail}"


_LOUDNORM = "loudnorm=I=-14:TP=-1.0:LRA=15"


def build_extract_command(
    input_path: str,
    stream_index: int,
    output_path: str,
    *,
    start_seconds: float = 0.0,
    duration_seconds: float | None = None,
) -> list[str]:
    """Build ffmpeg command to extract audio stream."""
    if start_seconds < 0:
        raise ValueError("start_seconds must be >= 0")
    if duration_seconds is not None and duration_seconds <= 0:
        raise ValueError("duration_seconds must be > 0")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
    ]

    if start_seconds > 0.0:
        cmd += ["-ss", f"{start_seconds}"]

    if duration_seconds is not None:
        cmd += ["-t", f"{duration_seconds}"]

    cmd += [
        "-map", f"0:a:{stream_index}",
        "-c:a", "aac",
        "-b:a", "192k",
        output_path,
    ]

    return cmd


def build_duration_adjust_command(
    audio_path: str,
    target_duration: float,
    bg_duration: float,
    output_path: str,
    *,
    loop_short_audio: bool = True,
) -> list[str]:
    """构建时长调整命令：长于目标则裁切；短于目标时可循环铺满或仅保留原长（不循环）。"""
    output_duration = target_duration if (bg_duration >= target_duration or loop_short_audio) else bg_duration
    cmd = ["ffmpeg", "-y"]
    if bg_duration < target_duration and loop_short_audio:
        cmd += ["-stream_loop", "-1"]
    cmd += [
        "-i", audio_path,
        "-t", f"{output_duration}",
        "-c:a", "aac",
        "-b:a", "192k",
        output_path,
    ]
    return cmd


def build_mix_command(
    base_audio: str, bg_audio: str, volume: float, output_path: str
) -> list[str]:
    """Build ffmpeg command to mix base and background audio with loudnorm."""
    filter_complex = (
        f"[0:a]{_LOUDNORM}[main];"
        f"[1:a]{_LOUDNORM}[bg];"
        f"[main][bg]amix=inputs=2:duration=first:dropout_transition=1:weights={volume} 1:normalize=0,volume=2,{_LOUDNORM}"
    )

    return [
        "ffmpeg",
        "-y",
        "-hwaccel", "auto",
        "-i", base_audio,
        "-i", bg_audio,
        "-filter_complex", filter_complex,
        "-c:a", "aac",
        "-b:a", "192k",
        output_path,
    ]


def build_mux_command(
    video_path: str, mixed_audios: list[str], output_path: str,
    keep_original_audio: bool = True,
) -> list[str]:
    """Build ffmpeg command to mux video with multiple audio tracks."""
    cmd = ["ffmpeg", "-y", "-i", video_path]

    for audio in mixed_audios:
        cmd += ["-i", audio]

    cmd += ["-map", "0:v", "-map", "0:s?"]

    for i in range(len(mixed_audios)):
        cmd += ["-map", f"{i+1}:a"]

    if keep_original_audio:
        cmd += ["-map", "0:a"]

    cmd += ["-c", "copy"]

    if mixed_audios:
        cmd += ["-disposition:a:0", "default"]
        total_audio_tracks = len(mixed_audios) + (1 if keep_original_audio else 0)
        for audio_index in range(1, total_audio_tracks):
            cmd += [f"-disposition:a:{audio_index}", "0"]

    cmd += [output_path]

    return cmd


def build_preview_command(
    base_audio: str,
    bg_audio: str,
    volume: float,
    output_path: str,
    *,
    start_seconds: float = 0.0,
    base_start_seconds: float | None = None,
    bg_start_seconds: float | None = None,
    duration_seconds: float = PREVIEW_DURATION_SECONDS,
) -> list[str]:
    """Build ffmpeg command to create a preview mix."""
    if start_seconds < 0:
        raise ValueError("start_seconds must be >= 0")
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be > 0")

    resolved_base_start = start_seconds if base_start_seconds is None else base_start_seconds
    resolved_bg_start = start_seconds if bg_start_seconds is None else bg_start_seconds
    if resolved_base_start < 0:
        raise ValueError("base_start_seconds must be >= 0")
    if resolved_bg_start < 0:
        raise ValueError("bg_start_seconds must be >= 0")

    base_end_seconds = resolved_base_start + duration_seconds
    bg_end_seconds = resolved_bg_start + duration_seconds
    filter_complex = (
        f"[0:a]atrim=start={resolved_base_start}:end={base_end_seconds},asetpts=PTS-STARTPTS,{_LOUDNORM}[main];"
        f"[1:a]atrim=start={resolved_bg_start}:end={bg_end_seconds},asetpts=PTS-STARTPTS,{_LOUDNORM}[bg];"
        f"[main][bg]amix=inputs=2:duration=first:dropout_transition=1:weights={volume} 1:normalize=0,volume=2,{_LOUDNORM}"
    )

    return [
        "ffmpeg",
        "-y",
        "-hwaccel", "auto",
        "-i", base_audio,
        "-stream_loop", "-1",
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
        ts = time.strftime("%Y%m%d%H%M%S")
        return [os.path.join(output_dir, f"{input_stem}_{ts}.mkv")]

    suffix = "mixed" if config.mix_enabled else "aligned"
    paths = []
    for i in range(audio_count):
        filename = f"{input_stem}_{suffix}_{i:02d}.aac"
        paths.append(os.path.join(output_dir, filename))

    return paths


def build_export_aac_command(input_path: str, output_path: str) -> list[str]:
    """Export AAC audio from a containerized temp file to raw ADTS AAC."""
    return [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-vn",
        "-c:a", "copy",
        "-f", "adts",
        output_path,
    ]
