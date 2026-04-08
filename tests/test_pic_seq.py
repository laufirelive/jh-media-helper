import os
import tempfile

from PIL import Image

from src.core.processors.pic_seq import detect_alpha, detect_resolution, detect_scan_format


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
