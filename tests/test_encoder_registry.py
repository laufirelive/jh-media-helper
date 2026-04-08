from unittest.mock import patch

from src.core.encoder_registry import EncoderRegistry


class TestEncoderRegistry:
    def test_get_fallback_always_returns_libx264(self):
        with patch("src.core.encoder_registry.EncoderRegistry._probe") as mock:
            registry = EncoderRegistry()
        assert registry.get_fallback() == "libx264"

    def test_get_best_hevc_returns_none_when_no_hw(self):
        registry = EncoderRegistry.__new__(EncoderRegistry)
        registry._available = {"libx264", "libx265"}
        assert registry.get_best_hevc() is None

    def test_get_best_hevc_returns_videotoolbox(self):
        registry = EncoderRegistry.__new__(EncoderRegistry)
        registry._available = {"libx264", "hevc_videotoolbox"}
        assert registry.get_best_hevc() == "hevc_videotoolbox"

    def test_get_best_hevc_prefers_nvenc_over_qsv(self):
        registry = EncoderRegistry.__new__(EncoderRegistry)
        registry._available = {"libx264", "hevc_nvenc", "hevc_qsv"}
        assert registry.get_best_hevc() == "hevc_nvenc"

    def test_is_available(self):
        registry = EncoderRegistry.__new__(EncoderRegistry)
        registry._available = {"libx264", "hevc_nvenc"}
        assert registry.is_available("libx264") is True
        assert registry.is_available("hevc_nvenc") is True
        assert registry.is_available("hevc_videotoolbox") is False

    def test_detect_returns_list(self):
        registry = EncoderRegistry.__new__(EncoderRegistry)
        registry._available = {"libx264", "libx265", "hevc_nvenc"}
        result = registry.detect()
        assert isinstance(result, list)
        assert "libx264" in result
