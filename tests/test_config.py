from src.core.config import (
    BackgroundMode,
    OutputFormat,
    PicSeqConfig,
    TaskStatus,
    TaskType,
)


def test_task_type_values():
    assert TaskType.PIC_SEQ.value == "pic_seq"
    assert TaskType.COMBAT_AUDIO.value == "combat_audio"
    assert TaskType.MKV_EXTRACT.value == "mkv_extract"


def test_output_format_values():
    assert OutputFormat.MOV_PRORES.value == "mov_prores"
    assert OutputFormat.MP4_HEVC.value == "mp4_hevc"
    assert OutputFormat.MP4_H264.value == "mp4_h264"


def test_background_mode_values():
    assert BackgroundMode.TRANSPARENT.value == "transparent"
    assert BackgroundMode.GREEN.value == "green"
    assert BackgroundMode.BLUE.value == "blue"


def test_task_status_values():
    assert TaskStatus.PENDING.value == "pending"
    assert TaskStatus.PROCESSING.value == "processing"
    assert TaskStatus.COMPLETED.value == "completed"
    assert TaskStatus.FAILED.value == "failed"
    assert TaskStatus.CANCELLED.value == "cancelled"


def test_pic_seq_config_defaults():
    cfg = PicSeqConfig(input_dir="/tmp/seq")
    assert cfg.fps == 120
    assert cfg.bitrate_mbps == 32
    assert cfg.width is None
    assert cfg.height is None
    assert cfg.scan_format is None
    assert cfg.output_dir is None
    assert cfg.output_format == OutputFormat.MOV_PRORES
    assert cfg.background_mode == BackgroundMode.TRANSPARENT
    assert cfg.hw_accel is True


def test_pic_seq_config_round_trip():
    cfg = PicSeqConfig(
        input_dir="/tmp/seq",
        fps=60,
        bitrate_mbps=16,
        width=1920,
        height=1080,
        scan_format="%04d.png",
        output_format=OutputFormat.MP4_HEVC,
        background_mode=BackgroundMode.GREEN,
        hw_accel=False,
    )
    d = cfg.to_dict()
    restored = PicSeqConfig.from_dict(d)
    assert restored.input_dir == cfg.input_dir
    assert restored.fps == cfg.fps
    assert restored.bitrate_mbps == cfg.bitrate_mbps
    assert restored.width == cfg.width
    assert restored.height == cfg.height
    assert restored.scan_format == cfg.scan_format
    assert restored.output_format == cfg.output_format
    assert restored.background_mode == cfg.background_mode
    assert restored.hw_accel == cfg.hw_accel
