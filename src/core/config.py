from dataclasses import dataclass
from enum import Enum


class TaskType(Enum):
    PIC_SEQ = "pic_seq"
    COMBAT_AUDIO = "combat_audio"
    MKV_EXTRACT = "mkv_extract"


class OutputFormat(Enum):
    MOV_PRORES = "mov_prores"
    MP4_HEVC = "mp4_hevc"
    MP4_H264 = "mp4_h264"


class BackgroundMode(Enum):
    TRANSPARENT = "transparent"
    GREEN = "green"
    BLUE = "blue"


class TaskStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PicSeqConfig:
    input_dir: str
    output_dir: str | None = None
    fps: int = 120
    bitrate_mbps: int = 32
    width: int | None = None
    height: int | None = None
    scan_format: str | None = None
    output_format: OutputFormat = OutputFormat.MOV_PRORES
    background_mode: BackgroundMode = BackgroundMode.TRANSPARENT
    hw_accel: bool = True

    def to_dict(self) -> dict:
        return {
            "input_dir": self.input_dir,
            "output_dir": self.output_dir,
            "fps": self.fps,
            "bitrate_mbps": self.bitrate_mbps,
            "width": self.width,
            "height": self.height,
            "scan_format": self.scan_format,
            "output_format": self.output_format.value,
            "background_mode": self.background_mode.value,
            "hw_accel": self.hw_accel,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PicSeqConfig":
        return cls(
            input_dir=d["input_dir"],
            output_dir=d.get("output_dir"),
            fps=d.get("fps", 120),
            bitrate_mbps=d.get("bitrate_mbps", 32),
            width=d.get("width"),
            height=d.get("height"),
            scan_format=d.get("scan_format"),
            output_format=OutputFormat(d.get("output_format", "mov_prores")),
            background_mode=BackgroundMode(d.get("background_mode", "transparent")),
            hw_accel=d.get("hw_accel", True),
        )


@dataclass
class CombatAudioConfig:
    input_path: str
    audio_dir: str
    output_dir: str | None = None
    mix_enabled: bool = True
    volume: float = 0.6
    boxed: bool = False
    thread_count: int = 1
    audio_stream_index: int = 0
    audio_order: list[str] | None = None
    secondary_video_paths: list[str] | None = None
    mkvmerge_path: str | None = None
    mux_backend: str = "auto"

    def __post_init__(self):
        if self.audio_order is None:
            self.audio_order = []
        if self.secondary_video_paths is None:
            self.secondary_video_paths = []

    def to_dict(self) -> dict:
        return {
            "input_path": self.input_path,
            "audio_dir": self.audio_dir,
            "output_dir": self.output_dir,
            "mix_enabled": self.mix_enabled,
            "volume": self.volume,
            "boxed": self.boxed,
            "thread_count": self.thread_count,
            "audio_stream_index": self.audio_stream_index,
            "audio_order": self.audio_order,
            "secondary_video_paths": self.secondary_video_paths,
            "mkvmerge_path": self.mkvmerge_path,
            "mux_backend": self.mux_backend,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CombatAudioConfig":
        return cls(
            input_path=d["input_path"],
            audio_dir=d["audio_dir"],
            output_dir=d.get("output_dir"),
            mix_enabled=d.get("mix_enabled", True),
            volume=d.get("volume", 0.6),
            boxed=d.get("boxed", False),
            thread_count=d.get("thread_count", 1),
            audio_stream_index=d.get("audio_stream_index", 0),
            audio_order=d.get("audio_order", []),
            secondary_video_paths=d.get("secondary_video_paths", []),
            mkvmerge_path=d.get("mkvmerge_path"),
            mux_backend=d.get("mux_backend", "auto"),
        )
