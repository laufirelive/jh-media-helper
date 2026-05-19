# Combat Audio Single Subtitle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional single `.srt` or `.ass` subtitle file to the combat-audio MKV mux workflow.

**Architecture:** Extend `CombatAudioConfig` with a `subtitle_path` snapshot field, validate it only for boxed video output, then pass it into the existing FFmpeg and mkvmerge mux command builders. Add a compact subtitle selector to `CombatAudioPanel` that is enabled only when MKV boxing is active for video input.

**Tech Stack:** Python 3.12, PyQt6, FFmpeg/FFprobe CLI, optional MKVToolNix `mkvmerge`, pytest, pytest-qt.

---

## File Structure

- Modify `src/core/config.py`
  - Owns `CombatAudioConfig` serialization compatibility.
  - Add `subtitle_path: str | None`.
- Modify `src/core/processors/combat_audio.py`
  - Owns media validation and command construction.
  - Add subtitle validation helper and pass optional subtitle into mux builders.
- Modify `src/worker/ffmpeg_worker.py`
  - Owns pipeline orchestration.
  - Pass `config.subtitle_path` to the selected mux backend.
- Modify `src/gui/task_panels/combat_audio_panel.py`
  - Owns the task UI and config construction.
  - Add subtitle file selector and clear button inside output settings.
- Modify tests:
  - `tests/test_combat_audio_config.py`
  - `tests/test_combat_audio_processor.py`
  - `tests/test_ffmpeg_worker.py`
  - `tests/gui/task_panels/test_combat_audio_panel_preview_start.py`

## Implementation Notes

- The feature is intentionally single-file only: field name is `subtitle_path`, not `subtitle_paths`.
- A subtitle path is meaningful only when `boxed=True` and input is video.
- Existing embedded subtitle preservation stays unchanged.
- Avoid changing `FileSelector` globally. Add a clear button next to the subtitle selector in `CombatAudioPanel` only.

---

### Task 1: Config and Subtitle Validation

**Files:**
- Modify: `src/core/config.py`
- Modify: `src/core/processors/combat_audio.py`
- Test: `tests/test_combat_audio_config.py`
- Test: `tests/test_combat_audio_processor.py`

- [ ] **Step 1: Write failing config tests**

Append these tests to `tests/test_combat_audio_config.py`:

```python
def test_combat_audio_config_subtitle_path_defaults_to_none():
    cfg = CombatAudioConfig(input_path="/tmp/video.mkv", audio_dir="/tmp/audio")

    assert cfg.subtitle_path is None


def test_combat_audio_config_subtitle_path_round_trip():
    cfg = CombatAudioConfig(
        input_path="/tmp/video.mkv",
        audio_dir="/tmp/audio",
        boxed=True,
        subtitle_path="/tmp/subtitle.ass",
    )

    restored = CombatAudioConfig.from_dict(cfg.to_dict())

    assert restored.subtitle_path == "/tmp/subtitle.ass"


def test_combat_audio_config_empty_subtitle_path_normalizes_to_none():
    restored = CombatAudioConfig.from_dict({
        "input_path": "/tmp/video.mkv",
        "audio_dir": "/tmp/audio",
        "subtitle_path": "",
    })

    assert restored.subtitle_path is None
```

- [ ] **Step 2: Run config tests to verify they fail**

Run:

```bash
python -m pytest tests/test_combat_audio_config.py -q
```

Expected: FAIL with `AttributeError: 'CombatAudioConfig' object has no attribute 'subtitle_path'`.

- [ ] **Step 3: Implement config field**

In `src/core/config.py`, update `CombatAudioConfig`:

```python
@dataclass
class CombatAudioConfig:
    input_path: str
    audio_dir: str
    output_dir: str | None = None
    mix_enabled: bool = True
    volume: float = 0.6
    boxed: bool = False
    thread_count: int = 1
    audio_stream_index: int = 0
    audio_order: list[str] | None = None
    secondary_video_paths: list[str] | None = None
    mkvmerge_path: str | None = None
    mux_backend: str = "auto"
    subtitle_path: str | None = None

    def __post_init__(self):
        if self.audio_order is None:
            self.audio_order = []
        if self.secondary_video_paths is None:
            self.secondary_video_paths = []
        if not self.subtitle_path:
            self.subtitle_path = None
```

Update `to_dict()` to include:

```python
"subtitle_path": self.subtitle_path,
```

Update `from_dict()` to pass:

```python
subtitle_path=d.get("subtitle_path") or None,
```

- [ ] **Step 4: Run config tests to verify they pass**

Run:

```bash
python -m pytest tests/test_combat_audio_config.py -q
```

Expected: PASS.

- [ ] **Step 5: Write failing validation tests**

Append these tests to `tests/test_combat_audio_processor.py` near the existing validation tests:

```python
class TestValidateSubtitleFile:
    def test_boxed_video_accepts_srt_subtitle(self, tmp_path, monkeypatch):
        input_path = tmp_path / "main.mkv"
        input_path.write_bytes(b"")
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "bg.aac").write_bytes(b"")
        subtitle_path = tmp_path / "caption.srt"
        subtitle_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n", encoding="utf-8")

        monkeypatch.setattr("src.core.processors.combat_audio.has_video_stream", lambda path: True)

        cfg = CombatAudioConfig(
            input_path=str(input_path),
            audio_dir=str(audio_dir),
            boxed=True,
            subtitle_path=str(subtitle_path),
        )

        ok, err = validate(cfg)

        assert ok is True
        assert err is None

    def test_boxed_video_accepts_ass_subtitle(self, tmp_path, monkeypatch):
        input_path = tmp_path / "main.mkv"
        input_path.write_bytes(b"")
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "bg.aac").write_bytes(b"")
        subtitle_path = tmp_path / "caption.ass"
        subtitle_path.write_text("[Script Info]\nTitle: Test\n", encoding="utf-8")

        monkeypatch.setattr("src.core.processors.combat_audio.has_video_stream", lambda path: True)

        cfg = CombatAudioConfig(
            input_path=str(input_path),
            audio_dir=str(audio_dir),
            boxed=True,
            subtitle_path=str(subtitle_path),
        )

        ok, err = validate(cfg)

        assert ok is True
        assert err is None

    def test_boxed_video_rejects_missing_subtitle(self, tmp_path, monkeypatch):
        input_path = tmp_path / "main.mkv"
        input_path.write_bytes(b"")
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "bg.aac").write_bytes(b"")
        subtitle_path = tmp_path / "missing.srt"

        monkeypatch.setattr("src.core.processors.combat_audio.has_video_stream", lambda path: True)

        cfg = CombatAudioConfig(
            input_path=str(input_path),
            audio_dir=str(audio_dir),
            boxed=True,
            subtitle_path=str(subtitle_path),
        )

        ok, err = validate(cfg)

        assert ok is False
        assert err == f"字幕文件不存在: {subtitle_path}"

    def test_boxed_video_rejects_unsupported_subtitle_extension(self, tmp_path, monkeypatch):
        input_path = tmp_path / "main.mkv"
        input_path.write_bytes(b"")
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "bg.aac").write_bytes(b"")
        subtitle_path = tmp_path / "caption.txt"
        subtitle_path.write_text("not a supported subtitle", encoding="utf-8")

        monkeypatch.setattr("src.core.processors.combat_audio.has_video_stream", lambda path: True)

        cfg = CombatAudioConfig(
            input_path=str(input_path),
            audio_dir=str(audio_dir),
            boxed=True,
            subtitle_path=str(subtitle_path),
        )

        ok, err = validate(cfg)

        assert ok is False
        assert err == f"字幕文件格式不支持: {subtitle_path}"

    def test_non_boxed_output_ignores_invalid_subtitle_path(self, tmp_path):
        input_path = tmp_path / "main.mkv"
        input_path.write_bytes(b"")
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        (audio_dir / "bg.aac").write_bytes(b"")

        cfg = CombatAudioConfig(
            input_path=str(input_path),
            audio_dir=str(audio_dir),
            boxed=False,
            subtitle_path=str(tmp_path / "missing.txt"),
        )

        ok, err = validate(cfg)

        assert ok is True
        assert err is None
```

- [ ] **Step 6: Run validation tests to verify they fail**

Run:

```bash
python -m pytest tests/test_combat_audio_processor.py::TestValidateSubtitleFile -q
```

Expected: FAIL because unsupported subtitle validation is not implemented.

- [ ] **Step 7: Implement subtitle validation**

In `src/core/processors/combat_audio.py`, add near constants:

```python
SUBTITLE_EXTENSIONS = {".srt", ".ass"}
```

Add helper near `validate_secondary_videos()`:

```python
def validate_subtitle_file(config: CombatAudioConfig, *, is_audio: bool) -> tuple[bool, str | None]:
    """Validate optional external subtitle for boxed video output."""
    if is_audio or not config.boxed or not config.subtitle_path:
        return True, None

    if not os.path.exists(config.subtitle_path):
        return False, f"字幕文件不存在: {config.subtitle_path}"

    ext = os.path.splitext(config.subtitle_path)[1].lower()
    if ext not in SUBTITLE_EXTENSIONS:
        return False, f"字幕文件格式不支持: {config.subtitle_path}"

    return True, None
```

Update `validate()` after `validate_secondary_videos()`:

```python
    is_audio = is_pure_audio(config.input_path)
    ok, err = validate_secondary_videos(config, is_audio=is_audio)
    if not ok:
        return ok, err
    return validate_subtitle_file(config, is_audio=is_audio)
```

- [ ] **Step 8: Run focused tests**

Run:

```bash
python -m pytest tests/test_combat_audio_config.py tests/test_combat_audio_processor.py::TestValidateSubtitleFile -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/core/config.py src/core/processors/combat_audio.py tests/test_combat_audio_config.py tests/test_combat_audio_processor.py
git commit -m "feat: validate optional combat audio subtitle"
```

---

### Task 2: Mux Command Builders

**Files:**
- Modify: `src/core/processors/combat_audio.py`
- Test: `tests/test_combat_audio_processor.py`

- [ ] **Step 1: Write failing FFmpeg mux command tests**

Add these methods to `TestBuildMuxCommand` in `tests/test_combat_audio_processor.py`:

```python
    def test_maps_external_subtitle_after_audio_streams(self):
        cmd = build_mux_command(
            "/video/input.mkv",
            ["/audio/m1.aac", "/audio/m2.aac"],
            "/output/final.mkv",
            subtitle_path="/subs/caption.srt",
        )

        assert cmd.count("-i") == 4
        assert cmd[cmd.index("/subs/caption.srt") - 1] == "-i"
        map_pairs = [cmd[i:i + 2] for i in range(len(cmd) - 1)]
        assert ["-map", "0:v"] in map_pairs
        assert ["-map", "0:s?"] in map_pairs
        assert ["-map", "1:a"] in map_pairs
        assert ["-map", "2:a"] in map_pairs
        assert ["-map", "3:s:0"] in map_pairs
        assert cmd.index("3:s:0") > cmd.index("2:a")

    def test_no_external_subtitle_keeps_existing_input_count(self):
        cmd = build_mux_command(
            "/video/input.mkv",
            ["/audio/m1.aac"],
            "/output/final.mkv",
            subtitle_path=None,
        )

        assert cmd.count("-i") == 2
        assert "/subs/caption.srt" not in cmd
```

- [ ] **Step 2: Write failing mkvmerge command tests**

Add these methods to `TestBuildMkvmergeMuxCommand`:

```python
    def test_appends_external_subtitle_input_segment(self):
        cmd = build_mkvmerge_mux_command(
            "/bin/mkvmerge",
            "/video/input.mkv",
            ["/audio/m1.aac"],
            "/output/final.mkv",
            subtitle_path="/subs/caption.ass",
        )

        subtitle_index = cmd.index("/subs/caption.ass")

        assert cmd[subtitle_index - 7:subtitle_index] == [
            "--no-video",
            "--no-audio",
            "--no-chapters",
            "--no-global-tags",
            "--no-track-tags",
            "--default-track-flag",
            "0:no",
        ]

    def test_no_external_subtitle_keeps_existing_tail(self):
        cmd = build_mkvmerge_mux_command(
            "/bin/mkvmerge",
            "/video/input.mkv",
            ["/audio/m1.aac"],
            "/output/final.mkv",
            subtitle_path=None,
        )

        assert "/subs/caption.ass" not in cmd
```

- [ ] **Step 3: Run command tests to verify they fail**

Run:

```bash
python -m pytest \
  tests/test_combat_audio_processor.py::TestBuildMuxCommand \
  tests/test_combat_audio_processor.py::TestBuildMkvmergeMuxCommand \
  -q
```

Expected: FAIL with `TypeError: ... got an unexpected keyword argument 'subtitle_path'`.

- [ ] **Step 4: Implement FFmpeg mux command support**

Update `build_mux_command()` signature:

```python
def build_mux_command(
    video_path: str,
    mixed_audios: list[str],
    output_path: str,
    keep_original_audio: bool = True,
    subtitle_path: str | None = None,
) -> list[str]:
```

Update command construction:

```python
    cmd = ["ffmpeg", "-y", "-fflags", "+genpts", "-i", video_path]

    for audio in mixed_audios:
        cmd += ["-i", audio]

    subtitle_input_index = None
    if subtitle_path:
        subtitle_input_index = len(mixed_audios) + 1
        cmd += ["-i", subtitle_path]

    cmd += ["-map", "0:v", "-map", "0:s?"]

    for i in range(len(mixed_audios)):
        cmd += ["-map", f"{i + 1}:a"]

    if keep_original_audio:
        cmd += ["-map", "0:a"]

    if subtitle_input_index is not None:
        cmd += ["-map", f"{subtitle_input_index}:s:0"]
```

Leave the existing metadata, codec, timestamp, and disposition block unchanged.

- [ ] **Step 5: Implement mkvmerge mux command support**

Update `build_mkvmerge_mux_command()` signature:

```python
def build_mkvmerge_mux_command(
    mkvmerge_path: str,
    video_path: str,
    final_audios: list[str],
    output_path: str,
    *,
    keep_original_audio: bool = True,
    subtitle_path: str | None = None,
) -> list[str]:
```

Before `return cmd`, append:

```python
    if subtitle_path:
        cmd += [
            "--no-video",
            "--no-audio",
            "--no-chapters",
            "--no-global-tags",
            "--no-track-tags",
            "--default-track-flag",
            "0:no",
            subtitle_path,
        ]
```

- [ ] **Step 6: Adjust mkvmerge subtitle segment test if needed**

If the test from Step 2 is awkward around slicing, replace `test_appends_external_subtitle_input_segment` with this exact version:

```python
    def test_appends_external_subtitle_input_segment(self):
        cmd = build_mkvmerge_mux_command(
            "/bin/mkvmerge",
            "/video/input.mkv",
            ["/audio/m1.aac"],
            "/output/final.mkv",
            subtitle_path="/subs/caption.ass",
        )

        subtitle_index = cmd.index("/subs/caption.ass")
        assert cmd[subtitle_index - 7:subtitle_index] == [
            "--no-video",
            "--no-audio",
            "--no-chapters",
            "--no-global-tags",
            "--no-track-tags",
            "--default-track-flag",
            "0:no",
        ]
```

- [ ] **Step 7: Run command tests to verify they pass**

Run:

```bash
python -m pytest \
  tests/test_combat_audio_processor.py::TestBuildMuxCommand \
  tests/test_combat_audio_processor.py::TestBuildMkvmergeMuxCommand \
  -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/core/processors/combat_audio.py tests/test_combat_audio_processor.py
git commit -m "feat: include optional subtitle in mkv mux commands"
```

---

### Task 3: Worker Pipeline Propagation

**Files:**
- Modify: `src/worker/ffmpeg_worker.py`
- Test: `tests/test_ffmpeg_worker.py`

- [ ] **Step 1: Write failing worker propagation tests**

Add these tests near existing combat audio mux tests in `tests/test_ffmpeg_worker.py`:

```python
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
```

- [ ] **Step 2: Run worker tests to verify they fail**

Run:

```bash
python -m pytest \
  tests/test_ffmpeg_worker.py::TestFFmpegWorker::test_combat_audio_pipeline_passes_subtitle_to_ffmpeg_mux \
  tests/test_ffmpeg_worker.py::TestFFmpegWorker::test_combat_audio_pipeline_passes_subtitle_to_mkvmerge_for_each_part \
  -q
```

Expected: FAIL because the worker does not pass `subtitle_path`.

- [ ] **Step 3: Pass subtitle_path into both mux builders**

In `src/worker/ffmpeg_worker.py`, update the mkvmerge builder call:

```python
                    cmd = combat_audio.build_mkvmerge_mux_command(
                        mkvmerge_path,
                        video_path,
                        final_paths,
                        output_path,
                        keep_original_audio=part_has_audio_streams,
                        subtitle_path=config.subtitle_path,
                    )
```

Update the FFmpeg builder call:

```python
                    cmd = combat_audio.build_mux_command(
                        video_path,
                        final_paths,
                        output_path,
                        keep_original_audio=part_has_audio_streams,
                        subtitle_path=config.subtitle_path,
                    )
```

- [ ] **Step 4: Run worker tests**

Run:

```bash
python -m pytest tests/test_ffmpeg_worker.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/worker/ffmpeg_worker.py tests/test_ffmpeg_worker.py
git commit -m "feat: pass subtitle through combat audio mux pipeline"
```

---

### Task 4: Combat Audio Panel UI

**Files:**
- Modify: `src/gui/task_panels/combat_audio_panel.py`
- Test: `tests/gui/task_panels/test_combat_audio_panel_preview_start.py`

- [ ] **Step 1: Write failing GUI tests**

Append these tests to `tests/gui/task_panels/test_combat_audio_panel_preview_start.py`:

```python
def test_subtitle_selector_enabled_only_for_boxed_video_input(panel, tmp_path):
    input_path = tmp_path / "main.mkv"
    input_path.write_bytes(b"")
    panel._input_selector._edit.setText(str(input_path))
    panel._is_pure_audio = False
    panel._boxed_checkbox.setChecked(True)
    panel._update_param_states()

    assert panel._subtitle_selector.isEnabled()
    assert panel._clear_subtitle_btn.isEnabled()

    panel._boxed_checkbox.setChecked(False)
    panel._update_param_states()

    assert not panel._subtitle_selector.isEnabled()
    assert not panel._clear_subtitle_btn.isEnabled()

    panel._is_pure_audio = True
    panel._boxed_checkbox.setChecked(True)
    panel._update_param_states()

    assert not panel._subtitle_selector.isEnabled()
    assert not panel._clear_subtitle_btn.isEnabled()


def test_subtitle_path_written_to_config_only_when_boxed_video(panel, tmp_path):
    input_path = tmp_path / "main.mkv"
    input_path.write_bytes(b"")
    subtitle_path = tmp_path / "caption.srt"
    subtitle_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n", encoding="utf-8")

    panel._input_selector._edit.setText(str(input_path))
    panel._audio_dir_selector._edit.setText("/audio")
    panel._subtitle_selector.set_path(str(subtitle_path))
    panel._is_pure_audio = False
    panel._boxed_checkbox.setChecked(True)

    assert panel.build_config().subtitle_path == str(subtitle_path)

    panel._boxed_checkbox.setChecked(False)
    assert panel.build_config().subtitle_path is None

    panel._boxed_checkbox.setChecked(True)
    panel._is_pure_audio = True
    panel._update_param_states()
    assert panel.build_config().subtitle_path is None


def test_clear_subtitle_button_clears_subtitle_path(panel, tmp_path):
    subtitle_path = tmp_path / "caption.ass"
    subtitle_path.write_text("[Script Info]\nTitle: Test\n", encoding="utf-8")
    panel._subtitle_selector.set_path(str(subtitle_path))

    panel._clear_subtitle()

    assert panel._subtitle_selector.path() == ""
```

- [ ] **Step 2: Run GUI tests to verify they fail**

Run:

```bash
python -m pytest tests/gui/task_panels/test_combat_audio_panel_preview_start.py -q
```

Expected: FAIL with `AttributeError: 'CombatAudioPanel' object has no attribute '_subtitle_selector'`.

- [ ] **Step 3: Add subtitle selector state**

In `CombatAudioPanel.__init__()` after `_secondary_video_paths`:

```python
self._subtitle_path: str | None = None
```

Add module-level filter near `_MEDIA_FILTER`:

```python
_SUBTITLE_FILTER = "字幕文件 (*.srt *.ass);;所有文件 (*)"
```

- [ ] **Step 4: Add UI controls**

In `_build_upper_right()`, after adding `_boxed_checkbox` and before `_output_selector`, add:

```python
        subtitle_row = QHBoxLayout()
        subtitle_row.setSpacing(6)
        self._subtitle_selector = FileSelector(
            label="字幕文件:",
            placeholder="可选，仅封装 MKV 时使用",
            dialog_mode="file",
            file_filter=_SUBTITLE_FILTER,
        )
        self._subtitle_selector.path_changed.connect(self._on_subtitle_changed)
        subtitle_row.addWidget(self._subtitle_selector, 1)

        self._clear_subtitle_btn = QPushButton("清空")
        self._clear_subtitle_btn.clicked.connect(self._clear_subtitle)
        subtitle_row.addWidget(self._clear_subtitle_btn)
        out_layout.addLayout(subtitle_row)
```

- [ ] **Step 5: Add subtitle UI handlers**

Add methods near secondary-video helper methods:

```python
    def _on_subtitle_changed(self, path: str) -> None:
        self._subtitle_path = path or None

    def _clear_subtitle(self) -> None:
        self._subtitle_selector.set_path("")
```

- [ ] **Step 6: Update enable/disable logic**

In `_update_param_states()`, after the existing secondary group enablement:

```python
        subtitle_enabled = is_video_input and self._boxed_checkbox.isChecked()
        self._subtitle_selector.setEnabled(subtitle_enabled)
        self._clear_subtitle_btn.setEnabled(subtitle_enabled)
```

Use the local `is_video_input` already computed by the method. If `_update_param_states()` is called before subtitle widgets exist, guard with:

```python
        if hasattr(self, "_subtitle_selector"):
            self._subtitle_selector.setEnabled(subtitle_enabled)
            self._clear_subtitle_btn.setEnabled(subtitle_enabled)
```

- [ ] **Step 7: Add subtitle to built config**

In `_build_combat_config()`, after `secondary_video_paths`:

```python
        subtitle_path = self._subtitle_selector.path() or None
        if not boxed or self._is_pure_audio:
            subtitle_path = None
```

Pass to `CombatAudioConfig(...)`:

```python
            subtitle_path=subtitle_path,
```

- [ ] **Step 8: Run GUI tests**

Run:

```bash
python -m pytest tests/gui/task_panels/test_combat_audio_panel_preview_start.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/gui/task_panels/combat_audio_panel.py tests/gui/task_panels/test_combat_audio_panel_preview_start.py
git commit -m "feat: add optional subtitle selector for combat mkv output"
```

---

### Task 5: Full Verification

**Files:**
- No source changes expected.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
python -m pytest \
  tests/test_combat_audio_config.py \
  tests/test_combat_audio_processor.py \
  tests/test_ffmpeg_worker.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run focused GUI tests**

Run:

```bash
python -m pytest \
  tests/gui/task_panels/test_combat_audio_panel_preview_start.py \
  tests/gui/test_queue_tab_combat_audio_counts.py \
  tests/gui/test_main_window_runtime_settings.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run full test suite**

Run:

```bash
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 4: Inspect git status**

Run:

```bash
git status --short
```

Expected: clean worktree, unless unrelated user changes existed before implementation.

---

## Self-Review

Spec coverage:

- Single `.srt/.ass` subtitle selection: Task 1 and Task 4.
- Config snapshot field: Task 1.
- FFmpeg and mkvmerge command support: Task 2.
- Worker propagation to every part: Task 3.
- UI enabled only for boxed video: Task 4.
- Validation and error messages: Task 1.
- Backward compatibility when no subtitle exists: Task 1 and Task 2.

Placeholder scan:

- No `TBD`, `TODO`, or vague "add tests" steps remain.
- Each code-changing step includes concrete snippets and exact files.

Type consistency:

- Field name is consistently `subtitle_path`.
- Builder parameter name is consistently `subtitle_path`.
- GUI attribute names are consistently `_subtitle_selector`, `_clear_subtitle_btn`, and `_clear_subtitle()`.
