# Combat Audio mkvmerge and Secondary Videos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable `mkvmerge` MKV muxing, readable AAC output names, and multi-part secondary-video MKV output to the existing combat audio workflow.

**Architecture:** Keep the feature inside the existing combat audio task. Add small focused core helpers for app settings, external tool resolution, output naming, and mux command construction; then wire those helpers into the existing worker and PyQt panels. The audio adjustment/mixing pipeline still runs once from the main input; the final mux phase iterates over `[main_video] + secondary_video_paths`.

**Tech Stack:** Python 3.12, PyQt6, FFmpeg/FFprobe, optional MKVToolNix `mkvmerge`, pytest, pytest-qt.

---

## File Structure

- Create `src/core/app_settings.py`
  - Owns `AppSettings`, `load_settings()`, `save_settings()`, and backwards-compatible JSON handling for `~/.jh-media-helper/settings.json`.
- Create `src/core/external_tools.py`
  - Owns `MuxBackend`, `resolve_mkvmerge_path()`, and `resolve_mux_backend()`.
- Modify `src/core/config.py`
  - Extends `CombatAudioConfig` with `secondary_video_paths`, `mkvmerge_path`, and `mux_backend`.
- Modify `src/core/processors/combat_audio.py`
  - Adds filename sanitization, named output path resolution, secondary-video validation helpers, `mkvmerge` command building, and multi-part MKV output path resolution.
- Modify `src/worker/ffmpeg_worker.py`
  - Keeps final audio generation single-pass and expands mux phase to loop over main plus secondary videos. Chooses `mkvmerge` when available, otherwise FFmpeg.
- Modify `src/gui/settings_tab.py`
  - Adds “外部工具” group for `mkvmerge` path, auto-detect, choose, status, save.
- Modify `src/gui/task_panels/combat_audio_panel.py`
  - Adds compact secondary-video list UI and includes secondary videos plus mux settings in built config.
- Modify `src/gui/main_window.py`
  - Supplies current settings to `CombatAudioPanel` before direct start/enqueue, or exposes a settings provider callback.
- Modify `src/gui/queue_tab.py`
  - Counts multi-part outputs for queue display and preserves compatibility with old task configs.
- Tests:
  - `tests/test_app_settings.py`
  - `tests/test_external_tools.py`
  - Existing `tests/test_combat_audio_config.py`
  - Existing `tests/test_combat_audio_processor.py`
  - Existing `tests/test_ffmpeg_worker.py`
  - Existing GUI tests under `tests/gui/`

## Preflight

- [ ] **Step 1: Confirm current worktree state**

Run:

```bash
git status --short
```

Expected: existing unrelated local edits may appear in:

```text
 M src/core/processors/combat_audio.py
 M src/worker/ffmpeg_worker.py
 M tests/test_combat_audio_processor.py
 M tests/test_ffmpeg_worker.py
```

Do not include those unrelated edits in feature commits unless the user explicitly says to keep them.

- [ ] **Step 2: Preserve unrelated local edits before implementation**

Run:

```bash
git stash push -m "pre-mkvmerge-secondary-videos local edits"
```

Expected: worktree becomes clean except committed docs.

- [ ] **Step 3: Create implementation branch**

Run:

```bash
git switch -c feat/combat-audio-mkvmerge-secondary-videos
```

Expected: branch created from current `master`.

---

### Task 1: Add App Settings Persistence

**Files:**
- Create: `src/core/app_settings.py`
- Test: `tests/test_app_settings.py`

- [ ] **Step 1: Write failing tests for settings defaults and round trip**

Create `tests/test_app_settings.py`:

```python
import json

from src.core.app_settings import AppSettings, load_settings, save_settings


def test_app_settings_defaults():
    settings = AppSettings()

    assert settings.mkvmerge_path is None


def test_app_settings_round_trip(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings = AppSettings(mkvmerge_path="/opt/bin/mkvmerge")

    save_settings(settings, path=str(settings_path))
    restored = load_settings(path=str(settings_path))

    assert restored == settings


def test_load_settings_returns_defaults_when_file_missing(tmp_path):
    settings_path = tmp_path / "missing.json"

    settings = load_settings(path=str(settings_path))

    assert settings == AppSettings()


def test_load_settings_ignores_unknown_keys(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"mkvmerge_path": "/bin/mkvmerge", "unknown": "ignored"}),
        encoding="utf-8",
    )

    settings = load_settings(path=str(settings_path))

    assert settings == AppSettings(mkvmerge_path="/bin/mkvmerge")


def test_load_settings_treats_empty_mkvmerge_path_as_none(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"mkvmerge_path": ""}), encoding="utf-8")

    settings = load_settings(path=str(settings_path))

    assert settings == AppSettings(mkvmerge_path=None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_app_settings.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.app_settings'`.

- [ ] **Step 3: Implement app settings module**

Create `src/core/app_settings.py`:

```python
import json
import os
from dataclasses import dataclass

from src.core.data_dir import get_settings_path


@dataclass
class AppSettings:
    mkvmerge_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "mkvmerge_path": self.mkvmerge_path or "",
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        raw_path = data.get("mkvmerge_path") or None
        return cls(mkvmerge_path=raw_path)


def load_settings(*, path: str | None = None) -> AppSettings:
    settings_path = path or get_settings_path()
    if not os.path.exists(settings_path):
        return AppSettings()
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return AppSettings()
    if not isinstance(data, dict):
        return AppSettings()
    return AppSettings.from_dict(data)


def save_settings(settings: AppSettings, *, path: str | None = None) -> None:
    settings_path = path or get_settings_path()
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings.to_dict(), f, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_app_settings.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/core/app_settings.py tests/test_app_settings.py
git commit -m "feat: add app settings persistence"
```

Expected: commit created.

---

### Task 2: Add mkvmerge Tool Resolution

**Files:**
- Create: `src/core/external_tools.py`
- Test: `tests/test_external_tools.py`

- [ ] **Step 1: Write failing tests for mkvmerge resolution**

Create `tests/test_external_tools.py`:

```python
import os

from src.core.external_tools import MuxBackend, resolve_mkvmerge_path, resolve_mux_backend


def test_resolve_mkvmerge_path_prefers_valid_manual_path(monkeypatch, tmp_path):
    tool = tmp_path / "mkvmerge"
    tool.write_text("#!/bin/sh\n", encoding="utf-8")
    tool.chmod(0o755)
    monkeypatch.setattr("src.core.external_tools.shutil.which", lambda name: None)

    assert resolve_mkvmerge_path(str(tool)) == str(tool)


def test_resolve_mkvmerge_path_falls_back_to_path_when_manual_invalid(monkeypatch):
    monkeypatch.setattr("src.core.external_tools.shutil.which", lambda name: "/usr/bin/mkvmerge")

    assert resolve_mkvmerge_path("/missing/mkvmerge") == "/usr/bin/mkvmerge"


def test_resolve_mkvmerge_path_returns_none_when_not_found(monkeypatch):
    monkeypatch.setattr("src.core.external_tools.shutil.which", lambda name: None)

    assert resolve_mkvmerge_path(None) is None


def test_resolve_mux_backend_uses_mkvmerge_when_available(monkeypatch):
    monkeypatch.setattr("src.core.external_tools.resolve_mkvmerge_path", lambda path: "/usr/bin/mkvmerge")

    backend, path = resolve_mux_backend("auto", None)

    assert backend == MuxBackend.MKVMERGE
    assert path == "/usr/bin/mkvmerge"


def test_resolve_mux_backend_falls_back_to_ffmpeg(monkeypatch):
    monkeypatch.setattr("src.core.external_tools.resolve_mkvmerge_path", lambda path: None)

    backend, path = resolve_mux_backend("auto", None)

    assert backend == MuxBackend.FFMPEG
    assert path is None


def test_manual_path_must_be_executable(tmp_path, monkeypatch):
    tool = tmp_path / "mkvmerge"
    tool.write_text("", encoding="utf-8")
    tool.chmod(0o644)
    monkeypatch.setattr("src.core.external_tools.shutil.which", lambda name: None)

    assert resolve_mkvmerge_path(str(tool)) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_external_tools.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.external_tools'`.

- [ ] **Step 3: Implement external tool resolution**

Create `src/core/external_tools.py`:

```python
import os
import shutil
from enum import Enum


class MuxBackend(Enum):
    MKVMERGE = "mkvmerge"
    FFMPEG = "ffmpeg"


def _is_executable_file(path: str | None) -> bool:
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def resolve_mkvmerge_path(manual_path: str | None = None) -> str | None:
    if _is_executable_file(manual_path):
        return manual_path
    detected = shutil.which("mkvmerge")
    if _is_executable_file(detected):
        return detected
    return None


def resolve_mux_backend(requested: str = "auto", mkvmerge_path: str | None = None) -> tuple[MuxBackend, str | None]:
    resolved_mkvmerge = resolve_mkvmerge_path(mkvmerge_path)
    if requested == MuxBackend.MKVMERGE.value and resolved_mkvmerge:
        return MuxBackend.MKVMERGE, resolved_mkvmerge
    if requested == MuxBackend.FFMPEG.value:
        return MuxBackend.FFMPEG, None
    if resolved_mkvmerge:
        return MuxBackend.MKVMERGE, resolved_mkvmerge
    return MuxBackend.FFMPEG, None
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_external_tools.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/core/external_tools.py tests/test_external_tools.py
git commit -m "feat: resolve mkvmerge mux backend"
```

Expected: commit created.

---

### Task 3: Extend Combat Audio Config

**Files:**
- Modify: `src/core/config.py`
- Test: `tests/test_combat_audio_config.py`

- [ ] **Step 1: Write failing tests for new config fields**

Append to `tests/test_combat_audio_config.py`:

```python
def test_combat_audio_config_mkvmerge_secondary_video_defaults():
    cfg = CombatAudioConfig(input_path="/tmp/video.mkv", audio_dir="/tmp/audio")

    assert cfg.secondary_video_paths == []
    assert cfg.mkvmerge_path is None
    assert cfg.mux_backend == "auto"


def test_combat_audio_config_mkvmerge_secondary_video_round_trip():
    cfg = CombatAudioConfig(
        input_path="/tmp/video.mkv",
        audio_dir="/tmp/audio",
        secondary_video_paths=["/tmp/part2.mp4", "/tmp/part3.mp4"],
        mkvmerge_path="/opt/bin/mkvmerge",
        mux_backend="auto",
    )

    restored = CombatAudioConfig.from_dict(cfg.to_dict())

    assert restored.secondary_video_paths == cfg.secondary_video_paths
    assert restored.mkvmerge_path == "/opt/bin/mkvmerge"
    assert restored.mux_backend == "auto"


def test_combat_audio_config_old_dict_defaults_new_fields():
    restored = CombatAudioConfig.from_dict({
        "input_path": "/tmp/video.mkv",
        "audio_dir": "/tmp/audio",
    })

    assert restored.secondary_video_paths == []
    assert restored.mkvmerge_path is None
    assert restored.mux_backend == "auto"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_combat_audio_config.py -q
```

Expected: FAIL with `AttributeError: 'CombatAudioConfig' object has no attribute 'secondary_video_paths'`.

- [ ] **Step 3: Update `CombatAudioConfig`**

Modify `src/core/config.py`:

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

    def __post_init__(self):
        if self.audio_order is None:
            self.audio_order = []
        if self.secondary_video_paths is None:
            self.secondary_video_paths = []

    def to_dict(self) -> dict:
        return {
            "input_path": self.input_path,
            "audio_dir": self.audio_dir,
            "output_dir": self.output_dir,
            "mix_enabled": self.mix_enabled,
            "volume": self.volume,
            "boxed": self.boxed,
            "thread_count": self.thread_count,
            "audio_stream_index": self.audio_stream_index,
            "audio_order": self.audio_order,
            "secondary_video_paths": self.secondary_video_paths,
            "mkvmerge_path": self.mkvmerge_path,
            "mux_backend": self.mux_backend,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CombatAudioConfig":
        return cls(
            input_path=d["input_path"],
            audio_dir=d["audio_dir"],
            output_dir=d.get("output_dir"),
            mix_enabled=d.get("mix_enabled", True),
            volume=d.get("volume", 0.6),
            boxed=d.get("boxed", False),
            thread_count=d.get("thread_count", 1),
            audio_stream_index=d.get("audio_stream_index", 0),
            audio_order=d.get("audio_order", []),
            secondary_video_paths=d.get("secondary_video_paths", []),
            mkvmerge_path=d.get("mkvmerge_path"),
            mux_backend=d.get("mux_backend", "auto"),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_combat_audio_config.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/core/config.py tests/test_combat_audio_config.py
git commit -m "feat: extend combat audio config for mkv parts"
```

Expected: commit created.

---

### Task 4: Add Output Naming Helpers

**Files:**
- Modify: `src/core/processors/combat_audio.py`
- Test: `tests/test_combat_audio_processor.py`

- [ ] **Step 1: Write failing tests for safe audio names and multi-part paths**

Add imports in `tests/test_combat_audio_processor.py`:

```python
from src.core.processors.combat_audio import (
    # existing imports...
    resolve_mkv_output_paths,
    sanitize_output_stem,
)
```

Add tests:

```python
class TestSanitizeOutputStem:
    def test_replaces_cross_platform_illegal_characters(self):
        assert sanitize_output_stem('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"

    def test_uses_audio_for_empty_result(self):
        assert sanitize_output_stem("////") == "audio"

    def test_strips_extension_and_compresses_spaces(self):
        assert sanitize_output_stem("  my   song .mp3") == "my song"


class TestNamedAudioOutputPaths:
    def test_non_boxed_outputs_include_original_background_name(self):
        with tempfile.TemporaryDirectory() as d, patch(
            "src.core.processors.combat_audio.time.strftime",
            return_value="20260507190000",
        ):
            cfg = CombatAudioConfig(
                input_path=os.path.join(d, "episode_01.mkv"),
                audio_dir="/audio",
                output_dir=os.path.join(d, "out"),
                mix_enabled=True,
                boxed=False,
            )

            paths = resolve_output_path(cfg, 2, audio_filenames=["bg one.mp3", "bad/name.aac"])

            assert paths[0].endswith("episode_01_mixed_20260507190000/01_bg one_mixed.aac")
            assert paths[1].endswith("episode_01_mixed_20260507190000/02_name_mixed.aac")


class TestResolveMkvOutputPaths:
    def test_single_mkv_keeps_existing_name_when_no_secondary_videos(self):
        with tempfile.TemporaryDirectory() as d, patch(
            "src.core.processors.combat_audio.time.strftime",
            return_value="20260507190000",
        ):
            cfg = CombatAudioConfig(input_path=os.path.join(d, "main.mkv"), audio_dir="/audio", boxed=True)

            paths = resolve_mkv_output_paths(cfg, timestamp=None)

            assert paths == [os.path.join(d, "main_20260507190000.mkv")]

    def test_secondary_videos_use_part_suffixes_and_same_timestamp(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = CombatAudioConfig(
                input_path=os.path.join(d, "main.mkv"),
                audio_dir="/audio",
                output_dir=os.path.join(d, "out"),
                boxed=True,
                secondary_video_paths=["/video/part2.mp4", "/video/part3.mp4"],
            )

            paths = resolve_mkv_output_paths(cfg, timestamp="20260507190000")

            assert paths == [
                os.path.join(d, "out", "main_20260507190000-part1.mkv"),
                os.path.join(d, "out", "main_20260507190000-part2.mkv"),
                os.path.join(d, "out", "main_20260507190000-part3.mkv"),
            ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_combat_audio_processor.py::TestSanitizeOutputStem tests/test_combat_audio_processor.py::TestNamedAudioOutputPaths tests/test_combat_audio_processor.py::TestResolveMkvOutputPaths -q
```

Expected: FAIL with missing import or old filenames.

- [ ] **Step 3: Implement naming helpers**

Modify `src/core/processors/combat_audio.py`:

```python
_ILLEGAL_FILENAME_CHARS = set('/\\:*?"<>|')


def sanitize_output_stem(filename: str, *, max_length: int = 80) -> str:
    stem = os.path.splitext(os.path.basename(filename))[0]
    cleaned = "".join("_" if ch in _ILLEGAL_FILENAME_CHARS else ch for ch in stem)
    cleaned = " ".join(cleaned.split())
    cleaned = cleaned.strip(" ._")
    if not cleaned:
        cleaned = "audio"
    return cleaned[:max_length].rstrip(" ._") or "audio"


def resolve_mkv_output_paths(config: CombatAudioConfig, *, timestamp: str | None = None) -> list[str]:
    input_stem = os.path.splitext(os.path.basename(config.input_path))[0]
    output_dir = config.output_dir or os.path.dirname(config.input_path)
    ts = timestamp or time.strftime("%Y%m%d%H%M%S")
    secondary_count = len(config.secondary_video_paths or [])
    if secondary_count == 0:
        return [os.path.join(output_dir, f"{input_stem}_{ts}.mkv")]
    return [
        os.path.join(output_dir, f"{input_stem}_{ts}-part{i + 1}.mkv")
        for i in range(secondary_count + 1)
    ]
```

Update `resolve_output_path` signature:

```python
def resolve_output_path(
    config: CombatAudioConfig,
    audio_count: int,
    *,
    audio_filenames: list[str] | None = None,
    timestamp: str | None = None,
) -> list[str]:
    input_stem = os.path.splitext(os.path.basename(config.input_path))[0]
    output_dir = config.output_dir or os.path.dirname(config.input_path)

    if config.boxed:
        return resolve_mkv_output_paths(config, timestamp=timestamp)

    suffix = "mixed" if config.mix_enabled else "aligned"
    ts = timestamp or time.strftime("%Y%m%d%H%M%S")
    output_dir = os.path.join(output_dir, f"{input_stem}_{suffix}_{ts}")
    paths = []
    for i in range(audio_count):
        if audio_filenames and i < len(audio_filenames):
            bg_stem = sanitize_output_stem(audio_filenames[i])
            filename = f"{i + 1:02d}_{bg_stem}_{suffix}.aac"
        else:
            filename = f"{input_stem}_{suffix}_{i:02d}.aac"
        paths.append(os.path.join(output_dir, filename))
    return paths
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_combat_audio_processor.py::TestSanitizeOutputStem tests/test_combat_audio_processor.py::TestNamedAudioOutputPaths tests/test_combat_audio_processor.py::TestResolveMkvOutputPaths tests/test_combat_audio_processor.py::TestResolveOutputPath -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/core/processors/combat_audio.py tests/test_combat_audio_processor.py
git commit -m "feat: add combat audio output naming helpers"
```

Expected: commit created.

---

### Task 5: Add mkvmerge and Multi-Part Mux Command Builders

**Files:**
- Modify: `src/core/processors/combat_audio.py`
- Test: `tests/test_combat_audio_processor.py`

- [ ] **Step 1: Write failing tests for mux command builders**

Add tests:

```python
class TestBuildMkvmergeMuxCommand:
    def test_command_maps_video_final_audios_and_original_audio(self):
        cmd = build_mkvmerge_mux_command(
            "/usr/bin/mkvmerge",
            "/video/part2.mp4",
            ["/tmp/mixed_00.m4a", "/tmp/mixed_01.m4a"],
            "/out/main_20260507190000-part2.mkv",
            keep_original_audio=True,
        )

        assert cmd[0] == "/usr/bin/mkvmerge"
        assert "-o" in cmd
        assert "/out/main_20260507190000-part2.mkv" in cmd
        assert "/video/part2.mp4" in cmd
        assert "/tmp/mixed_00.m4a" in cmd
        assert "/tmp/mixed_01.m4a" in cmd
        assert "--default-track" in cmd
        assert "0:yes" in cmd

    def test_command_can_skip_original_audio(self):
        cmd = build_mkvmerge_mux_command(
            "mkvmerge",
            "/video/no_audio.mp4",
            ["/tmp/mixed_00.m4a"],
            "/out/out.mkv",
            keep_original_audio=False,
        )

        joined = " ".join(cmd)
        assert "--no-audio /video/no_audio.mp4" in joined
```

Update imports to include `build_mkvmerge_mux_command`.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_combat_audio_processor.py::TestBuildMkvmergeMuxCommand -q
```

Expected: FAIL with missing `build_mkvmerge_mux_command`.

- [ ] **Step 3: Implement `mkvmerge` command builder**

Add to `src/core/processors/combat_audio.py`:

```python
def build_mkvmerge_mux_command(
    mkvmerge_path: str,
    video_path: str,
    final_audios: list[str],
    output_path: str,
    *,
    keep_original_audio: bool = True,
) -> list[str]:
    cmd = [
        mkvmerge_path,
        "-o", output_path,
        "--no-global-tags",
        "--no-chapters",
    ]

    if keep_original_audio:
        cmd += [video_path]
    else:
        cmd += ["--no-audio", video_path]

    for index, audio_path in enumerate(final_audios):
        default_value = "yes" if index == 0 else "no"
        cmd += [
            "--no-video",
            "--no-subtitles",
            "--no-chapters",
            "--no-global-tags",
            "--default-track", f"0:{default_value}",
            audio_path,
        ]

    return cmd
```

Do not remove `build_mux_command`; FFmpeg fallback still uses it.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_combat_audio_processor.py::TestBuildMkvmergeMuxCommand tests/test_combat_audio_processor.py::TestBuildMuxCommand -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/core/processors/combat_audio.py tests/test_combat_audio_processor.py
git commit -m "feat: build mkvmerge mux commands"
```

Expected: commit created.

---

### Task 6: Add Secondary Video Validation

**Files:**
- Modify: `src/core/processors/combat_audio.py`
- Test: `tests/test_combat_audio_processor.py`

- [ ] **Step 1: Write failing tests for validation**

Add tests:

```python
class TestValidateSecondaryVideos:
    def test_ignores_secondary_videos_when_not_boxed(self):
        cfg = CombatAudioConfig(
            input_path="/missing/main.mp4",
            audio_dir="/missing/audio",
            boxed=False,
            secondary_video_paths=["/missing/secondary.mp4"],
        )

        ok, err = validate_secondary_videos(cfg, is_audio=False)

        assert ok is True
        assert err is None

    def test_errors_when_boxed_secondary_video_missing(self):
        cfg = CombatAudioConfig(
            input_path="/tmp/main.mp4",
            audio_dir="/tmp/audio",
            boxed=True,
            secondary_video_paths=["/missing/secondary.mp4"],
        )

        ok, err = validate_secondary_videos(cfg, is_audio=False)

        assert ok is False
        assert "副视频不存在" in err
        assert "/missing/secondary.mp4" in err

    def test_ignores_secondary_videos_for_pure_audio_input(self):
        cfg = CombatAudioConfig(
            input_path="/tmp/main.aac",
            audio_dir="/tmp/audio",
            boxed=True,
            secondary_video_paths=["/missing/secondary.mp4"],
        )

        ok, err = validate_secondary_videos(cfg, is_audio=True)

        assert ok is True
        assert err is None
```

Update imports to include `validate_secondary_videos`.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_combat_audio_processor.py::TestValidateSecondaryVideos -q
```

Expected: FAIL with missing `validate_secondary_videos`.

- [ ] **Step 3: Implement validation helper**

Add to `src/core/processors/combat_audio.py`:

```python
def validate_secondary_videos(config: CombatAudioConfig, *, is_audio: bool) -> tuple[bool, str | None]:
    if is_audio or not config.boxed:
        return True, None

    for path in config.secondary_video_paths or []:
        if not os.path.exists(path):
            return False, f"副视频不存在: {path}"
        if is_pure_audio(path):
            return False, f"副视频不是视频文件: {path}"
    return True, None
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_combat_audio_processor.py::TestValidateSecondaryVideos -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/core/processors/combat_audio.py tests/test_combat_audio_processor.py
git commit -m "feat: validate secondary videos for mkv mux"
```

Expected: commit created.

---

### Task 7: Update Worker Mux Flow

**Files:**
- Modify: `src/worker/ffmpeg_worker.py`
- Test: `tests/test_ffmpeg_worker.py`

- [ ] **Step 1: Write failing worker test for multi-part mux**

Add to `tests/test_ffmpeg_worker.py`:

```python
def test_combat_audio_pipeline_muxes_main_and_secondary_videos_once_audio_is_ready(monkeypatch):
    worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
    exec_calls = []

    monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_audio_streams", lambda path: [object()])
    monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_duration", lambda path: 20.0)
    monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_extract_command", lambda *args, **kwargs: ["ffmpeg", "extract"])
    monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.resolve_output_path", lambda *args, **kwargs: [
        "/tmp/main_20260507190000-part1.mkv",
        "/tmp/main_20260507190000-part2.mkv",
    ])
    monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_mux_command", lambda video, audios, out, keep_original_audio=True: [
        "ffmpeg", "mux", video, out
    ])
    monkeypatch.setattr(
        FFmpegWorker,
        "_parallel_phase",
        lambda self, *args, **kwargs: ["/tmp/mixed_00.m4a"],
    )

    def fake_exec(self, cmd, *, progress_total=None, progress_desc="处理中"):
        exec_calls.append((cmd, progress_desc))
        return True

    monkeypatch.setattr(FFmpegWorker, "_exec_ffmpeg", fake_exec)

    config = CombatAudioConfig(
        input_path="/tmp/main.mkv",
        audio_dir="/tmp/audio",
        output_dir="/tmp",
        mix_enabled=True,
        boxed=True,
        secondary_video_paths=["/tmp/secondary.mp4"],
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        worker._combat_audio_pipeline(config, False, ["bg.aac"], 1, tmp_dir)

    mux_calls = [cmd for cmd, _ in exec_calls if cmd[:2] == ["ffmpeg", "mux"]]
    assert mux_calls == [
        ["ffmpeg", "mux", "/tmp/main.mkv", "/tmp/main_20260507190000-part1.mkv"],
        ["ffmpeg", "mux", "/tmp/secondary.mp4", "/tmp/main_20260507190000-part2.mkv"],
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_ffmpeg_worker.py::test_combat_audio_pipeline_muxes_main_and_secondary_videos_once_audio_is_ready -q
```

Expected: FAIL because worker only muxes one output.

- [ ] **Step 3: Implement multi-part mux loop with FFmpeg fallback**

Modify mux section in `src/worker/ffmpeg_worker.py`:

```python
from src.core.external_tools import MuxBackend, resolve_mux_backend
```

In `_combat_audio_pipeline`, replace the single mux call with:

```python
        if config.boxed and not is_audio:
            phase_idx += 1
            out_dir = os.path.dirname(output_paths[0])
            os.makedirs(out_dir, exist_ok=True)
            videos_to_mux = [config.input_path] + list(config.secondary_video_paths or [])
            backend, mkvmerge_path = resolve_mux_backend(config.mux_backend, config.mkvmerge_path)

            for part_index, (video_path, output_path) in enumerate(zip(videos_to_mux, output_paths), start=1):
                label = f"封装MKV part {part_index}/{len(videos_to_mux)}"
                self.progress.emit(0, 100, phase_desc(phase_idx, label, os.path.basename(video_path)))
                keep_original = bool(combat_audio.probe_audio_streams(video_path))
                if backend == MuxBackend.MKVMERGE and mkvmerge_path:
                    cmd = combat_audio.build_mkvmerge_mux_command(
                        mkvmerge_path,
                        video_path,
                        final_paths,
                        output_path,
                        keep_original_audio=keep_original,
                    )
                else:
                    cmd = combat_audio.build_mux_command(
                        video_path,
                        final_paths,
                        output_path,
                        keep_original_audio=keep_original,
                    )
                if not self._exec_ffmpeg(
                    cmd,
                    progress_total=base_duration,
                    progress_desc=phase_desc(phase_idx, label, os.path.basename(video_path)),
                ):
                    if self._cancel_event.is_set():
                        self.error.emit("已取消")
                        return
                    self.error.emit(self._compose_error_message(
                        f"MKV 封装失败：part{part_index} {os.path.basename(video_path)}",
                        self._last_ffmpeg_error_detail,
                    ))
                    return
            self.progress.emit(100, 100, phase_desc(phase_idx, "封装MKV"))
            self.finished.emit(out_dir if len(output_paths) > 1 else output_paths[0])
```

If `_exec_ffmpeg` name is misleading for `mkvmerge`, leave it for this task to avoid broader refactor; it runs any command list through `subprocess.Popen`.

- [ ] **Step 4: Run focused worker tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_ffmpeg_worker.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/worker/ffmpeg_worker.py tests/test_ffmpeg_worker.py
git commit -m "feat: mux combat audio outputs into multiple mkv parts"
```

Expected: commit created.

---

### Task 8: Add Settings Page UI for mkvmerge

**Files:**
- Modify: `src/gui/settings_tab.py`
- Test: `tests/gui/test_settings_tab.py`

- [ ] **Step 1: Write failing GUI tests**

Create `tests/gui/test_settings_tab.py`:

```python
import pytest
from PyQt6.QtWidgets import QApplication

from src.core.app_settings import AppSettings
from src.gui import settings_tab
from src.gui.settings_tab import SettingsTab


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_settings_tab_loads_mkvmerge_path(monkeypatch, qapp):
    monkeypatch.setattr(settings_tab, "load_settings", lambda: AppSettings(mkvmerge_path="/opt/bin/mkvmerge"))
    monkeypatch.setattr(settings_tab, "resolve_mkvmerge_path", lambda path: path)

    tab = SettingsTab()

    assert tab._mkvmerge_edit.text() == "/opt/bin/mkvmerge"
    assert "已检测" in tab._mkvmerge_status.text()


def test_settings_tab_auto_detect_sets_path(monkeypatch, qapp):
    saved = []
    monkeypatch.setattr(settings_tab, "load_settings", lambda: AppSettings())
    monkeypatch.setattr(settings_tab, "save_settings", lambda settings: saved.append(settings))
    monkeypatch.setattr(settings_tab, "resolve_mkvmerge_path", lambda path=None: "/usr/bin/mkvmerge")

    tab = SettingsTab()
    tab._detect_mkvmerge()

    assert tab._mkvmerge_edit.text() == "/usr/bin/mkvmerge"
    assert saved[-1].mkvmerge_path == "/usr/bin/mkvmerge"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/gui/test_settings_tab.py -q
```

Expected: FAIL because settings UI fields do not exist.

- [ ] **Step 3: Implement settings UI**

Modify imports in `src/gui/settings_tab.py`:

```python
from PyQt6.QtWidgets import QFileDialog, QLineEdit
from src.core.app_settings import AppSettings, load_settings, save_settings
from src.core.external_tools import resolve_mkvmerge_path
```

In `SettingsTab.__init__`, load settings:

```python
        self._settings = load_settings()
```

Add external tools group before about group:

```python
        tools_group = QGroupBox("外部工具")
        tools_layout = QVBoxLayout(tools_group)
        tools_layout.setSpacing(8)

        mkvmerge_row = QHBoxLayout()
        mkvmerge_row.addWidget(QLabel("mkvmerge 路径"))
        self._mkvmerge_edit = QLineEdit()
        self._mkvmerge_edit.setText(self._settings.mkvmerge_path or "")
        self._mkvmerge_edit.editingFinished.connect(self._save_mkvmerge_path)
        mkvmerge_row.addWidget(self._mkvmerge_edit, 1)
        detect_btn = QPushButton("自动检测")
        detect_btn.clicked.connect(self._detect_mkvmerge)
        mkvmerge_row.addWidget(detect_btn)
        choose_btn = QPushButton("选择...")
        choose_btn.clicked.connect(self._choose_mkvmerge)
        mkvmerge_row.addWidget(choose_btn)
        tools_layout.addLayout(mkvmerge_row)

        self._mkvmerge_status = QLabel()
        self._mkvmerge_status.setStyleSheet("color: gray; font-size: 11px;")
        tools_layout.addWidget(self._mkvmerge_status)
        layout.addWidget(tools_group)
        self._update_mkvmerge_status()
```

Add methods:

```python
    def _current_mkvmerge_path(self) -> str | None:
        return self._mkvmerge_edit.text().strip() or None

    def _save_mkvmerge_path(self) -> None:
        self._settings.mkvmerge_path = self._current_mkvmerge_path()
        save_settings(self._settings)
        self._update_mkvmerge_status()

    def _detect_mkvmerge(self) -> None:
        detected = resolve_mkvmerge_path(None)
        if detected:
            self._mkvmerge_edit.setText(detected)
            self._save_mkvmerge_path()
        else:
            self._update_mkvmerge_status()

    def _choose_mkvmerge(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 mkvmerge")
        if path:
            self._mkvmerge_edit.setText(path)
            self._save_mkvmerge_path()

    def _update_mkvmerge_status(self) -> None:
        manual = self._current_mkvmerge_path()
        resolved = resolve_mkvmerge_path(manual)
        if resolved:
            self._mkvmerge_status.setText(f"已检测：{resolved}")
        elif manual:
            self._mkvmerge_status.setText("路径不可用，将自动检测；未检测到时回退 FFmpeg")
        else:
            self._mkvmerge_status.setText("未检测到 mkvmerge 时将回退 FFmpeg")
```

- [ ] **Step 4: Run GUI tests**

Run:

```bash
.venv/bin/python -m pytest tests/gui/test_settings_tab.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/gui/settings_tab.py tests/gui/test_settings_tab.py
git commit -m "feat: configure mkvmerge path in settings"
```

Expected: commit created.

---

### Task 9: Add Secondary Video UI and Config Wiring

**Files:**
- Modify: `src/gui/task_panels/combat_audio_panel.py`
- Modify: `src/gui/main_window.py`
- Test: `tests/gui/task_panels/test_combat_audio_panel_preview_start.py`

- [ ] **Step 1: Write failing GUI tests for secondary video order and enabled state**

Append tests:

```python
def test_secondary_videos_are_disabled_until_boxed_video_input(panel):
    panel._is_pure_audio = False
    panel._input_streams = [object()]
    panel._boxed_checkbox.setChecked(False)
    panel._update_param_states()

    assert not panel._secondary_group.isEnabled()

    panel._boxed_checkbox.setChecked(True)
    panel._update_param_states()

    assert panel._secondary_group.isEnabled()


def test_secondary_video_order_is_written_to_config(panel, tmp_path):
    main = tmp_path / "main.mkv"
    audio_dir = tmp_path / "audio"
    secondary1 = tmp_path / "part2.mp4"
    secondary2 = tmp_path / "part3.mp4"
    main.write_text("", encoding="utf-8")
    secondary1.write_text("", encoding="utf-8")
    secondary2.write_text("", encoding="utf-8")
    audio_dir.mkdir()
    (audio_dir / "bg.aac").write_text("", encoding="utf-8")

    panel._input_selector.set_path(str(main))
    panel._audio_dir_selector.set_path(str(audio_dir))
    panel._is_pure_audio = False
    panel._input_streams = [object()]
    panel._boxed_checkbox.setChecked(True)
    panel._secondary_video_paths = [str(secondary2), str(secondary1)]
    panel._refresh_secondary_videos()

    cfg = panel._build_combat_config()

    assert cfg.secondary_video_paths == [str(secondary2), str(secondary1)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/gui/task_panels/test_combat_audio_panel_preview_start.py::test_secondary_videos_are_disabled_until_boxed_video_input tests/gui/task_panels/test_combat_audio_panel_preview_start.py::test_secondary_video_order_is_written_to_config -q
```

Expected: FAIL because secondary-video UI fields do not exist.

- [ ] **Step 3: Implement compact secondary video list**

Modify `CombatAudioPanel.__init__`:

```python
        self._secondary_video_paths: list[str] = []
        self._mkvmerge_path: str | None = None
        self._mux_backend = "auto"
```

Add under audio directory selector in `_build_upper_left`:

```python
        self._secondary_group = QGroupBox("副视频（仅封装 MKV 时可用）")
        secondary_layout = QVBoxLayout(self._secondary_group)
        secondary_layout.setSpacing(6)
        self._secondary_list = QVBoxLayout()
        secondary_layout.addLayout(self._secondary_list)
        secondary_buttons = QHBoxLayout()
        add_secondary = QPushButton("添加副视频")
        add_secondary.clicked.connect(self._add_secondary_video)
        clear_secondary = QPushButton("清空")
        clear_secondary.clicked.connect(self._clear_secondary_videos)
        secondary_buttons.addWidget(add_secondary)
        secondary_buttons.addWidget(clear_secondary)
        secondary_buttons.addStretch()
        secondary_layout.addLayout(secondary_buttons)
        left.addWidget(self._secondary_group)
```

Connect boxed checkbox:

```python
        self._boxed_checkbox.toggled.connect(lambda _checked: self._update_param_states())
```

Add methods:

```python
    def set_mux_settings(self, *, mkvmerge_path: str | None, mux_backend: str = "auto") -> None:
        self._mkvmerge_path = mkvmerge_path
        self._mux_backend = mux_backend
        self._update_param_states()

    def _add_secondary_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择副视频", "", _MEDIA_FILTER)
        if path:
            self._secondary_video_paths.append(path)
            self._refresh_secondary_videos()

    def _clear_secondary_videos(self) -> None:
        self._secondary_video_paths.clear()
        self._refresh_secondary_videos()

    def _move_secondary_video(self, index: int, delta: int) -> None:
        new_index = index + delta
        if new_index < 0 or new_index >= len(self._secondary_video_paths):
            return
        self._secondary_video_paths[index], self._secondary_video_paths[new_index] = (
            self._secondary_video_paths[new_index],
            self._secondary_video_paths[index],
        )
        self._refresh_secondary_videos()

    def _remove_secondary_video(self, index: int) -> None:
        if 0 <= index < len(self._secondary_video_paths):
            self._secondary_video_paths.pop(index)
            self._refresh_secondary_videos()

    def _refresh_secondary_videos(self) -> None:
        while self._secondary_list.count():
            item = self._secondary_list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for index, path in enumerate(self._secondary_video_paths):
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(QLabel(f"{index + 1:02d}"))
            row.addWidget(QLabel(os.path.basename(path)), 1)
            up = QPushButton("↑")
            up.clicked.connect(lambda _checked=False, i=index: self._move_secondary_video(i, -1))
            row.addWidget(up)
            down = QPushButton("↓")
            down.clicked.connect(lambda _checked=False, i=index: self._move_secondary_video(i, 1))
            row.addWidget(down)
            remove = QPushButton("移除")
            remove.clicked.connect(lambda _checked=False, i=index: self._remove_secondary_video(i))
            row.addWidget(remove)
            self._secondary_list.addWidget(row_widget)
```

Update `_update_param_states`:

```python
        secondary_enabled = (not is_audio) and self._boxed_checkbox.isChecked()
        self._secondary_group.setEnabled(secondary_enabled)
```

Update `_build_combat_config`:

```python
            secondary_video_paths=list(self._secondary_video_paths) if self._boxed_checkbox.isChecked() and not self._is_pure_audio else [],
            mkvmerge_path=self._mkvmerge_path,
            mux_backend=self._mux_backend,
```

Update `MainWindow._on_start` and `_on_enqueue` before `build_config()`:

```python
        if isinstance(panel, CombatAudioPanel):
            settings = load_settings()
            panel.set_mux_settings(mkvmerge_path=settings.mkvmerge_path, mux_backend="auto")
```

Import `load_settings` in `main_window.py`.

- [ ] **Step 4: Run focused GUI tests**

Run:

```bash
.venv/bin/python -m pytest tests/gui/task_panels/test_combat_audio_panel_preview_start.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/gui/task_panels/combat_audio_panel.py src/gui/main_window.py tests/gui/task_panels/test_combat_audio_panel_preview_start.py
git commit -m "feat: add secondary video controls to combat audio"
```

Expected: commit created.

---

### Task 10: Integrate Queue Counts and Validation

**Files:**
- Modify: `src/gui/task_panels/combat_audio_panel.py`
- Modify: `src/gui/queue_tab.py`
- Modify: `src/gui/main_window.py`
- Test: `tests/gui/task_panels/test_combat_audio_panel_preview_start.py`
- Test: `tests/test_combat_audio_processor.py`

- [ ] **Step 1: Write failing tests for secondary validation in panel**

Append GUI test:

```python
def test_validate_errors_for_missing_secondary_video_when_boxed(panel, tmp_path):
    main = tmp_path / "main.mkv"
    audio_dir = tmp_path / "audio"
    main.write_text("", encoding="utf-8")
    audio_dir.mkdir()
    (audio_dir / "bg.aac").write_text("", encoding="utf-8")

    panel._input_selector.set_path(str(main))
    panel._audio_dir_selector.set_path(str(audio_dir))
    panel._is_pure_audio = False
    panel._input_streams = [object()]
    panel._boxed_checkbox.setChecked(True)
    panel._secondary_video_paths = [str(tmp_path / "missing.mp4")]

    ok, _count, err = panel.validate()

    assert ok is False
    assert "副视频不存在" in err
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/gui/task_panels/test_combat_audio_panel_preview_start.py::test_validate_errors_for_missing_secondary_video_when_boxed -q
```

Expected: FAIL because panel validation does not call `validate_secondary_videos`.

- [ ] **Step 3: Wire validation and counts**

In `CombatAudioPanel.validate`, after `combat_audio.validate(config)`:

```python
        ok, err = combat_audio.validate_secondary_videos(config, is_audio=self._is_pure_audio)
        if not ok:
            return False, 0, err
```

Update count returned by `validate`:

```python
        if config.boxed and not self._is_pure_audio:
            output_count = 1 + len(config.secondary_video_paths or [])
            return True, output_count, None
        return True, audio_count, None
```

In `QueueTab` combat audio count logic:

```python
            if cfg.boxed and cfg.secondary_video_paths:
                count = 1 + len(cfg.secondary_video_paths)
            else:
                audio_files = cfg.audio_order or [f.filename for f in combat_audio.scan_audio_dir(cfg.audio_dir)]
                count = len(audio_files)
```

In `MainWindow._on_enqueue`, `combat_resolve(config, audio_count=count)` still works because boxed path resolution ignores `audio_count` and reads secondary videos.

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/gui/task_panels/test_combat_audio_panel_preview_start.py tests/test_combat_audio_processor.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/gui/task_panels/combat_audio_panel.py src/gui/queue_tab.py src/gui/main_window.py tests/gui/task_panels/test_combat_audio_panel_preview_start.py tests/test_combat_audio_processor.py
git commit -m "feat: validate and count secondary video outputs"
```

Expected: commit created.

---

### Task 11: Wire Named AAC Outputs Through Worker

**Files:**
- Modify: `src/worker/ffmpeg_worker.py`
- Test: `tests/test_ffmpeg_worker.py`

- [ ] **Step 1: Write failing worker test for named AAC output arguments**

Add test:

```python
def test_non_boxed_export_uses_audio_filenames_for_output_paths(monkeypatch):
    worker = FFmpegWorker(TaskType.COMBAT_AUDIO, {}, encoder_registry=None)
    resolve_calls = []

    monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_audio_streams", lambda path: [object()])
    monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.probe_duration", lambda path: 20.0)
    monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_extract_command", lambda *args, **kwargs: ["ffmpeg", "extract"])
    monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.build_export_aac_command", lambda src, out: ["ffmpeg", "export", out])

    def fake_resolve(config, audio_count, **kwargs):
        resolve_calls.append(kwargs)
        return ["/tmp/out/01_bg one_mixed.aac", "/tmp/out/02_bg two_mixed.aac"]

    monkeypatch.setattr("src.worker.ffmpeg_worker.combat_audio.resolve_output_path", fake_resolve)
    monkeypatch.setattr(
        FFmpegWorker,
        "_parallel_phase",
        lambda self, *args, **kwargs: ["/tmp/mixed_00.m4a", "/tmp/mixed_01.m4a"],
    )
    monkeypatch.setattr(FFmpegWorker, "_exec_ffmpeg", lambda self, *args, **kwargs: True)

    config = CombatAudioConfig(
        input_path="/tmp/main.mkv",
        audio_dir="/tmp/audio",
        output_dir="/tmp/out",
        mix_enabled=True,
        boxed=False,
        audio_order=["bg one.mp3", "bg two.mp3"],
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        worker._combat_audio_pipeline(config, False, ["bg one.mp3", "bg two.mp3"], 2, tmp_dir)

    assert resolve_calls[0]["audio_filenames"] == ["bg one.mp3", "bg two.mp3"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_ffmpeg_worker.py::test_non_boxed_export_uses_audio_filenames_for_output_paths -q
```

Expected: FAIL because worker does not pass `audio_filenames`.

- [ ] **Step 3: Pass audio names into path resolution**

Modify `src/worker/ffmpeg_worker.py`:

```python
        output_paths = combat_audio.resolve_output_path(
            replace(config, mix_enabled=mix_effective),
            audio_count=len(final_paths),
            audio_filenames=audio_files,
        )
```

This is safe for boxed output because boxed resolution ignores `audio_filenames`.

- [ ] **Step 4: Run worker tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_ffmpeg_worker.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/worker/ffmpeg_worker.py tests/test_ffmpeg_worker.py
git commit -m "feat: name exported audio by source file"
```

Expected: commit created.

---

### Task 12: Full Verification and Cleanup

**Files:**
- No code files required unless tests reveal gaps.

- [ ] **Step 1: Run full test suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: PASS with no failures.

- [ ] **Step 2: Inspect final diff**

Run:

```bash
git diff --stat origin/master..HEAD
git status --short
```

Expected:

- Only intended feature files are committed on the branch.
- No unrelated unstaged files are mixed into commits.

- [ ] **Step 3: Restore pre-existing local edits if they were stashed**

Run:

```bash
git stash list
```

If `pre-mkvmerge-secondary-videos local edits` is present and the user wants the original local edits restored, run:

```bash
git stash pop
```

Expected: original unrelated local edits return to the worktree. Do not commit them unless requested.

- [ ] **Step 4: Report completion state**

Report:

- Branch name.
- Commit list.
- Full test command and result.
- Any restored or remaining local unstaged changes.
