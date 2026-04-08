import os
import re
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import QThread, pyqtSignal

from src.core.config import CombatAudioConfig, OutputFormat, PicSeqConfig, TaskType
from src.core.encoder_registry import EncoderRegistry
from src.core.processors import combat_audio, pic_seq

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
            elif self._task_type == TaskType.COMBAT_AUDIO:
                self._run_combat_audio()
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

    def _run_combat_audio(self):
        if self._emit_cancelled_if_needed():
            return
        config = CombatAudioConfig.from_dict(self._config)
        is_audio = combat_audio.is_pure_audio(config.input_path)
        audio_files = config.audio_order if config.audio_order else [
            f.filename for f in combat_audio.scan_audio_dir(config.audio_dir)
        ]
        total = len(audio_files)
        if total == 0:
            self.error.emit("音频目录中没有音频文件")
            return

        tmp_dir = tempfile.mkdtemp(prefix="jh_combat_")
        try:
            self._combat_audio_pipeline(config, is_audio, audio_files, total, tmp_dir)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _combat_audio_pipeline(self, config, is_audio, audio_files, total, tmp_dir):
        # Phase 1: Extract base audio (get duration)
        self.progress.emit(0, total, f"[0/{total}] — 提取音频")
        if self._emit_cancelled_if_needed():
            return

        if is_audio:
            base_audio = config.input_path
        else:
            base_audio = os.path.join(tmp_dir, "extracted.aac")
            cmd = combat_audio.build_extract_command(
                config.input_path, config.audio_stream_index, base_audio,
            )
            if not self._exec_ffmpeg(cmd):
                if self._cancel_event.is_set():
                    self.error.emit("已取消")
                    return
                self.error.emit("音频提取失败")
                return

        base_duration = combat_audio.probe_duration(
            base_audio if is_audio else config.input_path
        )
        if base_duration <= 0:
            self.error.emit("无法获取输入时长")
            return

        if self._emit_cancelled_if_needed():
            return

        # Phase 2: Adjust duration (parallel)
        adjusted_dir = os.path.join(tmp_dir, "adjusted")
        os.makedirs(adjusted_dir)
        adjusted_paths = self._parallel_phase(
            config, audio_files, audio_files, total, base_duration, adjusted_dir, "调整时长",
            self._adjust_one,
        )
        if adjusted_paths is None:
            return

        # Phase 3: Mix (parallel, only if mix_enabled)
        if config.mix_enabled:
            mixed_dir = os.path.join(tmp_dir, "mixed")
            os.makedirs(mixed_dir)
            items_with_adjusted = [
                (name, adj) for name, adj in zip(audio_files, adjusted_paths)
                if adj is not None
            ]
            display_for_mix = [name for name, _ in items_with_adjusted]
            final_paths = self._parallel_phase(
                config, items_with_adjusted, display_for_mix, len(items_with_adjusted),
                base_audio, mixed_dir, "混音",
                lambda cfg, item, idx, base, out_dir: self._mix_one(cfg, item, idx, base, out_dir),
            )
            if final_paths is None:
                return
        else:
            final_paths = [p for p in adjusted_paths if p is not None]

        # Filter out None results from failed items
        final_paths = [p for p in final_paths if p is not None]

        if self._emit_cancelled_if_needed():
            return

        # Phase 4: Mux to MKV (optional)
        output_paths = combat_audio.resolve_output_path(config, audio_count=len(final_paths))
        if config.boxed and not is_audio:
            out_dir = os.path.dirname(output_paths[0])
            os.makedirs(out_dir, exist_ok=True)
            self.progress.emit(total, total, f"[{total}/{total}] — 封装MKV")
            cmd = combat_audio.build_mux_command(
                config.input_path, final_paths, output_paths[0],
            )
            if not self._exec_ffmpeg(cmd):
                if self._cancel_event.is_set():
                    self.error.emit("已取消")
                    return
                self.error.emit("MKV 封装失败")
                return
            self.finished.emit(output_paths[0])
        else:
            # Copy final audio files to output locations
            out_dir = config.output_dir or os.path.dirname(config.input_path)
            os.makedirs(out_dir, exist_ok=True)
            for i, src in enumerate(final_paths):
                if i < len(output_paths):
                    shutil.copy2(src, output_paths[i])
            self.finished.emit(out_dir)

    def _parallel_phase(self, config, items, display_names, total, extra_arg, out_dir, phase_name, func):
        """Run a phase in parallel using ThreadPoolExecutor.
        items: actual work items (str or tuple)
        display_names: list of filenames for progress display (same length as items)
        Returns list of output paths or None on cancel."""
        results = [None] * len(items)
        completed = 0

        def do_one(idx, item):
            return idx, func(config, item, idx, extra_arg, out_dir)

        with ThreadPoolExecutor(max_workers=config.thread_count) as pool:
            futures = {pool.submit(do_one, i, item): i for i, item in enumerate(items)}
            for future in as_completed(futures):
                if self._cancel_event.is_set():
                    pool.shutdown(wait=False, cancel_futures=True)
                    self.error.emit("已取消")
                    return None
                try:
                    idx, path = future.result()
                except Exception:
                    completed += 1
                    continue
                results[idx] = path
                completed += 1
                self.progress.emit(
                    completed, total,
                    f"[{completed}/{total}] {display_names[idx]} — {phase_name}",
                )
        return results

    def _adjust_one(self, config, filename, idx, base_duration, out_dir):
        """Adjust one background audio to match base duration."""
        audio_path = os.path.join(config.audio_dir, filename)
        bg_duration = combat_audio.probe_duration(audio_path)
        output_path = os.path.join(out_dir, f"adjusted_{idx:02d}.aac")
        cmd = combat_audio.build_duration_adjust_command(
            audio_path, base_duration, bg_duration, output_path,
        )
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"时长调整失败: {filename}")
        return output_path

    def _mix_one(self, config, item, idx, base_audio, out_dir):
        """Mix one adjusted audio with base audio."""
        filename, adjusted_path = item
        output_path = os.path.join(out_dir, f"mixed_{idx:02d}.aac")
        cmd = combat_audio.build_mix_command(
            base_audio, adjusted_path, config.volume, output_path,
        )
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"混音失败: {filename}")
        return output_path
