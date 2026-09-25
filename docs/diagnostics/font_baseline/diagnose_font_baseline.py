"""生成混排基线诊断证据；只调用现有渲染器，不修改应用配置或字体。

从项目根运行，先激活 venv，并将项目根加入 PYTHONPATH。
输出字体度量、真实绘制坐标、对照图和独立日志到 docs/diagnostics/font_baseline。
"""

import copy
import hashlib
import json
import logging
from pathlib import Path
from unittest.mock import patch

import PIL
import yaml
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from PIL import Image, ImageChops, ImageDraw, ImageFont, features

from src.core.text_renderer import TextRenderer
from src.utils.app_paths import get_app_dir, get_resource_root
from src.utils.font_manager import FontManager
from src.utils.layout_engine import LayoutEngine
from src.utils.render_context import RenderContext


def ink_bounds(font, text):
    """读取实际非零像素范围；返回相对于基线原点的半开区间边界。"""
    mask = Image.new('L', (1800, 500))
    ImageDraw.Draw(mask).text((30, 250), text, font=font, fill=255, anchor='ls')
    bounds = mask.getbbox()
    return [bounds[0] - 30, bounds[1] - 250,
            bounds[2] - 30, bounds[3] - 250] if bounds else None


def measure_fonts(font_dir):
    """记录字体身份、字体表、字形轮廓以及多字号的真实像素度量。"""
    result = []
    for family, weights in [('Gotham', ['Light', 'Book', 'Medium']),
                            ('GlowSansSC-Normal', ['Light', 'Regular', 'Medium'])]:
        for weight in weights:
            path = font_dir / f'{family}-{weight}.otf'
            with TTFont(path) as tt:
                glyphs = tt.getGlyphSet()
                cmap = tt.getBestCmap()
                outlines = {}
                for char in 'AaBbCc永和九年国口田gypq':
                    if ord(char) in cmap:
                        pen = BoundsPen(glyphs)
                        glyphs[cmap[ord(char)]].draw(pen)
                        outlines[char] = pen.bounds
                item = {
                    'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    'upem': tt['head'].unitsPerEm,
                    'hhea': [tt['hhea'].ascent, tt['hhea'].descent, tt['hhea'].lineGap],
                    'typo': [tt['OS/2'].sTypoAscender, tt['OS/2'].sTypoDescender,
                             tt['OS/2'].sTypoLineGap],
                    'win': [tt['OS/2'].usWinAscent, tt['OS/2'].usWinDescent],
                    'outlines_y_up': outlines, 'sizes': {},
                }
            for size in [12, 27, 54, 81, 100]:
                font = ImageFont.truetype(str(path), size)
                samples = ['AaBbCc', 'gypq'] if family == 'Gotham' else ['永和九年', '永', '和', '九', '年', '国口田', '，。']
                item['sizes'][size] = {
                    'metrics': font.getmetrics(),
                    'samples': {text: {'bbox_ls': font.getbbox(text, anchor='ls'),
                                       'ink_ls': ink_bounds(font, text),
                                       'advance': font.getlength(text)} for text in samples},
                }
            result.append(item)
    return result


def render_case(style, text, alignment=None, multiline=False):
    """调用生产 TextRenderer，并旁路记录每次 draw.text 的基线和像素包围盒。"""
    layout = copy.deepcopy(style['layout'])
    if alignment:
        layout['custom_text']['alignment'] = alignment
    if multiline:
        # custom_text 会主动消除换行；通过 defined_texts 验证真实多行分支。
        layout['custom_text']['enabled'] = False
        layout['info_position'] = {}
        layout['defined_texts'] = {'probe': {
            'content': text, 'position': 'top-center', 'alignment': 'top-center',
            'margin_top': 0.11, 'line_spacing_ratio': 0.006,
        }}
        style = copy.deepcopy(style)
        style['fonts']['sizes']['probe'] = 0.027
    engine = LayoutEngine((3000, 2000), layout)
    renderer = TextRenderer(FontManager(), engine)
    records = []
    original_text = ImageDraw.ImageDraw.text

    def record(draw, xy, content, *args, **kwargs):
        """在执行原绘制之前记录坐标；临时 mask 使用原函数以免递归。"""
        font = kwargs['font']
        ascent, descent = font.getmetrics()
        baseline = xy[1] + ascent
        mask = Image.new('L', (1800, 500))
        original_text(ImageDraw.Draw(mask), (30, 250), content,
                      font=font, fill=255, anchor='ls')
        bounds = mask.getbbox()
        records.append({
            'text': content, 'font': Path(font.path).name, 'xy': xy,
            'baseline': baseline, 'metrics': [ascent, descent],
            'ink_y': [baseline + bounds[1] - 250, baseline + bounds[3] - 250] if bounds else None,
        })
        return original_text(draw, xy, content, *args, **kwargs)

    with patch.object(ImageDraw.ImageDraw, 'text', record):
        output = renderer.render(
            Image.new('RGB', engine.canvas_size, 'white'),
            # 提供完整的最小 EXIF，满足 FilmClip 底部信息树的引用关系。
            RenderContext((3000, 2000), exif_data={
                'focal_length': '50', 'aperture': '2.8',
                'shutter_speed': '1/125', 'iso': '100',
            }, custom_text=text),
            style['colors'], style['fonts'], 'white')
    key = 'probe' if multiline else 'custom_text'
    info = {'text': text, 'alignment': alignment or 'center',
            'box': engine.positions[key], 'draws': records}
    return output, info


def main():
    """收集可重复的诊断数据，并为报告输出两张对照图。"""
    out = get_app_dir() / 'docs' / 'diagnostics' / 'font_baseline'
    out.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=out / 'diagnostic.txt', filemode='w',
                        level=logging.DEBUG, encoding='utf-8',
                        format='%(levelname)s %(name)s %(message)s')
    font_dir = get_resource_root() / 'assets' / 'fonts'
    style_path = get_resource_root() / 'src' / 'frame_styles' / 'configs' / '胶片夹风格 FilmClip' / 'default.yaml'
    style = yaml.safe_load(style_path.read_text(encoding='utf-8'))
    report = {'pillow': PIL.__version__, 'freetype': features.version('freetype2'),
              'fonts': measure_fonts(font_dir), 'cases': [], 'multiline': []}
    # 所有对照使用同一画布/锚点，截图不做垂直重定位。
    panel = Image.new('RGB', (1300, 680), '#f4f6fa')
    pd = ImageDraw.Draw(panel)
    label_font = ImageFont.truetype(str(font_dir / 'GlowSansSC-Normal-Regular.otf'), 22)
    texts = ['AaBbCc', 'AaBbCc永和九年', '永和九年']
    for alignment in ['top-center', 'center', 'bottom-center']:
        for text in texts:
            output, info = render_case(style, text, alignment)
            report['cases'].append(info)
            if alignment == 'center':
                idx = texts.index(text)
                y = 65 + idx * 200
                pd.text((24, y - 40), f'{text}  |  字号 54 px  |  实际 FilmClip default',
                        font=label_font, fill='#182537')
                crop = output.crop((1060, 205, 2360, 355))
                panel.paste(crop, (0, y))
                # 青色表示注册布局盒，红色表示实际基线，灰色表示公共锚点。
                box = info['box']
                pd.rectangle((box['x'] - 1060, y + box['y'] - 205,
                              box['x'] - 1060 + box['width'],
                              y + box['y'] - 205 + box['height']), outline='#0099bb')
                custom_draws = [d for d in info['draws'] if d['text'] in texts or d['text'] == '永和九年']
                base = custom_draws[0]['baseline']
                pd.line((250, y + base - 205, 1050, y + base - 205), fill='#dc5555')
                pd.line((1120, y + 280 - 205, 1240, y + 280 - 205), fill='#888888', width=3)
    panel.save(out / 'filmclip_comparison.png')
    for text in ['AaBbCc\n永和九年', '永和九年\nAaBbCc',
                 'AaBbCc\nAaBbCc永和九年', 'AaBbCc\n\nAaBbCc']:
        _, info = render_case(style, text, multiline=True)
        report['multiline'].append(info)
    # 100px 放大演示共同基线与候选光学修正；候选方案不写入生产代码。
    visual = Image.new('RGB', (1450, 450), 'white')
    vd = ImageDraw.Draw(visual)
    latin = ImageFont.truetype(str(font_dir / 'Gotham-Medium.otf'), 100)
    cjk = ImageFont.truetype(str(font_dir / 'GlowSansSC-Normal-Medium.otf'), 100)
    correction = latin.getbbox('H', anchor='ls')[3] - cjk.getbbox('永和九年', anchor='ls')[3]
    for idx, shift in enumerate([0, correction]):
        base = 170 + idx * 210
        vd.text((30, base - 135), '当前：共同基线' if idx == 0 else f'候选：中文光学上移 {-shift}px（仅演示）',
                font=label_font, fill='#182537')
        vd.line((30, base, 1400, base), fill='#dc5555')
        vd.text((40, base), 'AaBbCc', font=latin, fill='#162637', anchor='ls')
        vd.text((40 + latin.getlength('AaBbCc'), base + shift), '永和九年',
                font=cjk, fill='#162637', anchor='ls')
    visual.save(out / 'baseline_optical_comparison.png')
    report['demonstration_cjk_shift_100px'] = correction
    # 用逐像素比较确认旧写法确实共享基线，避免把字体形状误判为减 ascent 错误。
    checks = []
    for font, text in [(latin, 'AaBbCc'), (cjk, '永和九年')]:
        old = Image.new('L', (1200, 400))
        explicit = Image.new('L', old.size)
        ImageDraw.Draw(old).text((30, 200 - font.getmetrics()[0]), text, font=font, fill=255)
        ImageDraw.Draw(explicit).text((30, 200), text, font=font, fill=255, anchor='ls')
        assert ImageChops.difference(old, explicit).getbbox() is None
        checks.append(f'{Path(font.path).name}: implicit la == explicit ls')
    # 检查相同西文段的位置差，排除“中文更高导致主观错觉”的解释。
    for index, expected in [(0, 0), (3, -7), (6, -14)]:
        pure, mixed = report['cases'][index:index + 2]
        pure_draw = next(d for d in pure['draws'] if d['text'] == 'AaBbCc')
        mixed_draw = next(d for d in mixed['draws'] if d['text'] == 'AaBbCc')
        assert mixed_draw['baseline'] - pure_draw['baseline'] == expected
        assert mixed_draw['ink_y'][0] - pure_draw['ink_y'][0] == expected
        checks.append(f"{pure['alignment']}: Latin shift = {expected}px")
    report['checks_passed'] = checks
    (out / 'measurements.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    logging.info('诊断完成：%s', out)
    print(out)


if __name__ == '__main__':
    main()
