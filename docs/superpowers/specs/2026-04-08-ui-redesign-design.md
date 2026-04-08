# UI Redesign: 全面对齐 birefnet-gui 设计风格

**Date:** 2026-04-08
**Reference:** /Users/liujiahao/birefnet-gui
**Scope:** UI 重构 + BaseTaskPanel 基类提取 + 可复用组件库

---

## 1. Goals

1. 将 jh-media-helper 的 UI 设计语言全面对齐 birefnet-gui 的整洁风格
2. 提取 `BaseTaskPanel` 基类，为 M2（音视频混合）和 M3（MKV 解包）铺路
3. 建立可复用组件库，减少未来 tab 开发中的重复代码

## 2. Component Library

### 2.1 FileSelector (`src/gui/components/file_selector.py`)

通用文件/文件夹选择控件：`QLineEdit(readonly)` + `QPushButton("浏览...")`

**接口：**
```python
class FileSelector(QWidget):
    path_changed = pyqtSignal(str)

    def __init__(
        self,
        label: str,                          # "图片序列文件夹:"
        placeholder: str = "",               # "选择文件夹..."
        dialog_mode: str = "directory",      # "directory" | "file" | "save"
        file_filter: str = "",               # "视频文件 (*.mp4 *.mov)"
        parent=None,
    ): ...

    def path(self) -> str: ...
    def set_path(self, path: str): ...
```

**复用场景：**
- PicSeqPanel: input folder, output directory
- M2 Panel: video file, audio file, output directory
- M3 Panel: MKV file, output directory

### 2.2 ProgressSection (`src/gui/components/progress_section.py`)

进度条 + 状态文字的封装：

**接口：**
```python
class ProgressSection(QWidget):
    def __init__(self, parent=None): ...
    def update_progress(self, current: int, total: int, desc: str = ""): ...
    def set_finished(self, message: str): ...
    def reset(self): ...
    def set_visible(self, visible: bool): ...
```

**内部结构：**
- `QProgressBar`（6px 高度，圆角，自定义 QSS）
- `QLabel` 状态文字（gray, font-size 11px）

**复用场景：**
- BaseTaskPanel 左侧面板底部
- QueueTab "当前任务" 区域

### 2.3 ActionBar (`src/gui/components/action_bar.py`)

居中对齐的按钮行：

**接口：**
```python
class ActionBar(QWidget):
    def __init__(self, parent=None): ...
    def add_button(
        self,
        text: str,
        role: str = "secondary",  # "primary" | "danger" | "secondary"
        enabled: bool = True,
    ) -> QPushButton: ...
```

**按钮样式：**
- `primary`: 绿色背景 (#3a6)，白色文字
- `danger`: 红色背景 (#c44)，白色文字
- `secondary`: 灰色背景 (#444)，浅灰文字

**内部布局：** `QHBoxLayout` + 两侧 `addStretch()` 实现居中

**复用场景：**
- MainWindow 底部 action bar
- QueueTab 按钮行

## 3. BaseTaskPanel

### 3.1 文件位置

`src/gui/task_panels/base_panel.py`

### 3.2 类结构

```python
from abc import abstractmethod
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QScrollArea

class BaseTaskPanel(QWidget):
    """所有任务面板的基类，提供统一的左右分栏布局。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = ProgressSection()
        self._init_base_layout()

    def _init_base_layout(self):
        """构建左右分栏骨架。"""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Left panel (stretch=2)
        left = QVBoxLayout()
        self._build_left_panel(left)
        # separator
        # progress section
        left.addWidget(self._progress)
        left.addStretch()
        main_layout.addLayout(left, 2)

        # Right panel - scrollable settings sidebar (stretch=1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
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
        """子类实现：向左侧面板添加控件（文件选择、文件信息等）。"""

    @abstractmethod
    def _build_settings_panel(self, layout: QVBoxLayout):
        """子类实现：向右侧设置面板添加 QGroupBox 分组。"""

    @abstractmethod
    def validate(self) -> tuple[bool, int, str]:
        """校验配置，返回 (ok, frame_count, error_message)。"""

    @abstractmethod
    def build_config(self) -> object:
        """生成任务配置对象。"""

    @abstractmethod
    def get_task_type(self):
        """返回 TaskType 枚举。"""

    def on_progress(self, current: int, total: int, desc: str):
        self._progress.update_progress(current, total, desc)

    def on_finished(self, output_path: str):
        self._progress.set_finished(f"完成: {output_path}")
```

### 3.3 MainWindow 适配

```python
def _on_tab_changed(self, index: int):
    current_widget = self._tabs.widget(index)
    self._action_bar.setVisible(isinstance(current_widget, BaseTaskPanel))
```

`_on_start` / `_on_enqueue` 通过 `BaseTaskPanel` 的统一接口调用：
- `panel.validate()` 替代直接调用 `processors.pic_seq.validate()`
- `panel.build_config()` 替代 `panel.get_config()`
- `panel.get_task_type()` 替代硬编码 `TaskType.PIC_SEQ`

## 4. PicSeqPanel Redesign

### 4.1 继承 BaseTaskPanel

```python
class PicSeqPanel(BaseTaskPanel):
    def __init__(self, encoder_registry, parent=None):
        self._encoder_registry = encoder_registry
        super().__init__(parent)
```

### 4.2 Left Panel Structure（上→下）

1. `FileSelector(label="图片序列文件夹:", dialog_mode="directory")`
2. `QFrame(HLine)` 分隔线
3. `FileSelector(label="输出路径:", dialog_mode="directory", placeholder="与输入文件夹同级")`
4. `QFrame(HLine)` 分隔线
5. `QGroupBox("文件信息")` — 图片数量、格式、文件名范围、分辨率
6. `QFrame(HLine)` 分隔线
7. `ProgressSection`（由基类提供）

### 4.3 Right Panel Structure（Settings Sidebar）

**QGroupBox "编码参数"：**
- 帧率 (fps): `QSpinBox` range 1-300, default 120
- 比特率 (Mbps): `QSpinBox` range 1-200, default 32
- 分辨率: `QSpinBox` W × `QSpinBox` H
- 扫描格式: `QLineEdit` placeholder "自动探测"

**QGroupBox "输出设置"：**
- 输出格式: `QComboBox` (MOV ProRes 4444 / MP4 H.265 / MP4 H.264)
- 背景模式: `QComboBox` (透明 / 绿幕 / 蓝幕) — **动态隐藏**：选 ProRes 时整行隐藏

**硬件加速状态：** QLabel（绿色文字），位于 QGroupBox 之外底部

### 4.4 Dynamic Visibility

参照 birefnet-gui 的 `_update_advanced_visibility()` 模式：
- ProRes 格式选中时：隐藏背景模式整行（`setVisible(False)`，非 `setEnabled(False)`）
- 未来可扩展：根据输入类型隐藏不相关参数

## 5. QueueTab Redesign

### 5.1 Table Enhancement

**视觉改进：**
- 交替行背景色（`setAlternatingRowColors(True)` + QSS）
- 表格容器圆角
- 状态列使用彩色标识：完成=绿色、编码中=蓝色、等待=灰色、失败=红色
- 当前处理行文件名加粗

**交互增强（对齐 birefnet-gui）：**
- 拖拽行排序：`QTableWidget` 启用 `dragDropMode(InternalMove)`，通过 `verticalHeader` 拖动实现行重排
- 拖拽添加：实现 `dragEnterEvent` / `dropEvent`，支持从 Finder 拖入文件夹直接创建任务。当前仅支持 PIC_SEQ 类型，拖入的文件夹使用默认编码参数（fps=120, bitrate=32, 自动探测分辨率和扫描格式）。M2/M3 实现后再扩展拖拽类型识别。
- 保留右键上下文菜单：删除 / 移到顶部 / 移到底部

### 5.2 Progress Section

使用 `ProgressSection` 组件替代手动布局：
- 当前任务名 + 任务计数同行（space-between）
- 进度条 6px 高度，圆角
- 帧进度 + 总进度同行显示

### 5.3 Button Row

使用 `ActionBar` 组件：
- "开始队列" — `primary`（绿色）
- "取消当前" — `danger`（红色）
- "清空队列" — `secondary`（灰色）

### 5.4 Empty State

队列为空时显示居中占位提示：
- 图标 + "队列为空"
- 引导文字："在任务面板中点击「加入队列」添加任务"

## 6. SettingsTab Redesign

### 6.1 统一视觉风格

- `contentsMargins(20, 20, 20, 20)`，`spacing(16)`
- 所有内容用 `QGroupBox` 分区

### 6.2 Structure

**QGroupBox "数据目录"：**
- 路径显示：`QLabel` 显示 `resolve_data_dir()` 的值
- "打开" 按钮：点击在 Finder 中打开数据目录（`QDesktopServices.openUrl`）
- 说明文字：灰色小字 "队列持久化、日志等数据存储在此目录"

**QGroupBox "关于"：**
- 应用名 + 版本号
- 应用简介（灰色小字）

## 7. Global Style Conventions

参照 birefnet-gui 的样式约定，在全项目统一：

| 元素 | 样式 |
|---|---|
| 外边距 | 20px（所有 tab） |
| 组件间距 | 12-16px |
| 次要文字 | `color: gray` 或 `color: #888` |
| 辅助信息 | `color: gray; font-size: 11px` |
| 分隔线 | `QFrame` with `HLine` + `Sunken` |
| 进度条 | 6px height, border-radius 3px |
| QGroupBox | 标准 Qt 样式，用于逻辑分区 |
| Primary button | 绿色 (#3a6) |
| Danger button | 红色 (#c44) |
| Secondary button | 默认灰色 |

## 8. File Structure

```
src/gui/
├── components/
│   ├── __init__.py
│   ├── file_selector.py      # FileSelector
│   ├── progress_section.py   # ProgressSection
│   └── action_bar.py         # ActionBar
├── task_panels/
│   ├── __init__.py
│   ├── base_panel.py         # BaseTaskPanel
│   └── pic_seq_panel.py      # PicSeqPanel (refactored)
├── main_window.py             # MainWindow (refactored)
├── queue_tab.py               # QueueTab (redesigned)
└── settings_tab.py            # SettingsTab (redesigned)
```

## 9. Out of Scope

- 新功能（M2/M3 面板实现）— 仅提取基类为其铺路
- 全局主题/暗黑模式切换 — 沿用系统原生主题
- 国际化/多语言
