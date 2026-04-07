"""
图像渲染引擎模块
负责相框的图层合成、背景填充、高斯模糊等功能
"""
import os
import sys
import re
from pathlib import Path

# 添加项目根目录到sys.path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from typing import Tuple, Dict, Optional, List
import numpy as np
# 修改导入路径，使用绝对导入
from src.utils.exif_helper import ExifHelper
from src.core.decorator import Decorator


class FrameRenderer:
    """相框渲染器"""
    
    def __init__(self):
        """初始化渲染器"""
        # 预定义的颜色选项
        self.color_options = {
            "black": (0, 0, 0),
            "white": (255, 255, 255),
            "gray": (128, 128, 128)
        }
        
        # 初始化装饰器
        self.decorator = Decorator()
    
    def render_frame(
        self, 
        image: Image.Image, 
        exif_data: Optional[Dict], 
        author: Optional[str], 
        location: Optional[str],
        style_config: Dict,
        bg_fill_type: str = "white",
        decorations: Optional[List[Dict]] = None
    ) -> Image.Image:
        """
        渲染带相框的图像
        
        Args:
            image: 原始图像
            exif_data: EXIF数据
            author: 作者名
            location: 拍摄地点
            style_config: 样式配置
            bg_fill_type: 背景填充类型
            decorations: 装饰元素列表
            
        Returns:
            渲染后的图像
        """
        # 获取样式配置
        layout = style_config.get('layout', {})
        colors = style_config.get('colors', {})
        fonts = style_config.get('fonts', {})
        bg_fill_config = style_config.get('background_fill', {})
        
        # 保存当前布局配置、原始图像尺寸和背景类型到实例属性
        self._current_layout = layout
        self._original_image_size = image.size
        self._bg_fill_type = bg_fill_type
        
        # 计算最终画布尺寸（考虑扩展画布）
        canvas_width, canvas_height = self._calculate_canvas_size_with_expansion(
            image.size, layout
        )
        
        # 创建背景层（包含扩展区域的填充）
        background = self._create_background_with_expansion(
            image, canvas_width, canvas_height, bg_fill_type, bg_fill_config
        )
        
        # 将原图放置到背景上的正确位置
        positioned_image = self._position_original_image(background, image, layout)
        
        # 添加装饰元素（如果有的话）
        if decorations:
            decorated_image = self.decorator.apply_decorations(positioned_image, decorations)
        else:
            decorated_image = positioned_image
        
        # 添加文字和图标层
        final_image = self._add_text_and_icons_flexible(
            decorated_image, exif_data, author, location, layout, colors, fonts
        )
        
        return final_image
    
    def _calculate_canvas_size_with_expansion(
        self, 
        image_size: Tuple[int, int], 
        layout: Dict
    ) -> Tuple[int, int]:
        """
        计算画布尺寸（考虑扩展画布）
        
        Args:
            image_size: 原始图像尺寸
            layout: 布局配置
            
        Returns:
            画布尺寸 (width, height)
        """
        width, height = image_size
        
        # 获取扩展画布配置
        expand_config = layout.get('expand_canvas', {})
        if not expand_config.get('enabled', False):
            return width, height
        
        # 获取扩展比例
        top_exp = expand_config.get('top', 0)
        bottom_exp = expand_config.get('bottom', 0)
        left_exp = expand_config.get('left', 0)
        right_exp = expand_config.get('right', 0)
        
        # 计算长边（用于统一比例计算）
        longer_side = max(width, height)
        
        # 计算扩展后的尺寸
        new_width = width + int(longer_side * (left_exp + right_exp))
        new_height = height + int(longer_side * (top_exp + bottom_exp))
        
        return new_width, new_height
    
    def _create_background_with_expansion(
        self, 
        image: Image.Image, 
        canvas_width: int, 
        canvas_height: int, 
        bg_fill_type: str,
        bg_fill_config: Dict
    ) -> Image.Image:
        """
        创建背景层（包含扩展区域的填充）
        
        Args:
            image: 原始图像
            canvas_width: 画布宽度
            canvas_height: 画布高度
            bg_fill_type: 背景填充类型
            bg_fill_config: 背景填充配置
            
        Returns:
            背景图像
        """
        if bg_fill_type == "pure_black":
            return Image.new('RGB', (canvas_width, canvas_height), color='black')
        elif bg_fill_type == "pure_white":
            return Image.new('RGB', (canvas_width, canvas_height), color='white')
        elif bg_fill_type == "gaussian_black_65":
            return self._apply_gaussian_blur_overlay_expansion(
                image, canvas_width, canvas_height, 'black', 
                65  # 65%透明度
            )
        elif bg_fill_type == "gaussian_white_65":
            return self._apply_gaussian_blur_overlay_expansion(
                image, canvas_width, canvas_height, 'white', 
                65  # 65%透明度
            )
        elif bg_fill_type == "gaussian_black_35":
            return self._apply_gaussian_blur_overlay_expansion(
                image, canvas_width, canvas_height, 'black', 
                35  # 35%透明度
            )
        elif bg_fill_type == "gaussian_white_35":
            return self._apply_gaussian_blur_overlay_expansion(
                image, canvas_width, canvas_height, 'white', 
                35  # 35%透明度
            )
        else:
            # 默认使用白色背景
            return Image.new('RGB', (canvas_width, canvas_height), color='white')
    
    def _apply_gaussian_blur_overlay_expansion(
        self, 
        image: Image.Image, 
        canvas_width: int, 
        canvas_height: int, 
        overlay_color: str, 
        opacity: int
    ) -> Image.Image:
        """
        应用高斯模糊叠加效果（适用于扩展画布）
        
        Args:
            image: 原始图像
            canvas_width: 画布宽度
            canvas_height: 画布高度
            overlay_color: 叠加颜色
            opacity: 透明度百分比
            
        Returns:
            应用效果后的背景图像
        """
        # 创建一个与原图相同大小的副本用于模糊处理
        blur_img = image.copy()
        
        # 计算缩放因子，用于优化大图处理性能
        original_width, original_height = blur_img.size
        target_size = min(canvas_width, canvas_height)
        
        # 如果目标尺寸很大，先缩小图像进行模糊处理以提高性能
        scale_factor = min(1.0, 2000.0 / max(target_size, 2000))
        scaled_width = max(int(original_width * scale_factor), 512)  # 限制最小尺寸
        scaled_height = max(int(original_height * scale_factor), 512)
        
        if scale_factor < 1.0:
            # 缩小图像进行模糊处理
            blur_img = blur_img.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
        
        # 应用高斯模糊
        blur_radius = 200 * scale_factor  # 按比例调整模糊半径
        blur_img = blur_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        
        # 调整模糊图像大小以适应整个画布
        blur_img = blur_img.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)
        
        # 创建颜色叠加层
        overlay = Image.new('RGBA', (canvas_width, canvas_height), 
                           color=(*self.color_options.get(overlay_color, (255, 255, 255)), int(255 * opacity / 100)))
        
        # 将模糊图像转换为RGBA模式
        if blur_img.mode != 'RGBA':
            blur_img = blur_img.convert('RGBA')
        
        # 将颜色叠加层应用到模糊图像上
        result = Image.alpha_composite(blur_img, overlay)
        
        # 转回RGB模式
        result = result.convert('RGB')
        
        # 应用抖动算法以减少色彩断层
        result = self._apply_dithering(result)
        
        return result
    
    def _apply_dithering(self, image: Image.Image) -> Image.Image:
        """
        应用抖动算法以减少色彩断层
        
        Args:
            image: 输入图像
            
        Returns:
            应用抖动后的图像
        """
        # 将PIL图像转换为numpy数组以进行像素操作
        img_array = np.array(image, dtype=np.float64)
        
        # 获取图像尺寸
        height, width, channels = img_array.shape
        
        # 为性能优化，只对较大图像应用抖动
        if height * width > 2000000:  # 如果超过2百万像素，跳过抖动处理
            return image
        
        # 遍历每个像素应用抖动算法（Floyd-Steinberg抖动算法）
        for y in range(height - 1):  # 减1是为了避免越界
            for x in range(width - 1):  # 减1是为了避免越界
                # 获取当前像素值
                old_pixel = img_array[y, x].copy()
                
                # 四舍五入到0-255范围内的整数
                new_pixel = np.round(np.clip(old_pixel, 0, 255))
                
                # 将新像素值设置回去
                img_array[y, x] = new_pixel
                
                # 计算量化误差
                quant_error = old_pixel - new_pixel
                
                # 将误差扩散到相邻像素
                # 右侧像素 (7/16)
                img_array[y, x + 1] += quant_error * (7 / 16)
                
                # 下方像素 (5/16)
                img_array[y + 1, x] += quant_error * (5 / 16)
                
                # 下左像素 (3/16)
                if x > 0:
                    img_array[y + 1, x - 1] += quant_error * (3 / 16)
                
                # 下右像素 (1/16)
                img_array[y + 1, x + 1] += quant_error * (1 / 16)
        
        # 确保所有值都在有效范围内
        img_array = np.clip(img_array, 0, 255)
        
        # 转换回uint8类型
        img_array = img_array.astype(np.uint8)
        
        # 转换回PIL图像
        return Image.fromarray(img_array, mode='RGB')
    
    def _position_original_image(
        self, 
        background: Image.Image, 
        image: Image.Image, 
        layout: Dict
    ) -> Image.Image:
        """
        将原图放置到背景上的正确位置
        
        Args:
            background: 背景图像
            image: 原始图像
            layout: 布局配置
            
        Returns:
            放置图像后的图像
        """
        # 创建新图像以确保模式一致
        result = background.copy()
        
        # 计算原图在扩展画布中的位置
        bg_width, bg_height = result.size
        img_width, img_height = image.size
        
        # 获取扩展画布配置
        expand_config = layout.get('expand_canvas', {})
        if not expand_config.get('enabled', False):
            # 如果没有启用扩展画布，居中放置
            x = (bg_width - img_width) // 2
            y = (bg_height - img_height) // 2
        else:
            # 计算扩展比例
            top_exp = expand_config.get('top', 0)
            left_exp = expand_config.get('left', 0)
            
            # 使用长边作为计算基准，以保持一致的扩展效果
            longer_side = max(img_width, img_height)
            
            # 根据扩展比例计算位置
            top_offset = int(longer_side * top_exp)
            left_offset = int(longer_side * left_exp)
            
            x = left_offset
            y = top_offset
        
        # 将原图粘贴到背景上
        if image.mode == 'RGBA':
            result.paste(image, (x, y), image)
        else:
            result.paste(image, (x, y))
        
        return result
    
    def _load_font_responsive_with_longer_side(self, fonts: Dict, original_image_size: Tuple[int, int], specific_size_ratio: float = None, text_content: str = "") -> ImageFont.FreeTypeFont:
        """
        加载响应式字体，使用原始图像的长边作为计算基准

        Args:
            fonts: 字体配置
            original_image_size: 原始图像尺寸
            specific_size_ratio: 特定的字体大小比例（可选）
            text_content: 文本内容，用于判断使用哪种字体

        Returns:
            字体对象
        """
        # 优先使用配置中的字体名称和字重
        font_weight = fonts.get('weight', 'medium')  # 默认为中等字重
        font_base_name = fonts.get('family', 'Gotham')  # 默认字体系列
    
        # 根据字重选择对应的字体名称
        font_weight_mapping = {
            'light': {
                'regular': f'{font_base_name}-Light',
                'chinese': 'GlowSansSC-Normal-Light.otf' if font_base_name == 'Gotham' else f'GlowSansSC-{font_base_name}-Light.otf'
            },
            'medium': {
                'regular': f'{font_base_name}-Medium',
                'chinese': 'GlowSansSC-Normal-Medium.otf' if font_base_name == 'Gotham' else f'GlowSansSC-{font_base_name}-Medium.otf'
            },
            'regular': {
                'regular': f'{font_base_name}-Book',  # Gotham Regular 映射到 Gotham-Book
                'chinese': 'GlowSansSC-Normal-Regular.otf' if font_base_name == 'Gotham' else f'GlowSansSC-{font_base_name}-Regular.otf'
            }
        }
    
        # 获取当前字重的字体名称
        weight_config = font_weight_mapping.get(font_weight, font_weight_mapping['medium'])
        font_name = weight_config['regular']

        # 使用特定的字体大小比例，否则使用通用的
        size_ratio = specific_size_ratio if specific_size_ratio is not None else fonts.get('size_ratio', 0.015)

        # 根据项目规范，使用原始图像的长边作为计算基准
        longer_side = max(original_image_size)
        font_size = max(12, int(longer_side * size_ratio))

        print(f"使用长边基准字体大小计算: 比例={size_ratio}, 长边={longer_side}, 最终字体大小={font_size}")
        print(f"字重: {font_weight}, 字体名称: {font_name}")

        # 构建字体路径列表 - 使用相对于当前文件的路径
        base_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'assets', 'fonts')

        # 根据文本内容判断使用哪种字体
        contains_chinese = bool(re.search(r'[\u4e00-\u9fff]', text_content))  # 检查是否包含中文字符
        if contains_chinese:
            # 包含中文，优先使用中文字体
            font_candidates = [
                weight_config['chinese'],  # 根据字重选择的中文字体
                font_name + '.otf',
                font_name + '.ttf',
            ]
        else:
            # 不包含中文，优先使用西文字体
            font_candidates = [
                font_name + '.otf',  # 根据字重选择的西文字体
                font_name + '.ttf',
            ]

        font_paths = [os.path.join(base_path, font) for font in font_candidates]

        # 按优先级尝试加载字体
        for font_path in font_paths:
            print(f"尝试加载字体: {font_path}")  # 调试信息
            if os.path.exists(font_path):
                try:
                    print(f"字体文件存在，尝试加载: {font_path}")
                    font = ImageFont.truetype(font_path, size=font_size)
                    
                    # 检查字体类型，确保不是bitmap字体
                    if hasattr(font, 'getmetrics'):
                        print(f"成功加载 FreeType 字体: {font_path}，大小: {font_size}px")
                        
                        # 验证字体大小是否正确
                        test_text = "Test"
                        bbox = font.getbbox(test_text)
                        actual_height = bbox[3] - bbox[1]
                        print(f"字体测试 - 请求大小: {font_size}px, 实际渲染高度: {actual_height}px")
                        
                        # 如果实际渲染高度远小于请求大小，则可能存在字体问题
                        if actual_height < font_size * 0.3:  # 如果实际高度小于请求大小的30%
                            print(f"警告：字体高度异常小，可能加载了低分辨率字体")
                            continue
                        
                        return font
                    else:
                        print(f"加载的可能是bitmap字体，跳过: {font_path}")
                        continue
                except OSError as e:
                    print(f"加载字体失败 (OSError) {font_path}: {e}")
                    continue
                except Exception as e:
                    print(f"加载字体失败 (Exception) {font_path}: {e}")
                    continue
            else:
                print(f"字体文件不存在: {font_path}")

        print("警告：所有字体加载失败，使用默认字体")
        # 如果找不到字体文件，使用默认字体
        return ImageFont.load_default()

    def _add_text_and_icons_flexible(
        self, 
        image: Image.Image, 
        exif_data: Optional[Dict], 
        author: Optional[str], 
        location: Optional[str],
        layout: Dict,
        colors: Dict,
        fonts: Dict
    ) -> Image.Image:
        """
        添加更灵活定位的文字和图标层
        
        Args:
            image: 输入图像
            exif_data: EXIF数据
            author: 作者名
            location: 地点
            layout: 布局配置
            colors: 颜色配置
            fonts: 字体配置
            
        Returns:
            添加文字和图标的图像
        """
        result = image.copy()
        draw = ImageDraw.Draw(result)
        
        # 输出调试信息
        print(f"开始添加文字图层...")
        print(f"EXIF数据: {exif_data}")
        print(f"作者: {author}")
        print(f"地点: {location}")
        print(f"图像尺寸: {image.size}")
        print(f"原始图像尺寸: {getattr(self, '_original_image_size', 'N/A')}")
        
        # 获取原始图像尺寸
        original_image_size = getattr(self, '_original_image_size', image.size)
        
        # 使用ExifHelper获取用于显示的数据
        display_data = ExifHelper().get_display_data(exif_data) if exif_data else {}
        
        # 准备要显示的文本
        text_elements = []
        
        # EXIF信息（格式化的曝光参数）
        if 'exif_formatted' in display_data and display_data['exif_formatted']:
            exif_text = display_data['exif_formatted']
            print(f"格式化后的EXIF文本: '{exif_text}'")
            text_elements.append(('exif', exif_text))
        
        # 拍摄时间信息
        if exif_data and 'datetime_original' in exif_data:
            timestamp_text = f"{exif_data['datetime_original']}"
            print(f"拍摄时间文本: '{timestamp_text}'")
            text_elements.append(('timestamp', timestamp_text))
        
        # 相机型号信息 - 使用映射后的值，并包含品牌
        if 'camera_combined' in display_data:
            camera_text = display_data['camera_combined']
            print(f"相机型号文本: '{camera_text}'")
            text_elements.append(('camera', camera_text))
        
        # 镜头型号信息 - 使用映射后的值
        if 'lens_model' in display_data:
            lens_text = display_data['lens_model']
            print(f"镜头型号文本: '{lens_text}'")
            text_elements.append(('lens', lens_text))
        
        # 作者信息
        if author:
            author_text = f"{author}"
            print(f"作者文本: '{author_text}'")
            text_elements.append(('author', author_text))
        
        # 地点信息
        if location:
            location_text = f"{location}"
            print(f"地点文本: '{location_text}'")
            text_elements.append(('location', location_text))
        
        # 如果没有任何文本信息，则跳过
        if not text_elements:
            print("没有需要显示的文本信息")  # 调试信息
            return result
        
        print(f"待渲染的文本元素: {text_elements}")
        
        # 根据布局配置确定每个文本元素的位置
        info_positions = layout.get('info_position', {})
        
        for text_type, text in text_elements:
            # 获取特定文本类型的配置
            text_config = info_positions.get(text_type, {})
            position = text_config.get('position', 'outside')  # 默认在外部
            alignment = text_config.get('alignment', 'center')  # 默认居中
            
            # 获取传统margin值（如果存在的话，用于向后兼容）
            margin = text_config.get('margin', 10)  # 默认边距
            
            print(f"处理文本类型: {text_type}, 位置: {position}, 对齐: {alignment}, 边距: {margin}")
            
            # 获取特定信息的字体大小配置，如果没有则使用通用配置
            font_size_config = fonts.get('sizes', {})
            text_specific_size_ratio = font_size_config.get(text_type, fonts.get('size_ratio', 0.02))
            
            print(f"字体大小比例: {text_specific_size_ratio}")
            
            # 使用原始图像长边作为基准加载字体，传递文本内容以智能选择字体
            font = self._load_font_responsive_with_longer_side(fonts, original_image_size, text_specific_size_ratio, text)
            
            # 根据背景类型自动选择文字颜色
            bg_fill_type = getattr(self, '_bg_fill_type', 'pure_white')  # 默认为纯白色背景
            # 检查背景是否为深色系列，以便使用浅色文字
            if bg_fill_type.startswith('pure_black') or bg_fill_type.startswith('gaussian_black'):
                # 黑色背景使用白色文字
                text_color = (255, 255, 255)  # 白色
            else:
                # 白色背景使用黑色文字
                text_color = (0, 0, 0)  # 黑色
            
            print(f"背景类型: {bg_fill_type}, 文本颜色: {text_color}")
            
            # 计算文本位置
            x, y = self._calculate_text_position(
                image, text, text_config, font, position, alignment, margin
            )
            
            print(f"绘制文本: '{text}', 类型: {text_type}, 位置: ({x}, {y})")  # 调试信息
            
            # 检查文本是否在画布范围内
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            canvas_width, canvas_height = image.size
            print(f"画布尺寸: {canvas_width}x{canvas_height}, 文本框尺寸: {text_width}x{text_height}")
            print(f"文本位置检查 - X: {x} (范围: 0~{canvas_width-text_width}), Y: {y} (范围: 0~{canvas_height-text_height})")
            
            # 确保文本在画布范围内
            if x < 0 or x + text_width > canvas_width or y < 0 or y + text_height > canvas_height:
                print(f"警告: 文本位置超出画布范围!")
            else:
                print(f"文本位置在画布范围内")
            
            # 绘制文本
            draw.text((x, y), text, fill=text_color, font=font)
        
        print("文字图层添加完成")
        return result

    def _calculate_text_position(
        self, 
        image: Image.Image, 
        text: str, 
        text_config: Dict, 
        font: ImageFont.FreeTypeFont, 
        position: str, 
        alignment: str, 
        margin: int
    ) -> Tuple[int, int]:
        """
        计算文本位置
        
        Args:
            image: 原始图像
            text: 要绘制的文本
            text_config: 文本配置
            font: 字体对象
            position: 位置 ('inside', 'outside', 'top', 'bottom', 'left', 'right', 'tl', 'tr', 'bl', 'br')
            alignment: 对齐方式 ('left', 'center', 'right')
            margin: 边距
        
        Returns:
            (x, y) 文本绘制坐标
        """
        # 获取文本边界框
        bbox = font.getbbox(text)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # 获取当前画布尺寸（扩展后的）
        canvas_width, canvas_height = image.size
        
        # 获取当前布局配置
        layout = getattr(self, '_current_layout', {})
        expand_config = layout.get('expand_canvas', {})
        
        # 如果启用扩展画布，计算原始图像的位置
        if expand_config.get('enabled', False):
            # 获取扩展比例
            top_exp = expand_config.get('top', 0)
            left_exp = expand_config.get('left', 0)
            
            # 使用与 _position_original_image 方法相同的逻辑
            # 需要知道原始图像的尺寸才能正确计算
            original_image_size = getattr(self, '_original_image_size', None)
            
            if original_image_size:
                img_width, img_height = original_image_size
                # 使用长边作为计算基准
                longer_side = max(img_width, img_height)
                
                # 根据扩展比例计算原始图像在扩展画布中的位置
                top_offset = int(longer_side * top_exp)
                left_offset = int(longer_side * left_exp)
                
                orig_img_x = left_offset
                orig_img_y = top_offset
                orig_img_width = img_width
                orig_img_height = img_height
            else:
                # 如果没有原始图像尺寸，使用备用方法
                top_exp = expand_config.get('top', 0)
                left_exp = expand_config.get('left', 0)
                
                # 使用画布的长边估算原始图像尺寸
                longer_side = max(canvas_width, canvas_height)
                
                # 计算扩展总量
                total_top_exp = expand_config.get('top', 0)
                total_bottom_exp = expand_config.get('bottom', 0)
                total_left_exp = expand_config.get('left', 0)
                total_right_exp = expand_config.get('right', 0)
                
                # 计算原始图像尺寸
                orig_img_width = canvas_width - int(longer_side * (total_left_exp + total_right_exp))
                orig_img_height = canvas_height - int(longer_side * (total_top_exp + total_bottom_exp))
                
                # 计算原始图像位置
                orig_img_x = int(longer_side * left_exp)
                orig_img_y = int(longer_side * top_exp)
        else:
            # 没有扩展画布，原始图像就是整个画布
            orig_img_width = canvas_width
            orig_img_height = canvas_height
            orig_img_x = 0
            orig_img_y = 0
        
        # 处理margin，支持独立的四周margin配置
        # 首先检查是否提供了独立的margin配置
        original_longer_side = max(orig_img_width, orig_img_height)
        
        # 获取配置中的独立边距设置
        margin_top = text_config.get('margin_top', None)
        margin_bottom = text_config.get('margin_bottom', None)
        margin_left = text_config.get('margin_left', None)
        margin_right = text_config.get('margin_right', None)
        
        # 如果没有独立边距设置，则使用传统的margin配置
        if margin_top is None or margin_left is None:
            # 保持传统行为，如果是浮点数则认为是比例，转换为像素值
            calculated_margin = margin if isinstance(margin, int) else int(original_longer_side * margin)
            # 如果只定义了通用margin，则所有边距都使用该值
            margin_top = margin_left = margin_bottom = margin_right = calculated_margin
        else:
            # 使用独立边距配置，转换为像素值
            margin_top = int(original_longer_side * margin_top) if isinstance(margin_top, float) else margin_top
            margin_left = int(original_longer_side * margin_left) if isinstance(margin_left, float) else margin_left
            margin_bottom = int(original_longer_side * margin_bottom) if isinstance(margin_bottom, float) else margin_bottom
            margin_right = int(original_longer_side * margin_right) if isinstance(margin_right, float) else margin_right
        
        # 根据位置计算坐标
        if position in ['outside', 'bottom']:
            # 位于图像下方（在扩展画布的下方区域）
            if alignment == 'top-left':  # 特殊处理：当outside位置与top-left对齐组合时，意味着左上外侧区域
                x = orig_img_x + margin_left  # 从原图左边缘向右偏移
                y = orig_img_y - text_height - margin_top  # 从原图上边缘向上偏移
            else:
                y = orig_img_y + orig_img_height + margin_bottom
                if alignment == 'left':
                    x = orig_img_x + margin_left
                elif alignment == 'right':
                    x = orig_img_x + orig_img_width - text_width - margin_right
                else:  # center
                    x = orig_img_x + (orig_img_width - text_width) // 2
        elif position == 'top':
            # 位于图像上方（在扩展画布的上方区域）
            y = orig_img_y - text_height - margin_top
            if alignment == 'left':
                x = orig_img_x + margin_left
            elif alignment == 'right':
                x = orig_img_x + orig_img_width - text_width - margin_right
            elif alignment == 'top-left':  # 处理top-left对齐在上方的情况
                x = orig_img_x + margin_left  # 使用原图左边缘作为参考
                y = orig_img_y - text_height - margin_top  # 在原图上方
            else:  # center
                x = orig_img_x + (orig_img_width - text_width) // 2
        elif position == 'inside':
            # 位于图像内部
            y = orig_img_y + orig_img_height - text_height - margin_bottom
            if alignment == 'left':
                x = orig_img_x + margin_left
            elif alignment == 'right':
                x = orig_img_x + orig_img_width - text_width - margin_right
            elif alignment == 'top-left':  # 处理top-left对齐在内部的情况
                x = orig_img_x + margin_left
                y = orig_img_y + margin_top
            else:  # center
                x = orig_img_x + (orig_img_width - text_width) // 2
        elif position in ['tl', 'top-left']:
            # 左上角（等同于outside + top-left）
            x = orig_img_x + margin_left
            y = orig_img_y - text_height - margin_top
        elif position in ['tr', 'top-right']:
            # 右上角
            x = orig_img_x + orig_img_width - text_width - margin_right
            y = orig_img_y - text_height - margin_top
        elif position in ['bl', 'bottom-left']:
            # 左下角
            x = orig_img_x + margin_left
            y = orig_img_y + orig_img_height + margin_bottom
        elif position in ['br', 'bottom-right']:
            # 右下角
            x = orig_img_x + orig_img_width - text_width - margin_right
            y = orig_img_y + orig_img_height + margin_bottom
        else:
            # 默认情况下居中
            x = orig_img_x + (orig_img_width - text_width) // 2
            y = orig_img_y + orig_img_height + margin_bottom
        
        return x, y