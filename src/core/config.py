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
