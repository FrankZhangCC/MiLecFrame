"""
装饰元素处理模块
负责处理相框中的装饰元素，如边框、水印、徽标等
"""
import os
import re
from typing import Tuple, Dict, Optional, List
from PIL import Image, ImageDraw, ImageFont, ImageFilter


class Decorator:
    """装饰元素处理器"""
    
    def __init__(self):
        """初始化装饰处理器"""
        self.available_decorations = [
            'border',      # 边框
            'watermark',   # 水印
            'logo',        # 徽标
            'corner_mark', # 角标
        ]

    def add_border(
        self, 
        image: Image.Image, 
        width: int = 5, 
        color: Tuple[int, int, int] = (255, 255, 255)
    ) -> Image.Image:
        """
        为图像添加边框
        
        Args:
            image: 输入图像
            width: 边框宽度
            color: 边框颜色
            
        Returns:
            添加边框后的图像
        """
        # 创建新图像，尺寸稍大以容纳边框
        new_width = image.width + 2 * width
        new_height = image.height + 2 * width
        
        # 创建带边框的背景
        bordered_img = Image.new('RGB', (new_width, new_height), color=color)
        
        # 将原图粘贴到中心位置
        bordered_img.paste(image, (width, width))
        
        return bordered_img

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
        
        # 根据文本内容选择合适的字体
        contains_chinese = bool(re.search(r'[\u4e00-\u9fff]', text))  # 检查是否包含中文字符
        
        # 使用原始图像的长边作为计算基准，字体高度为长边的2%
        # 如果没有提供原始图像尺寸，则使用当前图像尺寸
        if original_image_size:
            longer_side = max(original_image_size)
        else:
            longer_side = max(image.size)
        
        # 根据项目规范，水印文字高度为原图长边的2%
        font_size = max(12, int(longer_side * 0.02))
        
        # 构建字体路径列表 - 使用相对于当前文件的路径
        base_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'assets', 'fonts')

        # 根据文本内容判断使用哪种字体
        if contains_chinese:
            # 包含中文，优先使用中文字体
            font_candidates = [
                'GlowSansSC-Normal-Medium.otf',  # 中文字体
                'HeitiSC-Medium.otf',
                'Arial Unicode.ttf',
                'DejaVuSans.ttf'
            ]
        else:
            # 不包含中文，优先使用西文字体
            font_candidates = [
                'Gotham-Medium.otf',  # 西文字体
                'Futura-Medium.ttf',
                'Arial.ttf',
                'DejaVuSans.ttf'
            ]

        font_paths = [os.path.join(base_path, font) for font in font_candidates]
        
        # 按优先级尝试加载字体
        font = None
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    font = ImageFont.truetype(font_path, size=font_size)
                    break
                except Exception as e:
                    print(f"加载字体失败 {font_path}: {e}")
                    continue
        
        if font is None:
            print("警告: 所有字体加载失败，使用默认字体")
            font = ImageFont.load_default()

        # 计算文本边界框
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # 根据位置参数计算实际位置，使用原始图像长边的2%作为边距
        margin = int(longer_side * 0.02)  # 使用原始图像长边的2%作为边距
        
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
                
                # 使用长边作为计算基准，以保持一致的扩展效果
                orig_width, orig_height = original_image_size
                longer_side_orig = max(orig_width, orig_height)
                
                # 根据扩展比例计算位置
                top_offset = int(longer_side_orig * top_exp)
                left_offset = int(longer_side_orig * left_exp)
                
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
        
        return watermarked_img.convert('RGB')

    def add_logo(
        self, 
        image: Image.Image, 
        logo_path: str, 
        position: str = 'top-left',
        size_ratio: float = 0.1,
        opacity: int = 100
    ) -> Image.Image:
        """
        为图像添加Logo
        
        Args:
            image: 输入图像
            logo_path: Logo文件路径
            position: Logo位置
            size_ratio: Logo相对于图像的比例
            opacity: 透明度 (0-100)
            
        Returns:
            添加Logo后的图像
        """
        if not os.path.exists(logo_path):
            print(f"Logo文件不存在: {logo_path}")
            return image
        
        # 加载Logo
        try:
            logo = Image.open(logo_path).convert('RGBA')
        except Exception as e:
            print(f"加载Logo失败: {str(e)}")
            return image
        
        # 计算Logo新尺寸
        max_logo_size = min(image.width, image.height) * size_ratio
        logo_width, logo_height = logo.size
        
        # 保持Logo的宽高比
        scale_factor = min(max_logo_size / logo_width, max_logo_size / logo_height)
        new_logo_width = int(logo_width * scale_factor)
        new_logo_height = int(logo_height * scale_factor)
        
        # 调整Logo大小
        logo = logo.resize((new_logo_width, new_logo_height), Image.Resampling.LANCZOS)
        
        # 如果指定了透明度，调整Logo的alpha通道
        if opacity < 100:
            alpha = logo.split()[-1]  # 获取alpha通道
            alpha = alpha.point(lambda p: int(p * opacity / 100))  # 调整透明度
            logo.putalpha(alpha)
        
        # 确保底图是RGBA模式
        if image.mode != 'RGBA':
            base_img = image.convert('RGBA')
        else:
            base_img = image.copy()
        
        # 计算Logo位置
        pos_x, pos_y = self._calculate_position(
            image.size, 
            (new_logo_width, new_logo_height), 
            position
        )
        
        # 将Logo粘贴到底图上
        base_img.paste(logo, (pos_x, pos_y), logo)
        
        return base_img.convert('RGB')
    
    def add_corner_mark(
        self, 
        image: Image.Image, 
        mark_text: str, 
        corner: str = 'top-left',
        font_size: int = 16,
        color: Tuple[int, int, int] = (255, 255, 255),
        padding: int = 10
    ) -> Image.Image:
        """
        为图像添加角落标记
        
        Args:
            image: 输入图像
            mark_text: 标记文本
            corner: 角落位置
            font_size: 字体大小
            color: 字体颜色
            padding: 内边距
            
        Returns:
            添加角落标记后的图像
        """
        # 确保图像是RGBA模式以支持透明度
        if image.mode != 'RGBA':
            base_img = image.convert('RGBA')
        else:
            base_img = image.copy()
        
        # 创建透明图层用于绘制角落标记
        mark_layer = Image.new('RGBA', base_img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(mark_layer)
        
        # 尝试加载字体
        try:
            # 优先使用中文字体
            font_dir = os.path.join(os.path.dirname(__file__), '..', 'assets', 'fonts')
            font_paths = [
                os.path.join(font_dir, 'Futura-Medium.ttf'),
                os.path.join(font_dir, 'HeitiSC-Medium.ttf'),
                os.path.join(font_dir, 'Arial Unicode.ttf'),
                os.path.join(font_dir, 'DejaVuSans.ttf')
            ]
            
            font = None
            for font_path in font_paths:
                if os.path.exists(font_path):
                    font = ImageFont.truetype(font_path, size=font_size)
                    break
            
            if font is None:
                font = ImageFont.load_default()
        except Exception as e:
            print(f"加载字体失败: {str(e)}, 使用默认字体")
            font = ImageFont.load_default()
        
        # 计算文本边界框
        bbox = draw.textbbox((0, 0), mark_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # 根据角落位置计算实际位置
        img_width, img_height = image.size
        
        if corner == 'top-left':
            x, y = padding, padding
        elif corner == 'top-right':
            x, y = img_width - text_width - padding, padding
        elif corner == 'bottom-left':
            x, y = padding, img_height - text_height - padding
        elif corner == 'bottom-right':
            x, y = img_width - text_width - padding, img_height - text_height - padding
        else:
            # 默认为左上角
            x, y = padding, padding
        
        # 绘制角落标记文本
        draw.text((x, y), mark_text, fill=color, font=font)
        
        # 合并图层
        marked_img = Image.alpha_composite(base_img, mark_layer)
        
        return marked_img.convert('RGB')
    
    def _calculate_position(
        self, 
        img_size: Tuple[int, int], 
        elem_size: Tuple[int, int], 
        position: str
    ) -> Tuple[int, int]:
        """
        计算元素的位置
        
        Args:
            img_size: 图像尺寸
            elem_size: 元素尺寸
            position: 位置描述
            
        Returns:
            (x, y) 坐标
        """
        img_width, img_height = img_size
        elem_width, elem_height = elem_size
        
        # 根据位置参数计算坐标
        if position == 'center':
            x = (img_width - elem_width) // 2
            y = (img_height - elem_height) // 2
        elif position == 'top-left':
            x = 10
            y = 10
        elif position == 'top-right':
            x = img_width - elem_width - 10
            y = 10
        elif position == 'bottom-left':
            x = 10
            y = img_height - elem_height - 10
        elif position == 'bottom-right':
            x = img_width - elem_width - 10
            y = img_height - elem_height - 10
        else:
            # 默认居中
            x = (img_width - elem_width) // 2
            y = (img_height - elem_height) // 2
        
        return x, y
    
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
            
            if decor_type == 'border':
                result_img = self.add_border(result_img, **params)
            elif decor_type == 'watermark':
                # 为水印功能添加原始图像尺寸和布局配置参数
                result_img = self.add_watermark(
                    result_img, 
                    original_image_size=original_image_size, 
                    layout_config=layout_config,
                    **params
                )
            elif decor_type == 'logo':
                result_img = self.add_logo(result_img, **params)
            elif decor_type == 'corner_mark':
                result_img = self.add_corner_mark(result_img, **params)
            else:
                print(f"未知的装饰类型: {decor_type}")
        
        return result_img