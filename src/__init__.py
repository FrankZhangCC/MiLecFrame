"""
MiLeica Frame - 照片相框程序包初始化

此包包含用于为照片添加包含EXIF信息的相框的所有模块。
"""
from .core import *
from .gui import *
from .utils import *
from .frame_styles import *

__version__ = "1.0.0"
__author__ = "MiLeica Frame Project"
__all__ = [
    'core',
    'gui', 
    'utils',
    'frame_styles',
    'main'
]