import re
import subprocess
import threading

from PyQt6.QtCore import QThread, pyqtSignal

from src.core.config import OutputFormat, PicSeqConfig, TaskType
from src.core.encoder_registry import EncoderRegistry
from src.core.processors import pic_seq

_FRAME_RE = re.compile(r"frame=\s*(\d+)")


def parse_progress(line: str) -> int | None:
    """Extract frame number from ffmpeg stderr line."""
    m = _FRAME_RE.search(line)
    if m:
        return int(m.group(1))
    return None


class FFmpegWorker(QThread):
    """Executes ffmpeg commands in a background thread with progress reporting."""

    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        task_type: TaskType,
        config: dict,
        encoder_registry: EncoderRegistry,
        total_frames: int = 0,
    ):
        super().__init__()
        self._task_type = task_type
        self._config = config
        self._encoder_registry = encoder_registry
        self._total_frames = total_frames
        self._cancel_event = threading.Event()
        self._process: subprocess.Popen | None = None

    def _emit_cancelled_if_needed(self) -> bool:
        """若已请求取消则发出 error 并返回 True（用于 Popen 前等阶段及时退出）。"""
        if self._cancel_event.is_set():
            self.error.emit("已取消")
            return True
        return False

    def _terminate_process(self) -> None:
        """优先温和终止，超时后强制 kill，确保取消操作可见生效。"""
        if self._process is None:
            return
        if self._process.poll() is not None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=1.0)

    def run(self):
        try:
            if self._task_type == TaskType.PIC_SEQ:
                self._run_pic_seq()
            else:
                self.error.emit(f"Unsupported task type: {self._task_type}")
        except Exception as e:
            self.error.emit(str(e))

    def _run_pic_seq(self):
        # 在尚未启动 ffmpeg 前也可取消；否则用户点「取消」无任何信号，界面不会恢复
        if self._emit_cancelled_if_needed():
            return
        config = PicSeqConfig.from_dict(self._config)
        if self._emit_cancelled_if_needed():
            return
        has_alpha = pic_seq.detect_alpha(config.input_dir, config.scan_format)
        if self._emit_cancelled_if_needed():
            return

        if config.output_format == OutputFormat.MOV_PRORES:
            encoder = "prores_ks"
        elif config.hw_accel:
            encoder = self._encoder_registry.get_best_hevc() or self._encoder_registry.get_fallback()
        else:
            encoder = self._encoder_registry.get_fallback()

        cmd = pic_seq.build_command(config, encoder=encoder, has_alpha=has_alpha)
        if self._emit_cancelled_if_needed():
            return
        success = self._exec_ffmpeg(cmd)
        if self._emit_cancelled_if_needed():
            return

        if not success and encoder != self._encoder_registry.get_fallback() and config.output_format != OutputFormat.MOV_PRORES:
            fallback = self._encoder_registry.get_fallback()
            self.progress.emit(0, self._total_frames, f"回退到 {fallback}")
            cmd = pic_seq.build_command(config, encoder=fallback, has_alpha=has_alpha)
            success = self._exec_ffmpeg(cmd)
            if self._emit_cancelled_if_needed():
                return

        if self._emit_cancelled_if_needed():
            return

        if success:
            output_path = cmd[-1]
            self.finished.emit(output_path)
        else:
            self.error.emit("FFmpeg 编码失败")

    def _exec_ffmpeg(self, cmd: list[str]) -> bool:
        # 启动子进程前再检查，避免已取消仍去 Popen
        if self._cancel_event.is_set():
            return False
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for raw_line in self._process.stderr:
            if self._cancel_event.is_set():
                self._terminate_process()
                return False
            line = raw_line.decode("utf-8", errors="replace").strip()
            frame = parse_progress(line)
            if frame is not None:
                self.progress.emit(frame, self._total_frames, "编码中")
        self._process.wait()
        return self._process.returncode == 0

    def cancel(self):
        self._cancel_event.set()
        self._terminate_process()
