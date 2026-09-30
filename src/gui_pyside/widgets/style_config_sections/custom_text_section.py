"""
自定义文本区块

启用开关 + 绝对/相对定位 + 行间距覆盖
"""
import logging

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
    HORIZONTAL_CROSS_OPTIONS, LINE_ALIGNMENT_OPTIONS,
    RELATIVE_POSITION_OPTIONS,
)
from ..positioning_binding import (
    PositionControls, load_positioned, save_positioned,
    sync_cross_options, apply_combo_options,
)
from ..spinbox_factory import make_spinbox

logger = logging.getLogger(__name__)


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

        # 多行文本块内部行对齐（与元素 alignment 完全分离，缺省 left）
        gen_row.addWidget(BodyLabel('line_alignment:', container))
        self.line_alignment_combo = ComboBox(container)
        self.line_alignment_combo.addItems(LINE_ALIGNMENT_OPTIONS)
        self.line_alignment_combo.setCurrentText('left')
        self.line_alignment_combo.currentTextChanged.connect(
            self._on_changed)
        gen_row.addWidget(self.line_alignment_combo)

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
        # 绝对定位 alignment：九点自对齐（默认 top-center：
        # 文字顶边贴照片下方外侧锚点，使文字位于照片下方）
        abs_grid.addWidget(BodyLabel('alignment:', container), r, 0)
        self.abs_alignment_combo = ComboBox(self._abs_widget)
        self.abs_alignment_combo.addItems(ALIGNMENT_OPTIONS)
        self.abs_alignment_combo.setCurrentText('top-center')
        self.abs_alignment_combo.currentTextChanged.connect(
            self._on_changed)
        abs_grid.addWidget(self.abs_alignment_combo, r, 1, 1, 3)

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
        self.rel_pos.currentTextChanged.connect(
            self._on_relative_position_changed)
        rel_grid.addWidget(self.rel_pos, r, 3)

        r += 1
        # 相对定位 cross_alignment：按方向切换三值，与绝对 alignment 分离
        rel_grid.addWidget(BodyLabel('cross_alignment:', container), r, 0)
        self.rel_cross_combo = ComboBox(self._rel_widget)
        self.rel_cross_combo.addItems(HORIZONTAL_CROSS_OPTIONS)
        self.rel_cross_combo.setCurrentText('left')
        self.rel_cross_combo.currentTextChanged.connect(
            self._on_changed)
        rel_grid.addWidget(self.rel_cross_combo, r, 1)

        r += 1
        rel_grid.addWidget(BodyLabel('relative_margin:', container), r, 0)
        self.rel_margin_sb = DoubleSpinBox(self._rel_widget)
        self.rel_margin_sb.setRange(0.0, 1.0)
        # margin/offset 类 decimals=4（G16：三位量化会改写 0.1605 类配置）
        self.rel_margin_sb.setDecimals(4)
        self.rel_margin_sb.setSingleStep(0.005)
        self.rel_margin_sb.setValue(0.01)
        self.rel_margin_sb.valueChanged.connect(self._on_changed)
        rel_grid.addWidget(self.rel_margin_sb, r, 1)

        r += 1
        rel_grid.addWidget(BodyLabel('offset_x:', container), r, 0)
        self.offset_x_sb = DoubleSpinBox(self._rel_widget)
        self.offset_x_sb.setRange(-1.0, 1.0)
        self.offset_x_sb.setDecimals(4)
        self.offset_x_sb.setSingleStep(0.001)
        self.offset_x_sb.valueChanged.connect(self._on_changed)
        rel_grid.addWidget(self.offset_x_sb, r, 1)
        rel_grid.addWidget(BodyLabel('offset_y:', container), r, 2)
        self.offset_y_sb = DoubleSpinBox(self._rel_widget)
        self.offset_y_sb.setRange(-1.0, 1.0)
        self.offset_y_sb.setDecimals(4)
        self.offset_y_sb.setSingleStep(0.001)
        self.offset_y_sb.valueChanged.connect(self._on_changed)
        rel_grid.addWidget(self.offset_y_sb, r, 3)

        layout.addWidget(self._rel_widget)
        # 初始禁用（非隐藏）恒占位（D1/G10 同根因修复：hide 之后
        # setEnabled 不会恢复可见，切到相对模式时参数组曾完全不可见）
        self._rel_widget.setEnabled(False)

        # G1 控件层：定位参数绑定束（本卡网格编排不变，仅收拢映射）
        self._controls = PositionControls(
            placement=self.abs_placement,
            position=self.abs_position,
            alignment=self.abs_alignment_combo,
            margin_top=self.abs_mt,
            margin_bottom=self.abs_mb,
            margin_left=self.abs_ml,
            margin_right=self.abs_mr,
            relative_to=self.rel_to,
            relative_position=self.rel_pos,
            cross_alignment=self.rel_cross_combo,
            relative_margin=self.rel_margin_sb,
            offset_x=self.offset_x_sb,
            offset_y=self.offset_y_sb,
        )

        self.addGroupWidget(container)

    def _make_spinbox(self, label, grid, row, col, parent=None):
        if parent is None:
            parent = self
        grid.addWidget(BodyLabel(label, parent), row, col)
        # G8：构造单点在 spinbox_factory（decimals=4，见 G16/决策 D7）
        sb = make_spinbox(self._abs_widget, on_changed=self._on_changed)
        grid.addWidget(sb, row, col + 1)
        return sb

    def _on_enabled_changed(self, checked: bool):
        for w in [self.mode_seg, self.hint_label,
                  self._abs_widget, self._rel_widget,
                  self.line_spacing_sb, self.line_alignment_combo]:
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

    def _on_relative_position_changed(self, direction: str):
        """relative_position 切换时同步 cross_alignment 合法值（共享实现）

        重置默认已按 G1 统一为模型序列化默认规则
        （left-of/right-of → center，above/below → left）。
        """
        sync_cross_options(self.rel_cross_combo, direction,
                           owner_label='CustomTextSection')
        self._on_changed()

    def _on_changed(self, *args):
        self.value_changed.emit()

    def _ensure_relative_to_option(self, value: str):
        """加载路径：模型引用值不在下拉选项中时先补进选项（G14）

        下拉默认只有固定键，模型引用可能是 defined_text 实例键；
        直接 setCurrentText 对缺失值静默失败，保存时会改写引用。
        """
        if value and self.rel_to.findText(value) < 0:
            logger.info(
                f"[CustomTextSection] relative_to 引用 {value!r} 不在当前"
                f"选项中，已补入选项（保存后由 StyleManager 校验）")
            self.rel_to.addItem(value)

    def update_relative_to_options(self, keys: list):
        """更新 relative_to 下拉选项（G14 接线，共享实现）"""
        apply_combo_options(self.rel_to, keys,
                            owner_label='CustomTextSection')

    def load_from_model(self, data):
        self.enabled_btn.setChecked(data.custom_text_enabled)
        self.mode_seg.setCurrentItem(data.custom_text_mode)
        self.line_spacing_sb.setValue(
            data.custom_text_line_spacing)
        spec = data.custom_text_spec
        # line_alignment 为本卡专属控件（文字专用字段，不进共享层），
        # 但与模式无关地加载（G15a：字段与定位模式无关）
        self.line_alignment_combo.setCurrentText(spec.line_alignment)
        # 相对引用的加载在两种模式下都补缺失选项（G14）：模型值可能是
        # defined_text 实例键，不在默认固定键选项中，直接 setCurrentText
        # 会静默失败导致保存时引用被改写
        if spec.relative_to:
            self._ensure_relative_to_option(spec.relative_to)
        # G1 统一：双分支全字段加载（与 ElementEditor 对齐）——非当前
        # 模式组禁用占位但控件值跟随模型，消除"切模式丢模型值"
        load_positioned(spec, self._controls, data.custom_text_mode)

    def save_to_model(self, data):
        data.custom_text_enabled = self.enabled_btn.isChecked()
        data.custom_text_mode = self._current_mode
        data.custom_text_line_spacing = \
            self.line_spacing_sb.value()
        # G1 控件层：定位字段映射单点在 save_positioned（全字段写回）
        save_positioned(data.custom_text_spec, self._controls,
                        self._current_mode)
        # line_alignment 为本卡专属控件，写回 spec（序列化按非默认规则）
        data.custom_text_spec.line_alignment = \
            self.line_alignment_combo.currentText()
