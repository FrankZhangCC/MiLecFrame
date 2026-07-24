"""
MiLeica Frame - 相框样式模块初始化

此模块包含样式管理和配置功能。
"""
from .style_manager import StyleManager, default_style_manager

__version__ = "1.0.0"
__author__ = "MiLeica Frame Project"
__all__ = [
    'StyleManager',
    'default_style_manager'
]