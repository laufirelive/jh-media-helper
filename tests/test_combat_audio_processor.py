import os
import tempfile

from src.core.processors.combat_audio import (
    PURE_AUDIO_EXTENSIONS,
    AudioFileInfo,
    AudioStreamInfo,
    is_pure_audio,
    scan_audio_dir,
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
