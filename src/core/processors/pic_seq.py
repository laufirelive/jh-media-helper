import os
import re
from collections import Counter

from PIL import Image

from src.core.config import BackgroundMode, OutputFormat, PicSeqConfig

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".exr", ".tga", ".tif", ".tiff"}

BG_COLOR_MAP = {
    BackgroundMode.GREEN: "0x00FF00",
    BackgroundMode.BLUE: "0x0000FF",
}


def detect_scan_format(input_dir: str) -> tuple[str, int] | None:
    """Detect the ffmpeg scan format from image filenames.
    Returns (format_string, file_count) or None if detection fails.
    Only scans filenames via os.listdir — never loads image data.
    """
    entries = os.listdir(input_dir)
    image_files = []
    for name in entries:
        ext = os.path.splitext(name)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            image_files.append(name)

    if not image_files:
        return None

    extensions = {os.path.splitext(f)[1].lower() for f in image_files}
    if len(extensions) != 1:
        return None
    ext = extensions.pop()

    pattern = re.compile(r"^(\d+)$")
    digit_widths = Counter()
    for name in image_files:
        stem = os.path.splitext(name)[0]
        m = pattern.match(stem)
        if not m:
            return None
        digit_widths[len(stem)] += 1

    if len(digit_widths) != 1:
        return None

    width = next(iter(digit_widths))
    fmt = f"%0{width}d{ext}"
    return fmt, len(image_files)


def detect_resolution(input_dir: str, scan_format: str) -> tuple[int, int]:
    """Read resolution from the first image. Only reads header, not pixel data."""
    entries = sorted(os.listdir(input_dir))
    ext = os.path.splitext(scan_format)[1]
    for name in entries:
        if os.path.splitext(name)[1].lower() == ext.lower():
            path = os.path.join(input_dir, name)
            with Image.open(path) as img:
                return img.size
    raise FileNotFoundError(f"No image files with extension {ext} in {input_dir}")


def detect_alpha(input_dir: str, scan_format: str) -> bool:
    """Check if the first image has an alpha channel. Only reads header."""
    entries = sorted(os.listdir(input_dir))
    ext = os.path.splitext(scan_format)[1]
    for name in entries:
        if os.path.splitext(name)[1].lower() == ext.lower():
            path = os.path.join(input_dir, name)
            with Image.open(path) as img:
                return img.mode in ("RGBA", "LA", "PA")
    return False


def validate(config: PicSeqConfig) -> tuple[bool, int, str | None]:
    """Validate config before processing. Returns (ok, file_count, error_message)."""
    if not os.path.isdir(config.input_dir):
        return False, 0, f"文件夹不存在: {config.input_dir}"
    if config.scan_format is None:
        return False, 0, "扫描格式未指定"
    ext = os.path.splitext(config.scan_format)[1]
    count = 0
    for name in os.listdir(config.input_dir):
        if os.path.splitext(name)[1].lower() == ext.lower():
            count += 1
    if count == 0:
        return False, 0, f"未找到匹配 {config.scan_format} 的图片文件"
    return True, count, None


def _resolve_output_path(config: PicSeqConfig) -> str:
    """Resolve the output file path."""
    dirname = os.path.basename(config.input_dir)
    if config.output_format == OutputFormat.MOV_PRORES:
        filename = f"s{dirname}.mov"
    else:
        filename = f"s{dirname}.mp4"
    if config.output_dir:
        return os.path.join(config.output_dir, filename)
    else:
        parent = os.path.dirname(config.input_dir)
        return os.path.join(parent, filename)


def build_command(config: PicSeqConfig, encoder: str, has_alpha: bool) -> list[str]:
    """Build the ffmpeg command as a list of arguments."""
    input_pattern = os.path.join(config.input_dir, config.scan_format)
    output_path = _resolve_output_path(config)
    cmd = ["ffmpeg", "-y", "-r", str(config.fps), "-i", input_pattern]
    if config.output_format == OutputFormat.MOV_PRORES:
        cmd += ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p"]
    else:
        cmd += ["-c:v", encoder]
        if config.output_format in (OutputFormat.MP4_HEVC, OutputFormat.MP4_H264):
            cmd += ["-b:v", f"{config.bitrate_mbps}M"]
        if has_alpha and config.background_mode != BackgroundMode.TRANSPARENT:
            bg_color = BG_COLOR_MAP.get(config.background_mode, "0x00FF00")
            vf = (
                f"color=c={bg_color}:s={config.width}x{config.height}:r={config.fps}[bg];"
                f"[bg][0:v]overlay=shortest=1"
            )
            cmd += ["-vf", vf]
        cmd += ["-pix_fmt", "yuv420p"]
    cmd += ["-s", f"{config.width}x{config.height}"]
    cmd.append(output_path)
    return cmd
