"""生成混排上移的可视化对照图，把"体感位移"变成可目视的证据。

配合 remeasure_visual_shift.py 使用。产出三类图：
A. 叠加对比图：纯西文（红）与混排（青）同坐标半透明叠加，位移肉眼可见；
B. 边界标注图：基线 / 墨迹盒 / 重心三类边界同时标注，看三者不一致；
C. 字号缩放图：多字号下位移如何随字号放大（回应"体感不止 7px"）。

只读取生产渲染器输出，不修改任何生产代码或配置。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import patch

import yaml
from PIL import Image, ImageDraw, ImageFont

from src.core.text_renderer import TextRenderer
from src.utils.app_paths import get_app_dir, get_resource_root
from src.utils.font_manager import FontManager
from src.utils.layout_engine import LayoutEngine
from src.utils.render_context import RenderContext

# 与 remeasure_visual_shift.py 保持一致的布局模板（FilmClip custom_text 真实配置）
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
COLORS = {
    'light': {'primary': '#162637', 'secondary': '#3a4a5c'},
    'dark': {'primary': '#f0f0f0', 'secondary': '#c8c8c8'},
}

# 纯西文 = 基准（红）；混排 = 观察对象（青）。两色在叠加时对比强烈。
PURE_RGB = (220, 40, 40)
MIXED_RGB = (0, 150, 190)


def draw_text_raw(draw, xy, content, *args, **kwargs):
    """绕过 hook 的原绘制入口；hook 期间必须用它，否则递归。"""
    return ImageDraw.ImageDraw.text(draw, xy, content, *args, **kwargs)


def render_to_mask(fonts_cfg, text, alignment, image_size):
    """真实渲染一次，返回 custom_text 各段的绘制坐标 + 字体对象（供合成 mask）。"""
    layout = copy.deepcopy(LAYOUT_TEMPLATE)
    layout['custom_text']['alignment'] = alignment
    engine = LayoutEngine(image_size, layout)
    renderer = TextRenderer(FontManager(), engine)

    records = []
    original_text = ImageDraw.ImageDraw.text

    def record(draw, xy, content, *args, **kwargs):
        font = kwargs['font']
        records.append({'xy': list(xy), 'text': content, '_font': font})
        return original_text(draw, xy, content, *args, **kwargs)

    context = RenderContext(image_size, exif_data={
        'focal_length': '50', 'aperture': '2.8',
        'shutter_speed': '1/125', 'iso': '100',
    }, custom_text=text)

    with patch.object(ImageDraw.ImageDraw, 'text', record):
        renderer.render(
            Image.new('RGB', engine.canvas_size, 'white'),
            context, COLORS, fonts_cfg, 'white')

    segments = FontManager.split_mixed_text(text)
    custom = records[-len(segments):] if segments else []
    return custom, engine


def compose_mask(draws, origin, size):
    """按最终坐标把各段合成到灰度 mask（用于提取墨迹盒与重心）。"""
    mask = Image.new('L', size, 0)
    md = ImageDraw.Draw(mask)
    for rec in draws:
        draw_text_raw(md, (rec['xy'][0] - origin[0], rec['xy'][1] - origin[1]),
                      rec['text'], font=rec['_font'], fill=255)
    return mask


def mask_stats(mask):
    """墨迹盒 + 像素重心（相对 mask 坐标）。"""
    bbox = mask.getbbox()
    if not bbox:
        return None
    import numpy as np
    arr = np.asarray(mask.crop(bbox), dtype=np.float64)
    total = arr.sum()
    if total <= 0:
        return None
    h, w = arr.shape
    ys, xs = np.mgrid[0:h, 0:w]
    return {
        'bbox': bbox,
        'gravity': (float((xs * arr).sum() / total) + bbox[0],
                    float((ys * arr).sum() / total) + bbox[1]),
    }


def tint(mask, rgb):
    """把灰度 mask 着色为 RGB 图层（黑底），供半透明叠加。"""
    layer = Image.new('RGB', mask.size, (0, 0, 0))
    solid = Image.new('RGB', mask.size, rgb)
    layer.paste(solid, (0, 0), mask)
    return layer


def diff_compose(p_mask, m_mask):
    """差分合成：位移部分一眼可见。

    像素分类（白底）：
      重叠（两组都有墨）  -> 深灰 #444444（"没动"的共同字形）
      纯西文独有墨迹     -> 红   #cc2828（"混排后离开这里"）
      混排独有墨迹       -> 青   #0096be（"混排后出现在这里"）
    红/青成对错位 = 该字形发生了位移；错开距离即体感位移。
    """
    import numpy as np
    p = np.asarray(p_mask) > 0
    m = np.asarray(m_mask) > 0
    overlap = p & m
    p_only = p & ~m
    m_only = m & ~p
    h, w = p.shape
    out = np.full((h, w, 3), 255, dtype=np.uint8)  # 白底
    out[overlap] = (68, 68, 68)
    out[p_only] = PURE_RGB
    out[m_only] = MIXED_RGB
    return Image.fromarray(out, 'RGB')


def build_overlay_panel(out, fonts_cfg):
    """图 A：纯西文（红）/ 混排（青）同坐标叠加，位移肉眼可见。"""
    image_size = (3000, 2000)
    fsize = 54
    pairs = [('AaBbCc', 'AaBbCc永和九年'), ('AaBbCc', '永和九年')]

    rows = []
    for pure_text, mixed_text in pairs:
        for alignment in ['top-center', 'center', 'bottom-center']:
            pure_draws, engine = render_to_mask(fonts_cfg, pure_text, alignment, image_size)
            mixed_draws, _ = render_to_mask(fonts_cfg, mixed_text, alignment, image_size)

            # 统一原点：取两组绘制坐标最小值，保证同框对照
            xs = [r['xy'][0] for r in pure_draws + mixed_draws]
            ys = [r['xy'][1] for r in pure_draws + mixed_draws]
            origin = (min(xs) - 40, min(ys) - 40)
            # mask 覆盖两组墨迹 + 边距
            size = (fsize * 24, fsize * 4)
            p_mask = compose_mask(pure_draws, origin, size)
            m_mask = compose_mask(mixed_draws, origin, size)
            rows.append({
                'label': f'{alignment} | 红:{pure_text}  青:{mixed_text}',
                'p_mask': p_mask, 'm_mask': m_mask,
                'p_stats': mask_stats(p_mask), 'm_stats': mask_stats(m_mask),
                'origin': origin,
                'baseline_p': pure_draws[0]['xy'][1] + pure_draws[0]['_font'].getmetrics()[0],
                'baseline_m': mixed_draws[0]['xy'][1] + mixed_draws[0]['_font'].getmetrics()[0],
            })

    row_h = fsize * 4 + 30
    panel = Image.new('RGB', (fsize * 24, row_h * len(rows) + 10), '#f4f6fa')
    pd = ImageDraw.Draw(panel)
    font_dir = get_resource_root() / 'assets' / 'fonts'
    label_font = ImageFont.truetype(str(font_dir / 'GlowSansSC-Normal-Regular.otf'), 20)

    for i, row in enumerate(rows):
        y0 = 10 + i * row_h
        pd.text((10, y0), row['label'], font=label_font, fill='#182537')
        # 差分合成：重叠深灰 / 纯西文红 / 混排青，位移成对错位肉眼可见
        base = diff_compose(row['p_mask'], row['m_mask'])
        panel.paste(base, (0, y0 + 28))

        # 辅助线：各自基线（实线）+ 墨迹盒（细框）+ 重心十字
        ox, oy = row['origin']
        for stats, color, tag in ((row['p_stats'], PURE_RGB, 'P'),
                                  (row['m_stats'], MIXED_RGB, 'M')):
            if not stats:
                continue
            bx0, by0, bx1, by1 = stats['bbox']
            gx, gy = stats['gravity']
            # 墨迹盒
            pd.rectangle((bx0, y0 + 28 + by0, bx1, y0 + 28 + by1), outline=color, width=1)
            # 重心十字
            pd.line((gx - 8, y0 + 28 + gy, gx + 8, y0 + 28 + gy), fill=color, width=1)
            pd.line((gx, y0 + 28 + gy - 8, gx, y0 + 28 + gy + 8), fill=color, width=1)
        # 基线（从 mask 坐标换算到面板坐标）
        pd.line((0, y0 + 28 + row['baseline_p'] - oy, panel.width, y0 + 28 + row['baseline_p'] - oy),
                fill=PURE_RGB, width=1)
        pd.line((0, y0 + 28 + row['baseline_m'] - oy, panel.width, y0 + 28 + row['baseline_m'] - oy),
                fill=MIXED_RGB, width=1)

        # 直接标注关键位移数值（体感指标），免去目测
        if row['p_stats'] and row['m_stats']:
            d_top = row['m_stats']['bbox'][1] - row['p_stats']['bbox'][1]
            d_grav = row['m_stats']['gravity'][1] - row['p_stats']['gravity'][1]
            d_base = row['baseline_m'] - row['baseline_p']
            pd.text((panel.width - 430, y0 + 2),
                    f'墨迹盒顶 {d_top:+d}px  重心 {d_grav:+.1f}px  基线 {d_base:+d}px',
                    font=label_font, fill='#182537')

    path = out / 'visual_overlay.png'
    panel.save(path)
    return path


def build_scale_panel(out, fonts_cfg):
    """图 C：多字号下混排 vs 纯西文叠加，看位移如何随字号放大。"""
    rows = []
    for image_size in [(2400, 1600), (3000, 2000), (4000, 3000), (6000, 4000)]:
        fsize = max(12, int(min(image_size) * 0.027))
        pure_draws, _ = render_to_mask(fonts_cfg, 'AaBbCc', 'center', image_size)
        mixed_draws, _ = render_to_mask(fonts_cfg, 'AaBbCc永和九年', 'center', image_size)
        xs = [r['xy'][0] for r in pure_draws + mixed_draws]
        ys = [r['xy'][1] for r in pure_draws + mixed_draws]
        origin = (min(xs) - 40, min(ys) - 40)
        size = (fsize * 24, fsize * 4)
        p_mask = compose_mask(pure_draws, origin, size)
        m_mask = compose_mask(mixed_draws, origin, size)
        p_stats, m_stats = mask_stats(p_mask), mask_stats(m_mask)
        delta_top = m_stats['bbox'][1] - p_stats['bbox'][1] if (p_stats and m_stats) else 0
        p_base = pure_draws[0]['xy'][1] + pure_draws[0]['_font'].getmetrics()[0]
        m_base = mixed_draws[0]['xy'][1] + mixed_draws[0]['_font'].getmetrics()[0]
        rows.append({
            'label': f'字号 {fsize}px (原图 {image_size[0]}x{image_size[1]})',
            'shift_label': f'墨迹盒顶 {delta_top:+d}px = 字号的 {delta_top / fsize * 100:.0f}%  '
                           f'基线 {m_base - p_base:+d}px',
            'p_mask': p_mask, 'm_mask': m_mask, 'fsize': fsize,
        })

    # 缩放到统一高度，便于并排比较
    target_h = 220
    tiles = []
    for row in rows:
        base = diff_compose(row['p_mask'], row['m_mask'])
        bbox = ImageChops_add_bbox(row['p_mask'], row['m_mask'])
        tile = base.crop(bbox) if bbox else base
        scale = target_h / tile.height
        tile = tile.resize((max(1, int(tile.width * scale)), target_h), Image.LANCZOS)
        tiles.append((row['label'], row['shift_label'], tile))

    width = sum(t.width + 20 for _, _, t in tiles) + 20
    panel = Image.new('RGB', (width, target_h + 80), '#f4f6fa')
    pd = ImageDraw.Draw(panel)
    font_dir = get_resource_root() / 'assets' / 'fonts'
    label_font = ImageFont.truetype(str(font_dir / 'GlowSansSC-Normal-Regular.otf'), 18)
    x = 20
    for label, shift_label, tile in tiles:
        panel.paste(tile, (x, 70))
        pd.text((x, 10), label, font=label_font, fill='#182537')
        pd.text((x, 36), shift_label, font=label_font, fill='#8a1f1f')
        x += tile.width + 20
    path = out / 'visual_scale.png'
    panel.save(path)
    return path


def ImageChops_add_bbox(m1, m2):
    """两个 mask 的墨迹盒并集。"""
    b1, b2 = m1.getbbox(), m2.getbbox()
    if not b1:
        return b2
    if not b2:
        return b1
    return (min(b1[0], b2[0]), min(b1[1], b2[1]), max(b1[2], b2[2]), max(b1[3], b2[3]))


def main():
    out = get_app_dir() / 'docs' / 'diagnostics' / 'font_baseline'
    out.mkdir(parents=True, exist_ok=True)
    style_path = (get_resource_root() / 'src' / 'frame_styles' / 'configs'
                  / '胶片夹风格 FilmClip' / 'default.yaml')
    fonts_cfg = yaml.safe_load(style_path.read_text(encoding='utf-8'))['fonts']

    p1 = build_overlay_panel(out, fonts_cfg)
    p2 = build_scale_panel(out, fonts_cfg)
    print(p1)
    print(p2)


if __name__ == '__main__':
    main()
