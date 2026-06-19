# Copyright (c) 2026 FrankZhangCC
# MIT License - see LICENSE file for details

"""
MiLecFrame - 照片相框程序包初始化

此包包含用于为照片添加包含EXIF信息的相框的所有模块。
©FrankZhangCC 2026
使用 DeepSeek V4 系列模型开发。
"""
from ._version import __version__
from .core import *
from .gui import *
from .utils import *
from .frame_styles import *

__author__ = "FrankZhangCC"
__all__ = [
    'core',
    'gui', 
    'utils',
    'frame_styles',
    'main'
]