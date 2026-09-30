# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

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
    HORIZONTAL_CROSS_OPTIONS,
    VERTICAL_CROSS_OPTIONS,
    RELATIVE_POSITION_OPTIONS,
)
from .positioning_binding import (
    PositionControls, load_positioned, save_positioned,
    sync_cross_options, apply_combo_options,
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
    # 定位模式切换信号（G10/D2-③：宿主卡片借此在切换后刷新折叠卡高度）
    mode_changed = Signal()

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
        step: float = 0.005, decimals: int = 4,
        col: int = 0,
    ) -> DoubleSpinBox:
        """在网格布局中添加一行带标签的 DoubleSpinBox

        decimals 默认 4（G16 修复）：margin/offset 类比例值存在四位
        小数（如 ParamCapsule margin_bottom 0.1605），三位量化会静默
        改写用户配置。
        """
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
        # 绝对定位 alignment：九点自对齐（元素布局盒相对元素锚点）
        self.abs_alignment = ComboBox(self.abs_widget)
        self.abs_alignment.addItems(ALIGNMENT_OPTIONS)
        self.abs_alignment.setCurrentText('top-left')
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
            self._on_relative_position_changed)
        rel_grid.addWidget(
            BodyLabel("relative_position:", self.rel_widget), r, 0)
        rel_grid.addWidget(self.rel_relative_position, r, 1)

        r += 1
        # 相对定位 cross_alignment：按方向切换三值（above/below →
        # left/center/right；left-of/right-of → top/center/bottom），
        # 与绝对定位的九点 alignment 完全分离，避免隐藏控件覆盖保存值
        self.rel_cross_alignment = ComboBox(self.rel_widget)
        self.rel_cross_alignment.addItems(HORIZONTAL_CROSS_OPTIONS)
        self.rel_cross_alignment.setCurrentText('left')
        self.rel_cross_alignment.currentTextChanged.connect(
            self._on_changed)
        self.rel_cross_label = BodyLabel(
            "cross_alignment:", self.rel_widget)
        self.rel_cross_label.setToolTip(
            "交叉轴对齐：above/below 时为 left/center/right，\n"
            "left-of/right-of 时为 top/center/bottom；\n"
            "切换方向后不合法的值会自动重置为 center")
        rel_grid.addWidget(self.rel_cross_label, r, 0)
        rel_grid.addWidget(self.rel_cross_alignment, r, 1)

        r += 1
        self.rel_margin = DoubleSpinBox(self.rel_widget)
        self.rel_margin.setRange(0.0, 1.0)
        # margin/offset 类 decimals=4（G16：三位量化会改写 0.1605 类配置）
        self.rel_margin.setDecimals(4)
        self.rel_margin.setSingleStep(0.005)
        self.rel_margin.setValue(0.01)
        self.rel_margin.valueChanged.connect(self._on_changed)
        rel_grid.addWidget(
            BodyLabel("relative_margin:", self.rel_widget), r, 0)
        rel_grid.addWidget(self.rel_margin, r, 1)

        r += 1
        self.rel_offset_x = DoubleSpinBox(self.rel_widget)
        self.rel_offset_x.setRange(-1.0, 1.0)
        self.rel_offset_x.setDecimals(4)
        self.rel_offset_x.setSingleStep(0.001)
        self.rel_offset_x.setValue(0.0)
        self.rel_offset_x.valueChanged.connect(self._on_changed)
        rel_grid.addWidget(
            BodyLabel("offset_x:", self.rel_widget), r, 0)
        rel_grid.addWidget(self.rel_offset_x, r, 1)

        r += 1
        self.rel_offset_y = DoubleSpinBox(self.rel_widget)
        self.rel_offset_y.setRange(-1.0, 1.0)
        self.rel_offset_y.setDecimals(4)
        self.rel_offset_y.setSingleStep(0.001)
        self.rel_offset_y.setValue(0.0)
        self.rel_offset_y.valueChanged.connect(self._on_changed)
        rel_grid.addWidget(
            BodyLabel("offset_y:", self.rel_widget), r, 0)
        rel_grid.addWidget(self.rel_offset_y, r, 1)
        rel_grid.setColumnStretch(1, 1)

        # 默认显示绝对定位；相对组以禁用态恒占位（D1：setEnabled 而非
        # hide，模式切换不改变卡片内容高度），并且必须加入编辑器布局
        # （G10 修复：此前 rel_widget 从未 addWidget，不参与布局管理，
        # 几何停留在 QWidget 默认 100x30，相对字段被严重裁剪）
        self.rel_widget.setEnabled(False)
        layout.addWidget(self.rel_widget)

        # G1 控件层：定位参数绑定束（控件引用协议，见 positioning_binding）
        self._controls = PositionControls(
            placement=self.abs_placement,
            position=self.abs_position,
            alignment=self.abs_alignment,
            margin_top=self.abs_mt,
            margin_bottom=self.abs_mb,
            margin_left=self.abs_ml,
            margin_right=self.abs_mr,
            relative_to=self.rel_relative_to,
            relative_position=self.rel_relative_position,
            cross_alignment=self.rel_cross_alignment,
            relative_margin=self.rel_margin,
            offset_x=self.rel_offset_x,
            offset_y=self.rel_offset_y,
        )

    # ── 模式切换 ───────────────────────────────────────────

    def _on_mode_changed(self, mode: str):
        """定位模式切换"""
        self._current_mode = mode
        is_absolute = mode == 'absolute'
        # D1：非当前模式参数组禁用（灰显）而非隐藏——两组恒占位，
        # 模式切换不改变卡片内容高度
        self.abs_widget.setEnabled(is_absolute)
        self.rel_widget.setEnabled(not is_absolute)
        # tree_align 只属于绝对定位的树根节点，相对模式下禁用
        self.tree_align_btn.setEnabled(is_absolute)

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
        # 通知宿主卡片刷新折叠卡高度（G10/D2-③ 防御性刷新）
        self.mode_changed.emit()

    def _on_relative_position_changed(self, direction: str):
        """relative_position 切换时同步 cross_alignment 合法值（共享实现）

        above/below → left/center/right（默认 left）；
        left-of/right-of → top/center/bottom（默认 center）；
        不合法旧值按模型序列化默认规则重置。
        """
        sync_cross_options(self.rel_cross_alignment, direction,
                           owner_label='ElementEditor')
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

    # ── 数据读写（G1 控件层：映射单点在 positioning_binding） ──

    def _load_common(self, positioned):
        """定位参数加载的共用路径（load_element/load_defined_text 单对化）"""
        self.set_mode(positioned.mode)
        # 先补缺失选项再设值，保证模型引用（如 defined_text_01 实例键）
        # 必能被选中（G14：直接 setCurrentText 对缺失值静默失败）
        self._ensure_relative_to_option(positioned.relative_to)
        load_positioned(positioned, self._controls, positioned.mode)
        self.tree_align_btn.setChecked(positioned.tree_align)
        self.tree_align_btn.setEnabled(positioned.mode == 'absolute')

    def _save_common(self, target):
        """定位参数保存的共用路径（save_element/save_defined_text 单对化）"""
        save_positioned(target, self._controls, self._current_mode)
        target.tree_align = self.tree_align_btn.isChecked()

    def load_element(self, elem: ElementConfig):
        """从 ElementConfig 加载数据"""
        if self._show_key_selector:
            self.key_combo.setCurrentText(elem.key)
        self._load_common(elem)

    def save_element(self, target: ElementConfig):
        """保存数据到 ElementConfig 对象"""
        if self._show_key_selector:
            target.key = self.key_combo.currentText()
        self._save_common(target)

    def load_defined_text(self, item: DefinedTextConfig):
        """从 DefinedTextConfig 加载数据"""
        self._load_common(item)

    def save_defined_text(self, target: DefinedTextConfig):
        """保存数据到 DefinedTextConfig 对象"""
        self._save_common(target)

    # ── relative_to 选项管理（G14 修复：实例键引用保留） ──────

    def _ensure_relative_to_option(self, value: str):
        """加载路径：模型引用值不在下拉选项中时先补进选项再设值

        下拉默认只有固定键（ELEMENT_KEYS），不含 defined_text_01 等
        实例键；直接 setCurrentText 对缺失值静默失败（保持默认项），
        保存时会把改写后的引用写回模型。加载时先补选项保证模型中的
        引用值必能被选中；引用指向不存在键时保留原文本并记日志，
        由保存后 StyleManager 校验拒绝，不得静默改写。
        """
        if value and self.rel_relative_to.findText(value) < 0:
            logger.info(
                f"[ElementEditor] relative_to 引用 {value!r} 不在当前"
                f"选项中，已补入选项（保存后由 StyleManager 校验）")
            self.rel_relative_to.addItem(value)

    def update_relative_to_options(self, keys: list[str]):
        """更新 relative_to 下拉选项（G14 接线，共享实现）"""
        apply_combo_options(self.rel_relative_to, keys,
                            owner_label='ElementEditor')
