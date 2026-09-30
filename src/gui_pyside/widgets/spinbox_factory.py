# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
比例值 spinbox 工厂（G8 去样板：六处相同工厂单点化）

canvas/padding/corner_radius/logo/custom_text 各 section 与
ElementEditor 的 margin/offset 类 DoubleSpinBox 构造收敛于此；
网格布局由调用方自行安排（不因工厂相似强制统一不同网格）。

decimals 默认 4（G16/决策 D7：margin/offset 类比例值存在四位
小数，如 ParamCapsule margin_bottom 0.1605，三位量化会静默改写
用户配置）。
"""
from qfluentwidgets import DoubleSpinBox


def make_spinbox(parent, *, default: float = 0.0,
                 min_val: float = 0.0, max_val: float = 1.0,
                 step: float = 0.005, decimals: int = 4,
                 on_changed=None) -> DoubleSpinBox:
    """构造一个比例值 DoubleSpinBox

    Args:
        parent: 父控件
        default: 初始值
        min_val / max_val: 取值范围
        step: 单步增量（各宿主既有步进经参数保留）
        decimals: 小数位数（默认 4，见 G16/决策 D7）
        on_changed: valueChanged 回调（可选）

    Returns:
        配置完成的 DoubleSpinBox
    """
    sb = DoubleSpinBox(parent)
    sb.setRange(min_val, max_val)
    sb.setDecimals(decimals)
    sb.setSingleStep(step)
    sb.setValue(default)
    if on_changed is not None:
        sb.valueChanged.connect(on_changed)
    return sb
