# M2: CombatVideoWithAudios Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add audio/video mixing feature (M2) — mix input audio tracks with background music, with preview playback, parallel processing, and optional MKV muxing.

**Architecture:** New `CombatAudioConfig` dataclass + `combat_audio.py` pure-function processor (matching `pic_seq.py` pattern) + `AudioPlayerBar` reusable component + `CombatAudioPanel` with custom 4-zone layout inheriting `BaseTaskPanel` + `FFmpegWorker` extension with `ThreadPoolExecutor` for parallel ffmpeg subprocess execution.

**Tech Stack:** Python 3.10+, PyQt6, PyQt6-QtMultimedia (QMediaPlayer), ffmpeg/ffprobe (subprocess), concurrent.futures.ThreadPoolExecutor

**Spec:** `docs/superpowers/specs/2026-04-08-m2-combat-audio-design.md`

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `src/core/config.py` | Add `CombatAudioConfig` dataclass |
| Create | `src/core/processors/combat_audio.py` | Pure functions: probe, validate, command builders |
| Modify | `src/gui/task_panels/base_panel.py` | Make `_init_base_layout()` opt-in via constructor param |
| Create | `src/gui/components/audio_player.py` | `AudioPlayerBar` — shared QMediaPlayer playback widget |
| Create | `src/gui/task_panels/combat_audio_panel.py` | M2 panel with 4-zone custom layout |
| Modify | `src/worker/ffmpeg_worker.py` | Add `_run_combat_audio()` with parallel phases |
| Modify | `src/gui/main_window.py` | Add M2 tab, generalize `_on_enqueue` |
| Modify | `src/gui/queue_tab.py` | Support `COMBAT_AUDIO` in queue execution |
| Create | `tests/test_combat_audio_config.py` | Config dataclass tests |
| Create | `tests/test_combat_audio_processor.py` | Processor function tests |

---

### Task 1: CombatAudioConfig dataclass

**Files:**
- Modify: `src/core/config.py`
- Create: `tests/test_combat_audio_config.py`

- [ ] **Step 1: Write failing tests for CombatAudioConfig**

```python
# tests/test_combat_audio_config.py
from src.core.config import CombatAudioConfig


def test_combat_audio_config_defaults():
    cfg = CombatAudioConfig(
        input_path="/tmp/video.mp4",
        audio_dir="/tmp/audio",
    )
    assert cfg.input_path == "/tmp/video.mp4"
    assert cfg.audio_dir == "/tmp/audio"
    assert cfg.output_dir is None
    assert cfg.mix_enabled is True
    assert cfg.volume == 0.6
    assert cfg.boxed is False
    assert cfg.thread_count == 1
    assert cfg.audio_stream_index == 0
    assert cfg.audio_order == []


def test_combat_audio_config_round_trip():
    cfg = CombatAudioConfig(
        input_path="/tmp/video.mkv",
        audio_dir="/tmp/bgm",
        output_dir="/tmp/out",
        mix_enabled=False,
        volume=0.8,
        boxed=True,
        thread_count=4,
        audio_stream_index=2,
        audio_order=["jazz.mp3", "piano.mp3"],
    )
    d = cfg.to_dict()
    restored = CombatAudioConfig.from_dict(d)
    assert restored.input_path == cfg.input_path
    assert restored.audio_dir == cfg.audio_dir
    assert restored.output_dir == cfg.output_dir
    assert restored.mix_enabled == cfg.mix_enabled
    assert restored.volume == cfg.volume
    assert restored.boxed == cfg.boxed
    assert restored.thread_count == cfg.thread_count
    assert restored.audio_stream_index == cfg.audio_stream_index
    assert restored.audio_order == cfg.audio_order


def test_combat_audio_config_from_dict_defaults():
    d = {"input_path": "/tmp/v.mp4", "audio_dir": "/tmp/a"}
    cfg = CombatAudioConfig.from_dict(d)
    assert cfg.mix_enabled is True
    assert cfg.volume == 0.6
    assert cfg.boxed is False
    assert cfg.thread_count == 1
    assert cfg.audio_stream_index == 0
    assert cfg.audio_order == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/test_combat_audio_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'CombatAudioConfig'`

- [ ] **Step 3: Implement CombatAudioConfig**

Add to `src/core/config.py` after the `PicSeqConfig` class:

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

    def __post_init__(self):
        if self.audio_order is None:
            self.audio_order = []

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
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/test_combat_audio_config.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/core/config.py tests/test_combat_audio_config.py
git commit -m "feat(m2): add CombatAudioConfig dataclass with serialization"
```

---

### Task 2: combat_audio.py processor — data types and helpers

**Files:**
- Create: `src/core/processors/combat_audio.py`
- Create: `tests/test_combat_audio_processor.py`

- [ ] **Step 1: Write failing tests for data types and helper functions**

```python
# tests/test_combat_audio_processor.py
import os
import tempfile

from src.core.processors.combat_audio import (
    AudioFileInfo,
    AudioStreamInfo,
    PURE_AUDIO_EXTENSIONS,
    is_pure_audio,
    scan_audio_dir,
)


def test_audio_stream_info_fields():
    info = AudioStreamInfo(
        index=0, codec="aac", sample_rate=48000,
        channels=2, channel_layout="stereo",
    )
    assert info.index == 0
    assert info.codec == "aac"
    assert info.sample_rate == 48000
    assert info.channels == 2
    assert info.channel_layout == "stereo"


def test_audio_file_info_fields():
    info = AudioFileInfo(filename="jazz.mp3", path="/tmp/jazz.mp3", duration=125.5)
    assert info.filename == "jazz.mp3"
    assert info.duration == 125.5


def test_is_pure_audio():
    assert is_pure_audio("/tmp/song.aac") is True
    assert is_pure_audio("/tmp/song.mp3") is True
    assert is_pure_audio("/tmp/song.wav") is True
    assert is_pure_audio("/tmp/song.flac") is True
    assert is_pure_audio("/tmp/song.AAC") is True
    assert is_pure_audio("/tmp/video.mp4") is False
    assert is_pure_audio("/tmp/video.mkv") is False


def test_scan_audio_dir_empty(tmp_path):
    result = scan_audio_dir(str(tmp_path))
    assert result == []


def test_scan_audio_dir_filters_non_audio(tmp_path):
    (tmp_path / "video.mp4").write_text("fake")
    (tmp_path / "readme.txt").write_text("fake")
    result = scan_audio_dir(str(tmp_path))
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/test_combat_audio_processor.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement data types and helpers**

```python
# src/core/processors/combat_audio.py
"""Combat audio processor — pure functions for audio/video mixing with background music."""

import json
import os
import subprocess
from dataclasses import dataclass

PURE_AUDIO_EXTENSIONS = {".aac", ".mp3", ".wav", ".flac"}


@dataclass
class AudioStreamInfo:
    index: int
    codec: str
    sample_rate: int
    channels: int
    channel_layout: str


@dataclass
class AudioFileInfo:
    filename: str
    path: str
    duration: float


def is_pure_audio(file_path: str) -> bool:
    """Check if the file is a pure audio file based on extension."""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in PURE_AUDIO_EXTENSIONS


def scan_audio_dir(dir_path: str) -> list[AudioFileInfo]:
    """Scan directory for audio files. Returns list sorted by filename.
    Duration is set to 0.0 — caller should use probe_duration() to fill it."""
    if not os.path.isdir(dir_path):
        return []
    results = []
    for name in sorted(os.listdir(dir_path)):
        ext = os.path.splitext(name)[1].lower()
        if ext in PURE_AUDIO_EXTENSIONS:
            results.append(AudioFileInfo(
                filename=name,
                path=os.path.join(dir_path, name),
                duration=0.0,
            ))
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/test_combat_audio_processor.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/core/processors/combat_audio.py tests/test_combat_audio_processor.py
git commit -m "feat(m2): add combat_audio processor data types and helpers"
```

---

### Task 3: combat_audio.py processor — ffprobe functions

**Files:**
- Modify: `src/core/processors/combat_audio.py`
- Modify: `tests/test_combat_audio_processor.py`

- [ ] **Step 1: Write failing tests for probe functions**

Append to `tests/test_combat_audio_processor.py`:

```python
from unittest.mock import patch
from src.core.processors.combat_audio import probe_audio_streams, probe_duration


def test_probe_duration_parses_ffprobe_output():
    fake_output = json.dumps({"format": {"duration": "185.320000"}})
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = fake_output
        mock_run.return_value.returncode = 0
        dur = probe_duration("/tmp/test.mp4")
    assert dur == 185.32
    mock_run.assert_called_once()


def test_probe_duration_returns_zero_on_failure():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        dur = probe_duration("/tmp/nonexistent.mp4")
    assert dur == 0.0


def test_probe_audio_streams_parses_ffprobe_output():
    fake_output = json.dumps({"streams": [
        {
            "index": 1,
            "codec_name": "aac",
            "sample_rate": "48000",
            "channels": 2,
            "channel_layout": "stereo",
        },
        {
            "index": 2,
            "codec_name": "ac3",
            "sample_rate": "48000",
            "channels": 6,
            "channel_layout": "5.1",
        },
    ]})
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = fake_output
        mock_run.return_value.returncode = 0
        streams = probe_audio_streams("/tmp/test.mkv")
    assert len(streams) == 2
    assert streams[0].index == 1
    assert streams[0].codec == "aac"
    assert streams[0].channels == 2
    assert streams[1].codec == "ac3"
    assert streams[1].channel_layout == "5.1"


def test_probe_audio_streams_returns_empty_on_failure():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        streams = probe_audio_streams("/tmp/nonexistent.mkv")
    assert streams == []
```

Add `import json` at the top of the test file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/test_combat_audio_processor.py::test_probe_duration_parses_ffprobe_output tests/test_combat_audio_processor.py::test_probe_audio_streams_parses_ffprobe_output -v`
Expected: FAIL — `ImportError: cannot import name 'probe_audio_streams'`

- [ ] **Step 3: Implement probe functions**

Add to `src/core/processors/combat_audio.py`:

```python
def probe_duration(file_path: str) -> float:
    """Get media duration in seconds using ffprobe. Returns 0.0 on failure."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_entries", "format=duration",
                file_path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception:
        return 0.0


def probe_audio_streams(file_path: str) -> list[AudioStreamInfo]:
    """Probe all audio streams in a media file using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                "-select_streams", "a",
                file_path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout)
        streams = []
        for s in data.get("streams", []):
            streams.append(AudioStreamInfo(
                index=s["index"],
                codec=s.get("codec_name", "unknown"),
                sample_rate=int(s.get("sample_rate", 0)),
                channels=s.get("channels", 0),
                channel_layout=s.get("channel_layout", ""),
            ))
        return streams
    except Exception:
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/test_combat_audio_processor.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/core/processors/combat_audio.py tests/test_combat_audio_processor.py
git commit -m "feat(m2): add ffprobe functions for audio stream and duration probing"
```

---

### Task 4: combat_audio.py processor — command builders

**Files:**
- Modify: `src/core/processors/combat_audio.py`
- Modify: `tests/test_combat_audio_processor.py`

- [ ] **Step 1: Write failing tests for command builders**

Append to `tests/test_combat_audio_processor.py`:

```python
from src.core.processors.combat_audio import (
    build_extract_command,
    build_duration_adjust_command,
    build_mix_command,
    build_mux_command,
    build_preview_command,
)


def test_build_extract_command():
    cmd = build_extract_command("/tmp/video.mkv", stream_index=2, output_path="/tmp/out.aac")
    assert cmd == ["ffmpeg", "-y", "-i", "/tmp/video.mkv", "-map", "0:a:2", "-c:a", "copy", "/tmp/out.aac"]


def test_build_duration_adjust_command_trim():
    cmd = build_duration_adjust_command("/tmp/bg.mp3", target_duration=60.0, bg_duration=120.0, output_path="/tmp/adj.aac")
    assert "-af" in cmd
    af_idx = cmd.index("-af")
    assert cmd[af_idx + 1] == "atrim=0:60.0"


def test_build_duration_adjust_command_loop():
    cmd = build_duration_adjust_command("/tmp/bg.mp3", target_duration=120.0, bg_duration=60.0, output_path="/tmp/adj.aac")
    af_idx = cmd.index("-af")
    assert "aloop=-1:1" in cmd[af_idx + 1]
    assert "atrim=0:120.0" in cmd[af_idx + 1]


def test_build_mix_command_contains_loudnorm():
    cmd = build_mix_command("/tmp/base.aac", "/tmp/bg.aac", volume=0.6, output_path="/tmp/mix.aac")
    assert "-filter_complex" in cmd
    fc_idx = cmd.index("-filter_complex")
    fc = cmd[fc_idx + 1]
    assert "loudnorm" in fc
    assert "amix" in fc
    assert "weights=0.6 1" in fc


def test_build_mux_command():
    cmd = build_mux_command(
        "/tmp/video.mkv",
        ["/tmp/mix_0.aac", "/tmp/mix_1.aac"],
        output_path="/tmp/out.mkv",
    )
    assert "-i" in cmd
    # video input + 2 audio inputs = 3 -i flags
    assert cmd.count("-i") == 3
    # map video, subtitles, mixed audios, original audio
    assert "-map" in cmd
    assert "0:v" in cmd
    assert "0:s?" in cmd
    assert "1:a" in cmd
    assert "2:a" in cmd
    assert "0:a" in cmd
    assert cmd[-1] == "/tmp/out.mkv"


def test_build_preview_command_contains_atrim_5s():
    cmd = build_preview_command("/tmp/base.aac", "/tmp/bg.aac", volume=0.6, output_path="/tmp/prev.aac")
    fc_idx = cmd.index("-filter_complex")
    fc = cmd[fc_idx + 1]
    assert "atrim=0:5" in fc
    assert "loudnorm" in fc
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/test_combat_audio_processor.py::test_build_extract_command -v`
Expected: FAIL — `ImportError: cannot import name 'build_extract_command'`

- [ ] **Step 3: Implement command builders**

Add to `src/core/processors/combat_audio.py`:

```python
_LOUDNORM = "loudnorm=I=-14:TP=-1.0:LRA=15"


def build_extract_command(input_path: str, stream_index: int, output_path: str) -> list[str]:
    """Build ffmpeg command to extract a specific audio stream."""
    return [
        "ffmpeg", "-y",
        "-i", input_path,
        "-map", f"0:a:{stream_index}",
        "-c:a", "copy",
        output_path,
    ]


def build_duration_adjust_command(
    audio_path: str, target_duration: float, bg_duration: float, output_path: str,
) -> list[str]:
    """Build ffmpeg command to adjust audio duration (trim or loop+trim)."""
    if bg_duration >= target_duration:
        af = f"atrim=0:{target_duration}"
    else:
        af = f"aloop=-1:1,atrim=0:{target_duration}"
    return [
        "ffmpeg", "-y",
        "-i", audio_path,
        "-af", af,
        "-c:a", "aac",
        output_path,
    ]


def build_mix_command(
    base_audio: str, bg_audio: str, volume: float, output_path: str,
) -> list[str]:
    """Build ffmpeg command for audio mixing with loudnorm chain."""
    fc = (
        f"[0:a]{_LOUDNORM}[main];"
        f"[1:a]{_LOUDNORM}[bg];"
        f"[main][bg]amix=inputs=2:duration=first:dropout_transition=1"
        f":weights={volume} 1:normalize=0,"
        f"volume=2,{_LOUDNORM}"
    )
    return [
        "ffmpeg", "-y", "-hwaccel", "auto",
        "-i", base_audio,
        "-i", bg_audio,
        "-filter_complex", fc,
        "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]


def build_mux_command(
    video_path: str, mixed_audios: list[str], output_path: str,
) -> list[str]:
    """Build ffmpeg command to mux video + mixed audio tracks into MKV."""
    cmd = ["ffmpeg", "-y", "-i", video_path]
    for audio in mixed_audios:
        cmd += ["-i", audio]
    # Map: video streams, subtitle streams (optional), mixed audios in order, then original audio
    cmd += ["-map", "0:v", "-map", "0:s?"]
    for i in range(len(mixed_audios)):
        cmd += ["-map", f"{i + 1}:a"]
    cmd += ["-map", "0:a", "-c", "copy", output_path]
    return cmd


def build_preview_command(
    base_audio: str, bg_audio: str, volume: float, output_path: str,
) -> list[str]:
    """Build ffmpeg command for 5-second preview mix."""
    fc = (
        f"[0:a]atrim=0:5,{_LOUDNORM}[main];"
        f"[1:a]atrim=0:5,{_LOUDNORM}[bg];"
        f"[main][bg]amix=inputs=2:duration=first:dropout_transition=1"
        f":weights={volume} 1:normalize=0,"
        f"volume=2,{_LOUDNORM}"
    )
    return [
        "ffmpeg", "-y", "-hwaccel", "auto",
        "-i", base_audio,
        "-i", bg_audio,
        "-filter_complex", fc,
        "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/test_combat_audio_processor.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add src/core/processors/combat_audio.py tests/test_combat_audio_processor.py
git commit -m "feat(m2): add ffmpeg command builders for extract, adjust, mix, mux, preview"
```

---

### Task 5: combat_audio.py processor — validate and output path

**Files:**
- Modify: `src/core/processors/combat_audio.py`
- Modify: `tests/test_combat_audio_processor.py`

- [ ] **Step 1: Write failing tests for validate and resolve_output_path**

Append to `tests/test_combat_audio_processor.py`:

```python
from src.core.config import CombatAudioConfig
from src.core.processors.combat_audio import validate, resolve_output_path


def test_validate_missing_input(tmp_path):
    cfg = CombatAudioConfig(input_path="/nonexistent/video.mp4", audio_dir=str(tmp_path))
    ok, err = validate(cfg)
    assert ok is False
    assert "不存在" in err


def test_validate_missing_audio_dir(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_text("fake")
    cfg = CombatAudioConfig(input_path=str(video), audio_dir="/nonexistent/dir")
    ok, err = validate(cfg)
    assert ok is False
    assert "不存在" in err


def test_validate_empty_audio_dir(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_text("fake")
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    cfg = CombatAudioConfig(input_path=str(video), audio_dir=str(audio_dir))
    ok, err = validate(cfg)
    assert ok is False
    assert "音频文件" in err


def test_validate_success(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_text("fake")
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "jazz.mp3").write_text("fake")
    cfg = CombatAudioConfig(input_path=str(video), audio_dir=str(audio_dir))
    ok, err = validate(cfg)
    assert ok is True
    assert err is None


def test_validate_empty_audio_order_uses_scan(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_text("fake")
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "a.mp3").write_text("fake")
    (audio_dir / "b.wav").write_text("fake")
    cfg = CombatAudioConfig(input_path=str(video), audio_dir=str(audio_dir), audio_order=[])
    ok, err = validate(cfg)
    assert ok is True


def test_resolve_output_path_mixed_no_box(tmp_path):
    cfg = CombatAudioConfig(
        input_path=str(tmp_path / "video.mp4"),
        audio_dir=str(tmp_path),
        mix_enabled=True, boxed=False,
    )
    paths = resolve_output_path(cfg, audio_count=2)
    assert len(paths) == 2
    assert paths[0].endswith("video_mixed_00.aac")
    assert paths[1].endswith("video_mixed_01.aac")


def test_resolve_output_path_aligned_no_box(tmp_path):
    cfg = CombatAudioConfig(
        input_path=str(tmp_path / "video.mp4"),
        audio_dir=str(tmp_path),
        mix_enabled=False, boxed=False,
    )
    paths = resolve_output_path(cfg, audio_count=2)
    assert paths[0].endswith("video_aligned_00.aac")
    assert paths[1].endswith("video_aligned_01.aac")


def test_resolve_output_path_boxed(tmp_path):
    cfg = CombatAudioConfig(
        input_path=str(tmp_path / "video.mp4"),
        audio_dir=str(tmp_path),
        mix_enabled=True, boxed=True,
    )
    paths = resolve_output_path(cfg, audio_count=3)
    assert len(paths) == 1
    assert paths[0].endswith(".mkv")


def test_resolve_output_path_uses_output_dir(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    cfg = CombatAudioConfig(
        input_path=str(tmp_path / "video.mp4"),
        audio_dir=str(tmp_path),
        output_dir=str(out),
        mix_enabled=True, boxed=False,
    )
    paths = resolve_output_path(cfg, audio_count=1)
    assert str(out) in paths[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/test_combat_audio_processor.py::test_validate_missing_input -v`
Expected: FAIL — `ImportError: cannot import name 'validate'`

- [ ] **Step 3: Implement validate and resolve_output_path**

Add to `src/core/processors/combat_audio.py`:

```python
import time

from src.core.config import CombatAudioConfig


def validate(config: CombatAudioConfig) -> tuple[bool, str | None]:
    """Validate config before processing. Returns (ok, error_message)."""
    if not os.path.exists(config.input_path):
        return False, f"输入文件不存在: {config.input_path}"
    if not os.path.isdir(config.audio_dir):
        return False, f"音频目录不存在: {config.audio_dir}"
    audio_files = scan_audio_dir(config.audio_dir)
    if not audio_files:
        return False, f"音频目录中没有音频文件: {config.audio_dir}"
    return True, None


def resolve_output_path(config: CombatAudioConfig, audio_count: int) -> list[str]:
    """Resolve output file paths based on config.
    Returns a list of paths: one per audio for non-boxed, one MKV for boxed."""
    stem = os.path.splitext(os.path.basename(config.input_path))[0]
    base_dir = config.output_dir or os.path.dirname(config.input_path)

    if config.boxed:
        ts = int(time.time() * 1000)
        return [os.path.join(base_dir, f"{stem}_{ts}.mkv")]

    tag = "mixed" if config.mix_enabled else "aligned"
    paths = []
    for i in range(audio_count):
        paths.append(os.path.join(base_dir, f"{stem}_{tag}_{i:02d}.aac"))
    return paths
```

Move the `from src.core.config import CombatAudioConfig` import to the top of the file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/test_combat_audio_processor.py -v`
Expected: 24 passed

- [ ] **Step 5: Commit**

```bash
git add src/core/processors/combat_audio.py tests/test_combat_audio_processor.py
git commit -m "feat(m2): add validate and resolve_output_path for combat audio"
```

---

### Task 6: BaseTaskPanel — make _init_base_layout opt-in

**Files:**
- Modify: `src/gui/task_panels/base_panel.py`

- [ ] **Step 1: Modify BaseTaskPanel.__init__ to accept init_layout parameter**

In `src/gui/task_panels/base_panel.py`, change the `__init__` method:

```python
def __init__(self, parent=None, *, init_layout: bool = True):
    super().__init__(parent)
    self._progress = ProgressSection()
    self._settings_scroll: QScrollArea | None = None
    self._settings_sidebar_root: QWidget | None = None
    if init_layout:
        self._init_base_layout()
```

- [ ] **Step 2: Verify PicSeqPanel still works**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/ -v`
Expected: all existing tests pass (PicSeqPanel doesn't pass `init_layout`, so default `True` keeps it unchanged)

- [ ] **Step 3: Commit**

```bash
git add src/gui/task_panels/base_panel.py
git commit -m "refactor: make BaseTaskPanel._init_base_layout opt-in via init_layout param"
```

---

### Task 7: AudioPlayerBar component

**Files:**
- Create: `src/gui/components/audio_player.py`

- [ ] **Step 1: Install PyQt6-QtMultimedia dependency**

Run: `cd /Users/liujiahao/jh-media-helper && pip install PyQt6-QtMultimedia`

- [ ] **Step 2: Implement AudioPlayerBar**

```python
# src/gui/components/audio_player.py
import os
import tempfile
import subprocess

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
)


def _format_time(ms: int) -> str:
    """Format milliseconds as MM:SS."""
    s = max(0, ms // 1000)
    return f"{s // 60:02d}:{s % 60:02d}"


class AudioPlayerBar(QWidget):
    """Shared audio playback bar based on QMediaPlayer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._temp_dir = tempfile.mkdtemp(prefix="jh_player_")
        self._current_temp: str | None = None

        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)

        self._init_ui()
        self._connect_signals()
        self.setVisible(False)

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(8)

        self._btn_play = QPushButton("\u25B6")
        self._btn_play.setFixedWidth(32)
        self._btn_play.clicked.connect(self._toggle_play)
        layout.addWidget(self._btn_play)

        self._name_label = QLabel("")
        self._name_label.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(self._name_label)

        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setStyleSheet("color: gray; font-size: 12px;")
        self._time_label.setFixedWidth(90)
        layout.addWidget(self._time_label)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.sliderMoved.connect(self._on_slider_moved)
        layout.addWidget(self._slider, 1)

        self._btn_stop = QPushButton("\u25A0")
        self._btn_stop.setFixedWidth(32)
        self._btn_stop.clicked.connect(self.stop)
        layout.addWidget(self._btn_stop)

    def _connect_signals(self):
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)

    def play_file(self, file_path: str, display_name: str = "") -> None:
        """Play a local audio file."""
        self.stop()
        name = display_name or os.path.basename(file_path)
        self._name_label.setText(name)
        self._player.setSource(QUrl.fromLocalFile(file_path))
        self._player.play()
        self.setVisible(True)

    def play_stream(self, file_path: str, stream_index: int, display_name: str = "") -> None:
        """Extract and play a specific audio stream from a video file."""
        self.stop()
        temp_path = os.path.join(self._temp_dir, f"stream_{stream_index}.aac")
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", file_path,
                    "-map", f"0:a:{stream_index}",
                    "-t", "10",
                    "-c:a", "aac",
                    temp_path,
                ],
                capture_output=True, timeout=30,
            )
        except Exception:
            return
        if not os.path.exists(temp_path):
            return
        self._current_temp = temp_path
        self.play_file(temp_path, display_name)

    def stop(self) -> None:
        """Stop playback."""
        self._player.stop()
        self._player.setSource(QUrl())

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def _toggle_play(self):
        if self.is_playing():
            self._player.pause()
        else:
            self._player.play()

    def _on_position_changed(self, position: int):
        if not self._slider.isSliderDown():
            self._slider.setValue(position)
        duration = self._player.duration()
        self._time_label.setText(f"{_format_time(position)} / {_format_time(duration)}")

    def _on_duration_changed(self, duration: int):
        self._slider.setRange(0, duration)

    def _on_slider_moved(self, position: int):
        self._player.setPosition(position)

    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._btn_play.setText("\u23F8")
        else:
            self._btn_play.setText("\u25B6")
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self._slider.setValue(0)

    def cleanup(self) -> None:
        """Clean up temporary files."""
        self.stop()
        import shutil
        try:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        except Exception:
            pass
```

- [ ] **Step 3: Verify import works**

Run: `cd /Users/liujiahao/jh-media-helper && python -c "from src.gui.components.audio_player import AudioPlayerBar; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/gui/components/audio_player.py
git commit -m "feat(m2): add AudioPlayerBar component with QMediaPlayer playback"
```

---

### Task 8: FFmpegWorker — add _run_combat_audio

**Files:**
- Modify: `src/worker/ffmpeg_worker.py`

- [ ] **Step 1: Add COMBAT_AUDIO dispatch in run()**

In `src/worker/ffmpeg_worker.py`, change the `run()` method:

```python
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
```

- [ ] **Step 2: Add imports for combat_audio**

Add to imports in `src/worker/ffmpeg_worker.py`:

```python
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.core.config import CombatAudioConfig
from src.core.processors import combat_audio
```

- [ ] **Step 3: Implement _run_combat_audio method**

Add to `FFmpegWorker` class in `src/worker/ffmpeg_worker.py`:

```python
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
    self.progress.emit(0, total, "[0/{0}] — 提取音频".format(total))
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
        config, audio_files, total, base_duration, adjusted_dir, "调整时长",
        self._adjust_one,
    )
    if adjusted_paths is None:
        return

    # Phase 3: Mix (parallel, only if mix_enabled)
    if config.mix_enabled:
        mixed_dir = os.path.join(tmp_dir, "mixed")
        os.makedirs(mixed_dir)
        final_paths = self._parallel_phase(
            config, list(zip(audio_files, adjusted_paths)), total,
            base_audio, mixed_dir, "混音",
            lambda cfg, item, idx, base, out_dir: self._mix_one(cfg, item, idx, base, out_dir),
        )
        if final_paths is None:
            return
    else:
        final_paths = adjusted_paths

    if self._emit_cancelled_if_needed():
        return

    # Phase 4: Mux to MKV (optional)
    output_paths = combat_audio.resolve_output_path(config, audio_count=total)
    if config.boxed and not is_audio:
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

def _parallel_phase(self, config, items, total, extra_arg, out_dir, phase_name, func):
    """Run a phase in parallel using ThreadPoolExecutor. Returns list of output paths or None on cancel."""
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
            idx, path = future.result()
            results[idx] = path
            completed += 1
            name = os.path.basename(items[idx] if isinstance(items[idx], str) else items[idx][0])
            self.progress.emit(completed, total, f"[{completed}/{total}] {name} — {phase_name}")
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
    return output_path
```

- [ ] **Step 4: Run existing tests to ensure no regression**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/ -v`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add src/worker/ffmpeg_worker.py
git commit -m "feat(m2): add _run_combat_audio with parallel pipeline in FFmpegWorker"
```

---

### Task 9: CombatAudioPanel — upper zone (file selectors + params)

**Files:**
- Create: `src/gui/task_panels/combat_audio_panel.py`

- [ ] **Step 1: Create CombatAudioPanel with upper zone layout**

```python
# src/gui/task_panels/combat_audio_panel.py
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.config import CombatAudioConfig, TaskType
from src.core.processors import combat_audio
from src.gui.components.audio_player import AudioPlayerBar
from src.gui.components.file_selector import FileSelector
from src.gui.components.progress_section import ProgressSection
from src.gui.task_panels.base_panel import BaseTaskPanel

_MEDIA_FILTER = "媒体文件 (*.mp4 *.mkv *.mov *.avi *.aac *.mp3 *.wav *.flac);;所有文件 (*)"


class CombatAudioPanel(BaseTaskPanel):
    def __init__(self, parent=None):
        self._input_streams: list[combat_audio.AudioStreamInfo] = []
        self._bg_files: list[combat_audio.AudioFileInfo] = []
        self._is_pure_audio = False
        self._input_duration = 0.0
        super().__init__(parent, init_layout=False)
        self._init_custom_layout()

    # --- Abstract method stubs (not used since init_layout=False) ---
    def _build_left_panel(self, layout):
        pass

    def _build_settings_panel(self, layout):
        pass

    # --- Custom 4-zone layout ---

    def _init_custom_layout(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(20, 20, 20, 20)
        main.setSpacing(12)

        # Upper zone: file selectors (left) + params (right)
        upper = QHBoxLayout()
        upper.setSpacing(16)
        self._build_upper_left(upper)
        self._build_upper_right(upper)
        main.addLayout(upper)

        # Middle zone: tables + player
        self._build_middle_zone(main)

        # Lower zone: progress
        main.addWidget(self._progress)

        main.addStretch()

    def _build_upper_left(self, parent_layout: QHBoxLayout):
        left = QVBoxLayout()
        left.setSpacing(10)

        self._input_selector = FileSelector(
            label="输入视频/音频:",
            placeholder="选择文件...",
            dialog_mode="file",
            file_filter=_MEDIA_FILTER,
        )
        self._input_selector.path_changed.connect(self._on_input_changed)
        left.addWidget(self._input_selector)

        self._audio_dir_selector = FileSelector(
            label="音频目录:",
            placeholder="选择背景音乐文件夹...",
            dialog_mode="directory",
        )
        self._audio_dir_selector.path_changed.connect(self._on_audio_dir_changed)
        left.addWidget(self._audio_dir_selector)

        self._info_group = QGroupBox("文件信息")
        info_layout = QVBoxLayout(self._info_group)
        self._info_label = QLabel("未选择文件")
        self._info_label.setStyleSheet("color: gray;")
        info_layout.addWidget(self._info_label)
        left.addWidget(self._info_group)

        left.addStretch()
        parent_layout.addLayout(left, 2)

    def _build_upper_right(self, parent_layout: QHBoxLayout):
        right = QVBoxLayout()
        right.setSpacing(16)

        # Mix params group
        mix_group = QGroupBox("混音参数")
        mix_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        mix_layout = QVBoxLayout(mix_group)
        mix_layout.setSpacing(12)

        self._mix_checkbox = QCheckBox("混合原始音轨")
        self._mix_checkbox.setChecked(True)
        self._mix_checkbox.toggled.connect(self._on_mix_toggled)
        mix_layout.addWidget(self._mix_checkbox)

        thread_row = QHBoxLayout()
        thread_row.addWidget(QLabel("并行线程数"))
        self._thread_spin = QSpinBox()
        self._thread_spin.setRange(1, 16)
        self._thread_spin.setValue(1)
        thread_row.addWidget(self._thread_spin, 1)
        mix_layout.addLayout(thread_row)

        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("原视频响度"))
        self._volume_spin = QDoubleSpinBox()
        self._volume_spin.setRange(0.0, 1.0)
        self._volume_spin.setSingleStep(0.1)
        self._volume_spin.setValue(0.6)
        vol_row.addWidget(self._volume_spin, 1)
        mix_layout.addLayout(vol_row)

        right.addWidget(mix_group)

        # Output settings group
        out_group = QGroupBox("输出设置")
        out_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        out_layout = QVBoxLayout(out_group)
        out_layout.setSpacing(12)

        self._boxed_checkbox = QCheckBox("封装为 MKV")
        out_layout.addWidget(self._boxed_checkbox)

        self._output_selector = FileSelector(
            label="输出目录:",
            placeholder="与输入文件同级",
            dialog_mode="directory",
        )
        out_layout.addWidget(self._output_selector)

        right.addWidget(out_group)
        right.addStretch()
        parent_layout.addLayout(right, 1)

    # --- Middle zone placeholder (implemented in next task) ---

    def _build_middle_zone(self, parent_layout: QVBoxLayout):
        mid = QHBoxLayout()
        mid.setSpacing(12)
        self._build_input_tracks_table(mid)
        self._build_bg_music_table(mid)
        parent_layout.addLayout(mid)

        self._player = AudioPlayerBar()
        parent_layout.addWidget(self._player)

    def _build_input_tracks_table(self, parent_layout: QHBoxLayout):
        group = QGroupBox("输入音轨")
        layout = QVBoxLayout(group)
        self._tracks_table = QTableWidget(0, 5)
        self._tracks_table.setHorizontalHeaderLabels(["", "索引", "编码", "采样率", "声道"])
        self._tracks_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tracks_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._tracks_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tracks_table.verticalHeader().setVisible(False)
        self._tracks_table.setMaximumHeight(150)
        layout.addWidget(self._tracks_table)

        self._track_play_buttons: list[QPushButton] = []
        self._track_radio_group = QButtonGroup(self)

        parent_layout.addWidget(group, 1)

    def _build_bg_music_table(self, parent_layout: QHBoxLayout):
        group = QGroupBox("背景音乐")
        layout = QVBoxLayout(group)
        self._bg_table = QTableWidget(0, 4)
        self._bg_table.setHorizontalHeaderLabels(["序号", "文件名", "时长", ""])
        self._bg_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._bg_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._bg_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._bg_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._bg_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._bg_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._bg_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._bg_table.verticalHeader().setVisible(True)
        self._bg_table.verticalHeader().setSectionsMovable(True)
        self._bg_table.verticalHeader().sectionMoved.connect(self._on_bg_row_moved)
        self._bg_table.setDragDropMode(QTableWidget.DragDropMode.InternalMove)
        self._bg_table.setMaximumHeight(200)
        layout.addWidget(self._bg_table)

        self._bg_play_buttons: list[QPushButton] = []

        parent_layout.addWidget(group, 1)

    # --- Signal handlers ---

    def _on_input_changed(self, path: str):
        if not path or not os.path.exists(path):
            self._input_streams = []
            self._is_pure_audio = False
            self._input_duration = 0.0
            self._info_label.setText("未选择文件")
            self._refresh_tracks_table()
            self._update_param_states()
            return

        self._is_pure_audio = combat_audio.is_pure_audio(path)
        self._input_duration = combat_audio.probe_duration(path)

        if self._is_pure_audio:
            ext = os.path.splitext(path)[1].upper().lstrip(".")
            self._input_streams = [combat_audio.AudioStreamInfo(
                index=0, codec=ext, sample_rate=0, channels=0, channel_layout="",
            )]
        else:
            self._input_streams = combat_audio.probe_audio_streams(path)

        dur_str = self._format_duration(self._input_duration)
        file_type = "纯音频" if self._is_pure_audio else os.path.splitext(path)[1].upper().lstrip(".")
        self._info_label.setText(
            f"类型: {file_type}\n时长: {dur_str}\n音轨数: {len(self._input_streams)}"
        )

        self._refresh_tracks_table()
        self._update_param_states()

    def _on_audio_dir_changed(self, path: str):
        if not path or not os.path.isdir(path):
            self._bg_files = []
            self._refresh_bg_table()
            return

        self._bg_files = combat_audio.scan_audio_dir(path)
        # Probe durations
        for f in self._bg_files:
            f.duration = combat_audio.probe_duration(f.path)
        self._refresh_bg_table()
        self._update_info_bg_count()

    def _on_mix_toggled(self, checked: bool):
        self._volume_spin.setEnabled(checked)
        self._update_param_states()

    def _update_param_states(self):
        """Update parameter enable/disable states based on current selections."""
        is_audio = self._is_pure_audio
        mix_on = self._mix_checkbox.isChecked()

        self._volume_spin.setEnabled(mix_on)
        # Boxed only available for video input
        self._boxed_checkbox.setEnabled(not is_audio)
        if is_audio:
            self._boxed_checkbox.setChecked(False)

    def _update_info_bg_count(self):
        text = self._info_label.text()
        lines = text.split("\n")
        # Remove old bg count line if present
        lines = [l for l in lines if not l.startswith("背景音乐:")]
        lines.append(f"背景音乐: {len(self._bg_files)} 个文件")
        self._info_label.setText("\n".join(lines))

    # --- Table refresh ---

    def _refresh_tracks_table(self):
        self._tracks_table.setRowCount(0)
        self._track_play_buttons.clear()
        # Clear old radio buttons from group
        for btn in self._track_radio_group.buttons():
            self._track_radio_group.removeButton(btn)

        for stream in self._input_streams:
            row = self._tracks_table.rowCount()
            self._tracks_table.insertRow(row)

            radio = QRadioButton()
            self._track_radio_group.addButton(radio, stream.index)
            radio_widget = QWidget()
            radio_layout = QHBoxLayout(radio_widget)
            radio_layout.addWidget(radio)
            radio_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            radio_layout.setContentsMargins(0, 0, 0, 0)
            self._tracks_table.setCellWidget(row, 0, radio_widget)

            self._tracks_table.setItem(row, 1, QTableWidgetItem(f"#{stream.index}"))
            self._tracks_table.setItem(row, 2, QTableWidgetItem(stream.codec.upper()))

            sr = f"{stream.sample_rate // 1000}kHz" if stream.sample_rate else "?"
            self._tracks_table.setItem(row, 3, QTableWidgetItem(sr))

            ch = self._channel_label(stream)
            self._tracks_table.setItem(row, 4, QTableWidgetItem(ch))

        # Auto-select first track
        if self._input_streams:
            first_radio = self._track_radio_group.button(self._input_streams[0].index)
            if first_radio:
                first_radio.setChecked(True)

    def _refresh_bg_table(self):
        self._bg_table.setRowCount(0)
        self._bg_play_buttons.clear()

        for i, f in enumerate(self._bg_files):
            row = self._bg_table.rowCount()
            self._bg_table.insertRow(row)

            num_item = QTableWidgetItem(f"{i + 1:02d}")
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._bg_table.setItem(row, 0, num_item)

            name_item = QTableWidgetItem(f.filename)
            name_item.setData(Qt.ItemDataRole.UserRole, f.path)
            self._bg_table.setItem(row, 1, name_item)

            dur_str = self._format_duration(f.duration)
            self._bg_table.setItem(row, 2, QTableWidgetItem(dur_str))

            btn = QPushButton("\u25B6")
            btn.setFixedWidth(32)
            btn.clicked.connect(lambda checked, path=f.path, name=f.filename: self._player.play_file(path, name))
            self._bg_table.setCellWidget(row, 3, btn)
            self._bg_play_buttons.append(btn)

    def _on_bg_row_moved(self, logical: int, old_visual: int, new_visual: int):
        """Reorder _bg_files after drag-drop and refresh numbering."""
        if old_visual < len(self._bg_files):
            item = self._bg_files.pop(old_visual)
            self._bg_files.insert(new_visual, item)
            self._refresh_bg_table()

    # --- Helpers ---

    @staticmethod
    def _format_duration(seconds: float) -> str:
        s = int(seconds)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    @staticmethod
    def _channel_label(stream: combat_audio.AudioStreamInfo) -> str:
        if stream.channel_layout:
            labels = {"stereo": "立体声", "mono": "单声道", "5.1": "5.1声道", "5.1(side)": "5.1声道"}
            return labels.get(stream.channel_layout, stream.channel_layout)
        if stream.channels == 1:
            return "单声道"
        if stream.channels == 2:
            return "立体声"
        if stream.channels == 6:
            return "5.1声道"
        return f"{stream.channels}声道" if stream.channels else "?"

    # --- BaseTaskPanel abstract methods ---

    def validate(self) -> tuple[bool, int, str | None]:
        input_path = self._input_selector.path()
        if not input_path:
            return False, 0, "请先选择输入文件"
        audio_dir = self._audio_dir_selector.path()
        if not audio_dir:
            return False, 0, "请先选择音频目录"

        config = self._build_combat_config()
        if config is None:
            return False, 0, "配置无效"

        ok, err = combat_audio.validate(config)
        if not ok:
            return False, 0, err
        audio_count = len(self._bg_files) if self._bg_files else len(combat_audio.scan_audio_dir(audio_dir))
        return True, audio_count, None

    def build_config(self) -> CombatAudioConfig | None:
        return self._build_combat_config()

    def get_task_type(self) -> TaskType:
        return TaskType.COMBAT_AUDIO

    def _build_combat_config(self) -> CombatAudioConfig | None:
        input_path = self._input_selector.path()
        audio_dir = self._audio_dir_selector.path()
        if not input_path or not audio_dir:
            return None

        selected_track = self._track_radio_group.checkedId()
        if selected_track < 0:
            selected_track = 0

        audio_order = [f.filename for f in self._bg_files]

        return CombatAudioConfig(
            input_path=input_path,
            audio_dir=audio_dir,
            output_dir=self._output_selector.path() or None,
            mix_enabled=self._mix_checkbox.isChecked(),
            volume=self._volume_spin.value(),
            boxed=self._boxed_checkbox.isChecked(),
            thread_count=self._thread_spin.value(),
            audio_stream_index=selected_track,
            audio_order=audio_order,
        )
```

- [ ] **Step 2: Verify import works**

Run: `cd /Users/liujiahao/jh-media-helper && python -c "from src.gui.task_panels.combat_audio_panel import CombatAudioPanel; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/gui/task_panels/combat_audio_panel.py
git commit -m "feat(m2): add CombatAudioPanel with 4-zone custom layout"
```

---

### Task 10: CombatAudioPanel — preview playback for input tracks

**Files:**
- Modify: `src/gui/task_panels/combat_audio_panel.py`

- [ ] **Step 1: Add play buttons to input tracks table**

In `_refresh_tracks_table`, the tracks table currently has 5 columns. Add a 6th column for the play button. Update `_build_input_tracks_table`:

```python
def _build_input_tracks_table(self, parent_layout: QHBoxLayout):
    group = QGroupBox("输入音轨")
    layout = QVBoxLayout(group)
    self._tracks_table = QTableWidget(0, 6)
    self._tracks_table.setHorizontalHeaderLabels(["", "索引", "编码", "采样率", "声道", ""])
    self._tracks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    self._tracks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    self._tracks_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    self._tracks_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
    self._tracks_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
    self._tracks_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
    self._tracks_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    self._tracks_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    self._tracks_table.verticalHeader().setVisible(False)
    self._tracks_table.setMaximumHeight(150)
    layout.addWidget(self._tracks_table)

    self._track_play_buttons: list[QPushButton] = []
    self._track_radio_group = QButtonGroup(self)

    parent_layout.addWidget(group, 1)
```

- [ ] **Step 2: Add play button in _refresh_tracks_table**

At the end of the per-stream loop in `_refresh_tracks_table`, add:

```python
btn = QPushButton("\u25B6")
btn.setFixedWidth(32)
if self._is_pure_audio:
    btn.clicked.connect(
        lambda checked, p=self._input_selector.path(), n=stream.codec:
            self._player.play_file(p, f"输入 {n}")
    )
else:
    btn.clicked.connect(
        lambda checked, p=self._input_selector.path(), si=stream.index, n=f"输入 #{stream.index} {stream.codec}":
            self._player.play_stream(p, si, n)
    )
self._tracks_table.setCellWidget(row, 5, btn)
self._track_play_buttons.append(btn)
```

- [ ] **Step 3: Verify no regressions**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/ -v`
Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add src/gui/task_panels/combat_audio_panel.py
git commit -m "feat(m2): add preview playback for input tracks and background music"
```

---

### Task 11: CombatAudioPanel — preview mix (trial listen)

**Files:**
- Modify: `src/gui/task_panels/combat_audio_panel.py`

- [ ] **Step 1: Add trial listen method and state tracking**

Add to `CombatAudioPanel`:

```python
def _get_preview_btn_enabled(self) -> bool:
    """Check if preview mix button should be enabled."""
    if not self._mix_checkbox.isChecked():
        return False
    if self._track_radio_group.checkedId() < 0:
        return False
    if not self._bg_table.selectionModel().hasSelection():
        return False
    return True

def preview_mix(self) -> None:
    """Generate and play a 5-second preview mix."""
    if not self._get_preview_btn_enabled():
        return

    input_path = self._input_selector.path()
    stream_idx = self._track_radio_group.checkedId()
    bg_row = self._bg_table.currentRow()
    if bg_row < 0 or bg_row >= len(self._bg_files):
        return
    bg_path = self._bg_files[bg_row].path
    volume = self._volume_spin.value()

    import tempfile
    import subprocess
    temp_dir = tempfile.mkdtemp(prefix="jh_preview_")

    # If video input, extract selected audio track first
    if not self._is_pure_audio:
        base_audio = os.path.join(temp_dir, "base.aac")
        cmd = combat_audio.build_extract_command(input_path, stream_idx, base_audio)
        subprocess.run(cmd, capture_output=True, timeout=30)
    else:
        base_audio = input_path

    preview_path = os.path.join(temp_dir, "preview.aac")
    cmd = combat_audio.build_preview_command(base_audio, bg_path, volume, preview_path)
    subprocess.run(cmd, capture_output=True, timeout=30)

    if os.path.exists(preview_path):
        self._player.play_file(preview_path, "试听混合")
```

- [ ] **Step 2: Commit**

```bash
git add src/gui/task_panels/combat_audio_panel.py
git commit -m "feat(m2): add preview mix (trial listen) functionality"
```

---

### Task 12: MainWindow integration

**Files:**
- Modify: `src/gui/main_window.py`

- [ ] **Step 1: Add CombatAudioPanel tab and imports**

Add import at top of `src/gui/main_window.py`:

```python
from src.gui.task_panels.combat_audio_panel import CombatAudioPanel
```

In `_init_ui`, after the PicSeqPanel tab and before `# Future: M2/M3 tabs will be added here`, replace the comment:

```python
# CombatAudio tab
self._combat_panel = CombatAudioPanel()
self._tabs.addTab(self._combat_panel, "音视频混合")
```

- [ ] **Step 2: Add "试听混合" button to action bar**

In `_init_ui`, after creating the action bar buttons but before creating `_action_bar_wrap`, add:

```python
self._btn_preview = self._action_bar.add_button("试听混合", role="secondary", enabled=False)
```

Connect the signal in `_connect_signals`:

```python
self._btn_preview.clicked.connect(self._on_preview)
```

- [ ] **Step 3: Add _on_preview handler and tab-change logic**

Add to `MainWindow`:

```python
def _on_preview(self):
    panel = self._get_active_panel()
    if isinstance(panel, CombatAudioPanel):
        panel.preview_mix()
```

Update `_on_tab_changed` to manage preview button visibility:

```python
def _on_tab_changed(self, index: int):
    current_widget = self._tabs.widget(index)
    show = isinstance(current_widget, BaseTaskPanel)
    self._action_bar_wrap.setVisible(show)
    # Only show preview button for CombatAudioPanel
    self._btn_preview.setVisible(isinstance(current_widget, CombatAudioPanel))
```

- [ ] **Step 4: Generalize _on_enqueue to support both task types**

Replace the current `_on_enqueue` method:

```python
def _on_enqueue(self):
    panel = self._get_active_panel()
    if panel is None:
        return
    ok, count, err = panel.validate()
    if not ok:
        QMessageBox.warning(self, "校验失败", err)
        return
    config = panel.build_config()
    if config is None:
        return

    # Resolve output path based on task type
    task_type = panel.get_task_type()
    if task_type == TaskType.PIC_SEQ:
        output_path = _resolve_output_path(config)
        input_path = config.input_dir
    elif task_type == TaskType.COMBAT_AUDIO:
        from src.core.processors.combat_audio import resolve_output_path as combat_resolve
        paths = combat_resolve(config, audio_count=count)
        output_path = paths[0] if paths else ""
        input_path = config.input_path
    else:
        output_path = ""
        input_path = ""

    task = QueueTask.create(
        task_type=task_type,
        config=config,
        input_path=input_path,
        output_path=output_path,
    )
    self._queue_manager.add_task(task)
    self._queue_manager.save()
    self._queue_tab.refresh()
```

Also update the import to include `TaskType`:

```python
from src.core.config import TaskType
```

- [ ] **Step 5: Update _display_name_from_config for CombatAudioConfig**

```python
@staticmethod
def _display_name_from_config(config) -> str:
    input_dir = getattr(config, "input_dir", None)
    input_path = getattr(config, "input_path", None)
    path = input_dir or input_path
    if path:
        return os.path.basename(path.rstrip(os.sep)) or path
    return "当前任务"
```

- [ ] **Step 6: Run all tests**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/ -v`
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add src/gui/main_window.py
git commit -m "feat(m2): integrate CombatAudioPanel into MainWindow with preview and enqueue"
```

---

### Task 13: QueueTab — support COMBAT_AUDIO task type

**Files:**
- Modify: `src/gui/queue_tab.py`

- [ ] **Step 1: Add combat_audio import and format label**

Add to imports in `src/gui/queue_tab.py`:

```python
from src.core.config import CombatAudioConfig
from src.core.processors import combat_audio
```

Update `_FORMAT_LABELS` to handle combat audio tasks (which don't have an `output_format` key):

No change needed to `_FORMAT_LABELS` — it already returns `"?"` for unknown formats, which is fine for combat audio tasks.

- [ ] **Step 2: Update _run_next to handle COMBAT_AUDIO**

In `_run_next`, after the `if task.task_type == TaskType.PIC_SEQ:` block, add:

```python
elif task.task_type == TaskType.COMBAT_AUDIO:
    cfg = CombatAudioConfig.from_dict(task.config)
    ok, err = combat_audio.validate(cfg)
    if not ok:
        task.status = TaskStatus.FAILED
        task.error = err
        self._queue_manager.save()
        self._refresh_table()
        self._run_next()
        return
    audio_files = cfg.audio_order or [f.filename for f in combat_audio.scan_audio_dir(cfg.audio_dir)]
    count = len(audio_files)
```

- [ ] **Step 3: Update display format for combat audio in table**

In `_refresh_table`, update the format column for combat audio:

Replace the format label line:

```python
fmt_label = _FORMAT_LABELS.get(task.config.get("output_format", ""), "?")
```

with:

```python
if task.task_type == TaskType.COMBAT_AUDIO:
    if task.config.get("boxed"):
        fmt_label = "MKV 封装"
    elif task.config.get("mix_enabled", True):
        fmt_label = "混合音频"
    else:
        fmt_label = "时长对齐"
else:
    fmt_label = _FORMAT_LABELS.get(task.config.get("output_format", ""), "?")
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/ -v`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add src/gui/queue_tab.py
git commit -m "feat(m2): support COMBAT_AUDIO task type in queue execution and display"
```

---

### Task 14: Cleanup and close event handling

**Files:**
- Modify: `src/gui/task_panels/combat_audio_panel.py`
- Modify: `src/gui/main_window.py`

- [ ] **Step 1: Add cleanup on panel destruction**

In `CombatAudioPanel`, add:

```python
def cleanup(self):
    """Clean up player temp files."""
    self._player.cleanup()
```

- [ ] **Step 2: Call cleanup from MainWindow.closeEvent**

In `MainWindow.closeEvent`, before `event.accept()`, add:

```python
self._combat_panel.cleanup()
```

- [ ] **Step 3: Run all tests**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/ -v`
Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add src/gui/task_panels/combat_audio_panel.py src/gui/main_window.py
git commit -m "feat(m2): add cleanup for player temp files on close"
```

---

### Task 15: Final integration test — manual verification

- [ ] **Step 1: Launch the application**

Run: `cd /Users/liujiahao/jh-media-helper && python -m src.main` (or whatever the entry point is)

Verify:
1. Three feature tabs visible: "图片序列转视频", "音视频混合", "设置"
2. Switching to "音视频混合" tab shows the 4-zone layout
3. Action bar shows "试听混合", "取消", "加入队列", "开始处理"

- [ ] **Step 2: Test file selection**

1. Select a video file — verify tracks table populates
2. Select an audio directory — verify background music table populates with durations
3. Select a pure audio file — verify single track, "封装为 MKV" disabled

- [ ] **Step 3: Test preview playback**

1. Click [▶] on an input track — verify player bar appears and plays
2. Click [▶] on a background music — verify player bar switches

- [ ] **Step 4: Test parameter linkage**

1. Uncheck "混合原始音轨" — verify "原视频响度" disabled, "试听混合" disabled
2. Re-check — verify both re-enabled
3. Select pure audio input — verify "封装为 MKV" disabled

- [ ] **Step 5: Test enqueue**

1. Configure a task and click "加入队列"
2. Switch to queue tab — verify task appears with correct type and format label

- [ ] **Step 6: Commit final state**

```bash
git add -A
git commit -m "feat(m2): complete M2 CombatVideoWithAudios integration"
```
