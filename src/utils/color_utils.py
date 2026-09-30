# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
颜色解析工具模块

渲染管线中颜色配置的唯一解析入口（审计 Q8）：此前 renderer 与
TextRenderer 各自实现 #RRGGBB / [R, G, B] 解析，失败与转换行为不同
（一个返回 None 并逐项 int()，一个抛 ValueError 且不转换序列项）。
统一后的策略：

- 空值 / 非法输入（非法十六进制、错误长度、不可转换的序列项、
  越界值不在此校验）一律返回 None，由调用方按各自语义回退
  （矩形跳过该层、文字回退默认配色）并记录告警；
- RGB 三元组序列逐项 int() 归一，浮点/数字字符串配置不再原样
  透传给 PIL。
"""
from typing import Optional, Tuple


def parse_color_value(value) -> Optional[Tuple[int, int, int]]:
    """
    解析颜色配置值，支持 #RRGGBB 字符串或 [R, G, B] 列表/元组。

    Returns:
        RGB 整数三元组；value 为空或解析失败时返回 None。
    """
    if not value:
        return None
    if isinstance(value, str):
        s = value.strip()
        if s.startswith('#'):
            # 与既有行为一致：不足 6 位的短串按切片静默部分解析
            #（如 '#fffff' → (255,255,15)），非法字符返回 None
            try:
                return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))
            except (ValueError, IndexError):
                return None
        return None
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            return tuple(int(c) for c in value)
        except (ValueError, TypeError):
            return None
    return None
