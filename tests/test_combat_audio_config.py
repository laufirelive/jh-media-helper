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
