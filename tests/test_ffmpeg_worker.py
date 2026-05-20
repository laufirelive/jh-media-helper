import subprocess
import tempfile

from src.core.config import CombatAudioConfig, TaskType
from src.core.external_tools import MuxBackend
from src.worker.ffmpeg_worker import (
    FFmpegWorker,
    parse_mkvmerge_progress_percent,
    parse_progress,
    parse_time_progress_seconds,
)


class TestParseProgress:
    def test_parse_frame_number(self):
        line = "frame=  810 fps=120 q=28.0 size=   25600kB time=00:00:06.75"
        assert parse_progress(line) == 810

    def test_parse_frame_no_spaces(self):
        line = "frame=1247 fps=95.2 q=31.0 Lsize=  102400kB time=00:00:10.39"
        assert parse_progress(line) == 1247

    def test_no_frame_returns_none(self):
        line = "Press [q] to stop, [?] for help"
        assert parse_progress(line) is None

    def test_empty_line(self):
        assert parse_progress("") is None


class TestParseTimeProgressSeconds:
    def test_parse_out_time_ms_as_seconds(self):
        assert parse_time_progress_seconds("out_time_ms=5000000") == 5.0

    def test_parse_out_time_us_as_seconds(self):
        assert parse_time_progress_seconds("out_time_us=2500000") == 2.5

    def test_ignore_non_progress_line(self):
        assert parse_time_progress_seconds("speed=1.25x") is None


class TestParseMkvmergeProgressPercent:
    def test_parse_progress_percent(self):
        assert parse_mkvmerge_progress_percent("Progress: 42%") == 42

    def test_ignore_non_progress_line(self):
        assert parse_mkvmerge_progress_percent("Multiplexing took 10 seconds.") is None


class TestErrorMessageFormatting:
    def test_split_error_message_returns_summary_and_details(self):
        summary, details = FFmpegWorker.split_error_message("混音失败：bgm.mp3\n\nline1\nline2")
        assert summary == "混音失败：bgm.mp3"
        assert details == "line1\nline2"


class _FakeProcess:
    def __init__(self, raise_timeout: bool, stderr_lines=None, stdout_lines=None, returncode: int = 0):
        self.raise_timeout = raise_timeout
        self.terminated = 0
        self.killed = 0
        self._polled = None
        self.stderr = iter(stderr_lines or [])
        self.stdout = iter(stdout_lines or [])
        self.returncode = returncode

    def poll(self):
        return self._polled

    def terminate(self):
        self.terminated += 1

    def wait(self, timeout=None):
        if self.raise_timeout and timeout is not None and self.killed == 0:
            raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=timeout)
        self._polled = self.returncode
        return self.returncode

    def kill(self):
        self.killed += 1
        self._polled = -9


class TestWorkerCancel:
    def test_cancel_terminates_process(self):
        worker = FFmpegWorker(TaskType.PIC_SEQ, {}, encoder_registry=None)
        fake = _FakeProcess(raise_timeout=False)
        worker._process = fake
        worker.cancel()
        assert fake.terminated == 1
        assert fake.killed == 0

    def test_cancel_kills_process_when_terminate_timeout(self):
        worker = FFmpegWorker(TaskType.PIC_SEQ, {}, encoder_registry=None)
        fake = _FakeProcess(raise_timeout=True)
        worker._process = fake
        worker.cancel()
        assert fake.terminated == 1
        assert fake.killed == 1


class TestWorkerProgress:
    def test_exec_ffmpeg_adds_machine_readable_progress_flags(self, monkeypatch):
        calls = {}

        def fake_popen(cmd, stdout=None, stderr=None):
            calls["cmd"] = cmd
            return _FakeProcess(raise_timeout=False)

        monkeypatch.setattr("src.worker.ffmpeg_worker.subprocess.Popen", fake_popen)

        worker = FFmpegWorker(TaskType.PIC_SEQ, {}, encoder_registry=None)
        assert worker._exec_ffmpeg(["ffmpeg", "-y", "-i", "in.mp4", "out.mp4"]) is True

        assert calls["cmd"][:6] == [
            "ffmpeg",
            "-progress",
            "pipe:2",
            "-nostats",
            "-y",
            "-i",
        ]

    def test_exec_ffmpeg_emits_time_based_progress(self, monkeypatch):
        fake = _FakeProcess(
            raise_timeout=False,
            stderr_lines=[
                b"out_time_ms=5000000\n",
                b"progress=continue\n",
            ],
        )

        monkeypatch.setattr(
            "src.worker.ffmpeg_worker.subprocess.Popen",
            lambda *args, **kwargs: fake,
        )

        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
        progress_events = []
        worker.progress.connect(lambda current, total, desc: progress_events.append((current, total, desc)))

        assert worker._exec_ffmpeg(
            ["ffmpeg", "-y", "-i", "in.mp4", "out.aac"],
            progress_total=10.0,
            progress_desc="提取音频",
        ) is True

        assert (50, 100, "提取音频") in progress_events

    def test_exec_ffmpeg_caps_time_based_progress_at_99_before_exit(self, monkeypatch):
        fake = _FakeProcess(
            raise_timeout=False,
            stderr_lines=[
                b"out_time_ms=10000000\n",
                b"progress=continue\n",
            ],
        )

        monkeypatch.setattr(
            "src.worker.ffmpeg_worker.subprocess.Popen",
            lambda *args, **kwargs: fake,
        )

        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
        progress_events = []
        worker.progress.connect(lambda current, total, desc: progress_events.append((current, total, desc)))

        assert worker._exec_ffmpeg(
            ["ffmpeg", "-y", "-i", "in.mp4", "out.aac"],
            progress_total=10.0,
            progress_desc="提取音频",
        ) is True

        assert (99, 100, "提取音频") in progress_events
        assert (100, 100, "提取音频") not in progress_events

    def test_exec_ffmpeg_accepts_custom_success_returncodes(self, monkeypatch):
        fake = _FakeProcess(raise_timeout=False, returncode=1)

        monkeypatch.setattr(
            "src.worker.ffmpeg_worker.subprocess.Popen",
            lambda *args, **kwargs: fake,
        )

        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)

        assert worker._exec_ffmpeg(["mkvmerge", "-o", "out.mkv", "in.mkv"], success_returncodes=(0, 1)) is True

    def test_exec_non_ffmpeg_non_mkvmerge_does_not_pipe_unread_stdout(self, monkeypatch):
        calls = {}

        def fake_popen(cmd, stdout=None, stderr=None):
            calls["stdout"] = stdout
            calls["stderr"] = stderr
            return _FakeProcess(raise_timeout=False)

        monkeypatch.setattr("src.worker.ffmpeg_worker.subprocess.Popen", fake_popen)

        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)

        assert worker._exec_ffmpeg(["other-tool", "-o", "out.mkv", "in.mkv"]) is True
        assert calls["stdout"] is not subprocess.PIPE
        assert calls["stderr"] is subprocess.PIPE

    def test_exec_mkvmerge_emits_stdout_progress(self, monkeypatch):
        fake = _FakeProcess(
            raise_timeout=False,
            stdout_lines=[
                b"Progress: 12%\n",
                b"Progress: 87%\n",
            ],
        )
        calls = {}

        def fake_popen(cmd, stdout=None, stderr=None):
            calls["stdout"] = stdout
            calls["stderr"] = stderr
            return fake

        monkeypatch.setattr("src.worker.ffmpeg_worker.subprocess.Popen", fake_popen)

        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
        progress_events = []
        worker.progress.connect(lambda current, total, desc: progress_events.append((current, total, desc)))

        assert worker._exec_ffmpeg(
            ["mkvmerge", "-o", "out.mkv", "in.mkv"],
            progress_desc="封装MKV",
        ) is True
        assert calls["stdout"] is subprocess.PIPE
        assert calls["stderr"] is subprocess.STDOUT
        assert progress_events == [
            (12, 100, "封装MKV"),
            (87, 100, "封装MKV"),
        ]

    def test_exec_ffmpeg_keeps_default_success_as_returncode_zero_only(self, monkeypatch):
        fake = _FakeProcess(raise_timeout=False, returncode=1)

        monkeypatch.setattr(
            "src.worker.ffmpeg_worker.subprocess.Popen",
            lambda *args, **kwargs: fake,
        )

        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)

        assert worker._exec_ffmpeg(["ffmpeg", "-y", "-i", "in.mp4", "out.mkv"]) is False

    def test_parallel_phase_emits_intermediate_aggregated_progress(self):
        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
        progress_events = []
        worker.progress.connect(lambda current, total, desc: progress_events.append((current, total, desc)))

        def fake_func(config, item, idx, extra, out_dir, progress_cb=None):
            if progress_cb is not None:
                progress_cb(50)
            return f"/tmp/{item}.aac"

        result = worker._parallel_phase(
            config=type("Cfg", (), {"thread_count": 2})(),
            items=["a", "b"],
            display_names=["a", "b"],
            phase_index=2,
            phase_total=4,
            extra_arg=None,
            out_dir=tempfile.gettempdir(),
            phase_name="混音",
            func=fake_func,
        )

        assert result == ["/tmp/a.aac", "/tmp/b.aac"]
        assert any(
            total == 100 and desc == "[2/4] 混音" and 0 < current < 100
            for current, total, desc in progress_events
        )

    def test_run_combat_audio_creates_temp_dir_under_data_dir(self, monkeypatch):
        created = {}
        real_mkdtemp = tempfile.mkdtemp

        def fake_mkdtemp(*, prefix, dir=None):
            created["prefix"] = prefix
            created["dir"] = dir
            return real_mkdtemp(prefix=prefix)

        monkeypatch.setattr("src.worker.ffmpeg_worker.tempfile.mkdtemp", fake_mkdtemp)
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.is_pure_audio", lambda path: True)
        monkeypatch.setattr(
            "src.worker.ffmpeg_worker.combat_audio.scan_audio_dir",
            lambda path: [type("Audio", (), {"filename": "bg.aac"})()],
        )
        monkeypatch.setattr(
            FFmpegWorker,
            "_combat_audio_pipeline",
            lambda self, config, is_audio, audio_files, total, tmp_dir: None,
        )

        worker = FFmpegWorker(
            TaskType.COMBAT_AUDIO,
            {"input_path": "/tmp/in.aac", "audio_dir": "/tmp/audio"},
            encoder_registry=None,
        )
        worker._run_combat_audio()

        assert created["prefix"] == "jh_combat_"
        assert created["dir"].endswith(".jh-media-helper/tmp")

    def test_combat_audio_pipeline_passes_duration_progress_to_mux(self, monkeypatch):
        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
        exec_calls = []

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_audio_streams", lambda path: [object()])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_duration", lambda path: 20.0)
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_extract_command", lambda *args, **kwargs: ["ffmpeg"])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_mux_command", lambda *args, **kwargs: ["ffmpeg"])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.resolve_output_path", lambda *args, **kwargs: ["/tmp/out.mkv"])
        monkeypatch.setattr(
            FFmpegWorker,
            "_parallel_phase",
            lambda self, *args, **kwargs: ["/tmp/mixed_00.m4a"],
        )

        def fake_exec(self, cmd, *, progress_total=None, progress_desc="处理中", success_returncodes=(0,)):
            exec_calls.append((cmd, progress_total, progress_desc, success_returncodes))
            return True

        monkeypatch.setattr(FFmpegWorker, "_exec_ffmpeg", fake_exec)

        config = CombatAudioConfig(
            input_path="/tmp/in.mkv",
            audio_dir="/tmp/audio",
            output_dir="/tmp",
            mix_enabled=True,
            boxed=True,
            audio_stream_index=0,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            worker._combat_audio_pipeline(config, False, ["bg.aac"], 1, tmp_dir)

        assert exec_calls[1][1] == 20.0
        assert exec_calls[1][2] == "[4/4] 封装MKV part 1/1 — in.mkv"

    def test_combat_audio_pipeline_muxes_main_and_secondary_videos_with_mkvmerge(self, monkeypatch):
        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
        exec_calls = []
        mkvmerge_calls = []
        probe_calls = []
        finished = []
        worker.finished.connect(finished.append)

        def fake_probe_audio_streams(path):
            probe_calls.append(path)
            return [] if path.endswith("part2.mkv") else [object()]

        def fake_build_mkvmerge(
            mkvmerge_path,
            video_path,
            final_paths,
            output_path,
            *,
            keep_original_audio=True,
            subtitle_path=None,
        ):
            mkvmerge_calls.append((mkvmerge_path, video_path, list(final_paths), output_path, keep_original_audio))
            return ["mkvmerge", video_path, output_path]

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_audio_streams", fake_probe_audio_streams)
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_duration", lambda path: 20.0)
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_extract_command", lambda *args, **kwargs: ["ffmpeg", "extract"])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_mkvmerge_mux_command", fake_build_mkvmerge)
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.resolve_output_path", lambda *args, **kwargs: [
            "/tmp/out/in-part1.mkv",
            "/tmp/out/in-part2.mkv",
            "/tmp/out/in-part3.mkv",
        ])
        monkeypatch.setattr(
            "src.worker.ffmpeg_worker.resolve_mux_backend",
            lambda requested, mkvmerge_path: (MuxBackend.MKVMERGE, "/usr/bin/mkvmerge"),
        )
        monkeypatch.setattr(
            FFmpegWorker,
            "_parallel_phase",
            lambda self, *args, **kwargs: ["/tmp/mixed_00.m4a", "/tmp/mixed_01.m4a"],
        )

        def fake_exec(self, cmd, *, progress_total=None, progress_desc="处理中", success_returncodes=(0,)):
            exec_calls.append((cmd, progress_total, progress_desc, success_returncodes))
            return True

        monkeypatch.setattr(FFmpegWorker, "_exec_ffmpeg", fake_exec)

        config = CombatAudioConfig(
            input_path="/tmp/in.mkv",
            audio_dir="/tmp/audio",
            output_dir="/tmp/out",
            mix_enabled=True,
            boxed=True,
            secondary_video_paths=["/tmp/part2.mkv", "/tmp/part3.mkv"],
            audio_stream_index=0,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            worker._combat_audio_pipeline(config, False, ["bg1.aac", "bg2.aac"], 2, tmp_dir)

        final_paths = ["/tmp/mixed_00.m4a", "/tmp/mixed_01.m4a"]
        assert exec_calls == [
            (["ffmpeg", "extract"], 20.0, "[1/4] 提取音频", (0,)),
            (["mkvmerge", "/tmp/in.mkv", "/tmp/out/in-part1.mkv"], 20.0, "[4/4] 封装MKV part 1/3 — in.mkv", (0, 1)),
            (["mkvmerge", "/tmp/part2.mkv", "/tmp/out/in-part2.mkv"], 20.0, "[4/4] 封装MKV part 2/3 — part2.mkv", (0, 1)),
            (["mkvmerge", "/tmp/part3.mkv", "/tmp/out/in-part3.mkv"], 20.0, "[4/4] 封装MKV part 3/3 — part3.mkv", (0, 1)),
        ]
        assert mkvmerge_calls == [
            ("/usr/bin/mkvmerge", "/tmp/in.mkv", final_paths, "/tmp/out/in-part1.mkv", True),
            ("/usr/bin/mkvmerge", "/tmp/part2.mkv", final_paths, "/tmp/out/in-part2.mkv", False),
            ("/usr/bin/mkvmerge", "/tmp/part3.mkv", final_paths, "/tmp/out/in-part3.mkv", True),
        ]
        assert probe_calls == ["/tmp/in.mkv", "/tmp/in.mkv", "/tmp/part2.mkv", "/tmp/part3.mkv"]
        assert finished == ["/tmp/out"]

    def test_combat_audio_pipeline_errors_when_boxed_output_paths_fewer_than_videos(self, monkeypatch):
        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
        errors = []
        exec_calls = []
        mux_calls = []
        worker.error.connect(errors.append)

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_audio_streams", lambda path: [object()])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_duration", lambda path: 20.0)
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.resolve_output_path", lambda *args, **kwargs: ["/tmp/out/in-part1.mkv"])
        monkeypatch.setattr(
            FFmpegWorker,
            "_parallel_phase",
            lambda self, *args, **kwargs: ["/tmp/adjusted_00.m4a"],
        )

        def fake_build_mux(*args, **kwargs):
            mux_calls.append(args)
            return ["ffmpeg", "mux"]

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_mux_command", fake_build_mux)
        monkeypatch.setattr(FFmpegWorker, "_exec_ffmpeg", lambda self, *args, **kwargs: exec_calls.append(args) or True)

        config = CombatAudioConfig(
            input_path="/tmp/in.mkv",
            audio_dir="/tmp/audio",
            output_dir="/tmp/out",
            mix_enabled=False,
            boxed=True,
            secondary_video_paths=["/tmp/part2.mkv", "/tmp/part3.mkv"],
            audio_stream_index=0,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            worker._combat_audio_pipeline(config, False, ["bg.aac"], 1, tmp_dir)

        assert errors == ["MKV 输出数量异常：需要 3 个，实际 1 个"]
        assert mux_calls == []
        assert exec_calls == []

    def test_combat_audio_pipeline_errors_when_boxed_output_paths_empty(self, monkeypatch):
        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
        errors = []
        exec_calls = []
        mux_calls = []
        worker.error.connect(errors.append)

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_audio_streams", lambda path: [object()])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_duration", lambda path: 20.0)
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.resolve_output_path", lambda *args, **kwargs: [])
        monkeypatch.setattr(
            FFmpegWorker,
            "_parallel_phase",
            lambda self, *args, **kwargs: ["/tmp/adjusted_00.m4a"],
        )

        def fake_build_mux(*args, **kwargs):
            mux_calls.append(args)
            return ["ffmpeg", "mux"]

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_mux_command", fake_build_mux)
        monkeypatch.setattr(FFmpegWorker, "_exec_ffmpeg", lambda self, *args, **kwargs: exec_calls.append(args) or True)

        config = CombatAudioConfig(
            input_path="/tmp/in.mkv",
            audio_dir="/tmp/audio",
            output_dir="/tmp/out",
            mix_enabled=False,
            boxed=True,
            audio_stream_index=0,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            worker._combat_audio_pipeline(config, False, ["bg.aac"], 1, tmp_dir)

        assert errors == ["MKV 输出数量异常：需要 1 个，实际 0 个"]
        assert mux_calls == []
        assert exec_calls == []

    def test_combat_audio_pipeline_falls_back_to_ffmpeg_mux_backend_for_single_output(self, monkeypatch):
        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
        mux_calls = []
        finished = []
        worker.finished.connect(finished.append)

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_audio_streams", lambda path: [object()])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_duration", lambda path: 20.0)
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_extract_command", lambda *args, **kwargs: ["ffmpeg", "extract"])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.resolve_output_path", lambda *args, **kwargs: ["/tmp/out.mkv"])
        monkeypatch.setattr(
            "src.worker.ffmpeg_worker.resolve_mux_backend",
            lambda requested, mkvmerge_path: (MuxBackend.FFMPEG, None),
        )
        monkeypatch.setattr(
            FFmpegWorker,
            "_parallel_phase",
            lambda self, *args, **kwargs: ["/tmp/mixed_00.m4a"],
        )

        def fake_build_mux(video_path, final_paths, output_path, keep_original_audio=True, subtitle_path=None):
            mux_calls.append((video_path, list(final_paths), output_path, keep_original_audio))
            return ["ffmpeg", "mux"]

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_mux_command", fake_build_mux)
        monkeypatch.setattr(FFmpegWorker, "_exec_ffmpeg", lambda *args, **kwargs: True)

        config = CombatAudioConfig(
            input_path="/tmp/in.mkv",
            audio_dir="/tmp/audio",
            output_dir="/tmp",
            mix_enabled=True,
            boxed=True,
            audio_stream_index=0,
            mux_backend="ffmpeg",
            mkvmerge_path="/bad/mkvmerge",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            worker._combat_audio_pipeline(config, False, ["bg.aac"], 1, tmp_dir)

        assert mux_calls == [("/tmp/in.mkv", ["/tmp/mixed_00.m4a"], "/tmp/out.mkv", True)]
        assert finished == ["/tmp/out.mkv"]

    def test_combat_audio_pipeline_passes_subtitle_to_ffmpeg_mux(self, monkeypatch):
        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
        mux_calls = []

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_audio_streams", lambda path: [object()])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_duration", lambda path: 20.0)
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_extract_command", lambda *args, **kwargs: ["ffmpeg", "extract"])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.resolve_output_path", lambda *args, **kwargs: ["/tmp/out.mkv"])
        monkeypatch.setattr(
            "src.worker.ffmpeg_worker.resolve_mux_backend",
            lambda requested, mkvmerge_path: (MuxBackend.FFMPEG, None),
        )
        monkeypatch.setattr(
            FFmpegWorker,
            "_parallel_phase",
            lambda self, *args, **kwargs: ["/tmp/mixed_00.m4a"],
        )

        def fake_build_mux(video_path, final_paths, output_path, keep_original_audio=True, subtitle_path=None):
            mux_calls.append((video_path, list(final_paths), output_path, keep_original_audio, subtitle_path))
            return ["ffmpeg", "mux"]

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_mux_command", fake_build_mux)
        monkeypatch.setattr(FFmpegWorker, "_exec_ffmpeg", lambda *args, **kwargs: True)

        config = CombatAudioConfig(
            input_path="/tmp/in.mkv",
            audio_dir="/tmp/audio",
            output_dir="/tmp",
            mix_enabled=True,
            boxed=True,
            audio_stream_index=0,
            subtitle_path="/tmp/caption.srt",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            worker._combat_audio_pipeline(config, False, ["bg.aac"], 1, tmp_dir)

        assert mux_calls == [
            ("/tmp/in.mkv", ["/tmp/mixed_00.m4a"], "/tmp/out.mkv", True, "/tmp/caption.srt")
        ]

    def test_combat_audio_pipeline_passes_subtitle_to_mkvmerge_for_each_part(self, monkeypatch):
        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
        mkvmerge_calls = []

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_audio_streams", lambda path: [object()])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_duration", lambda path: 20.0)
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_extract_command", lambda *args, **kwargs: ["ffmpeg", "extract"])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.resolve_output_path", lambda *args, **kwargs: [
            "/tmp/out/in-part1.mkv",
            "/tmp/out/in-part2.mkv",
        ])
        monkeypatch.setattr(
            "src.worker.ffmpeg_worker.resolve_mux_backend",
            lambda requested, mkvmerge_path: (MuxBackend.MKVMERGE, "/usr/bin/mkvmerge"),
        )
        monkeypatch.setattr(
            FFmpegWorker,
            "_parallel_phase",
            lambda self, *args, **kwargs: ["/tmp/mixed_00.m4a"],
        )

        def fake_build_mkvmerge(
            mkvmerge_path,
            video_path,
            final_paths,
            output_path,
            *,
            keep_original_audio=True,
            subtitle_path=None,
        ):
            mkvmerge_calls.append((video_path, output_path, subtitle_path))
            return ["mkvmerge", video_path, output_path]

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_mkvmerge_mux_command", fake_build_mkvmerge)
        monkeypatch.setattr(FFmpegWorker, "_exec_ffmpeg", lambda *args, **kwargs: True)

        config = CombatAudioConfig(
            input_path="/tmp/in.mkv",
            audio_dir="/tmp/audio",
            output_dir="/tmp/out",
            mix_enabled=True,
            boxed=True,
            secondary_video_paths=["/tmp/part2.mkv"],
            audio_stream_index=0,
            subtitle_path="/tmp/caption.ass",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            worker._combat_audio_pipeline(config, False, ["bg.aac"], 1, tmp_dir)

        assert mkvmerge_calls == [
            ("/tmp/in.mkv", "/tmp/out/in-part1.mkv", "/tmp/caption.ass"),
            ("/tmp/part2.mkv", "/tmp/out/in-part2.mkv", "/tmp/caption.ass"),
        ]

    def test_mix_phase_uses_original_input_duration_instead_of_probe_from_temp_aac(self, monkeypatch):
        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
        run_calls = []

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_mix_command", lambda *args, **kwargs: ["ffmpeg"])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_duration", lambda path: 1440.0)

        def fake_run_ffmpeg_process(self, cmd, *, progress_total=None, progress_desc="处理中", progress_callback=None, track_main_process=True):
            run_calls.append(progress_total)
            if progress_callback is not None:
                progress_callback(50)
            return True

        monkeypatch.setattr(FFmpegWorker, "_run_ffmpeg_process", fake_run_ffmpeg_process)

        output = worker._mix_one(
            config=type("Cfg", (), {"volume": 0.6})(),
            item=("bg.aac", "/tmp/adjusted.aac"),
            idx=0,
            mix_input=("/tmp/extracted.aac", 3600.0),
            out_dir="/tmp",
        )

        assert output == "/tmp/mixed_00.m4a"
        assert run_calls == [3600.0]

    def test_combat_audio_pipeline_errors_when_non_boxed_output_is_empty(self, monkeypatch):
        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
        errors = []
        finished = []
        worker.error.connect(errors.append)
        worker.finished.connect(finished.append)

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_audio_streams", lambda path: [object()])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_duration", lambda path: 20.0)
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_extract_command", lambda *args, **kwargs: ["ffmpeg"])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.resolve_output_path", lambda *args, **kwargs: [])
        monkeypatch.setattr(FFmpegWorker, "_exec_ffmpeg", lambda *args, **kwargs: True)
        monkeypatch.setattr(
            FFmpegWorker,
            "_parallel_phase",
            lambda self, config, items, *args, **kwargs: [None] * len(items),
        )

        config = CombatAudioConfig(
            input_path="/tmp/in.mkv",
            audio_dir="/tmp/audio",
            output_dir="/tmp",
            mix_enabled=True,
            boxed=False,
            audio_stream_index=0,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            worker._combat_audio_pipeline(config, False, ["bg.aac"], 1, tmp_dir)

        assert errors == ["未生成任何输出音频"]
        assert finished == []

    def test_combat_audio_pipeline_uses_audio_filenames_for_non_boxed_exports(self, monkeypatch):
        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
        resolve_calls = []
        export_calls = []

        audio_files = ["z_theme.aac", "a_theme.aac"]
        final_paths = ["/tmp/final_z.m4a", "/tmp/final_a.m4a"]
        output_paths = ["/tmp/out/01_z_theme_aligned.aac", "/tmp/out/02_a_theme_aligned.aac"]

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_audio_streams", lambda path: [])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_duration", lambda path: 20.0)
        monkeypatch.setattr(
            FFmpegWorker,
            "_parallel_phase",
            lambda self, *args, **kwargs: list(final_paths),
        )

        def fake_resolve_output_path(config, audio_count, **kwargs):
            resolve_calls.append((audio_count, kwargs))
            return list(output_paths)

        def fake_build_export(input_path, output_path):
            export_calls.append((input_path, output_path))
            return ["ffmpeg", input_path, output_path]

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.resolve_output_path", fake_resolve_output_path)
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_export_aac_command", fake_build_export)
        monkeypatch.setattr(FFmpegWorker, "_exec_ffmpeg", lambda *args, **kwargs: True)

        config = CombatAudioConfig(
            input_path="/tmp/in.mkv",
            audio_dir="/tmp/audio",
            output_dir="/tmp/out",
            mix_enabled=False,
            boxed=False,
            audio_stream_index=0,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            worker._combat_audio_pipeline(config, False, audio_files, len(audio_files), tmp_dir)

        assert resolve_calls == [(2, {"audio_filenames": audio_files})]
        assert export_calls == list(zip(final_paths, output_paths))

    def test_combat_audio_pipeline_keeps_original_audio_filenames_when_some_outputs_fail(self, monkeypatch):
        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
        resolve_calls = []
        export_calls = []

        audio_files = ["z_theme.aac", "a_theme.aac", "m_theme.aac"]
        output_paths = ["/tmp/out/01_z_theme_aligned.aac", "/tmp/out/02_m_theme_aligned.aac"]

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_audio_streams", lambda path: [])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_duration", lambda path: 20.0)
        monkeypatch.setattr(
            FFmpegWorker,
            "_parallel_phase",
            lambda self, *args, **kwargs: ["/tmp/final_z.m4a", None, "/tmp/final_m.m4a"],
        )

        def fake_resolve_output_path(config, audio_count, **kwargs):
            resolve_calls.append((audio_count, kwargs))
            return list(output_paths)

        def fake_build_export(input_path, output_path):
            export_calls.append((input_path, output_path))
            return ["ffmpeg", input_path, output_path]

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.resolve_output_path", fake_resolve_output_path)
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_export_aac_command", fake_build_export)
        monkeypatch.setattr(FFmpegWorker, "_exec_ffmpeg", lambda *args, **kwargs: True)

        config = CombatAudioConfig(
            input_path="/tmp/in.mkv",
            audio_dir="/tmp/audio",
            output_dir="/tmp/out",
            mix_enabled=False,
            boxed=False,
            audio_stream_index=0,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            worker._combat_audio_pipeline(config, False, audio_files, len(audio_files), tmp_dir)

        assert resolve_calls == [(2, {"audio_filenames": ["z_theme.aac", "m_theme.aac"]})]
        assert export_calls == [
            ("/tmp/final_z.m4a", "/tmp/out/01_z_theme_aligned.aac"),
            ("/tmp/final_m.m4a", "/tmp/out/02_m_theme_aligned.aac"),
        ]

    def test_combat_audio_pipeline_includes_parallel_failure_details_when_all_outputs_fail(self, monkeypatch):
        worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
        errors = []
        worker.error.connect(errors.append)

        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_audio_streams", lambda path: [object()])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_duration", lambda path: 20.0)
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_extract_command", lambda *args, **kwargs: ["ffmpeg"])
        monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.resolve_output_path", lambda *args, **kwargs: [])
        monkeypatch.setattr(FFmpegWorker, "_exec_ffmpeg", lambda *args, **kwargs: True)

        def fake_parallel_phase(self, config, items, *args, **kwargs):
            if len(items) == 2 and isinstance(items[0], tuple):
                self._parallel_phase_failures = [
                    ("bg1.aac", "mix failed: bg1.aac"),
                    ("bg2.aac", "mix failed: bg2.aac"),
                ]
                return [None, None]
            self._parallel_phase_failures = []
            return ["/tmp/adjusted_00.m4a", "/tmp/adjusted_01.m4a"]

        monkeypatch.setattr(FFmpegWorker, "_parallel_phase", fake_parallel_phase)

        config = CombatAudioConfig(
            input_path="/tmp/in.mkv",
            audio_dir="/tmp/audio",
            output_dir="/tmp",
            mix_enabled=True,
            boxed=False,
            audio_stream_index=0,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            worker._combat_audio_pipeline(config, False, ["bg1.aac", "bg2.aac"], 2, tmp_dir)

        assert len(errors) == 1
        assert "未生成任何输出音频" in errors[0]
        assert "bg1.aac: mix failed: bg1.aac" in errors[0]
        assert "bg2.aac: mix failed: bg2.aac" in errors[0]
