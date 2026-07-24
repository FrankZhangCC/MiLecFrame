"""
装饰元素处理模块
负责处理相框中的装饰元素，如水印等
"""
from typing import Tuple, Dict, Optional, List
from PIL import Image, ImageDraw, ImageFont


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
        layout_config: Optional[Dict] = None  # 布局配置，用于计算扩展画布偏移
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
            layout_config: 布局配置，用于计算扩展画布的偏移量
            
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
        
        # 获取当前图像与原始图像的尺寸差，用于调整边距计算
        # 如果有布局配置，使用FrameRenderer的计算方式
        if layout_config and original_image_size:
            # 获取扩展画布配置
            expand_config = layout_config.get('expand_canvas', {})
            if expand_config.get('enabled', False):
                # 计算扩展比例
                top_exp = expand_config.get('top', 0)
                left_exp = expand_config.get('left', 0)
                
                # 使用参照边作为计算基准，以保持一致的扩展效果
                orig_width, orig_height = original_image_size
                reference_side_orig = min(orig_width, orig_height)
                
                # 根据扩展比例计算位置
                top_offset = int(reference_side_orig * top_exp)
                left_offset = int(reference_side_orig * left_exp)
                
                offset_x = left_offset
                offset_y = top_offset
            else:
                # 如果没有启用扩展画布，图像在画布中央
                orig_width, orig_height = original_image_size
                offset_x = (img_width - orig_width) // 2
                offset_y = (img_height - orig_height) // 2
        elif original_image_size:
            # 如果没有布局配置但有原始图像尺寸，则假设图像在画布中央
            orig_width, orig_height = original_image_size
            offset_x = (img_width - orig_width) // 2
            offset_y = (img_height - orig_height) // 2
        else:
            # 如果没有原始图像尺寸，则认为当前图像就是原始图像
            offset_x = 0
            offset_y = 0
            # 为了后续计算不报错，设置一个默认值，虽然这种情况下通常不会进入下面的original_image_size分支
            orig_width, orig_height = img_width, img_height
        
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

        # 根据位置决定对齐方式
        if 'left' in position:
            align_x = x
        elif 'right' in position:
            align_x = x
        else:  # center
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
        original_image_size: Optional[Tuple[int, int]] = None,  # 新增参数
        layout_config: Optional[Dict] = None  # 新增参数：布局配置
    ) -> Image.Image:
        """
        应用多个装饰元素
        
        Args:
            image: 输入图像
            decorations: 装饰元素列表
            original_image_size: 原始图像尺寸，用于计算字体大小和margin
            layout_config: 布局配置，用于计算扩展画布的偏移量
            
        Returns:
            应用装饰后的图像
        """
        result_img = image.copy()
        
        for decoration in decorations:
            decor_type = decoration.get('type')
            params = decoration.get('params', {})
            
            if decor_type == 'watermark':
                result_img = self.add_watermark(
                    result_img, 
                    original_image_size=original_image_size, 
                    layout_config=layout_config,
                    **params
                )
            else:
                print(f"未知的装饰类型: {decor_type}")
        
        return result_img