# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
MiLeica Frame - 相框样式模块初始化

此模块包含样式管理和配置功能。
"""
from .style_manager import StyleManager, default_style_manager

__all__ = [
    'StyleManager',
    'default_style_manager'
]