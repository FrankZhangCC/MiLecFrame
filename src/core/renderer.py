"""
图像渲染引擎模块
负责相框的图层合成、背景填充、高斯模糊等功能
"""
import sys
from pathlib import Path

# 添加项目根目录到sys.path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from PIL import Image, ImageDraw
from typing import Tuple, Dict, Optional, List
# 修改导入路径，使用绝对导入
from src.utils.exif_helper import ExifHelper
from src.utils.font_manager import FontManager
from src.utils.layout_engine import LayoutEngine
from src.utils.logo_selector import LogoSelector  # 导入LogoSelector
from src.utils.gaussian_blur import apply_gaussian_blur_overlay_expansion
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
        
        # 定义深色和浅色背景类型列表，便于后续扩展
        self.dark_bg_types = [
            'pure_black',
            'gaussian_black_65',
            'gaussian_black_35',
            'gaussian_black'
        ]
        
        self.light_bg_types = [
            'pure_white',
            'gaussian_white_65',
            'gaussian_white_35',
            'gaussian_white'
        ]
        
        # 初始化装饰器
        self.decorator = Decorator()
        
        # 字体管理器
        self.font_manager = FontManager()

    def _get_logo_selector(self):
        """获取LogoSelector实例"""
        if not hasattr(self, '_logo_selector'):
            self._logo_selector = LogoSelector()
        return self._logo_selector
    
    def render_frame(
        self, 
        image: Image.Image, 
        exif_data: Optional[Dict], 
        author: Optional[str], 
        location: Optional[str],
        style_config: Dict,
        bg_fill_type: str = "white",
        decorations: Optional[List[Dict]] = None,
        logo_filename: Optional[str] = None
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
            logo_filename: logo文件名
            
        Returns:
            渲染后的图像
        """
        # 获取样式配置
        layout = style_config.get('layout', {})
        colors = style_config.get('colors', {})
        fonts = style_config.get('fonts', {})
        bg_fill_config = style_config.get('background_fill', {})
        logo_config = style_config.get('logo', {})

        self._bg_fill_type = bg_fill_type

        self.layout_engine = LayoutEngine(image.size, layout)

        canvas_width, canvas_height = self.layout_engine.canvas_size

        background = self._create_background_with_expansion(
            image, canvas_width, canvas_height, bg_fill_type, bg_fill_config
        )

        orig_x, orig_y, orig_w, orig_h = self.layout_engine.original_bounds
        positioned_image = background.copy()
        if image.mode == 'RGBA':
            positioned_image.paste(image, (orig_x, orig_y), image)
        else:
            positioned_image.paste(image, (orig_x, orig_y))

        if decorations:
            decorated_image = self.decorator.apply_decorations(
                positioned_image,
                decorations,
                self.layout_engine.original_image_size,
                self.layout_engine.layout_config
            )
        else:
            decorated_image = positioned_image
        
        # 添加logo（如果启用）
        if logo_config.get('enabled', False):
            # 如果没有指定logo文件名，尝试自动匹配
            if not logo_filename:
                camera_brand = ExifHelper.get_camera_brand(exif_data) or ExifHelper.get_camera_model(exif_data)
                if camera_brand:
                    # 使用LogoSelector类的实例来自动匹配logo
                    logo_selector_instance = self._get_logo_selector()
                    logo_filename = logo_selector_instance.auto_match_logo(camera_brand)
            
            if logo_filename:
                decorated_image = self._add_logo(decorated_image, logo_filename, logo_config)
        
        # 添加文字和图标层
        final_image = self._add_text_and_icons_flexible(
            decorated_image, exif_data, author, location, layout, colors, fonts
        )
        
        return final_image
    
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
            return apply_gaussian_blur_overlay_expansion(
                image, canvas_width, canvas_height, 'black', 
                65  # 65%透明度
            )
        elif bg_fill_type == "gaussian_white_65":
            return apply_gaussian_blur_overlay_expansion(
                image, canvas_width, canvas_height, 'white', 
                65  # 65%透明度
            )
        elif bg_fill_type == "gaussian_black_35":
            return apply_gaussian_blur_overlay_expansion(
                image, canvas_width, canvas_height, 'black', 
                35  # 35%透明度
            )
        elif bg_fill_type == "gaussian_white_35":
            return apply_gaussian_blur_overlay_expansion(
                image, canvas_width, canvas_height, 'white', 
                35  # 35%透明度
            )
        else:
            # 默认使用白色背景
            return Image.new('RGB', (canvas_width, canvas_height), color='white')
    
    def _determine_text_color(self, bg_fill_type: str, colors_config: Dict, text_type: str = None) -> Tuple[int, int, int]:
        """
        根据背景类型和配置确定文字颜色
        如果配置中有自定义文字颜色，优先使用；否则根据背景类型使用自适应颜色
        
        Args:
            bg_fill_type: 背景填充类型
            colors_config: 颜色配置字典
            text_type: 文本类型（如 'timestamp', 'location' 等），用于特定类型的颜色设置
            
        Returns:
            RGB格式的文字颜色元组
        """
        # 检查是否有特定文本类型的自定义颜色（区分亮色和暗色背景）
        if text_type:
            # 检查暗色背景下特定文本类型的自定义颜色
            dark_color_key = f'custom_{text_type}_dark_color'
            light_color_key = f'custom_{text_type}_light_color'
            
            if dark_color_key in colors_config and light_color_key in colors_config:
                # 根据背景类型选择对应的颜色
                if any(bg_fill_type.startswith(dark_type) for dark_type in self.dark_bg_types):
                    # 深色背景使用亮色文字
                    custom_color = colors_config[dark_color_key]
                else:
                    # 浅色背景使用暗色文字
                    custom_color = colors_config[light_color_key]
                
                if custom_color:
                    # 处理自定义颜色格式
                    if isinstance(custom_color, str) and custom_color.startswith('#'):
                        # 转换十六进制颜色为RGB
                        return tuple(int(custom_color[i:i+2], 16) for i in (1, 3, 5))
                    elif isinstance(custom_color, (tuple, list)) and len(custom_color) == 3:
                        # RGB元组或列表
                        return tuple(custom_color)

        # 检查是否有通用的自定义颜色（区分亮色和暗色背景）
        dark_color_key = 'custom_text_dark_color'
        light_color_key = 'custom_text_light_color'
        
        if dark_color_key in colors_config and light_color_key in colors_config:
            # 根据背景类型选择对应的颜色
            if any(bg_fill_type.startswith(dark_type) for dark_type in self.dark_bg_types):
                # 深色背景使用亮色文字
                custom_color = colors_config[dark_color_key]
            else:
                # 浅色背景使用暗色文字
                custom_color = colors_config[light_color_key]
            
            if custom_color:
                # 处理自定义颜色格式
                if isinstance(custom_color, str) and custom_color.startswith('#'):
                    # 转换十六进制颜色为RGB
                    return tuple(int(custom_color[i:i+2], 16) for i in (1, 3, 5))
                elif isinstance(custom_color, (tuple, list)) and len(custom_color) == 3:
                    # RGB元组或列表
                    return tuple(custom_color)

        # 根据背景类型列表判断使用什么颜色的文字
        # 检查是否为深色背景（直接匹配或以深色背景类型开头）
        if any(bg_fill_type.startswith(dark_type) for dark_type in self.dark_bg_types):
            # 深色背景使用白色文字
            return (255, 255, 255)  # 白色
        else:
            # 其他情况（包括浅色背景）使用黑色文字
            return (0, 0, 0)  # 黑色

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
        print(f"原始图像尺寸: {self.layout_engine.original_image_size}")
        
        # 获取原始图像尺寸
        original_image_size = self.layout_engine.original_image_size
        
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

            # 获取特定信息的字体大小配置，如果没有则使用通用配置
            font_size_config = fonts.get('sizes', {})
            text_specific_size_ratio = font_size_config.get(text_type, fonts.get('size_ratio', 0.02))

            # 使用原始图像长边作为基准加载字体，传递文本内容以智能选择字体
            font = self.font_manager.load_font(fonts, original_image_size, text_specific_size_ratio, text)

            # 根据背景类型和配置确定文字颜色
            bg_fill_type = getattr(self, '_bg_fill_type', 'pure_white')  # 默认为纯白色背景
            text_color = self._determine_text_color(bg_fill_type, colors, text_type)

            # 计算文本边界框
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # 使用布局引擎计算文本位置
            x, y = self.layout_engine.calculate_position(text_width, text_height, text_config)

            print(f"[Pos] {text_type}: calc=({x}, {y}), bbox=({text_width}x{text_height}), config={text_config.get('position', '?')}/{text_config.get('alignment', '?')} marg={self.layout_engine._resolve_margins(text_config)}")

            # 使用基线定位修正Y坐标
            ascent, descent = font.getmetrics()
            y -= descent  # 调整Y坐标，使文本以其基线为准

            # 绘制文本
            draw.text((x, y), text, fill=text_color, font=font)

            # 记录元素位置，用于相对定位
            self.layout_engine.register_element(text_type, x, y, text_width, text_height)
        
        print("文字图层添加完成")
        return result

    def _add_logo(
        self, 
        image: Image.Image, 
        logo_filename: str, 
        logo_config: Dict
    ) -> Image.Image:
        """
        在图像上添加logo
        
        Args:
            image: 输入图像
            logo_filename: logo文件名
            logo_config: logo配置
            
        Returns:
            添加logo后的图像
        """
        # 获取项目根目录
        project_root = Path(__file__).resolve().parent.parent.parent
        logo_path = project_root / 'assets' / 'logos' / logo_filename
        
        if not logo_path.exists():
            print(f"警告: Logo文件不存在: {logo_path}")
            return image
        
        try:
            # 加载logo图像
            logo = Image.open(logo_path)
            if logo.mode != 'RGBA':
                logo = logo.convert('RGBA')
        except Exception as e:
            print(f"错误: 无法加载logo文件: {e}")
            return image
        
        # 获取原始图像尺寸
        original_image_size = self.layout_engine.original_image_size
        longer_side = max(original_image_size)

        # 计算logo尺寸
        size_ratio = logo_config.get('size_ratio', 0.05)  # 默认为原图长边的5%
        logo_height = int(longer_side * size_ratio)

        # 保持宽高比缩放logo
        logo_aspect_ratio = logo.width / logo.height
        logo_width = int(logo_height * logo_aspect_ratio)

        logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)

        # 使用布局引擎计算logo位置
        x, y = self.layout_engine.calculate_position(logo_width, logo_height, logo_config)

        # 将logo粘贴到图像上
        result = image.copy()
        if logo.mode == 'RGBA':
            result.paste(logo, (x, y), logo)
        else:
            result.paste(logo, (x, y))

        # 记录logo位置，用于其他元素的相对定位
        self.layout_engine.register_element('logo', x, y, logo_width, logo_height)
        
        return result
