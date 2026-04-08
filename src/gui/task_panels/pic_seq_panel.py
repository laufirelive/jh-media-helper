import os

from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.core.config import BackgroundMode, OutputFormat, PicSeqConfig
from src.core.encoder_registry import EncoderRegistry
from src.core.processors.pic_seq import detect_alpha, detect_resolution, detect_scan_format


class PicSeqPanel(QWidget):
    def __init__(self, encoder_registry: EncoderRegistry, parent=None):
        super().__init__(parent)
        self._encoder_registry = encoder_registry
        self._detected_scan_format: str | None = None
        self._detected_width: int | None = None
        self._detected_height: int | None = None
        self._file_count: int = 0
        self._init_ui()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)

        # Left side: file selection + info + progress
        left = QVBoxLayout()
        main_layout.addLayout(left, 1)

        left.addWidget(QLabel("图片序列文件夹"))
        input_row = QHBoxLayout()
        self._input_edit = QLineEdit()
        self._input_edit.setReadOnly(True)
        self._input_edit.setPlaceholderText("选择文件夹...")
        input_row.addWidget(self._input_edit)
        self._btn_browse_input = QPushButton("浏览...")
        self._btn_browse_input.clicked.connect(self._browse_input)
        input_row.addWidget(self._btn_browse_input)
        left.addLayout(input_row)

        self._info_group = QGroupBox("文件信息")
        info_layout = QVBoxLayout(self._info_group)
        self._info_label = QLabel("未选择文件夹")
        info_layout.addWidget(self._info_label)
        left.addWidget(self._info_group)

        left.addWidget(QLabel("输出目录 (可选，默认同级)"))
        output_row = QHBoxLayout()
        self._output_edit = QLineEdit()
        self._output_edit.setPlaceholderText("默认: 原文件夹同级目录")
        output_row.addWidget(self._output_edit)
        self._btn_browse_output = QPushButton("浏览...")
        self._btn_browse_output.clicked.connect(self._browse_output)
        output_row.addWidget(self._btn_browse_output)
        left.addLayout(output_row)

        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        left.addWidget(self._progress_bar)
        self._status_label = QLabel("")
        left.addWidget(self._status_label)
        left.addStretch()

        # Right side: parameters
        right = QVBoxLayout()
        main_layout.addLayout(right, 0)

        right.addWidget(QLabel("编码参数"))

        right.addWidget(QLabel("帧率 (fps)"))
        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(1, 300)
        self._fps_spin.setValue(120)
        right.addWidget(self._fps_spin)

        right.addWidget(QLabel("比特率 (Mbps)"))
        self._bitrate_spin = QSpinBox()
        self._bitrate_spin.setRange(1, 200)
        self._bitrate_spin.setValue(32)
        right.addWidget(self._bitrate_spin)

        right.addWidget(QLabel("分辨率"))
        res_row = QHBoxLayout()
        self._width_spin = QSpinBox()
        self._width_spin.setRange(1, 7680)
        self._width_spin.setValue(3840)
        res_row.addWidget(self._width_spin)
        res_row.addWidget(QLabel("x"))
        self._height_spin = QSpinBox()
        self._height_spin.setRange(1, 4320)
        self._height_spin.setValue(2160)
        res_row.addWidget(self._height_spin)
        right.addLayout(res_row)

        right.addWidget(QLabel("扫描格式"))
        self._scan_format_edit = QLineEdit()
        self._scan_format_edit.setPlaceholderText("自动探测")
        right.addWidget(self._scan_format_edit)

        right.addWidget(QLabel("输出格式"))
        self._format_combo = QComboBox()
        self._format_combo.addItem("MOV ProRes 4444 (透明)", OutputFormat.MOV_PRORES)
        self._format_combo.addItem("MP4 H.265", OutputFormat.MP4_HEVC)
        self._format_combo.addItem("MP4 H.264", OutputFormat.MP4_H264)
        self._format_combo.currentIndexChanged.connect(self._on_format_changed)
        right.addWidget(self._format_combo)

        right.addWidget(QLabel("背景模式"))
        self._bg_combo = QComboBox()
        self._bg_combo.addItem("透明", BackgroundMode.TRANSPARENT)
        self._bg_combo.addItem("绿幕", BackgroundMode.GREEN)
        self._bg_combo.addItem("蓝幕", BackgroundMode.BLUE)
        self._bg_combo.setEnabled(False)
        right.addWidget(self._bg_combo)

        self._hw_label = QLabel("")
        self._update_hw_label()
        right.addWidget(self._hw_label)
        right.addStretch()

    def _browse_input(self):
        path = QFileDialog.getExistingDirectory(self, "选择图片序列文件夹")
        if not path:
            return
        self._input_edit.setText(path)
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

    def _browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self._output_edit.setText(path)

    def _on_format_changed(self, index: int):
        fmt = self._format_combo.currentData()
        if fmt == OutputFormat.MOV_PRORES:
            self._bg_combo.setCurrentIndex(0)
            self._bg_combo.setEnabled(False)
        else:
            self._bg_combo.setCurrentIndex(1)
            self._bg_combo.setEnabled(True)

    def _update_hw_label(self):
        best = self._encoder_registry.get_best_hevc()
        if best:
            self._hw_label.setText(f"硬件加速: {best} ✓")
        else:
            self._hw_label.setText("硬件加速: 不可用 (将使用 libx264)")

    def get_config(self) -> PicSeqConfig | None:
        input_dir = self._input_edit.text()
        if not input_dir:
            QMessageBox.warning(self, "提示", "请先选择图片序列文件夹")
            return None

        scan_format = self._scan_format_edit.text() or self._detected_scan_format
        if not scan_format:
            QMessageBox.warning(self, "提示", "无法探测扫描格式，请手动输入")
            return None

        output_dir = self._output_edit.text() or None
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

    def on_progress(self, current: int, total: int, desc: str):
        self._progress_bar.setVisible(True)
        if total > 0:
            self._progress_bar.setMaximum(total)
            self._progress_bar.setValue(current)
        self._status_label.setText(f"{desc}... {current}/{total}")

    def on_finished(self, output_path: str):
        self._progress_bar.setVisible(False)
        self._status_label.setText(f"完成: {output_path}")
