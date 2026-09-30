"""T4（Q6 Logo 匹配上下文收敛）的独立验证证据脚本。

从项目根目录激活 venv 后运行；直接调用现有实现，不依赖测试框架。
只写自己的输出 JSON（*_pre.json / *_post.json）。

用法：
    python docs/review_evidence/core_pipeline_t4_logo_context_fix.py --pre
    python docs/review_evidence/core_pipeline_t4_logo_context_fix.py

验证内容：
- 品牌来源调查（§2 待定事项）：camera_map.csv 的 mapped_brand 是否
  与 original_brand 恒等；原始 EXIF 品牌（strip/lower）与 RenderContext
  显示品牌在各样本上经真实 auto_match_logo 的匹配结果是否一致。
  结论随 JSON 留档，作为"统一品牌来源不产生匹配差异"的依据。
- 保持组：三态端到端输出 digest（无样式背景覆盖时 renderer 自动路径
  未变）；固定/禁用语义不受上游收敛影响。
- 行为修复：样式覆盖背景时，自动模式按最终背景（而非用户所选背景）
  选择明暗变体——这是 Q6 的预期行为变化，不是像素回归。
"""

import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from PIL import Image

from src.core.batch_processor import BatchProcessor
from src.core.renderer import FrameRenderer, RenderMetadata, RenderOptions
from src.utils.app_paths import get_app_dir
from src.utils.background_fill import BackgroundFillManager
from src.utils.exif_helper import ExifHelper
from src.utils.logo_selector import LogoSelector
from src.utils.render_context import RenderContext

EVIDENCE_DIR = Path(__file__).resolve().parent
PRE_FILE = EVIDENCE_DIR / 'core_pipeline_t4_logo_context_fix_pre.json'
POST_FILE = EVIDENCE_DIR / 'core_pipeline_t4_logo_context_fix_post.json'

BASE_OPTIONS = dict(logo_filename=None)


def _digest(img):
    return hashlib.sha256(img.tobytes()).hexdigest()


def _metadata(make):
    return RenderMetadata(exif_data={'camera_make': make,
                                     'camera_model': 'R6'})


def _logo_style(bg_override=None):
    style = {'logo': {'enabled': True, 'position': 'top-right',
                      'alignment': 'top-right', 'margin_right': 0.03,
                      'margin_top': 0.03, 'size_ratio': 0.1}}
    if bg_override:
        style['colors'] = {'custom_bg_color': bg_override,
                           'custom_bg_text_scheme': 'dark'}
    return style


def keep_auto_end_to_end(renderer):
    """无样式背景覆盖：自动模式输出与 T3 基线同场景同值。"""
    options = RenderOptions(bg_fill_type='pure_white')
    result = renderer.render_frame(
        Image.new('RGB', (400, 300), 'white'), _logo_style(),
        metadata=_metadata('Canon'), options=options)
    return {'digest': _digest(result)}


def keep_fixed_end_to_end(renderer):
    options = RenderOptions(bg_fill_type='pure_white',
                            logo_filename='Canon_logo_black.png')
    result = renderer.render_frame(
        Image.new('RGB', (400, 300), 'white'), _logo_style(),
        metadata=_metadata('Canon'), options=options)
    return {'digest': _digest(result)}


def keep_disabled_end_to_end(renderer):
    options = RenderOptions(bg_fill_type='pure_white', logo_filename='')
    result = renderer.render_frame(
        Image.new('RGB', (400, 300), 'white'), _logo_style(),
        metadata=_metadata('Canon'), options=options)
    return {'digest': _digest(result)}


class RecordingSelector:
    """替身选择器：只记录调用，返回固定文件以便观测绘制端。"""

    def __init__(self):
        self.calls = []

    def auto_match_logo(self, brand, is_dark_bg=None):
        self.calls.append((brand, is_dark_bg))
        return 'Canon_logo_black.png' if not is_dark_bg else 'Canon_logo_white.png'


def survey_brand_sources():
    """品牌来源调查：映射表恒等性 + 两种来源的匹配结果比对。"""
    # 1) 映射表 brand 列恒等性（决定"映射后品牌"是否可能偏离原始品牌；
    #    用 list 存储以保持 JSON 往返后可比较）
    csv_path = get_app_dir() / 'data' / 'camera_map.csv'
    brand_rows = 0
    brand_changed = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            brand_rows += 1
            if row['original_brand'].strip() != row['mapped_brand'].strip():
                brand_changed.append(
                    [row['original_brand'], row['mapped_brand']])
    # 2) 两种来源经真实选择器的匹配结果（样本覆盖 logos 目录全部品牌）
    selector = LogoSelector()
    exif_helper = ExifHelper()
    samples = ['Canon', 'Nikon', 'Apple', 'Hasselblad', 'Sony',
               'Fujifilm', 'Leica', 'ricoh', 'DJI']
    per_brand = {}
    for brand in samples:
        exif = {'camera_make': brand, 'camera_model': 'X'}
        raw_source = exif_helper.get_camera_brand(exif)  # strip/lower
        context = RenderContext((100, 100), exif)
        display_source = context.get_text('camera_make')
        display_lower = display_source.lower() if display_source else None
        matches = {
            'raw': selector.auto_match_logo(raw_source, is_dark_bg=False),
            'display': selector.auto_match_logo(display_lower,
                                                is_dark_bg=False),
        }
        per_brand[brand] = {
            'raw_source': raw_source, 'display_source': display_source,
            'match_light': matches,
            'consistent': matches['raw'] == matches['display'],
        }
    return {'csv_rows': brand_rows,
            'mapped_brand_changed': brand_changed,
            'mapped_brand_always_identical': not brand_changed,
            'per_brand': per_brand,
            'all_consistent': all(v['consistent']
                                  for v in per_brand.values())}


def probe_style_override(renderer, selector):
    """样式覆盖背景场景：自动模式应按最终背景选明暗变体。

    用户选择纯白背景（bg_fill_type），样式 custom_bg_color 覆盖为黑色：
    - 修复前的上游预匹配路径：按 pure_white 选 black 变体并固定传入，
      渲染器收到非空文件名不再按最终黑背景改选 → 黑底配黑 Logo（错）；
    - 修复后（上游传 None）：渲染器按最终黑背景选 white 变体（对）。
    """
    renderer._logo_selector = selector
    drawn = []
    renderer._add_logo = (
        lambda image, filename, config, engine:
        drawn.append(filename) or image)
    options = RenderOptions(bg_fill_type='pure_white')  # 上游"自动"= None
    renderer.render_frame(
        Image.new('RGB', (400, 300), 'white'),
        _logo_style(bg_override='#000000'),
        metadata=_metadata('Canon'), options=options)
    return {'selector_calls': selector.calls, 'drawn_files': drawn}


def probe_legacy_upstream_preselect(renderer):
    """修复前上游预匹配路径的对照演示（仅记录，不断言为正确行为）：
    按用户白背景预选 black 固定传入 + 样式覆盖黑背景 → 绘制 black。"""
    drawn = []
    renderer._add_logo = (
        lambda image, filename, config, engine:
        drawn.append(filename) or image)
    real_selector = LogoSelector()
    preselected = real_selector.auto_match_logo(
        'canon', is_dark_bg=BackgroundFillManager.is_dark_bg('pure_white'))
    options = RenderOptions(bg_fill_type='pure_white',
                            logo_filename=preselected)
    renderer.render_frame(
        Image.new('RGB', (400, 300), 'white'),
        _logo_style(bg_override='#000000'),
        metadata=_metadata('Canon'), options=options)
    return {'preselected_by_upstream': preselected, 'drawn_files': drawn}


def main():
    renderer = FrameRenderer()

    if '--pre' in sys.argv:
        results = {
            'keep': {
                'auto_end_to_end': keep_auto_end_to_end(renderer),
                'fixed_end_to_end': keep_fixed_end_to_end(renderer),
                'disabled_end_to_end': keep_disabled_end_to_end(renderer),
            },
            'survey': survey_brand_sources(),
            'fix_probe': {
                'legacy_upstream_preselect':
                    probe_legacy_upstream_preselect(renderer),
            },
        }
        PRE_FILE.write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8')
        print(json.dumps(results, ensure_ascii=False, indent=2))
        print(f"[pre] 基线已写入 {PRE_FILE.name}")
        return

    pre = json.loads(PRE_FILE.read_text(encoding='utf-8'))

    keep_now = {
        'auto_end_to_end': keep_auto_end_to_end(renderer),
        'fixed_end_to_end': keep_fixed_end_to_end(renderer),
        'disabled_end_to_end': keep_disabled_end_to_end(renderer),
    }
    for case, snapshot in keep_now.items():
        assert snapshot == pre['keep'][case], \
            f"保持组行为变化: {case}\npre ={pre['keep'][case]}\npost={snapshot}"

    # 品牌来源调查必须复现一致结论
    survey = survey_brand_sources()
    assert survey == pre['survey'], "品牌来源调查结果与基线不一致"

    # 批处理器不再持有选择器（决策收敛到渲染器）
    assert not hasattr(BatchProcessor(), 'logo_selector'), \
        "BatchProcessor 仍持有 LogoSelector（预匹配未移除）"

    # 行为修复断言：样式覆盖背景时按最终背景（dark → white 变体）匹配
    fix = probe_style_override(renderer, RecordingSelector())
    assert fix['selector_calls'] == [('canon', True)], \
        f"自动匹配未按最终黑背景执行: {fix['selector_calls']}"
    assert fix['drawn_files'] == ['Canon_logo_white.png'], \
        f"样式覆盖黑背景时未选用白色变体: {fix['drawn_files']}"
    legacy = pre['fix_probe']['legacy_upstream_preselect']
    assert legacy['preselected_by_upstream'] != fix['drawn_files'][0], \
        "预期差异消失：上游预选与渲染器匹配结果意外相同"

    results = {'keep': keep_now, 'survey_consistent': True, 'fix': fix,
               'legacy_demo': legacy}
    POST_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"[post] 保持组与调查结论一致；样式覆盖背景行为修复通过，"
          f"已写入 {POST_FILE.name}")


if __name__ == '__main__':
    main()
