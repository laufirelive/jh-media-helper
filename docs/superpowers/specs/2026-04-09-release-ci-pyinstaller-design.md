# 发布设计：PyInstaller 双平台打包 + GitHub Actions Release

**日期**: 2026-04-09
**项目**: `jh-media-helper`
**状态**: 已确认设计，待编写实现计划

---

## 1. 目标

为 `jh-media-helper` 增加可重复执行的桌面发布流程，在 GitHub 上稳定产出：

- macOS Apple Silicon 版本
- Windows x64 版本

用户下载后无需安装 Python，即可直接运行应用；但仍需要自行安装 `ffmpeg` 和 `ffprobe`。

---

## 2. 已确认范围

### 2.1 包含在发布物中的内容

- Python 运行时
- 项目源码
- Python 依赖（如 `PyQt6`、`Pillow`）
- PyQt6 运行所需插件与库

### 2.2 不包含在发布物中的内容

- `ffmpeg`
- `ffprobe`
- 安装器逻辑（如 Windows installer、macOS dmg）

### 2.3 发布形式

- Windows：发布 zip，解压后直接运行 `jh-media-helper.exe`
- macOS：发布包含 `jh-media-helper.app` 的 zip，解压后直接运行 `.app`

### 2.4 平台范围

- macOS Apple Silicon
- Windows x64

不在本轮支持范围内：

- macOS Intel
- Linux
- 代码签名 / notarization
- 自动下载 FFmpeg

---

## 3. 总体方案

采用与参考项目相同的大方向，但按当前项目实际复杂度做轻量化实现：

1. 使用 PyInstaller 生成双平台便携版应用
2. 使用 GitHub Actions 执行双平台 matrix 构建
3. 使用 `workflow_dispatch` 进行手动验证构建
4. 使用 `v*` tag 触发正式 Release 上传
5. Release 产物命名包含版本号和平台信息

当前项目依赖较轻，不需要像参考项目那样处理大模型、CUDA 包体和分卷压缩，因此方案应尽量简单、稳定、可维护。

---

## 4. 仓库改动设计

### 4.1 新增 `jh-media-helper.spec`

职责：

- 定义 PyInstaller 打包入口为 `main.py`
- 显式收集 `PyQt6` 与 `PyQt6.QtMultimedia` 运行时所需内容
- 统一走 `onedir` 模式
- macOS 下额外生成 `.app`
- 排除测试和无关开发内容，减少包体噪音

设计原则：

- 不引入与业务逻辑耦合的复杂打包脚本
- 尽量在 spec 中完成平台差异处理
- 维持单一 spec 文件，避免双平台各维护一份

### 4.2 新增 `.github/workflows/build.yml`

职责：

- 定义 Windows 和 macOS 双平台构建
- 支持手动触发构建
- 支持 tag 自动发布到 GitHub Release
- 统一产物命名与压缩逻辑

### 4.3 新增 `src/core/runtime_env.py`

职责：

- 判断是否运行在 PyInstaller 环境
- 提供运行时辅助函数，如 FFmpeg 可用性检测

此模块应保持很薄，只承接“运行环境判断”，不混入业务流程或 GUI 逻辑。

### 4.4 更新 `main.py`

职责：

- 增加 `multiprocessing.freeze_support()`
- 在 GUI 主窗口创建前执行 `ffmpeg` / `ffprobe` 可用性检测
- 缺失时弹窗提示并退出

### 4.5 更新 `README.md`

补充面向最终用户的发布说明：

- 从 GitHub Releases 下载哪个文件
- 无需安装 Python
- 需要先安装 `ffmpeg` / `ffprobe`
- macOS 与 Windows 的建议安装方式

---

## 5. 运行时行为设计

### 5.1 FFmpeg / FFprobe 启动检查

应用启动时统一检测：

- `ffmpeg` 是否在 `PATH`
- `ffprobe` 是否在 `PATH`

检测失败时：

1. 弹出错误对话框
2. 明确告诉用户缺少依赖
3. 给出平台对应安装建议
4. 终止应用启动

提示文案方向与参考项目一致，但内容针对本项目收敛：

- 标题：缺少 FFmpeg
- 内容：
  - 未检测到 `ffmpeg` 或 `ffprobe`
  - 请安装后重新启动应用
  - Windows 推荐 `winget install ffmpeg`
  - macOS 推荐 `brew install ffmpeg`

此检查放在 `QApplication` 创建之后、`MainWindow` 创建之前，保证可以使用原生 GUI 弹窗提示。

### 5.2 Python 运行时打包策略

使用 PyInstaller 默认能力将 Python 解释器和项目依赖一起打入发布物。

用户侧预期：

- 不需要单独安装 Python
- 解压即用
- 只有 FFmpeg 需要额外准备

---

## 6. PyInstaller 设计

### 6.1 打包模式

统一采用 `onedir`：

- Windows：输出包含 `jh-media-helper.exe` 的目录
- macOS：输出 `jh-media-helper.app`

不采用 `onefile`，原因如下：

- PyQt6 桌面应用在 `onefile` 下启动体验通常更差
- 多媒体插件和运行时调试更不直观
- 当前项目没有需要追求单文件分发的强需求

### 6.2 入口与隐藏依赖

spec 应至少覆盖：

- `main.py`
- `PyQt6.QtWidgets`
- `PyQt6.QtMultimedia`
- 项目实际使用到的 GUI / worker / core 模块

重点风险点：

- `PyQt6.QtMultimedia` 的运行时插件收集
- macOS `.app` 中 Qt 多媒体相关 dylib 的完整性

因此实现上应优先使用 PyInstaller 的 Qt hook 与数据收集方式，不手写过多路径拼装。

### 6.3 产物命名

构建产物命名带版本号：

- `jh-media-helper-vX.Y.Z-Windows.zip`
- `jh-media-helper-vX.Y.Z-macOS-ARM.zip`

手动触发时如果没有 tag，可回退使用：

- 短 SHA
- 或 `manual-<run_number>`

但正式 Release 必须以 tag 版本号为准。

---

## 7. GitHub Actions 设计

### 7.1 触发方式

同时支持两种触发：

- `workflow_dispatch`
- `push.tags: v*`

使用方式：

- 日常验证：手动触发
- 正式发版：在 `master` 上打 `v*` tag

### 7.2 Matrix 维度

固定两项：

- `windows-latest`
- `macos-latest`

并为每个平台配置：

- 产物名称
- 压缩方式
- 打包后需收集的目标路径

### 7.3 CI 主要步骤

每个平台统一执行：

1. Checkout 仓库
2. 安装指定 Python 版本
3. 安装 `requirements.txt`
4. 安装 `pyinstaller`
5. 执行 `pyinstaller jh-media-helper.spec`
6. 生成随包分发的 `README.txt`
7. 按平台整理产物目录
8. 压缩为 zip
9. 上传 Actions artifact
10. 若当前为 tag 构建，则上传到 GitHub Release

### 7.4 Release 上传策略

在 tag 构建时：

- 使用 GitHub Actions 自动创建或更新对应 Release
- 上传两个 zip 产物

在手动构建时：

- 仅上传 Actions artifact
- 不发布 Release

---

## 8. 随包说明文件设计

CI 生成的 `README.txt` 用于放入压缩包内，内容保持简短明确：

- 这是便携版应用
- 无需安装 Python
- 需要先安装 `ffmpeg` / `ffprobe`
- Windows 安装建议：`winget install ffmpeg`
- macOS 安装建议：`brew install ffmpeg`
- 解压后直接运行应用

此文件的作用是减少用户只下载 zip、不看仓库 README 时的使用门槛。

---

## 9. Git 工作流设计

按用户要求，本次工作采用分支开发：

1. 从当前 `master` 创建独立分支
2. 在该分支完成打包与 CI 相关改动
3. 本地验证通过后合并回 `master`
4. 再推送 `master`

后续正式发布流程：

1. 保证 `master` 已包含发布改动
2. 在 `master` 创建版本 tag，如 `v0.1.0`
3. 推送 tag
4. GitHub Actions 自动构建并上传 Release

---

## 10. 测试与验证设计

本轮需要的验证分为三层：

### 10.1 本地代码层

- 与新增 FFmpeg 检测相关的单元测试
- 对运行时辅助函数的纯逻辑测试

### 10.2 本地构建层

- 在当前开发机至少验证 macOS PyInstaller 能出 `.app`
- 确认应用启动时：
  - 缺失 FFmpeg 会弹窗退出
  - 存在 FFmpeg 时可正常进入主界面

### 10.3 CI 层

- 手动触发 workflow，确认双平台均能出 artifact
- tag 构建时确认 Release 附件命名符合预期

---

## 11. 风险与处理

### 11.1 PyQt6 Multimedia 插件缺失

风险：

- 打包后应用能启动，但播放相关能力异常

处理：

- 在 spec 中显式关注 `PyQt6.QtMultimedia`
- 优先依赖 PyInstaller 对 Qt 的官方 hook
- 构建后验证 macOS 本地运行

### 11.2 macOS `.app` 可运行但存在系统安全提示

风险：

- 未签名应用首次打开时会被 Gatekeeper 提示

处理：

- 本轮仅在 README 中说明“如遇系统拦截需在系统设置中允许打开”
- 不在本轮引入签名 / notarization

### 11.3 手动构建与正式发布命名不一致

风险：

- 用户或维护者难以区分构建来源

处理：

- tag 构建严格使用版本号
- 非 tag 构建明确标识为手动构建产物

---

## 12. 本轮不做的事情

- 自动下载或内置 FFmpeg
- 平台安装器封装
- macOS Intel 兼容
- Linux 发布
- 自动签名、notarization、Windows 签名
- 自动创建 tag 或自动递增版本号

---

## 13. 推荐实现顺序

1. 增加运行时 FFmpeg 检测与测试
2. 编写 PyInstaller spec
3. 本地验证 macOS 打包
4. 增加 GitHub Actions workflow
5. 更新 README 与随包 README.txt
6. 手动触发 CI 验证
7. 合并到 `master`
8. 后续按版本 tag 正式发布
