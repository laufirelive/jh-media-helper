import json
import os
import tempfile
from unittest.mock import patch

from src.core.config import CombatAudioConfig
from src.core.processors.combat_audio import (
    PURE_AUDIO_EXTENSIONS,
    AudioFileInfo,
    AudioStreamInfo,
    build_duration_adjust_command,
    build_extract_command,
    build_mix_command,
    build_mux_command,
    build_preview_command,
    is_pure_audio,
    probe_audio_streams,
    probe_duration,
    resolve_output_path,
    scan_audio_dir,
    validate,
)


class TestAudioStreamInfo:
    def test_fields(self):
        info = AudioStreamInfo(
            index=1,
            codec="aac",
            sample_rate=48000,
            channels=2,
            channel_layout="stereo",
        )
        assert info.index == 1
        assert info.codec == "aac"
        assert info.sample_rate == 48000
        assert info.channels == 2
        assert info.channel_layout == "stereo"


class TestAudioFileInfo:
    def test_fields(self):
        info = AudioFileInfo(
            filename="bgm_01.aac",
            path="/audio/bgm_01.aac",
            duration=185.32,
        )
        assert info.filename == "bgm_01.aac"
        assert info.path == "/audio/bgm_01.aac"
        assert info.duration == 185.32


class TestIsPureAudio:
    def test_aac_is_pure_audio(self):
        assert is_pure_audio("/path/to/file.aac") is True

    def test_mp3_is_pure_audio(self):
        assert is_pure_audio("/path/to/file.mp3") is True

    def test_wav_is_pure_audio(self):
        assert is_pure_audio("/path/to/file.wav") is True

    def test_flac_is_pure_audio(self):
        assert is_pure_audio("/path/to/file.flac") is True

    def test_uppercase_aac_is_pure_audio(self):
        assert is_pure_audio("/path/to/file.AAC") is True

    def test_mp4_is_not_pure_audio(self):
        assert is_pure_audio("/path/to/file.mp4") is False

    def test_mkv_is_not_pure_audio(self):
        assert is_pure_audio("/path/to/file.mkv") is False


class TestScanAudioDir:
    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            result = scan_audio_dir(d)
            assert result == []

    def test_filters_non_audio(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "bgm_01.aac"), "w").close()
            open(os.path.join(d, "video.mp4"), "w").close()
            open(os.path.join(d, "readme.txt"), "w").close()
            result = scan_audio_dir(d)
            assert len(result) == 1
            assert result[0].filename == "bgm_01.aac"

    def test_sorted_by_filename(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "bgm_03.mp3"), "w").close()
            open(os.path.join(d, "bgm_01.aac"), "w").close()
            open(os.path.join(d, "bgm_02.wav"), "w").close()
            result = scan_audio_dir(d)
            assert len(result) == 3
            assert result[0].filename == "bgm_01.aac"
            assert result[1].filename == "bgm_02.wav"
            assert result[2].filename == "bgm_03.mp3"

    def test_duration_is_zero(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "bgm_01.aac"), "w").close()
            result = scan_audio_dir(d)
            assert result[0].duration == 0.0

    def test_path_is_absolute(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "bgm_01.aac"), "w").close()
            result = scan_audio_dir(d)
            assert result[0].path == os.path.join(d, "bgm_01.aac")


class TestProbeDuration:
    @patch("subprocess.run")
    def test_parses_ffprobe_output(self, mock_run):
        mock_run.return_value.stdout = json.dumps({"format": {"duration": "185.32"}})
        mock_run.return_value.returncode = 0
        duration = probe_duration("/path/to/audio.aac")
        assert duration == 185.32

    @patch("subprocess.run")
    def test_returns_zero_on_failure(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        duration = probe_duration("/path/to/missing.aac")
        assert duration == 0.0

    @patch("subprocess.run")
    def test_returns_zero_on_missing_duration(self, mock_run):
        mock_run.return_value.stdout = json.dumps({"format": {}})
        mock_run.return_value.returncode = 0
        duration = probe_duration("/path/to/audio.aac")
        assert duration == 0.0


class TestProbeAudioStreams:
    @patch("subprocess.run")
    def test_parses_ffprobe_output(self, mock_run):
        mock_run.return_value.stdout = json.dumps({
            "streams": [
                {
                    "index": 1,
                    "codec_name": "aac",
                    "sample_rate": "48000",
                    "channels": 2,
                    "channel_layout": "stereo",
                },
                {
                    "index": 2,
                    "codec_name": "ac3",
                    "sample_rate": "48000",
                    "channels": 6,
                    "channel_layout": "5.1",
                },
            ]
        })
        mock_run.return_value.returncode = 0
        streams = probe_audio_streams("/path/to/video.mkv")
        assert len(streams) == 2
        assert streams[0].index == 1
        assert streams[0].codec == "aac"
        assert streams[0].sample_rate == 48000
        assert streams[0].channels == 2
        assert streams[0].channel_layout == "stereo"
        assert streams[1].index == 2
        assert streams[1].codec == "ac3"

    @patch("subprocess.run")
    def test_returns_empty_on_failure(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        streams = probe_audio_streams("/path/to/missing.mkv")
        assert streams == []

    @patch("subprocess.run")
    def test_returns_empty_on_no_streams(self, mock_run):
        mock_run.return_value.stdout = json.dumps({"streams": []})
        mock_run.return_value.returncode = 0
        streams = probe_audio_streams("/path/to/video.mkv")
        assert streams == []


class TestBuildExtractCommand:
    def test_command_structure(self):
        cmd = build_extract_command("/input/video.mkv", 1, "/output/audio.aac")
        assert cmd[0] == "ffmpeg"
        assert "-y" in cmd
        assert "-i" in cmd
        assert "/input/video.mkv" in cmd
        assert "-map" in cmd
        assert "0:a:1" in cmd
        assert "-c:a" in cmd
        assert "copy" in cmd
        assert cmd[-1] == "/output/audio.aac"


class TestBuildDurationAdjustCommand:
    def test_trim_when_bg_longer_than_target(self):
        cmd = build_duration_adjust_command("/audio/bg.aac", 100.0, 150.0, "/output/adjusted.aac")
        filter_str = " ".join(cmd)
        assert "atrim=0:100.0" in filter_str
        assert "aloop" not in filter_str
        assert "-c:a" in cmd
        assert "aac" in cmd

    def test_loop_when_bg_shorter_than_target(self):
        cmd = build_duration_adjust_command("/audio/bg.aac", 100.0, 50.0, "/output/adjusted.aac")
        filter_str = " ".join(cmd)
        assert "aloop=-1:1" in filter_str
        assert "atrim=0:100.0" in filter_str
        assert "-c:a" in cmd
        assert "aac" in cmd


class TestBuildMixCommand:
    def test_contains_loudnorm(self):
        cmd = build_mix_command("/audio/base.aac", "/audio/bg.aac", 0.6, "/output/mixed.aac")
        filter_str = " ".join(cmd)
        assert "loudnorm" in filter_str
        assert filter_str.count("loudnorm") == 3

    def test_contains_amix_with_weights(self):
        cmd = build_mix_command("/audio/base.aac", "/audio/bg.aac", 0.6, "/output/mixed.aac")
        filter_str = " ".join(cmd)
        assert "amix" in filter_str
        assert "weights=0.6 1" in filter_str or "weights=0.6" in filter_str

    def test_output_codec(self):
        cmd = build_mix_command("/audio/base.aac", "/audio/bg.aac", 0.6, "/output/mixed.aac")
        assert "-c:a" in cmd
        assert "aac" in cmd
        assert "-b:a" in cmd
        assert "192k" in cmd


class TestBuildMuxCommand:
    def test_three_input_flags(self):
        cmd = build_mux_command("/video/input.mkv", ["/audio/m1.aac", "/audio/m2.aac"], "/output/final.mkv")
        assert cmd.count("-i") == 3

    def test_correct_map_order(self):
        cmd = build_mux_command("/video/input.mkv", ["/audio/m1.aac", "/audio/m2.aac"], "/output/final.mkv")
        map_indices = [i for i, x in enumerate(cmd) if x == "-map"]
        assert len(map_indices) >= 4
        assert cmd[map_indices[0] + 1] == "0:v"
        assert cmd[map_indices[1] + 1] in ["0:s?", "0:s"]
        assert cmd[map_indices[2] + 1] == "1:a"
        assert cmd[map_indices[3] + 1] == "2:a"

    def test_copy_codec(self):
        cmd = build_mux_command("/video/input.mkv", ["/audio/m1.aac"], "/output/final.mkv")
        assert "-c" in cmd
        assert "copy" in cmd


class TestBuildPreviewCommand:
    def test_contains_atrim_5s(self):
        cmd = build_preview_command("/audio/base.aac", "/audio/bg.aac", 0.6, "/output/preview.aac")
        filter_str = " ".join(cmd)
        assert "atrim=0:5" in filter_str
        assert filter_str.count("atrim=0:5") == 2


class TestValidate:
    def test_missing_input(self):
        with tempfile.TemporaryDirectory() as d:
            audio_dir = os.path.join(d, "audio")
            os.makedirs(audio_dir)
            open(os.path.join(audio_dir, "bgm.aac"), "w").close()
            cfg = CombatAudioConfig(input_path="/nonexistent/video.mkv", audio_dir=audio_dir)
            ok, err = validate(cfg)
            assert ok is False
            assert err is not None

    def test_missing_audio_dir(self):
        with tempfile.TemporaryDirectory() as d:
            video_path = os.path.join(d, "video.mkv")
            open(video_path, "w").close()
            cfg = CombatAudioConfig(input_path=video_path, audio_dir="/nonexistent/audio")
            ok, err = validate(cfg)
            assert ok is False
            assert err is not None

    def test_empty_audio_dir(self):
        with tempfile.TemporaryDirectory() as d:
            video_path = os.path.join(d, "video.mkv")
            audio_dir = os.path.join(d, "audio")
            os.makedirs(audio_dir)
            open(video_path, "w").close()
            cfg = CombatAudioConfig(input_path=video_path, audio_dir=audio_dir)
            ok, err = validate(cfg)
            assert ok is False
            assert err is not None

    def test_success(self):
        with tempfile.TemporaryDirectory() as d:
            video_path = os.path.join(d, "video.mkv")
            audio_dir = os.path.join(d, "audio")
            os.makedirs(audio_dir)
            open(video_path, "w").close()
            open(os.path.join(audio_dir, "bgm.aac"), "w").close()
            cfg = CombatAudioConfig(input_path=video_path, audio_dir=audio_dir)
            ok, err = validate(cfg)
            assert ok is True
            assert err is None

    def test_empty_audio_order_uses_scan(self):
        with tempfile.TemporaryDirectory() as d:
            video_path = os.path.join(d, "video.mkv")
            audio_dir = os.path.join(d, "audio")
            os.makedirs(audio_dir)
            open(video_path, "w").close()
            open(os.path.join(audio_dir, "bgm_02.aac"), "w").close()
            open(os.path.join(audio_dir, "bgm_01.mp3"), "w").close()
            cfg = CombatAudioConfig(input_path=video_path, audio_dir=audio_dir, audio_order=[])
            ok, err = validate(cfg)
            assert ok is True


class TestResolveOutputPath:
    def test_mixed_no_box(self):
        with tempfile.TemporaryDirectory() as d:
            video_path = os.path.join(d, "episode_01.mkv")
            cfg = CombatAudioConfig(input_path=video_path, audio_dir="/audio", mix_enabled=True, boxed=False)
            paths = resolve_output_path(cfg, 2)
            assert len(paths) == 2
            assert paths[0].endswith("episode_01_mixed_00.aac")
            assert paths[1].endswith("episode_01_mixed_01.aac")

    def test_aligned_no_box(self):
        with tempfile.TemporaryDirectory() as d:
            video_path = os.path.join(d, "episode_01.mkv")
            cfg = CombatAudioConfig(input_path=video_path, audio_dir="/audio", mix_enabled=False, boxed=False)
            paths = resolve_output_path(cfg, 2)
            assert len(paths) == 2
            assert paths[0].endswith("episode_01_aligned_00.aac")
            assert paths[1].endswith("episode_01_aligned_01.aac")

    def test_boxed(self):
        with tempfile.TemporaryDirectory() as d:
            video_path = os.path.join(d, "episode_01.mkv")
            cfg = CombatAudioConfig(input_path=video_path, audio_dir="/audio", boxed=True)
            paths = resolve_output_path(cfg, 2)
            assert len(paths) == 1
            assert paths[0].endswith(".mkv")

    def test_uses_output_dir(self):
        with tempfile.TemporaryDirectory() as d:
            video_path = os.path.join(d, "episode_01.mkv")
            output_dir = os.path.join(d, "output")
            cfg = CombatAudioConfig(input_path=video_path, audio_dir="/audio", output_dir=output_dir, boxed=False)
            paths = resolve_output_path(cfg, 1)
            assert paths[0].startswith(output_dir)
