import logging
import subprocess

logger = logging.getLogger(__name__)

_HEVC_HW_PRIORITY: list[str] = [
    "hevc_nvenc",
    "hevc_videotoolbox",
    "hevc_qsv",
    "hevc_amf",
    "hevc_vaapi",
]


class EncoderRegistry:
    """Probes ffmpeg for available encoders at construction time."""

    def __init__(self) -> None:
        self._available: set[str] = set()
        self._probe()

    def _probe(self) -> None:
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("ffmpeg not found or timed out during encoder probe")
            return

        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2 or parts[0].startswith("-"):
                continue
            self._available.add(parts[1])

        hw = {e for e in _HEVC_HW_PRIORITY if e in self._available}
        if hw:
            logger.info("Hardware HEVC encoders: %s", ", ".join(sorted(hw)))
        else:
            logger.info("No hardware HEVC encoders found")

    def detect(self) -> list[str]:
        return sorted(self._available)

    def is_available(self, encoder_name: str) -> bool:
        return encoder_name in self._available

    def get_best_hevc(self) -> str | None:
        for enc in _HEVC_HW_PRIORITY:
            if enc in self._available:
                return enc
        return None

    def get_fallback(self) -> str:
        return "libx264"
