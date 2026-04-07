"""
装饰元素处理模块
负责处理相框中的装饰元素，如边框、水印、徽标等
"""
import os
from PIL import Image, ImageDraw, ImageFont
from typing import Tuple, Dict, Optional, List
import numpy as np


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
        font_size: int = 20,
        color: Tuple[int, int, int] = (255, 255, 255)
    ) -> Image.Image:
        """
        为图像添加文字水印
        
        Args:
            image: 输入图像
            text: 水印文字
            position: 水印位置
            opacity: 透明度 (0-100)
            font_size: 字体大小
            color: 字体颜色
            
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
        
        # 计算文本位置
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # 根据位置参数计算实际位置
        x, y = self._calculate_position(
            image.size, 
            (text_width, text_height), 
            position
        )
        
        # 绘制水印文本
        draw.text((x, y), text, fill=(*color, int(255 * opacity / 100)), font=font)
        
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
        decorations: List[Dict]
    ) -> Image.Image:
        """
        应用多个装饰元素
        
        Args:
            image: 输入图像
            decorations: 装饰元素列表
            
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
                result_img = self.add_watermark(result_img, **params)
            elif decor_type == 'logo':
                result_img = self.add_logo(result_img, **params)
            elif decor_type == 'corner_mark':
                result_img = self.add_corner_mark(result_img, **params)
            else:
                print(f"未知的装饰类型: {decor_type}")
        
        return result_img