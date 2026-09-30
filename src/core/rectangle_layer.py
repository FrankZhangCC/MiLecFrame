# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
矩形图层模块（审计 Q1/Q2 拆分产物）

矩形子系统的唯一实现：分流分类、几何求值、三层效果解析与绘制。
FrameRenderer 只做整帧编排（背景 → legacy 矩形 → 原图 → 效果栈 →
文字/Logo/装饰），不再解释矩形配置。

统一分流计划（设计文档 §3.1 + 审计 Q1 的三种结果）：

    legacy       — 未写 fill 且未开启 stroke/gaussian_blur，
                   只在原图下方绘制（历史输出不变）
    effect_stack — 显式写了 fill 或开启 stroke/gaussian_blur，
                   只在原图上方按"模糊 → 填充 → 内描边"合成
    禁用、无效或完全在画布外的效果栈矩形不生成 spec：
    不绘制、不回流 legacy（审计 Q3 的最小修复语义由本模块承接）

Q2 层模型：填充/描边/模糊建模为校验后的可选层（None = 关闭/无效），
层参数在分析阶段一次解析完成；绘制端只消费，不再解释配置组合。
"""
import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from src.utils.background_fill import BackgroundFillManager
from src.utils.color_utils import parse_color_value

logger = logging.getLogger(__name__)

# 矩形模糊半径资源安全上限（全分辨率等效半径）。超过时 warning 并截断，
# 不静默丢弃（设计文档 §3 规则 9）
GAUSSIAN_RADIUS_MAX = 1000

# 矩形专用字段：构造定位配置时必须剔除，不能传入定位引擎（设计文档 §3 规则 11）
RECTANGLE_SKIP_KEYS = {
    'width_ratio', 'height_ratio', 'opacity', 'corner_radius', 'name',
    'fill', 'stroke', 'gaussian_blur',
}


def is_effect_stack(rect_cfg: Dict) -> bool:
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


@dataclass
class FillLayer:
    """有效填充层：存在即表示该层通过校验、参数满足绘制要求。"""
    color: Tuple[int, int, int]
    opacity: float


@dataclass
class StrokeLayer:
    """有效描边层（内描边，不改外部尺寸）。"""
    color: Tuple[int, int, int]
    thickness_px: int
    opacity: float


@dataclass
class BlurLayer:
    """有效模糊层：取样一律取自冻结的原图卷积缓存。"""
    radius: int


@dataclass
class RectangleSpec:
    """单矩形解析结果（分类/几何/颜色决策的唯一产物，绘制端纯执行）。

    kind 表达统一分流计划：'legacy' 只在原图下方绘制；
    'effect_stack' 只在原图上方绘制。
    """
    name: str
    kind: str                                     # 'legacy' | 'effect_stack'
    box: Tuple[int, int, int, int]                # 未裁切矩形盒 (x, y, w, h)（画布坐标）
    source_kind: str = 'photo'                    # 'photo'（⊆original_bounds）| 'canvas'（跨界/照片外）
    canvas_clip: Optional[Tuple[int, int, int, int]] = None  # 与画布交集（效果栈裁切基准）
    # ── legacy 单层（kind='legacy'）──
    legacy_color: Optional[Tuple[int, int, int]] = None
    legacy_opacity: float = 1.0
    legacy_corner_radius: Optional[Dict] = None   # 原始圆角配置（绘制端按参照边换算）
    # ── 效果栈三层（kind='effect_stack'；None = 该层关闭/无效）──
    fill: Optional[FillLayer] = None
    stroke: Optional[StrokeLayer] = None
    blur: Optional[BlurLayer] = None
    # 外轮廓四角像素半径 (tl, tr, bl, br)，效果栈组裁切与内描边内缩共用
    corner_px: Tuple[int, int, int, int] = (0, 0, 0, 0)


def rounded_corner_mask(w, h, r_tl, r_tr, r_bl, r_br):
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


def draw_single_rectangle(
    background,
    rect_w: int,
    rect_h: int,
    position: Tuple[int, int],
    color: Tuple[int, int, int],
    opacity: float,
    corner_radius: Optional[Dict] = None,
    reference_side: float = 1.0,
):
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
            mask = rounded_corner_mask(rect_w, rect_h, r_tl, r_tr, r_bl, r_br)
            mask_array = np.array(mask, dtype=np.float32) * opacity
            rect_img.putalpha(Image.fromarray(mask_array.astype(np.uint8)))

    rect_layer.paste(rect_img, position)
    result = background.convert('RGBA')
    result = Image.alpha_composite(result, rect_layer)
    return result.convert('RGB')


def _resolve_fill_color(colors_cfg: Dict, rect_name: str,
                        is_dark_bg: bool) -> Optional[Tuple[int, int, int]]:
    """解析矩形填充颜色（dark/light 回退语义，legacy 与效果栈共用）"""
    dark_key = f'custom_{rect_name}_dark_color'
    light_key = f'custom_{rect_name}_light_color'
    color_raw = colors_cfg.get(dark_key if is_dark_bg else light_key)
    if color_raw is None:
        color_raw = colors_cfg.get(light_key if is_dark_bg else dark_key)
    if color_raw is None:
        return None
    return parse_color_value(color_raw)


def _resolve_stroke_color(colors_cfg: Dict, rect_name: str,
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
        parsed = parse_color_value(colors_cfg.get(key))
        if parsed is not None:
            return parsed
    return None


def analyze_rectangles(
    style_config: Dict,
    layout_engine,
    effective_bg_type: str,
) -> Tuple[List[RectangleSpec], List[RectangleSpec]]:
    """
    矩形需求分析阶段：全部分类、几何与颜色决策的唯一入口。

    遍历按 key 排序的全部矩形配置，共享几何求值后按分流身份分别产出：
    legacy spec（原图下方绘制）与效果栈 spec（原图上方绘制）。
    效果栈三层（填充/描边/模糊）逐层校验与独立降级；三层全部无效或
    完全在画布外时不生成 spec。

    Returns:
        (legacy_specs, effect_specs)，各自保持 key 排序（后画覆盖先画）
    """
    layout = style_config.get('layout', {})
    colors_cfg = style_config.get('colors', {})
    rectangles = layout.get('rectangles')
    if not rectangles or not isinstance(rectangles, dict):
        return [], []

    ref = layout_engine.reference_side
    is_dark_bg = BackgroundFillManager.is_dark_bg(effective_bg_type)
    orig_x, orig_y, orig_w, orig_h = layout_engine.original_bounds
    canvas_w, canvas_h = layout_engine.canvas_size

    legacy_specs: List[RectangleSpec] = []
    effect_specs: List[RectangleSpec] = []

    for rect_name in sorted(rectangles.keys()):
        rect_cfg = rectangles[rect_name]
        if not isinstance(rect_cfg, dict):
            continue

        # ── 几何：尺寸（两种身份共用同一校验与文案）──
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
        # 矩形按设计永久豁免 padding 安全区（STYLE_GUIDE §padding，
        # 审计 Q4 的 exempt 语义），不是延迟夹持
        rect_x, rect_y = layout_engine.calculate_position(
            rect_w, rect_h, position_cfg, padding_mode='exempt')

        # ── 分流：分类/几何/颜色此后按身份解析，不再有第二条路径 ──
        if not is_effect_stack(rect_cfg):
            # legacy：颜色解析（缺失/非法即跳过，与历史行为一致）
            dark_key = f'custom_{rect_name}_dark_color'
            light_key = f'custom_{rect_name}_light_color'
            color_raw = colors_cfg.get(dark_key if is_dark_bg else light_key)
            if color_raw is None:
                color_raw = colors_cfg.get(light_key if is_dark_bg else dark_key)
            if color_raw is None:
                logger.warning("矩形 %s 未找到颜色配置，跳过", rect_name)
                continue
            color = parse_color_value(color_raw)
            if color is None:
                logger.warning("矩形 %s 颜色解析失败: %s，跳过", rect_name, color_raw)
                continue
            opacity = float(rect_cfg.get('opacity', 1.0))
            opacity = max(0.0, min(1.0, opacity))
            legacy_specs.append(RectangleSpec(
                name=rect_name,
                kind='legacy',
                box=(rect_x, rect_y, rect_w, rect_h),
                legacy_color=color,
                legacy_opacity=opacity,
                legacy_corner_radius=rect_cfg.get('corner_radius'),
            ))
            continue

        # ── 效果栈：画布交集（完全在外直接跳过，不触发任何模糊计算）──
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
        fill_layer = None
        fill_opacity = max(0.0, min(1.0, float(rect_cfg.get('opacity', 1.0))))
        if fill_enabled:
            fill_color = _resolve_fill_color(colors_cfg, rect_name, is_dark_bg)
            if fill_color is None:
                logger.warning("矩形 %s 未找到有效填充颜色，填充层降级", rect_name)
                fill_enabled = False
        if fill_enabled and fill_opacity <= 0:
            # opacity<=0：纯色填充透明，不创建颜色层（§6 短路表）
            fill_enabled = False
        if fill_enabled:
            fill_layer = FillLayer(color=fill_color, opacity=fill_opacity)

        # ── 描边层（enabled 缺失默认 false；§3 规则 3/规则 10）──
        stroke_cfg = rect_cfg.get('stroke')
        stroke_enabled = (isinstance(stroke_cfg, dict)
                          and bool(stroke_cfg.get('enabled', False)))
        stroke_layer = None
        stroke_opacity = 0.0
        if stroke_enabled:
            stroke_opacity = max(0.0, min(
                1.0, float(stroke_cfg.get('opacity', 1.0))))
            if stroke_opacity <= 0:
                stroke_enabled = False
        if stroke_enabled:
            stroke_color = _resolve_stroke_color(
                colors_cfg, rect_name, is_dark_bg)
            if stroke_color is None:
                logger.warning("矩形 %s 未找到描边颜色（回退链均无效），仅跳过描边层",
                               rect_name)
                stroke_enabled = False
        stroke_px = 0
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
        if stroke_enabled:
            stroke_layer = StrokeLayer(
                color=stroke_color, thickness_px=stroke_px,
                opacity=stroke_opacity)

        # ── 模糊层（enabled 缺失默认 false；半径须为有限正数）──
        blur_cfg = rect_cfg.get('gaussian_blur')
        blur_enabled = (isinstance(blur_cfg, dict)
                        and bool(blur_cfg.get('enabled', False)))
        blur_layer = None
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
                blur_enabled = True
                blur_layer = BlurLayer(radius=int(raw_radius))
        # 模糊可见性优化：有效且 opacity>=1 的填充完全覆盖时，
        # 模糊层不可见，降级关闭且不为该矩形登记高斯需求（§6 短路表）
        if blur_layer is not None and fill_layer is not None \
                and fill_layer.opacity >= 1.0:
            blur_layer = None

        # 三层全部关闭/无效 → 整个矩形跳过，不创建任何临时层（§6 短路表）
        if fill_layer is None and stroke_layer is None and blur_layer is None:
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
            kind='effect_stack',
            box=(rect_x, rect_y, rect_w, rect_h),
            source_kind=source_kind,
            canvas_clip=canvas_clip,
            fill=fill_layer,
            stroke=stroke_layer,
            blur=blur_layer,
            corner_px=corner_px,
        )
        logger.debug(
            "rectangle %s: source=%s, box=%s, blur_radius=%s, "
            "fill=%s/%.2f, stroke=%s/%spx/%.2f",
            rect_name, source_kind, spec.box,
            blur_layer.radius if blur_layer else None,
            bool(fill_layer), fill_layer.opacity if fill_layer else 0.0,
            bool(stroke_layer), stroke_layer.thickness_px if stroke_layer else 0,
            stroke_layer.opacity if stroke_layer else 0.0)
        effect_specs.append(spec)

    return legacy_specs, effect_specs


def draw_legacy_rectangles(background, specs: List[RectangleSpec],
                           reference_side: float):
    """
    在背景上绘制全部 legacy 矩形（背景层之上，原图层之下）

    specs 已按 key 排序：后画覆盖先画。几何与颜色均来自分析阶段，
    绘制端不做任何配置解释。
    """
    result = background
    for spec in specs:
        logger.debug("绘制矩形 %s: %dx%d @ (%d,%d), color=%s, opacity=%.2f",
                     spec.name, spec.box[2], spec.box[3],
                     spec.box[0], spec.box[1],
                     spec.legacy_color, spec.legacy_opacity)
        result = draw_single_rectangle(
            result, spec.box[2], spec.box[3], (spec.box[0], spec.box[1]),
            spec.legacy_color, spec.legacy_opacity,
            spec.legacy_corner_radius, reference_side)
    return result


def draw_effect_stacks(output, specs: List[RectangleSpec],
                       blur_cache, layout_engine):
    """
    绘制全部效果栈矩形（原图上方，decorator 之前）

    specs 已按 key 排序：后画覆盖先画。模糊源一律取自冻结的原图
    卷积缓存（RenderBlurCache），不含任何已绘制的效果栈矩形，
    保证绘制顺序不影响取样（设计文档 §2.2）。
    """
    for spec in specs:
        output = _draw_effect_stack_rectangle(
            output, spec, blur_cache, layout_engine)
    return output


def _draw_effect_stack_rectangle(output, spec: RectangleSpec,
                                 blur_cache, layout_engine):
    """
    单矩形三层效果合成：模糊 → 填充 → 内描边，局部 patch 内混合，
    最后仅经 outer_mask 一次组裁切合成到输出（设计文档 §5.5）。
    """
    from PIL import Image
    cx, cy, clip_w, clip_h = spec.canvas_clip
    bx, by, box_w, box_h = spec.box
    if clip_w <= 0 or clip_h <= 0:
        return output

    # ── 1. 内容底图：模糊 patch 或 underlay patch ──────────
    blur_patch = None
    if spec.blur is not None and blur_cache is not None:
        try:
            if spec.source_kind == 'photo':
                # 照片尺寸模糊层按 box-orig 偏移取局部裁切区域
                orig_x, orig_y = layout_engine.original_bounds[0], \
                    layout_engine.original_bounds[1]
                photo_blur = blur_cache.get_photo_size_blur(
                    spec.blur.radius, saturation=1.0)
                blur_patch = photo_blur.crop((
                    cx - orig_x, cy - orig_y,
                    cx - orig_x + clip_w, cy - orig_y + clip_h))
            else:
                # 跨界/照片外：画布尺寸模糊层按画布坐标裁切
                # （延续背景"原图拉伸到画布"的模糊语义，§4.1）
                canvas_blur = blur_cache.get_canvas_size_blur(
                    spec.blur.radius, saturation=1.0,
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
    if spec.fill is not None:
        fa = spec.fill.opacity
        fill_rgb = np.array(spec.fill.color, dtype=np.float32)
        patch_arr = patch_arr * (1.0 - fa) + fill_rgb * fa

    # ── 3. 描边层：stroke_coverage × stroke_opacity ─────────
    # 内轮廓 = 外轮廓内缩 stroke_px；内圆角 = max(外圆角 - stroke_px, 0)
    if spec.stroke is not None:
        sp = spec.stroke.thickness_px
        inner_w, inner_h = box_w - 2 * sp, box_h - 2 * sp
        inner_corners = tuple(max(r - sp, 0) for r in spec.corner_px)
        if any(r > 0 for r in inner_corners):
            inner_mask = rounded_corner_mask(inner_w, inner_h, *inner_corners)
        else:
            inner_mask = Image.new('L', (inner_w, inner_h), 255)
        # 内覆盖率铺到整矩形坐标系（inner_box 外为 0）
        inner_full = np.zeros((box_h, box_w), dtype=np.float32)
        inner_full[sp:sp + inner_h, sp:sp + inner_w] = np.array(
            inner_mask, dtype=np.float32)
        # stroke_coverage 只描述矩形组内部描边环；外边缘抗锯齿统一
        # 交给最终 outer_mask（防止同一 alpha 被乘两次产生暗边）
        stroke_alpha = (255.0 - inner_full) / 255.0 * spec.stroke.opacity
        stroke_alpha = stroke_alpha[
            cy - by:cy - by + clip_h, cx - bx:cx - bx + clip_w]
        stroke_rgb = np.array(spec.stroke.color, dtype=np.float32)
        patch_arr = patch_arr * (1.0 - stroke_alpha[..., None]) \
            + stroke_rgb * stroke_alpha[..., None]

    # ── 4. 单次组裁切：效果 patch 的 alpha 只经 outer_mask 写入
    #      一次，paste() 不再传 patch 自身 alpha（透明度平方防护）──
    outer_mask_full = rounded_corner_mask(box_w, box_h, *spec.corner_px)
    outer_clip = np.array(outer_mask_full, dtype=np.uint8)[
        cy - by:cy - by + clip_h, cx - bx:cx - bx + clip_w]
    effect_patch = Image.fromarray(
        np.clip(patch_arr, 0, 255).astype(np.uint8), mode='RGB')
    output.paste(effect_patch, (cx, cy), Image.fromarray(outer_clip, mode='L'))
    return output
