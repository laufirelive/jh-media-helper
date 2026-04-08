# jh-media-helper M1 设计文档

**版本**: v1.0
**日期**: 2026-04-08
**范围**: M1（图片序列转视频）+ 基础 GUI 框架 + 统一队列

---

## 1. 概述

将 ffmpeg-video-helper（Java CLI）的图片序列转视频功能迁移到 Python + PyQt6 桌面应用，采用 birefnet-gui 的分层架构模式。本次交付包含完整的 M1 功能、基础 GUI 框架（为 M2/M3 扩展预留）和通用任务队列系统。

### 参考项目

| 项目 | 路径 | 用途 |
|------|------|------|
| ffmpeg-video-helper | `/Users/liujiahao/ffmpeg-video-helper` | M1 业务逻辑和 FFmpeg 命令 |
| birefnet-gui | `/Users/liujiahao/birefnet-gui` | PyQt6 架构、队列系统、Worker 模式 |

---

## 2. 项目结构

```
jh-media-helper/
├── main.py                         # 入口：QApplication + MainWindow
├── requirements.txt                # PyQt6, Pillow
├── src/
│   ├── core/                       # 纯 Python，无 Qt 依赖
│   │   ├── config.py               # TaskType、OutputFormat、BackgroundMode 枚举 + PicSeqConfig dataclass
│   │   ├── settings.py             # AppSettings dataclass + JSON I/O
│   │   ├── data_dir.py             # 数据目录解析 (~/.jh-media-helper/)
│   │   ├── encoder_registry.py     # 跨平台编码器检测
│   │   ├── ffprobe.py              # ffprobe 封装（流分析）
│   │   ├── queue_task.py           # QueueTask dataclass + TaskStatus 枚举
│   │   ├── queue_manager.py        # QueueManager: 统一队列 + JSON 持久化
│   │   └── processors/             # 功能处理器（每个功能一个文件）
│   │       └── pic_seq.py          # M1: 图片序列转视频（校验、探测、命令构建）
│   ├── gui/                        # PyQt6 组件
│   │   ├── main_window.py          # MainWindow: Tab 容器 + 底部操作栏
│   │   ├── task_panels/            # 各功能的参数配置面板
│   │   │   └── pic_seq_panel.py    # M1: 图片序列参数面板
│   │   ├── queue_tab.py            # 批量队列 Tab
│   │   └── settings_tab.py         # 设置 Tab
│   └── worker/                     # QThread 工作线程
│       └── ffmpeg_worker.py        # FFmpegWorker: 进程执行 + 进度解析
└── tests/
```

### 对应关系

- `gui/task_panels/pic_seq_panel.py` → `core/processors/pic_seq.py`
- 各 processor 调用 `core/ffprobe.py` + `core/encoder_registry.py`
- M2/M3 扩展时在 `core/processors/` 和 `gui/task_panels/` 下新增文件即可

---

## 3. 核心数据模型

### 3.1 枚举定义 (core/config.py)

```python
class TaskType(Enum):
    PIC_SEQ = "pic_seq"
    COMBAT_AUDIO = "combat_audio"      # M2 预留
    MKV_EXTRACT = "mkv_extract"        # M3 预留

class OutputFormat(Enum):
    MOV_PRORES = "mov_prores"          # ProRes 4444, 透明通道
    MP4_HEVC = "mp4_hevc"              # H.265
    MP4_H264 = "mp4_h264"             # H.264

class BackgroundMode(Enum):
    TRANSPARENT = "transparent"        # 仅 MOV ProRes
    GREEN = "green"                    # 绿幕，MP4 默认
    BLUE = "blue"                      # 蓝幕

class TaskStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

### 3.2 PicSeqConfig (core/config.py)

```python
@dataclass
class PicSeqConfig:
    input_dir: str                          # 图片序列文件夹
    output_dir: str | None = None           # None = 原文件夹同级
    fps: int = 120
    bitrate_mbps: int = 32
    width: int | None = None                # None = 自动探测首张图片
    height: int | None = None               # None = 自动探测首张图片
    scan_format: str | None = None          # None = 自动探测文件名序列
    output_format: OutputFormat = OutputFormat.MOV_PRORES
    background_mode: BackgroundMode = BackgroundMode.TRANSPARENT
    hw_accel: bool = True

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> "PicSeqConfig": ...
```

### 3.3 QueueTask (core/queue_task.py)

```python
@dataclass
class QueueTask:
    id: str                     # 8位 hex UUID
    task_type: TaskType
    config: dict                # PicSeqConfig.to_dict() 等
    input_path: str             # 主输入路径（展示用）
    output_path: str
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    total: int = 0
    error: str | None = None
    created_at: str = ""        # ISO 时间戳

    @classmethod
    def create(cls, task_type, config_dataclass, input_path, output_path) -> "QueueTask": ...
    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> "QueueTask": ...
```

---

## 4. M1: 图片序列转视频处理器 (core/processors/pic_seq.py)

### 4.1 自动探测

**scan_format 探测**：
1. `os.listdir()` 获取文件名列表（不加载文件内容）
2. 按扩展名过滤图片文件（png/jpg/exr/tga）
3. 正则匹配纯数字文件名，推断位数和扩展名（如 `000001.png` → `%06d.png`）
4. 验证序列连续性
5. 探测失败 → 返回 None，GUI 弹出输入框让用户手动填写

**分辨率探测**：
1. 取排序后第一张图片
2. `PIL.Image.open(path).size`（惰性加载，仅读 header，不解码像素数据）
3. 返回 (width, height)

### 4.2 校验

```python
def validate(config: PicSeqConfig) -> tuple[bool, int, str | None]:
    """
    返回 (ok, file_count, error_message)
    - input_dir 是否存在
    - 是否有匹配 scan_format 的图片文件
    - 返回文件数量用于进度计算
    """
```

### 4.3 命令构建

```python
def build_command(config: PicSeqConfig, encoder: str) -> list[str]:
    """
    根据 config 和编码器构建 ffmpeg 命令参数列表。
    """
```

**MOV ProRes 4444（透明通道）**：
```
ffmpeg -r {fps} -i {input_dir}/{scan_format}
  -c:v prores_ks -profile:v 4444 -pix_fmt yuva444p
  -s {width}x{height}
  {output_dir}/s{dirname}.mov
```

**MP4 HEVC 硬件加速（绿幕/蓝幕）**：
```
ffmpeg -r {fps} -i {input_dir}/{scan_format}
  -c:v {hevc_encoder} -b:v {bitrate}M
  -vf "color=c={bg_color}:s={w}x{h}:r={fps}[bg];[bg][0:v]overlay=shortest=1"
  -pix_fmt yuv420p -s {width}x{height}
  {output_dir}/s{dirname}.mp4
```

**alpha 通道检测**：探测阶段用 `PIL.Image.open().mode` 检查首张图片是否含 alpha（RGBA/LA）。
- 有 alpha → 使用 overlay 滤镜合成绿幕/蓝幕背景
- 无 alpha → 跳过 overlay，直接编码原图

**hw_accel 与输出格式的关系**：
- MOV ProRes → 始终使用 `prores_ks` 软件编码器，`hw_accel` 开关无效（GUI 中置灰）
- MP4 → `hw_accel` 控制是否使用硬件 HEVC 编码器

**MP4 软件回退（libx264）**：
```
ffmpeg -r {fps} -i {input_dir}/{scan_format}
  -c:v libx264 -preset slow -b:v {bitrate}M
  -vf "color=c={bg_color}:s={w}x{h}:r={fps}[bg];[bg][0:v]overlay=shortest=1"
  -pix_fmt yuv420p -s {width}x{height}
  {output_dir}/s{dirname}.mp4
```

### 4.4 输出命名

- MOV: `s{文件夹名}.mov`
- MP4: `s{文件夹名}.mp4`
- 位置：指定输出目录或原文件夹同级目录

---

## 5. 编码器检测 (core/encoder_registry.py)

### 检测方法

启动时运行一次探测，尝试用各编码器编码空视频：
```
ffmpeg -f lavfi -i nullsrc=s=64x64:d=0.1 -c:v {encoder} -f null -
```

### 优先级链

| 平台 | HEVC 优先级 |
|------|------------|
| macOS | hevc_videotoolbox → libx265 → libx264 |
| Windows | hevc_nvenc → hevc_qsv → hevc_amf → libx265 → libx264 |
| Linux | hevc_nvenc → hevc_vaapi → libx265 → libx264 |

### 接口

```python
class EncoderRegistry:
    def detect(self) -> list[str]:
        """启动时探测所有可用编码器，返回列表"""

    def get_best_hevc(self) -> str | None:
        """返回最优硬件 HEVC 编码器，无则返回 None"""

    def get_fallback(self) -> str:
        """始终返回 'libx264'"""
```

### 回退机制

FFmpegWorker 执行时，如果硬件编码器失败（returncode != 0），自动用 `get_fallback()` 重新构建命令并重试。

---

## 6. 统一队列系统

### 6.1 QueueManager (core/queue_manager.py)

```python
class QueueManager:
    _tasks: list[QueueTask]
    _path: Path                     # ~/.jh-media-helper/queue.json

    def add_task(self, task: QueueTask): ...
    def remove_task(self, task_id: str): ...
    def move_task(self, task_id: str, offset: int): ...  # -1 上移, +1 下移
    def clear_all(self): ...
    def get_task(self, task_id: str) -> QueueTask | None: ...
    def next_pending(self) -> QueueTask | None: ...      # 第一个 PENDING

    def save(self): ...             # 序列化到 JSON
    def load(self): ...             # 启动时读取
```

### 6.2 持久化

- 路径：`~/.jh-media-helper/queue.json`
- 格式：JSON 数组，每个元素是 QueueTask.to_dict()
- 保存时机：任务增删、状态变更、应用关闭

### 6.3 恢复策略

1. 启动时读取 queue.json
2. 状态为 PROCESSING 的任务自动改为 PENDING
3. 如有未完成任务，弹窗询问：继续 / 清空 / 忽略

### 6.4 队列控制

- **开始队列**：从第一个 PENDING 任务开始，逐个执行
- **取消当前**：终止当前 FFmpeg 进程，标记 CANCELLED，继续下一个
- **清空队列**：删除所有任务
- 暂停功能后续迭代

---

## 7. FFmpegWorker (worker/ffmpeg_worker.py)

```python
class FFmpegWorker(QThread):
    progress = pyqtSignal(int, int, str)    # (current_frame, total_frames, description)
    finished = pyqtSignal(str)              # output_path
    error    = pyqtSignal(str)              # error_message

    _cancel_event: threading.Event

    def __init__(self, task_type: TaskType, config: dict, encoder_registry: EncoderRegistry): ...

    def run(self):
        # 1. 根据 task_type 选择 processor
        # 2. 调用 processor.validate() 前置校验
        # 3. 调用 processor.build_command() 构建命令
        # 4. subprocess.Popen 执行，实时解析 stderr 的 frame= 进度
        # 5. 硬件编码失败 → 回退 libx264 重试
        # 6. 发射 finished 或 error 信号

    def cancel(self):
        self._cancel_event.set()
```

### 进度解析

从 FFmpeg stderr 输出中正则匹配 `frame=\s*(\d+)`，结合 validate 返回的总帧数计算百分比。

### 队列执行链

```
QueueTab._run_next()
  → QueueManager.next_pending()
  → FFmpegWorker(task_type, config)
  → worker.finished → mark COMPLETED → _run_next()
  → worker.error → mark FAILED → _run_next()
```

---

## 8. GUI 设计

### 8.1 MainWindow (gui/main_window.py)

QMainWindow，包含 QTabWidget：

```
┌─────────────────────────────────────────┐
│ [单任务] [批量队列 (N)] [设置]           │
└─────────────────────────────────────────┘
```

- 单任务 Tab：任务类型选择器 + 动态参数面板 + 操作栏
- 批量队列 Tab：QueueTab
- 设置 Tab：SettingsTab

### 8.2 单任务 Tab 布局

```
┌──────────────────────┬──────────────────┐
│ 任务类型: [图片序列转视频 ▼]              │
├──────────────────────┬──────────────────┤
│                      │   编码参数        │
│  图片序列文件夹       │   ─────────       │
│  [____路径____][浏览]│   帧率: [120]     │
│                      │   比特率: [32]Mbps │
│  ┌─文件信息────────┐ │   分辨率: 自动探测  │
│  │ 1,247 张图片    │ │     [3840]x[2160] │
│  │ %06d.png (自动) │ │   扫描格式:        │
│  │ 000001→001247   │ │     %06d.png(自动) │
│  └─────────────────┘ │   输出格式:        │
│                      │     [MOV ProRes ▼] │
│  输出目录 (可选)      │   背景模式:        │
│  [____路径____][浏览]│     (透明-锁定)    │
│                      │   硬件加速: [✓]    │
│  进度条 65% 810/1247 │     hevc_vtb ✓    │
├──────────────────────┴──────────────────┤
│        [取消]  [加入队列]  [开始处理]     │
└─────────────────────────────────────────┘
```

**输出格式联动逻辑**：
- 选择 MOV ProRes → 背景模式锁定为"透明"，不可选
- 选择 MP4 H.265/H.264 → 背景模式可选：绿幕（默认）/ 蓝幕

### 8.3 批量队列 Tab

```
┌─────────────────────────────────────────┐
│ [开始队列] [取消当前] [清空]             │
├────┬──────────┬──────────┬──────┬──────┤
│ #  │ 类型     │ 输入     │ 状态 │ 操作 │
├────┼──────────┼──────────┼──────┼──────┤
│ 1  │ 图片序列 │ scene01/ │ ✓完成│  ✕   │
│ 2  │ 图片序列 │ scene02/ │ ▶处理│ ████ │
│ 3  │ 图片序列 │ scene03/ │ 等待 │  ✕   │
└────┴──────────┴──────────┴──────┴──────┘
```

- 不同任务类型用颜色标签区分
- 支持拖拽排序、删除
- 当前处理任务显示进度条

### 8.4 设置 Tab

- 数据目录配置
- 默认参数预设（后续迭代）

---

## 9. 错误处理

| 场景 | 处理 |
|------|------|
| 文件夹不存在 | validate 阶段报错，阻止开始 |
| 无匹配图片 | validate 阶段报错 |
| scan_format 探测失败 | GUI 弹出输入框，用户手动填写 |
| 硬件编码器失败 | 自动回退 libx264 重试 |
| FFmpeg 进程异常退出 | 显示 stderr 错误日志 |
| 队列任务失败 | 标记 FAILED，继续下一个任务 |

---

## 10. 技术约束

| 项目 | 规格 |
|------|------|
| Python | 3.10+ |
| GUI | PyQt6 |
| 图片元数据 | Pillow (PIL) |
| FFmpeg/ffprobe | 系统 PATH 中的命令行工具 |
| 配置存储 | ~/.jh-media-helper/queue.json |

---

## 11. M1 验收标准

- [ ] 选择图片文件夹，自动探测 scan_format 和分辨率
- [ ] 探测失败时可手动输入 scan_format
- [ ] MOV ProRes 4444 透明通道输出（默认）
- [ ] MP4 H.265/H.264 输出，支持绿幕/蓝幕背景模式
- [ ] 硬件加速编码，失败自动回退 libx264
- [ ] 编码进度实时显示
- [ ] 任务可加入统一队列
- [ ] 队列支持开始/取消/清空
- [ ] 队列持久化，重启后恢复
- [ ] 跨平台编码器检测（macOS VideoToolbox / Windows NVENC/QSV）

---

## 12. 后续迭代

- M2: CombatVideoWithAudios（音视频混合，Loudnorm 标准化）
- M3: VideoExtractor（MKV 解包）
- 队列暂停/恢复功能
- 设置 Tab 默认参数预设
