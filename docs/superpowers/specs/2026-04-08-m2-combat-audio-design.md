# M2: CombatVideoWithAudios（音视频混合）设计文档

**日期**: 2026-04-08  
**状态**: 设计完成，待实施

---

## 1. 功能概述

批量为视频/音频混合背景音乐。用户选择一个输入文件（视频或纯音频）和一个背景音乐目录，系统将输入音轨与每个背景音乐依次混合，输出混合音频文件或封装为 MKV。

支持两种工作模式：
- **混合模式**（默认）：将输入音轨与背景音乐混合，输出混合后的音频
- **仅对齐模式**：跳过混音，仅将背景音乐按输入时长裁剪/循环后直接输出

### 核心特性

- 支持视频文件（MP4/MKV）和纯音频文件（AAC/MP3/WAV）作为输入
- 两种工作模式：混合模式 / 仅对齐模式
- MKV 多音轨选择
- 背景音乐列表可拖拽排序，决定输出文件顺序和 MKV 音轨顺序
- 试听预览：输入音轨、背景音乐、混合结果（5 秒片段，仅混合模式）
- 并行处理（可配置线程数）
- 管线：提取音频 → 调整时长 → 混音（仅混合模式）→ 可选封装 MKV

---

## 2. 面板布局

`CombatAudioPanel` 继承 `BaseTaskPanel`，但不使用基类的左右分栏（`_init_base_layout`），而是自定义四区布局：上区、中区、下区、底部操作栏。

### 2.1 整体结构

```
┌─────────────────────────────────────────────────────────────┐
│                        上区                                  │
│  ┌─ 左：文件选择与信息 ────────┬─ 右：参数配置 ─────────────┐ │
│  │                            │                             │ │
│  └────────────────────────────┴─────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                        中区                                  │
│  ┌─ 左：输入音轨表 ───────────┬─ 右：背景音乐表 ────────────┐ │
│  │                            │                             │ │
│  └────────────────────────────┴─────────────────────────────┘ │
│  ┌─ 播放器条 ───────────────────────────────────────────────┐ │
│  └──────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                        下区                                  │
│  ┌─ 进度条 ─────────────────────────────────────────────────┐ │
│  └──────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│           [试听混合]  [取消]  [加入队列]  [开始处理]           │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 上区 — 文件选择与参数

水平分割，左右两列。

**左列（stretch=2）：文件选择与信息**

```
┌─ 文件选择与信息 ──────────────────────┐
│ 输入视频/音频                          │
│ [浏览...]  /path/to/video.mkv         │
│                                        │
│ 音频目录                               │
│ [浏览...]  /path/to/audio_dir         │
│                                        │
│ ┌─ 文件信息 ────────────────────────┐  │
│ │ 类型: MKV (H.264)                 │  │
│ │ 时长: 01:23:45                    │  │
│ │ 背景音乐: 8 个文件                 │  │
│ │ 输出位置: /path/to/output         │  │
│ └───────────────────────────────────┘  │
└────────────────────────────────────────┘
```

- 输入文件：使用 `FileSelector`（file 模式），过滤器接受视频和音频格式
- 音频目录：使用 `FileSelector`（directory 模式）
- 文件信息 `QGroupBox`：选择文件后自动用 ffprobe 探测并显示

**右列（stretch=1）：参数配置**

```
┌─ 参数配置 ──────────────────────┐
│ ┌─ 混音参数 ──────────────────┐ │
│ │ 混合原始音轨  [☑ QCheckBox] │ │
│ │ 并行线程数  [QSpinBox 1-16] │ │
│ │ 原视频响度  [QDoubleSpinBox] │ │
│ │             范围 0.0-1.0    │ │
│ │             步进 0.1        │ │
│ │             默认 0.6        │ │
│ └─────────────────────────────┘ │
│                                  │
│ ┌─ 输出设置 ──────────────────┐ │
│ │ 是否封装MKV  [QCheckBox]    │ │
│ │ 输出目录  [FileSelector]    │ │
│ └─────────────────────────────┘ │
└──────────────────────────────────┘
```

- **混合原始音轨**：`QCheckBox`，默认勾选。取消勾选 = 仅对齐模式，此时：
  - "原视频响度" 灰显禁用
  - "试听混合" 按钮禁用
  - 处理管线跳过混音阶段，直接输出时长对齐后的背景音乐
- 并行线程数：`QSpinBox`，范围 1-16，默认 1
- 原视频响度：`QDoubleSpinBox`，范围 0.0-1.0，步进 0.1，默认 0.6
- 是否封装 MKV：`QCheckBox`，默认不勾选；纯音频输入时自动禁用灰显
- 输出目录：`FileSelector`（directory 模式），默认为输入文件同级目录

**参数联动规则汇总**：

| 条件 | 原视频响度 | 试听混合 | 是否封装MKV |
|---|---|---|---|
| 混合原始音轨=勾选 + 视频输入 | 启用 | 启用（需选中音轨+背景） | 启用 |
| 混合原始音轨=勾选 + 音频输入 | 启用 | 启用（需选中音轨+背景） | 禁用 |
| 混合原始音轨=取消 + 视频输入 | 禁用 | 禁用 | 启用 |
| 混合原始音轨=取消 + 音频输入 | 禁用 | 禁用 | 禁用 |

### 2.3 中区 — 音轨选择与预览

水平分割为左右两个表格，下方共享一个播放器条。

**左表：输入音轨**

```
┌─ 输入音轨 ────────────────────────────┐
│ ○  #0  AAC  48kHz  立体声       [▶]  │
│ ○  #1  AC3  48kHz  5.1声道      [▶]  │
│ ●  #2  AAC  44.1kHz  立体声     [▶]  │
└───────────────────────────────────────┘
```

| 列 | 内容 | 说明 |
|---|---|---|
| 选择 | `QRadioButton` | 单选，选择作为混合基底的音轨 |
| 索引 | `#N` | ffprobe 报告的流索引 |
| 编码 | AAC/AC3/FLAC 等 | 编码格式 |
| 采样率 | 48kHz/44.1kHz | - |
| 声道 | 立体声/5.1/单声道 | - |
| 播放 | `[▶]` 按钮 | 点击在底部播放条预览该音轨 |

行为：
- 选择输入文件后，ffprobe 探测所有音频流，填充表格
- MP4 通常只有一个音轨，自动选中
- 纯音频文件：一行，显示文件本身信息，自动选中
- MKV 多音轨：用户 radio button 选择

**右表：背景音乐**

```
┌─ 背景音乐 (8) ───────────────────────┐
│ ≡  01  jazz_smooth.mp3   03:25  [▶]  │
│ ≡  02  piano_soft.mp3    02:18  [▶]  │
│ ≡  03  guitar_loop.wav   01:45  [▶]  │
│ ...                                   │
└───────────────────────────────────────┘
```

| 列 | 内容 | 说明 |
|---|---|---|
| 拖拽 | `≡` 手柄 | 拖拽排序 |
| 序号 | 自增 | 拖拽后自动重新编号 |
| 文件名 | 文件名 | - |
| 时长 | MM:SS | ffprobe 获取 |
| 播放 | `[▶]` 按钮 | 点击在底部播放条预览 |

行为：
- 选择音频目录后，扫描目录下所有音频文件（aac/mp3/wav/flac），ffprobe 获取时长，填充表格
- 拖拽排序决定：输出文件命名序号、MKV 音轨顺序
- 点击行高亮选中（单选），用于试听混合
- 封装 MKV 时，表格第一行对应的混合音频为 MKV 默认音轨

**底部播放器条**

```
┌─ 播放器 ──────────────────────────────────────────────┐
│ ▶  jazz_smooth.mp3   00:12 / 03:25   ━━━░░░░░  [⏹]  │
└───────────────────────────────────────────────────────┘
```

- 使用 `QMediaPlayer` + `QAudioOutput`（PyQt6-QtMultimedia）
- 显示：播放/暂停按钮、当前播放源名称、时间进度、进度滑条、停止按钮
- 左表 `[▶]`、右表 `[▶]`、试听混合结果 共享此播放条
- 同一时间只播放一个，点击其他 `[▶]` 自动停止当前播放

### 2.4 下区 — 处理进度

复用现有 `ProgressSection` 组件。

```
┌─ 处理进度 ──────────────────────────────────────────┐
│ [3/8] jazz_smooth.mp3 — 混音                         │
│ ██████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░  62%   │
└──────────────────────────────────────────────────────┘
```

- 单进度条 + 描述文字
- 描述格式：`[当前/总数] 文件名 — 阶段名`
- 阶段名：`提取音频` / `调整时长` / `混音` / `封装MKV`
- 每个阶段内进度条 0%→100%，切阶段时重置

### 2.5 底部操作栏

```
[试听混合]  [取消]  [加入队列]  [开始处理]
```

- **试听混合**：左表有选中音轨 + 右表有高亮行时启用，否则禁用。点击后 ffmpeg 生成 5 秒混合片段，播放条自动播放。
- **取消/加入队列/开始处理**：复用现有 ActionBar 逻辑

---

## 3. 数据模型

### 3.1 CombatAudioConfig（dataclass）

```python
@dataclass
class CombatAudioConfig:
    input_path: str           # 输入视频/音频文件路径
    audio_dir: str            # 背景音乐目录路径
    output_dir: str           # 输出目录路径
    mix_enabled: bool         # 是否混合原始音轨，默认 True；False = 仅对齐模式
    volume: float             # 原视频响度 0.0-1.0，默认 0.6（仅 mix_enabled=True 时有效）
    boxed: bool               # 是否封装 MKV，默认 False
    thread_count: int         # 并行线程数，默认 1
    audio_stream_index: int   # 选中的输入音轨索引，默认 0
    audio_order: list[str]    # 背景音乐文件名列表（用户排序后的顺序）
```

- `to_dict()` / `from_dict()` 方法用于队列序列化
- 存放在 `src/core/config.py`

### 3.2 输入类型判断

通过文件扩展名判断：
- 纯音频：扩展名在 `{"aac", "mp3", "wav", "flac"}` 中
- 视频：其他（mp4, mkv, mov 等）

---

## 4. 处理器（Processor）

新建 `src/core/processors/combat_audio.py`，纯函数模块，与 `pic_seq.py` 风格一致。

### 4.1 函数列表

| 函数 | 输入 | 输出 | 说明 |
|---|---|---|---|
| `probe_audio_streams(file_path)` | 文件路径 | `list[AudioStreamInfo]` | ffprobe 探测所有音频流信息 |
| `probe_duration(file_path)` | 文件路径 | `float` (秒) | 获取时长 |
| `scan_audio_dir(dir_path)` | 目录路径 | `list[AudioFileInfo]` | 扫描目录下音频文件，返回文件名+时长 |
| `is_pure_audio(file_path)` | 文件路径 | `bool` | 判断是否纯音频文件 |
| `validate(config)` | `CombatAudioConfig` | `(ok, error_msg)` | 校验输入有效性 |
| `build_extract_command(input_path, stream_index, output_path)` | - | `list[str]` | 构建音频提取命令 |
| `build_duration_adjust_command(audio_path, target_duration, output_path)` | - | `list[str]` | 构建时长调整命令（循环/裁剪） |
| `build_mix_command(base_audio, bg_audio, volume, output_path)` | - | `list[str]` | 构建混音命令（含 loudnorm） |
| `build_mux_command(video_path, mixed_audios, output_path)` | - | `list[str]` | 构建 MKV 封装命令 |
| `build_preview_command(base_audio, bg_audio, volume, output_path)` | - | `list[str]` | 构建 5 秒试听片段命令 |

### 4.2 AudioStreamInfo / AudioFileInfo

```python
@dataclass
class AudioStreamInfo:
    index: int          # 流索引
    codec: str          # 编码格式 (aac, ac3, flac...)
    sample_rate: int    # 采样率
    channels: int       # 声道数
    channel_layout: str # 声道布局描述 (stereo, 5.1...)

@dataclass
class AudioFileInfo:
    filename: str       # 文件名
    path: str           # 完整路径
    duration: float     # 时长（秒）
```

### 4.3 FFmpeg 命令详情

**音频提取**（从视频中提取选中音轨）：
```
ffmpeg -i <input> -map 0:a:<index> -c:a copy <output.aac>
```

**时长调整**：
- 背景音乐 >= 基底时长：裁剪
  ```
  ffmpeg -i <audio> -af "atrim=0:<duration>" -c:a aac <output.aac>
  ```
- 背景音乐 < 基底时长：循环后裁剪
  ```
  ffmpeg -i <audio> -af "aloop=-1:1,atrim=0:<duration>" -c:a aac <output.aac>
  ```

**混音**（忠实复刻 Java 版 loudnorm 链）：
```
ffmpeg -hwaccel auto
  -i <base_audio>
  -i <bg_audio>
  -filter_complex
    "[0:a]loudnorm=I=-14:TP=-1.0:LRA=15[main];
     [1:a]loudnorm=I=-14:TP=-1.0:LRA=15[bg];
     [main][bg]amix=inputs=2:duration=first:dropout_transition=1:weights=<volume> 1:normalize=0,volume=2,loudnorm=I=-14:TP=-1.0:LRA=15"
  -c:a aac -b:a 192k <output.aac>
```

**MKV 封装**：
```
ffmpeg
  -i <video>
  -i <mixed_0.aac>
  [-i <mixed_1.aac> ...]
  -map 0:v
  -map 0:s?
  -map 1:a -map 2:a ...   (按用户排序顺序)
  -map 0:a                 (原始音轨保留在最后)
  -c copy
  <output.mkv>
```

**试听预览**（5 秒片段）：
```
ffmpeg -hwaccel auto
  -i <base_audio>
  -i <bg_audio>
  -filter_complex
    "[0:a]atrim=0:5,loudnorm=I=-14:TP=-1.0:LRA=15[main];
     [1:a]atrim=0:5,loudnorm=I=-14:TP=-1.0:LRA=15[bg];
     [main][bg]amix=inputs=2:duration=first:dropout_transition=1:weights=<volume> 1:normalize=0,volume=2,loudnorm=I=-14:TP=-1.0:LRA=15"
  -c:a aac -b:a 192k <output_preview.aac>
```

### 4.4 输出文件命名

**混合模式 + 封装=False**：
```
<output_dir>/<input_name>_mixed_00.aac
<output_dir>/<input_name>_mixed_01.aac
...
```

**仅对齐模式 + 封装=False**：
```
<output_dir>/<input_name>_aligned_00.aac
<output_dir>/<input_name>_aligned_01.aac
...
```

序号均按背景音乐表格排序顺序。

**封装=True（输出 MKV，仅视频输入可用）**：
```
<output_dir>/<input_name>_<timestamp>.mkv
```
MKV 内音轨顺序：混合/对齐后的音频按表格顺序排列在前，原始音轨在最后。第一条音轨为默认音轨（打开即播放）。

---

## 5. Worker 集成

### 5.1 FFmpegWorker 扩展

在现有 `FFmpegWorker.run()` 中增加 `TaskType.COMBAT_AUDIO` 分支，调用 `_run_combat_audio()` 方法。

### 5.2 _run_combat_audio() 处理流程

```
1. 从 config dict 重建 CombatAudioConfig
2. 判断输入类型（纯音频 / 视频）
3. 创建临时目录
4. 阶段一：提取音频
   - 纯音频：复制文件作为基底（获取时长）
   - 视频：ffmpeg 提取选中音轨
   - 进度: "[0/N] — 提取音频"
5. 阶段二：调整时长（ThreadPoolExecutor 并行）
   - 每个背景音乐：比较时长，循环/裁剪
   - 进度: "[i/N] filename — 调整时长"
6. 阶段三（仅 mix_enabled=True）：混音（ThreadPoolExecutor 并行）
   - 每个背景音乐：loudnorm + amix 混合
   - 进度: "[i/N] filename — 混音"
   - mix_enabled=False 时跳过此阶段，阶段二的输出即为最终音频
7. 阶段四（可选）：封装 MKV
   - 仅 boxed=True 且输入为视频时执行
   - mix_enabled=True: 将混合音频封装进 MKV
   - mix_enabled=False: 将时长对齐后的背景音乐封装进 MKV
   - 进度: "[N/N] — 封装MKV"
8. 清理临时目录
9. emit finished(output_path)
```

### 5.3 并行策略

- 阶段二和阶段三内部使用 `concurrent.futures.ThreadPoolExecutor(max_workers=thread_count)`
- 每个线程启动独立的 ffmpeg 子进程
- 阶段间严格串行（阶段二全部完成后才开始阶段三）
- 取消时：设置 `_cancel_event`，终止所有活跃子进程

### 5.4 进度信号

复用现有 `progress(int, int, str)` 信号：
- `current`: 当前已完成的项数（阶段内）
- `total`: 当前阶段总项数
- `desc`: `"[i/N] filename — 阶段名"` 格式字符串

阶段切换时 current 重置为 0，ProgressSection 进度条随之从 0% 开始。

---

## 6. 播放器组件

### 6.1 AudioPlayerBar（新组件）

放在 `src/gui/components/audio_player.py`。

```python
class AudioPlayerBar(QWidget):
    """共享音频播放条，基于 QMediaPlayer"""
```

**UI 组成**：
- 播放/暂停按钮（`QPushButton`，图标切换）
- 源名称标签（`QLabel`，显示当前播放的文件名/音轨描述）
- 时间标签（`QLabel`，`00:12 / 03:25` 格式）
- 进度滑条（`QSlider`，可拖拽跳转）
- 停止按钮（`QPushButton`）

**API**：
- `play_file(file_path, display_name)` — 播放本地音频/视频文件
- `play_stream(file_path, stream_index, display_name)` — 播放视频中指定音轨（先提取到临时文件再播放）
- `stop()` — 停止播放
- `is_playing() -> bool`

**行为**：
- 调用 `play_*` 时自动停止当前播放
- 播放结束自动回到停止状态
- 播放视频音轨时，先用 ffmpeg 快速提取到临时文件（仅提取 5-10 秒片段用于预览），再用 QMediaPlayer 播放

### 6.2 依赖

需要安装 `PyQt6-QtMultimedia`：
```
pip install PyQt6-QtMultimedia
```

---

## 7. 试听混合功能

### 7.1 触发条件

"试听混合" 按钮启用条件（全部满足才启用）：
- "混合原始音轨" checkbox 已勾选（仅对齐模式下禁用）
- 左表（输入音轨）有 radio button 选中
- 右表（背景音乐）有行高亮选中

### 7.2 流程

1. 获取左表选中音轨索引、右表高亮行的音频文件路径、当前响度参数
2. 如果输入是视频：先提取选中音轨到临时文件（如果已提取过则复用缓存）
3. 调用 `build_preview_command()` 生成 5 秒混合片段到临时文件
4. 播放条自动播放生成的临时文件
5. 用户调整响度后可再次点击试听（重新生成）

### 7.3 临时文件

试听临时文件放在系统 temp 目录（`tempfile.mkdtemp()`），面板关闭或切换时清理。

---

## 8. 面板与基类的关系

### 8.1 BaseTaskPanel 的使用方式

`CombatAudioPanel` 继承 `BaseTaskPanel` 但**不调用** `_init_base_layout()`。原因：M2 的四区布局（上区文件+参数、中区双表格+播放器、下区进度、底部操作栏）与基类的左右二分布局不兼容。

`CombatAudioPanel` 仍然实现基类的抽象方法：
- `validate() -> (bool, str)` — 校验输入有效性
- `build_config() -> CombatAudioConfig` — 从 UI 构建配置对象
- `get_task_type() -> TaskType` — 返回 `TaskType.COMBAT_AUDIO`
- `on_progress(current, total, desc)` — 更新进度条
- `on_finished(output_path)` — 处理完成回调

### 8.2 BaseTaskPanel 调整

当前 `__init__` 在第 66 行自动调用 `_init_base_layout()`。改造方案：

1. `__init__` 增加 `init_layout: bool = True` 参数
2. 仅当 `init_layout=True` 时调用 `_init_base_layout()`
3. `PicSeqPanel` 不传参，保持默认 `True`，行为不变
4. `CombatAudioPanel.__init__` 传 `init_layout=False`，然后自建布局
5. `_build_left_panel` / `_build_settings_panel` 在 `CombatAudioPanel` 中不使用，实现为空方法（或 raise NotImplementedError 由 `init_layout=False` 保护不被调用）

---

## 9. MainWindow 集成

### 9.1 新增 Tab

在 `MainWindow.__init__` 中添加 `CombatAudioPanel` 作为新 tab：

```python
self._combat_panel = CombatAudioPanel()
self._tabs.addTab(self._combat_panel, "音视频混合")
```

### 9.2 已有机制自动适配

- `_on_tab_changed`：已使用 `isinstance(widget, BaseTaskPanel)` 判断，`CombatAudioPanel` 自动被识别，ActionBar 自动显示/隐藏
- `_on_start` / `_on_finished` / `_on_error`：按 `task_type` 分发，新增 `COMBAT_AUDIO` 分支
- 队列系统：`QueueTask.create()` 接受任意 config dict，无需改动

---

## 10. 错误处理

| 场景 | 处理方式 |
|---|---|
| 输入文件不存在 | `validate()` 前置校验报错 |
| 音频目录不存在或为空 | `validate()` 前置校验报错 |
| 输入视频无音频流 | 探测后表格为空，禁用开始按钮 |
| ffmpeg 提取/混音失败 | 记录错误，跳过当前背景音乐，继续处理下一个 |
| 临时文件清理失败 | 静默忽略，打印日志 |
| QMediaPlayer 播放失败 | 播放条显示错误提示 |

---

## 11. 文件结构变更

```
src/
  core/
    config.py                    # 新增 CombatAudioConfig
    processors/
      combat_audio.py            # 新建：纯函数处理器
  gui/
    task_panels/
      base_panel.py              # 调整：_init_base_layout 改为可选
      combat_audio_panel.py      # 新建：M2 面板
    components/
      audio_player.py            # 新建：共享播放器组件
  worker/
    ffmpeg_worker.py             # 扩展：新增 _run_combat_audio()
```

---

## 12. 验收标准

**混合模式：**
- [ ] 选择视频文件 + 音频目录，成功生成混合音频文件
- [ ] 选择纯音频文件 + 音频目录，成功生成混合音频文件
- [ ] 选择 MKV 多音轨文件，可选择音轨，混合正确
- [ ] 试听混合生成 5 秒片段并播放

**仅对齐模式：**
- [ ] 取消勾选"混合原始音轨"，成功输出时长对齐后的背景音乐
- [ ] 仅对齐模式下 "原视频响度" 灰显、"试听混合" 禁用
- [ ] 仅对齐 + 封装 MKV：对齐后的背景音乐正确封装进 MKV

**通用：**
- [ ] 封装 MKV 模式：音轨按表格顺序排列，第一条为默认音轨
- [ ] 并行线程数生效（可配置 1-16）
- [ ] 背景音乐表格可拖拽排序，输出顺序正确
- [ ] 输入音轨可预览播放
- [ ] 背景音乐可预览播放
- [ ] 纯音频输入时 "是否封装MKV" 自动禁用
- [ ] 参数联动规则正确（见 2.2 节联动表）
- [ ] 进度显示正确：`[i/N] filename — 阶段名`，阶段切换时进度重置
- [ ] 临时文件自动清理
- [ ] 任务可加入队列，队列可正常处理
