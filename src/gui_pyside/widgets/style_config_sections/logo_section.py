"""
Logo 配置区块

启用开关 + 绝对/相对定位切换 + 尺寸/边距/偏移参数
"""
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QGridLayout, QWidget
from PySide6.QtCore import Qt, Signal

from qfluentwidgets import (
    ExpandGroupSettingCard,
    ComboBox, DoubleSpinBox, SwitchButton, SegmentedWidget,
    FluentIcon, BodyLabel,
)

from ...models.style_config_form import (
    ELEMENT_KEYS, PLACEMENT_OPTIONS,
    ANCHOR_POSITION_OPTIONS, ALIGNMENT_OPTIONS,
    RELATIVE_POSITION_OPTIONS,
)


class LogoSection(ExpandGroupSettingCard):
    """Logo 配置区块"""

    value_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(
            FluentIcon.PHOTO, 'Logo',
            '启用开关 + 绝对/相对定位 + 尺寸/边距/偏移',
            parent=parent,
        )
        # 模式相关控件
        self._abs_widget = None
        self._rel_widget = None
        self._setup_ui()

    def _setup_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(8)

        # 启用
        row0 = QHBoxLayout()
        row0.addWidget(BodyLabel('启用 Logo:', container))
        self.enabled_btn = SwitchButton(container)
        self.enabled_btn.checkedChanged.connect(
            self._on_enabled_changed)
        row0.addWidget(self.enabled_btn)
        row0.addStretch()
        layout.addLayout(row0)

        # 定位模式
        self._current_mode = 'absolute'
        self.mode_seg = SegmentedWidget(container)
        self.mode_seg.addItem('absolute', '绝对定位')
        self.mode_seg.addItem('relative', '相对定位')
        self.mode_seg.setCurrentItem('absolute')
        self.mode_seg.currentItemChanged.connect(
            self._on_mode_changed)
        layout.addWidget(self.mode_seg)

        # 通用参数行
        gen_grid = QGridLayout()
        gen_grid.setSpacing(6)

        gen_grid.addWidget(BodyLabel('size_ratio:', container), 0, 0)
        self.size_ratio_sb = DoubleSpinBox(container)
        self.size_ratio_sb.setRange(0.001, 0.2)
        self.size_ratio_sb.setDecimals(3)
        self.size_ratio_sb.setSingleStep(0.001)
        self.size_ratio_sb.setValue(0.04)
        self.size_ratio_sb.valueChanged.connect(self._on_changed)
        gen_grid.addWidget(self.size_ratio_sb, 0, 1)

        gen_grid.addWidget(BodyLabel('diagonal_limit:', container), 0, 2)
        self.diag_limit_sb = DoubleSpinBox(container)
        self.diag_limit_sb.setRange(1.0, 5.0)
        self.diag_limit_sb.setDecimals(1)
        self.diag_limit_sb.setSingleStep(0.1)
        self.diag_limit_sb.setValue(2.0)
        self.diag_limit_sb.valueChanged.connect(self._on_changed)
        gen_grid.addWidget(self.diag_limit_sb, 0, 3)

        gen_grid.addWidget(BodyLabel('alignment:', container), 1, 0)
        self.alignment_combo = ComboBox(container)
        self.alignment_combo.addItems(ALIGNMENT_OPTIONS)
        self.alignment_combo.setCurrentText('top-right')
        self.alignment_combo.currentTextChanged.connect(
            self._on_changed)
        gen_grid.addWidget(self.alignment_combo, 1, 1, 1, 3)

        layout.addLayout(gen_grid)

        # ── 绝对定位控件 ──
        self._abs_widget = QWidget(container)
        abs_grid = QGridLayout(self._abs_widget)
        abs_grid.setSpacing(6)
        r = 0

        abs_grid.addWidget(BodyLabel('placement:', container), r, 0)
        self.abs_placement = ComboBox(self._abs_widget)
        self.abs_placement.addItems(PLACEMENT_OPTIONS)
        self.abs_placement.currentTextChanged.connect(
            self._on_changed)
        abs_grid.addWidget(self.abs_placement, r, 1)
        abs_grid.addWidget(BodyLabel('position:', container), r, 2)
        self.abs_position = ComboBox(self._abs_widget)
        self.abs_position.addItems(ANCHOR_POSITION_OPTIONS)
        self.abs_position.setCurrentText('top-right')
        self.abs_position.currentTextChanged.connect(
            self._on_changed)
        abs_grid.addWidget(self.abs_position, r, 3)

        r += 1
        self.abs_mt = self._make_spinbox(
            'margin_top', abs_grid, r, 0, parent=container)
        self.abs_mb = self._make_spinbox(
            'margin_bottom', abs_grid, r, 2, parent=container)
        r += 1
        self.abs_ml = self._make_spinbox(
            'margin_left', abs_grid, r, 0, parent=container)
        self.abs_mr = self._make_spinbox(
            'margin_right', abs_grid, r, 2, parent=container)

        layout.addWidget(self._abs_widget)

        # ── 相对定位控件 ──
        self._rel_widget = QWidget(container)
        rel_grid = QGridLayout(self._rel_widget)
        rel_grid.setSpacing(6)
        r = 0

        rel_grid.addWidget(BodyLabel('relative_to:', container), r, 0)
        self.rel_to = ComboBox(self._rel_widget)
        self.rel_to.addItems(ELEMENT_KEYS)
        self.rel_to.currentTextChanged.connect(self._on_changed)
        rel_grid.addWidget(self.rel_to, r, 1)
        rel_grid.addWidget(BodyLabel('relative_position:', container), r, 2)
        self.rel_pos = ComboBox(self._rel_widget)
        self.rel_pos.addItems(RELATIVE_POSITION_OPTIONS)
        self.rel_pos.currentTextChanged.connect(self._on_changed)
        rel_grid.addWidget(self.rel_pos, r, 3)

        r += 1
        rel_grid.addWidget(BodyLabel('relative_margin:', container), r, 0)
        self.rel_margin_sb = DoubleSpinBox(self._rel_widget)
        self.rel_margin_sb.setRange(0.0, 1.0)
        self.rel_margin_sb.setDecimals(3)
        self.rel_margin_sb.setSingleStep(0.005)
        self.rel_margin_sb.setValue(0.01)
        self.rel_margin_sb.valueChanged.connect(self._on_changed)
        rel_grid.addWidget(self.rel_margin_sb, r, 1)

        r += 1
        rel_grid.addWidget(BodyLabel('offset_x:', container), r, 0)
        self.offset_x_sb = DoubleSpinBox(self._rel_widget)
        self.offset_x_sb.setRange(-1.0, 1.0)
        self.offset_x_sb.setDecimals(3)
        self.offset_x_sb.setSingleStep(0.001)
        self.offset_x_sb.valueChanged.connect(self._on_changed)
        rel_grid.addWidget(self.offset_x_sb, r, 1)
        rel_grid.addWidget(BodyLabel('offset_y:', container), r, 2)
        self.offset_y_sb = DoubleSpinBox(self._rel_widget)
        self.offset_y_sb.setRange(-1.0, 1.0)
        self.offset_y_sb.setDecimals(3)
        self.offset_y_sb.setSingleStep(0.001)
        self.offset_y_sb.valueChanged.connect(self._on_changed)
        rel_grid.addWidget(self.offset_y_sb, r, 3)

        layout.addWidget(self._rel_widget)
        self._rel_widget.hide()

        self.addGroupWidget(container)

    def _make_spinbox(self, label, grid, row, col, parent=None):
        if parent is None:
            parent = self
        grid.addWidget(BodyLabel(label, parent), row, col)
        sb = DoubleSpinBox(self._abs_widget)
        sb.setRange(0.0, 1.0)
        sb.setDecimals(3)
        sb.setSingleStep(0.005)
        sb.valueChanged.connect(self._on_changed)
        grid.addWidget(sb, row, col + 1)
        return sb

    def _on_enabled_changed(self, checked: bool):
        self.mode_seg.setEnabled(checked)
        if self._abs_widget:
            self._abs_widget.setEnabled(
                checked and self._current_mode == 'absolute')
        if self._rel_widget:
            self._rel_widget.setEnabled(
                checked and self._current_mode == 'relative')
        self._on_changed()

    def _on_mode_changed(self, mode: str):
        self._current_mode = mode
        is_absolute = mode == 'absolute'
        if self._abs_widget:
            self._abs_widget.setEnabled(self.enabled_btn.isChecked() and is_absolute)
        if self._rel_widget:
            self._rel_widget.setEnabled(self.enabled_btn.isChecked() and not is_absolute)
        self._on_changed()

    def _on_changed(self, *args):
        self.value_changed.emit()

    def load_from_model(self, data):
        self.enabled_btn.setChecked(data.logo_enabled)
        self.mode_seg.setCurrentItem(data.logo_mode)
        self.size_ratio_sb.setValue(data.logo_size_ratio)
        self.diag_limit_sb.setValue(data.logo_diagonal_limit)
        self.alignment_combo.setCurrentText(
            data.logo_alignment)
        if data.logo_mode == 'absolute':
            self.abs_placement.setCurrentText(
                data.logo_placement)
            self.abs_position.setCurrentText(
                data.logo_position)
            self.abs_mt.setValue(data.logo_mt)
            self.abs_mb.setValue(data.logo_mb)
            self.abs_ml.setValue(data.logo_ml)
            self.abs_mr.setValue(data.logo_mr)
        else:
            self.rel_to.setCurrentText(
                data.logo_relative_to)
            self.rel_pos.setCurrentText(
                data.logo_relative_position)
            self.rel_margin_sb.setValue(
                data.logo_relative_margin)
            self.offset_x_sb.setValue(data.logo_offset_x)
            self.offset_y_sb.setValue(data.logo_offset_y)

    def save_to_model(self, data):
        data.logo_enabled = self.enabled_btn.isChecked()
        data.logo_mode = self._current_mode
        data.logo_size_ratio = self.size_ratio_sb.value()
        data.logo_diagonal_limit = self.diag_limit_sb.value()
        data.logo_alignment = self.alignment_combo.currentText()
        if data.logo_mode == 'absolute':
            data.logo_placement = self.abs_placement.currentText()
            data.logo_position = self.abs_position.currentText()
            data.logo_mt = self.abs_mt.value()
            data.logo_mb = self.abs_mb.value()
            data.logo_ml = self.abs_ml.value()
            data.logo_mr = self.abs_mr.value()
        else:
            data.logo_relative_to = self.rel_to.currentText()
            data.logo_relative_position = \
                self.rel_pos.currentText()
            data.logo_relative_margin = self.rel_margin_sb.value()
            data.logo_offset_x = self.offset_x_sb.value()
            data.logo_offset_y = self.offset_y_sb.value()
