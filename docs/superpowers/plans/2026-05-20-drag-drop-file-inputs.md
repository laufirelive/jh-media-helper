# Drag Drop File Inputs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Finder drag-and-drop support to the main file inputs and副视频列表, while keeping media info compact enough that副视频 remains visible.

**Architecture:** Extend the existing `FileSelector` with opt-in single-path drop validation, then wire that capability into `PicSeqPanel` and `CombatAudioPanel`. Keep副视频 drag handling inside `CombatAudioPanel` because it owns the ordered `_secondary_video_paths` list. Limit the media info group height in the same panel without changing task config or processing logic.

**Tech Stack:** Python, PyQt6 widgets/events, pytest, pytest-qt.

---

## File Structure

- Modify `src/gui/components/file_selector.py`: add opt-in drag/drop validation for one local file or one local directory.
- Modify `tests/gui/components/test_file_selector.py`: add direct tests for drop-path validation without constructing native drag events.
- Modify `src/gui/task_panels/pic_seq_panel.py`: enable directory drops on the image sequence input selector.
- Modify `src/gui/task_panels/combat_audio_panel.py`: enable file/directory drops on input/audio/subtitle selectors, add副视频 list drop handling, and constrain the media info group height.
- Modify `tests/gui/task_panels/test_combat_audio_panel_preview_start.py`: cover selector configuration,副视频 drop helper behavior, and media info height constraints.

Do not modify core processors, queue persistence, FFmpeg/mkvmerge commands, or output path logic.

---

### Task 1: Add Opt-In Drop Validation To FileSelector

**Files:**
- Modify: `src/gui/components/file_selector.py`
- Test: `tests/gui/components/test_file_selector.py`

- [ ] **Step 1: Write failing FileSelector tests**

Append these tests to `tests/gui/components/test_file_selector.py`:

```python
def test_drop_disabled_by_default_rejects_path(qapp, tmp_path):
    folder = tmp_path / "seq"
    folder.mkdir()
    selector = FileSelector(label="Dir:")

    assert selector._resolve_drop_path([str(folder)]) is None


def test_directory_drop_accepts_single_directory(qapp, tmp_path):
    folder = tmp_path / "seq"
    folder.mkdir()
    selector = FileSelector(label="Dir:", drop_enabled=True, drop_kind="directory")

    assert selector._resolve_drop_path([str(folder)]) == str(folder)


def test_directory_drop_rejects_file(qapp, tmp_path):
    file_path = tmp_path / "frame.png"
    file_path.write_bytes(b"")
    selector = FileSelector(label="Dir:", drop_enabled=True, drop_kind="directory")

    assert selector._resolve_drop_path([str(file_path)]) is None


def test_file_drop_accepts_single_file(qapp, tmp_path):
    file_path = tmp_path / "clip.mkv"
    file_path.write_bytes(b"")
    selector = FileSelector(label="File:", drop_enabled=True, drop_kind="file")

    assert selector._resolve_drop_path([str(file_path)]) == str(file_path)


def test_file_drop_rejects_directory(qapp, tmp_path):
    folder = tmp_path / "audio"
    folder.mkdir()
    selector = FileSelector(label="File:", drop_enabled=True, drop_kind="file")

    assert selector._resolve_drop_path([str(folder)]) is None


def test_file_drop_filter_rejects_unlisted_extension(qapp, tmp_path):
    file_path = tmp_path / "notes.txt"
    file_path.write_text("not media")
    selector = FileSelector(
        label="File:",
        drop_enabled=True,
        drop_kind="file",
        drop_file_filter={".mkv", ".mp4"},
    )

    assert selector._resolve_drop_path([str(file_path)]) is None


def test_file_drop_filter_accepts_case_insensitive_extension(qapp, tmp_path):
    file_path = tmp_path / "CAPTION.SRT"
    file_path.write_text("1")
    selector = FileSelector(
        label="Subtitle:",
        drop_enabled=True,
        drop_kind="file",
        drop_file_filter={".srt", ".ass"},
    )

    assert selector._resolve_drop_path([str(file_path)]) == str(file_path)


def test_single_value_drop_rejects_multiple_paths(qapp, tmp_path):
    first = tmp_path / "one.mkv"
    second = tmp_path / "two.mkv"
    first.write_bytes(b"")
    second.write_bytes(b"")
    selector = FileSelector(label="File:", drop_enabled=True, drop_kind="file")
    selector.set_path("/existing.mkv")

    assert selector._resolve_drop_path([str(first), str(second)]) is None
    assert selector.path() == "/existing.mkv"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/gui/components/test_file_selector.py -q
```

Expected: FAIL because `FileSelector.__init__()` does not accept `drop_enabled`, and `_resolve_drop_path` does not exist.

- [ ] **Step 3: Implement FileSelector drop support**

Update imports in `src/gui/components/file_selector.py`:

```python
import os

from PyQt6.QtCore import pyqtSignal
```

Extend `FileSelector.__init__`:

```python
def __init__(
    self,
    label: str,
    placeholder: str = "",
    dialog_mode: str = "directory",
    file_filter: str = "",
    parent=None,
    *,
    drop_enabled: bool = False,
    drop_kind: str | None = None,
    drop_file_filter: set[str] | None = None,
):
    super().__init__(parent)
    self._dialog_mode = dialog_mode
    self._file_filter = file_filter
    self._drop_enabled = drop_enabled
    self._drop_kind = drop_kind
    self._drop_file_filter = {ext.lower() for ext in drop_file_filter or set()}
    self.setAcceptDrops(drop_enabled)
```

Add these methods to `FileSelector`:

```python
def _resolve_drop_path(self, paths: list[str]) -> str | None:
    if not self._drop_enabled or len(paths) != 1:
        return None
    path = paths[0]
    if self._drop_kind == "directory":
        return path if os.path.isdir(path) else None
    if self._drop_kind == "file":
        if not os.path.isfile(path):
            return None
        if self._drop_file_filter:
            ext = os.path.splitext(path)[1].lower()
            if ext not in self._drop_file_filter:
                return None
        return path
    return None

def dragEnterEvent(self, event):
    if not self.isEnabled() or not event.mimeData().hasUrls():
        event.ignore()
        return
    paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
    if self._resolve_drop_path(paths):
        event.acceptProposedAction()
    else:
        event.ignore()

def dropEvent(self, event):
    if not self.isEnabled() or not event.mimeData().hasUrls():
        event.ignore()
        return
    paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
    path = self._resolve_drop_path(paths)
    if path:
        self.set_path(path)
        event.acceptProposedAction()
    else:
        event.ignore()
```

- [ ] **Step 4: Run FileSelector tests**

Run:

```bash
.venv/bin/python -m pytest tests/gui/components/test_file_selector.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit FileSelector support**

```bash
git add src/gui/components/file_selector.py tests/gui/components/test_file_selector.py
git commit -m "feat: support drag drop file selectors"
```

---

### Task 2: Wire Drag Drop Into PicSeqPanel And CombatAudio Selectors

**Files:**
- Modify: `src/gui/task_panels/pic_seq_panel.py`
- Modify: `src/gui/task_panels/combat_audio_panel.py`
- Test: `tests/gui/task_panels/test_combat_audio_panel_preview_start.py`

- [ ] **Step 1: Write failing selector configuration tests**

Append these tests to `tests/gui/task_panels/test_combat_audio_panel_preview_start.py`:

```python
def test_combat_audio_file_selectors_enable_expected_drop_modes(panel):
    assert panel._input_selector._drop_enabled
    assert panel._input_selector._drop_kind == "file"
    assert ".mkv" in panel._input_selector._drop_file_filter

    assert panel._audio_dir_selector._drop_enabled
    assert panel._audio_dir_selector._drop_kind == "directory"

    assert panel._subtitle_selector._drop_enabled
    assert panel._subtitle_selector._drop_kind == "file"
    assert panel._subtitle_selector._drop_file_filter == {".srt", ".ass"}
```

Add this import near the top:

```python
from src.gui.task_panels.pic_seq_panel import PicSeqPanel
```

Append this test:

```python
def test_pic_seq_input_selector_accepts_directory_drop(qapp):
    class DummyRegistry:
        def get_best_hevc(self):
            return None

        def get_fallback(self):
            return "libx264"

    panel = PicSeqPanel(DummyRegistry())

    assert panel._input_selector._drop_enabled
    assert panel._input_selector._drop_kind == "directory"
```

- [ ] **Step 2: Run selector configuration tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/gui/task_panels/test_combat_audio_panel_preview_start.py::test_combat_audio_file_selectors_enable_expected_drop_modes tests/gui/task_panels/test_combat_audio_panel_preview_start.py::test_pic_seq_input_selector_accepts_directory_drop -q
```

Expected: FAIL because the selectors are not yet configured with drop options.

- [ ] **Step 3: Add extension constants and enable drops**

In `src/gui/task_panels/combat_audio_panel.py`, add constants after the filter strings:

```python
_MEDIA_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".aac", ".mp3", ".wav", ".flac"}
_SUBTITLE_EXTENSIONS = {".srt", ".ass"}
```

Update the three selector constructors:

```python
self._input_selector = FileSelector(
    label="输入视频/音频:",
    placeholder="选择文件...",
    dialog_mode="file",
    file_filter=_MEDIA_FILTER,
    drop_enabled=True,
    drop_kind="file",
    drop_file_filter=_MEDIA_EXTENSIONS,
)
```

```python
self._audio_dir_selector = FileSelector(
    label="音频目录:",
    placeholder="选择背景音乐文件夹...",
    dialog_mode="directory",
    drop_enabled=True,
    drop_kind="directory",
)
```

```python
self._subtitle_selector = FileSelector(
    label="字幕文件:",
    placeholder="可选，仅封装 MKV 时使用",
    dialog_mode="file",
    file_filter=_SUBTITLE_FILTER,
    drop_enabled=True,
    drop_kind="file",
    drop_file_filter=_SUBTITLE_EXTENSIONS,
)
```

In `src/gui/task_panels/pic_seq_panel.py`, update the image sequence input selector:

```python
self._input_selector = FileSelector(
    label="图片序列文件夹:",
    placeholder="选择文件夹...",
    dialog_mode="directory",
    drop_enabled=True,
    drop_kind="directory",
)
```

- [ ] **Step 4: Run selector configuration tests**

Run:

```bash
.venv/bin/python -m pytest tests/gui/task_panels/test_combat_audio_panel_preview_start.py::test_combat_audio_file_selectors_enable_expected_drop_modes tests/gui/task_panels/test_combat_audio_panel_preview_start.py::test_pic_seq_input_selector_accepts_directory_drop -q
```

Expected: PASS.

- [ ] **Step 5: Commit selector wiring**

```bash
git add src/gui/task_panels/pic_seq_panel.py src/gui/task_panels/combat_audio_panel.py tests/gui/task_panels/test_combat_audio_panel_preview_start.py
git commit -m "feat: enable drag drop on task inputs"
```

---

### Task 3: Add Drag Drop Append Behavior To Secondary Videos

**Files:**
- Modify: `src/gui/task_panels/combat_audio_panel.py`
- Test: `tests/gui/task_panels/test_combat_audio_panel_preview_start.py`

- [ ] **Step 1: Write failing副视频 helper tests**

Append these tests to `tests/gui/task_panels/test_combat_audio_panel_preview_start.py`:

```python
def test_secondary_video_drop_filters_and_appends_media_files(panel, tmp_path):
    first = tmp_path / "secondary-1.mkv"
    second = tmp_path / "secondary-2.MP4"
    ignored = tmp_path / "notes.txt"
    folder = tmp_path / "folder"
    first.write_bytes(b"")
    second.write_bytes(b"")
    ignored.write_text("not media")
    folder.mkdir()
    panel._secondary_video_paths = ["/existing.mkv"]

    panel._append_secondary_video_drop_paths([
        str(first),
        str(ignored),
        str(folder),
        str(second),
    ])

    assert panel._secondary_video_paths == [
        "/existing.mkv",
        str(first),
        str(second),
    ]


def test_secondary_video_drop_keeps_list_when_no_media_files(panel, tmp_path):
    ignored = tmp_path / "notes.txt"
    ignored.write_text("not media")
    panel._secondary_video_paths = ["/existing.mkv"]

    panel._append_secondary_video_drop_paths([str(ignored)])

    assert panel._secondary_video_paths == ["/existing.mkv"]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/gui/task_panels/test_combat_audio_panel_preview_start.py::test_secondary_video_drop_filters_and_appends_media_files tests/gui/task_panels/test_combat_audio_panel_preview_start.py::test_secondary_video_drop_keeps_list_when_no_media_files -q
```

Expected: FAIL because `_append_secondary_video_drop_paths` does not exist.

- [ ] **Step 3: Implement副视频 drop helpers and events**

In `_build_secondary_video_group`, after creating `_secondary_group`, enable drops:

```python
self._secondary_group.setAcceptDrops(True)
```

Add methods to `CombatAudioPanel` near `_add_secondary_video`:

```python
def _filter_secondary_video_drop_paths(self, paths: list[str]) -> list[str]:
    valid_paths: list[str] = []
    for path in paths:
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(path)[1].lower()
        if ext in _MEDIA_EXTENSIONS:
            valid_paths.append(path)
    return valid_paths

def _append_secondary_video_drop_paths(self, paths: list[str]) -> None:
    valid_paths = self._filter_secondary_video_drop_paths(paths)
    if not valid_paths:
        return
    self._secondary_video_paths.extend(valid_paths)
    self._refresh_secondary_videos()

def dragEnterEvent(self, event):
    if not self._secondary_group.isEnabled() or not event.mimeData().hasUrls():
        event.ignore()
        return
    paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
    if self._filter_secondary_video_drop_paths(paths):
        event.acceptProposedAction()
    else:
        event.ignore()

def dropEvent(self, event):
    if not self._secondary_group.isEnabled() or not event.mimeData().hasUrls():
        event.ignore()
        return
    paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
    before = list(self._secondary_video_paths)
    self._append_secondary_video_drop_paths(paths)
    if self._secondary_video_paths != before:
        event.acceptProposedAction()
    else:
        event.ignore()
```

Note: This accepts drops at the panel level. If testing shows child widgets consume the event first, move the same handlers to a small `QGroupBox` subclass or install an event filter on `_secondary_group`; keep the helper methods unchanged.

- [ ] **Step 4: Run副视频 tests**

Run:

```bash
.venv/bin/python -m pytest tests/gui/task_panels/test_combat_audio_panel_preview_start.py::test_secondary_video_drop_filters_and_appends_media_files tests/gui/task_panels/test_combat_audio_panel_preview_start.py::test_secondary_video_drop_keeps_list_when_no_media_files -q
```

Expected: PASS.

- [ ] **Step 5: Commit副视频 drop support**

```bash
git add src/gui/task_panels/combat_audio_panel.py tests/gui/task_panels/test_combat_audio_panel_preview_start.py
git commit -m "feat: support secondary video drag drop"
```

---

### Task 4: Constrain Combat Audio Media Info Height

**Files:**
- Modify: `src/gui/task_panels/combat_audio_panel.py`
- Test: `tests/gui/task_panels/test_combat_audio_panel_preview_start.py`

- [ ] **Step 1: Write failing layout test**

Append this test to `tests/gui/task_panels/test_combat_audio_panel_preview_start.py`:

```python
def test_file_info_group_has_height_limit_so_secondary_group_remains_visible(panel):
    assert panel._info_group.maximumHeight() > 0
    assert panel._info_group.maximumHeight() <= 130
    assert panel._info_label.wordWrap()
```

- [ ] **Step 2: Run layout test and verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/gui/task_panels/test_combat_audio_panel_preview_start.py::test_file_info_group_has_height_limit_so_secondary_group_remains_visible -q
```

Expected: FAIL because `_info_group.maximumHeight()` is not constrained.

- [ ] **Step 3: Add compact height constraint**

In `src/gui/task_panels/combat_audio_panel.py`, inside `_build_upper_left` after `_info_label.setWordWrap(True)`, add:

```python
self._info_group.setMaximumHeight(120)
self._info_group.setSizePolicy(
    QSizePolicy.Policy.Preferred,
    QSizePolicy.Policy.Maximum,
)
```

In `_sync_file_info_height`, prevent the right-side alignment code from overriding the maximum. Replace:

```python
if h > 0:
    ig.setFixedHeight(h)
```

with:

```python
if h > 0:
    ig.setFixedHeight(min(h, ig.maximumHeight()))
```

- [ ] **Step 4: Run layout test**

Run:

```bash
.venv/bin/python -m pytest tests/gui/task_panels/test_combat_audio_panel_preview_start.py::test_file_info_group_has_height_limit_so_secondary_group_remains_visible -q
```

Expected: PASS.

- [ ] **Step 5: Commit layout fix**

```bash
git add src/gui/task_panels/combat_audio_panel.py tests/gui/task_panels/test_combat_audio_panel_preview_start.py
git commit -m "fix: keep media info panel compact"
```

---

### Task 5: Final Verification

**Files:**
- Verify all changed files.

- [ ] **Step 1: Run focused GUI tests**

Run:

```bash
.venv/bin/python -m pytest tests/gui/components/test_file_selector.py tests/gui/task_panels/test_combat_audio_panel_preview_start.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: PASS.

- [ ] **Step 3: Manual smoke test**

Run:

```bash
.venv/bin/python main.py
```

Verify in the GUI:

- Drag one folder onto“图片序列文件夹”; the file info updates.
- Drag multiple files onto“输入视频/音频”; the existing value does not change.
- Drag one media file onto“输入视频/音频”; the path updates.
- Drag one folder onto“音频目录”; the audio list refreshes.
- Enable MKV boxing, then drag `.srt` or `.ass` onto“字幕文件”; the path updates.
- Enable副视频, then drag two media files onto副视频区域; both append in order.
- The“文件信息” box stays compact and does not cover副视频.

- [ ] **Step 4: Final commit if verification required changes**

If Task 5 required code or test changes, commit them:

```bash
git add src/gui/components/file_selector.py src/gui/task_panels/pic_seq_panel.py src/gui/task_panels/combat_audio_panel.py tests/gui/components/test_file_selector.py tests/gui/task_panels/test_combat_audio_panel_preview_start.py
git commit -m "test: verify drag drop file inputs"
```

If no files changed during Task 5, do not create an empty commit.

---

## Self-Review

- Spec coverage: single-path fields reject multiple paths in Task 1; PicSeq input, media input, audio directory, and subtitle selector wiring are in Task 2;副视频 multi-file append is in Task 3; media info height constraint is in Task 4; final GUI smoke testing is in Task 5.
- Placeholder scan: the plan contains no TBD/TODO placeholders.
- Type consistency: `drop_enabled`, `drop_kind`, `drop_file_filter`, `_resolve_drop_path`, `_filter_secondary_video_drop_paths`, and `_append_secondary_video_drop_paths` are introduced before use.
