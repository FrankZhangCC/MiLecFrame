# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
处理配置模型

ProcessingConfig 封装了图像处理所需的所有配置参数，
从 GUI 控件收集后传递给 ImageProcessor。
"""
from dataclasses import dataclass, field
from typing import Optional, Tuple

from src.utils.background_fill import BackgroundFillManager


@dataclass
class ProcessingConfig:
    """处理配置模型

    每个 FileItem 可以拥有独立的 ProcessingConfig，
    实现"多文件各自设置配置"的功能。
    """
    # ── 输出设置 ──
    output_format: str = "JPEG"

    # ── 相框配置 ──
    style_name: str = "底部信息条 Bottom Bars"
    bg_fill_type: str = BackgroundFillManager.DEFAULT_FILL
    font_weight: str = "medium"
    enhance_background: bool = True

    # ── 个性化配置 ──
    author: str = ""
    location: str = ""
    use_gps_location: bool = False
    custom_text: Optional[str] = None

    # ── 拍摄信息配置 ──
    lens_display_mode: str = "combined"  # "combined" / "camera_only" / "lens_only"
    use_short_lens: bool = False
    logo_selection: str = "auto"  # "auto" / "none" / 具体文件名

    # ── 文本水印 ──
    watermark_enabled: bool = False
    watermark_text: str = ""
    watermark_position: str = "bottom-right"
    watermark_opacity: int = 50
    watermark_color: Tuple[int, int, int] = (255, 255, 255)
