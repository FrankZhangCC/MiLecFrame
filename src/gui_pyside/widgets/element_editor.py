# Copyright (c) 2026 FrankZhangCC
# MIT License - see LICENSE file for details

"""
元素定位编辑器（可复用组件）

用于编辑单个元素（info_position 元素或预定义文本）的定位参数，
支持绝对定位和相对定位两种模式切换。
"""
import logging

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
)
from PySide6.QtCore import Qt, Signal

from qfluentwidgets import (
    ComboBox, LineEdit, SwitchButton, DoubleSpinBox,
    SegmentedWidget, StrongBodyLabel, BodyLabel,
    FluentIcon, ExpandSettingCard,
)

from ..models.style_config_form import (
    ElementConfig, DefinedTextConfig,
    ELEMENT_KEYS,
    PLACEMENT_OPTIONS,
    ANCHOR_POSITION_OPTIONS,
    ALIGNMENT_OPTIONS,
    RELATIVE_POSITION_OPTIONS,
)

logger = logging.getLogger(__name__)


class ElementEditor(QWidget):
    """元素定位编辑器

    编辑单个元素的定位参数，支持绝对/相对定位切换。
    发出 value_changed 信号供父容器监听。

    信号:
        changed(): 任一参数变更时发出
    """

    changed = Signal()

    def __init__(self, parent=None, show_key_selector: bool = True):
        """
        Args:
            parent: 父 widget
            show_key_selector: 是否显示元素类型选择器
                              （info_position 元素需要，预定义文本通过 key 字段独立编辑）
        """
        super().__init__(parent)
        self._show_key_selector = show_key_selector
        self._setup_ui()

    def _add_spinbox_row(
        self, label: str, layout: QGridLayout,
        row: int, *,
        min_val: float = 0.0, max_val: float = 1.0,
        step: float = 0.005, decimals: int = 3,
        col: int = 0,
    ) -> DoubleSpinBox:
        """在网格布局中添加一行带标签的 DoubleSpinBox"""
        lb = BodyLabel(label, self)
        sb = DoubleSpinBox(self)
        sb.setRange(min_val, max_val)
        sb.setDecimals(decimals)
        sb.setSingleStep(step)
        sb.setValue(0.0)
        sb.valueChanged.connect(self._on_changed)
        layout.addWidget(lb, row, col * 2)
        layout.addWidget(sb, row, col * 2 + 1)
        return sb

    def _setup_ui(self):
        """搭建 UI"""
        self._current_mode = 'absolute'  # 内部追踪模式字符串，避免 currentItem() 返回 SegmentedItem 对象
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ── 第1行：元素类型（可选） + 定位模式 ──
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        if self._show_key_selector:
            self.key_label = BodyLabel("元素类型:", self)
            self.key_combo = ComboBox(self)
            self.key_combo.addItems(ELEMENT_KEYS)
            self.key_combo.setCurrentText('exif')
            self.key_combo.currentTextChanged.connect(
                self._on_changed)
            row1.addWidget(self.key_label)
            row1.addWidget(self.key_combo, stretch=1)

        self.mode_seg = SegmentedWidget(self)
        self.mode_seg.addItem('absolute', '绝对定位')
        self.mode_seg.addItem('relative', '相对定位')
        self.mode_seg.setCurrentItem('absolute')
        self.mode_seg.currentItemChanged.connect(
            self._on_mode_changed)
        row1.addStretch()
        row1.addWidget(self.mode_seg)

        layout.addLayout(row1)

        # ── 绝对定位控件组 ──
        self.abs_widget = QWidget(self)
        abs_grid = QGridLayout(self.abs_widget)
        abs_grid.setSpacing(6)

        r = 0
        self.abs_placement = ComboBox(self.abs_widget)
        self.abs_placement.addItems(PLACEMENT_OPTIONS)
        self.abs_placement.currentTextChanged.connect(
            self._on_changed)
        abs_grid.addWidget(BodyLabel("placement:", self.abs_widget), r, 0)
        abs_grid.addWidget(self.abs_placement, r, 1)

        r += 1
        self.abs_position = ComboBox(self.abs_widget)
        self.abs_position.addItems(ANCHOR_POSITION_OPTIONS)
        self.abs_position.setCurrentText('bottom-left')
        self.abs_position.currentTextChanged.connect(
            self._on_changed)
        abs_grid.addWidget(BodyLabel("position:", self.abs_widget), r, 0)
        abs_grid.addWidget(self.abs_position, r, 1)

        r += 1
        self.abs_alignment = ComboBox(self.abs_widget)
        self.abs_alignment.addItems(ALIGNMENT_OPTIONS)
        self.abs_alignment.setCurrentText('left')
        self.abs_alignment.currentTextChanged.connect(
            self._on_changed)
        abs_grid.addWidget(
            BodyLabel("alignment:", self.abs_widget), r, 0)
        abs_grid.addWidget(self.abs_alignment, r, 1)

        r += 1
        self.abs_mt = self._add_spinbox_row(
            "margin_top", abs_grid, r, col=0)
        r += 1
        self.abs_mb = self._add_spinbox_row(
            "margin_bottom", abs_grid, r, col=0)
        r += 1
        self.abs_ml = self._add_spinbox_row(
            "margin_left", abs_grid, r, col=0)
        r += 1
        self.abs_mr = self._add_spinbox_row(
            "margin_right", abs_grid, r, col=0)

        # tree_align
        r += 1
        self.tree_align_btn = SwitchButton(self.abs_widget)
        self.tree_align_btn.checkedChanged.connect(
            self._on_changed)
        abs_grid.addWidget(
            BodyLabel("tree_align:", self.abs_widget), r, 0)
        abs_grid.addWidget(self.tree_align_btn, r, 1)
        abs_grid.setColumnStretch(1, 1)

        layout.addWidget(self.abs_widget)

        # ── 相对定位控件组 ──
        self.rel_widget = QWidget(self)
        rel_grid = QGridLayout(self.rel_widget)
        rel_grid.setSpacing(6)

        r = 0
        self.rel_relative_to = ComboBox(self.rel_widget)
        self.rel_relative_to.addItems(ELEMENT_KEYS)
        self.rel_relative_to.setCurrentText('exif')
        self.rel_relative_to.currentTextChanged.connect(
            self._on_changed)
        rel_grid.addWidget(
            BodyLabel("relative_to:", self.rel_widget), r, 0)
        rel_grid.addWidget(self.rel_relative_to, r, 1)

        r += 1
        self.rel_relative_position = ComboBox(self.rel_widget)
        self.rel_relative_position.addItems(
            RELATIVE_POSITION_OPTIONS)
        self.rel_relative_position.currentTextChanged.connect(
            self._on_changed)
        rel_grid.addWidget(
            BodyLabel("relative_position:", self.rel_widget), r, 0)
        rel_grid.addWidget(self.rel_relative_position, r, 1)

        r += 1
        self.rel_alignment = ComboBox(self.rel_widget)
        self.rel_alignment.addItems(ALIGNMENT_OPTIONS)
        self.rel_alignment.setCurrentText('left')
        self.rel_alignment.currentTextChanged.connect(
            self._on_changed)
        rel_grid.addWidget(
            BodyLabel("alignment:", self.rel_widget), r, 0)
        rel_grid.addWidget(self.rel_alignment, r, 1)

        r += 1
        self.rel_margin = DoubleSpinBox(self.rel_widget)
        self.rel_margin.setRange(0.0, 1.0)
        self.rel_margin.setDecimals(3)
        self.rel_margin.setSingleStep(0.005)
        self.rel_margin.setValue(0.01)
        self.rel_margin.valueChanged.connect(self._on_changed)
        rel_grid.addWidget(
            BodyLabel("relative_margin:", self.rel_widget), r, 0)
        rel_grid.addWidget(self.rel_margin, r, 1)

        r += 1
        self.rel_offset_x = DoubleSpinBox(self.rel_widget)
        self.rel_offset_x.setRange(-1.0, 1.0)
        self.rel_offset_x.setDecimals(3)
        self.rel_offset_x.setSingleStep(0.001)
        self.rel_offset_x.setValue(0.0)
        self.rel_offset_x.valueChanged.connect(self._on_changed)
        rel_grid.addWidget(
            BodyLabel("offset_x:", self.rel_widget), r, 0)
        rel_grid.addWidget(self.rel_offset_x, r, 1)

        r += 1
        self.rel_offset_y = DoubleSpinBox(self.rel_widget)
        self.rel_offset_y.setRange(-1.0, 1.0)
        self.rel_offset_y.setDecimals(3)
        self.rel_offset_y.setSingleStep(0.001)
        self.rel_offset_y.setValue(0.0)
        self.rel_offset_y.valueChanged.connect(self._on_changed)
        rel_grid.addWidget(
            BodyLabel("offset_y:", self.rel_widget), r, 0)
        rel_grid.addWidget(self.rel_offset_y, r, 1)
        rel_grid.setColumnStretch(1, 1)

        # 默认显示绝对定位
        self.rel_widget.hide()

    # ── 模式切换 ───────────────────────────────────────────

    def _on_mode_changed(self, mode: str):
        """定位模式切换"""
        self._current_mode = mode
        is_absolute = mode == 'absolute'
        self.abs_widget.setVisible(is_absolute)
        self.rel_widget.setVisible(not is_absolute)

        # 切换到相对定位时，避免自引用（relative_to == 元素自身 key）
        if not is_absolute and self._show_key_selector:
            own_key = self.key_combo.currentText()
            if self.rel_relative_to.currentText() == own_key:
                # 自引用会导致渲染死循环，切换到第一个不同 key
                for i in range(self.rel_relative_to.count()):
                    if self.rel_relative_to.itemText(i) != own_key:
                        self.rel_relative_to.setCurrentIndex(i)
                        break

        self._on_changed()

    def _on_changed(self, *args):
        """值变更信号转发"""
        self.changed.emit()

    # ── 数据读写 ───────────────────────────────────────────

    def get_mode(self) -> str:
        """获取当前定位模式"""
        return self._current_mode

    def set_mode(self, mode: str):
        """设置定位模式"""
        if mode in ('absolute', 'relative'):
            self._current_mode = mode
            self.mode_seg.setCurrentItem(mode)

    def load_element(self, elem: ElementConfig):
        """从 ElementConfig 加载数据"""
        if self._show_key_selector:
            self.key_combo.setCurrentText(elem.key)
        self.set_mode(elem.mode)
        self.abs_placement.setCurrentText(elem.placement)
        self.abs_position.setCurrentText(elem.position)
        self.abs_alignment.setCurrentText(elem.alignment)
        self.abs_mt.setValue(elem.margin_top)
        self.abs_mb.setValue(elem.margin_bottom)
        self.abs_ml.setValue(elem.margin_left)
        self.abs_mr.setValue(elem.margin_right)
        self.tree_align_btn.setChecked(elem.tree_align)
        self.rel_relative_to.setCurrentText(elem.relative_to)
        self.rel_relative_position.setCurrentText(
            elem.relative_position)
        self.rel_alignment.setCurrentText(elem.alignment)
        self.rel_margin.setValue(elem.relative_margin)
        self.rel_offset_x.setValue(elem.offset_x)
        self.rel_offset_y.setValue(elem.offset_y)

    def save_element(self, target: ElementConfig):
        """保存数据到 ElementConfig 对象"""
        if self._show_key_selector:
            target.key = self.key_combo.currentText()
        target.mode = self._current_mode
        target.placement = self.abs_placement.currentText()
        target.position = self.abs_position.currentText()
        target.alignment = self.abs_alignment.currentText()
        target.margin_top = self.abs_mt.value()
        target.margin_bottom = self.abs_mb.value()
        target.margin_left = self.abs_ml.value()
        target.margin_right = self.abs_mr.value()
        target.tree_align = self.tree_align_btn.isChecked()
        target.relative_to = self.rel_relative_to.currentText()
        target.relative_position = \
            self.rel_relative_position.currentText()
        target.relative_margin = self.rel_margin.value()
        target.offset_x = self.rel_offset_x.value()
        target.offset_y = self.rel_offset_y.value()

    def load_defined_text(self, item: DefinedTextConfig):
        """从 DefinedTextConfig 加载数据"""
        self.set_mode(item.mode)
        self.abs_placement.setCurrentText(item.placement)
        self.abs_position.setCurrentText(item.position)
        self.abs_alignment.setCurrentText(item.alignment)
        self.abs_mt.setValue(item.margin_top)
        self.abs_mb.setValue(item.margin_bottom)
        self.abs_ml.setValue(item.margin_left)
        self.abs_mr.setValue(item.margin_right)
        self.tree_align_btn.setChecked(item.tree_align)
        self.rel_relative_to.setCurrentText(item.relative_to)
        self.rel_relative_position.setCurrentText(
            item.relative_position)
        self.rel_alignment.setCurrentText(item.alignment)
        self.rel_margin.setValue(item.relative_margin)
        self.rel_offset_x.setValue(item.offset_x)
        self.rel_offset_y.setValue(item.offset_y)

    def save_defined_text(self, target: DefinedTextConfig):
        """保存数据到 DefinedTextConfig 对象"""
        target.mode = self._current_mode
        target.placement = self.abs_placement.currentText()
        target.position = self.abs_position.currentText()
        target.alignment = self.abs_alignment.currentText()
        target.margin_top = self.abs_mt.value()
        target.margin_bottom = self.abs_mb.value()
        target.margin_left = self.abs_ml.value()
        target.margin_right = self.abs_mr.value()
        target.tree_align = self.tree_align_btn.isChecked()
        target.relative_to = self.rel_relative_to.currentText()
        target.relative_position = \
            self.rel_relative_position.currentText()
        target.relative_margin = self.rel_margin.value()
        target.offset_x = self.rel_offset_x.value()
        target.offset_y = self.rel_offset_y.value()

    def update_relative_to_options(self, keys: list[str]):
        """更新 relative_to 下拉选项"""
        current = self.rel_relative_to.currentText()
        self.rel_relative_to.clear()
        self.rel_relative_to.addItems(keys)
        if current in keys:
            self.rel_relative_to.setCurrentText(current)
