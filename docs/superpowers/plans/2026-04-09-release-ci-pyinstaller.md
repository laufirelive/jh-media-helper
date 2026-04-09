# Release CI PyInstaller Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repeatable PyInstaller-based release pipeline that builds self-contained macOS Apple Silicon and Windows x64 desktop artifacts, checks for `ffmpeg` and `ffprobe` at startup, and publishes versioned GitHub Release assets from tags.

**Architecture:** Keep release concerns in a thin runtime helper plus packaging config, leaving the existing app flow intact. The app entrypoint gains a small startup guard for FFmpeg detection, PyInstaller gets a single cross-platform spec file, and GitHub Actions orchestrates matrix builds and versioned release uploads.

**Tech Stack:** Python 3.12+, PyQt6, PyInstaller, pytest, GitHub Actions

---

## File Structure

### New files

- `src/core/runtime_env.py`
  Release/runtime helper functions for PyInstaller detection and `ffmpeg` / `ffprobe` availability checks.
- `tests/test_runtime_env.py`
  Pure unit tests for runtime helper behavior.
- `tests/test_main_entry.py`
  Entry-point tests for startup guard behavior, including the missing-FFmpeg dialog flow.
- `jh-media-helper.spec`
  Single PyInstaller spec for Windows `onedir` output and macOS `.app` bundle generation.
- `.github/workflows/build.yml`
  Dual-platform GitHub Actions workflow for manual builds and tag-triggered releases.
- `docs/superpowers/plans/2026-04-09-release-ci-pyinstaller.md`
  This execution plan.

### Modified files

- `main.py`
  Add `freeze_support()`, startup dependency check, and a small GUI error dialog path before `MainWindow` creation.
- `README.md`
  Replace the current “适合用 PyInstaller” note with concrete release-download and runtime dependency instructions.

---

### Task 1: Add Runtime Helper Module

**Files:**
- Create: `src/core/runtime_env.py`
- Test: `tests/test_runtime_env.py`

- [ ] **Step 1: Write the failing runtime helper tests**

```python
from unittest.mock import patch

from src.core.runtime_env import (
    get_missing_ffmpeg_tools,
    has_required_ffmpeg_tools,
    is_frozen,
)


class TestIsFrozen:
    def test_returns_false_when_sys_frozen_missing(self):
        with patch("src.core.runtime_env.getattr", return_value=False):
            assert is_frozen() is False


class TestGetMissingFfmpegTools:
    @patch("src.core.runtime_env.shutil.which")
    def test_reports_both_tools_when_missing(self, mock_which):
        mock_which.return_value = None
        assert get_missing_ffmpeg_tools() == ["ffmpeg", "ffprobe"]

    @patch("src.core.runtime_env.shutil.which")
    def test_reports_only_ffprobe_when_ffmpeg_exists(self, mock_which):
        mock_which.side_effect = ["/usr/local/bin/ffmpeg", None]
        assert get_missing_ffmpeg_tools() == ["ffprobe"]


class TestHasRequiredFfmpegTools:
    @patch("src.core.runtime_env.get_missing_ffmpeg_tools")
    def test_returns_true_when_no_tools_missing(self, mock_missing):
        mock_missing.return_value = []
        assert has_required_ffmpeg_tools() is True

    @patch("src.core.runtime_env.get_missing_ffmpeg_tools")
    def test_returns_false_when_any_tool_missing(self, mock_missing):
        mock_missing.return_value = ["ffprobe"]
        assert has_required_ffmpeg_tools() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/test_runtime_env.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.runtime_env'`

- [ ] **Step 3: Write the minimal runtime helper implementation**

```python
import shutil
import sys


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_missing_ffmpeg_tools() -> list[str]:
    missing: list[str] = []
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            missing.append(tool)
    return missing


def has_required_ffmpeg_tools() -> bool:
    return get_missing_ffmpeg_tools() == []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/test_runtime_env.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/runtime_env.py tests/test_runtime_env.py
git commit -m "test: add runtime environment helpers"
```

---

### Task 2: Guard App Startup When FFmpeg Is Missing

**Files:**
- Modify: `main.py`
- Test: `tests/test_main_entry.py`

- [ ] **Step 1: Write the failing entry-point tests**

```python
from unittest.mock import Mock, patch

import main


@patch("main.sys.exit")
@patch("main.QMessageBox.critical")
@patch("main.has_required_ffmpeg_tools", return_value=False)
@patch("main.QApplication")
def test_main_shows_dialog_and_exits_when_ffmpeg_tools_missing(
    mock_app_cls,
    mock_has_tools,
    mock_critical,
    mock_exit,
):
    app = Mock()
    mock_app_cls.return_value = app

    main.main()

    mock_critical.assert_called_once()
    mock_exit.assert_called_once_with(1)


@patch("main.sys.exit")
@patch("main.MainWindow")
@patch("main.has_required_ffmpeg_tools", return_value=True)
@patch("main.QApplication")
def test_main_starts_window_when_ffmpeg_tools_exist(
    mock_app_cls,
    mock_has_tools,
    mock_window_cls,
    mock_exit,
):
    app = Mock()
    app.exec.return_value = 0
    mock_app_cls.return_value = app
    window = mock_window_cls.return_value

    main.main()

    window.show.assert_called_once()
    mock_exit.assert_called_once_with(0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/test_main_entry.py -q`

Expected: FAIL because `main.py` does not yet import `QMessageBox` or `has_required_ffmpeg_tools`

- [ ] **Step 3: Update `main.py` with a startup guard and dialog**

```python
import multiprocessing
import platform
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from src.core.runtime_env import get_missing_ffmpeg_tools, has_required_ffmpeg_tools
from src.gui.main_window import MainWindow


def _build_missing_ffmpeg_message() -> str:
    lines = [
        "未检测到 ffmpeg 或 ffprobe。",
        "请先安装 FFmpeg 后重新启动应用。",
        "",
    ]
    if platform.system() == "Windows":
        lines.append("推荐安装方式：winget install ffmpeg")
    else:
        lines.append("推荐安装方式：brew install ffmpeg")
    lines.append("")
    lines.append(f"缺失工具: {', '.join(get_missing_ffmpeg_tools())}")
    return "\n".join(lines)


def main():
    multiprocessing.freeze_support()

    app = QApplication(sys.argv)
    app.setApplicationName("jh-media-helper")

    if not has_required_ffmpeg_tools():
        QMessageBox.critical(None, "缺少 FFmpeg", _build_missing_ffmpeg_message())
        sys.exit(1)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/test_main_entry.py -q`

Expected: PASS

- [ ] **Step 5: Run the focused startup test suite**

Run: `PYTHONPATH=. pytest tests/test_runtime_env.py tests/test_main_entry.py -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main_entry.py src/core/runtime_env.py tests/test_runtime_env.py
git commit -m "feat: guard startup on ffmpeg availability"
```

---

### Task 3: Add PyInstaller Spec For Windows and macOS

**Files:**
- Create: `jh-media-helper.spec`

- [ ] **Step 1: Write the spec file**

```python
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = [
    "PyQt6.QtMultimedia",
]
hiddenimports += collect_submodules("src")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "tkinter",
        "unittest",
        "test",
        "tests",
    ],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="jh-media-helper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="jh-media-helper",
)

app = BUNDLE(
    coll,
    name="jh-media-helper.app",
    icon=None,
    bundle_identifier=None,
)
```

- [ ] **Step 2: Run PyInstaller locally to verify the spec is accepted**

Run: `PYTHONPATH=. pyinstaller --clean jh-media-helper.spec`

Expected: PASS and create `dist/jh-media-helper/` on Windows-compatible builds or `dist/jh-media-helper.app` on macOS

- [ ] **Step 3: Verify the macOS artifact shape**

Run: `find dist -maxdepth 2 \\( -name 'jh-media-helper.app' -o -name 'jh-media-helper' \\) | sort`

Expected: output contains `dist/jh-media-helper.app`

- [ ] **Step 4: Commit**

```bash
git add jh-media-helper.spec
git commit -m "build: add pyinstaller spec"
```

---

### Task 4: Add GitHub Actions Build and Release Workflow

**Files:**
- Create: `.github/workflows/build.yml`

- [ ] **Step 1: Write the workflow**

```yaml
name: Build Portable Release

on:
  push:
    tags:
      - "v*"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  build:
    strategy:
      matrix:
        include:
          - os: windows-latest
            artifact_suffix: Windows
            package_path: dist/jh-media-helper
          - os: macos-latest
            artifact_suffix: macOS-ARM
            package_path: dist/jh-media-helper.app

    runs-on: ${{ matrix.os }}

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pyinstaller

      - name: Build app
        run: pyinstaller --clean jh-media-helper.spec

      - name: Derive version label
        shell: bash
        run: |
          if [[ "${GITHUB_REF}" == refs/tags/v* ]]; then
            echo "VERSION_LABEL=${GITHUB_REF_NAME}" >> "$GITHUB_ENV"
          else
            echo "VERSION_LABEL=manual-${GITHUB_RUN_NUMBER}" >> "$GITHUB_ENV"
          fi

      - name: Create bundled README
        shell: bash
        run: |
          cat > README.txt <<'EOF'
          jh-media-helper portable build

          This package already includes Python and all Python dependencies.
          Before running the app, install both ffmpeg and ffprobe.

          Windows:
            winget install ffmpeg

          macOS:
            brew install ffmpeg
          EOF

      - name: Package zip
        shell: bash
        run: |
          mkdir package
          cp README.txt package/README.txt
          cp -R "${{ matrix.package_path }}" package/
          cd package
          zip -r "../jh-media-helper-${VERSION_LABEL}-${{ matrix.artifact_suffix }}.zip" .

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: jh-media-helper-${{ env.VERSION_LABEL }}-${{ matrix.artifact_suffix }}
          path: jh-media-helper-${{ env.VERSION_LABEL }}-${{ matrix.artifact_suffix }}.zip

      - name: Upload to Release
        if: startsWith(github.ref, 'refs/tags/')
        uses: softprops/action-gh-release@v2
        with:
          files: jh-media-helper-${{ env.VERSION_LABEL }}-${{ matrix.artifact_suffix }}.zip
```

- [ ] **Step 2: Validate workflow syntax locally**

Run: `python - <<'PY'\nimport yaml, pathlib\npath = pathlib.Path('.github/workflows/build.yml')\nprint(yaml.safe_load(path.read_text())['name'])\nPY`

Expected: prints `Build Portable Release`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/build.yml
git commit -m "ci: add release build workflow"
```

---

### Task 5: Update User-Facing Release Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the packaging section with concrete release instructions**

```markdown
## 下载发布版

从 GitHub Releases 下载对应平台的压缩包：

- macOS Apple Silicon: `jh-media-helper-vX.Y.Z-macOS-ARM.zip`
- Windows x64: `jh-media-helper-vX.Y.Z-Windows.zip`

解压后即可直接运行：

- macOS: `jh-media-helper.app`
- Windows: `jh-media-helper.exe`

发布版已内置 Python 运行时和 Python 依赖，无需额外安装 Python。

## FFmpeg 依赖

发布版和源码运行都要求系统中可直接找到 `ffmpeg` 与 `ffprobe`。

macOS:

```bash
brew install ffmpeg
```

Windows:

```bash
winget install ffmpeg
```

如果缺少上述依赖，程序启动时会弹窗提示并退出。
```

- [ ] **Step 2: Verify the README contains the new release guidance**

Run: `rg -n "GitHub Releases|内置 Python|winget install ffmpeg|brew install ffmpeg" README.md`

Expected: output shows all four phrases

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add release usage instructions"
```

---

### Task 6: Run End-to-End Verification

**Files:**
- Modify: none

- [ ] **Step 1: Run the focused Python tests**

Run: `PYTHONPATH=. pytest tests/test_runtime_env.py tests/test_main_entry.py -q`

Expected: PASS

- [ ] **Step 2: Run an existing smoke test suite to catch regressions**

Run: `PYTHONPATH=. pytest tests/test_data_dir.py tests/test_ffmpeg_worker.py -q`

Expected: PASS

- [ ] **Step 3: Build the macOS package locally**

Run: `PYTHONPATH=. pyinstaller --clean jh-media-helper.spec`

Expected: PASS and create `dist/jh-media-helper.app`

- [ ] **Step 4: Confirm the app bundle exists**

Run: `test -d dist/jh-media-helper.app && echo OK`

Expected: `OK`

- [ ] **Step 5: Commit verification-safe metadata if needed**

```bash
git status --short
```

Expected: only the intended release-related files are modified

- [ ] **Step 6: Merge back to `master` after review**

```bash
git checkout master
git merge --no-ff codex/release-ci-pyinstaller
```

- [ ] **Step 7: Push `master` and later tag for release**

```bash
git push origin master
git tag v0.1.0
git push origin v0.1.0
```

---

## Self-Review

### Spec coverage

- Dual-platform PyInstaller packaging: covered by Task 3 and Task 4
- Self-contained Python runtime in release artifacts: covered by Task 3, Task 4, and Task 5
- FFmpeg / FFprobe startup detection with GUI prompt: covered by Task 1 and Task 2
- Manual build plus tag-based release flow: covered by Task 4 and Task 6
- Release naming with version numbers: covered by Task 4 and Task 5
- Merge-to-`master` flow: covered by Task 6

### Placeholder scan

- No `TODO`, `TBD`, or “implement later” placeholders remain
- All code-touching tasks include concrete snippets
- All validation steps include explicit commands and expected outcomes

### Type consistency

- Runtime helper names are consistent across plan tasks:
  - `get_missing_ffmpeg_tools`
  - `has_required_ffmpeg_tools`
  - `is_frozen`
- Entry-point plan uses the same helper names defined in Task 1
- Workflow artifact naming is consistent across build, upload, and release steps
