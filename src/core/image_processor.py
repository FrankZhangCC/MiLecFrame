"""
图像处理器模块
负责图像的基本处理、色彩空间转换、尺寸调整等
"""
import os
import io
import logging
from pathlib import Path
from typing import Tuple, Optional, Dict, List

from PIL import Image, ImageCms, ImageDraw, ImageFont
# 设置PIL最大图像像素限制，解决解压炸弹警告
Image.MAX_IMAGE_PIXELS = 200000000  # 2亿像素，可根据需要调整

import piexif

from src.utils.exif_helper import ExifHelper
from src.utils.device_mapper import DeviceMapper
from src.frame_styles.style_manager import StyleManager
from src.core.renderer import FrameRenderer
from src.core.hdr_handler import HDRHandler


class ImageProcessor:
    """图像处理器"""
    
    def __init__(self, style_config: Optional[str] = None):
        """
        初始化图像处理器
        
        Args:
            style_config: 相框样式配置
        """
        self.style_config = style_config
        self.supported_formats = ['JPEG', 'PNG', 'TIFF', 'MPO']
        self.hdr_supported_formats = ['HEIF', 'HEIC', 'AVIF']  # HDR相关格式
        self.max_input_size = (12000, 12000)  # 最大输入尺寸
        self.max_output_size = (8192, 8192)   # 最大输出尺寸
        
        # 初始化组件
        self.exif_helper = ExifHelper()
        self.renderer = FrameRenderer()
        self.style_manager = StyleManager()
        self.device_mapper = DeviceMapper()
        self.hdr_handler = HDRHandler()
        
        self.logger = logging.getLogger(__name__)
    
    def process(self, input_path: str, output_path: str, 
                author: Optional[str] = None, 
                location: Optional[str] = None,
                style_name: Optional[str] = None,
                bg_fill_type: str = "white",
                decorations: Optional[List[Dict]] = None,
                font_weight: Optional[str] = None,
                logo_filename: Optional[str] = None) -> bool:
        """
        处理图像并添加相框
        
        Args:
            input_path: 输入图像路径
            output_path: 输出图像路径
            author: 作者姓名
            location: 拍摄地点
            style_name: 样式名称
            bg_fill_type: 背景填充类型
            decorations: 装饰元素列表。每个元素是一个字典，包含 'type' 和 'params'。
                         例如水印: {'type': 'watermark', 'params': {'text': '...', 'position': '...', 'opacity': 0.5, 'color': '#FFFFFF'}}
            font_weight: 字体字重 (light, regular, medium)
            logo_filename: logo文件名
            
        Returns:
            是否处理成功
        """
        try:
            # 1. 验证输入文件
            if not os.path.exists(input_path):
                error_msg = f"错误: 输入文件不存在 - {input_path}"
                self.logger.error(error_msg)
                print(error_msg)
                return False
            
            # 2. 检查图像格式支持
            img_format = self._check_image_format(input_path)
            if not img_format:
                error_msg = f"错误: 不支持的图像格式 - {input_path}"
                self.logger.error(error_msg)
                print(error_msg)
                return False
            
            # 3. 根据图像类型读取图像
            if self.hdr_handler.is_hdr_format(input_path):
                # 如果是HDR图像，使用HDR处理器
                image = self.hdr_handler.process_hdr_image(input_path)
                if image is None:
                    error_msg = f"错误: 无法处理HDR图像 - {input_path}"
                    self.logger.error(error_msg)
                    print(error_msg)
                    return False
            else:
                # 普通图像直接用PIL打开
                image = Image.open(input_path)
            
            # 4. 检查EXIF信息
            exif_data = self.exif_helper.extract_exif_data(input_path)
            if not exif_data:
                warn_msg = f"警告: 未找到EXIF信息 - {input_path}"
                self.logger.warning(warn_msg)
                print(warn_msg)
            
            raw_exif = self.exif_helper.extract_raw_exif(input_path)
            
            # 获取格式化的EXIF数据用于显示（如果需要传递给renderer或后续处理）
            # 注意：如果renderer仍然需要原始exif_data，我们保留它。
            # 如果renderer更新为使用格式化后的文本，可以在这里准备。
            # 目前保持兼容，但展示了新helper的使用。
            formatted_exif = self.exif_helper.get_formatted_exif_for_display(exif_data) if exif_data else {}
            
            # 5. 验证图像尺寸
            if not self._validate_image_size(image.size):
                warn_msg = f"警告: 图像尺寸超出限制 - {image.size}"
                self.logger.warning(warn_msg)
                print(warn_msg)
                # 缩放图像
                image = self._resize_image_proportionally(image)
            
            # 6. 处理色彩空间
            image = self._convert_colorspace(image)
            sRGB_icc_bytes = image.info.get('icc_profile')
            
            # 7. 获取样式配置（传入上下文以便文件夹样式自动选择变体）
            if style_name:
                context = {'location': location, 'author': author}
                style_config = self.style_manager.get_style_config(style_name, context)
            else:
                style_config = self.style_manager.get_default_style()
            
            if not style_config:
                error_msg = f"错误: 无法获取样式配置 - {style_name or 'default'}"
                self.logger.error(error_msg)
                print(error_msg)
                return False
            
            # 8. 如果指定了字体字重，则更新样式配置
            if font_weight:
                # 设置字重
                style_config['fonts']['weight'] = font_weight

            # 9. 渲染图像
            rendered_image = self.renderer.render_frame(
                image=image,
                exif_data=exif_data,
                author=author,
                location=location,
                style_config=style_config,
                bg_fill_type=bg_fill_type,
                decorations=decorations,
                logo_filename=logo_filename
            )
            
            # 10. 保存图像
            self._save_image(rendered_image, output_path, img_format, raw_exif, sRGB_icc_bytes)
            
            success_msg = f"成功处理图像: {input_path} -> {output_path}"
            self.logger.info(success_msg)
            print(success_msg)
            return True
            
        except Exception as e:
            error_msg = f"处理图像时出错: {str(e)}"
            self.logger.error(error_msg)
            print(error_msg)
            # 记录详细错误信息
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def _check_image_format(self, image_path: str) -> Optional[str]:
        """
        检查图像格式是否支持
        
        Args:
            image_path: 图像路径
            
        Returns:
            图像格式，如果不支持则返回None
        """
        try:
            img_format = Image.open(image_path).format
            if img_format and (img_format in self.supported_formats or 
                              self.hdr_handler.is_hdr_format(image_path)):
                return img_format
            return None
        except Exception:
            return None
    
    def _validate_image_size(self, size: Tuple[int, int]) -> bool:
        """
        验证图像尺寸是否在支持范围内
        
        Args:
            size: 图像尺寸 (宽, 高)
            
        Returns:
            尺寸是否有效
        """
        width, height = size
        max_width, max_height = self.max_input_size
        return width <= max_width and height <= max_height
    
    def _resize_image_proportionally(self, image: Image.Image) -> Image.Image:
        """
        按比例缩放图像
        
        Args:
            image: 原始图像
            
        Returns:
            缩放后的图像
        """
        max_width, max_height = self.max_input_size
        width, height = image.size
        
        # 计算缩放比例
        scale_w = max_width / width
        scale_h = max_height / height
        scale = min(scale_w, scale_h)
        
        new_width = int(width * scale)
        new_height = int(height * scale)
        
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    def _convert_colorspace(self, image: Image.Image) -> Image.Image:
        """
        转换图像色彩空间到sRGB

        处理流程：
        1. ICC 色彩配置文件转换（Adobe RGB / ProPhoto RGB / Display P3 等 → sRGB）
        2. 像素模式转换（P/RGBA/LA/非RGB → RGB）

        Args:
            image: 原始图像

        Returns:
            转换后的 sRGB 图像
        """
        icc_profile = image.info.get('icc_profile')

        # 步骤1: ICC色彩空间转换（前置，在模式转换之前保留原始位深）
        if icc_profile:
            try:
                icc_stream = io.BytesIO(icc_profile)
                profile_desc = ImageCms.getProfileDescription(icc_stream)
                self.logger.info(f"检测到ICC色彩空间: {profile_desc}，转换为sRGB")
                icc_stream.seek(0)
                srgb_profile = ImageCms.createProfile('sRGB')
                image = ImageCms.profileToProfile(
                    image, icc_stream, srgb_profile,
                    outputMode='RGB',
                    renderingIntent=ImageCms.Intent.PERCEPTUAL
                )
                self.logger.info("ICC色彩空间转换成功")
            except Exception as e:
                self.logger.warning(f"ICC色彩空间转换失败，使用像素模式转换: {e}")

        # 步骤2: 像素模式转换（此时已在sRGB空间内）
        if image.mode in ('RGBA', 'LA', 'P'):
            if image.mode == 'P':
                image = image.convert('RGBA')
            if image.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'RGBA':
                    background.paste(image, mask=image.split()[-1])
                else:
                    background.paste(image, mask=image.split()[-1])
                image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')

        return image
    
    def _save_image(self, image: Image.Image, output_path: str, 
                    original_format: str, raw_exif: Optional[Dict] = None,
                    icc_profile_bytes: Optional[bytes] = None) -> None:
        """
        保存图像

        Args:
            image: 要保存的图像
            output_path: 输出路径
            original_format: 原始图像格式
            raw_exif: 原始EXIF字典（piexif格式），用于嵌入输出图
            icc_profile_bytes: sRGB ICC profile字节，用于嵌入输出图
        """
        try:
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)

            output_ext = os.path.splitext(output_path)[1].lower()
            if output_ext in ('.jpg', '.jpeg'):
                save_format = 'JPEG'
                save_kwargs = {'quality': 95, 'optimize': True}
            elif output_ext == '.png':
                save_format = 'PNG'
                save_kwargs = {'optimize': True}
            else:
                save_format = original_format
                save_kwargs = {}

            # 嵌入 sRGB ICC profile
            if icc_profile_bytes:
                save_kwargs['icc_profile'] = icc_profile_bytes

            if raw_exif:
                try:
                    exif_bytes = piexif.dump(raw_exif)
                    save_kwargs['exif'] = exif_bytes
                except Exception as e:
                    self.logger.warning(f"嵌入EXIF信息失败: {e}")

            image.save(output_path, format=save_format, **save_kwargs)
        except Exception as e:
            error_msg = f"保存图像时出错: {str(e)}"
            self.logger.error(error_msg)
            raise e