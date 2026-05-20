import os

from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
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

    def _build_left_panel(self, layout: QVBoxLayout):
        self._input_selector = FileSelector(
            label="图片序列文件夹:",
            placeholder="选择文件夹...",
            dialog_mode="directory",
            drop_enabled=True,
            drop_kind="directory",
        )
        self._input_selector.path_changed.connect(self._on_input_changed)
        layout.addWidget(self._input_selector)

        layout.addWidget(_create_separator())

        self._output_selector = FileSelector(
            label="输出路径:",
            placeholder="与输入文件夹同级",
            dialog_mode="directory",
        )
        layout.addWidget(self._output_selector)

        layout.addWidget(_create_separator())

        self._info_group = QGroupBox("文件信息")
        info_layout = QVBoxLayout(self._info_group)
        self._info_label = QLabel("未选择文件夹")
        self._info_label.setStyleSheet("color: gray;")
        info_layout.addWidget(self._info_label)
        layout.addWidget(self._info_group)

    def _build_settings_panel(self, layout: QVBoxLayout):
        enc_group = QGroupBox("编码参数")
        # 避免组框在父布局富余高度时被垂直拉伸
        enc_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        enc_layout = QVBoxLayout(enc_group)
        enc_layout.setSpacing(16)

        fps_row = QHBoxLayout()
        fps_row.addWidget(QLabel("帧率"))
        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(1, 300)
        self._fps_spin.setValue(120)
        self._fps_spin.setSuffix(" fps")
        fps_row.addWidget(self._fps_spin, 1)
        enc_layout.addLayout(fps_row)

        br_row = QHBoxLayout()
        br_row.addWidget(QLabel("比特率"))
        self._bitrate_spin = QSpinBox()
        self._bitrate_spin.setRange(1, 200)
        self._bitrate_spin.setValue(32)
        self._bitrate_spin.setSuffix(" Mbps")
        br_row.addWidget(self._bitrate_spin, 1)
        enc_layout.addLayout(br_row)

        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("分辨率"))
        self._width_spin = QSpinBox()
        self._width_spin.setRange(1, 7680)
        self._width_spin.setValue(3840)
        res_row.addWidget(self._width_spin, 1)
        res_row.addWidget(QLabel("x"))
        self._height_spin = QSpinBox()
        self._height_spin.setRange(1, 4320)
        self._height_spin.setValue(2160)
        res_row.addWidget(self._height_spin, 1)
        enc_layout.addLayout(res_row)

        sf_row = QHBoxLayout()
        sf_row.addWidget(QLabel("扫描格式"))
        self._scan_format_edit = QLineEdit()
        self._scan_format_edit.setPlaceholderText("自动探测")
        sf_row.addWidget(self._scan_format_edit, 1)
        enc_layout.addLayout(sf_row)

        layout.addWidget(enc_group)
        layout.addSpacing(8)

        out_group = QGroupBox("输出设置")
        # 避免输出设置区域被无意义地拉高，导致内部大片空白
        out_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        out_layout = QVBoxLayout(out_group)
        out_layout.setSpacing(12)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("格式"))
        self._format_combo = QComboBox()
        self._format_combo.addItem("MOV ProRes 4444 (透明)", OutputFormat.MOV_PRORES)
        self._format_combo.addItem("MP4 H.265", OutputFormat.MP4_HEVC)
        self._format_combo.addItem("MP4 H.264", OutputFormat.MP4_H264)
        self._format_combo.currentIndexChanged.connect(self._on_format_changed)
        fmt_row.addWidget(self._format_combo, 1)
        out_layout.addLayout(fmt_row)

        self._bg_row = QHBoxLayout()
        self._bg_label = QLabel("背景")
        self._bg_row.addWidget(self._bg_label)
        self._bg_combo = QComboBox()
        self._bg_combo.addItem("透明", BackgroundMode.TRANSPARENT)
        self._bg_combo.addItem("绿幕", BackgroundMode.GREEN)
        self._bg_combo.addItem("蓝幕", BackgroundMode.BLUE)
        self._bg_row.addWidget(self._bg_combo, 1)

        self._bg_widget = QWidget()
        self._bg_widget.setLayout(self._bg_row)
        self._bg_widget.setVisible(False)
        out_layout.addWidget(self._bg_widget)

        layout.addWidget(out_group)

        layout.addSpacing(8)

        self._hw_label = QLabel("")
        self._hw_label.setStyleSheet("color: gray; font-size: 11px;")
        self._update_hw_label()
        layout.addWidget(self._hw_label)
        # 把剩余空白固定到最底部，而不是分摊给各个组框
        layout.addStretch()

    def _on_input_changed(self, path: str):
        self._detect(path)

    def _detect(self, input_dir: str):
        # 每次切换文件夹都清空手输的扫描格式，避免沿用上一目录导致校验仍读旧字符串
        self._scan_format_edit.clear()
        self._scan_format_edit.setPlaceholderText("自动探测")

        result = detect_scan_format(input_dir)
        if result is None:
            self._detected_scan_format = None
            self._file_count = 0
            self._detected_width = None
            self._detected_height = None
            # 探测失败时分辨率恢复默认，避免显示上一文件夹的宽高
            self._width_spin.setValue(3840)
            self._height_spin.setValue(2160)
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
            # 读不到首帧时回到默认分辨率，与首次打开面板一致
            self._width_spin.setValue(3840)
            self._height_spin.setValue(2160)

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
            self._bg_combo.setCurrentIndex(1)

    def _update_hw_label(self):
        best = self._encoder_registry.get_best_hevc()
        if best:
            self._hw_label.setText(f"硬件加速: {best} ✓")
        else:
            self._hw_label.setText("硬件加速: 不可用 (将使用 libx264)")
            self._hw_label.setStyleSheet("color: gray; font-size: 11px;")

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
