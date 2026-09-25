# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
单个图片文件的数据模型

FileItem 是 GUI 中每个图片文件的核心数据结构，
包含文件信息、EXIF 数据、缩略图、处理状态和独立配置。
"""
from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtGui import QImage, QPixmap


def compute_cache_key(file_bytes: bytes) -> str:
    """对已在内存中的文件字节计算一次性内容摘要（sha256 前 16 hex）

    导入时调用一次并保存为 FileItem.cache_key，后续生成直接复用，
    作为二级模糊缓存的稳定 source_cache_key（禁止用临时路径或
    PIL 对象身份做跨帧键）。
    """
    from src.core.blur_cache import compute_source_cache_key
    return compute_source_cache_key(file_bytes)


@dataclass
class FileItem:
    """单个图片文件的数据模型

    Attributes:
        file_path: 原始文件路径
        file_name: 文件名（显示用）
        file_bytes: 原始文件字节（内存中保留，避免重复读盘）
        thumbnail: 缩略图（胶片栏显示用，高度固定 100px）
        result_thumbnail: 效果图缩略图（已处理时替换缩略图）
        exif_data: 提取的 EXIF 数据字典
        display_data: 格式化后的显示数据字典
        file_info: 文件元数据（格式/色彩空间/尺寸）
        is_processed: 是否已处理
        result_path: 输出文件路径
        width: 图片原始宽度
        height: 图片原始高度
    """
    file_path: str = ""
    file_name: str = ""
    file_bytes: Optional[bytes] = None
    thumbnail: Optional[QImage] = None
    result_thumbnail: Optional[QImage] = None
    exif_data: Optional[dict] = None
    display_data: Optional[dict] = None
    file_info: Optional[dict] = None
    is_processed: bool = False
    result_path: Optional[str] = None
    width: int = 0
    height: int = 0
    cached_pixmap: Optional[QPixmap] = None
    # 源图稳定摘要键（导入时对 file_bytes 一次性计算），
    # 用于二级模糊缓存跨生成复用；None=尚未计算
    cache_key: Optional[str] = None
