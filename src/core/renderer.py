# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
图像渲染引擎模块
负责相框的图层合成、背景填充、高斯模糊等功能
"""
import sys
import math
import logging
from dataclasses import dataclass
from pathlib import Path

# 添加项目根目录到sys.path（使用统一的路径定位，保证开发/打包环境一致）
from src.utils.app_paths import get_resource_root
project_root = get_resource_root()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from PIL import Image
import numpy as np
from typing import Tuple, Optional, Dict, List
from src.utils.font_manager import FontManager
from src.utils.layout_engine import LayoutEngine
from src.utils.logo_selector import LogoSelector
from src.utils.background_fill import BackgroundFillManager
from src.utils.render_context import RenderContext
from src.core.blur_cache import RenderBlurCache, PreparedBlurLRU
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
    use_short_lens: bool = False                # 是否使用短版镜头名
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


# ── 矩形效果栈（设计文档 §3 / §5.1） ──────────────────────────

# 矩形模糊半径资源安全上限（全分辨率等效半径）。超过时 warning 并截断，
# 不静默丢弃（设计文档 §3 规则 9）
GAUSSIAN_RADIUS_MAX = 1000

# 矩形专用字段：构造定位配置时必须剔除，不能传入定位引擎（设计文档 §3 规则 11）
RECTANGLE_SKIP_KEYS = {
    'width_ratio', 'height_ratio', 'opacity', 'corner_radius', 'name',
    'fill', 'stroke', 'gaussian_blur',
}


@dataclass
class RectangleSpec:
    """单矩形效果解析结果（需求分析阶段的产物，不含渲染逻辑）

    mode 分流（设计文档 §3.1）：
      legacy       — fill/stroke/gaussian_blur 全部未启用，仍在原图下方绘制
      effect_stack — 显式写了 fill 或开启 stroke/gaussian_blur，
                     在原图上方按"模糊 → 填充 → 内描边"合成
    """
    name: str
    mode: str                                     # 'legacy' | 'effect_stack'
    box: Tuple[int, int, int, int]                # 未裁切矩形盒 (x, y, w, h)（画布坐标）
    canvas_clip: Tuple[int, int, int, int]        # 与画布交集 (x, y, w, h)（五层同步裁切基准）
    source_kind: str = 'photo'                    # 'photo'（⊆original_bounds）| 'canvas'（跨界/照片外）
    # ── 填充层（中层）──
    fill_enabled: bool = False
    fill_color: Optional[Tuple[int, int, int]] = None
    fill_opacity: float = 1.0
    # ── 描边层（顶层，内描边不改外部尺寸）──
    stroke_enabled: bool = False
    stroke_color: Optional[Tuple[int, int, int]] = None
    stroke_px: int = 0
    stroke_opacity: float = 1.0
    # ── 模糊层（底层）──
    blur_enabled: bool = False
    blur_radius: Optional[int] = None
    # ── 圆角（外轮廓；描边内轮廓按 stroke_px 自动内缩）──
    corner_px: Tuple[int, int, int, int] = (0, 0, 0, 0)  # (tl, tr, bl, br) 像素半径
    corner_radius: Optional[Dict] = None          # 原始配置（保留备用）


def _rect_is_effect_stack(rect_cfg: Dict) -> bool:
    """矩形分流判定（设计文档 §3.1）：

        legacy_mode = fill 字段缺失 and stroke.enabled != true
                      and gaussian_blur.enabled != true

    仅写入 stroke.enabled: false / gaussian_blur.enabled: false 不会把
    旧矩形迁移到原图上方；显式写 fill（哪怕 enabled: false）即选择
    效果栈语义。
    """
    if 'fill' in rect_cfg:
        return True
    stroke_cfg = rect_cfg.get('stroke')
    if isinstance(stroke_cfg, dict) and stroke_cfg.get('enabled', False) is True:
        return True
    blur_cfg = rect_cfg.get('gaussian_blur')
    if isinstance(blur_cfg, dict) and blur_cfg.get('enabled', False) is True:
        return True
    return False


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
        skip_names: Optional[set] = None,
    ) -> Image.Image:
        """
        在背景上绘制所有自定义矩形（背景层之上，原图层之下）

        Args:
            skip_names: 效果栈矩形名集合（在原图上方另行绘制），本方法跳过。
                        None/空集时保持 v2.5 全部矩形原位绘制的行为。
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
            # 效果栈矩形走 _draw_rectangle_effect_stack（原图上方），此处跳过
            if skip_names and rect_name in skip_names:
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

            # 4. 构建定位配置（剔除矩形专用键，保留定位参数；
            #    fill/stroke/gaussian_blur 同属专用键，防御性剔除）
            skip_keys = RECTANGLE_SKIP_KEYS
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

    def _compute_gaussian_required(
        self,
        effective_bg_type: str,
        layout_engine: LayoutEngine,
        image: Image.Image,
        rect_consumers: List,
    ):
        """
        全图高斯需求统一判定（设计文档 §5.4）

        短路条件位于整帧渲染级，而不是绑定在背景分支上：
            gaussian_required = background_blur or 矩形有模糊需求
        背景是否可见只判断背景是不是有效消费者，不能覆盖矩形需求
        （矩形需求由 rect_consumers 携带，Phase 3 起填充）。

        Args:
            effective_bg_type: 有效背景填充类型 key
            layout_engine: 布局引擎（含画布/原图几何与 layout 配置）
            image: 原始图像（用于 RGBA 保守判定）
            rect_consumers: 矩形模糊需求列表 [(source_kind, radius), ...]

        Returns:
            (gaussian_required, background_blur, bg_is_gaussian, bg_cfg) 四元组
        """
        cfg = BackgroundFillManager.FILL_TYPES.get(effective_bg_type) or {}
        bg_is_gaussian = cfg.get('method') == 'gaussian'

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
        gaussian_required = background_blur or len(rect_consumers) > 0
        return gaussian_required, background_blur, bg_is_gaussian, cfg

    def _resolve_rect_fill_color(self, colors_cfg: Dict, rect_name: str,
                                 is_dark_bg: bool) -> Optional[Tuple[int, int, int]]:
        """解析矩形填充颜色（现有 dark/light 回退语义，与旧式矩形一致）"""
        dark_key = f'custom_{rect_name}_dark_color'
        light_key = f'custom_{rect_name}_light_color'
        color_raw = colors_cfg.get(dark_key if is_dark_bg else light_key)
        if color_raw is None:
            color_raw = colors_cfg.get(light_key if is_dark_bg else dark_key)
        if color_raw is None:
            return None
        return _parse_hex_or_rgb(color_raw)

    def _resolve_rect_stroke_color(self, colors_cfg: Dict, rect_name: str,
                                   is_dark_bg: bool) -> Optional[Tuple[int, int, int]]:
        """解析矩形描边颜色（设计文档 §3 四级回退链）：

        当前方案描边色 → 另一方案描边色 → 当前方案填充色 → 另一方案填充色
        """
        stroke_dark = f'custom_{rect_name}_stroke_dark_color'
        stroke_light = f'custom_{rect_name}_stroke_light_color'
        fill_dark = f'custom_{rect_name}_dark_color'
        fill_light = f'custom_{rect_name}_light_color'
        if is_dark_bg:
            candidates = (stroke_dark, stroke_light, fill_dark, fill_light)
        else:
            candidates = (stroke_light, stroke_dark, fill_light, fill_dark)
        for key in candidates:
            parsed = _parse_hex_or_rgb(colors_cfg.get(key))
            if parsed is not None:
                return parsed
        return None

    def _analyze_rectangles(
        self,
        style_config: Dict,
        layout_engine: LayoutEngine,
        effective_bg_type: str,
    ) -> List[RectangleSpec]:
        """
        矩形需求分析阶段（设计文档 §5.1）：在生成背景前解析全部效果栈矩形

        完成分流、几何分类（照片内 vs 跨界/照片外）、三层参数校验与
        独立降级、颜色解析、模糊需求汇总。旧式矩形不在此解析
        （仍由 _draw_rectangles 原路径绘制，保证历史输出不变）。

        Returns:
            按 key 排序的 RectangleSpec 列表（后画覆盖先画）
        """
        layout = style_config.get('layout', {})
        colors_cfg = style_config.get('colors', {})
        rectangles = layout.get('rectangles')
        if not rectangles or not isinstance(rectangles, dict):
            return []

        ref = layout_engine.reference_side
        is_dark_bg = BackgroundFillManager.is_dark_bg(effective_bg_type)
        orig_x, orig_y, orig_w, orig_h = layout_engine.original_bounds
        canvas_w, canvas_h = layout_engine.canvas_size

        specs: List[RectangleSpec] = []

        for rect_name in sorted(rectangles.keys()):
            rect_cfg = rectangles[rect_name]
            if not isinstance(rect_cfg, dict):
                continue
            # 分流：仅效果栈矩形进入本阶段（§3.1）
            if not _rect_is_effect_stack(rect_cfg):
                continue

            # ── 几何：尺寸与位置 ──
            width_ratio = rect_cfg.get('width_ratio', 0)
            height_ratio = rect_cfg.get('height_ratio', 0)
            if width_ratio <= 0 or height_ratio <= 0:
                logger.warning("矩形 %s 尺寸无效 (width_ratio=%s, height_ratio=%s)，跳过",
                               rect_name, width_ratio, height_ratio)
                continue
            rect_w = int(ref * width_ratio)
            rect_h = int(ref * height_ratio)
            position_cfg = {k: v for k, v in rect_cfg.items()
                            if k not in RECTANGLE_SKIP_KEYS}
            rect_x, rect_y = layout_engine.calculate_position(
                rect_w, rect_h, position_cfg, defer_padding=True)

            # ── 几何：画布交集（完全在外直接跳过，不触发任何模糊计算）──
            ix0, iy0 = max(rect_x, 0), max(rect_y, 0)
            ix1 = min(rect_x + rect_w, canvas_w)
            iy1 = min(rect_y + rect_h, canvas_h)
            if ix1 <= ix0 or iy1 <= iy0:
                logger.debug("矩形 %s 完全位于画布外 box=%s，跳过",
                             rect_name, (rect_x, rect_y, rect_w, rect_h))
                continue
            canvas_clip = (ix0, iy0, ix1 - ix0, iy1 - iy0)

            # ── 几何：源分类（§4.1 包含关系判定）──
            inside = (rect_x >= orig_x and rect_y >= orig_y
                      and rect_x + rect_w <= orig_x + orig_w
                      and rect_y + rect_h <= orig_y + orig_h)
            source_kind = 'photo' if inside else 'canvas'

            # ── 填充层（缺失时默认开启，保持旧样式语义；§3 规则 2）──
            fill_cfg = rect_cfg.get('fill')
            fill_enabled = (not isinstance(fill_cfg, dict)) or bool(
                fill_cfg.get('enabled', True))
            fill_color = None
            fill_opacity = max(0.0, min(1.0, float(rect_cfg.get('opacity', 1.0))))
            if fill_enabled:
                fill_color = self._resolve_rect_fill_color(
                    colors_cfg, rect_name, is_dark_bg)
                if fill_color is None:
                    logger.warning("矩形 %s 未找到有效填充颜色，填充层降级", rect_name)
                    fill_enabled = False
            if fill_enabled and fill_opacity <= 0:
                # opacity<=0：纯色填充透明，不创建颜色层（§6 短路表）
                fill_enabled = False

            # ── 描边层（enabled 缺失默认 false；§3 规则 3/规则 10）──
            stroke_cfg = rect_cfg.get('stroke')
            stroke_enabled = (isinstance(stroke_cfg, dict)
                              and bool(stroke_cfg.get('enabled', False)))
            stroke_color = None
            stroke_px = 0
            stroke_opacity = 0.0
            if stroke_enabled:
                stroke_opacity = max(0.0, min(
                    1.0, float(stroke_cfg.get('opacity', 1.0))))
                if stroke_opacity <= 0:
                    stroke_enabled = False
            if stroke_enabled:
                stroke_color = self._resolve_rect_stroke_color(
                    colors_cfg, rect_name, is_dark_bg)
                if stroke_color is None:
                    logger.warning("矩形 %s 未找到描边颜色（回退链均无效），仅跳过描边层",
                                   rect_name)
                    stroke_enabled = False
            if stroke_enabled:
                radius_ratio = stroke_cfg.get('radius_ratio', 0.005)
                if not (isinstance(radius_ratio, (int, float))
                        and math.isfinite(radius_ratio) and radius_ratio > 0):
                    logger.warning("矩形 %s stroke.radius_ratio 非法: %s，描边层降级",
                                   rect_name, radius_ratio)
                    stroke_enabled = False
                else:
                    # 不足 1px 时保底 1px（避免开关开启却无视觉结果，§6 短路表）
                    stroke_px = max(1, round(ref * radius_ratio))
                    # 厚度上限：保留至少 1px 内容区，超限 warning 并截断
                    max_px = (min(rect_w, rect_h) - 1) // 2
                    if max_px < 1:
                        logger.warning(
                            "矩形 %s 过小 (%dx%d)，无内容区可保留，描边层降级",
                            rect_name, rect_w, rect_h)
                        stroke_enabled = False
                    elif stroke_px > max_px:
                        logger.warning(
                            "矩形 %s 描边厚度 %dpx 超过上限 %dpx，已截断（保留 1px 内容区）",
                            rect_name, stroke_px, max_px)
                        stroke_px = max_px

            # ── 模糊层（enabled 缺失默认 false；半径须为有限正数）──
            blur_cfg = rect_cfg.get('gaussian_blur')
            blur_enabled = (isinstance(blur_cfg, dict)
                            and bool(blur_cfg.get('enabled', False)))
            blur_radius = None
            if blur_enabled:
                raw_radius = blur_cfg.get('radius', 200)
                if not (isinstance(raw_radius, (int, float))
                        and math.isfinite(raw_radius) and raw_radius > 0):
                    logger.warning("矩形 %s gaussian_blur.radius 非法: %s，模糊层降级",
                                   rect_name, raw_radius)
                    blur_enabled = False
                else:
                    if raw_radius > GAUSSIAN_RADIUS_MAX:
                        logger.warning(
                            "矩形 %s 模糊半径 %s 超过安全上限 %d，已截断",
                            rect_name, raw_radius, GAUSSIAN_RADIUS_MAX)
                        raw_radius = GAUSSIAN_RADIUS_MAX
                    blur_radius = int(raw_radius)
            # 模糊可见性优化：被启用且 opacity>=1 的有效填充完全覆盖时，
            # 模糊层不可见，降级关闭且不为该矩形登记高斯需求（§6 短路表）
            if blur_enabled and fill_enabled and fill_opacity >= 1.0:
                blur_enabled = False

            # 三层全部关闭/无效 → 整个矩形跳过，不创建任何临时层（§6 短路表）
            if not (fill_enabled or stroke_enabled or blur_enabled):
                logger.debug("矩形 %s 三层均无效，整体跳过", rect_name)
                continue

            # ── 圆角（像素半径，与旧式矩形 int(ref*ratio) 语义一致）──
            corner_cfg = rect_cfg.get('corner_radius')
            corner_px = (0, 0, 0, 0)
            if isinstance(corner_cfg, dict):
                corner_px = tuple(
                    int(ref * corner_cfg.get(k, 0))
                    for k in ('top_left', 'top_right', 'bottom_left', 'bottom_right'))

            spec = RectangleSpec(
                name=rect_name,
                mode='effect_stack',
                box=(rect_x, rect_y, rect_w, rect_h),
                canvas_clip=canvas_clip,
                source_kind=source_kind,
                fill_enabled=fill_enabled,
                fill_color=fill_color,
                fill_opacity=fill_opacity,
                stroke_enabled=stroke_enabled,
                stroke_color=stroke_color,
                stroke_px=stroke_px,
                stroke_opacity=stroke_opacity,
                blur_enabled=blur_enabled,
                blur_radius=blur_radius,
                corner_px=corner_px,
                corner_radius=corner_cfg if isinstance(corner_cfg, dict) else None,
            )
            logger.debug(
                "rectangle %s: source=%s, box=%s, blur_radius=%s, "
                "fill=%s/%.2f, stroke=%s/%spx/%.2f",
                rect_name, source_kind, spec.box, blur_radius,
                fill_enabled, fill_opacity if fill_enabled else 0.0,
                stroke_enabled, stroke_px if stroke_enabled else 0,
                stroke_opacity if stroke_enabled else 0.0)
            specs.append(spec)

        return specs

    def _draw_effect_stack(
        self,
        output: Image.Image,
        stack_specs: List[RectangleSpec],
        blur_cache: Optional[RenderBlurCache],
        layout_engine: LayoutEngine,
    ) -> Image.Image:
        """
        绘制全部效果栈矩形（原图上方，decorator 之前）

        specs 已按 key 排序：后画覆盖先画。模糊源一律取自冻结的原图
        卷积缓存（RenderBlurCache），不含任何已绘制的效果栈矩形，
        保证绘制顺序不影响取样（设计文档 §2.2）。
        """
        for spec in stack_specs:
            output = self._draw_rectangle_effect_stack(
                output, spec, blur_cache, layout_engine)
        return output

    def _draw_rectangle_effect_stack(
        self,
        output: Image.Image,
        spec: RectangleSpec,
        blur_cache: Optional[RenderBlurCache],
        layout_engine: LayoutEngine,
    ) -> Image.Image:
        """
        单矩形三层效果合成：模糊 → 填充 → 内描边，局部 patch 内混合，
        最后仅经 outer_mask 一次组裁切合成到输出（设计文档 §5.5）。
        """
        cx, cy, clip_w, clip_h = spec.canvas_clip
        bx, by, box_w, box_h = spec.box
        if clip_w <= 0 or clip_h <= 0:
            return output

        # ── 1. 内容底图：模糊 patch 或 underlay patch ──────────
        blur_patch = None
        if spec.blur_enabled and spec.blur_radius is not None and blur_cache is not None:
            try:
                if spec.source_kind == 'photo':
                    # 照片尺寸模糊层按 box-orig 偏移取局部裁切区域
                    orig_x, orig_y = layout_engine.original_bounds[0], \
                        layout_engine.original_bounds[1]
                    photo_blur = blur_cache.get_photo_size_blur(
                        spec.blur_radius, saturation=1.0)
                    blur_patch = photo_blur.crop((
                        cx - orig_x, cy - orig_y,
                        cx - orig_x + clip_w, cy - orig_y + clip_h))
                else:
                    # 跨界/照片外：画布尺寸模糊层按画布坐标裁切
                    # （延续背景"原图拉伸到画布"的模糊语义，§4.1）
                    canvas_blur = blur_cache.get_canvas_size_blur(
                        spec.blur_radius, saturation=1.0,
                        canvas_size=layout_engine.canvas_size)
                    blur_patch = canvas_blur.crop((cx, cy, cx + clip_w, cy + clip_h))
            except NotImplementedError:
                # 方案 B 接口位防御：source_kind 异常时回退 underlay
                blur_patch = None
        if blur_patch is not None:
            patch_arr = np.array(blur_patch, dtype=np.float32)
        else:
            # 模糊关闭：取当前输出在矩形位置的 underlay patch
            patch_arr = np.array(
                output.crop((cx, cy, cx + clip_w, cy + clip_h)), dtype=np.float32)

        # ── 2. 填充层：按 fill_opacity 混合（只乘填充，不乘模糊层，
        #      防止"25% 模糊 + 25% 着色"的双重着色，§5.5） ──────────
        if spec.fill_enabled:
            fa = spec.fill_opacity
            fill_rgb = np.array(spec.fill_color, dtype=np.float32)
            patch_arr = patch_arr * (1.0 - fa) + fill_rgb * fa

        # ── 3. 描边层：stroke_coverage × stroke_opacity ─────────
        # 内轮廓 = 外轮廓内缩 stroke_px；内圆角 = max(外圆角 - stroke_px, 0)
        if spec.stroke_enabled:
            sp = spec.stroke_px
            inner_w, inner_h = box_w - 2 * sp, box_h - 2 * sp
            inner_corners = tuple(max(r - sp, 0) for r in spec.corner_px)
            if any(r > 0 for r in inner_corners):
                inner_mask = _rounded_corner_mask(inner_w, inner_h, *inner_corners)
            else:
                inner_mask = Image.new('L', (inner_w, inner_h), 255)
            # 内覆盖率铺到整矩形坐标系（inner_box 外为 0）
            inner_full = np.zeros((box_h, box_w), dtype=np.float32)
            inner_full[sp:sp + inner_h, sp:sp + inner_w] = np.array(
                inner_mask, dtype=np.float32)
            # stroke_coverage 只描述矩形组内部描边环；外边缘抗锯齿统一
            # 交给最终 outer_mask（防止同一 alpha 被乘两次产生暗边）
            stroke_alpha = (255.0 - inner_full) / 255.0 * spec.stroke_opacity
            stroke_alpha = stroke_alpha[
                cy - by:cy - by + clip_h, cx - bx:cx - bx + clip_w]
            stroke_rgb = np.array(spec.stroke_color, dtype=np.float32)
            patch_arr = patch_arr * (1.0 - stroke_alpha[..., None]) \
                + stroke_rgb * stroke_alpha[..., None]

        # ── 4. 单次组裁切：效果 patch 的 alpha 只经 outer_mask 写入
        #      一次，paste() 不再传 patch 自身 alpha（透明度平方防护）──
        outer_mask_full = _rounded_corner_mask(box_w, box_h, *spec.corner_px)
        outer_clip = np.array(outer_mask_full, dtype=np.uint8)[
            cy - by:cy - by + clip_h, cx - bx:cx - bx + clip_w]
        effect_patch = Image.fromarray(
            np.clip(patch_arr, 0, 255).astype(np.uint8), mode='RGB')
        output.paste(effect_patch, (cx, cy), Image.fromarray(outer_clip, mode='L'))
        return output
    
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
                effective_bg_type = options.bg_fill_type
        else:
            effective_bg_type = options.bg_fill_type

        layout_engine = LayoutEngine(image.size, layout)
        canvas_width, canvas_height = layout_engine.canvas_size

        context = RenderContext(image.size, metadata.exif_data, metadata.author, metadata.location, metadata.lens_display_mode, metadata.use_short_lens, custom_text=metadata.custom_text, timestamp_display_mode=metadata.timestamp_display_mode)

        # ── 矩形需求分析（背景渲染前：模糊需求须参与统一判定）──────
        # stack_specs 为效果栈矩形（原图上方）；旧式矩形仍由
        # _draw_rectangles 原路径绘制，保证历史输出不变
        stack_specs = self._analyze_rectangles(
            style_config, layout_engine, effective_bg_type)
        stack_names = {spec.name for spec in stack_specs}

        # ── 全图高斯需求统一判定（设计文档 §5.4） ──────────────────
        # rect_consumers：启用模糊的效果栈矩形需求 [(source_kind, radius), ...]
        # （分析阶段已完成画布相交/覆盖降级等短路过滤）
        rect_consumers = [(spec.source_kind, spec.blur_radius)
                          for spec in stack_specs if spec.blur_enabled]
        (gaussian_required, background_blur,
         bg_is_gaussian, bg_cfg) = self._compute_gaussian_required(
            effective_bg_type, layout_engine, image, rect_consumers)
        photo_radii = sorted({r for (_kind, r) in rect_consumers})
        logger.debug(
            "blur plan: gaussian_required=%s, background_blur=%s, "
            "photo_radii=%s, scene_radii=[]",
            gaussian_required, background_blur, photo_radii)

        blur_cache = None
        if gaussian_required:
            # 需要高斯：创建每帧一级缓存，背景与矩形共享原图卷积；
            # LRU + 稳定源键齐备时同步接入二级跨帧缓存
            blur_cache = RenderBlurCache(
                image, prepared_lru=options.prepared_blur_cache,
                source_cache_key=options.source_cache_key)
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
            fallback_color = ((0, 0, 0) if bg_cfg.get('text_scheme') == 'dark'
                              else (255, 255, 255))
            background = Image.new('RGB', (canvas_width, canvas_height),
                                   fallback_color)
        else:
            # 纯色背景（含样式自定义纯色）：零高斯计算，无需建缓存
            background = BackgroundFillManager.render(
                image, canvas_width, canvas_height, effective_bg_type,
                saturation=options.saturation_override)

        # ── 自定义矩形（背景层之上，原图层之下） ──────────────────
        # 效果栈矩形（stack_names）跳过，另在原图上方绘制
        background = self._draw_rectangles(
            background, style_config, layout_engine, effective_bg_type,
            skip_names=stack_names)

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

        # ── 效果栈矩形（原图上方，decorator 之前；后画覆盖先画） ──
        # 模糊源冻结取自原图卷积缓存，不含任何已绘制的效果栈矩形
        if stack_specs:
            positioned_image = self._draw_effect_stack(
                positioned_image, stack_specs, blur_cache, layout_engine)

        if options.decorations:
            decorated_image = self.decorator.apply_decorations(
                positioned_image,
                options.decorations,
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
            if options.logo_filename is None:
                camera_brand = context.get_text('camera_make')
                if camera_brand:
                    logo_selector_instance = self._get_logo_selector()
                    is_dark_bg = BackgroundFillManager.is_dark_bg(effective_bg_type)
                    options.logo_filename = logo_selector_instance.auto_match_logo(
                        camera_brand.lower(), is_dark_bg=is_dark_bg
                    )

            if options.logo_filename:
                image_with_text = self._add_logo(image_with_text, options.logo_filename, logo_config, layout_engine)
        
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
