# Preview Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add session-scoped preview caching for the CombatAudio tab so repeated input-track previews and mix previews reuse ffmpeg outputs within one app run and are cleaned up on exit.

**Architecture:** Introduce a small preview-cache module under `src/core` to manage `~/.jh-media-helper/cache/preview/<session_id>/`, hashed cache keys, and cleanup. Wire `MainWindow` to own the session lifecycle, then update `AudioPlayerBar` and `CombatAudioPanel` to resolve cached preview paths before invoking ffmpeg.

**Tech Stack:** Python 3, PyQt6, ffmpeg/ffprobe, pytest, hashlib, pathlib/os/shutil

---

### Task 1: Add Preview Cache Module

**Files:**
- Create: `src/core/preview_cache.py`
- Test: `tests/test_preview_cache.py`

- [ ] **Step 1: Write the failing tests for session lifecycle and cache path generation**

```python
import os

from src.core.preview_cache import PreviewCacheSession


def test_start_cleans_old_preview_sessions(tmp_path):
    root = tmp_path / "cache" / "preview"
    old_dir = root / "old-session"
    old_dir.mkdir(parents=True)
    (old_dir / "old.aac").write_text("stale")

    session = PreviewCacheSession(root_dir=str(root))
    session.start()

    assert os.path.isdir(session.session_dir)
    assert os.path.basename(session.session_dir) != "old-session"
    assert not old_dir.exists()


def test_cache_path_uses_stable_hash_name(tmp_path):
    root = tmp_path / "cache" / "preview"
    session = PreviewCacheSession(root_dir=str(root))
    session.start()

    path1 = session.get_cache_path("kind=input_track|input=/a.mp4|stream=0|version=v1")
    path2 = session.get_cache_path("kind=input_track|input=/a.mp4|stream=0|version=v1")

    assert path1 == path2
    assert path1.endswith(".aac")
    assert os.path.dirname(path1) == session.session_dir


def test_cleanup_removes_current_session_only(tmp_path):
    root = tmp_path / "cache" / "preview"
    session = PreviewCacheSession(root_dir=str(root))
    session.start()
    current_dir = session.session_dir
    keep_dir = root / "keep-me"
    keep_dir.mkdir(parents=True)

    session.cleanup()

    assert not os.path.exists(current_dir)
    assert keep_dir.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_preview_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.preview_cache'`

- [ ] **Step 3: Write minimal preview cache implementation**

```python
# src/core/preview_cache.py
import hashlib
import os
import shutil
import uuid

from src.core.data_dir import resolve_data_dir


class PreviewCacheSession:
    def __init__(self, root_dir: str | None = None):
        base = root_dir or os.path.join(resolve_data_dir(), "cache", "preview")
        self._root_dir = base
        self._session_dir: str | None = None

    @property
    def session_dir(self) -> str:
        if self._session_dir is None:
            raise RuntimeError("Preview cache session not started")
        return self._session_dir

    def start(self) -> str:
        os.makedirs(self._root_dir, exist_ok=True)
        for name in os.listdir(self._root_dir):
            path = os.path.join(self._root_dir, name)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
        self._session_dir = os.path.join(self._root_dir, uuid.uuid4().hex)
        os.makedirs(self._session_dir, exist_ok=True)
        return self._session_dir

    def get_cache_path(self, cache_key: str, suffix: str = ".aac") -> str:
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return os.path.join(self.session_dir, f"{digest}{suffix}")

    def cleanup(self) -> None:
        if self._session_dir and os.path.isdir(self._session_dir):
            shutil.rmtree(self._session_dir, ignore_errors=True)
            self._session_dir = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_preview_cache.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/preview_cache.py tests/test_preview_cache.py
git commit -m "feat: add session-scoped preview cache manager"
```

### Task 2: Wire Preview Cache Session Into MainWindow Lifecycle

**Files:**
- Modify: `src/gui/main_window.py`
- Test: `tests/test_preview_cache.py`

- [ ] **Step 1: Add a failing test for startup and shutdown lifecycle**

```python
from unittest.mock import Mock

from src.gui.main_window import MainWindow


def test_main_window_starts_and_cleans_preview_cache(monkeypatch, qapp):
    fake_cache = Mock()
    monkeypatch.setattr("src.gui.main_window.PreviewCacheSession", lambda: fake_cache)

    window = MainWindow()
    assert fake_cache.start.call_count == 1

    class DummyEvent:
        def accept(self):
            self.accepted = True

    event = DummyEvent()
    window.closeEvent(event)

    assert fake_cache.cleanup.call_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_preview_cache.py::test_main_window_starts_and_cleans_preview_cache -v`
Expected: FAIL because `MainWindow` does not create or clean a preview cache session

- [ ] **Step 3: Inject preview cache session into MainWindow**

```python
# src/gui/main_window.py
from src.core.preview_cache import PreviewCacheSession


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._preview_cache = PreviewCacheSession()
        self._preview_cache.start()
        ...
        self._combat_panel = CombatAudioPanel(preview_cache=self._preview_cache)
        ...

    def closeEvent(self, event):
        if self._worker:
            self._worker.cancel()
            self._worker.wait(3000)
        self._queue_tab.stop()
        self._queue_manager.save()
        self._combat_panel.cleanup()
        self._preview_cache.cleanup()
        event.accept()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_preview_cache.py::test_main_window_starts_and_cleans_preview_cache -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gui/main_window.py tests/test_preview_cache.py
git commit -m "feat: manage preview cache session in main window"
```

### Task 3: Cache Input Track Preview Extractions

**Files:**
- Modify: `src/gui/components/audio_player.py`
- Modify: `src/core/preview_cache.py`
- Test: `tests/test_preview_cache.py`

- [ ] **Step 1: Write the failing tests for cache hit and miss behavior**

```python
from unittest.mock import patch

from src.core.preview_cache import PreviewCacheSession, build_input_track_cache_key


def test_build_input_track_cache_key_is_stable():
    key1 = build_input_track_cache_key("/tmp/a.mp4", 0)
    key2 = build_input_track_cache_key("/tmp/a.mp4", 0)
    key3 = build_input_track_cache_key("/tmp/a.mp4", 1)
    assert key1 == key2
    assert key1 != key3


@patch("src.gui.components.audio_player.combat_audio.run_ffmpeg_command")
def test_play_stream_uses_cached_file_when_present(mock_run, tmp_path, qapp):
    from src.gui.components.audio_player import AudioPlayerBar

    session = PreviewCacheSession(root_dir=str(tmp_path / "preview"))
    session.start()
    cache_path = session.get_cache_path(build_input_track_cache_key("/tmp/a.mp4", 0))
    with open(cache_path, "wb") as f:
        f.write(b"cached")

    player = AudioPlayerBar(preview_cache=session)
    player.play_file = lambda file_path, display_name="": setattr(player, "_played_path", file_path)

    err = player.play_stream("/tmp/a.mp4", 0, "输入 #1 AAC")

    assert err is None
    assert player._played_path == cache_path
    mock_run.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_preview_cache.py::test_play_stream_uses_cached_file_when_present -v`
Expected: FAIL because `AudioPlayerBar` does not accept a preview cache or look up cached files

- [ ] **Step 3: Implement cache-key helper and AudioPlayerBar integration**

```python
# src/core/preview_cache.py
def build_input_track_cache_key(input_path: str, audio_position: int) -> str:
    return "|".join([
        "kind=input_track",
        f"input={input_path}",
        f"stream={audio_position}",
        "version=v1",
    ])


# src/gui/components/audio_player.py
from src.core.preview_cache import PreviewCacheSession, build_input_track_cache_key


class AudioPlayerBar(QWidget):
    def __init__(self, parent=None, preview_cache: PreviewCacheSession | None = None):
        super().__init__(parent)
        self._preview_cache = preview_cache
        ...

    def play_stream(self, file_path: str, stream_index: int, display_name: str = "") -> str | None:
        self.stop()
        cache_path = None
        if self._preview_cache is not None:
            key = build_input_track_cache_key(file_path, stream_index)
            cache_path = self._preview_cache.get_cache_path(key)
            if os.path.isfile(cache_path):
                self.play_file(cache_path, display_name)
                return None

        temp_path = cache_path or os.path.join(self._temp_dir, f"stream_{stream_index}.aac")
        ...
```

- [ ] **Step 4: Run the focused tests**

Run: `pytest tests/test_preview_cache.py -k "input_track_cache_key or play_stream_uses_cached_file_when_present" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/preview_cache.py src/gui/components/audio_player.py tests/test_preview_cache.py
git commit -m "feat: cache extracted input track previews"
```

### Task 4: Cache Base Audio and Mix Preview Outputs

**Files:**
- Modify: `src/core/preview_cache.py`
- Modify: `src/gui/task_panels/combat_audio_panel.py`
- Test: `tests/test_preview_cache.py`

- [ ] **Step 1: Write the failing tests for mix-preview cache semantics**

```python
from src.core.preview_cache import (
    build_base_audio_cache_key,
    build_mix_preview_cache_key,
)


def test_mix_preview_key_changes_with_bgm_or_volume():
    key1 = build_mix_preview_cache_key("/tmp/in.mp4", 0, "/tmp/a.aac", 0.6)
    key2 = build_mix_preview_cache_key("/tmp/in.mp4", 0, "/tmp/b.aac", 0.6)
    key3 = build_mix_preview_cache_key("/tmp/in.mp4", 0, "/tmp/a.aac", 0.8)
    assert key1 != key2
    assert key1 != key3


def test_base_audio_key_reuses_same_input_stream():
    key1 = build_base_audio_cache_key("/tmp/in.mp4", 0)
    key2 = build_base_audio_cache_key("/tmp/in.mp4", 0)
    assert key1 == key2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_preview_cache.py -k "mix_preview_key_changes_with_bgm_or_volume or base_audio_key_reuses_same_input_stream" -v`
Expected: FAIL because base-audio and mix-preview key builders do not exist

- [ ] **Step 3: Implement cache lookup in CombatAudioPanel**

```python
# src/core/preview_cache.py
def build_base_audio_cache_key(input_path: str, audio_position: int) -> str:
    return "|".join([
        "kind=base_audio",
        f"input={input_path}",
        f"stream={audio_position}",
        "version=v1",
    ])


def build_mix_preview_cache_key(input_path: str, audio_position: int, bg_path: str, volume: float) -> str:
    return "|".join([
        "kind=mix_preview",
        f"input={input_path}",
        f"stream={audio_position}",
        f"bg={bg_path}",
        f"volume={volume:.3f}",
        "version=v1",
    ])


# src/gui/task_panels/combat_audio_panel.py
from src.core.preview_cache import (
    PreviewCacheSession,
    build_base_audio_cache_key,
    build_mix_preview_cache_key,
)


class CombatAudioPanel(BaseTaskPanel):
    def __init__(self, preview_cache: PreviewCacheSession | None = None, parent=None):
        self._preview_cache = preview_cache
        ...

    def _build_middle_zone(self, parent_layout: QVBoxLayout):
        ...
        self._player = AudioPlayerBar(preview_cache=self._preview_cache)
        ...

    def preview_mix(self) -> None:
        ...
        mix_path = None
        if self._preview_cache is not None:
            mix_key = build_mix_preview_cache_key(input_path, stream_idx, bg_path, volume)
            mix_path = self._preview_cache.get_cache_path(mix_key)
            if os.path.isfile(mix_path):
                self._player.play_file(mix_path, "试听混合")
                return

        if not self._is_pure_audio:
            if self._preview_cache is not None:
                base_key = build_base_audio_cache_key(input_path, stream_idx)
                base_audio = self._preview_cache.get_cache_path(base_key)
            else:
                base_audio = os.path.join(self._preview_temp_dir, "base.aac")
            ...

        preview_path = mix_path or os.path.join(self._preview_temp_dir, "preview.aac")
        ...
```

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_preview_cache.py -k "mix_preview or base_audio" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/preview_cache.py src/gui/task_panels/combat_audio_panel.py tests/test_preview_cache.py
git commit -m "feat: cache base audio and mix preview outputs"
```

### Task 5: End-to-End Verification and Cleanup

**Files:**
- Modify: `tests/test_preview_cache.py`
- Modify: `src/gui/components/audio_player.py`
- Modify: `src/gui/task_panels/combat_audio_panel.py`

- [ ] **Step 1: Add regression tests for cache fallback and cleanup**

```python
@patch("src.gui.components.audio_player.combat_audio.run_ffmpeg_command")
def test_play_stream_regenerates_when_cached_file_missing(mock_run, tmp_path, qapp):
    from src.gui.components.audio_player import AudioPlayerBar
    from src.core.preview_cache import PreviewCacheSession

    session = PreviewCacheSession(root_dir=str(tmp_path / "preview"))
    session.start()
    mock_run.return_value = None

    player = AudioPlayerBar(preview_cache=session)
    player.play_file = lambda file_path, display_name="": None

    err = player.play_stream("/tmp/a.mp4", 0, "输入 #1 AAC")

    assert err is None
    assert mock_run.call_count == 1
```

- [ ] **Step 2: Run the complete targeted suite**

Run: `pytest tests/test_preview_cache.py tests/test_combat_audio_processor.py tests/test_combat_audio_config.py -v`
Expected: PASS

- [ ] **Step 3: Run syntax verification**

Run: `python3 -m py_compile src/core/preview_cache.py src/gui/main_window.py src/gui/components/audio_player.py src/gui/task_panels/combat_audio_panel.py`
Expected: no output

- [ ] **Step 4: Do a quick manual smoke test**

Run: `python3 main.py`
Expected:
- App opens normally
- First click on an input video track incurs extraction delay
- Second click on the same track replays quickly
- First click on the same mix preview generates audio
- Second click on the same mix preview replays quickly
- Closing the app removes the current preview session directory

- [ ] **Step 5: Commit**

```bash
git add tests/test_preview_cache.py src/core/preview_cache.py src/gui/main_window.py src/gui/components/audio_player.py src/gui/task_panels/combat_audio_panel.py
git commit -m "feat: add session-scoped preview caching"
```
