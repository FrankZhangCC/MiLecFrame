"""
MiLeica Frame - 核心处理模块初始化

此模块包含图像处理、渲染和HDR处理的核心功能。
"""
from .image_processor import ImageProcessor
from .renderer import FrameRenderer
from .hdr_handler import HDRHandler
from .decorator import Decorator
from .batch_processor import BatchProcessor

__version__ = "1.0.0"
__author__ = "MiLeica Frame Project"
__all__ = [
    'ImageProcessor',
    'FrameRenderer',
    'HDRHandler',
    'Decorator',
    'BatchProcessor'
]