from src.core.config import CombatAudioConfig


def test_combat_audio_config_defaults():
    cfg = CombatAudioConfig(
        input_path="/tmp/video.mp4",
        audio_dir="/tmp/audio",
    )
    assert cfg.input_path == "/tmp/video.mp4"
    assert cfg.audio_dir == "/tmp/audio"
    assert cfg.output_dir is None
    assert cfg.mix_enabled is True
    assert cfg.volume == 0.6
    assert cfg.boxed is False
    assert cfg.thread_count == 1
    assert cfg.audio_stream_index == 0
    assert cfg.audio_order == []


def test_combat_audio_config_round_trip():
    cfg = CombatAudioConfig(
        input_path="/tmp/video.mkv",
        audio_dir="/tmp/bgm",
        output_dir="/tmp/out",
        mix_enabled=False,
        volume=0.8,
        boxed=True,
        thread_count=4,
        audio_stream_index=2,
        audio_order=["jazz.mp3", "piano.mp3"],
    )
    d = cfg.to_dict()
    restored = CombatAudioConfig.from_dict(d)
    assert restored.input_path == cfg.input_path
    assert restored.audio_dir == cfg.audio_dir
    assert restored.output_dir == cfg.output_dir
    assert restored.mix_enabled == cfg.mix_enabled
    assert restored.volume == cfg.volume
    assert restored.boxed == cfg.boxed
    assert restored.thread_count == cfg.thread_count
    assert restored.audio_stream_index == cfg.audio_stream_index
    assert restored.audio_order == cfg.audio_order


def test_combat_audio_config_from_dict_defaults():
    d = {"input_path": "/tmp/v.mp4", "audio_dir": "/tmp/a"}
    cfg = CombatAudioConfig.from_dict(d)
    assert cfg.mix_enabled is True
    assert cfg.volume == 0.6
    assert cfg.boxed is False
    assert cfg.thread_count == 1
    assert cfg.audio_stream_index == 0
    assert cfg.audio_order == []


def test_combat_audio_config_mkvmerge_secondary_video_defaults():
    cfg = CombatAudioConfig(input_path="/tmp/video.mkv", audio_dir="/tmp/audio")

    assert cfg.secondary_video_paths == []
    assert cfg.mkvmerge_path is None
    assert cfg.mux_backend == "auto"


def test_combat_audio_config_mkvmerge_secondary_video_round_trip():
    cfg = CombatAudioConfig(
        input_path="/tmp/video.mkv",
        audio_dir="/tmp/audio",
        secondary_video_paths=["/tmp/part2.mp4", "/tmp/part3.mp4"],
        mkvmerge_path="/opt/bin/mkvmerge",
        mux_backend="auto",
    )

    restored = CombatAudioConfig.from_dict(cfg.to_dict())

    assert restored.secondary_video_paths == cfg.secondary_video_paths
    assert restored.mkvmerge_path == "/opt/bin/mkvmerge"
    assert restored.mux_backend == "auto"


def test_combat_audio_config_old_dict_defaults_new_fields():
    restored = CombatAudioConfig.from_dict({
        "input_path": "/tmp/video.mkv",
        "audio_dir": "/tmp/audio",
    })

    assert restored.secondary_video_paths == []
    assert restored.mkvmerge_path is None
    assert restored.mux_backend == "auto"


def test_combat_audio_config_subtitle_path_defaults_to_none():
    cfg = CombatAudioConfig(input_path="/tmp/video.mkv", audio_dir="/tmp/audio")

    assert cfg.subtitle_path is None


def test_combat_audio_config_subtitle_path_round_trip():
    cfg = CombatAudioConfig(
        input_path="/tmp/video.mkv",
        audio_dir="/tmp/audio",
        boxed=True,
        subtitle_path="/tmp/subtitle.ass",
    )

    restored = CombatAudioConfig.from_dict(cfg.to_dict())

    assert restored.subtitle_path == "/tmp/subtitle.ass"


def test_combat_audio_config_empty_subtitle_path_normalizes_to_none():
    restored = CombatAudioConfig.from_dict({
        "input_path": "/tmp/video.mkv",
        "audio_dir": "/tmp/audio",
        "subtitle_path": "",
    })

    assert restored.subtitle_path is None
