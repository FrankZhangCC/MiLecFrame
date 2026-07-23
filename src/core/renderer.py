# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

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

from PIL import Image
import numpy as np
from typing import Tuple, Optional, Dict
from src.utils.font_manager import FontManager
from src.utils.layout_engine import LayoutEngine
from src.utils.logo_selector import LogoSelector
from src.utils.background_fill import BackgroundFillManager
from src.utils.render_context import RenderContext
from src.core.decorator import Decorator
from src.core.text_renderer import TextRenderer

logger = logging.getLogger(__name__)


def _parse_hex_or_rgb(value) -> Optional[Tuple[int, int, int]]:
    """
    解析颜色值，支持 #RRGGBB 字符串或 [R, G, B] 列表/元组
    返回 RGB 元组，解析失败返回 None
    """
    if isinstance(value, str):
        s = value.strip()
        if s.startswith('#'):
            try:
                return tuple(int(s[i:i+2], 16) for i in (1, 3, 5))
            except (ValueError, IndexError):
                return None
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            return tuple(int(c) for c in value)
        except (ValueError, TypeError):
            return None
    return None


def _rounded_corner_mask(w, h, r_tl, r_tr, r_bl, r_br):
    """
    创建四角独立圆角的抗锯齿灰度蒙版
    255 = 保留（不透明），0 = 切除（透明）

    基于 signed distance field（SDF）对弧形边缘做 1px 软过渡，
    消除纯 PIL rectangle + pieslice 方案产生的像素锯齿。
    仅在四个 r×r 角区域内做 numpy 运算，不扫描全图。
    """
    mask = np.full((h, w), 255, dtype=np.float32)

    if r_tl > 0 and r_tl <= w and r_tl <= h:
        iy, ix = np.ogrid[:r_tl, :r_tl]
        dist = np.sqrt((ix - r_tl) ** 2 + (iy - r_tl) ** 2)
        mask[:r_tl, :r_tl] = np.clip(r_tl - dist + 0.5, 0, 1) * 255

    if r_tr > 0 and r_tr <= w and r_tr <= h:
        iy, ix = np.ogrid[:r_tr, :r_tr]
        dist = np.sqrt(ix ** 2 + (iy - r_tr) ** 2)
        mask[:r_tr, w - r_tr:] = np.clip(r_tr - dist + 0.5, 0, 1) * 255

    if r_bl > 0 and r_bl <= w and r_bl <= h:
        iy, ix = np.ogrid[:r_bl, :r_bl]
        dist = np.sqrt((ix - r_bl) ** 2 + iy ** 2)
        mask[h - r_bl:, :r_bl] = np.clip(r_bl - dist + 0.5, 0, 1) * 255

    if r_br > 0 and r_br <= w and r_br <= h:
        iy, ix = np.ogrid[:r_br, :r_br]
        dist = np.sqrt(ix ** 2 + iy ** 2)
        mask[h - r_br:, w - r_br:] = np.clip(r_br - dist + 0.5, 0, 1) * 255

    return Image.fromarray(mask.astype(np.uint8))


def _draw_single_rectangle(
    background: Image.Image,
    rect_w: int,
    rect_h: int,
    position: Tuple[int, int],
    color: Tuple[int, int, int],
    opacity: float,
    corner_radius: Optional[Dict] = None,
    reference_side: float = 1.0,
) -> Image.Image:
    """
    在背景上绘制单个矩形（RGBA 合成，支持透明度和圆角）

    Args:
        background: 背景图像（RGB 模式）
        rect_w, rect_h: 矩形像素尺寸
        position: 左上角坐标 (x, y)
        color: RGB 颜色元组
        opacity: 透明度 0.0-1.0
        corner_radius: 圆角配置 {'top_left': ratio, ...} 或 None（直角）
        reference_side: 参照边长度，用于将圆角 ratio 转为像素
    """
    alpha_val = int(round(255 * opacity))
    rect_layer = Image.new('RGBA', background.size, (0, 0, 0, 0))
    rect_img = Image.new('RGBA', (rect_w, rect_h), (*color, alpha_val))

    if corner_radius and isinstance(corner_radius, dict):
        r_tl = int(reference_side * corner_radius.get('top_left', 0))
        r_tr = int(reference_side * corner_radius.get('top_right', 0))
        r_bl = int(reference_side * corner_radius.get('bottom_left', 0))
        r_br = int(reference_side * corner_radius.get('bottom_right', 0))
        if any(r > 0 for r in [r_tl, r_tr, r_bl, r_br]):
            mask = _rounded_corner_mask(rect_w, rect_h, r_tl, r_tr, r_bl, r_br)
            mask_array = np.array(mask, dtype=np.float32) * opacity
            rect_img.putalpha(Image.fromarray(mask_array.astype(np.uint8)))

    rect_layer.paste(rect_img, position)
    result = background.convert('RGBA')
    result = Image.alpha_composite(result, rect_layer)
    return result.convert('RGB')


class FrameRenderer:
    """相框渲染器"""
    
    def __init__(self):
        """初始化渲染器"""
        # 字体管理器
        self.font_manager = FontManager()

        # 初始化装饰器
        self.decorator = Decorator(font_manager=self.font_manager)

    def _draw_rectangles(
        self,
        background: Image.Image,
        style_config: Dict,
        layout_engine: LayoutEngine,
        effective_bg_type: str,
    ) -> Image.Image:
        """
        在背景上绘制所有自定义矩形（背景层之上，原图层之下）
        """
        layout = style_config.get('layout', {})
        colors_cfg = style_config.get('colors', {})
        rectangles = layout.get('rectangles')

        if not rectangles or not isinstance(rectangles, dict):
            return background

        ref = layout_engine.reference_side
        is_dark_bg = BackgroundFillManager.is_dark_bg(effective_bg_type)

        result = background.copy()

        for rect_name in sorted(rectangles.keys()):
            rect_cfg = rectangles[rect_name]
            if not isinstance(rect_cfg, dict):
                continue

            # 1. 颜色解析（深/浅背景自适应）
            dark_key = f'custom_{rect_name}_dark_color'
            light_key = f'custom_{rect_name}_light_color'
            color_raw = colors_cfg.get(dark_key if is_dark_bg else light_key)
            if color_raw is None:
                color_raw = colors_cfg.get(light_key if is_dark_bg else dark_key)
            if color_raw is None:
                logger.warning("矩形 %s 未找到颜色配置，跳过", rect_name)
                continue

            color = _parse_hex_or_rgb(color_raw)
            if color is None:
                logger.warning("矩形 %s 颜色解析失败: %s，跳过", rect_name, color_raw)
                continue

            # 2. 尺寸解析
            width_ratio = rect_cfg.get('width_ratio', 0)
            height_ratio = rect_cfg.get('height_ratio', 0)
            if width_ratio <= 0 or height_ratio <= 0:
                logger.warning("矩形 %s 尺寸无效 (width_ratio=%s, height_ratio=%s)，跳过",
                               rect_name, width_ratio, height_ratio)
                continue
            rect_w = int(ref * width_ratio)
            rect_h = int(ref * height_ratio)

            # 3. 透明度
            opacity = float(rect_cfg.get('opacity', 1.0))
            opacity = max(0.0, min(1.0, opacity))

            # 4. 构建定位配置（剔除矩形专用键，保留定位参数）
            skip_keys = {'width_ratio', 'height_ratio', 'opacity', 'corner_radius', 'name'}
            position_cfg = {k: v for k, v in rect_cfg.items() if k not in skip_keys}

            # 5. 计算位置（跳过 padding 约束）
            rect_x, rect_y = layout_engine.calculate_position(
                rect_w, rect_h, position_cfg, defer_padding=True)

            # 6. 圆角
            corner_radius = rect_cfg.get('corner_radius')

            # 7. 绘制
            logger.debug("绘制矩形 %s: %dx%d @ (%d,%d), color=%s, opacity=%.2f",
                         rect_name, rect_w, rect_h, rect_x, rect_y, color, opacity)
            result = _draw_single_rectangle(
                result, rect_w, rect_h, (rect_x, rect_y), color,
                opacity, corner_radius, ref)

        return result

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
        custom_text: Optional[str] = None,
        timestamp_display_mode: str = 'full',
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
            custom_text: 自定义文本内容（由用户在 GUI 输入，仅当样式配置中 custom_text.enabled=True 时生效）
            timestamp_display_mode: 拍摄时间显示模式（'full'=日期与时刻, 'date_only'=仅日期, 'hide'=不显示）
            
        Returns:
            渲染后的图像
        """
        # 获取样式配置
        layout = style_config.get('layout', {})
        colors = style_config.get('colors', {})
        fonts = style_config.get('fonts', {})
        logo_config = style_config.get('logo', {})

        # ── 自定义背景填充色（样式配置中 colors 区块指定） ────────────
        custom_bg_color_raw = colors.get('custom_bg_color')
        if custom_bg_color_raw:
            parsed = _parse_hex_or_rgb(custom_bg_color_raw)
            if parsed:
                # 从配置中获取 text_scheme，未设置时自动根据亮度判定
                text_scheme = colors.get('custom_bg_text_scheme')
                if not text_scheme:
                    r, g, b = parsed
                    luminance = 0.299 * r + 0.587 * g + 0.114 * b
                    text_scheme = 'dark' if luminance < 128 else 'light'
                # 注册到 BackgroundFillManager 并获取有效 key
                effective_bg_type = BackgroundFillManager.register_custom_solid(
                    parsed, text_scheme)
            else:
                logger.warning("样式自定义背景色解析失败: %s，回退到 GUI 选择", custom_bg_color_raw)
                effective_bg_type = bg_fill_type
        else:
            effective_bg_type = bg_fill_type

        layout_engine = LayoutEngine(image.size, layout)
        canvas_width, canvas_height = layout_engine.canvas_size

        context = RenderContext(image.size, exif_data, author, location, lens_display_mode, use_short_lens, custom_text=custom_text, timestamp_display_mode=timestamp_display_mode)

        background = BackgroundFillManager.render(
            image, canvas_width, canvas_height, effective_bg_type,
            saturation=saturation_override
        )

        # ── 自定义矩形（背景层之上，原图层之下） ──────────────────
        background = self._draw_rectangles(
            background, style_config, layout_engine, effective_bg_type)

        orig_x, orig_y, orig_w, orig_h = layout_engine.original_bounds
        positioned_image = background.copy()

        # 原图圆角处理（若启用）
        corner_cfg = layout.get('corner_radius')
        use_rounded = isinstance(corner_cfg, dict) and corner_cfg.get('enabled', False)
        if use_rounded:
            ref = layout_engine.reference_side
            r_tl = int(ref * corner_cfg.get('top_left', 0))
            r_tr = int(ref * corner_cfg.get('top_right', 0))
            r_bl = int(ref * corner_cfg.get('bottom_left', 0))
            r_br = int(ref * corner_cfg.get('bottom_right', 0))

            if any(r > 0 for r in [r_tl, r_tr, r_bl, r_br]):
                img_rgba = image.convert('RGBA')
                mask = _rounded_corner_mask(orig_w, orig_h, r_tl, r_tr, r_bl, r_br)
                img_rgba.putalpha(mask)
                positioned_image.paste(img_rgba, (orig_x, orig_y), img_rgba)
            else:
                positioned_image.paste(image, (orig_x, orig_y))
        elif image.mode == 'RGBA':
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
        
        # 文字层（委托给 TextRenderer）
        text_renderer = TextRenderer(self.font_manager, layout_engine)
        image_with_text = text_renderer.render(
            decorated_image, context, colors, fonts, effective_bg_type,
        )
        
        # Logo 后处理（可依赖文字层已注册的坐标）
        if logo_config.get('enabled', False):
            if logo_filename is None:
                camera_brand = context.get_text('camera_make')
                if camera_brand:
                    logo_selector_instance = self._get_logo_selector()
                    is_dark_bg = BackgroundFillManager.is_dark_bg(effective_bg_type)
                    logo_filename = logo_selector_instance.auto_match_logo(
                        camera_brand.lower(), is_dark_bg=is_dark_bg
                    )
            
            if logo_filename:
                image_with_text = self._add_logo(image_with_text, logo_filename, logo_config, layout_engine)
        
        return image_with_text

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

        # Logo 长边长度限制：防止细长条 Logo 失控
        # 优先读取 max_dim_limit_ratio，兼容旧字段 diagonal_limit_ratio
        limit_ratio = logo_config.get('max_dim_limit_ratio',
                        logo_config.get('diagonal_limit_ratio', 2.5))
        max_dim_limit = int(reference_side * limit_ratio * size_ratio)
        logo_max_dim = max(logo_width, logo_height)
        if logo_max_dim * scale > max_dim_limit:
            scale = max_dim_limit / logo_max_dim

        # 品牌独立缩放系数（在长度限制之后叠加）
        logo_selector = self._get_logo_selector()
        brand_scale = logo_selector.get_brand_scale_factor(logo_filename)
        scale *= brand_scale

        new_logo_width = int(logo_width * scale)
        new_logo_height = int(logo_height * scale)

        logo = logo.resize((new_logo_width, new_logo_height), Image.Resampling.LANCZOS)

        x, y = layout_engine.calculate_position(new_logo_width, new_logo_height, logo_config)

        result = image.copy()
        if logo.mode == 'RGBA':
            result.paste(logo, (x, y), logo)
        else:
            result.paste(logo, (x, y))

        layout_engine.register_element('logo', x, y, new_logo_width, new_logo_height, ascent=0)
        
        return result
