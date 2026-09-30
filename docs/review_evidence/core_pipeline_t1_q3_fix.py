"""T1（Q3 最小分流修复）的独立验证证据脚本。

从项目根目录激活 venv 后，以绝对路径运行本脚本；直接调用现有实现，
不依赖测试框架。本脚本只写自己的输出 JSON（*_pre.json / *_post.json），
绝不触碰 core_pipeline_reaudit.json 基线。

用法：
    python docs/review_evidence/core_pipeline_t1_q3_fix.py --pre
        修复前运行：采样"必须保持"组基线 + 记录反例当前（缺陷）行为，
        不做修复断言，输出 core_pipeline_t1_q3_fix_pre.json。

    python docs/review_evidence/core_pipeline_t1_q3_fix.py
        修复后运行：保持组逐项与 pre 基线比对（必须完全一致），
        修复组断言预期行为，输出 core_pipeline_t1_q3_fix_post.json。

场景设计对应审计报告 §3 Q3 验收要求：
- 保持组：正常 legacy 矩形、有效效果栈（边框/照片内/跨界）、高斯短路，
  修复前后像素必须逐项一致；
- 修复组：三层关闭（边框可见/被照片覆盖/跨界）、完全在画布外、
  透明填充、逐层非法降级、尺寸不足 1px——其中"三层关闭 + 跨界/边框
  可见"与"0 尺寸崩溃"两组在修复前后存在可观测差异。
"""

import copy
import hashlib
import json
import sys
from pathlib import Path

# 本脚本的运行约定是项目根目录；仅补充模块搜索路径。
sys.path.insert(0, str(Path.cwd()))

from PIL import Image

from src.core.renderer import FrameRenderer, RenderOptions

# 证据文件与本脚本同目录，文件名固定，重复运行覆盖自己的输出。
EVIDENCE_DIR = Path(__file__).resolve().parent
PRE_FILE = EVIDENCE_DIR / 'core_pipeline_t1_q3_fix_pre.json'
POST_FILE = EVIDENCE_DIR / 'core_pipeline_t1_q3_fix_post.json'

# 通用渲染入参：白色背景、禁用 Logo，排除无关图层干扰。
BASE_OPTIONS = dict(bg_fill_type='pure_white', logo_filename='')


def _render(renderer, style):
    """统一渲染入口：100×100 蓝色照片 + 底部扩展 50px 白色边框。"""
    image = Image.new('RGB', (100, 100), 'blue')
    return renderer.render_frame(image, style, options=RenderOptions(**BASE_OPTIONS))


def _style_with_rect(rect_overrides, colors):
    """构造"底部扩展 50px + 单矩形"的样式配置。

    Args:
        rect_overrides: 覆盖 rect_01 定位/三层配置的字段。
        colors: colors 区块（矩形颜色键按需提供）。
    """
    return {
        'layout': {
            'expand_canvas': {'enabled': True, 'bottom': 0.5},
            'rectangles': {'rect_01': dict(rect_overrides)},
        },
        'colors': colors,
    }


def _bytes_digest(img):
    """全图字节摘要：保持组用逐字节一致判定，避免逐点采样的遗漏。"""
    return hashlib.sha256(img.tobytes()).hexdigest()


# ── 保持组：修复前后像素必须完全一致 ──────────────────────────

def keep_legacy_border(renderer):
    """正常 legacy 矩形（未写 fill 键）：仍在原图下方绘制，边框可见。"""
    style = _style_with_rect(
        {'width_ratio': 0.5, 'height_ratio': 0.2,
         'position': 'bottom-center', 'alignment': 'top-center'},
        {'custom_rect_01_light_color': '#FF0000'})
    result = _render(renderer, style)
    return {'pixel_50_110': result.getpixel((50, 110)),
            'digest': _bytes_digest(result)}


def keep_effect_stack_border(renderer):
    """有效效果栈（显式 fill.enabled=true）：原图上方绘制，边框可见。"""
    style = _style_with_rect(
        {'width_ratio': 0.5, 'height_ratio': 0.2,
         'position': 'bottom-center', 'alignment': 'top-center',
         'fill': {'enabled': True}},
        {'custom_rect_01_light_color': '#FF0000'})
    result = _render(renderer, style)
    return {'pixel_50_110': result.getpixel((50, 110)),
            'digest': _bytes_digest(result)}


def keep_effect_stack_in_photo(renderer):
    """有效效果栈完全在照片内部：绘制在原图上方，覆盖照片像素。"""
    style = _style_with_rect(
        {'width_ratio': 0.5, 'height_ratio': 0.2,
         'position': 'center', 'alignment': 'center',
         'fill': {'enabled': True}},
        {'custom_rect_01_light_color': '#FF0000'})
    result = _render(renderer, style)
    return {'pixel_50_50': result.getpixel((50, 50)),
            'digest': _bytes_digest(result)}


def keep_effect_stack_straddle(renderer):
    """有效效果栈跨界（照片内 + 边框各一半）：按画布源绘制在原图上方。

    bottom-center + placement outside + margin_bottom=0.1 → 锚点 y=110，
    alignment bottom-center → 矩形 y∈[90,110]，横跨照片底边。
    """
    style = _style_with_rect(
        {'width_ratio': 0.5, 'height_ratio': 0.2,
         'position': 'bottom-center', 'alignment': 'bottom-center',
         'margin_bottom': 0.1, 'fill': {'enabled': True}},
        {'custom_rect_01_light_color': '#FF0000'})
    result = _render(renderer, style)
    return {'pixel_50_95': result.getpixel((50, 95)),
            'pixel_50_105': result.getpixel((50, 105)),
            'digest': _bytes_digest(result)}


def keep_gaussian_shortcircuit(renderer):
    """高斯背景 + 无画布扩展：短路生效，输出与原图逐字节一致。"""
    image = Image.new('RGB', (16, 16), (50, 80, 110))
    result = renderer.render_frame(
        image, {'layout': {}}, options=RenderOptions(**BASE_OPTIONS))
    return {'digest': _bytes_digest(result)}


# ── 修复组：断言 Q3 修复后的预期行为 ──────────────────────────

def fix_three_layers_off_border(renderer):
    """审计反例本体：三层关闭的效果栈矩形不得回流 legacy 绘制到边框。

    修复前：回流 legacy → (50,110) 红色（缺陷）；
    修复后：不绘制 → (50,110) 白色（边框底色）。
    """
    style = _style_with_rect(
        {'width_ratio': 0.5, 'height_ratio': 0.2,
         'position': 'bottom-center', 'alignment': 'top-center',
         'fill': {'enabled': False}},
        {'custom_rect_01_light_color': '#FF0000'})
    result = _render(renderer, style)
    assert result.getpixel((50, 110)) == (255, 255, 255), \
        f"三层关闭矩形仍出现在边框: {result.getpixel((50, 110))}"
    return {'pixel_50_110': result.getpixel((50, 110))}


def fix_three_layers_off_straddle(renderer):
    """三层关闭 + 跨界矩形：照片内与边框段都不得出现红色。

    修复前：回流 legacy → 先画背景再贴照片，边框段 (50,105) 红色（缺陷）；
    修复后：完全不绘制 → (50,105) 白色；(50,95) 保持照片蓝色。
    """
    style = _style_with_rect(
        {'width_ratio': 0.5, 'height_ratio': 0.2,
         'position': 'bottom-center', 'alignment': 'bottom-center',
         'margin_bottom': 0.1, 'fill': {'enabled': False}},
        {'custom_rect_01_light_color': '#FF0000'})
    result = _render(renderer, style)
    assert result.getpixel((50, 105)) == (255, 255, 255), \
        f"三层关闭跨界矩形的边框段仍被绘制: {result.getpixel((50, 105))}"
    assert result.getpixel((50, 95)) == (0, 0, 255), \
        f"照片区域被意外修改: {result.getpixel((50, 95))}"
    return {'pixel_50_95': result.getpixel((50, 95)),
            'pixel_50_105': result.getpixel((50, 105))}


def fix_three_layers_off_covered(renderer):
    """三层关闭 + 完全在照片内：修复前后像素相同（都被照片盖住），
    保留为回归项防止未来把该情形误改为可见。"""
    style = _style_with_rect(
        {'width_ratio': 0.5, 'height_ratio': 0.2,
         'position': 'center', 'alignment': 'center',
         'fill': {'enabled': False}},
        {'custom_rect_01_light_color': '#FF0000'})
    result = _render(renderer, style)
    assert result.getpixel((50, 50)) == (0, 0, 255), \
        f"照片中心被意外修改: {result.getpixel((50, 50))}"
    return {'pixel_50_50': result.getpixel((50, 50))}


def fix_three_layers_off_outside(renderer):
    """三层关闭 + 完全在画布外：不得回流，输出保持无矩形状态。

    margin_bottom=0.8 → 锚点 y=180，矩形 y∈[160,180]，画布高 150，
    完全在外。修复前会走 legacy paste（被 PIL 裁掉，像素巧合相同），
    修复后根本不进入绘制；本例锁定输出并保证不抛异常。
    """
    style = _style_with_rect(
        {'width_ratio': 0.5, 'height_ratio': 0.2,
         'position': 'bottom-center', 'alignment': 'bottom-center',
         'margin_bottom': 0.8, 'fill': {'enabled': False}},
        {'custom_rect_01_light_color': '#FF0000'})
    result = _render(renderer, style)
    return {'pixel_50_110': result.getpixel((50, 110)),
            'digest': _bytes_digest(result)}


def fix_transparent_fill(renderer):
    """显式 fill.enabled=true 但矩形 opacity=0：填充层降级关闭，
    三层皆无效 → 不绘制（不得借道 legacy 以透明层参与合成）。"""
    style = _style_with_rect(
        {'width_ratio': 0.5, 'height_ratio': 0.2,
         'position': 'bottom-center', 'alignment': 'top-center',
         'opacity': 0, 'fill': {'enabled': True}},
        {'custom_rect_01_light_color': '#FF0000'})
    result = _render(renderer, style)
    assert result.getpixel((50, 110)) == (255, 255, 255), \
        f"透明填充矩形出现可见像素: {result.getpixel((50, 110))}"
    return {'pixel_50_110': result.getpixel((50, 110))}


def fix_fill_color_missing(renderer):
    """fill.enabled=true 但完全缺少颜色配置：填充层非法降级，
    三层皆无效 → 整体跳过且不回流（与 legacy 颜色缺失跳过行为一致）。"""
    style = _style_with_rect(
        {'width_ratio': 0.5, 'height_ratio': 0.2,
         'position': 'bottom-center', 'alignment': 'top-center',
         'fill': {'enabled': True}},
        {})
    result = _render(renderer, style)
    assert result.getpixel((50, 110)) == (255, 255, 255), \
        f"颜色缺失降级后矩形仍可见: {result.getpixel((50, 110))}"
    return {'pixel_50_110': result.getpixel((50, 110))}


def fix_zero_width_no_crash(renderer):
    """尺寸不足 1px（int(ref*ratio)=0）：修复前回流 legacy 会以
    0 宽度构造 PIL 图像（ValueError 崩溃风险）；修复后直接跳过。"""
    style = _style_with_rect(
        {'width_ratio': 0.004, 'height_ratio': 0.2,
         'position': 'bottom-center', 'alignment': 'top-center',
         'fill': {'enabled': False}},
        {'custom_rect_01_light_color': '#FF0000'})
    result = _render(renderer, style)
    assert result.getpixel((50, 110)) == (255, 255, 255), \
        f"0 宽矩形残留可见像素: {result.getpixel((50, 110))}"
    return {'pixel_50_110': result.getpixel((50, 110))}


def _normalize(obj):
    """递归把 tuple 转为 list：与 JSON 反序列化后的 pre 基线同构，
    避免 PIL getpixel 的 tuple 与 JSON list 的类型差异干扰比对。"""
    if isinstance(obj, tuple):
        return [_normalize(v) for v in obj]
    if isinstance(obj, list):
        return [_normalize(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items()}
    return obj


def main():
    renderer = FrameRenderer()

    if '--pre' in sys.argv:
        results = {
            'keep': {
                'legacy_border': keep_legacy_border(renderer),
                'effect_stack_border': keep_effect_stack_border(renderer),
                'effect_stack_in_photo': keep_effect_stack_in_photo(renderer),
                'effect_stack_straddle': keep_effect_stack_straddle(renderer),
                'gaussian_shortcircuit': keep_gaussian_shortcircuit(renderer),
            },
            'fix_probe': {
                # 修复前只记录缺陷行为，不做断言（断言在 post 阶段执行）。
                'three_layers_off_border_pixel': _render(
                    renderer,
                    _style_with_rect(
                        {'width_ratio': 0.5, 'height_ratio': 0.2,
                         'position': 'bottom-center', 'alignment': 'top-center',
                         'fill': {'enabled': False}},
                        {'custom_rect_01_light_color': '#FF0000'}),
                ).getpixel((50, 110)),
                'three_layers_off_straddle_pixel': _render(
                    renderer,
                    _style_with_rect(
                        {'width_ratio': 0.5, 'height_ratio': 0.2,
                         'position': 'bottom-center', 'alignment': 'bottom-center',
                         'margin_bottom': 0.1, 'fill': {'enabled': False}},
                        {'custom_rect_01_light_color': '#FF0000'}),
                ).getpixel((50, 105)),
                'zero_width_error': _probe_zero_width(renderer),
            },
        }
        PRE_FILE.write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8')
        print(json.dumps(results, ensure_ascii=False, indent=2))
        print(f"[pre] 基线已写入 {PRE_FILE.name}")
        return

    # ── post 阶段：修复断言 + 保持组与 pre 基线逐项比对 ──
    pre = json.loads(PRE_FILE.read_text(encoding='utf-8'))
    keep_now = {
        'legacy_border': keep_legacy_border(renderer),
        'effect_stack_border': keep_effect_stack_border(renderer),
        'effect_stack_in_photo': keep_effect_stack_in_photo(renderer),
        'effect_stack_straddle': keep_effect_stack_straddle(renderer),
        'gaussian_shortcircuit': keep_gaussian_shortcircuit(renderer),
    }
    for case, snapshot in keep_now.items():
        assert _normalize(snapshot) == pre['keep'][case], \
            f"保持组行为变化: {case}\npre ={pre['keep'][case]}\npost={snapshot}"

    fix_results = {
        'three_layers_off_border': fix_three_layers_off_border(renderer),
        'three_layers_off_straddle': fix_three_layers_off_straddle(renderer),
        'three_layers_off_covered': fix_three_layers_off_covered(renderer),
        'three_layers_off_outside': fix_three_layers_off_outside(renderer),
        'transparent_fill': fix_transparent_fill(renderer),
        'fill_color_missing': fix_fill_color_missing(renderer),
        'zero_width_no_crash': fix_zero_width_no_crash(renderer),
    }
    results = {'keep': keep_now, 'fix': fix_results}
    POST_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"[post] 保持组与 pre 一致；修复断言全部通过，已写入 {POST_FILE.name}")


def _probe_zero_width(renderer):
    """修复前探测：0 宽效果栈矩形回流 legacy 是否抛 PIL 异常。

    只捕获异常类型作为证据记录，不让脚本整体失败。
    """
    style = _style_with_rect(
        {'width_ratio': 0.004, 'height_ratio': 0.2,
         'position': 'bottom-center', 'alignment': 'top-center',
         'fill': {'enabled': False}},
        {'custom_rect_01_light_color': '#FF0000'})
    try:
        _render(renderer, style)
        return 'no_error'
    except Exception as exc:  # noqa: BLE001 — 证据采集需要记录任意异常类型
        return f'{type(exc).__name__}: {exc}'


if __name__ == '__main__':
    main()
