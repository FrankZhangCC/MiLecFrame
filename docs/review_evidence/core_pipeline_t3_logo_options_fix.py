"""T3（Q5 停止回写 options）的独立验证证据脚本。

从项目根目录激活 venv 后，以绝对路径运行本脚本；直接调用现有实现，
不依赖测试框架。本脚本只写自己的输出 JSON（*_pre.json / *_post.json）。

用法：
    python docs/review_evidence/core_pipeline_t3_logo_options_fix.py --pre
        修复前运行：采样三态端到端输出基线 + 记录回写缺陷行为。

    python docs/review_evidence/core_pipeline_t3_logo_options_fix.py
        修复后运行：端到端输出与 pre 基线逐字节比对（正常单帧输出
        不变），断言 options 不再被回写、复用 options 时逐帧重选。

场景对应审计报告 §3 Q5 验收要求：相同 options 连续渲染不同品牌和
不同有效背景每帧自动重选；调用前后 options 字段不变；禁用不自动
匹配；固定文件不被重选；正常单帧输出不变。
"""

import dataclasses
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from PIL import Image

from src.core.renderer import FrameRenderer, RenderMetadata, RenderOptions

EVIDENCE_DIR = Path(__file__).resolve().parent
PRE_FILE = EVIDENCE_DIR / 'core_pipeline_t3_logo_options_fix_pre.json'
POST_FILE = EVIDENCE_DIR / 'core_pipeline_t3_logo_options_fix_post.json'


def _digest(img):
    return hashlib.sha256(img.tobytes()).hexdigest()


def _metadata(brand):
    """构造带相机品牌的渲染元数据（走真实 RenderContext/显示链）。"""
    return RenderMetadata(exif_data={'camera_make': brand,
                                     'camera_model': 'R6'})


class RecordingSelector:
    """替身选择器：记录 auto_match_logo 调用，文件名按明暗固定映射。"""

    def __init__(self):
        self.calls = []

    def auto_match_logo(self, brand, is_dark_bg=None):
        self.calls.append((brand, is_dark_bg))
        return 'Canon_logo_black.png' if not is_dark_bg else 'Canon_logo_white.png'


# ── 保持组：真实端到端输出，修复前后逐字节一致 ────────────────

def keep_auto_end_to_end(renderer):
    """自动模式单帧：真实匹配 + 真实 Logo 绘制，输出为验收基线。"""
    options = RenderOptions(bg_fill_type='pure_white')
    result = renderer.render_frame(
        Image.new('RGB', (400, 300), 'white'),
        {'logo': {'enabled': True, 'position': 'top-right',
                  'alignment': 'top-right', 'margin_right': 0.03,
                  'margin_top': 0.03, 'size_ratio': 0.1}},
        metadata=_metadata('Canon'), options=options)
    return {'digest': _digest(result),
            'options_logo_after': options.logo_filename}


def keep_fixed_end_to_end(renderer):
    """固定文件模式：绘制路径与自动模式命中同名文件时完全一致。"""
    options = RenderOptions(bg_fill_type='pure_white',
                            logo_filename='Canon_logo_black.png')
    result = renderer.render_frame(
        Image.new('RGB', (400, 300), 'white'),
        {'logo': {'enabled': True, 'position': 'top-right',
                  'alignment': 'top-right', 'margin_right': 0.03,
                  'margin_top': 0.03, 'size_ratio': 0.1}},
        metadata=_metadata('Canon'), options=options)
    return {'digest': _digest(result),
            'options_logo_after': options.logo_filename}


def keep_disabled_end_to_end(renderer):
    """禁用模式（空串哨兵）：不匹配、不绘制，输出无 Logo。"""
    options = RenderOptions(bg_fill_type='pure_white', logo_filename='')
    result = renderer.render_frame(
        Image.new('RGB', (400, 300), 'white'),
        {'logo': {'enabled': True, 'position': 'top-right',
                  'alignment': 'top-right', 'margin_right': 0.03,
                  'margin_top': 0.03, 'size_ratio': 0.1}},
        metadata=_metadata('Canon'), options=options)
    return {'digest': _digest(result),
            'options_logo_after': options.logo_filename}


def _logo_style():
    return {'logo': {'enabled': True, 'position': 'top-right',
                     'alignment': 'top-right', 'margin_right': 0.03,
                     'margin_top': 0.03, 'size_ratio': 0.1}}


# ── 缺陷探针 / 修复断言共用的行为采样 ─────────────────────────

def probe_options_reuse(renderer, selector):
    """同一 options 连续渲染 Canon（浅背景）、Nikon（深背景）。

    返回自动匹配调用序列与每帧实际绘制的 Logo 文件名；同时检查
    options 全部字段是否被渲染过程修改。
    """
    renderer._logo_selector = selector
    drawn = []
    renderer._add_logo = (
        lambda image, filename, config, engine:
        drawn.append(filename) or image)
    options = RenderOptions(bg_fill_type='pure_white')
    renderer.render_frame(
        Image.new('RGB', (400, 300), 'white'), _logo_style(),
        metadata=_metadata('Canon'), options=options)
    first_frame_options = dataclasses.asdict(options)
    options.bg_fill_type = 'gaussian_black_65'
    # 渲染器不得修改 options 的任何字段；基线取在第二帧渲染前
    #（bg_fill_type 的变更是本探针有意为之的输入，不算渲染副作用）
    snapshot_baseline = dataclasses.asdict(options)
    renderer.render_frame(
        Image.new('RGB', (400, 300), 'white'), _logo_style(),
        metadata=_metadata('Nikon'), options=options)
    snapshot_after = dataclasses.asdict(options)
    return {'selector_calls': selector.calls,
            'drawn_files': drawn,
            'options_after_first_frame': first_frame_options,
            'options_snapshot_after': snapshot_after,
            'options_snapshot_baseline': snapshot_baseline}


def main():
    renderer = FrameRenderer()

    if '--pre' in sys.argv:
        keep = {
            'auto_end_to_end': keep_auto_end_to_end(renderer),
            'fixed_end_to_end': keep_fixed_end_to_end(renderer),
            'disabled_end_to_end': keep_disabled_end_to_end(renderer),
        }
        probe = probe_options_reuse(renderer, RecordingSelector())
        results = {
            'keep': keep,
            'fix_probe': {
                'selector_calls': probe['selector_calls'],
                'drawn_files': probe['drawn_files'],
                'options_after_first_frame':
                    probe['options_after_first_frame'],
            },
        }
        PRE_FILE.write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8')
        print(json.dumps(results, ensure_ascii=False, indent=2))
        print(f"[pre] 基线已写入 {PRE_FILE.name}")
        return

    # ── post 阶段：端到端与 pre 比对 + 修复断言 ──
    pre = json.loads(PRE_FILE.read_text(encoding='utf-8'))

    keep_now = {
        'auto_end_to_end': keep_auto_end_to_end(renderer),
        'fixed_end_to_end': keep_fixed_end_to_end(renderer),
        'disabled_end_to_end': keep_disabled_end_to_end(renderer),
    }
    for case, snapshot in keep_now.items():
        # 输出像素必须逐字节一致；options_logo_after 单独断言——自动
        # 模式的回写值从缺陷值变为 None 正是修复目标，不属于回归
        assert snapshot['digest'] == pre['keep'][case]['digest'], \
            f"保持组输出变化: {case}\npre ={pre['keep'][case]['digest']}\n" \
            f"post={snapshot['digest']}"
    # 自动模式命中文件与固定同名文件的输出必须一致（正常单帧不变）
    assert keep_now['auto_end_to_end']['digest'] \
        == keep_now['fixed_end_to_end']['digest'], \
        "自动模式与固定同名文件的输出不一致"
    assert keep_now['auto_end_to_end']['options_logo_after'] is None, \
        "自动模式渲染后 options.logo_filename 被回写"

    probe = probe_options_reuse(renderer, RecordingSelector())
    # 每帧一次自动匹配：Canon/浅背景、Nikon/深背景各选一次
    assert probe['selector_calls'] == [
        ('canon', False), ('nikon', True)], \
        f"自动匹配调用序列异常: {probe['selector_calls']}"
    # 每帧绘制各自匹配结果（第二帧不再沿用第一帧结果）
    assert probe['drawn_files'] == [
        'Canon_logo_black.png', 'Canon_logo_white.png'], \
        f"绘制文件序列异常: {probe['drawn_files']}"
    # options 全字段渲染前后一致（未被回写）
    assert probe['options_after_first_frame']['logo_filename'] is None, \
        "第一帧渲染后 options.logo_filename 被回写"
    assert probe['options_snapshot_after'] == probe['options_snapshot_baseline'], \
        "options 对象被渲染过程修改"

    # 禁用与固定模式不触发自动匹配
    disabled_probe = probe_static_modes(renderer)
    fix_results = {
        'reuse_probe': {
            'selector_calls': probe['selector_calls'],
            'drawn_files': probe['drawn_files'],
            'options_logo_after': probe['options_snapshot_after']
            ['logo_filename'],
        },
        **disabled_probe,
    }
    results = {'keep': keep_now, 'fix': fix_results}
    POST_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"[post] 端到端输出与 pre 一致；修复断言全部通过，"
          f"已写入 {POST_FILE.name}")


def probe_static_modes(renderer):
    """禁用（空串）与固定文件模式：不触发自动匹配，绘制行为正确。"""
    selector = RecordingSelector()
    renderer._logo_selector = selector
    drawn = []
    renderer._add_logo = (
        lambda image, filename, config, engine:
        drawn.append(filename) or image)

    disabled_options = RenderOptions(bg_fill_type='pure_white',
                                     logo_filename='')
    renderer.render_frame(
        Image.new('RGB', (400, 300), 'white'), _logo_style(),
        metadata=_metadata('Canon'), options=disabled_options)
    assert selector.calls == [], "禁用模式仍触发自动匹配"
    assert drawn == [], "禁用模式仍绘制 Logo"

    fixed_options = RenderOptions(bg_fill_type='pure_white',
                                  logo_filename='Canon_logo_white.png')
    renderer.render_frame(
        Image.new('RGB', (400, 300), 'white'), _logo_style(),
        metadata=_metadata('Canon'), options=fixed_options)
    assert selector.calls == [], "固定文件模式仍触发自动匹配"
    assert drawn == ['Canon_logo_white.png'], \
        f"固定文件未按指定绘制: {drawn}"
    return {'disabled_no_match': True, 'fixed_draws_exact_file': True}


if __name__ == '__main__':
    main()
