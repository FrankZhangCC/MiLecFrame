"""
图像渲染引擎模块
负责相框的图层合成、背景填充、高斯模糊等功能
"""
import sys
import math
import logging
from pathlib import Path

# 添加项目根目录到sys.path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from PIL import Image, ImageDraw
from typing import Tuple, Dict, Optional, List
from src.utils.exif_helper import ExifHelper
from src.utils.font_manager import FontManager
from src.utils.layout_engine import LayoutEngine
from src.utils.logo_selector import LogoSelector
from src.utils.background_fill import BackgroundFillManager
from src.utils.render_context import RenderContext
from src.core.decorator import Decorator

logger = logging.getLogger(__name__)


class FrameRenderer:
    """相框渲染器"""
    
    def __init__(self):
        """初始化渲染器"""
        # 字体管理器
        self.font_manager = FontManager()

        # 初始化装饰器
        self.decorator = Decorator(font_manager=self.font_manager)

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
        logo_filename: Optional[str] = None,
        lens_display_mode: str = 'combined',
        use_short_lens: bool = False,
        saturation_override: Optional[float] = None,
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
            lens_display_mode: 镜头显示模式
            use_short_lens: 是否使用短版镜头名
            saturation_override: 覆盖饱和度增强系数（None=使用FILL_TYPES默认值）
            
        Returns:
            渲染后的图像
        """
        # 获取样式配置
        layout = style_config.get('layout', {})
        colors = style_config.get('colors', {})
        fonts = style_config.get('fonts', {})
        logo_config = style_config.get('logo', {})

        layout_engine = LayoutEngine(image.size, layout)
        canvas_width, canvas_height = layout_engine.canvas_size

        context = RenderContext(image.size, exif_data, author, location, lens_display_mode, use_short_lens)

        background = BackgroundFillManager.render(
            image, canvas_width, canvas_height, bg_fill_type,
            saturation=saturation_override
        )

        orig_x, orig_y, orig_w, orig_h = layout_engine.original_bounds
        positioned_image = background.copy()
        if image.mode == 'RGBA':
            positioned_image.paste(image, (orig_x, orig_y), image)
        else:
            positioned_image.paste(image, (orig_x, orig_y))

        if decorations:
            decorated_image = self.decorator.apply_decorations(
                positioned_image,
                decorations,
                layout_engine.original_image_size,
                layout_engine.layout_config
            )
        else:
            decorated_image = positioned_image
        
        # 文字层先处理（注册元素位置供 Logo 相对定位引用）
        image_with_text = self._add_text_and_icons_flexible(
            decorated_image, context, colors, fonts,
            bg_fill_type, layout_engine
        )
        
        # Logo 后处理（可依赖文字层已注册的坐标）
        if logo_config.get('enabled', False):
            if logo_filename is None:
                camera_brand = context.get_text('camera_make')
                if camera_brand:
                    logo_selector_instance = self._get_logo_selector()
                    is_dark_bg = BackgroundFillManager.is_dark_bg(bg_fill_type)
                    logo_filename = logo_selector_instance.auto_match_logo(
                        camera_brand.lower(), is_dark_bg=is_dark_bg
                    )
            
            if logo_filename:
                image_with_text = self._add_logo(image_with_text, logo_filename, logo_config, layout_engine)
        
        return image_with_text

    def _parse_color_value(self, custom_color) -> Optional[Tuple[int, int, int]]:
        """
        解析自定义颜色值，支持十六进制和RGB元组/列表格式
        """
        if not custom_color:
            return None
        if isinstance(custom_color, str) and custom_color.startswith('#'):
            return tuple(int(custom_color[i:i+2], 16) for i in (1, 3, 5))
        elif isinstance(custom_color, (tuple, list)) and len(custom_color) == 3:
            return tuple(custom_color)
        return None

    def _resolve_color_from_config(
        self, colors_config: Dict, dark_key: str, light_key: str, bg_fill_type: str
    ) -> Optional[Tuple[int, int, int]]:
        """
        根据背景类型从配置中解析自定义颜色
        """
        if dark_key not in colors_config or light_key not in colors_config:
            return None
        is_dark_bg = BackgroundFillManager.is_dark_bg(bg_fill_type)
        custom_color = colors_config[dark_key] if is_dark_bg else colors_config[light_key]
        return self._parse_color_value(custom_color)

    def _determine_text_color(
        self, bg_fill_type: str, colors_config: Dict, text_type: str = None
    ) -> Tuple[int, int, int]:
        """
        根据背景类型和配置确定文字颜色
        """
        if text_type:
            color = self._resolve_color_from_config(
                colors_config,
                f'custom_{text_type}_dark_color',
                f'custom_{text_type}_light_color',
                bg_fill_type
            )
            if color:
                return color

        color = self._resolve_color_from_config(
            colors_config, 'custom_text_dark_color', 'custom_text_light_color', bg_fill_type
        )
        if color:
            return color

        if BackgroundFillManager.is_dark_bg(bg_fill_type):
            return (255, 255, 255)
        else:
            return (0, 0, 0)

    def _resolve_element_order(
        self,
        text_elements: List[Tuple[str, str]],
        info_positions: Dict
    ) -> List[str]:
        """
        按 relative_to 依赖关系拓扑排序，保证参考元素先于被引用元素处理
        """
        names_in_list = [t[0] for t in text_elements]
        names_set = set(names_in_list)

        dependents = {name: [] for name in names_in_list}
        in_degree = {name: 0 for name in names_in_list}

        for name in names_in_list:
            cfg = info_positions.get(name, {})
            ref = cfg.get('relative_to')
            if ref and ref in names_set:
                dependents[ref].append(name)
                in_degree[name] += 1

        queue = [name for name in names_in_list if in_degree[name] == 0]
        ordered = []

        while queue:
            name = queue.pop(0)
            ordered.append(name)
            for dep in dependents[name]:
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)

        # 兜底：未被拓扑覆盖的元素（循环依赖等）按原序追加
        for name in names_in_list:
            if name not in ordered:
                ordered.append(name)

        return ordered

    def _add_text_and_icons_flexible(
        self, 
        image: Image.Image, 
        context: RenderContext,
        colors: Dict,
        fonts: Dict,
        bg_fill_type: str,
        layout_engine: LayoutEngine
    ) -> Image.Image:
        """
        添加更灵活定位的文字和图标层
        """
        result = image.copy()
        draw = ImageDraw.Draw(result)
        
        logger.debug("开始添加文字图层...")
        logger.debug(f"EXIF数据: {context.exif_data}")
        logger.debug(f"作者: {context.author}")
        logger.debug(f"地点: {context.location}")
        logger.debug(f"图像尺寸: {image.size}")
        logger.debug(f"原始图像尺寸: {layout_engine.original_image_size}")
        
        original_image_size = layout_engine.original_image_size
        
        text_elements = []
        
        info_positions = layout_engine.layout_config.get('info_position', {})
        
        for key in info_positions:
            text = context.get_text(key)
            if text:
                text_elements.append((key, text))
        
        if not text_elements:
            logger.debug("没有需要显示的文本信息")
            return result
        
        logger.debug(f"待渲染的文本元素: {text_elements}")
        
        # Phase 1: 测量所有元素的尺寸（不计算位置，不注册）
        draw_items = {}
        for text_type, text in text_elements:
            text_config = info_positions.get(text_type, {})

            font_size_config = fonts.get('sizes', {})
            text_specific_size_ratio = font_size_config.get(text_type, fonts.get('size_ratio', 0.02))

            text_color = self._determine_text_color(bg_fill_type, colors, text_type)

            segments = FontManager.split_mixed_text(text)

            if len(segments) <= 1:
                font = self.font_manager.load_font(fonts, original_image_size, text_specific_size_ratio, text)

                bbox = font.getbbox(text)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                ascent, descent = font.getmetrics()

                draw_items[text_type] = {
                    'text': text, 'font': font, 'color': text_color,
                    'width': text_width, 'height': ascent + descent,
                    'descent': descent, 'mixed': False
                }
            else:
                # 中英文混排：按 CJK / 拉丁片段拆分，分别加载对应字体，
                # 以拉丁字体（Gotham）的基线为基准对齐所有片段
                drawn_fonts = {}

                def _get_segment_font(is_cjk):
                    key = 'cjk' if is_cjk else 'latin'
                    if key not in drawn_fonts:
                        drawn_fonts[key] = self.font_manager.load_font(
                            fonts, original_image_size, text_specific_size_ratio,
                            force_chinese=is_cjk
                        )
                    return drawn_fonts[key]

                seg_info = []
                total_width = 0
                for seg_text, is_cjk in segments:
                    font = _get_segment_font(is_cjk)
                    bbox = font.getbbox(seg_text)
                    seg_width = bbox[2] - bbox[0]
                    ascent, descent = font.getmetrics()
                    seg_info.append((seg_text, font, seg_width, ascent, descent))
                    total_width += seg_width

                # 以拉丁字体（Gotham）为参考基准，使混排位置与纯英文一致
                ref_font = drawn_fonts.get('latin') or drawn_fonts.get('cjk')
                ref_ascent, ref_descent = ref_font.getmetrics()

                # 块高度取各片段的最大值，确保 CJK 字体的高出部不被裁切
                max_ascent = max(s[3] for s in seg_info)
                max_descent = max(s[4] for s in seg_info)
                text_height = max_ascent + max_descent

                draw_items[text_type] = {
                    'seg_info': seg_info, 'ref_ascent': ref_ascent,
                    'ref_descent': ref_descent, 'color': text_color,
                    'width': total_width, 'height': text_height, 'mixed': True
                }

        # Phase 2: 按依赖拓扑序计算位置并注册（保证 relative_to 指向的元素已就位）
        # 预注册缺失的参考元素：当 relative_to 指向的元素因无文本而被跳过时，
        # 以 0x0 尺寸注册其绝对位置锚点，避免依赖元素降级为绝对定位导致位置偏移
        for name in draw_items:
            cfg = info_positions.get(name, {})
            ref = cfg.get('relative_to')
            if ref and ref not in draw_items and ref in info_positions:
                ref_cfg = info_positions[ref]
                if not ref_cfg.get('relative_to'):
                    rx, ry = layout_engine.calculate_position(0, 0, ref_cfg)
                    layout_engine.register_element(ref, rx, ry, 0, 0)

        ordered_names = self._resolve_element_order(text_elements, info_positions)

        for name in ordered_names:
            item = draw_items[name]
            cfg = info_positions.get(name, {})

            x, y = layout_engine.calculate_position(item['width'], item['height'], cfg)

            logger.debug(
                f"[Pos] {name}: calc=({x}, {y}), bbox=({item['width']}x{item['height']}), "
                f"config={cfg.get('position', '?')}/{cfg.get('alignment', '?')} "
                f"marg={layout_engine._resolve_margins(cfg)}"
            )

            if item['mixed']:
                # 应用 refer 字体的 descent 偏移（与单字体路径一致），
                # 然后以 refer 字体的 ascent 确定共享基线
                y -= item['ref_descent']
            else:
                y -= item['descent']

            layout_engine.register_element(name, x, y, item['width'], item['height'], cfg.get('relative_to'))

        # Phase 3: 从 position 注册表读取最终坐标后统一绘制
        for name in ordered_names:
            bounds = layout_engine.get_element_bounds(name)
            if bounds is None:
                continue
            x, y, w, h = bounds

            item = draw_items[name]
            if not item['mixed']:
                draw.text((x, y), item['text'], fill=item['color'], font=item['font'])
            else:
                # 以 refer 字体的 ascent 确定共享基线
                baseline_y = y + item['ref_ascent']
                current_x = x
                # 逐片段绘制，各片段基线对齐到共享基线
                # CJK 字体 ascent 较大时自动上移，适配拉丁基线
                for seg_text, font, seg_width, ascent, descent in item['seg_info']:
                    seg_y = baseline_y - ascent
                    draw.text((current_x, seg_y), seg_text, fill=item['color'], font=font)
                    current_x += seg_width
        
        logger.debug("文字图层添加完成")
        return result

    def _add_logo(
        self, 
        image: Image.Image, 
        logo_filename: str, 
        logo_config: Dict,
        layout_engine: LayoutEngine
    ) -> Image.Image:
        """
        在图像上添加logo
        """
        logo_path = project_root / 'assets' / 'logos' / logo_filename
        
        if not logo_path.exists():
            logger.warning(f"Logo文件不存在: {logo_path}")
            return image
        
        try:
            logo = Image.open(logo_path)
            if logo.mode != 'RGBA':
                logo = logo.convert('RGBA')
        except Exception as e:
            logger.error(f"无法加载logo文件: {e}")
            return image
        
        original_image_size = layout_engine.original_image_size
        reference_side = min(original_image_size)

        size_ratio = logo_config.get('size_ratio', 0.05)

        logo_width, logo_height = logo.size
        logo_short_side = min(logo_width, logo_height)
        target_short_side = int(reference_side * size_ratio)
        scale = target_short_side / logo_short_side

        # Logo 对角线上限保护：防止细长条 Logo 失控
        max_diagonal = int(reference_side * 2 * size_ratio)
        logo_diagonal = math.hypot(logo_width, logo_height)
        if logo_diagonal * scale > max_diagonal:
            scale = max_diagonal / logo_diagonal

        new_logo_width = int(logo_width * scale)
        new_logo_height = int(logo_height * scale)

        logo = logo.resize((new_logo_width, new_logo_height), Image.Resampling.LANCZOS)

        x, y = layout_engine.calculate_position(new_logo_width, new_logo_height, logo_config)

        result = image.copy()
        if logo.mode == 'RGBA':
            result.paste(logo, (x, y), logo)
        else:
            result.paste(logo, (x, y))

        layout_engine.register_element('logo', x, y, new_logo_width, new_logo_height)
        
        return result
