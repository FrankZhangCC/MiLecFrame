# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
装饰元素处理模块
负责处理相框中的装饰元素，如水印等
"""
import logging
from typing import Tuple, Dict, Optional, List
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class Decorator:
    """装饰元素处理器"""
    
    def __init__(self, font_manager=None):
        """初始化装饰处理器
        
        Args:
            font_manager: FontManager实例，用于统一字体加载
        """
        self.font_manager = font_manager

    def add_watermark(
        self,
        image: Image.Image,
        text: str,
        position: str = 'bottom-right',
        opacity: int = 50,
        color: Tuple[int, int, int] = (255, 255, 255),
        original_image_size: Optional[Tuple[int, int]] = None,  # 原始图像尺寸
        original_bounds: Optional[Tuple[int, int, int, int]] = None
    # 原图在画布上的 bounds (x, y, w, h)，与 LayoutEngine 共享同一几何
    ) -> Image.Image:
        """
        为图像添加文字水印

        Args:
            image: 输入图像
            text: 水印文字
            position: 水印位置
            opacity: 透明度 (0-100)
            color: 字体颜色
            original_image_size: 原始图像尺寸，用于计算字体大小和margin
            original_bounds: 原图在画布上的偏移与尺寸（审计 Q14-13：与
                LayoutEngine.original_bounds 共享同一几何，水印定位不再
                根据 layout_config 重新推算偏移；水印定位保持独立于文字
                定位，不套用 padding）

        Returns:
            添加水印后的图像
        """
        # 确保图像是RGBA模式以支持透明度
        if image.mode != 'RGBA':
            base_img = image.convert('RGBA')
        else:
            base_img = image.copy()
        
        # 创建透明图层用于绘制水印
        txt_layer = Image.new('RGBA', base_img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_layer)
        
        # 使用原始图像的参照边作为计算基准
        if original_image_size:
            reference_side = min(original_image_size)
        else:
            reference_side = min(image.size)
        
        # 使用FontManager统一加载字体（水印文字高度为参照边的2%）
        img_size_for_font = original_image_size if original_image_size else image.size
        if self.font_manager:
            font = self.font_manager.load_font(
                fonts_config={'weight': 'medium', 'family': 'Gotham', 'size_ratio': 0.02},
                original_image_size=img_size_for_font,
                text_content=text
            )
        else:
            font = ImageFont.load_default()

        # 计算文本边界框
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # 根据位置参数计算实际位置，使用参照边的2%作为边距
        margin = int(reference_side * 0.02)

        img_width, img_height = image.size

        # 原图在画布上的偏移直接取共享几何（审计 Q14-13）；
        # 未提供 bounds 时视为画布与原图重合（offset 0）
        if original_bounds:
            offset_x, offset_y = original_bounds[0], original_bounds[1]
        else:
            offset_x, offset_y = 0, 0
        
        # 支持的位置: top-left, top-center, top-right, bottom-left, bottom-center, bottom-right
        # 所有位置都相对于原始图像边缘计算，保持一致的margin
        # 注意：这里需要确保 original_image_size 存在才能使用其宽高进行相对定位
        if original_image_size:
            orig_w, orig_h = original_image_size
        else:
            orig_w, orig_h = img_width, img_height

        if position == 'top-left':
            x = offset_x + margin  # 从原始图像左边起始加上margin
            y = offset_y + margin  # 从原始图像顶边起始加上margin
        elif position == 'top-center':
            x = offset_x + (orig_w - text_width) // 2  # 在原始图像宽度中心
            y = offset_y + margin  # 从原始图像顶边起始加上margin
        elif position == 'top-right':
            x = offset_x + orig_w - text_width - margin  # 从原始图像右边减去宽度和margin
            y = offset_y + margin  # 从原始图像顶边起始加上margin
        elif position == 'bottom-left':
            x = offset_x + margin  # 从原始图像左边起始加上margin
            y = offset_y + orig_h - text_height - margin  # 从原始图像底边减去高度和margin
        elif position == 'bottom-center':
            x = offset_x + (orig_w - text_width) // 2  # 在原始图像宽度中心
            y = offset_y + orig_h - text_height - margin  # 从原始图像底边减去高度和margin
        elif position == 'bottom-right':
            x = offset_x + orig_w - text_width - margin  # 从原始图像右边减去宽度和margin
            y = offset_y + orig_h - text_height - margin  # 从原始图像底边减去高度和margin
        else:
            # 默认为右下角
            x = offset_x + orig_w - text_width - margin  # 从原始图像右边减去宽度和margin
            y = offset_y + orig_h - text_height - margin  # 从原始图像底边减去高度和margin

        # 水印 x 坐标在三个分支下取值相同（审计 Q14-6：原 if/elif 三分支
        # 均为 align_x = x，属重复决策，直接使用绘制坐标）
        align_x = x

        # 绘制水印文本
        draw.text((align_x, y), text, fill=(*color, int(255 * opacity / 100)), font=font)
        
        # 合并图层
        watermarked_img = Image.alpha_composite(base_img, txt_layer)

        background = Image.new('RGB', watermarked_img.size, (255, 255, 255))
        background.paste(watermarked_img, mask=watermarked_img.split()[-1])
        return background

    def apply_decorations(
        self,
        image: Image.Image,
        decorations: List[Dict],
        original_bounds: Optional[Tuple[int, int, int, int]] = None
    # 原图在画布上的 bounds，与 LayoutEngine 共享同一几何
    ) -> Image.Image:
        """
        应用多个装饰元素

        Args:
            image: 输入图像
            decorations: 装饰元素列表
            original_bounds: 原图在画布上的偏移与尺寸，水印定位直接消费，
                不再根据 layout_config 重算偏移
        """
        result_img = image.copy()

        for decoration in decorations:
            decor_type = decoration.get('type')
            params = decoration.get('params', {})

            if decor_type == 'watermark':
                result_img = self.add_watermark(
                    result_img,
                    original_bounds=original_bounds,
                    **params
                )
            else:
                # 未知装饰类型：告警并跳过（审计 Q14-13：print 改 logger）
                logger.warning("未知的装饰类型: %s，已跳过", decor_type)

        return result_img