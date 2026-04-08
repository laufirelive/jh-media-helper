# jh-media-helper 开发进度

**最后更新**: 2026-04-08

---

## 里程碑总览

| 里程碑 | 功能 | 状态 | 说明 |
|--------|------|------|------|
| M1 | 图片序列转视频 (PictureSeqConvertToMp4) | ✅ 已完成 | 核心功能 + GUI + 队列 |
| M2 | 音视频混合 (CombatVideoWithAudios) | ⬚ 未开始 | Loudnorm 标准化 |
| M3 | MKV 解包 (VideoExtractor) | ⬚ 未开始 | |
| M4 | 队列暂停/恢复 | ⬚ 未开始 | 需要设计暂停策略 |

---

## M1 详细进度

### 基础设施

| 模块 | 文件 | 状态 | 测试 |
|------|------|------|------|
| 项目脚手架 | `requirements.txt`, `__init__.py` | ✅ | - |
| 配置枚举 + PicSeqConfig | `src/core/config.py` | ✅ | 6 tests |
| 数据目录 | `src/core/data_dir.py` | ✅ | 3 tests |
| 编码器检测 | `src/core/encoder_registry.py` | ✅ | 6 tests |
| QueueTask | `src/core/queue_task.py` | ✅ | 3 tests |
| QueueManager | `src/core/queue_manager.py` | ✅ | 9 tests |

### M1 核心逻辑

| 模块 | 文件 | 状态 | 测试 |
|------|------|------|------|
| scan_format 自动探测 | `src/core/processors/pic_seq.py` | ✅ | 5 tests |
| 分辨率/alpha 探测 | `src/core/processors/pic_seq.py` | ✅ | 3 tests |
| 校验 (validate) | `src/core/processors/pic_seq.py` | ✅ | 3 tests |
| 命令构建 (build_command) | `src/core/processors/pic_seq.py` | ✅ | 6 tests |

### Worker

| 模块 | 文件 | 状态 | 测试 |
|------|------|------|------|
| FFmpegWorker + 进度解析 | `src/worker/ffmpeg_worker.py` | ✅ | 4 tests |

### GUI

| 模块 | 文件 | 状态 |
|------|------|------|
| MainWindow (3 Tab) | `src/gui/main_window.py` | ✅ |
| PicSeqPanel (参数面板) | `src/gui/task_panels/pic_seq_panel.py` | ✅ |
| QueueTab (批量队列) | `src/gui/queue_tab.py` | ✅ |
| SettingsTab (设置) | `src/gui/settings_tab.py` | ✅ |
| 入口 | `main.py` | ✅ |

### 测试汇总

**48 / 48 tests passing**

---

## M1 验收标准

- [x] 选择图片文件夹，自动探测 scan_format 和分辨率
- [x] 探测失败时可手动输入 scan_format
- [x] MOV ProRes 4444 透明通道输出（默认）
- [x] MP4 H.265/H.264 输出，支持绿幕/蓝幕背景模式
- [x] 硬件加速编码，失败自动回退 libx264
- [x] 编码进度实时显示
- [x] 任务可加入统一队列
- [x] 队列支持开始/取消/清空
- [x] 队列持久化，重启后恢复
- [x] 跨平台编码器检测（macOS VideoToolbox / Windows NVENC/QSV）

---

## 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 架构 | 分层 (core/gui/worker) | 复刻 birefnet-gui 模式，core 层可独立测试 |
| 功能分组 | core/processors/ + gui/task_panels/ | M2/M3 扩展时只需新增文件 |
| 队列 | 统一队列，task_type 区分 | 简洁，一处管理所有类型 |
| 编码器 | 跨平台自动检测 | macOS VTB / Windows NVENC/QSV |
| 输出默认 | MOV ProRes 4444 (透明) | 用户常用格式 |
| 背景模式 | 绿幕(默认)/蓝幕 | MP4 无 alpha 时使用 |
| 队列暂停 | 后续迭代 | FFmpeg 进程无法断点续传，需单独设计 |

---

## 后续迭代

- [ ] M2: CombatVideoWithAudios（音视频混合，Loudnorm 标准化）
- [ ] M3: VideoExtractor（MKV 解包）
- [ ] M4: 队列暂停/恢复功能
- [ ] 设置 Tab 默认参数预设
