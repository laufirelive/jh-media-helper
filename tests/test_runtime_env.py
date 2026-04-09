from unittest.mock import patch

from src.core.runtime_env import (
    get_missing_ffmpeg_tools,
    has_required_ffmpeg_tools,
    is_frozen,
)


class TestIsFrozen:
    def test_returns_false_when_sys_frozen_missing(self):
        with patch("src.core.runtime_env.getattr", return_value=False):
            assert is_frozen() is False

    def test_returns_true_when_sys_frozen_is_truthy(self):
        with patch("src.core.runtime_env.getattr", return_value=True):
            assert is_frozen() is True


class TestGetMissingFfmpegTools:
    @patch("src.core.runtime_env.shutil.which")
    def test_reports_both_tools_when_missing(self, mock_which):
        mock_which.return_value = None

        assert get_missing_ffmpeg_tools() == ["ffmpeg", "ffprobe"]

    @patch("src.core.runtime_env.shutil.which")
    def test_reports_only_ffprobe_when_ffmpeg_exists(self, mock_which):
        mock_which.side_effect = ["/usr/local/bin/ffmpeg", None]

        assert get_missing_ffmpeg_tools() == ["ffprobe"]


class TestHasRequiredFfmpegTools:
    @patch("src.core.runtime_env.get_missing_ffmpeg_tools")
    def test_returns_true_when_no_tools_missing(self, mock_missing):
        mock_missing.return_value = []

        assert has_required_ffmpeg_tools() is True

    @patch("src.core.runtime_env.get_missing_ffmpeg_tools")
    def test_returns_false_when_any_tool_missing(self, mock_missing):
        mock_missing.return_value = ["ffprobe"]

        assert has_required_ffmpeg_tools() is False
