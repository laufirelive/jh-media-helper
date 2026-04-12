import os
import re
import shutil
import subprocess
import tempfile
import threading
from collections import deque
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import QThread, pyqtSignal

from src.core.config import CombatAudioConfig, OutputFormat, PicSeqConfig, TaskType
from src.core.data_dir import get_temp_root_dir
from src.core.encoder_registry import EncoderRegistry
from src.core.processors import combat_audio, pic_seq

_FRAME_RE = re.compile(r"frame=\s*(\d+)")
_OUT_TIME_RE = re.compile(r"out_time_(?:us|ms)=(\d+)")


def parse_progress(line: str) -> int | None:
    """Extract frame number from ffmpeg stderr line."""
    m = _FRAME_RE.search(line)
    if m:
        return int(m.group(1))
    return None


def parse_time_progress_seconds(line: str) -> float | None:
    """Extract ffmpeg machine-readable out_time progress in seconds."""
    m = _OUT_TIME_RE.search(line)
    if not m:
        return None
    # FFmpeg reports these values in microseconds for progress output.
    return int(m.group(1)) / 1_000_000.0


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
        self._last_ffmpeg_error_detail: str | None = None
        self._parallel_phase_failures: list[tuple[str, str]] = []

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

    @staticmethod
    def _is_progress_noise_line(line: str) -> bool:
        prefixes = (
            "frame=",
            "fps=",
            "size=",
            "bitrate=",
            "total_size=",
            "out_time_",
            "out_time=",
            "dup_frames=",
            "drop_frames=",
            "speed=",
            "progress=",
        )
        return line.startswith(prefixes)

    @staticmethod
    def _compose_error_message(summary: str, detail: str | None = None) -> str:
        detail = (detail or "").strip()
        if not detail:
            return summary
        return f"{summary}\n\n{detail}"

    @staticmethod
    def split_error_message(message: str | None) -> tuple[str, str]:
        if not message:
            return "", ""
        summary, _, details = message.partition("\n\n")
        return summary.strip(), details.strip()

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

    def _with_progress_args(self, cmd: list[str]) -> list[str]:
        if not cmd or cmd[0] != "ffmpeg":
            return cmd
        if "-progress" in cmd:
            return cmd
        return [cmd[0], "-progress", "pipe:2", "-nostats", *cmd[1:]]

    def _run_ffmpeg_process(
        self,
        cmd: list[str],
        *,
        progress_total: float | None = None,
        progress_desc: str = "处理中",
        progress_callback=None,
        track_main_process: bool = True,
    ) -> bool:
        effective_cmd = self._with_progress_args(cmd)
        error_tail: deque[str] = deque(maxlen=8)
        process = subprocess.Popen(
            effective_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if track_main_process:
            self._process = process

        last_time_pct = -1
        try:
            for raw_line in process.stderr:
                if self._cancel_event.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=1.0)
                    return False
                decoded = raw_line.decode("utf-8", errors="replace")
                for chunk in re.split(r"[\r\n]+", decoded):
                    line = chunk.strip()
                    if not line:
                        continue
                    if not self._is_progress_noise_line(line):
                        error_tail.append(line)
                    frame = parse_progress(line)
                    if frame is not None and track_main_process:
                        self.progress.emit(frame, self._total_frames, "编码中")
                    if progress_total and progress_total > 0:
                        seconds = parse_time_progress_seconds(line)
                        if seconds is None:
                            continue
                        pct = max(0, min(99, int(seconds / progress_total * 100)))
                        if pct > last_time_pct:
                            last_time_pct = pct
                            if progress_callback is not None:
                                progress_callback(pct)
                            else:
                                self.progress.emit(pct, 100, progress_desc)
            process.wait()
            detail = "\n".join(error_tail).strip()
            if track_main_process:
                self._last_ffmpeg_error_detail = detail or None
            return process.returncode == 0
        finally:
            if track_main_process and self._process is process:
                self._process = None

    def _exec_ffmpeg(
        self,
        cmd: list[str],
        *,
        progress_total: float | None = None,
        progress_desc: str = "处理中",
    ) -> bool:
        # 启动子进程前再检查，避免已取消仍去 Popen
        if self._cancel_event.is_set():
            return False
        return self._run_ffmpeg_process(
            cmd,
            progress_total=progress_total,
            progress_desc=progress_desc,
            track_main_process=True,
        )

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

        temp_root = get_temp_root_dir()
        os.makedirs(temp_root, exist_ok=True)
        tmp_dir = tempfile.mkdtemp(prefix="jh_combat_", dir=temp_root)
        try:
            self._combat_audio_pipeline(config, is_audio, audio_files, total, tmp_dir)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _combat_audio_pipeline(self, config, is_audio, audio_files, total, tmp_dir):
        # 检测输入是否含音轨；纯音频输入视为有「原音」可参与混音
        streams = [] if is_audio else combat_audio.probe_audio_streams(config.input_path)
        has_audio_streams = is_audio or bool(streams)
        base_duration = combat_audio.probe_duration(config.input_path)
        if base_duration <= 0:
            self.error.emit("无法获取输入时长")
            return
        # 无音轨视频无法与原片混音，等价于关闭混音（避免 base_audio 为空仍走混音阶段）
        mix_effective = config.mix_enabled and has_audio_streams
        # 无视频原音时背景音乐只裁到不超过片长，不循环拉长
        loop_short_bgm = has_audio_streams
        phase_labels: list[str] = []
        if mix_effective:
            phase_labels.append("提取音频")
        phase_labels.append("调整时长")
        if mix_effective:
            phase_labels.append("混音")
        if config.boxed and not is_audio:
            phase_labels.append("封装MKV")
        phase_total = max(len(phase_labels), 1)
        phase_idx = 0

        def phase_desc(index: int, label: str, filename: str | None = None) -> str:
            desc = f"[{index}/{phase_total}] {label}"
            if filename:
                return f"{desc} — {filename}"
            return desc

        # Phase 1: Extract base audio (only when mixing is needed)
        base_audio = None
        if mix_effective:
            phase_idx += 1
            self.progress.emit(0, 100, phase_desc(phase_idx, "提取音频"))
            if self._emit_cancelled_if_needed():
                return
            if is_audio:
                base_audio = config.input_path
            elif has_audio_streams:
                base_audio = os.path.join(tmp_dir, "extracted.m4a")
                cmd = combat_audio.build_extract_command(
                    config.input_path, config.audio_stream_index, base_audio,
                )
                if not self._exec_ffmpeg(
                    cmd,
                    progress_total=base_duration,
                    progress_desc=phase_desc(phase_idx, "提取音频"),
                ):
                    if self._cancel_event.is_set():
                        self.error.emit("已取消")
                        return
                    self.error.emit(self._compose_error_message("音频提取失败", self._last_ffmpeg_error_detail))
                    return
            self.progress.emit(100, 100, phase_desc(phase_idx, "提取音频"))

        if self._emit_cancelled_if_needed():
            return

        # Phase 2: Adjust duration (parallel)
        phase_idx += 1
        adjusted_dir = os.path.join(tmp_dir, "adjusted")
        os.makedirs(adjusted_dir)
        adjusted_paths = self._parallel_phase(
            config,
            audio_files,
            audio_files,
            phase_idx,
            phase_total,
            (base_duration, loop_short_bgm),
            adjusted_dir,
            "调整时长",
            self._adjust_one,
        )
        if adjusted_paths is None:
            return

        # Phase 3: Mix (parallel, only if mix_effective)
        if mix_effective:
            phase_idx += 1
            mixed_dir = os.path.join(tmp_dir, "mixed")
            os.makedirs(mixed_dir)
            items_with_adjusted = [
                (name, adj) for name, adj in zip(audio_files, adjusted_paths)
                if adj is not None
            ]
            display_for_mix = [name for name, _ in items_with_adjusted]
            final_paths = self._parallel_phase(
                config, items_with_adjusted, display_for_mix, phase_idx, phase_total,
                (base_audio, base_duration), mixed_dir, "混音",
                lambda cfg, item, idx, mix_input, out_dir, progress_cb=None: self._mix_one(
                    cfg, item, idx, mix_input, out_dir, progress_cb=progress_cb
                ),
            )
            if final_paths is None:
                return
        else:
            final_paths = [p for p in adjusted_paths if p is not None]

        # Filter out None results from failed items
        final_paths = [p for p in final_paths if p is not None]
        if not final_paths:
            if self._parallel_phase_failures:
                detail_lines = [
                    f"{name}: {reason}" for name, reason in self._parallel_phase_failures[:5]
                ]
                if len(self._parallel_phase_failures) > 5:
                    detail_lines.append(f"... 共 {len(self._parallel_phase_failures)} 个失败项")
                self.error.emit(
                    self._compose_error_message(
                        "未生成任何输出音频",
                        "\n".join(detail_lines),
                    )
                )
            else:
                self.error.emit("未生成任何输出音频")
            return

        if self._emit_cancelled_if_needed():
            return

        # Phase 4: Mux to MKV (optional)；输出文件名后缀与是否实际混音一致
        output_paths = combat_audio.resolve_output_path(
            replace(config, mix_enabled=mix_effective), audio_count=len(final_paths)
        )
        if config.boxed and not is_audio:
            phase_idx += 1
            out_dir = os.path.dirname(output_paths[0])
            os.makedirs(out_dir, exist_ok=True)
            self.progress.emit(0, 100, phase_desc(phase_idx, "封装MKV"))
            cmd = combat_audio.build_mux_command(
                config.input_path, final_paths, output_paths[0],
                keep_original_audio=has_audio_streams,
            )
            if not self._exec_ffmpeg(
                cmd,
                progress_total=base_duration,
                progress_desc=phase_desc(phase_idx, "封装MKV"),
            ):
                if self._cancel_event.is_set():
                    self.error.emit("已取消")
                    return
                self.error.emit(self._compose_error_message("MKV 封装失败", self._last_ffmpeg_error_detail))
                return
            self.progress.emit(100, 100, phase_desc(phase_idx, "封装MKV"))
            self.finished.emit(output_paths[0])
        else:
            # Export final audio files to user-facing AAC outputs.
            out_dir = config.output_dir or os.path.dirname(config.input_path)
            os.makedirs(out_dir, exist_ok=True)
            for i, src in enumerate(final_paths):
                if i < len(output_paths):
                    cmd = combat_audio.build_export_aac_command(src, output_paths[i])
                    if not self._exec_ffmpeg(cmd):
                        if self._cancel_event.is_set():
                            self.error.emit("已取消")
                            return
                        self.error.emit(self._compose_error_message("导出最终音频失败", self._last_ffmpeg_error_detail))
                        return
            self.finished.emit(out_dir)

    def _parallel_phase(self, config, items, display_names, phase_index, phase_total, extra_arg, out_dir, phase_name, func):
        """Run a phase in parallel using ThreadPoolExecutor.
        items: actual work items (str or tuple)
        display_names: list of filenames for progress display (same length as items)
        Returns list of output paths or None on cancel."""
        results = [None] * len(items)
        failures: list[tuple[str, str]] = []
        completed = 0
        item_total = max(len(items), 1)
        item_progress = [0] * len(items)
        progress_lock = threading.Lock()
        last_emitted_pct = -1

        self.progress.emit(0, 100, f"[{phase_index}/{phase_total}] {phase_name}")

        def update_item_progress(idx: int, pct: int) -> None:
            nonlocal last_emitted_pct
            with progress_lock:
                item_progress[idx] = max(item_progress[idx], pct)
                aggregate_pct = int(sum(item_progress) / item_total)
                if aggregate_pct > last_emitted_pct:
                    last_emitted_pct = aggregate_pct
                    self.progress.emit(aggregate_pct, 100, f"[{phase_index}/{phase_total}] {phase_name}")

        def do_one(idx, item):
            return idx, func(
                config,
                item,
                idx,
                extra_arg,
                out_dir,
                progress_cb=lambda pct: update_item_progress(idx, pct),
            )

        with ThreadPoolExecutor(max_workers=config.thread_count) as pool:
            futures = {pool.submit(do_one, i, item): i for i, item in enumerate(items)}
            for future in as_completed(futures):
                if self._cancel_event.is_set():
                    pool.shutdown(wait=False, cancel_futures=True)
                    self.error.emit("已取消")
                    self._parallel_phase_failures = failures
                    return None
                try:
                    idx, path = future.result()
                except Exception as exc:
                    idx = futures[future]
                    display_name = display_names[idx] if idx < len(display_names) else f"item_{idx}"
                    detail = str(exc).strip() or exc.__class__.__name__
                    failures.append((display_name, detail))
                    completed += 1
                    continue
                update_item_progress(idx, 100)
                results[idx] = path
                completed += 1
                pct = int(completed / item_total * 100)
                self.progress.emit(
                    pct, 100,
                    f"[{phase_index}/{phase_total}] {phase_name} - {display_names[idx]}",
                )
        self._parallel_phase_failures = failures
        return results

    def _adjust_one(self, config, filename, idx, duration_and_loop, out_dir, progress_cb=None):
        """将单条背景音乐对齐基准时长（可禁止循环以适配无原音视频）。"""
        base_duration, loop_short_audio = duration_and_loop
        audio_path = os.path.join(config.audio_dir, filename)
        bg_duration = combat_audio.probe_duration(audio_path)
        output_path = os.path.join(out_dir, f"adjusted_{idx:02d}.m4a")
        cmd = combat_audio.build_duration_adjust_command(
            audio_path,
            base_duration,
            bg_duration,
            output_path,
            loop_short_audio=loop_short_audio,
        )
        output_duration = base_duration if (bg_duration >= base_duration or loop_short_audio) else bg_duration
        if not self._run_ffmpeg_process(
            cmd,
            progress_total=output_duration,
            progress_callback=progress_cb,
            track_main_process=False,
        ):
            raise RuntimeError(f"时长调整失败: {filename}")
        return output_path

    def _mix_one(self, config, item, idx, mix_input, out_dir, progress_cb=None):
        """Mix one adjusted audio with base audio."""
        filename, adjusted_path = item
        base_audio, base_duration = mix_input
        output_path = os.path.join(out_dir, f"mixed_{idx:02d}.m4a")
        cmd = combat_audio.build_mix_command(
            base_audio, adjusted_path, config.volume, output_path,
        )
        if not self._run_ffmpeg_process(
            cmd,
            progress_total=base_duration,
            progress_callback=progress_cb,
            track_main_process=False,
        ):
            raise RuntimeError(f"混音失败: {filename}")
        return output_path
