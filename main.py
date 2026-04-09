import multiprocessing
import platform
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from src.core.runtime_env import get_missing_ffmpeg_tools, has_required_ffmpeg_tools
from src.gui.main_window import MainWindow


def _build_missing_ffmpeg_message() -> str:
    lines = [
        "未检测到 ffmpeg 或 ffprobe。",
        "请先安装 FFmpeg 后重新启动应用。",
        "",
    ]
    if platform.system() == "Windows":
        lines.append("推荐安装方式：winget install ffmpeg")
    else:
        lines.append("推荐安装方式：brew install ffmpeg")
    lines.append("")
    lines.append(f"缺失工具: {', '.join(get_missing_ffmpeg_tools())}")
    return "\n".join(lines)


def main():
    multiprocessing.freeze_support()

    app = QApplication(sys.argv)
    app.setApplicationName("jh-media-helper")

    if not has_required_ffmpeg_tools():
        QMessageBox.critical(None, "缺少 FFmpeg", _build_missing_ffmpeg_message())
        sys.exit(1)
        return

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
