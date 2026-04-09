# jh-media-helper

一个基于 `PyQt6` 的桌面媒体处理工具，当前主要提供两类工作流：

- 图片序列转视频
- 音视频混合与批量队列处理

## 功能概览

### 图片序列转视频

- 支持将图片序列编码为视频
- 支持 `MOV ProRes 4444`、`MP4 H.265`、`MP4 H.264`
- 自动探测分辨率与扫描格式
- 支持透明背景、绿幕、蓝幕等模式

### 音视频混合

- 支持为视频或纯音频输入批量混入背景音乐
- 支持选择输入音轨
- 支持试听输入音轨与试听混合结果
- 支持预览起点滑条，可从任意时间点试听 `10s`
- 支持短背景音乐循环补足
- 支持封装为 `MKV`

### 批量队列

- 支持将任务加入队列顺序执行
- 支持拖拽调整队列顺序
- 支持取消当前任务
- 当前任务进度按阶段显示，例如：
  - 提取音频
  - 调整时长
  - 混音
  - 封装 MKV

## 运行环境

- Python 3.12+
- FFmpeg / FFprobe
- PyQt6

推荐先确认本机可以直接执行：

```bash
ffmpeg -version
ffprobe -version
python3 --version
```

## 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows:

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

## 启动

```bash
python main.py
```

## 项目结构

```text
main.py
src/
  core/        核心配置、队列、处理器、缓存
  gui/         主窗口、任务面板、组件、队列页
  worker/      FFmpeg 后台线程
tests/         单元测试与 GUI 测试
```

## 测试

常用测试命令：

```bash
pytest tests/test_combat_audio_processor.py tests/test_preview_cache.py -q
pytest tests/test_queue_task.py tests/test_queue_manager.py -q
```

GUI 相关测试在当前项目里通常需要带有 `PyQt6` 的环境，例如：

```bash
PYTHONPATH=. python -m pytest tests/gui/components/test_preview_start_cell.py tests/gui/task_panels/test_combat_audio_panel_preview_start.py -q
```

## 打包说明

这个项目适合用 `PyInstaller` 做桌面打包，但需要分别在目标平台构建：

- macOS 上构建 `.app` / `.dmg`
- Windows 上构建 `.exe`

打包时要额外注意：

- `PyQt6 Multimedia` 插件是否被正确带入
- `ffmpeg` / `ffprobe` 是否随程序分发，或者要求用户预装

## 说明

- 项目运行过程中会在用户数据目录下保存队列、日志、预览缓存等数据
- 预览缓存是会话级缓存，退出应用后无需长期保留
