"""
自定义文本区块

启用开关 + 绝对/相对定位 + 行间距覆盖
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


class CustomTextSection(ExpandGroupSettingCard):
    """自定义文本配置区块"""

    value_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(
            FluentIcon.EDIT, '自定义文本 custom_text',
            '启用开关 + 绝对/相对定位 + 行间距覆盖',
            parent=parent,
        )
        self._setup_ui()

    def _setup_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(8)

        # 启用
        row0 = QHBoxLayout()
        row0.addWidget(BodyLabel('启用 (enabled):', container))
        self.enabled_btn = SwitchButton(container)
        self.enabled_btn.checkedChanged.connect(
            self._on_enabled_changed)
        row0.addWidget(self.enabled_btn)
        row0.addStretch()
        layout.addLayout(row0)

        # 高亮提示
        self.hint_label = BodyLabel(
            '用户内容由 GUI 文本框在运行时输入，此处仅配置定位参数', container)
        self.hint_label.setStyleSheet('color: #888;')
        layout.addWidget(self.hint_label)

        # 定位模式
        self._current_mode = 'absolute'
        self.mode_seg = SegmentedWidget(container)
        self.mode_seg.addItem('absolute', '绝对定位')
        self.mode_seg.addItem('relative', '相对定位')
        self.mode_seg.setCurrentItem('absolute')
        self.mode_seg.currentItemChanged.connect(
            self._on_mode_changed)
        layout.addWidget(self.mode_seg)

        # 通用参数
        gen_row = QHBoxLayout()
        gen_row.addWidget(BodyLabel('line_spacing_ratio:', container))
        self.line_spacing_sb = DoubleSpinBox(container)
        self.line_spacing_sb.setRange(0.0, 0.1)
        self.line_spacing_sb.setDecimals(3)
        self.line_spacing_sb.setSingleStep(0.001)
        self.line_spacing_sb.setValue(0.005)
        self.line_spacing_sb.valueChanged.connect(
            self._on_changed)
        gen_row.addWidget(self.line_spacing_sb)
        gen_row.addStretch()

        gen_row.addWidget(BodyLabel('alignment:', container))
        self.alignment_combo = ComboBox(container)
        self.alignment_combo.addItems(ALIGNMENT_OPTIONS)
        self.alignment_combo.setCurrentText('center')
        self.alignment_combo.currentTextChanged.connect(
            self._on_changed)
        gen_row.addWidget(self.alignment_combo)

        layout.addLayout(gen_row)

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
        self.abs_position.setCurrentText('bottom-center')
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
        for w in [self.mode_seg, self.hint_label,
                  self._abs_widget, self._rel_widget,
                  self.line_spacing_sb, self.alignment_combo]:
            w.setEnabled(checked)
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
        self.enabled_btn.setChecked(data.custom_text_enabled)
        self.mode_seg.setCurrentItem(data.custom_text_mode)
        self.line_spacing_sb.setValue(
            data.custom_text_line_spacing)
        self.alignment_combo.setCurrentText(
            data.custom_text_alignment)
        if data.custom_text_mode == 'absolute':
            self.abs_placement.setCurrentText(
                data.custom_text_placement)
            self.abs_position.setCurrentText(
                data.custom_text_position)
            self.abs_mt.setValue(data.custom_text_mt)
            self.abs_mb.setValue(data.custom_text_mb)
            self.abs_ml.setValue(data.custom_text_ml)
            self.abs_mr.setValue(data.custom_text_mr)
        else:
            self.rel_to.setCurrentText(
                data.custom_text_relative_to)
            self.rel_pos.setCurrentText(
                data.custom_text_relative_position)
            self.rel_margin_sb.setValue(
                data.custom_text_relative_margin)
            self.offset_x_sb.setValue(
                data.custom_text_offset_x)
            self.offset_y_sb.setValue(
                data.custom_text_offset_y)

    def save_to_model(self, data):
        data.custom_text_enabled = self.enabled_btn.isChecked()
        data.custom_text_mode = self._current_mode
        data.custom_text_alignment = \
            self.alignment_combo.currentText()
        data.custom_text_line_spacing = \
            self.line_spacing_sb.value()
        if data.custom_text_mode == 'absolute':
            data.custom_text_placement = \
                self.abs_placement.currentText()
            data.custom_text_position = \
                self.abs_position.currentText()
            data.custom_text_mt = self.abs_mt.value()
            data.custom_text_mb = self.abs_mb.value()
            data.custom_text_ml = self.abs_ml.value()
            data.custom_text_mr = self.abs_mr.value()
        else:
            data.custom_text_relative_to = \
                self.rel_to.currentText()
            data.custom_text_relative_position = \
                self.rel_pos.currentText()
            data.custom_text_relative_margin = \
                self.rel_margin_sb.value()
            data.custom_text_offset_x = \
                self.offset_x_sb.value()
            data.custom_text_offset_y = \
                self.offset_y_sb.value()
