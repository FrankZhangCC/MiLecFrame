"""T5（Q1/Q2/Q8 矩形统一模型重构）的逐像素回归证据脚本。

从项目根目录激活 venv 后运行。重构前后各跑一次：--pre 采样基线，
默认模式逐场景比对 digest（必须全部一致——本重构承诺像素等价）。
只写自己的输出 JSON，不触碰其他审计证据文件。

场景集：
- 内置样式：7 个含矩形的样式 YAML 变体直读渲染（InfoCard 4 变体为
  效果栈、ParamCapsule 2 变体为 fill+stroke 效果栈、FrameBar 为
  legacy 且宽 5×参照边的跨界矩形），各跑浅色/高斯深两种背景；
- 合成边界：legacy/效果栈的可见、跨界、三层关闭、透明填充、颜色
  缺失、0 宽、多矩形混合、半透明重叠、圆角+描边+跨界模糊。
"""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

import yaml
from PIL import Image

from src.core.renderer import FrameRenderer, RenderOptions

EVIDENCE_DIR = Path(__file__).resolve().parent
PRE_FILE = EVIDENCE_DIR / 'core_pipeline_t5_rect_regression_pre.json'
POST_FILE = EVIDENCE_DIR / 'core_pipeline_t5_rect_regression_post.json'

CONFIGS_DIR = Path.cwd() / 'src' / 'frame_styles' / 'configs'


def _digest(img):
    return hashlib.sha256(img.tobytes()).hexdigest()


def _gradient_image(w=600, h=400):
    """横向 R、纵向 G 的渐变图：避免纯色让混合类缺陷隐身。"""
    img = Image.new('RGB', (w, h))
    px = img.load()
    for y in range(h):
        g = y * 255 // (h - 1)
        for x in range(w):
            px[x, y] = (x * 255 // (w - 1), g, 128)
    return img


TEST_IMAGE = None  # 惰性初始化，避免 import 期开销


def _render(renderer, style, bg_type='pure_white'):
    global TEST_IMAGE
    if TEST_IMAGE is None:
        TEST_IMAGE = _gradient_image()
    options = RenderOptions(bg_fill_type=bg_type, logo_filename='')
    return renderer.render_frame(TEST_IMAGE.copy(), style, options=options)


def collect_cases():
    """返回 {场景名: 渲染后的图}；digest 在 main 中统一计算。"""
    renderer = FrameRenderer()
    cases = {}

    # ── 内置样式直读 ──
    style_files = sorted(
        p for p in CONFIGS_DIR.glob('*/*.yaml') if p.name != '_STYLE_TEMPLATE.txt')
    for path in style_files:
        with open(path, 'r', encoding='utf-8') as f:
            style = yaml.safe_load(f)
        if not isinstance(style, dict) or 'rectangles' not in (
                style.get('layout') or {}):
            continue
        label = path.parent.name + '/' + path.stem
        cases[f'builtin::{label}::white'] = _render(renderer, style)
        cases[f'builtin::{label}::gaussian'] = _render(
            renderer, style, 'gaussian_black_65')

    # ── 合成边界：与 T1 场景同源，另补混合/重叠/模糊跨界 ──
    def rect_style(rects, colors, expand=None):
        layout = {'rectangles': rects}
        if expand:
            layout['expand_canvas'] = {'enabled': True, **expand}
        return {'layout': layout, 'colors': colors}

    base_expand = {'bottom': 0.5}
    red = {'custom_rect_01_light_color': '#FF0000'}
    blue = {'custom_rect_02_light_color': '#0000FF'}

    scene_legacy = rect_style(
        {'rect_01': {'width_ratio': 0.5, 'height_ratio': 0.2,
                     'position': 'bottom-center', 'alignment': 'top-center'}},
        red, base_expand)
    cases['edge::legacy_border'] = _render(renderer, scene_legacy)

    scene_effect = rect_style(
        {'rect_01': {'width_ratio': 0.5, 'height_ratio': 0.2,
                     'position': 'bottom-center', 'alignment': 'top-center',
                     'fill': {'enabled': True}}},
        red, base_expand)
    cases['edge::effect_border'] = _render(renderer, scene_effect)

    scene_off_straddle = rect_style(
        {'rect_01': {'width_ratio': 0.5, 'height_ratio': 0.2,
                     'position': 'bottom-center', 'alignment': 'bottom-center',
                     'margin_bottom': 0.1, 'fill': {'enabled': False}}},
        red, base_expand)
    cases['edge::off_straddle'] = _render(renderer, scene_off_straddle)

    scene_transparent = rect_style(
        {'rect_01': {'width_ratio': 0.5, 'height_ratio': 0.2,
                     'position': 'bottom-center', 'alignment': 'top-center',
                     'opacity': 0, 'fill': {'enabled': True}}},
        red, base_expand)
    cases['edge::transparent_fill'] = _render(renderer, scene_transparent)

    scene_nocolor = rect_style(
        {'rect_01': {'width_ratio': 0.5, 'height_ratio': 0.2,
                     'position': 'bottom-center', 'alignment': 'top-center',
                     'fill': {'enabled': True}}},
        {}, base_expand)
    cases['edge::fill_color_missing'] = _render(renderer, scene_nocolor)

    scene_zerow = rect_style(
        {'rect_01': {'width_ratio': 0.004, 'height_ratio': 0.2,
                     'position': 'bottom-center', 'alignment': 'top-center',
                     'fill': {'enabled': False}}},
        red, base_expand)
    cases['edge::zero_width'] = _render(renderer, scene_zerow)

    # 混合：legacy（红）与效果栈（蓝）重叠；legacy 先画（背景层），
    # 效果栈后画（原图上方）
    scene_mixed = rect_style(
        {'rect_01': {'width_ratio': 0.5, 'height_ratio': 0.2,
                     'position': 'bottom-center', 'alignment': 'top-center'},
         'rect_02': {'width_ratio': 0.3, 'height_ratio': 0.1,
                     'position': 'bottom-center', 'alignment': 'top-center',
                     'fill': {'enabled': True}, 'opacity': 0.5}},
        {**red, **blue}, base_expand)
    cases['edge::mixed_overlap'] = _render(renderer, scene_mixed)

    # 半透明重叠：两个效果栈矩形相互叠压（逐次合成顺序敏感）
    scene_overlap = rect_style(
        {'rect_01': {'width_ratio': 0.4, 'height_ratio': 0.15,
                     'position': 'bottom-center', 'alignment': 'top-center',
                     'fill': {'enabled': True}, 'opacity': 0.5},
         'rect_02': {'width_ratio': 0.4, 'height_ratio': 0.15,
                     'position': 'bottom-center', 'alignment': 'center',
                     'fill': {'enabled': True}, 'opacity': 0.5}},
        {**red, **blue}, base_expand)
    cases['edge::effect_overlap'] = _render(renderer, scene_overlap)

    # 圆角 + 描边 + 跨界模糊：canvas 源 blur 路径与内外圆角
    scene_rich = rect_style(
        {'rect_01': {'width_ratio': 0.6, 'height_ratio': 0.3,
                     'position': 'bottom-center', 'alignment': 'center',
                     'corner_radius': {'top_left': 0.02, 'top_right': 0.02,
                                       'bottom_left': 0.02, 'bottom_right': 0.02},
                     'fill': {'enabled': True}, 'opacity': 0.6,
                     'stroke': {'enabled': True, 'radius_ratio': 0.004,
                                'opacity': 0.9},
                     'gaussian_blur': {'enabled': True, 'radius': 60}}},
        {**red, **blue}, base_expand)
    cases['edge::rounded_stroke_blur'] = _render(renderer, scene_rich)

    return cases


def main():
    cases = collect_cases()
    digests = {name: _digest(img) for name, img in sorted(cases.items())}

    if '--pre' in sys.argv:
        PRE_FILE.write_text(
            json.dumps(digests, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8')
        print(f"[pre] {len(digests)} 个场景基线已写入 {PRE_FILE.name}")
        return

    pre = json.loads(PRE_FILE.read_text(encoding='utf-8'))
    missing = set(pre) - set(digests)
    assert not missing, f"post 缺少场景: {sorted(missing)}"
    changed = {name: (pre[name], digests[name])
               for name in sorted(pre) if pre[name] != digests[name]}
    assert not changed, \
        "像素回归失败（重构必须等价）:\n" + "\n".join(
            f"  {n}: pre={p[:12]}… post={q[:12]}…" for n, (p, q) in changed.items())
    POST_FILE.write_text(
        json.dumps(digests, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print(f"[post] 全部 {len(digests)} 个场景逐像素一致，已写入 {POST_FILE.name}")


if __name__ == '__main__':
    main()
