"""
MiLecFrame - 照片相框程序包初始化

此包包含用于为照片添加包含EXIF信息的相框的所有模块。
©Frank Zhang 2025
使用 DeepSeek V4 系列模型开发。
"""
from .core import *
from .gui import *
from .utils import *
from .frame_styles import *

__version__ = "1.6.2"
__author__ = "FrankZCC"
__all__ = [
    'core',
    'gui', 
    'utils',
    'frame_styles',
    'main'
]