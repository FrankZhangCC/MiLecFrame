# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
图像显示转换 helper（G8 去样板）

pil_to_qimage 收敛原四处拷贝（预览 ×2、缩略图 ×1、样式预览 ×1）的
"PIL → QImage" 转换；filmstrip_thumb_size 收敛胶片栏缩略图尺寸的
三处相同计算。
"""
from PySide6.QtGui import QColorSpace, QImage


def pil_to_qimage(pil_image) -> QImage:
    """PIL Image → QImage（RGB888 + sRGB 标记 + 数据独立副本）

    语义保留（原四处拷贝一致）：非 RGB 模式先转换；bytes 缓冲构造
    QImage 后标记 sRGB 色彩空间；copy() 使像素数据独立于临时 bytes
    对象（QImage 不拥有该缓冲，直接返回会悬垂）。
    """
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    data = pil_image.tobytes()
    qimage = QImage(
        data, pil_image.width, pil_image.height,
        3 * pil_image.width, QImage.Format.Format_RGB888,
    )
    qimage.setColorSpace(QColorSpace.NamedColorSpace.SRgb)
    return qimage.copy()


def filmstrip_thumb_size(scroll_height: int) -> tuple[int, int]:
    """胶片栏缩略图尺寸（随可用高度动态缩放）

    原三处相同计算的收敛点：高度下限 60、上限 120、宽高比 1.25。

    Returns:
        (thumb_w, thumb_h) 二元组
    """
    available_height = max(60, scroll_height - 40)
    thumb_h = min(available_height, 120)
    thumb_w = int(thumb_h * 1.25)
    return thumb_w, thumb_h
