"""T2（Q14-12 依赖环处理）的独立验证证据脚本。

从项目根目录激活 venv 后，以绝对路径运行本脚本；直接调用现有实现，
不依赖测试框架。本脚本只写自己的输出 JSON（*_pre.json / *_post.json），
绝不触碰其他审计证据文件。

用法：
    python docs/review_evidence/core_pipeline_t2_cycle_fix.py --pre
        修复前运行：采样"必须保持"组基线 + 用有界 tracing 记录环的
        当前（挂死）行为，输出 core_pipeline_t2_cycle_fix_pre.json。

    python docs/review_evidence/core_pipeline_t2_cycle_fix.py
        修复后运行：保持组逐项与 pre 基线比对（像素必须完全一致），
        断言 StyleManager 拒绝环、直调渲染受控报错，输出
        core_pipeline_t2_cycle_fix_post.json。

场景对应审计报告 §3 Q14-12 验收要求：自环、双节点环、较长环、
正常多级链、没有实际文本的环、缺失目标。
"""

import hashlib
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from PIL import Image

from src.core.renderer import FrameRenderer, RenderOptions
from src.frame_styles.style_manager import StyleManager
from src.utils.layout_engine import LayoutEngine

EVIDENCE_DIR = Path(__file__).resolve().parent
PRE_FILE = EVIDENCE_DIR / 'core_pipeline_t2_cycle_fix_pre.json'
POST_FILE = EVIDENCE_DIR / 'core_pipeline_t2_cycle_fix_post.json'

# 统一渲染入参：显式选浅色背景方案，文字用黑色绘制在白色测试画布上，
# 保证"合法链像素不变"考察的是真实墨迹而非空白图（默认 gaussian_black_35
# 是深色方案，白字画白布会让布局回归不可见）。
BASE_OPTIONS = dict(bg_fill_type='pure_white', logo_filename='')


def _digest(img):
    """全图字节摘要：合法链渲染行为用逐字节一致判定。"""
    return hashlib.sha256(img.tobytes()).hexdigest()


def _defined_texts_style(cycles):
    """构造 defined_texts 双源环样式；cycles 为 [(name, content, target)]。

    顶层 name 为 _validate_config 的必需字段，缺失会在字段检查阶段
    被拒，掩盖环校验本身的行为。
    """
    return {'name': 'audit-t2', 'layout': {'defined_texts': {
        name: {'content': content, 'relative_to': target,
               'relative_position': 'below', 'cross_alignment': 'left'}
        for name, content, target in cycles
    }, 'info_position': {}}}


# ── 有界 tracing：观察真实 render 的 walk 局部变量，防止挂死 ──

class _AuditCycleStop(Exception):
    """仅由审计追踪器抛出，用于有界退出真实渲染中的 walk 循环。"""


def _bounded_walk_trace(renderer, style, max_steps=12):
    """在 text_renderer.render 的 while walk 行采样 walk 变量。

    绑定当前源码的 379 行（while walk）；源码行号变化后需重新校准。
    返回 (walk 序列, 是否被审计中断, 其他异常或 None)。
    """
    walk_steps = []

    def trace_walk(frame, event, arg):
        if (event == 'line' and frame.f_code.co_name == 'render'
                and frame.f_code.co_filename.replace('\\', '/').endswith(
                    '/text_renderer.py')
                and frame.f_lineno == 379):
            walk_steps.append(frame.f_locals.get('walk'))
            if len(walk_steps) >= max_steps:
                raise _AuditCycleStop()
        return trace_walk

    stopped = False
    other_error = None
    previous_trace = sys.gettrace()
    try:
        sys.settrace(trace_walk)
        renderer.render_frame(
            Image.new('RGB', (100, 100), 'white'), style,
            options=RenderOptions(**BASE_OPTIONS))
    except _AuditCycleStop:
        stopped = True
    except Exception as exc:  # noqa: BLE001 — 记录生产代码自身的报错
        other_error = f'{type(exc).__name__}: {exc}'
    finally:
        sys.settrace(previous_trace)
    return walk_steps, stopped, other_error


# ── 保持组：合法链渲染行为修复前后必须一致 ────────────────────

def keep_tree_chain(renderer):
    """合法多级链 + tree_align：root（绝对）← child ← grandchild。"""
    style = {'layout': {
        'info_position': {
            'author': {
                'position': 'bottom-left', 'alignment': 'top-left',
                'placement': 'outside', 'margin_left': 0.03,
                'margin_bottom': 0.03, 'tree_align': True,
            },
        },
        'defined_texts': {
            'custom_note': {
                'content': 'NOTE-A', 'relative_to': 'author',
                'relative_position': 'below', 'cross_alignment': 'left',
            },
            'custom_sub': {
                'content': 'SUB-B', 'relative_to': 'custom_note',
                'relative_position': 'right-of', 'cross_alignment': 'top',
            },
        },
    }}
    result = renderer.render_frame(
        Image.new('RGB', (400, 300), 'white'), style,
        metadata=None, options=RenderOptions(**BASE_OPTIONS))
    return {'digest': _digest(result)}


def keep_simple_relative(renderer):
    """单层相对定位（非 tree_align）：行为保持不变。"""
    style = {'layout': {
        'info_position': {
            'author': {
                'position': 'bottom-left', 'alignment': 'top-left',
                'placement': 'outside', 'margin_left': 0.03,
                'margin_bottom': 0.03,
            },
        },
        'defined_texts': {
            'custom_note': {
                'content': 'NOTE-B', 'relative_to': 'author',
                'relative_position': 'below', 'cross_alignment': 'left',
            },
        },
    }}
    result = renderer.render_frame(
        Image.new('RGB', (400, 300), 'white'), style,
        metadata=type('M', (), {'exif_data': {'camera_make': 'Canon',
                                              'camera_model': 'R6'},
                                'author': 'tester', 'location': None,
                                'lens_display_mode': 'combined',
                                'use_short_lens': False,
                                'custom_text': None,
                                'timestamp_display_mode': 'full'})(),
        options=RenderOptions(**BASE_OPTIONS))
    return {'digest': _digest(result)}


def keep_cycle_without_text(renderer):
    """没有实际文本的环：defined_texts content 为空时不参与渲染，
    直调渲染保持正常完成（配置边界由 StyleManager 拒绝）。"""
    style = _defined_texts_style([
        ('empty_a', '', 'empty_b'),
        ('empty_b', '', 'empty_a'),
    ])
    result = renderer.render_frame(
        Image.new('RGB', (100, 100), 'white'), style,
        options=RenderOptions(**BASE_OPTIONS))
    return {'digest': _digest(result)}


def keep_missing_target(renderer):
    """缺失目标：walk 终止于无名节点，定位阶段按现有规则报错。"""
    style = _defined_texts_style([('lonely', 'X', 'missing_target')])
    try:
        renderer.render_frame(
            Image.new('RGB', (100, 100), 'white'), style,
            options=RenderOptions(**BASE_OPTIONS))
        return {'error': None}
    except Exception as exc:  # noqa: BLE001 — 记录生产代码的现有报错行为
        return {'error': f'{type(exc).__name__}: {exc}'}


# ── 修复组断言（post 阶段） ───────────────────────────────────

class _ListHandler(logging.Handler):
    """收集 StyleValidation 错误消息，供断言环链节点名。"""

    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _make_validator():
    """构造绕过目录加载的 StyleManager（只测配置校验逻辑本身）。"""
    manager = StyleManager.__new__(StyleManager)
    manager.logger = logging.getLogger('audit-t2')
    manager.logger.setLevel(logging.ERROR)
    manager.logger.addHandler(_ListHandler())
    return manager


def _assert_cycle_rejected(manager, style, expect_names):
    """断言样式校验拒绝环且错误信息包含环链中的节点名。"""
    manager.logger.handlers[0].messages.clear()
    assert manager._validate_config(style) is False, \
        "样式校验未拒绝依赖环"
    joined = '；'.join(manager.logger.handlers[0].messages)
    for node in expect_names:
        assert node in joined, f"环错误缺少节点 {node!r}: {joined}"
    assert '环' in joined, f"环错误未说明环: {joined}"
    return {'rejected': True, 'error_sample': joined[:200]}


def _assert_render_raises(renderer, style, expect_names):
    """断言直调渲染对环受控报错（ValueError）且消息含节点链。"""
    try:
        renderer.render_frame(
            Image.new('RGB', (100, 100), 'white'), style,
            options=RenderOptions(**BASE_OPTIONS))
    except ValueError as exc:
        message = str(exc)
        assert '环' in message, f"报错未说明环: {message}"
        for node in expect_names:
            assert node in message, f"报错缺少节点 {node!r}: {message}"
        return {'controlled_error': message[:200]}
    raise AssertionError("直调渲染未对依赖环报错（可能仍挂死或静默通过）")


def main():
    renderer = FrameRenderer()

    if '--pre' in sys.argv:
        two_cycle = _defined_texts_style([
            ('a', 'A', 'b'), ('b', 'B', 'a')])
        self_cycle = _defined_texts_style([('a', 'A', 'a')])
        long_cycle = _defined_texts_style([
            ('a', 'A', 'b'), ('b', 'B', 'c'), ('c', 'C', 'a')])
        results = {
            'keep': {
                'tree_chain': keep_tree_chain(renderer),
                'simple_relative': keep_simple_relative(renderer),
                'cycle_without_text': keep_cycle_without_text(renderer),
                'missing_target': keep_missing_target(renderer),
            },
            'fix_probe': {
                'two_nodes_walk': _bounded_walk_trace(renderer, two_cycle)[0],
                'two_nodes_stopped': _bounded_walk_trace(renderer, two_cycle)[1],
                'self_walk': _bounded_walk_trace(renderer, self_cycle)[0],
                'long_walk': _bounded_walk_trace(renderer, long_cycle)[0],
                'validator_accepts_cycle': _make_validator()._validate_config(
                    two_cycle),
            },
        }
        PRE_FILE.write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8')
        print(json.dumps(results, ensure_ascii=False, indent=2))
        print(f"[pre] 基线已写入 {PRE_FILE.name}")
        return

    # ── post 阶段：保持组比对 + 修复断言 ──
    pre = json.loads(PRE_FILE.read_text(encoding='utf-8'))
    keep_now = {
        'tree_chain': keep_tree_chain(renderer),
        'simple_relative': keep_simple_relative(renderer),
        'cycle_without_text': keep_cycle_without_text(renderer),
        'missing_target': keep_missing_target(renderer),
    }
    for case, snapshot in keep_now.items():
        assert snapshot == pre['keep'][case], \
            f"保持组行为变化: {case}\npre ={pre['keep'][case]}\npost={snapshot}"

    manager = _make_validator()
    two_cycle = _defined_texts_style([('a', 'A', 'b'), ('b', 'B', 'a')])
    self_cycle = _defined_texts_style([('a', 'A', 'a')])
    long_cycle = _defined_texts_style([
        ('a', 'A', 'b'), ('b', 'B', 'c'), ('c', 'C', 'a')])
    empty_cycle = _defined_texts_style([
        ('empty_a', '', 'empty_b'), ('empty_b', '', 'empty_a')])

    fix_results = {
        'validator_rejects_two_nodes': _assert_cycle_rejected(
            manager, two_cycle, ['a', 'b']),
        'validator_rejects_self': _assert_cycle_rejected(
            manager, self_cycle, ['a']),
        'validator_rejects_long': _assert_cycle_rejected(
            manager, long_cycle, ['a', 'b', 'c']),
        'validator_rejects_empty_text_cycle': _assert_cycle_rejected(
            manager, empty_cycle, ['empty_a', 'empty_b']),
        'validator_accepts_chain': _chain_acceptance(manager),
        'render_rejects_two_nodes': _assert_render_raises(
            renderer, two_cycle, ['a', 'b']),
        'render_rejects_self': _assert_render_raises(
            renderer, self_cycle, ['a']),
        'render_rejects_long': _assert_render_raises(
            renderer, long_cycle, ['a', 'b', 'c']),
        'shift_dependents_cycle': _probe_shift_cycle(),
        'collect_tree_members_cycle': _probe_collect_cycle(),
    }
    results = {'keep': keep_now, 'fix': fix_results}
    POST_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"[post] 保持组与 pre 一致；修复断言全部通过，已写入 {POST_FILE.name}")


def _chain_acceptance(manager):
    """合法链与缺失目标必须继续通过样式校验（缺失目标属运行时错误）。"""
    style = {'name': 'audit-t2', 'layout': {
        'info_position': {
            'author': {'position': 'bottom-left', 'alignment': 'top-left',
                       'placement': 'outside', 'tree_align': True},
        },
        'defined_texts': {
            'note': {'content': 'N', 'relative_to': 'author',
                     'relative_position': 'below', 'cross_alignment': 'left'},
        },
    }}
    assert manager._validate_config(style) is True, "合法链被误拒绝"
    missing = _defined_texts_style([('lonely', 'X', 'missing_target')])
    assert manager._validate_config(missing) is True, \
        "缺失目标不应在样式校验阶段报错（保持现有运行时报错规则）"
    return {'legal_chain_accepted': True, 'missing_target_accepted': True}


def _probe_shift_cycle():
    """LayoutEngine._shift_dependents 的环防御：受控报错而非无限递归。"""
    engine = LayoutEngine((100, 100), {})
    engine.register_element('a', 0, 0, 10, 10, relative_to='b')
    engine.register_element('b', 20, 20, 10, 10, relative_to='a')
    try:
        engine._shift_dependents('a', 5, 5)
    except ValueError as exc:
        assert '环' in str(exc), f"报错未说明环: {exc}"
        return {'controlled_error': str(exc)[:200]}
    raise AssertionError("_shift_dependents 未对依赖环报错")


def _probe_collect_cycle():
    """LayoutEngine._collect_tree_members 的环防御：受控报错。"""
    engine = LayoutEngine((100, 100), {})
    engine.register_element('a', 0, 0, 10, 10, relative_to='b')
    engine.register_element('b', 20, 20, 10, 10, relative_to='a')
    try:
        engine._collect_tree_members('a', set())
    except ValueError as exc:
        assert '环' in str(exc), f"报错未说明环: {exc}"
        return {'controlled_error': str(exc)[:200]}
    raise AssertionError("_collect_tree_members 未对依赖环报错")


if __name__ == '__main__':
    main()
