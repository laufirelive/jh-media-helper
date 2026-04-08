import os
import re
from collections import Counter

from PIL import Image

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".exr", ".tga", ".tif", ".tiff"}


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
