# Preview Start Slider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a row-level preview start slider to the CombatAudio tab so both input-track preview and mix preview can start from the selected timestamp and always preview 10 seconds.

**Architecture:** First extend the preview command/data path to accept `start_ms` and unify preview duration at 10 seconds. Then update preview-cache keys to include the start position, add a dedicated `PreviewStartCell` widget for the track table, and wire `CombatAudioPanel` to keep a single shared `_preview_start_ms` for the currently selected track.

**Tech Stack:** Python 3, PyQt6 widgets, ffmpeg/ffprobe, pytest

---

### Task 1: Add Preview Window Parameters To Processor Helpers

**Files:**
- Modify: `src/core/processors/combat_audio.py`
- Test: `tests/test_combat_audio_processor.py`

- [ ] **Step 1: Write the failing tests for preview offset and duration**

```python
def test_build_extract_preview_command_includes_start_and_duration():
    cmd = build_extract_command("/input/video.mkv", 0, "/output/audio.aac", start_seconds=12.5, duration_seconds=10.0)
    assert "-ss" in cmd
    assert "12.5" in cmd
    assert "-t" in cmd
    assert "10.0" in cmd
    assert "0:a:0" in cmd


def test_build_preview_command_trims_both_inputs_from_offset():
    cmd = build_preview_command(
        "/audio/base.aac",
        "/audio/bg.aac",
        0.6,
        "/output/preview.aac",
        start_seconds=42.0,
        duration_seconds=10.0,
    )
    filter_str = " ".join(cmd)
    assert "atrim=start=42.0:end=52.0" in filter_str
    assert filter_str.count("atrim=start=42.0:end=52.0") == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_combat_audio_processor.py::TestBuildExtractCommand::test_command_structure tests/test_combat_audio_processor.py::TestBuildPreviewCommand::test_contains_atrim_5s -v`
Expected: FAIL because the helpers do not accept preview offsets or a unified 10-second duration

- [ ] **Step 3: Write minimal implementation**

```python
PREVIEW_DURATION_SECONDS = 10.0


def build_extract_command(
    input_path: str,
    stream_index: int,
    output_path: str,
    *,
    start_seconds: float = 0.0,
    duration_seconds: float | None = None,
) -> list[str]:
    cmd = ["ffmpeg", "-y"]
    if start_seconds > 0:
        cmd += ["-ss", str(start_seconds)]
    cmd += ["-i", input_path, "-map", f"0:a:{stream_index}"]
    if duration_seconds is not None:
        cmd += ["-t", str(duration_seconds)]
    cmd += ["-c:a", "aac", output_path]
    return cmd


def build_preview_command(
    base_audio: str,
    bg_audio: str,
    volume: float,
    output_path: str,
    *,
    start_seconds: float = 0.0,
    duration_seconds: float = PREVIEW_DURATION_SECONDS,
) -> list[str]:
    end_seconds = start_seconds + duration_seconds
    trim = f"atrim=start={start_seconds}:end={end_seconds}"
    filter_complex = (
        f"[0:a]{trim},{_LOUDNORM}[main];"
        f"[1:a]{trim},{_LOUDNORM}[bg];"
        f"[main][bg]amix=inputs=2:duration=first:dropout_transition=1:weights={volume} 1:normalize=0,volume=2,{_LOUDNORM}"
    )
    return [
        "ffmpeg", "-y", "-hwaccel", "auto",
        "-i", base_audio, "-i", bg_audio,
        "-filter_complex", filter_complex,
        "-c:a", "aac", "-b:a", "192k", output_path,
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_combat_audio_processor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/processors/combat_audio.py tests/test_combat_audio_processor.py
git commit -m "feat: add offset-based preview command builders"
```

### Task 2: Include Preview Start In Cache Keys

**Files:**
- Modify: `src/core/preview_cache.py`
- Test: `tests/test_preview_cache.py`

- [ ] **Step 1: Write the failing tests for `start_ms` cache separation**

```python
def test_build_input_track_cache_key_changes_with_start_ms(tmp_path):
    source = tmp_path / "input.aac"
    source.write_bytes(b"audio")
    key1 = build_input_track_cache_key(str(source), 0, start_ms=0)
    key2 = build_input_track_cache_key(str(source), 0, start_ms=15000)
    assert key1 != key2


def test_build_mix_preview_cache_key_changes_with_start_ms(tmp_path):
    input_file = tmp_path / "input.aac"
    bg_file = tmp_path / "bg.aac"
    input_file.write_bytes(b"input")
    bg_file.write_bytes(b"bg")
    key1 = build_mix_preview_cache_key(str(input_file), 0, str(bg_file), 0.6, start_ms=0)
    key2 = build_mix_preview_cache_key(str(input_file), 0, str(bg_file), 0.6, start_ms=10000)
    assert key1 != key2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_preview_cache.py -k "start_ms" -v`
Expected: FAIL because cache-key builders do not accept `start_ms`

- [ ] **Step 3: Write minimal implementation**

```python
def build_input_track_cache_key(input_path: str, audio_position: int, *, start_ms: int = 0) -> str:
    return "|".join([
        "kind=input_track",
        f"input={input_path}",
        _build_file_fingerprint(input_path),
        f"stream={audio_position}",
        f"start_ms={start_ms}",
        "version=v3",
    ])


def build_base_audio_cache_key(input_path: str, audio_position: int, *, start_ms: int = 0) -> str:
    return "|".join([
        "kind=base_audio",
        f"input={input_path}",
        _build_file_fingerprint(input_path),
        f"stream={audio_position}",
        f"start_ms={start_ms}",
        "version=v2",
    ])


def build_mix_preview_cache_key(
    input_path: str,
    audio_position: int,
    bg_path: str,
    volume: float,
    *,
    start_ms: int = 0,
) -> str:
    return "|".join([
        "kind=mix_preview",
        f"input={input_path}",
        _build_file_fingerprint(input_path),
        f"stream={audio_position}",
        f"bg={bg_path}",
        _build_file_fingerprint(bg_path),
        f"volume={volume!r}",
        f"start_ms={start_ms}",
        "version=v2",
    ])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_preview_cache.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/preview_cache.py tests/test_preview_cache.py
git commit -m "feat: add preview start offsets to cache keys"
```

### Task 3: Add Preview Start Cell Widget

**Files:**
- Create: `src/gui/components/preview_start_cell.py`
- Modify: `src/gui/components/__init__.py`
- Test: `tests/gui/components/test_preview_start_cell.py`

- [ ] **Step 1: Write the failing widget tests**

```python
def test_preview_start_cell_shows_formatted_start_time(qapp):
    cell = PreviewStartCell()
    cell.set_maximum_ms(3_723_000)
    cell.set_value_ms(83_000)
    assert cell.time_text() == "00:01:23"


def test_preview_start_cell_disables_slider_when_inactive(qapp):
    cell = PreviewStartCell()
    cell.set_active(False)
    assert cell.is_slider_enabled() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/gui/components/test_preview_start_cell.py -v`
Expected: FAIL with `ModuleNotFoundError` because the widget does not exist

- [ ] **Step 3: Write minimal widget implementation**

```python
class PreviewStartCell(QWidget):
    value_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._max_ms = 0
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._label = QLabel("00:00:00")
        ...

    def set_maximum_ms(self, max_ms: int) -> None:
        self._max_ms = max(0, max_ms)
        self._slider.setRange(0, self._max_ms)

    def set_value_ms(self, value_ms: int) -> None:
        self._slider.setValue(max(0, min(value_ms, self._max_ms)))
        self._label.setText(_format_hhmmss(self._slider.value()))

    def set_active(self, active: bool) -> None:
        self._slider.setEnabled(active)

    def time_text(self) -> str:
        return self._label.text()

    def is_slider_enabled(self) -> bool:
        return self._slider.isEnabled()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/gui/components/test_preview_start_cell.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gui/components/preview_start_cell.py src/gui/components/__init__.py tests/gui/components/test_preview_start_cell.py
git commit -m "feat: add preview start cell widget"
```

### Task 4: Wire Shared Preview Start State Into CombatAudioPanel UI

**Files:**
- Modify: `src/gui/task_panels/combat_audio_panel.py`
- Test: `tests/test_preview_cache.py`
- Test: `tests/gui/components/test_preview_start_cell.py`

- [ ] **Step 1: Write the failing panel tests for shared active-row behavior**

```python
def test_only_selected_track_row_has_active_preview_start_cell(qapp):
    panel = CombatAudioPanel(preview_cache=None)
    panel._input_duration = 120.0
    panel._input_streams = [
        combat_audio.AudioStreamInfo(index=1, audio_position=0, codec="aac", sample_rate=48000, channels=2, channel_layout="stereo"),
        combat_audio.AudioStreamInfo(index=2, audio_position=1, codec="aac", sample_rate=48000, channels=2, channel_layout="stereo"),
    ]
    panel._refresh_tracks_table()
    assert panel._preview_start_cells[0].is_slider_enabled() is True
    assert panel._preview_start_cells[1].is_slider_enabled() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_preview_cache.py -k "active_preview_start_cell" -v`
Expected: FAIL because the panel does not yet create preview-start cells

- [ ] **Step 3: Write minimal UI wiring**

```python
class CombatAudioPanel(BaseTaskPanel):
    def __init__(...):
        ...
        self._preview_start_ms = 0
        self._preview_start_cells: list[PreviewStartCell] = []

    def _build_input_tracks_table(...):
        self._tracks_table = QTableWidget(0, 7)
        self._tracks_table.setHorizontalHeaderLabels(["", "索引", "编码", "预览起点", "采样率", "声道", ""])
        ...

    def _refresh_tracks_table(self):
        self._preview_start_cells.clear()
        ...
        cell = PreviewStartCell()
        cell.set_maximum_ms(int(self._input_duration * 1000))
        cell.set_value_ms(self._preview_start_ms)
        cell.set_active(stream.audio_position == self._track_radio_group.checkedId() or row == 0)
        cell.value_changed.connect(self._on_preview_start_changed)
        self._tracks_table.setCellWidget(row, 3, cell)
        self._preview_start_cells.append(cell)

    def _on_preview_start_changed(self, value_ms: int) -> None:
        self._preview_start_ms = value_ms
        for cell in self._preview_start_cells:
            cell.set_value_ms(value_ms)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_preview_cache.py tests/gui/components/test_preview_start_cell.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gui/task_panels/combat_audio_panel.py tests/test_preview_cache.py tests/gui/components/test_preview_start_cell.py
git commit -m "feat: add shared preview start slider to track table"
```

### Task 5: Use Preview Start In Input Track Preview

**Files:**
- Modify: `src/gui/components/audio_player.py`
- Modify: `src/gui/task_panels/combat_audio_panel.py`
- Test: `tests/test_preview_cache.py`

- [ ] **Step 1: Write the failing tests for offset-based input preview**

```python
@patch("src.gui.components.audio_player.combat_audio.run_ffmpeg_command")
def test_play_stream_uses_start_ms_in_extract_command(mock_run, tmp_path, qapp):
    session = PreviewCacheSession(root_dir=str(tmp_path / "preview"))
    session.start()
    player = AudioPlayerBar(preview_cache=session)
    mock_run.return_value = None
    with patch("src.gui.components.audio_player.combat_audio.build_extract_command") as mock_build:
        mock_build.return_value = ["ffmpeg"]
        player.play_file = lambda *args, **kwargs: None
        player.play_stream("/tmp/a.mp4", 0, "输入 #1 AAC", start_ms=15000)
        _, kwargs = mock_build.call_args
        assert kwargs["start_seconds"] == 15.0
        assert kwargs["duration_seconds"] == 10.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_preview_cache.py -k "uses_start_ms_in_extract_command" -v`
Expected: FAIL because `play_stream()` does not accept `start_ms`

- [ ] **Step 3: Write minimal implementation**

```python
class AudioPlayerBar(QWidget):
    def play_stream(
        self,
        file_path: str,
        stream_index: int,
        display_name: str = "",
        *,
        start_ms: int = 0,
    ) -> str | None:
        ...
        cache_key = build_input_track_cache_key(file_path, stream_index, start_ms=start_ms)
        ...
        cmd = combat_audio.build_extract_command(
            file_path,
            stream_index,
            temp_path,
            start_seconds=start_ms / 1000.0,
            duration_seconds=10.0,
        )
        err = combat_audio.run_ffmpeg_command(cmd, timeout=30, default_message="输入音轨试听失败")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_preview_cache.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gui/components/audio_player.py src/gui/task_panels/combat_audio_panel.py tests/test_preview_cache.py
git commit -m "feat: support offset-based input track preview"
```

### Task 6: Use Preview Start In Mix Preview

**Files:**
- Modify: `src/gui/task_panels/combat_audio_panel.py`
- Modify: `src/core/preview_cache.py`
- Test: `tests/test_preview_cache.py`

- [ ] **Step 1: Write the failing tests for offset-based mix preview**

```python
def test_preview_mix_cache_key_changes_with_preview_start(tmp_path):
    input_file = tmp_path / "input.aac"
    bg_file = tmp_path / "bg.aac"
    input_file.write_bytes(b"in")
    bg_file.write_bytes(b"bg")
    key1 = build_mix_preview_cache_key(str(input_file), 0, str(bg_file), 0.6, start_ms=0)
    key2 = build_mix_preview_cache_key(str(input_file), 0, str(bg_file), 0.6, start_ms=5000)
    assert key1 != key2


def test_preview_mix_uses_start_ms_when_building_preview_command(...):
    ...
    assert kwargs["start_seconds"] == 15.0
    assert kwargs["duration_seconds"] == 10.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_preview_cache.py -k "preview_start" -v`
Expected: FAIL because preview mix still assumes start=0

- [ ] **Step 3: Write minimal implementation**

```python
class CombatAudioPanel(BaseTaskPanel):
    def preview_mix(self) -> None:
        ...
        preview_path = preview_cache.get_cache_path(
            build_mix_preview_cache_key(input_path, stream_idx, bg_path, volume, start_ms=self._preview_start_ms)
        )
        ...
        base_audio = preview_cache.get_cache_path(
            build_base_audio_cache_key(input_path, stream_idx, start_ms=self._preview_start_ms)
        )
        ...
        cmd = combat_audio.build_extract_command(
            input_path,
            stream_idx,
            base_audio,
            start_seconds=self._preview_start_ms / 1000.0,
            duration_seconds=10.0,
        )
        ...
        cmd = combat_audio.build_preview_command(
            base_audio,
            bg_path,
            volume,
            preview_path,
            start_seconds=self._preview_start_ms / 1000.0,
            duration_seconds=10.0,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_preview_cache.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gui/task_panels/combat_audio_panel.py src/core/preview_cache.py tests/test_preview_cache.py
git commit -m "feat: support offset-based mix preview"
```

### Task 7: End-to-End Verification

**Files:**
- Modify: `tests/test_preview_cache.py`
- Modify: `tests/test_combat_audio_processor.py`
- Modify: `tests/gui/components/test_preview_start_cell.py`

- [ ] **Step 1: Add final regression tests**

```python
def test_switching_input_file_resets_preview_start_to_zero(...):
    ...


def test_preview_start_cell_shows_zero_when_duration_invalid(...):
    ...
```

- [ ] **Step 2: Run the full targeted suite**

Run: `pytest tests/test_preview_cache.py tests/test_combat_audio_processor.py tests/test_combat_audio_config.py tests/gui/components/test_preview_start_cell.py -v`
Expected: PASS

- [ ] **Step 3: Run syntax verification**

Run: `python3 -m py_compile src/core/processors/combat_audio.py src/core/preview_cache.py src/gui/components/preview_start_cell.py src/gui/components/audio_player.py src/gui/task_panels/combat_audio_panel.py`
Expected: no output

- [ ] **Step 4: Manual smoke test**

Run: `python3 main.py`
Expected:
- Track table shows a `预览起点` column
- Only the selected track row’s slider is enabled
- Dragging the slider updates only the selected row interaction state and the displayed start time
- Input-track preview starts from the chosen offset and lasts about 10 seconds
- Mix preview starts from the same chosen offset and lasts about 10 seconds
- Repeating the same preview from the same offset is faster due to cache reuse

- [ ] **Step 5: Commit**

```bash
git add tests/test_preview_cache.py tests/test_combat_audio_processor.py tests/gui/components/test_preview_start_cell.py src/core/processors/combat_audio.py src/core/preview_cache.py src/gui/components/preview_start_cell.py src/gui/components/audio_player.py src/gui/task_panels/combat_audio_panel.py
git commit -m "feat: add row-level preview start slider"
```
