import json
import os
import tempfile
from unittest.mock import patch

import pytest

from src.core.config import CombatAudioConfig
from src.core.processors.combat_audio import (
    PURE_AUDIO_EXTENSIONS,
    PREVIEW_DURATION_SECONDS,
    AudioFileInfo,
    AudioStreamInfo,
    build_duration_adjust_command,
    build_export_aac_command,
    build_extract_command,
    build_mkvmerge_mux_command,
    build_mix_command,
    build_mux_command,
    build_preview_command,
    run_ffmpeg_command,
    is_pure_audio,
    probe_audio_streams,
    probe_duration,
    probe_video_stream_count,
    resolve_mkv_output_paths,
    resolve_output_path,
    sanitize_output_stem,
    scan_audio_dir,
    validate,
    validate_secondary_videos,
)


class TestAudioStreamInfo:
    def test_fields(self):
        info = AudioStreamInfo(
            index=1,
            audio_position=0,
            codec="aac",
            sample_rate=48000,
            channels=2,
            channel_layout="stereo",
            language="jpn",
        )
        assert info.index == 1
        assert info.audio_position == 0
        assert info.codec == "aac"
        assert info.sample_rate == 48000
        assert info.channels == 2
        assert info.channel_layout == "stereo"
        assert info.language == "jpn"


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

    def test_m4a_is_pure_audio(self):
        assert is_pure_audio("/path/to/file.m4a") is True

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

    @patch("subprocess.run")
    def test_prefers_longest_positive_duration_from_format_and_streams(self, mock_run):
        mock_run.return_value.stdout = json.dumps({
            "format": {"duration": "1440.95"},
            "streams": [
                {"duration": "3600.09"},
                {"duration": "3599.80"},
            ],
        })
        mock_run.return_value.returncode = 0
        duration = probe_duration("/path/to/audio.aac")
        assert duration == 3600.09


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
                    "tags": {"language": "jpn"},
                },
                {
                    "index": 2,
                    "codec_name": "ac3",
                    "sample_rate": "48000",
                    "channels": 6,
                    "channel_layout": "5.1",
                    "tags": {"language": "eng"},
                },
            ]
        })
        mock_run.return_value.returncode = 0
        streams = probe_audio_streams("/path/to/video.mkv")
        assert len(streams) == 2
        assert streams[0].index == 1
        assert streams[0].audio_position == 0
        assert streams[0].codec == "aac"
        assert streams[0].sample_rate == 48000
        assert streams[0].channels == 2
        assert streams[0].channel_layout == "stereo"
        assert streams[0].language == "jpn"
        assert streams[1].index == 2
        assert streams[1].audio_position == 1
        assert streams[1].codec == "ac3"
        assert streams[1].language == "eng"

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


class TestProbeVideoStreamCount:
    @patch("subprocess.run")
    def test_parses_ffprobe_output(self, mock_run):
        mock_run.return_value.stdout = json.dumps({
            "streams": [
                {"index": 0},
                {"index": 3},
            ]
        })
        mock_run.return_value.returncode = 0

        count = probe_video_stream_count("/path/to/video.mkv")

        assert count == 2

    @patch("subprocess.run")
    def test_returns_zero_on_failure(self, mock_run):
        mock_run.side_effect = FileNotFoundError()

        count = probe_video_stream_count("/path/to/missing.mkv")

        assert count == 0


class TestBuildExtractCommand:
    def test_command_structure(self):
        cmd = build_extract_command("/input/video.mkv", 0, "/output/audio.aac")
        assert cmd[0] == "ffmpeg"
        assert "-y" in cmd
        assert "-i" in cmd
        assert "/input/video.mkv" in cmd
        assert "-map" in cmd
        assert "0:a:0" in cmd
        assert "-c:a" in cmd
        assert "aac" in cmd
        assert "-b:a" in cmd
        assert "192k" in cmd
        assert cmd[-1] == "/output/audio.aac"

    def test_seek_and_duration_follow_input(self):
        cmd = build_extract_command(
            "/input/video.mkv",
            1,
            "/output/audio.aac",
            start_seconds=12.5,
            duration_seconds=8.0,
        )
        seek_index = cmd.index("-ss")
        input_index = cmd.index("-i")
        duration_index = cmd.index("-t")
        map_index = cmd.index("-map")
        assert seek_index < input_index < map_index
        assert input_index < duration_index < map_index

    def test_supports_start_and_duration(self):
        cmd = build_extract_command(
            "/input/video.mkv",
            1,
            "/output/audio.aac",
            start_seconds=12.5,
            duration_seconds=8.0,
        )
        assert "-ss" in cmd
        assert cmd[cmd.index("-ss") + 1] == "12.5"
        assert "-t" in cmd
        assert cmd[cmd.index("-t") + 1] == "8.0"
        assert cmd[cmd.index("-map") + 1] == "0:a:1"

    def test_omits_seek_and_duration_defaults(self):
        cmd = build_extract_command("/input/video.mkv", 0, "/output/audio.aac")
        assert "-ss" not in cmd
        assert "-t" not in cmd

    def test_rejects_negative_start_seconds(self):
        with pytest.raises(ValueError, match="start_seconds must be >= 0"):
            build_extract_command(
                "/input/video.mkv",
                0,
                "/output/audio.aac",
                start_seconds=-0.1,
            )

    @pytest.mark.parametrize("duration_seconds", [0.0, -1.0])
    def test_rejects_non_positive_duration_seconds(self, duration_seconds):
        with pytest.raises(ValueError, match="duration_seconds must be > 0"):
            build_extract_command(
                "/input/video.mkv",
                0,
                "/output/audio.aac",
                duration_seconds=duration_seconds,
            )


class TestBuildDurationAdjustCommand:
    def test_trim_when_bg_longer_than_target(self):
        cmd = build_duration_adjust_command("/audio/bg.aac", 100.0, 150.0, "/output/adjusted.aac")
        assert "-stream_loop" not in cmd
        assert "-t" in cmd
        assert cmd[cmd.index("-t") + 1] == "100.0"
        assert "-c:a" in cmd
        assert "aac" in cmd
        assert "-b:a" in cmd
        assert "192k" in cmd

    def test_loop_when_bg_shorter_than_target(self):
        cmd = build_duration_adjust_command("/audio/bg.aac", 100.0, 50.0, "/output/adjusted.aac")
        assert "-stream_loop" in cmd
        assert cmd[cmd.index("-stream_loop") + 1] == "-1"
        assert "-t" in cmd
        assert cmd[cmd.index("-t") + 1] == "100.0"
        assert "-c:a" in cmd
        assert "aac" in cmd
        assert "-b:a" in cmd
        assert "192k" in cmd

    def test_trim_only_when_bg_shorter_and_no_loop(self):
        """无原音场景：短视频不循环，仅保留原背景音乐长度"""
        cmd = build_duration_adjust_command(
            "/audio/bg.aac", 100.0, 50.0, "/output/adjusted.aac", loop_short_audio=False
        )
        assert "-stream_loop" not in cmd
        assert "-t" in cmd
        assert cmd[cmd.index("-t") + 1] == "50.0"

    def test_ignores_attached_cover_art_video_streams(self):
        cmd = build_duration_adjust_command("/audio/with-cover.mp3", 100.0, 50.0, "/output/adjusted.m4a")

        assert "-vn" in cmd
        assert cmd.index("-vn") > cmd.index("/audio/with-cover.mp3")
        assert cmd.index("-vn") < cmd.index("-c:a")


class TestBuildMixCommand:
    def test_resets_pts_before_loudnorm(self):
        cmd = build_mix_command("/audio/base.aac", "/audio/bg.aac", 0.6, "/output/mixed.aac")
        filter_str = " ".join(cmd)
        assert "asetpts=PTS-STARTPTS" in filter_str

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

    def test_drops_source_metadata_and_chapters(self):
        cmd = build_mux_command("/video/input.mkv", ["/audio/m1.m4a"], "/output/final.mkv")

        assert "-map_metadata" in cmd
        assert cmd[cmd.index("-map_metadata") + 1] == "-1"
        assert "-map_chapters" in cmd
        assert cmd[cmd.index("-map_chapters") + 1] == "-1"

    def test_resets_timestamps_for_mkv_muxing(self):
        cmd = build_mux_command("/video/input.mkv", ["/audio/m1.m4a"], "/output/final.mkv")

        assert "-fflags" in cmd
        assert cmd[cmd.index("-fflags") + 1] == "+genpts"
        assert "-avoid_negative_ts" in cmd
        assert cmd[cmd.index("-avoid_negative_ts") + 1] == "make_zero"

    def test_clears_all_audio_dispositions_and_sets_first_generated_audio_default(self):
        cmd = build_mux_command(
            "/video/input.mkv",
            ["/audio/m1.aac", "/audio/m2.aac"],
            "/output/final.mkv",
            keep_original_audio=True,
        )

        map_pairs = [cmd[i:i + 2] for i in range(len(cmd) - 1)]
        assert ["-map", "0:a"] in map_pairs
        assert "-disposition:a" in cmd
        assert cmd[cmd.index("-disposition:a") + 1] == "0"
        assert "-disposition:a:0" in cmd
        assert cmd[cmd.index("-disposition:a:0") + 1] == "default"
        assert "-disposition:a:1" not in cmd
        assert "-disposition:a:2" not in cmd

    def test_maps_external_subtitle_after_audio_streams(self):
        cmd = build_mux_command(
            "/video/input.mkv",
            ["/audio/m1.aac", "/audio/m2.aac"],
            "/output/final.mkv",
            subtitle_path="/subs/caption.srt",
        )

        assert cmd.count("-i") == 4
        assert cmd[cmd.index("/subs/caption.srt") - 1] == "-i"
        map_pairs = [cmd[i:i + 2] for i in range(len(cmd) - 1)]
        assert ["-map", "0:v"] in map_pairs
        assert ["-map", "0:s?"] in map_pairs
        assert ["-map", "1:a"] in map_pairs
        assert ["-map", "2:a"] in map_pairs
        assert ["-map", "3:s:0"] in map_pairs
        assert cmd.index("3:s:0") > cmd.index("2:a")

    def test_no_external_subtitle_keeps_existing_input_count(self):
        cmd = build_mux_command(
            "/video/input.mkv",
            ["/audio/m1.aac"],
            "/output/final.mkv",
            subtitle_path=None,
        )

        assert cmd.count("-i") == 2
        assert "/subs/caption.srt" not in cmd


class TestBuildMkvmergeMuxCommand:
    def test_video_input_is_first_without_audio_or_tags(self):
        cmd = build_mkvmerge_mux_command(
            "/bin/mkvmerge",
            "/video/input.mkv",
            ["/audio/m1.aac"],
            "/output/final.mkv",
        )

        assert cmd[:4] == [
            "/bin/mkvmerge",
            "-o",
            "/output/final.mkv",
            "--disable-track-statistics-tags",
        ]
        assert cmd[4:9] == [
            "--no-audio",
            "--no-chapters",
            "--no-global-tags",
            "--no-track-tags",
            "/video/input.mkv",
        ]
        assert "--no-video" not in cmd[4:9]
        assert "--no-subtitles" not in cmd[4:9]

    def test_generated_audio_inputs_follow_video_input(self):
        cmd = build_mkvmerge_mux_command(
            "/bin/mkvmerge",
            "/video/input.mkv",
            ["/audio/m1.aac", "/audio/m2.aac"],
            "/output/final.mkv",
        )

        first_video_index = cmd.index("/video/input.mkv")
        second_video_index = cmd.index("/video/input.mkv", first_video_index + 1)

        assert first_video_index < cmd.index("/audio/m1.aac")
        assert cmd.index("/audio/m1.aac") < cmd.index("/audio/m2.aac")
        assert cmd.index("/audio/m2.aac") < second_video_index

    def test_original_source_audio_only_input_is_appended_after_generated_audio_when_kept(self):
        cmd = build_mkvmerge_mux_command(
            "/bin/mkvmerge",
            "/video/input.mkv",
            ["/audio/m1.aac", "/audio/m2.aac"],
            "/output/final.mkv",
            keep_original_audio=True,
        )

        assert cmd[-8:] == [
            "--no-video",
            "--no-subtitles",
            "--no-chapters",
            "--no-global-tags",
            "--no-track-tags",
            "--default-track-flag",
            "-1:no",
            "/video/input.mkv",
        ]

    def test_skips_original_audio_uses_source_video_once_with_no_audio(self):
        cmd = build_mkvmerge_mux_command(
            "/bin/mkvmerge",
            "/video/input.mkv",
            ["/audio/m1.aac"],
            "/output/final.mkv",
            keep_original_audio=False,
        )

        video_index = cmd.index("/video/input.mkv")
        video_segment = cmd[4:video_index]

        assert cmd.count("/video/input.mkv") == 1
        assert video_segment == [
            "--no-audio",
            "--no-chapters",
            "--no-global-tags",
            "--no-track-tags",
        ]
        assert "-1:no" not in cmd

    def test_suppresses_track_and_statistics_tags_for_every_input(self):
        cmd = build_mkvmerge_mux_command(
            "/bin/mkvmerge",
            "/video/input.mkv",
            ["/audio/m1.aac", "/audio/m2.aac"],
            "/output/final.mkv",
            keep_original_audio=True,
        )

        assert "--disable-track-statistics-tags" in cmd
        path_indices = []
        start = 0
        for path in ["/video/input.mkv", "/audio/m1.aac", "/audio/m2.aac", "/video/input.mkv"]:
            index = cmd.index(path, start)
            path_indices.append(index)
            start = index + 1

        segment_starts = [4, path_indices[0] + 1, path_indices[1] + 1, path_indices[2] + 1]
        for start, end in zip(segment_starts, path_indices):
            segment = cmd[start:end]
            assert "--no-chapters" in segment
            assert "--no-global-tags" in segment
            assert "--no-track-tags" in segment

    def test_generated_audio_inputs_disable_video_subtitles_and_tags(self):
        cmd = build_mkvmerge_mux_command(
            "/bin/mkvmerge",
            "/video/input.mkv",
            ["/audio/m1.aac"],
            "/output/final.mkv",
        )

        audio_index = cmd.index("/audio/m1.aac")
        audio_segment = cmd[cmd.index("/video/input.mkv") + 1:audio_index]

        assert audio_segment == [
            "--no-video",
            "--no-subtitles",
            "--no-chapters",
            "--no-global-tags",
            "--no-track-tags",
            "--default-track-flag",
            "0:yes",
        ]

    def test_sets_only_first_final_audio_as_default_track(self):
        cmd = build_mkvmerge_mux_command(
            "/bin/mkvmerge",
            "/video/input.mkv",
            ["/audio/m1.aac", "/audio/m2.aac", "/audio/m3.aac"],
            "/output/final.mkv",
        )

        default_track_indices = [
            i
            for i, value in enumerate(cmd)
            if value == "--default-track-flag" and cmd[i + 1].startswith("0:")
        ]
        assert [cmd[i + 1] for i in default_track_indices] == ["0:yes", "0:no", "0:no"]
        assert default_track_indices[0] < cmd.index("/audio/m1.aac")
        assert default_track_indices[1] < cmd.index("/audio/m2.aac")
        assert default_track_indices[2] < cmd.index("/audio/m3.aac")

    def test_appends_external_subtitle_input_segment(self):
        cmd = build_mkvmerge_mux_command(
            "/bin/mkvmerge",
            "/video/input.mkv",
            ["/audio/m1.aac"],
            "/output/final.mkv",
            subtitle_path="/subs/caption.ass",
        )

        subtitle_index = cmd.index("/subs/caption.ass")

        assert cmd[subtitle_index - 7:subtitle_index] == [
            "--no-video",
            "--no-audio",
            "--no-chapters",
            "--no-global-tags",
            "--no-track-tags",
            "--default-track-flag",
            "0:no",
        ]

    def test_no_external_subtitle_keeps_existing_tail(self):
        cmd = build_mkvmerge_mux_command(
            "/bin/mkvmerge",
            "/video/input.mkv",
            ["/audio/m1.aac"],
            "/output/final.mkv",
            subtitle_path=None,
        )

        assert "/subs/caption.ass" not in cmd


class TestBuildExportAacCommand:
    def test_exports_container_audio_to_adts_aac(self):
        cmd = build_export_aac_command("/tmp/in.m4a", "/tmp/out.aac")
        assert cmd == [
            "ffmpeg",
            "-y",
            "-i", "/tmp/in.m4a",
            "-vn",
            "-c:a", "copy",
            "-f", "adts",
            "/tmp/out.aac",
        ]

    def test_sets_first_mixed_audio_as_default_track(self):
        cmd = build_mux_command("/video/input.mkv", ["/audio/m1.aac", "/audio/m2.aac"], "/output/final.mkv")

        assert "-disposition:a" in cmd
        assert cmd[cmd.index("-disposition:a") + 1] == "0"
        assert "-disposition:a:0" in cmd
        assert cmd[cmd.index("-disposition:a:0") + 1] == "default"
        assert "-disposition:a:1" not in cmd

    def test_clears_original_audio_default_when_kept(self):
        cmd = build_mux_command(
            "/video/input.mkv",
            ["/audio/m1.aac", "/audio/m2.aac"],
            "/output/final.mkv",
            keep_original_audio=True,
        )

        assert "-disposition:a" in cmd
        assert cmd[cmd.index("-disposition:a") + 1] == "0"
        assert "-disposition:a:2" not in cmd


class TestBuildPreviewCommand:
    def test_contains_default_preview_window(self):
        cmd = build_preview_command("/audio/base.aac", "/audio/bg.aac", 0.6, "/output/preview.aac")
        filter_str = " ".join(cmd)
        assert "asetpts=PTS-STARTPTS" in filter_str
        assert "atrim=start=" not in filter_str
        assert "-stream_loop" in cmd
        assert cmd[cmd.index("-stream_loop") + 1] == "-1"
        assert "-t" in cmd
        assert cmd[cmd.index("-t") + 1] == str(PREVIEW_DURATION_SECONDS)

    def test_supports_start_and_duration(self):
        cmd = build_preview_command(
            "/audio/base.aac",
            "/audio/bg.aac",
            0.6,
            "/output/preview.aac",
            start_seconds=2.5,
            duration_seconds=7.5,
        )
        assert cmd[:7] == ["ffmpeg", "-y", "-hwaccel", "auto", "-ss", "2.5", "-i"]
        assert "-t" in cmd
        assert cmd[cmd.index("-t") + 1] == "7.5"

    def test_supports_different_base_and_bg_start_offsets(self):
        cmd = build_preview_command(
            "/audio/base.aac",
            "/audio/bg.aac",
            0.6,
            "/output/preview.aac",
            start_seconds=2.5,
            base_start_seconds=0.0,
            bg_start_seconds=2.5,
            duration_seconds=10.0,
        )
        assert cmd[:5] == ["ffmpeg", "-y", "-hwaccel", "auto", "-i"]
        bg_i = cmd.index("/audio/bg.aac")
        assert cmd[bg_i - 5:bg_i + 1] == ["-stream_loop", "-1", "-ss", "2.5", "-i", "/audio/bg.aac"]

    def test_rejects_negative_start_seconds(self):
        with pytest.raises(ValueError, match="start_seconds must be >= 0"):
            build_preview_command(
                "/audio/base.aac",
                "/audio/bg.aac",
                0.6,
                "/output/preview.aac",
                start_seconds=-1.0,
            )

    @pytest.mark.parametrize("duration_seconds", [0.0, -1.0])
    def test_rejects_non_positive_duration_seconds(self, duration_seconds):
        with pytest.raises(ValueError, match="duration_seconds must be > 0"):
            build_preview_command(
                "/audio/base.aac",
                "/audio/bg.aac",
                0.6,
                "/output/preview.aac",
                duration_seconds=duration_seconds,
            )

    def test_rejects_negative_base_start_seconds(self):
        with pytest.raises(ValueError, match="base_start_seconds must be >= 0"):
            build_preview_command(
                "/audio/base.aac",
                "/audio/bg.aac",
                0.6,
                "/output/preview.aac",
                base_start_seconds=-1.0,
            )

    def test_rejects_negative_bg_start_seconds(self):
        with pytest.raises(ValueError, match="bg_start_seconds must be >= 0"):
            build_preview_command(
                "/audio/base.aac",
                "/audio/bg.aac",
                0.6,
                "/output/preview.aac",
                bg_start_seconds=-1.0,
            )


class TestRunFfmpegCommand:
    @patch("subprocess.run")
    def test_returns_none_on_success(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""
        err = run_ffmpeg_command(["ffmpeg", "-version"], timeout=5, default_message="失败")
        assert err is None

    @patch("subprocess.run")
    def test_returns_stderr_tail_on_failure(self, mock_run):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "line1\nline2\nline3\nline4\n"
        err = run_ffmpeg_command(["ffmpeg"], timeout=5, default_message="失败")
        assert err == "失败\n\nline2\nline3\nline4"

    @patch("subprocess.run")
    def test_returns_exception_message(self, mock_run):
        mock_run.side_effect = TimeoutError("timed out")
        err = run_ffmpeg_command(["ffmpeg"], timeout=5, default_message="失败")
        assert err == "失败\n\ntimed out"


class TestValidate:
    def _write_valid_inputs(self, base_dir, *, input_name="video.mkv"):
        input_path = os.path.join(base_dir, input_name)
        audio_dir = os.path.join(base_dir, "audio")
        os.makedirs(audio_dir)
        open(input_path, "w").close()
        open(os.path.join(audio_dir, "bgm.aac"), "w").close()
        return input_path, audio_dir

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

    def test_boxed_video_rejects_missing_secondary_video(self):
        with tempfile.TemporaryDirectory() as d:
            video_path, audio_dir = self._write_valid_inputs(d)
            secondary_path = os.path.join(d, "missing-secondary.mkv")
            cfg = CombatAudioConfig(
                input_path=video_path,
                audio_dir=audio_dir,
                boxed=True,
                secondary_video_paths=[secondary_path],
            )

            ok, err = validate(cfg)

            assert ok is False
            assert err == f"副视频不存在: {secondary_path}"

    def test_non_boxed_ignores_missing_secondary_video(self):
        with tempfile.TemporaryDirectory() as d:
            video_path, audio_dir = self._write_valid_inputs(d)
            cfg = CombatAudioConfig(
                input_path=video_path,
                audio_dir=audio_dir,
                boxed=False,
                secondary_video_paths=[os.path.join(d, "missing-secondary.mkv")],
            )

            ok, err = validate(cfg)

            assert ok is True
            assert err is None

    def test_pure_audio_main_input_ignores_missing_secondary_video(self):
        with tempfile.TemporaryDirectory() as d:
            input_path, audio_dir = self._write_valid_inputs(d, input_name="input.aac")
            cfg = CombatAudioConfig(
                input_path=input_path,
                audio_dir=audio_dir,
                boxed=True,
                secondary_video_paths=[os.path.join(d, "missing-secondary.mkv")],
            )

            ok, err = validate(cfg)

            assert ok is True
            assert err is None

    def test_boxed_video_rejects_existing_non_video_secondary(self, monkeypatch):
        monkeypatch.setattr("src.core.processors.combat_audio.has_video_stream", lambda path: False)
        with tempfile.TemporaryDirectory() as d:
            video_path, audio_dir = self._write_valid_inputs(d)
            secondary_path = os.path.join(d, "secondary.txt")
            open(secondary_path, "w").close()
            cfg = CombatAudioConfig(
                input_path=video_path,
                audio_dir=audio_dir,
                boxed=True,
                secondary_video_paths=[secondary_path],
            )

            ok, err = validate(cfg)

            assert ok is False
            assert err == f"副视频不是视频文件: {secondary_path}"


class TestValidateSecondaryVideos:
    def test_ignored_when_not_boxed(self):
        cfg = CombatAudioConfig(
            input_path="/input/video.mkv",
            audio_dir="/audio",
            boxed=False,
            secondary_video_paths=["/missing/secondary.mkv", "/audio/song.aac"],
        )

        ok, err = validate_secondary_videos(cfg, is_audio=False)

        assert ok is True
        assert err is None

    def test_error_when_boxed_secondary_is_missing(self):
        with tempfile.TemporaryDirectory() as d:
            missing_path = os.path.join(d, "missing.mkv")
            cfg = CombatAudioConfig(
                input_path="/input/video.mkv",
                audio_dir="/audio",
                boxed=True,
                secondary_video_paths=[missing_path],
            )

            ok, err = validate_secondary_videos(cfg, is_audio=False)

            assert ok is False
            assert err == f"副视频不存在: {missing_path}"

    def test_ignored_for_pure_audio_main_input(self):
        cfg = CombatAudioConfig(
            input_path="/input/audio.aac",
            audio_dir="/audio",
            boxed=True,
            secondary_video_paths=["/missing/secondary.mkv", "/audio/song.aac"],
        )

        ok, err = validate_secondary_videos(cfg, is_audio=True)

        assert ok is True
        assert err is None

    def test_existing_secondary_video_passes(self, monkeypatch):
        monkeypatch.setattr("src.core.processors.combat_audio.has_video_stream", lambda path: True)
        with tempfile.TemporaryDirectory() as d:
            secondary_path = os.path.join(d, "secondary.mkv")
            open(secondary_path, "w").close()
            cfg = CombatAudioConfig(
                input_path="/input/video.mkv",
                audio_dir="/audio",
                boxed=True,
                secondary_video_paths=[secondary_path],
            )

            ok, err = validate_secondary_videos(cfg, is_audio=False)

            assert ok is True
            assert err is None

    def test_existing_txt_secondary_path_is_rejected_when_boxed_video_input(self):
        with tempfile.TemporaryDirectory() as d:
            secondary_path = os.path.join(d, "secondary.txt")
            open(secondary_path, "w").close()
            cfg = CombatAudioConfig(
                input_path="/input/video.mkv",
                audio_dir="/audio",
                boxed=True,
                secondary_video_paths=[secondary_path],
            )

            ok, err = validate_secondary_videos(cfg, is_audio=False)

            assert ok is False
            assert err == f"副视频不是视频文件: {secondary_path}"

    def test_audio_only_mkv_secondary_path_is_rejected_when_boxed_video_input(self, monkeypatch):
        monkeypatch.setattr("src.core.processors.combat_audio.has_video_stream", lambda path: False)
        with tempfile.TemporaryDirectory() as d:
            secondary_path = os.path.join(d, "secondary.mkv")
            open(secondary_path, "w").close()
            cfg = CombatAudioConfig(
                input_path="/input/video.mkv",
                audio_dir="/audio",
                boxed=True,
                secondary_video_paths=[secondary_path],
            )

            ok, err = validate_secondary_videos(cfg, is_audio=False)

            assert ok is False
            assert err == f"副视频不是视频文件: {secondary_path}"

    def test_pure_audio_secondary_path_is_rejected_when_boxed_video_input(self):
        with tempfile.TemporaryDirectory() as d:
            secondary_path = os.path.join(d, "secondary.aac")
            open(secondary_path, "w").close()
            cfg = CombatAudioConfig(
                input_path="/input/video.mkv",
                audio_dir="/audio",
                boxed=True,
                secondary_video_paths=[secondary_path],
            )

            ok, err = validate_secondary_videos(cfg, is_audio=False)

            assert ok is False
            assert err == f"副视频不是视频文件: {secondary_path}"


class TestValidateSubtitleFile:
    def test_boxed_video_accepts_srt_subtitle(self, tmp_path, monkeypatch):
        input_path = tmp_path / "main.mkv"
        input_path.write_bytes(b"")
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "bg.aac").write_bytes(b"")
        subtitle_path = tmp_path / "caption.srt"
        subtitle_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n", encoding="utf-8")

        monkeypatch.setattr("src.core.processors.combat_audio.has_video_stream", lambda path: True)

        cfg = CombatAudioConfig(
            input_path=str(input_path),
            audio_dir=str(audio_dir),
            boxed=True,
            subtitle_path=str(subtitle_path),
        )

        ok, err = validate(cfg)

        assert ok is True
        assert err is None

    def test_boxed_video_accepts_ass_subtitle(self, tmp_path, monkeypatch):
        input_path = tmp_path / "main.mkv"
        input_path.write_bytes(b"")
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "bg.aac").write_bytes(b"")
        subtitle_path = tmp_path / "caption.ass"
        subtitle_path.write_text("[Script Info]\nTitle: Test\n", encoding="utf-8")

        monkeypatch.setattr("src.core.processors.combat_audio.has_video_stream", lambda path: True)

        cfg = CombatAudioConfig(
            input_path=str(input_path),
            audio_dir=str(audio_dir),
            boxed=True,
            subtitle_path=str(subtitle_path),
        )

        ok, err = validate(cfg)

        assert ok is True
        assert err is None

    def test_boxed_video_rejects_missing_subtitle(self, tmp_path, monkeypatch):
        input_path = tmp_path / "main.mkv"
        input_path.write_bytes(b"")
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "bg.aac").write_bytes(b"")
        subtitle_path = tmp_path / "missing.srt"

        monkeypatch.setattr("src.core.processors.combat_audio.has_video_stream", lambda path: True)

        cfg = CombatAudioConfig(
            input_path=str(input_path),
            audio_dir=str(audio_dir),
            boxed=True,
            subtitle_path=str(subtitle_path),
        )

        ok, err = validate(cfg)

        assert ok is False
        assert err == f"字幕文件不存在: {subtitle_path}"

    def test_boxed_video_rejects_subtitle_directory(self, tmp_path, monkeypatch):
        input_path = tmp_path / "main.mkv"
        input_path.write_bytes(b"")
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "bg.aac").write_bytes(b"")
        subtitle_path = tmp_path / "caption.srt"
        subtitle_path.mkdir()

        monkeypatch.setattr("src.core.processors.combat_audio.has_video_stream", lambda path: True)

        cfg = CombatAudioConfig(
            input_path=str(input_path),
            audio_dir=str(audio_dir),
            boxed=True,
            subtitle_path=str(subtitle_path),
        )

        ok, err = validate(cfg)

        assert ok is False
        assert err == f"字幕文件不是文件: {subtitle_path}"

    def test_boxed_video_rejects_unsupported_subtitle_extension(self, tmp_path, monkeypatch):
        input_path = tmp_path / "main.mkv"
        input_path.write_bytes(b"")
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "bg.aac").write_bytes(b"")
        subtitle_path = tmp_path / "caption.txt"
        subtitle_path.write_text("not a supported subtitle", encoding="utf-8")

        monkeypatch.setattr("src.core.processors.combat_audio.has_video_stream", lambda path: True)

        cfg = CombatAudioConfig(
            input_path=str(input_path),
            audio_dir=str(audio_dir),
            boxed=True,
            subtitle_path=str(subtitle_path),
        )

        ok, err = validate(cfg)

        assert ok is False
        assert err == f"字幕文件格式不支持: {subtitle_path}"

    def test_non_boxed_output_ignores_invalid_subtitle_path(self, tmp_path):
        input_path = tmp_path / "main.mkv"
        input_path.write_bytes(b"")
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "bg.aac").write_bytes(b"")

        cfg = CombatAudioConfig(
            input_path=str(input_path),
            audio_dir=str(audio_dir),
            boxed=False,
            subtitle_path=str(tmp_path / "missing.txt"),
        )

        ok, err = validate(cfg)

        assert ok is True
        assert err is None


class TestSanitizeOutputStem:
    def test_replaces_cross_platform_illegal_characters(self):
        assert sanitize_output_stem('b\\c:d*e?f"g<h>i|j') == "b_c_d_e_f_g_h_i_j"

    def test_uses_audio_for_empty_result(self):
        assert sanitize_output_stem("////") == "audio"

    def test_strips_extension_and_compresses_spaces(self):
        assert sanitize_output_stem("  my   song .mp3") == "my song"

    def test_extensionless_path_uses_basename(self):
        assert sanitize_output_stem('/tmp/track') == 'track'


class TestNamedAudioOutputPaths:
    def test_non_boxed_outputs_include_original_background_name(self):
        with tempfile.TemporaryDirectory() as d:
            video_path = os.path.join(d, "episode_01.mkv")
            output_dir = os.path.join(d, "output")
            cfg = CombatAudioConfig(
                input_path=video_path,
                audio_dir="/audio",
                output_dir=output_dir,
                mix_enabled=True,
                boxed=False,
            )

            paths = resolve_output_path(
                cfg,
                2,
                audio_filenames=["bg one.mp3", "bad/name.aac"],
                timestamp="20260507190000",
            )

            batch_dir = os.path.join(output_dir, "episode_01_mixed_20260507190000")
            assert paths == [
                os.path.join(batch_dir, "01_bg one_mixed.aac"),
                os.path.join(batch_dir, "02_name_mixed.aac"),
            ]

    def test_partial_audio_filenames_falls_back_for_unnamed_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            video_path = os.path.join(d, "episode_01.mkv")
            output_dir = os.path.join(d, "output")
            cfg = CombatAudioConfig(
                input_path=video_path,
                audio_dir="/audio",
                output_dir=output_dir,
                mix_enabled=False,
                boxed=False,
            )

            paths = resolve_output_path(
                cfg,
                3,
                audio_filenames=["bg one.mp3"],
                timestamp="20260507190000",
            )

            batch_dir = os.path.join(output_dir, "episode_01_aligned_20260507190000")
            assert paths == [
                os.path.join(batch_dir, "01_bg one_aligned.aac"),
                os.path.join(batch_dir, "episode_01_aligned_01.aac"),
                os.path.join(batch_dir, "episode_01_aligned_02.aac"),
            ]


class TestResolveMkvOutputPaths:
    def test_single_mkv_keeps_existing_name_when_no_secondary_videos(self):
        with tempfile.TemporaryDirectory() as d:
            video_path = os.path.join(d, "episode_01.mkv")
            output_dir = os.path.join(d, "output")
            cfg = CombatAudioConfig(
                input_path=video_path,
                audio_dir="/audio",
                output_dir=output_dir,
                boxed=True,
            )

            paths = resolve_mkv_output_paths(cfg, timestamp="20260507190000")

            assert paths == [os.path.join(output_dir, "episode_01_20260507190000.mkv")]

    def test_secondary_videos_use_part_suffixes_and_same_timestamp(self):
        with tempfile.TemporaryDirectory() as d:
            video_path = os.path.join(d, "episode_01.mkv")
            output_dir = os.path.join(d, "output")
            cfg = CombatAudioConfig(
                input_path=video_path,
                audio_dir="/audio",
                output_dir=output_dir,
                boxed=True,
                secondary_video_paths=[
                    os.path.join(d, "episode_01_part2.mkv"),
                    os.path.join(d, "episode_01_part3.mkv"),
                ],
            )

            paths = resolve_mkv_output_paths(cfg, timestamp="20260507190000")

            assert paths == [
                os.path.join(output_dir, "episode_01_20260507190000-part1.mkv"),
                os.path.join(output_dir, "episode_01_20260507190000-part2.mkv"),
                os.path.join(output_dir, "episode_01_20260507190000-part3.mkv"),
            ]


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

    def test_non_boxed_outputs_are_grouped_in_batch_subdirectory(self):
        with tempfile.TemporaryDirectory() as d, patch(
            "src.core.processors.combat_audio.time.strftime",
            return_value="20260507123456",
        ):
            video_path = os.path.join(d, "episode_01.mkv")
            output_dir = os.path.join(d, "output")
            cfg = CombatAudioConfig(
                input_path=video_path,
                audio_dir="/audio",
                output_dir=output_dir,
                mix_enabled=True,
                boxed=False,
            )

            paths = resolve_output_path(cfg, 2)

            assert os.path.dirname(paths[0]) == os.path.join(output_dir, "episode_01_mixed_20260507123456")
            assert os.path.dirname(paths[1]) == os.path.join(output_dir, "episode_01_mixed_20260507123456")
