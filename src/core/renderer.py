# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
图像渲染引擎模块
负责相框的图层合成、背景填充、高斯模糊等功能
"""
import sys
import logging
from dataclasses import dataclass
from pathlib import Path

# 添加项目根目录到sys.path（使用统一的路径定位，保证开发/打包环境一致）
from src.utils.app_paths import get_resource_root
project_root = get_resource_root()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from PIL import Image
from typing import Tuple, Optional, Dict, List
from src.utils.font_manager import FontManager
from src.utils.layout_engine import LayoutEngine
from src.utils.logo_selector import LogoSelector
from src.utils.background_fill import BackgroundFillManager
from src.utils.render_context import RenderContext
from src.utils.color_utils import parse_color_value
from src.core.blur_cache import RenderBlurCache, PreparedBlurLRU
from src.core.decorator import Decorator
from src.core.rectangle_layer import (
    analyze_rectangles,
    draw_legacy_rectangles,
    draw_effect_stacks,
    rounded_corner_mask,
)
from src.core.text_renderer import TextRenderer
# 竖图方向适配（方案 docs/plans/PORTRAIT_ORIENTATION_ADAPTATION_PLAN.md §5）：
# 解析/旋转/还原/缓存键派生全部收敛到统一工具模块，渲染器不自带规则
from src.utils.orientation_adaptation import (
    resolve_effective_adaptation,
    rotate_image_for_render,
    restore_rendered_orientation,
    build_adapted_source_cache_key,
)

logger = logging.getLogger(__name__)


@dataclass
class RenderMetadata:
    """渲染元数据：拍摄相关信息，render_frame 内部整体转喂 RenderContext。

    生命周期：随每张图 / 每次生成新建，不跨请求持有。
    注意：走 ImageProcessor.process() 路径时 exif_data 由处理器从文件
    提取并覆盖（见 process() 内说明），调用方无需也无法从外部传入。
    """
    exif_data: Optional[Dict] = None            # EXIF 数据（预览直调路径使用）
    author: Optional[str] = None                # 作者名
    location: Optional[str] = None              # 拍摄地点
    custom_text: Optional[str] = None           # 自定义文本（样式 custom_text.enabled 时生效）
    lens_display_mode: str = 'combined'         # 镜头显示模式 combined/camera_only/lens_only
    lens_name_mode: str = 'default'             # 镜头名模式：default(键归位)/full(强制完整名)/short(强制短版名)
    timestamp_display_mode: str = 'full'        # 拍摄时间显示模式 full/date_only/hide


@dataclass
class RenderOptions:
    """渲染行为选项：背景 / 装饰 / Logo 等跨图层渲染开关。

    生命周期：可由 GUI 页面长期持有、随用户操作就地更新字段
    （高斯矩形设计第 8 步将在此追加 source_cache_key / prepared_blur_cache
    两个带默认值字段，届时所有现有构造点零改动）。
    """
    # 默认值取注册表常量：历史默认 "white" 是非法键（image_processor.py
    # 注释已记录该坑），凡未显式指定背景的调用一律落到 DEFAULT_FILL
    bg_fill_type: str = BackgroundFillManager.DEFAULT_FILL
    decorations: Optional[List[Dict]] = None    # 装饰元素列表 [{'type': ..., 'params': ...}]
    logo_filename: Optional[str] = None         # None=按相机品牌自动匹配；""=禁用 Logo；其他=指定文件
    saturation_override: Optional[float] = None # None=FILL_TYPES 默认；1.0=不做增强
    # ── 二级缓存接入（dataclass 加默认字段，全部现有构造点零改动） ──
    # 源图稳定键：FileItem 导入摘要 / 样式编辑器样本图键；None=不启用二级缓存
    source_cache_key: Optional[str] = None
    # 页面级 LRU（PreparedBlurLRU）：与 source_cache_key 同时提供才生效；
    # 批量处理路径不传，仅用一级缓存
    prepared_blur_cache: Optional[PreparedBlurLRU] = None
    # ── 竖图方向适配用户选项（方案 docs/plans/PORTRAIT_ORIENTATION_ADAPTATION_PLAN.md §3.1）──
    # default=跟随样式 default_portrait_adaptation；none/clockwise/counterclockwise=
    # 显式覆盖样式。渲染器内解析为局部有效方向并做整帧前置旋转，
    # 绝不回写本字段（本对象可被 GUI/批处理跨多次渲染复用）
    portrait_adaptation: str = 'default'


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

    def _compute_gaussian_required(
        self,
        effective_bg_type: str,
        layout_engine: LayoutEngine,
        image: Image.Image,
        rect_needs_blur: bool,
    ):
        """
        全图高斯需求统一判定（设计文档 §5.4）

        短路条件位于整帧渲染级，而不是绑定在背景分支上：
            gaussian_required = background_blur or 矩形有模糊需求
        背景是否可见只判断背景是不是有效消费者，不能覆盖矩形需求。

        Args:
            effective_bg_type: 有效背景填充类型 key
            layout_engine: 布局引擎（含画布/原图几何与 layout 配置）
            image: 原始图像（用于 RGBA 保守判定）
            rect_needs_blur: 任一效果栈矩形启用模糊（审计 Q14-10：
                本判定只消费布尔，需求详情由持有它的 rectangle_layer 表达）

        Returns:
            (gaussian_required, background_blur, bg_is_gaussian) 三元组
        """
        # 背景语义通过管理器接口获取（审计 Q7），不直读注册表 schema
        bg_is_gaussian = BackgroundFillManager.is_gaussian(effective_bg_type)

        # "背景可见"几何判定（比较最终几何而非 expand_canvas 开关，
        # 因为开关为 true 但四边扩展均为 0 时画布实际没有扩展）：
        #   1. original_bounds != 全画布（存在可见边框区域）
        orig_x, orig_y, orig_w, orig_h = layout_engine.original_bounds
        cw, ch = layout_engine.canvas_size
        background_visible = (orig_x, orig_y, orig_w, orig_h) != (0, 0, cw, ch)

        #   2. 原图圆角启用且任一半径 > 0 → 四角可能露出背景
        if not background_visible:
            corner_cfg = layout_engine.layout_config.get('corner_radius')
            if isinstance(corner_cfg, dict) and corner_cfg.get('enabled', False):
                ref = layout_engine.reference_side
                if any(int(ref * corner_cfg.get(k, 0)) > 0 for k in (
                        'top_left', 'top_right', 'bottom_left', 'bottom_right')):
                    background_visible = True

        #   3. 输入图仍可能含透明像素（渲染器允许外部直传 RGBA）→ 保守视为可见
        if image.mode == 'RGBA':
            background_visible = True

        background_blur = bg_is_gaussian and background_visible
        gaussian_required = background_blur or rect_needs_blur
        return gaussian_required, background_blur, bg_is_gaussian

    def render_frame(
        self,
        image: Image.Image,
        style_config: Dict,
        metadata: Optional[RenderMetadata] = None,
        options: Optional[RenderOptions] = None,
    ) -> Image.Image:
        """
        渲染带相框的图像

        Args:
            image: 原始图像
            style_config: 样式配置
            metadata: 渲染元数据（拍摄相关信息，None 时使用默认值）
            options: 渲染行为选项（背景/装饰/Logo 等，None 时使用默认值）

        Returns:
            渲染后的图像
        """
        # 哨兵解包：避免可变默认值陷阱，也兼容 None 直传
        metadata = metadata or RenderMetadata()
        options = options or RenderOptions()

        # ── 方向适配·前置（方案 §5.1） ─────────────────────────────
        # 解析最终方向（用户显式选择优先、样式默认兜底）并按来源决定
        # 图片方向适用范围：用户显式选择对所有图片（横/竖/方形）整帧
        # 前置旋转；样式预设仅对竖图生效。旋转后的整帧全部阶段按旋转
        # 后尺寸处理，函数末尾统一还原。旋转放在函数最前，
        # LayoutEngine / RenderContext 自然按旋转后 image.size 计算，
        # 后续阶段零改动。解析失败（非法样式默认值/非法用户值）→
        # ValueError 沿现有异常链抛出，由调用方既有 try/except 兜底。
        effective_adaptation, adaptation_from_user = resolve_effective_adaptation(
            style_config, options.portrait_adaptation)
        image, adaptation_applied = rotate_image_for_render(
            image, effective_adaptation, adaptation_from_user)
        # 派生局部高斯二级缓存键：真实旋转时附加方向后缀隔离 CW/CCW
        # 卷积结果；只构造局部键，绝不回写 options.source_cache_key
        # （本对象可被 GUI/批处理跨多次渲染复用）
        effective_source_cache_key = build_adapted_source_cache_key(
            options.source_cache_key, effective_adaptation, adaptation_applied)
        if adaptation_applied:
            logger.info("方向适配生效: %s（来源=%s，渲染期转置，输出前还原）",
                        effective_adaptation,
                        "用户显式" if adaptation_from_user else "样式预设")

        # 获取样式配置
        layout = style_config.get('layout', {})
        colors = style_config.get('colors', {})
        fonts = style_config.get('fonts', {})
        logo_config = style_config.get('logo', {})

        # ── 自定义背景填充色（样式配置中 colors 区块指定） ────────────
        custom_bg_color_raw = colors.get('custom_bg_color')
        if custom_bg_color_raw:
            parsed = parse_color_value(custom_bg_color_raw)
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
                effective_bg_type = options.bg_fill_type
        else:
            effective_bg_type = options.bg_fill_type

        layout_engine = LayoutEngine(image.size, layout)
        canvas_width, canvas_height = layout_engine.canvas_size

        context = RenderContext(image.size, metadata.exif_data, metadata.author, metadata.location, metadata.lens_display_mode, metadata.lens_name_mode, custom_text=metadata.custom_text, timestamp_display_mode=metadata.timestamp_display_mode)

        # ── 矩形需求分析（背景渲染前：模糊需求须参与统一判定）──────
        # 矩形子系统的分类、几何与颜色决策全部收敛在 rectangle_layer
        # （审计 Q1/Q2）：legacy 与效果栈分别产出 spec 列表，绘制端纯
        # 执行。禁用、无效或画布外的效果栈矩形不生成 spec——不绘制、
        # 不回流 legacy（审计 Q3 语义由分析阶段承接）。
        legacy_rects, effect_rects = analyze_rectangles(
            style_config, layout_engine, effective_bg_type)

        # ── 全图高斯需求统一判定（设计文档 §5.4） ──────────────────
        # 矩形模糊需求详情由 rectangle_layer 持有；本判定只消费布尔
        rect_needs_blur = any(spec.blur is not None for spec in effect_rects)
        (gaussian_required, background_blur,
         bg_is_gaussian) = self._compute_gaussian_required(
            effective_bg_type, layout_engine, image, rect_needs_blur)
        photo_radii = sorted({spec.blur.radius for spec in effect_rects
                              if spec.blur is not None})
        logger.debug(
            "blur plan: gaussian_required=%s, background_blur=%s, "
            "photo_radii=%s",
            gaussian_required, background_blur, photo_radii)

        blur_cache = None
        if gaussian_required:
            # 需要高斯：创建每帧一级缓存，背景与矩形共享原图卷积；
            # LRU + 稳定源键齐备时同步接入二级跨帧缓存。
            # 传入方向适配派生的局部键（真实旋转时含方向后缀），
            # 防止 CW/CCW 两方向尺寸相同导致二级缓存错误复用
            blur_cache = RenderBlurCache(
                image, prepared_lru=options.prepared_blur_cache,
                source_cache_key=effective_source_cache_key)
            background = BackgroundFillManager.render(
                image, canvas_width, canvas_height, effective_bg_type,
                saturation=options.saturation_override, blur_cache=blur_cache)
            logger.debug("blur cache: %s", blur_cache.summary())
        elif bg_is_gaussian:
            # 短路：背景类型为高斯但背景完全不可见（原图将覆盖全部画布）。
            # 用与 text_scheme 匹配的纯色替代——替代像素不会出现在最终
            # 输出（被原图全覆盖），但 is_dark_bg 仍驱动文字/Logo/矩形
            # 配色，替代色必须与原背景的明暗方案一致，保证输出像素不变。
            # 顺带修复既有浪费：高斯背景+无画布扩展不再全量模糊。
            # fallback 画布是后续复制/粘贴的承载画布，不能删除（审计 Q7）
            fallback_color = ((0, 0, 0)
                              if BackgroundFillManager.get_text_scheme(
                                  effective_bg_type) == 'dark'
                              else (255, 255, 255))
            background = Image.new('RGB', (canvas_width, canvas_height),
                                   fallback_color)
        else:
            # 纯色背景（含样式自定义纯色）：零高斯计算，无需建缓存
            background = BackgroundFillManager.render(
                image, canvas_width, canvas_height, effective_bg_type,
                saturation=options.saturation_override)

        # ── legacy 矩形（背景层之上，原图层之下） ──────────────────
        background = draw_legacy_rectangles(
            background, legacy_rects, layout_engine.reference_side)

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
                mask = rounded_corner_mask(orig_w, orig_h, r_tl, r_tr, r_bl, r_br)
                img_rgba.putalpha(mask)
                positioned_image.paste(img_rgba, (orig_x, orig_y), img_rgba)
            else:
                positioned_image.paste(image, (orig_x, orig_y))
        elif image.mode == 'RGBA':
            positioned_image.paste(image, (orig_x, orig_y), image)
        else:
            positioned_image.paste(image, (orig_x, orig_y))

        # ── 效果栈矩形（原图上方，decorator 之前；后画覆盖先画） ──
        # 模糊源冻结取自原图卷积缓存，不含任何已绘制的效果栈矩形
        if effect_rects:
            positioned_image = draw_effect_stacks(
                positioned_image, effect_rects, blur_cache, layout_engine)

        if options.decorations:
            decorated_image = self.decorator.apply_decorations(
                positioned_image,
                options.decorations,
                layout_engine.original_bounds
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
            # 自动匹配结果只在本帧内有效（审计 Q5）：写入局部变量，
            # 绝不回写 options.logo_filename——本对象可被 GUI/批处理
            # 跨多次渲染复用，回写会让后续帧沿用上一帧按旧品牌/旧背景
            # 匹配的结果，跳过应有的自动重选。三态语义保持不变：
            # None=自动、""=禁用、非空=固定文件。
            effective_logo_filename = options.logo_filename
            if effective_logo_filename is None:
                camera_brand = context.get_text('camera_make')
                if camera_brand:
                    logo_selector_instance = self._get_logo_selector()
                    is_dark_bg = BackgroundFillManager.is_dark_bg(effective_bg_type)
                    effective_logo_filename = logo_selector_instance.auto_match_logo(
                        camera_brand.lower(), is_dark_bg=is_dark_bg
                    )

            if effective_logo_filename:
                image_with_text = self._add_logo(
                    image_with_text, effective_logo_filename,
                    logo_config, layout_engine)

        # ── 方向适配·还原（方案 §5.1） ─────────────────────────────
        # 整帧渲染完成后执行反向转置；仅在前置旋转真实应用过时生效，
        # 未旋转路径原引用返回（零复制）。render_frame 唯一返回点。
        return restore_rendered_orientation(
            image_with_text, effective_adaptation, adaptation_applied)

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
        # 加载阶段已强制转换为 RGBA（审计 Q14-5：mode 分支恒真，删除）
        result.paste(logo, (x, y), logo)

        layout_engine.register_element('logo', x, y, new_logo_width, new_logo_height)
        
        return result
