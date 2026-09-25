"""复测中英混排上移的视觉显著性，检验原诊断数据的适用范围与指标完整性。

背景
----
用户反馈：FilmClip.default 样式自定义文本填入中英混排时，文字明显向上偏移，
体感位移"不止 7px"。原诊断 diagnose_font_baseline.py 存在两个方法论盲点：
1. 只测 3000x2000 原图 / 54px 字号单点，未覆盖用户实际图片尺寸导致的字号变化
   （字号 = max(12, int(min(w, h) * size_ratio))，原图越大字号越大、绝对位移越大）；
2. 核心指标是"混排中西文段基线相对纯西文的位移"（7px），未记录整行墨迹盒与
   视觉重心的变化——人眼感知的"整行文字向上跳"更接近墨迹盒顶/重心位移。

本脚本补充三类证据
------------------
A. 复现原 54px 数据点，确认可重复性（可靠性检验）；
B. 多图片尺寸 x 多字号矩阵，检验位移随字号的缩放规律；
C. 体感指标：整行墨迹盒顶/底/中心、像素重心、横向位移、位移占字号比例。

约束
----
只调用生产渲染器与字体，不修改任何生产代码或配置；输出写入本目录。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont

from src.core.text_renderer import TextRenderer
from src.utils.app_paths import get_app_dir, get_resource_root
from src.utils.font_manager import FontManager
from src.utils.layout_engine import LayoutEngine
from src.utils.render_context import RenderContext

# ── 测试矩阵 ──────────────────────────────────────────────────────────
# 原图尺寸矩阵：覆盖手机/相机常见规格。字号 = max(12, int(min(w,h) * 0.027))。
# (3000, 2000) 是原诊断唯一数据点，作为可重复性基准。
IMAGE_SIZES = [
    (2400, 1600),   # min=1600 -> 43px
    (3000, 2000),   # min=2000 -> 54px（原诊断基准点）
    (4000, 3000),   # min=3000 -> 81px
    (6000, 4000),   # min=4000 -> 108px
    (2000, 3000),   # 竖图 min=2000 -> 54px（验证与横图同字号同位移）
]

# 文本矩阵：纯西文是位移基准；其余检验中英比例与顺序对位移的影响。
TEXTS = [
    'AaBbCc',                # 纯西文基准（所有位移以它为 0 参照）
    'AaBbCc永和九年',        # 原诊断样本：1:1 混排
    '永和九年',              # 纯中文
    'Hello世界',             # 短混排，中文在后
    '世界Hello',             # 短混排，中文在前（检验 ref_font 切换）
    '摄影Photo 2024永和九年',  # 长混排，含数字/空格
]

# 三种对齐：center 是用户主诉场景（FilmClip custom_text 即 alignment: center）。
ALIGNMENTS = ['top-center', 'center', 'bottom-center']

# FilmClip custom_text 的真实布局配置（从 default.yaml 提取，避免每次解析 YAML 依赖）。
# position: top-center + placement 默认 outside -> 锚点 Y = T - margin_top_px
# expand_canvas 上下 0.25 -> T = int(min(w,h) * 0.25)；margin_top 0.11 -> 向外 0.11*min(w,h)
LAYOUT_TEMPLATE = {
    'expand_canvas': {'enabled': True, 'top': 0.25, 'bottom': 0.25, 'left': 0.07, 'right': 0.07},
    'padding': {'top': 0.025, 'bottom': 0.025, 'left': 0.07, 'right': 0.07},
    'custom_text': {
        'enabled': True,
        'position': 'top-center',
        'alignment': 'center',
        'margin_top': 0.11,
        'line_spacing_ratio': 0.006,
    },
}


def ink_box_relative(font: ImageFont.FreeTypeFont, text: str, draw_text=None):
    """测量单段字形相对绘制原点（Pillow 默认 la 锚点）的非零像素范围。

    与 font.getbbox() 区别：getbbox 返回的是字形设计边界（hinting 相关），
    不是严格的非零像素盒；这里用真实栅格化 mask 测量，与人眼看到的墨迹一致。
    返回半开区间 (left, top, right, bottom)，坐标系为图像坐标（向下为正）。

    draw_text: 绘制函数。hook ImageDraw.ImageDraw.text 期间必须传入保存的原函数，
    否则会递归触发 hook（本模块 record() 即如此调用）。
    """
    if draw_text is None:
        draw_text = ImageDraw.ImageDraw.text
    # 离屏 mask 尺寸留足上下左右余量，避免字形被裁切
    mask = Image.new('L', (2400, 800))
    draw_text(ImageDraw.Draw(mask), (100, 300), text, font=font, fill=255)
    bounds = mask.getbbox()
    if not bounds:
        return None
    return (bounds[0] - 100, bounds[1] - 300, bounds[2] - 100, bounds[3] - 300)


def compose_line_ink(draws, draw_text=None):
    """把一条文本的全部绘制段合成到局部 mask，返回整行墨迹盒与像素重心。

    人眼感知的"整行文字位置"由所有字形墨迹的并集决定，而不是单段基线。
    重心以像素灰度为权重（抗锯齿像素权重低），近似视觉重心。

    Parameters
    ----------
    draws : list of dict
        每段含 'xy'（画布坐标绘制原点）、'text'、'_font'（真实字体对象）。
    draw_text : 可选绘制函数；若在 hook 期间调用须传入保存的原函数。

    Returns
    -------
    dict : ink_box(画布坐标包围盒) / gravity(加权重心) / 若空文本返回 None
    """
    if not draws:
        return None
    if draw_text is None:
        draw_text = ImageDraw.ImageDraw.text
    # 第一遍：估算各段墨迹范围，求并集，确定局部 mask 的位置与尺寸
    boxes = []
    for rec in draws:
        rel = ink_box_relative(rec['_font'], rec['text'], draw_text=draw_text)
        if rel is None:
            continue
        x, y = rec['xy']
        boxes.append((x + rel[0], y + rel[1], x + rel[2], y + rel[3]))
    if not boxes:
        return None
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)

    # 第二遍：在局部 mask 上按最终坐标重新绘制，得到真实并集（含段间重叠）
    pad = 2
    mask = Image.new('L', (x1 - x0 + pad * 2, y1 - y0 + pad * 2), 0)
    md = ImageDraw.Draw(mask)
    for rec in draws:
        draw_text(md, (rec['xy'][0] - x0 + pad, rec['xy'][1] - y0 + pad),
                  rec['text'], font=rec['_font'], fill=255)
    bbox = mask.getbbox()
    if not bbox:
        return None

    # 像素重心：arr[y, x] 为灰度，0 表示无墨
    arr = np.asarray(mask.crop(bbox), dtype=np.float64)
    total = arr.sum()
    if total <= 0:
        return None
    h, w = arr.shape
    ys, xs = np.mgrid[0:h, 0:w]
    # 坐标还原：crop 内坐标 -> mask 坐标(+bbox) -> 画布坐标(+origin-pad)。
    # 绘制时内容画在 (xy - origin + pad)，故还原必须减 pad（曾误加，导致绝对坐标多 2*pad）。
    gravity_cx = float((xs * arr).sum() / total) + bbox[0] + x0 - pad
    gravity_cy = float((ys * arr).sum() / total) + bbox[1] + y0 - pad

    return {
        'ink_box': [x0 - pad + bbox[0], y0 - pad + bbox[1],
                    x0 - pad + bbox[2], y0 - pad + bbox[3]],
        'gravity': [gravity_cx, gravity_cy],
    }


def render_case(fonts_cfg, text, alignment, image_size):
    """走真实 TextRenderer.render() 全链路，hook draw.text 记录每段绘制坐标。

    与原诊断同法：不 mock 渲染器内部，只旁路记录，保证测的是生产代码真实行为。
    额外返回整行墨迹统计（原诊断只返回单段 ink_y）。
    """
    layout = copy.deepcopy(LAYOUT_TEMPLATE)
    layout['custom_text']['alignment'] = alignment

    engine = LayoutEngine(image_size, layout)
    renderer = TextRenderer(FontManager(), engine)

    records = []
    original_text = ImageDraw.ImageDraw.text

    def record(draw, xy, content, *args, **kwargs):
        """在执行原绘制之前记录坐标；临时 mask 使用原函数以免递归。"""
        font = kwargs['font']
        ascent, descent = font.getmetrics()
        # 默认锚点 la（左-ascender）：xy[1] 即 ascender 线，基线在其下一个 ascent 处
        baseline = xy[1] + ascent
        # 必须传原函数：此处仍在 hook 内，直接调 ImageDraw.text 会递归
        rel = ink_box_relative(font, content, draw_text=original_text)
        records.append({
            'text': content,
            'font': Path(font.path).name,
            'xy': list(xy),
            'baseline': baseline,
            'metrics': [ascent, descent],
            # 相对绘制原点的墨迹盒，便于横向 bearing 分析
            'ink_rel': rel,
            # 相对基线的墨迹纵向范围（与原诊断 ink_y 口径一致，便于对照）
            'ink_y_rel_baseline': [rel[1] - ascent, rel[3] - ascent] if rel else None,
            '_font': font,
        })
        return original_text(draw, xy, content, *args, **kwargs)

    context = RenderContext(image_size, exif_data={
        'focal_length': '50', 'aperture': '2.8',
        'shutter_speed': '1/125', 'iso': '100',
    }, custom_text=text)

    with patch.object(ImageDraw.ImageDraw, 'text', record):
        renderer.render(
            Image.new('RGB', engine.canvas_size, 'white'),
            context, COLORS, fonts_cfg, 'white')

    # 只保留 custom_text 的绘制记录（FilmClip 底部信息树也会被 hook 捕获）。
    # custom_text 在 render() 中最后绘制，故取末尾 N 段；N = 分段函数给出的段数。
    segments = FontManager.split_mixed_text(text)
    custom_records = records[-len(segments):] if segments else []

    line_stats = compose_line_ink(custom_records, draw_text=original_text)
    box = engine.positions.get('custom_text', {})
    for r in custom_records:
        r.pop('_font', None)

    return {
        'text': text,
        'alignment': alignment,
        'image_size': list(image_size),
        'canvas_size': list(engine.canvas_size),
        'registered_box': box,
        'draws': custom_records,
        'line_ink': line_stats,
    }


# FilmClip 的双色配置（light/dark），这里固定用浅色分支，不影响几何测量。
COLORS = {
    'light': {'primary': '#162637', 'secondary': '#3a4a5c'},
    'dark': {'primary': '#f0f0f0', 'secondary': '#c8c8c8'},
}


def load_style():
    """读取 FilmClip default.yaml 的 fonts 配置，保证字体选择与生产一致。"""
    root = get_resource_root()
    style_path = root / 'src' / 'frame_styles' / 'configs' / '胶片夹风格 FilmClip' / 'default.yaml'
    style = yaml.safe_load(style_path.read_text(encoding='utf-8'))
    return style


def compute_shift(pure, mixed):
    """计算混排相对纯西文的各项位移（正值 = 混排更靠下）。

    体感核心指标：ink_top_shift（墨迹盒顶位移，人眼最先察觉）、
    gravity_shift_y（视觉重心位移）、baseline_shift（原诊断唯一指标）。
    """
    if not pure.get('line_ink') or not mixed.get('line_ink'):
        return None
    p_ink = pure['line_ink']['ink_box']
    m_ink = mixed['line_ink']['ink_box']
    p_g = pure['line_ink']['gravity']
    m_g = mixed['line_ink']['gravity']
    p_base = pure['draws'][0]['baseline'] if pure['draws'] else None
    m_base = next((d['baseline'] for d in mixed['draws'] if d['text'] == 'AaBbCc'), None)
    if m_base is None and mixed['draws']:
        m_base = mixed['draws'][0]['baseline']

    p_top, p_bottom = p_ink[1], p_ink[3]
    m_top, m_bottom = m_ink[1], m_ink[3]
    font_size = pure.get('font_size_px')

    result = {
        # 原诊断指标：西文段基线位移
        'baseline_shift': (m_base - p_base) if (m_base is not None and p_base is not None) else None,
        # 体感指标：整行墨迹盒
        'ink_top_shift': m_top - p_top,
        'ink_bottom_shift': m_bottom - p_bottom,
        'ink_center_shift': ((m_top + m_bottom) - (p_top + p_bottom)) / 2.0,
        'ink_height_pure': p_bottom - p_top,
        'ink_height_mixed': m_bottom - m_top,
        # 体感指标：视觉重心
        'gravity_shift_y': m_g[1] - p_g[1],
        'gravity_shift_x': m_g[0] - p_g[0],
        # 横向：墨迹盒中心位移（居中对齐下文本变宽会带出水平跳动）
        'ink_center_shift_x': ((m_ink[0] + m_ink[2]) - (p_ink[0] + p_ink[2])) / 2.0,
        'ink_width_pure': p_ink[2] - p_ink[0],
        'ink_width_mixed': m_ink[2] - m_ink[0],
    }
    # 位移占字号比例：体感显著性的归一化度量（与字号无关，可跨尺寸比较）
    if font_size:
        result['baseline_shift_ratio'] = (result['baseline_shift'] or 0) / font_size
        result['ink_top_shift_ratio'] = result['ink_top_shift'] / font_size
        result['gravity_shift_ratio'] = result['gravity_shift_y'] / font_size
    return result


def main():
    """执行复测矩阵，输出结构化数据 + Markdown 汇总 + 对照图。"""
    out = get_app_dir() / 'docs' / 'diagnostics' / 'font_baseline'
    out.mkdir(parents=True, exist_ok=True)
    style = load_style()
    fonts_cfg = style['fonts']

    # 预测字号表（与 FontManager.load_font 的字号公式一致），供位移归一化使用
    def font_size_of(image_size, ratio):
        return max(12, int(min(image_size) * ratio))

    size_ratio = fonts_cfg['sizes']['custom_text']  # 0.027

    report = {
        'purpose': '复测混排上移的体感显著性，检验原诊断 7px 单点数据的适用范围',
        'image_sizes': [list(s) for s in IMAGE_SIZES],
        'texts': TEXTS,
        'alignments': ALIGNMENTS,
        'cases': [],
        'shift_table': [],
        'reproducibility': {},
    }

    for image_size in IMAGE_SIZES:
        fsize = font_size_of(image_size, size_ratio)
        for alignment in ALIGNMENTS:
            cases = {}
            for text in TEXTS:
                info = render_case(fonts_cfg, text, alignment, image_size)
                info['font_size_px'] = fsize
                cases[text] = info
                report['cases'].append(info)
            pure = cases['AaBbCc']
            for text in TEXTS[1:]:
                shift = compute_shift(pure, cases[text])
                if shift is None:
                    continue
                entry = {
                    'image_size': list(image_size),
                    'font_size_px': fsize,
                    'alignment': alignment,
                    'text': text,
                }
                entry.update(shift)
                report['shift_table'].append(entry)

    # 可重复性检验：与原诊断 54px / center / AaBbCc永和九年的 7px 对照
    baseline_54 = [e for e in report['shift_table']
                   if e['font_size_px'] == 54 and e['alignment'] == 'center'
                   and e['text'] == 'AaBbCc永和九年']
    report['reproducibility'] = {
        'expected_latin_baseline_shift': -7,
        'measured': baseline_54[0] if baseline_54 else None,
    }

    (out / 'remeasure_visual_shift.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    # ── Markdown 汇总：体感指标为主，原指标为辅 ──────────────────────
    lines = ['# 混排上移体感复测汇总', '',
             '每行 = 一个 (字号, 对齐, 文本) 组合相对纯西文 `AaBbCc` 的位移（px）。',
             '**负值 = 混排更靠上**。`ink_top_shift` 是人眼最先察觉的整行墨迹盒顶位移。',
             '',
             '| 字号 | 对齐 | 文本 | 基线位移(原指标) | 墨迹盒顶 | 墨迹盒底 | 墨迹中心 | 重心Y | 重心X | 占字号(基线) | 占字号(盒顶) |',
             '|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for e in report['shift_table']:
        bs = e.get('baseline_shift')
        lines.append(
            f"| {e['font_size_px']} | {e['alignment']} | {e['text']} "
            f"| {bs if bs is not None else '—'} "
            f"| {e['ink_top_shift']} | {e['ink_bottom_shift']} "
            f"| {e['ink_center_shift']:.1f} | {e['gravity_shift_y']:.1f} "
            f"| {e['gravity_shift_x']:.1f} "
            f"| {e.get('baseline_shift_ratio', 0) * 100:.1f}% "
            f"| {e.get('ink_top_shift_ratio', 0) * 100:.1f}% |")
    (out / 'remeasure_summary.md').write_text('\n'.join(lines), encoding='utf-8')

    print(out / 'remeasure_visual_shift.json')
    print(out / 'remeasure_summary.md')


if __name__ == '__main__':
    main()
