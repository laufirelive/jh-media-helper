import os
import tempfile

from PIL import Image

from src.core.config import BackgroundMode, OutputFormat, PicSeqConfig
from src.core.processors.pic_seq import build_command, detect_alpha, detect_resolution, detect_scan_format, validate


def _create_image_seq(tmp_dir: str, count: int, digits: int = 6, ext: str = "png", mode: str = "RGB"):
    """Helper: create numbered image files in tmp_dir."""
    for i in range(1, count + 1):
        name = f"{str(i).zfill(digits)}.{ext}"
        img = Image.new(mode, (1920, 1080))
        img.save(os.path.join(tmp_dir, name))


class TestDetectScanFormat:
    def test_six_digit_png(self):
        with tempfile.TemporaryDirectory() as d:
            _create_image_seq(d, 5, digits=6, ext="png")
            fmt, count = detect_scan_format(d)
            assert fmt == "%06d.png"
            assert count == 5

    def test_four_digit_jpg(self):
        with tempfile.TemporaryDirectory() as d:
            _create_image_seq(d, 3, digits=4, ext="jpg")
            fmt, count = detect_scan_format(d)
            assert fmt == "%04d.jpg"
            assert count == 3

    def test_empty_dir_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            result = detect_scan_format(d)
            assert result is None

    def test_mixed_names_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            Image.new("RGB", (10, 10)).save(os.path.join(d, "frame_001.png"))
            Image.new("RGB", (10, 10)).save(os.path.join(d, "shot_002.png"))
            result = detect_scan_format(d)
            assert result is None

    def test_mixed_extensions_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            Image.new("RGB", (10, 10)).save(os.path.join(d, "000001.png"))
            Image.new("RGB", (10, 10)).save(os.path.join(d, "000002.jpg"))
            result = detect_scan_format(d)
            assert result is None


class TestDetectResolution:
    def test_reads_first_image(self):
        with tempfile.TemporaryDirectory() as d:
            _create_image_seq(d, 3, digits=6, ext="png")
            w, h = detect_resolution(d, "%06d.png")
            assert w == 1920
            assert h == 1080


class TestDetectAlpha:
    def test_rgba_has_alpha(self):
        with tempfile.TemporaryDirectory() as d:
            _create_image_seq(d, 1, digits=6, ext="png", mode="RGBA")
            assert detect_alpha(d, "%06d.png") is True

    def test_rgb_no_alpha(self):
        with tempfile.TemporaryDirectory() as d:
            _create_image_seq(d, 1, digits=6, ext="png", mode="RGB")
            assert detect_alpha(d, "%06d.png") is False


class TestValidate:
    def test_valid_dir(self):
        with tempfile.TemporaryDirectory() as d:
            _create_image_seq(d, 10, digits=6, ext="png")
            cfg = PicSeqConfig(input_dir=d, scan_format="%06d.png")
            ok, count, err = validate(cfg)
            assert ok is True
            assert count == 10
            assert err is None

    def test_missing_dir(self):
        cfg = PicSeqConfig(input_dir="/nonexistent/path", scan_format="%06d.png")
        ok, count, err = validate(cfg)
        assert ok is False
        assert "不存在" in err or "not exist" in err.lower()

    def test_no_matching_files(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = PicSeqConfig(input_dir=d, scan_format="%06d.png")
            ok, count, err = validate(cfg)
            assert ok is False
            assert count == 0


class TestBuildCommand:
    def test_mov_prores(self):
        cfg = PicSeqConfig(
            input_dir="/tmp/seq", fps=120, width=3840, height=2160,
            scan_format="%06d.png", output_format=OutputFormat.MOV_PRORES,
        )
        cmd = build_command(cfg, encoder="prores_ks", has_alpha=True)
        assert cmd[0] == "ffmpeg"
        assert "-r" in cmd
        assert "120" in cmd
        assert "prores_ks" in cmd
        assert "yuva444p" in cmd
        assert cmd[-1].endswith(".mov")

    def test_mp4_hevc_with_green_bg(self):
        cfg = PicSeqConfig(
            input_dir="/tmp/seq", fps=60, bitrate_mbps=16, width=1920, height=1080,
            scan_format="%06d.png", output_format=OutputFormat.MP4_HEVC,
            background_mode=BackgroundMode.GREEN,
        )
        cmd = build_command(cfg, encoder="hevc_videotoolbox", has_alpha=True)
        assert "hevc_videotoolbox" in cmd
        assert "16M" in cmd
        assert cmd[-1].endswith(".mp4")
        vf_idx = cmd.index("-vf")
        assert "0x00FF00" in cmd[vf_idx + 1]

    def test_mp4_h264_no_alpha_no_overlay(self):
        cfg = PicSeqConfig(
            input_dir="/tmp/seq", fps=30, bitrate_mbps=8, width=1920, height=1080,
            scan_format="%06d.png", output_format=OutputFormat.MP4_H264,
            background_mode=BackgroundMode.GREEN,
        )
        cmd = build_command(cfg, encoder="libx264", has_alpha=False)
        assert "libx264" in cmd
        assert "-vf" not in cmd
        assert cmd[-1].endswith(".mp4")

    def test_output_naming(self):
        cfg = PicSeqConfig(
            input_dir="/path/to/scene01", scan_format="%06d.png",
            output_format=OutputFormat.MOV_PRORES, width=3840, height=2160,
        )
        cmd = build_command(cfg, encoder="prores_ks", has_alpha=True)
        assert cmd[-1] == "/path/to/sscene01.mov"

    def test_custom_output_dir(self):
        cfg = PicSeqConfig(
            input_dir="/path/to/scene01", output_dir="/output",
            scan_format="%06d.png", output_format=OutputFormat.MOV_PRORES,
            width=3840, height=2160,
        )
        cmd = build_command(cfg, encoder="prores_ks", has_alpha=True)
        assert cmd[-1] == "/output/sscene01.mov"

    def test_mp4_blue_bg(self):
        cfg = PicSeqConfig(
            input_dir="/tmp/seq", fps=60, width=1920, height=1080,
            scan_format="%06d.png", output_format=OutputFormat.MP4_HEVC,
            background_mode=BackgroundMode.BLUE, bitrate_mbps=16,
        )
        cmd = build_command(cfg, encoder="hevc_videotoolbox", has_alpha=True)
        vf_idx = cmd.index("-vf")
        assert "0x0000FF" in cmd[vf_idx + 1]
