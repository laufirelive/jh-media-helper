# UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align jh-media-helper's UI with birefnet-gui's clean design, extract a BaseTaskPanel base class, and build a reusable component library.

**Architecture:** Bottom-up build order: components first, then base class, then refactor panels to use them, then redesign QueueTab/SettingsTab, finally rewire MainWindow. Each task produces a working commit.

**Tech Stack:** PyQt6, Python 3.14, pytest

---

## File Structure

```
src/gui/
├── components/
│   ├── __init__.py              # NEW — empty
│   ├── file_selector.py         # NEW — FileSelector widget
│   ├── progress_section.py      # NEW — ProgressSection widget
│   └── action_bar.py            # NEW — ActionBar widget
├── task_panels/
│   ├── __init__.py              # EXISTS — empty
│   ├── base_panel.py            # NEW — BaseTaskPanel ABC
│   └── pic_seq_panel.py         # MODIFY — refactor to extend BaseTaskPanel
├── main_window.py               # MODIFY — use BaseTaskPanel interface + ActionBar
├── queue_tab.py                 # MODIFY — full redesign
└── settings_tab.py              # MODIFY — visual upgrade

tests/
├── gui/
│   ├── __init__.py              # NEW — empty
│   └── components/
│       ├── __init__.py          # NEW — empty
│       ├── test_file_selector.py    # NEW
│       ├── test_progress_section.py # NEW
│       └── test_action_bar.py       # NEW
```

---

### Task 1: FileSelector Component

**Files:**
- Create: `src/gui/components/__init__.py`
- Create: `src/gui/components/file_selector.py`
- Create: `tests/gui/__init__.py`
- Create: `tests/gui/components/__init__.py`
- Create: `tests/gui/components/test_file_selector.py`

- [ ] **Step 1: Write the failing test**

Create `tests/gui/__init__.py` and `tests/gui/components/__init__.py` as empty files, then create the test file:

```python
# tests/gui/components/test_file_selector.py
import pytest
from PyQt6.QtWidgets import QApplication

from src.gui.components.file_selector import FileSelector

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture
def selector(qapp):
    return FileSelector(label="测试目录:", placeholder="选择...")


def test_initial_path_is_empty(selector):
    assert selector.path() == ""


def test_set_path(selector):
    selector.set_path("/tmp/test")
    assert selector.path() == "/tmp/test"


def test_placeholder(selector):
    assert selector._edit.placeholderText() == "选择..."


def test_label_text(selector):
    assert selector._label.text() == "测试目录:"


def test_edit_is_readonly(selector):
    assert selector._edit.isReadOnly()


def test_path_changed_signal(selector, qtbot):
    """Signal emits when set_path is called."""
    with qtbot.waitSignal(selector.path_changed, timeout=1000) as blocker:
        selector.set_path("/tmp/new")
    assert blocker.args == ["/tmp/new"]


def test_directory_mode_default(qapp):
    s = FileSelector(label="Dir:", dialog_mode="directory")
    assert s._dialog_mode == "directory"


def test_file_mode(qapp):
    s = FileSelector(label="File:", dialog_mode="file", file_filter="Videos (*.mp4)")
    assert s._dialog_mode == "file"
    assert s._file_filter == "Videos (*.mp4)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/gui/components/test_file_selector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.gui.components'`

- [ ] **Step 3: Install pytest-qt if needed**

Run: `cd /Users/liujiahao/jh-media-helper && pip install pytest-qt`

- [ ] **Step 4: Write the implementation**

Create `src/gui/components/__init__.py` as an empty file, then:

```python
# src/gui/components/file_selector.py
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class FileSelector(QWidget):
    """Reusable file/folder selector: label + read-only edit + browse button."""

    path_changed = pyqtSignal(str)

    def __init__(
        self,
        label: str,
        placeholder: str = "",
        dialog_mode: str = "directory",
        file_filter: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._dialog_mode = dialog_mode
        self._file_filter = file_filter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._label = QLabel(label)
        layout.addWidget(self._label)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._edit = QLineEdit()
        self._edit.setReadOnly(True)
        if placeholder:
            self._edit.setPlaceholderText(placeholder)
        row.addWidget(self._edit)

        self._btn = QPushButton("浏览...")
        self._btn.clicked.connect(self._browse)
        row.addWidget(self._btn)

        layout.addLayout(row)

    def path(self) -> str:
        return self._edit.text()

    def set_path(self, path: str) -> None:
        self._edit.setText(path)
        self.path_changed.emit(path)

    def _browse(self) -> None:
        if self._dialog_mode == "directory":
            path = QFileDialog.getExistingDirectory(self, self._label.text())
        elif self._dialog_mode == "file":
            path, _ = QFileDialog.getOpenFileName(
                self, self._label.text(), "", self._file_filter
            )
        elif self._dialog_mode == "save":
            path, _ = QFileDialog.getSaveFileName(
                self, self._label.text(), "", self._file_filter
            )
        else:
            return
        if path:
            self.set_path(path)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/gui/components/test_file_selector.py -v`
Expected: All 8 tests PASS (the `test_path_changed_signal` test requires `pytest-qt`; if not installed, that single test will error — install it in step 3)

- [ ] **Step 6: Commit**

```bash
git add src/gui/components/__init__.py src/gui/components/file_selector.py tests/gui/__init__.py tests/gui/components/__init__.py tests/gui/components/test_file_selector.py
git commit -m "$(cat <<'EOF'
feat(gui): add FileSelector reusable component

Reusable file/folder selector widget with label, read-only edit,
and browse button. Supports directory, file, and save dialog modes.
EOF
)"
```

---

### Task 2: ProgressSection Component

**Files:**
- Create: `src/gui/components/progress_section.py`
- Create: `tests/gui/components/test_progress_section.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/gui/components/test_progress_section.py
import pytest
from PyQt6.QtWidgets import QApplication

from src.gui.components.progress_section import ProgressSection

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture
def section(qapp):
    return ProgressSection()


def test_initial_state_hidden(section):
    assert not section._progress_bar.isVisible()
    assert section._status_label.text() == ""


def test_update_progress_shows_bar(section):
    section.update_progress(50, 100, "编码中")
    assert section._progress_bar.isVisible()
    assert section._progress_bar.value() == 50
    assert section._progress_bar.maximum() == 100
    assert "50/100" in section._status_label.text()


def test_set_finished(section):
    section.set_finished("完成: /tmp/out.mov")
    assert not section._progress_bar.isVisible()
    assert "完成" in section._status_label.text()


def test_reset(section):
    section.update_progress(50, 100, "编码中")
    section.reset()
    assert not section._progress_bar.isVisible()
    assert section._status_label.text() == ""
    assert section._progress_bar.value() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/gui/components/test_progress_section.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.gui.components.progress_section'`

- [ ] **Step 3: Write the implementation**

```python
# src/gui/components/progress_section.py
from PyQt6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

_PROGRESS_QSS = """
QProgressBar {
    border: 1px solid #444;
    border-radius: 3px;
    background: #333;
    max-height: 6px;
    text-align: center;
}
QProgressBar::chunk {
    background: #33aa66;
    border-radius: 3px;
}
"""


class ProgressSection(QWidget):
    """Reusable progress bar + status label widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._progress_bar = QProgressBar()
        self._progress_bar.setStyleSheet(_PROGRESS_QSS)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self._status_label)

    def update_progress(self, current: int, total: int, desc: str = "") -> None:
        self._progress_bar.setVisible(True)
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        if desc:
            self._status_label.setText(f"{desc}... {current}/{total}")
        else:
            self._status_label.setText(f"{current}/{total}")

    def set_finished(self, message: str) -> None:
        self._progress_bar.setVisible(False)
        self._status_label.setText(message)

    def reset(self) -> None:
        self._progress_bar.setVisible(False)
        self._progress_bar.setValue(0)
        self._status_label.setText("")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/gui/components/test_progress_section.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/gui/components/progress_section.py tests/gui/components/test_progress_section.py
git commit -m "$(cat <<'EOF'
feat(gui): add ProgressSection reusable component

Encapsulates a 6px styled progress bar + gray status label.
Provides update_progress, set_finished, and reset methods.
EOF
)"
```

---

### Task 3: ActionBar Component

**Files:**
- Create: `src/gui/components/action_bar.py`
- Create: `tests/gui/components/test_action_bar.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/gui/components/test_action_bar.py
import pytest
from PyQt6.QtWidgets import QApplication

from src.gui.components.action_bar import ActionBar

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture
def bar(qapp):
    return ActionBar()


def test_add_button_returns_qpushbutton(bar):
    btn = bar.add_button("测试")
    assert btn.text() == "测试"


def test_buttons_centered(bar):
    """Layout should have stretch-buttons-stretch pattern."""
    bar.add_button("A")
    bar.add_button("B")
    layout = bar._layout
    # First item is stretch, last item is stretch
    assert layout.itemAt(0).widget() is None  # stretch
    assert layout.itemAt(layout.count() - 1).widget() is None  # stretch


def test_primary_role(bar):
    btn = bar.add_button("开始", role="primary")
    ss = btn.styleSheet()
    assert "#33aa66" in ss or "#3a6" in ss or "33aa66" in ss


def test_danger_role(bar):
    btn = bar.add_button("取消", role="danger")
    ss = btn.styleSheet()
    assert "#cc4444" in ss or "#c44" in ss or "cc4444" in ss


def test_secondary_role_is_default(bar):
    btn = bar.add_button("清空")
    # Secondary has no special stylesheet (uses Qt default)
    assert btn.styleSheet() == ""


def test_disabled_button(bar):
    btn = bar.add_button("不可用", enabled=False)
    assert not btn.isEnabled()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/gui/components/test_action_bar.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/gui/components/action_bar.py
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget

_ROLE_STYLES = {
    "primary": "QPushButton { background-color: #33aa66; color: white; border: none; padding: 5px 16px; border-radius: 3px; }",
    "danger": "QPushButton { background-color: #cc4444; color: white; border: none; padding: 5px 16px; border-radius: 3px; }",
}


class ActionBar(QWidget):
    """Centered button row with role-based styling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(16, 8, 16, 8)
        self._layout.addStretch()
        # Buttons will be inserted before the trailing stretch
        self._layout.addStretch()

    def add_button(
        self,
        text: str,
        role: str = "secondary",
        enabled: bool = True,
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setEnabled(enabled)
        style = _ROLE_STYLES.get(role, "")
        if style:
            btn.setStyleSheet(style)
        # Insert before the trailing stretch
        self._layout.insertWidget(self._layout.count() - 1, btn)
        return btn
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/gui/components/test_action_bar.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/gui/components/action_bar.py tests/gui/components/test_action_bar.py
git commit -m "$(cat <<'EOF'
feat(gui): add ActionBar reusable component

Centered button row with primary/danger/secondary role styling.
Buttons auto-center via dual addStretch() pattern.
EOF
)"
```

---

### Task 4: BaseTaskPanel Base Class

**Files:**
- Create: `src/gui/task_panels/base_panel.py`
- Create: `tests/gui/test_base_panel.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/gui/test_base_panel.py
import pytest
from PyQt6.QtWidgets import QApplication, QGroupBox, QLabel, QVBoxLayout

from src.gui.task_panels.base_panel import BaseTaskPanel
from src.gui.components.progress_section import ProgressSection


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class ConcretePanel(BaseTaskPanel):
    """Minimal concrete subclass for testing."""

    def _build_left_panel(self, layout: QVBoxLayout):
        layout.addWidget(QLabel("Left content"))

    def _build_settings_panel(self, layout: QVBoxLayout):
        group = QGroupBox("Settings")
        layout.addWidget(group)

    def validate(self):
        return True, 10, None

    def build_config(self):
        return {"test": True}

    def get_task_type(self):
        return "test"


@pytest.fixture
def panel(qapp):
    return ConcretePanel()


def test_panel_has_progress_section(panel):
    assert isinstance(panel._progress, ProgressSection)


def test_layout_is_horizontal(panel):
    from PyQt6.QtWidgets import QHBoxLayout
    assert isinstance(panel.layout(), QHBoxLayout)


def test_margins_are_20px(panel):
    m = panel.layout().contentsMargins()
    assert m.left() == 20
    assert m.right() == 20
    assert m.top() == 20
    assert m.bottom() == 20


def test_spacing_is_16(panel):
    assert panel.layout().spacing() == 16


def test_on_progress_updates_progress_section(panel):
    panel.on_progress(5, 10, "测试")
    assert panel._progress._progress_bar.isVisible()
    assert panel._progress._progress_bar.value() == 5


def test_on_finished_updates_status(panel):
    panel.on_finished("/tmp/output.mov")
    assert "完成" in panel._progress._status_label.text()


def test_validate_returns_tuple(panel):
    ok, count, err = panel.validate()
    assert ok is True
    assert count == 10


def test_build_config(panel):
    cfg = panel.build_config()
    assert cfg == {"test": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/gui/test_base_panel.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# src/gui/task_panels/base_panel.py
from abc import abstractmethod

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.gui.components.progress_section import ProgressSection


def _create_separator() -> QFrame:
    """Create a horizontal line separator."""
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setFrameShadow(QFrame.Shadow.Sunken)
    return sep


class BaseTaskPanel(QWidget):
    """Base class for all task panels. Provides a left-right split layout
    with a scrollable settings sidebar on the right."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = ProgressSection()
        self._init_base_layout()

    def _init_base_layout(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Left panel (stretch=2): subclass content + separator + progress
        left = QVBoxLayout()
        left.setSpacing(10)
        self._build_left_panel(left)
        left.addWidget(_create_separator())
        left.addWidget(self._progress)
        left.addStretch()
        main_layout.addLayout(left, 2)

        # Right panel (stretch=1): scrollable settings sidebar
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        settings_layout = QVBoxLayout(container)
        settings_layout.setSpacing(12)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        self._build_settings_panel(settings_layout)
        settings_layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

    @abstractmethod
    def _build_left_panel(self, layout: QVBoxLayout):
        """Subclass: add file selectors, info, etc. to the left panel."""

    @abstractmethod
    def _build_settings_panel(self, layout: QVBoxLayout):
        """Subclass: add QGroupBox sections to the settings sidebar."""

    @abstractmethod
    def validate(self) -> tuple[bool, int, str | None]:
        """Validate config. Returns (ok, frame_count, error_message)."""

    @abstractmethod
    def build_config(self) -> object:
        """Build and return the task config object."""

    @abstractmethod
    def get_task_type(self):
        """Return the TaskType enum value."""

    def on_progress(self, current: int, total: int, desc: str):
        self._progress.update_progress(current, total, desc)

    def on_finished(self, output_path: str):
        self._progress.set_finished(f"完成: {output_path}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/gui/test_base_panel.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/gui/task_panels/base_panel.py tests/gui/test_base_panel.py
git commit -m "$(cat <<'EOF'
feat(gui): add BaseTaskPanel abstract base class

Provides left-right split layout (2:1), scrollable settings sidebar,
integrated ProgressSection, and abstract methods for validate/build_config/get_task_type.
EOF
)"
```

---

### Task 5: Refactor PicSeqPanel to Extend BaseTaskPanel

**Files:**
- Modify: `src/gui/task_panels/pic_seq_panel.py` (full rewrite)

- [ ] **Step 1: Rewrite PicSeqPanel**

Replace the entire contents of `src/gui/task_panels/pic_seq_panel.py` with:

```python
# src/gui/task_panels/pic_seq_panel.py
import os

from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from src.core.config import (
    BackgroundMode,
    OutputFormat,
    PicSeqConfig,
    TaskType,
)
from src.core.encoder_registry import EncoderRegistry
from src.core.processors.pic_seq import detect_resolution, detect_scan_format
from src.gui.components.file_selector import FileSelector
from src.gui.task_panels.base_panel import BaseTaskPanel, _create_separator


class PicSeqPanel(BaseTaskPanel):
    def __init__(self, encoder_registry: EncoderRegistry, parent=None):
        self._encoder_registry = encoder_registry
        self._detected_scan_format: str | None = None
        self._detected_width: int | None = None
        self._detected_height: int | None = None
        self._file_count: int = 0
        super().__init__(parent)

    # --- Left panel ---

    def _build_left_panel(self, layout: QVBoxLayout):
        # Input folder selector
        self._input_selector = FileSelector(
            label="图片序列文件夹:",
            placeholder="选择文件夹...",
            dialog_mode="directory",
        )
        self._input_selector.path_changed.connect(self._on_input_changed)
        layout.addWidget(self._input_selector)

        layout.addWidget(_create_separator())

        # Output directory selector
        self._output_selector = FileSelector(
            label="输出路径:",
            placeholder="与输入文件夹同级",
            dialog_mode="directory",
        )
        layout.addWidget(self._output_selector)

        layout.addWidget(_create_separator())

        # File info group
        self._info_group = QGroupBox("文件信息")
        info_layout = QVBoxLayout(self._info_group)
        self._info_label = QLabel("未选择文件夹")
        self._info_label.setStyleSheet("color: gray;")
        info_layout.addWidget(self._info_label)
        layout.addWidget(self._info_group)

        # Note: separator before ProgressSection is added by BaseTaskPanel

    # --- Right panel (settings sidebar) ---

    def _build_settings_panel(self, layout: QVBoxLayout):
        # Encoding parameters group
        enc_group = QGroupBox("编码参数")
        enc_layout = QVBoxLayout(enc_group)
        enc_layout.setSpacing(8)

        # FPS
        fps_row = QHBoxLayout()
        fps_row.addWidget(QLabel("帧率"))
        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(1, 300)
        self._fps_spin.setValue(120)
        self._fps_spin.setSuffix(" fps")
        fps_row.addWidget(self._fps_spin)
        enc_layout.addLayout(fps_row)

        # Bitrate
        br_row = QHBoxLayout()
        br_row.addWidget(QLabel("比特率"))
        self._bitrate_spin = QSpinBox()
        self._bitrate_spin.setRange(1, 200)
        self._bitrate_spin.setValue(32)
        self._bitrate_spin.setSuffix(" Mbps")
        br_row.addWidget(self._bitrate_spin)
        enc_layout.addLayout(br_row)

        # Resolution
        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("分辨率"))
        self._width_spin = QSpinBox()
        self._width_spin.setRange(1, 7680)
        self._width_spin.setValue(3840)
        res_row.addWidget(self._width_spin)
        res_row.addWidget(QLabel("x"))
        self._height_spin = QSpinBox()
        self._height_spin.setRange(1, 4320)
        self._height_spin.setValue(2160)
        res_row.addWidget(self._height_spin)
        enc_layout.addLayout(res_row)

        # Scan format
        sf_row = QHBoxLayout()
        sf_row.addWidget(QLabel("扫描格式"))
        self._scan_format_edit = QLineEdit()
        self._scan_format_edit.setPlaceholderText("自动探测")
        sf_row.addWidget(self._scan_format_edit)
        enc_layout.addLayout(sf_row)

        layout.addWidget(enc_group)

        # Output settings group
        out_group = QGroupBox("输出设置")
        out_layout = QVBoxLayout(out_group)
        out_layout.setSpacing(8)

        # Output format
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("格式"))
        self._format_combo = QComboBox()
        self._format_combo.addItem("MOV ProRes 4444 (透明)", OutputFormat.MOV_PRORES)
        self._format_combo.addItem("MP4 H.265", OutputFormat.MP4_HEVC)
        self._format_combo.addItem("MP4 H.264", OutputFormat.MP4_H264)
        self._format_combo.currentIndexChanged.connect(self._on_format_changed)
        fmt_row.addWidget(self._format_combo)
        out_layout.addLayout(fmt_row)

        # Background mode (dynamically hidden)
        self._bg_row = QHBoxLayout()
        self._bg_label = QLabel("背景")
        self._bg_row.addWidget(self._bg_label)
        self._bg_combo = QComboBox()
        self._bg_combo.addItem("透明", BackgroundMode.TRANSPARENT)
        self._bg_combo.addItem("绿幕", BackgroundMode.GREEN)
        self._bg_combo.addItem("蓝幕", BackgroundMode.BLUE)
        self._bg_row.addWidget(self._bg_combo)

        # Wrap in a widget for visibility control
        self._bg_widget = QWidget()
        self._bg_widget.setLayout(self._bg_row)
        self._bg_widget.setVisible(False)  # Hidden by default (ProRes selected)
        out_layout.addWidget(self._bg_widget)

        layout.addWidget(out_group)

        # Hardware acceleration label
        self._hw_label = QLabel("")
        self._hw_label.setStyleSheet("color: #33aa66; font-size: 11px;")
        self._update_hw_label()
        layout.addWidget(self._hw_label)

    # --- Callbacks ---

    def _on_input_changed(self, path: str):
        self._detect(path)

    def _detect(self, input_dir: str):
        result = detect_scan_format(input_dir)
        if result is None:
            self._detected_scan_format = None
            self._file_count = 0
            self._info_label.setText("探测失败: 无法识别图片序列格式\n请手动输入扫描格式")
            self._scan_format_edit.setPlaceholderText("请手动输入，如 %06d.png")
            return

        fmt, count = result
        self._detected_scan_format = fmt
        self._file_count = count
        self._scan_format_edit.setPlaceholderText(f"{fmt} (自动)")

        try:
            w, h = detect_resolution(input_dir, fmt)
            self._detected_width = w
            self._detected_height = h
            self._width_spin.setValue(w)
            self._height_spin.setValue(h)
        except FileNotFoundError:
            self._detected_width = None
            self._detected_height = None

        entries = sorted(
            [f for f in os.listdir(input_dir)
             if os.path.splitext(f)[1].lower() == os.path.splitext(fmt)[1].lower()]
        )
        first = entries[0] if entries else "?"
        last = entries[-1] if entries else "?"
        info = f"检测到 {count} 张图片\n格式: {fmt} (自动)\n{first} → {last}"
        if self._detected_width and self._detected_height:
            info += f"\n分辨率: {self._detected_width}x{self._detected_height}"
        self._info_label.setText(info)

    def _on_format_changed(self, index: int):
        fmt = self._format_combo.currentData()
        is_prores = fmt == OutputFormat.MOV_PRORES
        self._bg_widget.setVisible(not is_prores)
        if not is_prores:
            self._bg_combo.setCurrentIndex(1)  # Default to green

    def _update_hw_label(self):
        best = self._encoder_registry.get_best_hevc()
        if best:
            self._hw_label.setText(f"硬件加速: {best} ✓")
        else:
            self._hw_label.setText("硬件加速: 不可用 (将使用 libx264)")
            self._hw_label.setStyleSheet("color: gray; font-size: 11px;")

    # --- BaseTaskPanel interface ---

    def validate(self) -> tuple[bool, int, str | None]:
        input_dir = self._input_selector.path()
        if not input_dir:
            return False, 0, "请先选择图片序列文件夹"

        scan_format = self._scan_format_edit.text() or self._detected_scan_format
        if not scan_format:
            return False, 0, "无法探测扫描格式，请手动输入"

        from src.core.processors.pic_seq import validate
        config = self._build_pic_seq_config()
        if config is None:
            return False, 0, "配置无效"
        return validate(config)

    def build_config(self) -> PicSeqConfig | None:
        return self._build_pic_seq_config()

    def get_task_type(self) -> TaskType:
        return TaskType.PIC_SEQ

    def _build_pic_seq_config(self) -> PicSeqConfig | None:
        input_dir = self._input_selector.path()
        if not input_dir:
            return None

        scan_format = self._scan_format_edit.text() or self._detected_scan_format
        if not scan_format:
            return None

        output_dir = self._output_selector.path() or None
        fmt = self._format_combo.currentData()
        bg = self._bg_combo.currentData()
        hw_accel = fmt != OutputFormat.MOV_PRORES

        return PicSeqConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            fps=self._fps_spin.value(),
            bitrate_mbps=self._bitrate_spin.value(),
            width=self._width_spin.value(),
            height=self._height_spin.value(),
            scan_format=scan_format,
            output_format=fmt,
            background_mode=bg if fmt != OutputFormat.MOV_PRORES else BackgroundMode.TRANSPARENT,
            hw_accel=hw_accel,
        )
```

- [ ] **Step 2: Verify the app launches without errors**

Run: `cd /Users/liujiahao/jh-media-helper && python -c "from src.gui.task_panels.pic_seq_panel import PicSeqPanel; print('Import OK')"`
Expected: `Import OK`

- [ ] **Step 3: Run all existing tests to check no regressions**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/gui/task_panels/pic_seq_panel.py
git commit -m "$(cat <<'EOF'
refactor(gui): PicSeqPanel extends BaseTaskPanel

Left-right split with FileSelector components, QGroupBox settings,
dynamic background mode visibility, and unified BaseTaskPanel interface.
EOF
)"
```

---

### Task 6: Refactor MainWindow to Use BaseTaskPanel Interface

**Files:**
- Modify: `src/gui/main_window.py` (full rewrite)

- [ ] **Step 1: Rewrite MainWindow**

Replace the entire contents of `src/gui/main_window.py` with:

```python
# src/gui/main_window.py
from PyQt6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.data_dir import get_queue_path
from src.core.encoder_registry import EncoderRegistry
from src.core.processors.pic_seq import _resolve_output_path
from src.core.queue_manager import QueueManager
from src.core.queue_task import QueueTask
from src.gui.components.action_bar import ActionBar
from src.gui.queue_tab import QueueTab
from src.gui.settings_tab import SettingsTab
from src.gui.task_panels.base_panel import BaseTaskPanel
from src.gui.task_panels.pic_seq_panel import PicSeqPanel
from src.worker.ffmpeg_worker import FFmpegWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("jh-media-helper")
        self.setMinimumSize(800, 600)

        self._encoder_registry = EncoderRegistry()
        self._queue_manager = QueueManager(get_queue_path())
        self._queue_manager.load()
        self._worker: FFmpegWorker | None = None

        self._init_ui()
        self._connect_signals()
        self._check_queue_recovery()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._tabs = QTabWidget()
        outer.addWidget(self._tabs)

        # PicSeq tab
        self._pic_seq_panel = PicSeqPanel(self._encoder_registry)
        self._tabs.addTab(self._pic_seq_panel, "图片序列转视频")

        # Future: M2/M3 tabs will be added here

        # Queue tab
        self._queue_tab = QueueTab(self._queue_manager, self._encoder_registry)
        self._tabs.addTab(self._queue_tab, f"批量队列 ({len(self._queue_manager.tasks)})")

        # Settings tab
        self._settings_tab = SettingsTab()
        self._tabs.addTab(self._settings_tab, "设置")

        # Bottom action bar (centered)
        self._action_bar = ActionBar()
        self._btn_cancel = self._action_bar.add_button("取消", role="secondary", enabled=False)
        self._btn_enqueue = self._action_bar.add_button("加入队列", role="secondary")
        self._btn_start = self._action_bar.add_button("开始处理", role="primary")
        outer.addWidget(self._action_bar)

        self._tabs.currentChanged.connect(self._on_tab_changed)

    def _connect_signals(self):
        self._btn_start.clicked.connect(self._on_start)
        self._btn_cancel.clicked.connect(self._on_cancel)
        self._btn_enqueue.clicked.connect(self._on_enqueue)
        self._queue_tab.task_count_changed.connect(self._update_queue_badge)

    def _on_tab_changed(self, index: int):
        current_widget = self._tabs.widget(index)
        self._action_bar.setVisible(isinstance(current_widget, BaseTaskPanel))

    def _get_active_panel(self) -> BaseTaskPanel | None:
        widget = self._tabs.currentWidget()
        if isinstance(widget, BaseTaskPanel):
            return widget
        return None

    def _update_queue_badge(self, count: int):
        idx = self._tabs.indexOf(self._queue_tab)
        self._tabs.setTabText(idx, f"批量队列 ({count})")

    def _on_start(self):
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

        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)

        self._worker = FFmpegWorker(
            task_type=panel.get_task_type(),
            config=config.to_dict(),
            encoder_registry=self._encoder_registry,
            total_frames=count,
        )
        self._worker.progress.connect(panel.on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_cancel(self):
        if self._worker:
            self._worker.cancel()
            self._worker = None
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)

    def _on_finished(self, output_path: str):
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._worker = None
        panel = self._get_active_panel()
        if panel:
            panel.on_finished(output_path)

    def _on_error(self, message: str):
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._worker = None
        QMessageBox.critical(self, "错误", message)

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

        output_path = _resolve_output_path(config)
        task = QueueTask.create(
            task_type=panel.get_task_type(),
            config=config,
            input_path=config.input_dir,
            output_path=output_path,
        )
        self._queue_manager.add_task(task)
        self._queue_manager.save()
        self._queue_tab.refresh()

    def _check_queue_recovery(self):
        pending = [t for t in self._queue_manager.tasks if t.status.value == "pending"]
        if not pending:
            return
        reply = QMessageBox.question(
            self,
            "队列恢复",
            f"发现 {len(pending)} 个未完成任务，是否继续执行？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Discard,
        )
        if reply == QMessageBox.StandardButton.Discard:
            self._queue_manager.clear_all()
            self._queue_manager.save()

    def closeEvent(self, event):
        if self._worker:
            self._worker.cancel()
            self._worker.wait(3000)
        self._queue_tab.stop()
        self._queue_manager.save()
        event.accept()
```

- [ ] **Step 2: Verify import works**

Run: `cd /Users/liujiahao/jh-media-helper && python -c "from src.gui.main_window import MainWindow; print('Import OK')"`
Expected: `Import OK`

- [ ] **Step 3: Run all tests**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/gui/main_window.py
git commit -m "$(cat <<'EOF'
refactor(gui): MainWindow uses BaseTaskPanel interface + ActionBar

Replaces hardcoded PicSeqPanel references with BaseTaskPanel abstraction.
Action bar now centered via ActionBar component. Outer margins set to 0
so each tab controls its own padding.
EOF
)"
```

---

### Task 7: Redesign QueueTab

**Files:**
- Modify: `src/gui/queue_tab.py` (full rewrite)

- [ ] **Step 1: Rewrite QueueTab**

Replace the entire contents of `src/gui/queue_tab.py` with:

```python
# src/gui/queue_tab.py
import os
import time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.config import PicSeqConfig, TaskStatus, TaskType
from src.core.encoder_registry import EncoderRegistry
from src.core.processors.pic_seq import (
    detect_resolution,
    detect_scan_format,
    validate,
    _resolve_output_path,
)
from src.core.queue_manager import QueueManager
from src.core.queue_task import QueueTask
from src.gui.components.action_bar import ActionBar
from src.gui.components.progress_section import ProgressSection
from src.worker.ffmpeg_worker import FFmpegWorker

_TYPE_LABELS = {
    TaskType.PIC_SEQ: "图片序列",
    TaskType.COMBAT_AUDIO: "音视频混合",
    TaskType.MKV_EXTRACT: "MKV解包",
}

_FORMAT_LABELS = {
    "mov_prores": "MOV ProRes 4444",
    "mp4_hevc": "MP4 H.265",
    "mp4_h264": "MP4 H.264",
}

_STATUS_COLORS = {
    TaskStatus.COMPLETED: "#33aa66",
    TaskStatus.PROCESSING: "#6699cc",
    TaskStatus.FAILED: "#cc4444",
    TaskStatus.CANCELLED: "#cc4444",
    TaskStatus.PENDING: "#888888",
}

_TABLE_QSS = """
QTableWidget {
    border: 1px solid #555;
    border-radius: 4px;
    gridline-color: #333;
    alternate-background-color: #1e1e2e;
}
QTableWidget::item {
    padding: 4px 8px;
}
QHeaderView::section {
    background: #2a2a3a;
    color: #888;
    border: none;
    border-bottom: 1px solid #555;
    padding: 6px 8px;
    font-weight: bold;
}
"""


class QueueTab(QWidget):
    task_count_changed = pyqtSignal(int)

    def __init__(self, queue_manager: QueueManager, encoder_registry: EncoderRegistry, parent=None):
        super().__init__(parent)
        self._queue_manager = queue_manager
        self._encoder_registry = encoder_registry
        self._worker: FFmpegWorker | None = None
        self._running = False
        self._last_refresh_time = 0.0
        self.setAcceptDrops(True)
        self._init_ui()
        self._refresh_table()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Task table
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["文件名", "类型", "输出格式", "状态"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(True)
        self._table.verticalHeader().setSectionsMovable(True)
        self._table.verticalHeader().sectionMoved.connect(self._on_row_moved)
        self._table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(_TABLE_QSS)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._table)

        # Empty state overlay
        self._empty_widget = QWidget(self._table)
        empty_layout = QVBoxLayout(self._empty_widget)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon = QLabel("📋")
        empty_icon.setStyleSheet("font-size: 32px; color: #666;")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)
        empty_title = QLabel("队列为空")
        empty_title.setStyleSheet("color: #888; font-size: 14px;")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_hint = QLabel("在任务面板中点击「加入队列」添加任务")
        empty_hint.setStyleSheet("color: #666; font-size: 11px;")
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_hint)

        # Current task progress
        progress_group = QGroupBox("当前任务")
        progress_layout = QVBoxLayout(progress_group)

        info_row = QHBoxLayout()
        self._current_label = QLabel("")
        self._current_label.setStyleSheet("color: #ccc; font-weight: bold;")
        info_row.addWidget(self._current_label)
        info_row.addStretch()
        self._task_count_label = QLabel("")
        self._task_count_label.setStyleSheet("color: gray; font-size: 11px;")
        info_row.addWidget(self._task_count_label)
        progress_layout.addLayout(info_row)

        self._progress = ProgressSection()
        progress_layout.addWidget(self._progress)

        self._total_label = QLabel("")
        self._total_label.setStyleSheet("color: gray; font-size: 11px;")
        self._total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        progress_layout.addWidget(self._total_label)

        layout.addWidget(progress_group)

        # Control buttons
        self._action_bar = ActionBar()
        self._btn_start = self._action_bar.add_button("开始队列", role="primary")
        self._btn_start.clicked.connect(self._on_start)
        self._btn_cancel = self._action_bar.add_button("取消当前", role="danger", enabled=False)
        self._btn_cancel.clicked.connect(self._on_cancel_current)
        self._btn_clear = self._action_bar.add_button("清空队列", role="secondary")
        self._btn_clear.clicked.connect(self._on_clear)
        layout.addWidget(self._action_bar)

    # --- Table ---

    def _refresh_table(self):
        tasks = self._queue_manager.tasks
        self._table.setRowCount(0)

        # Show/hide empty state
        self._empty_widget.setVisible(len(tasks) == 0)

        for task in tasks:
            row = self._table.rowCount()
            self._table.insertRow(row)

            display_name = os.path.basename(task.input_path.rstrip(os.sep)) or task.input_path
            name_item = QTableWidgetItem(display_name)
            if task.status == TaskStatus.PROCESSING:
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)
            self._table.setItem(row, 0, name_item)

            type_item = QTableWidgetItem(_TYPE_LABELS.get(task.task_type, "?"))
            type_item.setForeground(Qt.GlobalColor.gray)
            self._table.setItem(row, 1, type_item)

            fmt_label = _FORMAT_LABELS.get(task.config.get("output_format", ""), "?")
            fmt_item = QTableWidgetItem(fmt_label)
            fmt_item.setForeground(Qt.GlobalColor.gray)
            self._table.setItem(row, 2, fmt_item)

            status_text = self._status_text(task)
            status_item = QTableWidgetItem(status_text)
            color = _STATUS_COLORS.get(task.status, "#888")
            from PyQt6.QtGui import QColor
            status_item.setForeground(QColor(color))
            self._table.setItem(row, 3, status_item)

        self.task_count_changed.emit(len(tasks))

    def _status_text(self, task) -> str:
        if task.status == TaskStatus.COMPLETED:
            return "完成"
        if task.status == TaskStatus.FAILED:
            return "失败"
        if task.status == TaskStatus.CANCELLED:
            return "已取消"
        if task.status == TaskStatus.PROCESSING:
            if task.total > 0:
                return f"编码中 {task.progress}/{task.total}"
            return "编码中..."
        return "等待"

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_empty_widget'):
            self._empty_widget.setGeometry(self._table.rect())

    # --- Drag and drop ---

    def _on_row_moved(self, logical: int, old_visual: int, new_visual: int):
        tasks = self._queue_manager.tasks
        if old_visual < len(tasks):
            task_id = tasks[old_visual].id
            self._queue_manager.move_task(task_id, new_visual)
            self._queue_manager.save()
            self._refresh_table()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isdir(path):
                self._add_folder_as_task(path)
        event.acceptProposedAction()

    def _add_folder_as_task(self, folder: str):
        result = detect_scan_format(folder)
        if result is None:
            return
        fmt, count = result
        try:
            w, h = detect_resolution(folder, fmt)
        except FileNotFoundError:
            w, h = 3840, 2160

        config = PicSeqConfig(
            input_dir=folder,
            fps=120,
            bitrate_mbps=32,
            width=w,
            height=h,
            scan_format=fmt,
        )
        ok, frame_count, err = validate(config)
        if not ok:
            return

        output_path = _resolve_output_path(config)
        task = QueueTask.create(
            task_type=TaskType.PIC_SEQ,
            config=config,
            input_path=folder,
            output_path=output_path,
        )
        self._queue_manager.add_task(task)
        self._queue_manager.save()
        self._refresh_table()

    # --- Context menu ---

    def _show_context_menu(self, pos):
        row = self._table.rowAt(pos.y())
        tasks = self._queue_manager.tasks
        if row < 0 or row >= len(tasks):
            return
        task = tasks[row]
        if task.status == TaskStatus.PROCESSING:
            return

        menu = QMenu(self)
        menu.addAction("删除", lambda: self._remove_task(task.id))
        if row > 0:
            menu.addAction("移到顶部", lambda: self._move_to(task.id, 0))
        if row < len(tasks) - 1:
            menu.addAction("移到底部", lambda: self._move_to(task.id, len(tasks) - 1))
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _remove_task(self, task_id: str):
        self._queue_manager.remove_task(task_id)
        self._queue_manager.save()
        self._refresh_table()

    def _move_to(self, task_id: str, new_index: int):
        self._queue_manager.move_task(task_id, new_index)
        self._queue_manager.save()
        self._refresh_table()

    # --- Queue execution ---

    def _on_start(self):
        self._running = True
        self._btn_start.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._btn_clear.setEnabled(False)
        self._run_next()

    def _run_next(self):
        if not self._running:
            self._on_queue_stopped()
            return
        task = self._queue_manager.next_pending()
        if task is None:
            self._on_queue_finished()
            return

        task.status = TaskStatus.PROCESSING
        self._queue_manager.save()
        self._refresh_table()

        self._current_label.setText(os.path.basename(task.input_path))
        self._progress.reset()

        count = 0
        if task.task_type == TaskType.PIC_SEQ:
            cfg = PicSeqConfig.from_dict(task.config)
            ok, count, err = validate(cfg)
            if not ok:
                task.status = TaskStatus.FAILED
                task.error = err
                self._queue_manager.save()
                self._refresh_table()
                self._run_next()
                return

        self._worker = FFmpegWorker(
            task_type=task.task_type,
            config=task.config,
            encoder_registry=self._encoder_registry,
            total_frames=count,
        )
        self._worker.progress.connect(
            lambda cur, tot, desc, tid=task.id: self._on_task_progress(tid, cur, tot, desc)
        )
        self._worker.finished.connect(
            lambda path, tid=task.id: self._on_task_finished(tid)
        )
        self._worker.error.connect(
            lambda msg, tid=task.id: self._on_task_error(tid, msg)
        )
        self._worker.start()

    def _on_task_progress(self, task_id: str, current: int, total: int, desc: str):
        task = self._queue_manager.get_task(task_id)
        if task:
            task.progress = current
            task.total = total

        self._progress.update_progress(current, total, desc)
        self._update_total_progress()

        now = time.time()
        if now - self._last_refresh_time >= 2.0 or current % 100 == 0:
            self._queue_manager.save()
            self._refresh_table()
            self._last_refresh_time = now

    def _update_total_progress(self):
        tasks = self._queue_manager.tasks
        task_count = len(tasks)
        if task_count == 0:
            return
        completed_count = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        current_idx = completed_count + 1
        self._task_count_label.setText(f"任务 {current_idx}/{task_count}")

        total_work = 0
        completed_work = 0
        for t in tasks:
            weight = max(t.total, 1)
            total_work += weight
            if t.status == TaskStatus.COMPLETED:
                completed_work += weight
            elif t.status == TaskStatus.PROCESSING:
                completed_work += t.progress

        pct = int(completed_work / total_work * 100) if total_work > 0 else 0
        self._total_label.setText(f"总进度 {pct}%")

    def _on_task_finished(self, task_id: str):
        task = self._queue_manager.get_task(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
        self._queue_manager.save()
        self._refresh_table()
        self._worker = None
        self._run_next()

    def _on_task_error(self, task_id: str, message: str):
        task = self._queue_manager.get_task(task_id)
        if task:
            task.status = TaskStatus.FAILED
            task.error = message
        self._queue_manager.save()
        self._refresh_table()
        self._worker = None
        self._run_next()

    def _on_cancel_current(self):
        if self._worker:
            self._worker.cancel()

    def _on_clear(self):
        reply = QMessageBox.question(
            self, "确认", "确定清空所有队列任务？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._queue_manager.clear_all()
            self._queue_manager.save()
            self._refresh_table()
            self._current_label.setText("")
            self._task_count_label.setText("")
            self._total_label.setText("")
            self._progress.reset()

    def _on_queue_finished(self):
        self._on_queue_stopped()
        self._current_label.setText("队列完成")
        self._progress.set_finished("所有任务已完成")
        QApplication.beep()

    def _on_queue_stopped(self):
        self._running = False
        self._btn_start.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._btn_clear.setEnabled(True)

    def refresh(self):
        self._refresh_table()

    def stop(self):
        self._running = False
        if self._worker:
            self._worker.cancel()
            self._worker.wait(3000)
```

- [ ] **Step 2: Verify import**

Run: `cd /Users/liujiahao/jh-media-helper && python -c "from src.gui.queue_tab import QueueTab; print('Import OK')"`
Expected: `Import OK`

- [ ] **Step 3: Run all tests**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/gui/queue_tab.py
git commit -m "$(cat <<'EOF'
refactor(gui): redesign QueueTab with visual polish + drag-and-drop

- Styled table with alternating rows, colored status, bold active row
- Drag-and-drop row reorder via vertical header
- Drag-and-drop folder addition from Finder
- ActionBar + ProgressSection components
- Empty state placeholder
EOF
)"
```

---

### Task 8: Redesign SettingsTab

**Files:**
- Modify: `src/gui/settings_tab.py` (full rewrite)

- [ ] **Step 1: Rewrite SettingsTab**

Replace the entire contents of `src/gui/settings_tab.py` with:

```python
# src/gui/settings_tab.py
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.data_dir import resolve_data_dir


class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Data directory group
        data_group = QGroupBox("数据目录")
        data_layout = QVBoxLayout(data_group)
        data_layout.setSpacing(8)

        dir_row = QHBoxLayout()
        dir_label = QLabel(f"路径: {resolve_data_dir()}")
        dir_label.setStyleSheet("color: #ccc;")
        dir_row.addWidget(dir_label)
        dir_row.addStretch()
        open_btn = QPushButton("打开")
        open_btn.clicked.connect(self._open_data_dir)
        dir_row.addWidget(open_btn)
        data_layout.addLayout(dir_row)

        hint = QLabel("队列持久化、日志等数据存储在此目录")
        hint.setStyleSheet("color: gray; font-size: 11px;")
        data_layout.addWidget(hint)

        layout.addWidget(data_group)

        # About group
        about_group = QGroupBox("关于")
        about_layout = QVBoxLayout(about_group)
        about_layout.setSpacing(4)

        name_label = QLabel("jh-media-helper v0.1")
        name_label.setStyleSheet("color: #ccc; font-weight: bold;")
        about_layout.addWidget(name_label)

        desc_label = QLabel("影视后期媒体处理工具")
        desc_label.setStyleSheet("color: gray; font-size: 11px;")
        about_layout.addWidget(desc_label)

        layout.addWidget(about_group)

        layout.addStretch()

    def _open_data_dir(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(resolve_data_dir()))
```

- [ ] **Step 2: Verify import**

Run: `cd /Users/liujiahao/jh-media-helper && python -c "from src.gui.settings_tab import SettingsTab; print('Import OK')"`
Expected: `Import OK`

- [ ] **Step 3: Run all tests**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/gui/settings_tab.py
git commit -m "$(cat <<'EOF'
refactor(gui): redesign SettingsTab with QGroupBox sections

Data directory group with open-in-Finder button.
About group with version info. Consistent 20px margins.
EOF
)"
```

---

### Task 9: Final Integration Smoke Test

**Files:** (none — verification only)

- [ ] **Step 1: Run the full test suite**

Run: `cd /Users/liujiahao/jh-media-helper && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Launch the app and verify visually**

Run: `cd /Users/liujiahao/jh-media-helper && python main.py`

Verify:
- PicSeqPanel: left-right split, FileSelector components, QGroupBox settings, separators, 20px margins
- QueueTab: styled table, empty state visible, centered buttons with colored roles
- SettingsTab: QGroupBox sections, "打开" button, version info
- Action bar centered at bottom, only visible on task panel tabs
- Switch tabs: action bar hides on Queue/Settings tabs

- [ ] **Step 3: Test dynamic visibility**

In the app:
1. On PicSeqPanel, change output format from "MOV ProRes 4444" to "MP4 H.265"
2. Verify background mode row appears
3. Switch back to "MOV ProRes 4444"
4. Verify background mode row hides

- [ ] **Step 4: Test drag-and-drop on QueueTab (if test data available)**

1. Switch to QueueTab
2. Try dragging rows via the vertical header
3. Try dragging a folder from Finder onto the queue

- [ ] **Step 5: Final commit if any fixes needed**

If any fixes were needed during smoke testing:
```bash
git add -u
git commit -m "fix(gui): address integration issues from smoke test"
```
