# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
定位参数绑定层（G1 控件层收敛，T7）

ElementEditor / LogoSection / CustomTextSection 三个宿主各自重建的
"abs/rel 参数组 ↔ PositionedSpec" 映射、cross 合法值同步、
relative_to 选项管理，收敛为本模块的单点实现。

**宿主保留自己的网格编排**（列数、字段顺序、专属字段、视觉位置），
只按 PositionControls 协议提供控件引用；共享层不做任何布局操作。
专属字段（size_ratio / diagonal_limit / line_spacing / line_alignment /
tree_align）留在宿主，不进共享层。
"""
import logging

from qfluentwidgets import ComboBox, DoubleSpinBox

logger = logging.getLogger(__name__)


class PositionControls:
    """定位参数控件束（宿主 ↔ PositionedSpec 的绑定协议）

    宿主以关键字参数提供自己的控件引用；字段名与 PositionedSpec
    的定位字段一一对应。
    """

    def __init__(self, *,
                 placement: ComboBox,
                 position: ComboBox,
                 alignment: ComboBox,
                 margin_top: DoubleSpinBox,
                 margin_bottom: DoubleSpinBox,
                 margin_left: DoubleSpinBox,
                 margin_right: DoubleSpinBox,
                 relative_to: ComboBox,
                 relative_position: ComboBox,
                 cross_alignment: ComboBox,
                 relative_margin: DoubleSpinBox,
                 offset_x: DoubleSpinBox,
                 offset_y: DoubleSpinBox):
        self.placement = placement
        self.position = position
        self.alignment = alignment
        self.margin_top = margin_top
        self.margin_bottom = margin_bottom
        self.margin_left = margin_left
        self.margin_right = margin_right
        self.relative_to = relative_to
        self.relative_position = relative_position
        self.cross_alignment = cross_alignment
        self.relative_margin = relative_margin
        self.offset_x = offset_x
        self.offset_y = offset_y


def sync_cross_options(cross_combo: ComboBox, direction: str,
                       *, owner_label: str = '') -> None:
    """relative_position 切换时同步 cross_alignment 合法值（单点实现）

    above/below → left/center/right；left-of/right-of → top/center/bottom。
    当前值与新方向轴向不匹配时按模型序列化默认规则重置：
    left-of/right-of → center，above/below → left（G1 统一决策——
    Logo/自定义文本此前一律重置为 center 是历史漂移，统一为与
    PositionedSpec.update_from_entry 相同的默认规则）。
    """
    if direction in ('left-of', 'right-of'):
        legal = ('top', 'center', 'bottom')
        default = 'center'
    else:
        legal = ('left', 'center', 'right')
        default = 'left'
    current = cross_combo.currentText()
    cross_combo.blockSignals(True)
    cross_combo.clear()
    cross_combo.addItems(legal)
    if current in legal:
        cross_combo.setCurrentText(current)
    else:
        cross_combo.setCurrentText(default)
        logger.info(
            f"[{owner_label or 'PositionControls'}] relative_position "
            f"切换为 {direction!r}，cross_alignment 原值 {current!r} "
            f"不合法，已重置为 {cross_combo.currentText()!r}")
    cross_combo.blockSignals(False)


def load_positioned(spec, c: PositionControls, mode: str) -> None:
    """把 PositionedSpec 的定位字段加载到控件束（全字段、双分支）

    与模式无关地加载全部字段——非当前模式组处于禁用占位态（D1），
    但其控件值跟随模型，切模式后不会显示构造默认值（G1 统一：
    消除"切模式丢模型值"）。
    """
    c.placement.setCurrentText(spec.placement)
    c.position.setCurrentText(spec.position)
    c.alignment.setCurrentText(spec.absolute_alignment)
    c.margin_top.setValue(spec.margin_top)
    c.margin_bottom.setValue(spec.margin_bottom)
    c.margin_left.setValue(spec.margin_left)
    c.margin_right.setValue(spec.margin_right)
    c.relative_to.setCurrentText(spec.relative_to)
    # 先同步 cross 合法值集合再设当前值（不发信号）
    sync_cross_options(c.cross_alignment, spec.relative_position,
                       owner_label='load_positioned')
    c.cross_alignment.setCurrentText(spec.cross_alignment)
    c.relative_position.setCurrentText(spec.relative_position)
    c.relative_margin.setValue(spec.relative_margin)
    c.offset_x.setValue(spec.offset_x)
    c.offset_y.setValue(spec.offset_y)


def save_positioned(spec, c: PositionControls, mode: str) -> None:
    """把控件束当前值写回 PositionedSpec（全字段映射）

    alignment 双字段都按当前控件值写入（九点与交叉轴分属两个独立
    控件，序列化时由 PositionedSpec 按模式二选一，互不覆盖）。
    """
    spec.mode = mode
    spec.placement = c.placement.currentText()
    spec.position = c.position.currentText()
    spec.absolute_alignment = c.alignment.currentText()
    spec.cross_alignment = c.cross_alignment.currentText()
    spec.margin_top = c.margin_top.value()
    spec.margin_bottom = c.margin_bottom.value()
    spec.margin_left = c.margin_left.value()
    spec.margin_right = c.margin_right.value()
    spec.relative_to = c.relative_to.currentText()
    spec.relative_position = c.relative_position.currentText()
    spec.relative_margin = c.relative_margin.value()
    spec.offset_x = c.offset_x.value()
    spec.offset_y = c.offset_y.value()


def apply_combo_options(combo: ComboBox, keys: list, *,
                        owner_label: str) -> None:
    """刷新下拉选项并保留失效引用（G14 选项管理的单点实现）

    当前引用值不在新选项集合时保留原文本进选项并记日志——引用指向
    已删除条目等失效键不得被静默改写，由保存后 StyleManager 校验
    拒绝。全程屏蔽信号：选项刷新不是数据变更。
    """
    current = combo.currentText()
    options = list(keys)
    if current and current not in options:
        options.append(current)
        logger.info(
            f"[{owner_label}] relative_to 引用 {current!r} 不在可用键"
            f"列表，已保留原引用（保存后由 StyleManager 校验）")
    combo.blockSignals(True)
    combo.clear()
    combo.addItems(options)
    if current:
        combo.setCurrentText(current)
    combo.blockSignals(False)
