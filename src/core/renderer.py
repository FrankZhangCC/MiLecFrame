# Copyright (c) 2026 FrankZhangCC
# MIT License - see LICENSE file for details

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
from typing import Tuple, Optional
from src.utils.font_manager import FontManager
from src.utils.layout_engine import LayoutEngine
from src.utils.logo_selector import LogoSelector
from src.utils.background_fill import BackgroundFillManager
from src.utils.render_context import RenderContext
from src.core.decorator import Decorator
from src.core.text_renderer import TextRenderer

logger = logging.getLogger(__name__)


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
        custom_text: Optional[str] = None,
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

        context = RenderContext(image.size, exif_data, author, location, lens_display_mode, use_short_lens, custom_text=custom_text)

        background = BackgroundFillManager.render(
            image, canvas_width, canvas_height, bg_fill_type,
            saturation=saturation_override
        )

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
            decorated_image, context, colors, fonts, bg_fill_type,
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
