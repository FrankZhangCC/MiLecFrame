"""T6（Q4/Q9/Q10/Q11/Q12/Q13 布局原语收敛）的等价性验证脚本。

从项目根目录激活 venv 后运行。收敛前后各跑一次：--pre 采样坐标与
行为基线，默认模式逐项比对（布局原语收敛承诺坐标与行为完全等价，
除 Q12 的既定保留策略外无任何预期差异）。

覆盖面：
- Q10/Q11 坐标等价：九点 position×alignment 全组合（inside/outside、
  非对称 margin、奇偶尺寸、画布扩展）穷举坐标；
- Q12：普通盒与单成员树在超大盒下的差异（既定保留行为：普通盒贴左
  x=20、树贴右 x=0）；相对定位组合盒平移与末尾夹持；
- Q13：padding 恒比例、margin 整数像素/浮点比例的单位语义；
- Q9：九点常量一致性与旧别名拒绝（报错字段不变）；
- Q4：padding 夹持三态（clamp/defer/exempt）与依赖链根查找（含环）；
- Q11：元素查找（精确/唯一后缀/多候选/缺失）与位移传播真实 key。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from src.frame_styles.style_manager import StyleManager
from src.utils.layout_engine import (
    ABSOLUTE_ALIGNMENTS,
    ABSOLUTE_POSITIONS,
    LayoutEngine,
)

EVIDENCE_DIR = Path(__file__).resolve().parent
PRE_FILE = EVIDENCE_DIR / 'core_pipeline_t6_layout_primitives_pre.json'
POST_FILE = EVIDENCE_DIR / 'core_pipeline_t6_layout_primitives_post.json'

NINE_POINTS = [
    'top-left', 'top-center', 'top-right',
    'center-left', 'center', 'center-right',
    'bottom-left', 'bottom-center', 'bottom-right',
]


def survey_nine_point_grid():
    """Q10 坐标穷举：9×9 position×alignment × 配置维度。"""
    results = {}
    # 画布扩展不对称（照片边界偏移）+ 奇偶尺寸
    engines = {
        'plain_odd': LayoutEngine((101, 205), {}),
        'expand_asym': LayoutEngine((100, 100), {
            'expand_canvas': {'enabled': True, 'top': 0.1,
                              'left': 0.2, 'bottom': 0.05}}),
    }
    for eng_name, engine in engines.items():
        for i, position in enumerate(NINE_POINTS):
            for alignment in NINE_POINTS:
                for placement, margins in (
                        ('outside', {}),
                        ('inside', {}),
                        ('outside', {'margin_left': 0.01,
                                     'margin_right': 0.03,
                                     'margin_top': 2,
                                     'margin_bottom': 7})):
                    cfg = {'position': position, 'alignment': alignment,
                           'placement': placement, **margins}
                    x, y = engine.calculate_position(33, 17, cfg)
                    results[f'{eng_name}|{position}|{alignment}|'
                            f'{placement}|{sorted(margins.items())}'] = [x, y]
    return results


def _calc_compat(engine, w, h, cfg, mode, defer_padding=None):
    """calculate_position 的前后签名兼容包装。

    T6 之后是 padding_mode 字符串；改动前是 defer_padding 布尔
    （exempt 与 defer 在旧签名下同为 True，语义混用正是 Q4 要澄清的）。
    """
    try:
        return list(engine.calculate_position(w, h, cfg, padding_mode=mode))
    except TypeError:
        if defer_padding is None:
            return {'legacy_signature_no_equivalent': True}
        return list(engine.calculate_position(
            w, h, cfg, defer_padding=defer_padding))


def survey_clamp_and_units():
    """Q12/Q13/Q4：夹持差异、单位语义、三态模式。"""
    results = {}
    # Q12：安全区 [20,80]，元素宽 80 双边越界——普通盒贴左、树贴右（保留差异）
    engine = LayoutEngine((100, 100), {'padding': {'left': 0.2, 'right': 0.2}})
    root_cfg = {'position': 'top-left', 'alignment': 'top-left',
                'placement': 'inside', 'margin_left': 30, 'tree_align': True}
    results['q12_normal_box'] = list(
        engine.calculate_position(80, 10, root_cfg))
    engine.register_element('root', 30, 0, 80, 10)
    engine.apply_tree_positioning({'root': root_cfg})
    results['q12_single_member_tree'] = list(
        engine.get_element_bounds('root'))

    # Q13：padding 恒比例 vs margin 整数像素/浮点比例
    units = LayoutEngine((4000, 4000), {'padding': {'left': 10}})
    results['q13_padding_int_10'] = units.padding_bounds[0]
    results['q13_margin_int_10'] = units._resolve_margins({'margin': 10})['left']
    results['q13_margin_float_10'] = units._resolve_margins(
        {'margin': 10.0})['left']
    results['q13_margin_direction_override'] = units._resolve_margins(
        {'margin': 5, 'margin_left': 0.02})['left']

    # Q4：三态夹持。exempt（矩形）不夹持；clamp 立即夹持；defer 由整树处理。
    # padding_mode 是 T6 新签名；pre 阶段（旧 defer_padding 布尔）按
    # 语义对照采样（exempt↔True、clamp↔False），post 阶段专属断言坐标。
    pad = LayoutEngine((200, 200), {'padding': {'left': 0.5, 'top': 0.5}})
    cfg_out = {'position': 'top-left', 'alignment': 'top-center',
               'placement': 'outside', 'margin_left': 0.1}
    results['q4_exempt_rect'] = _calc_compat(
        pad, 40, 10, cfg_out, 'exempt', defer_padding=True)
    results['q4_clamp_text'] = _calc_compat(
        pad, 40, 10, cfg_out, 'clamp', defer_padding=False)
    # defer：树根 + 子孙，整树定位后统一夹持
    tree_engine = LayoutEngine((200, 200), {'padding': {'left': 0.5}})
    tree_cfgs = {
        'root': {'position': 'center-left', 'alignment': 'center-left',
                 'placement': 'inside', 'tree_align': True},
        'child': {'relative_to': 'root', 'relative_position': 'right-of',
                  'cross_alignment': 'top', 'relative_margin': 0.02},
    }
    rx, ry = _calc_compat(
        tree_engine, 20, 10, tree_cfgs['root'], 'clamp', defer_padding=False)
    tree_engine.register_element('root', rx, ry, 20, 10)
    cx, cy = _calc_compat(
        tree_engine, 20, 10, tree_cfgs['child'], 'defer', defer_padding=True)
    tree_engine.register_element(
        'child', cx, cy, 20, 10, relative_to='root')
    tree_engine.apply_tree_positioning(tree_cfgs)
    results['q4_tree_root'] = list(tree_engine.get_element_bounds('root'))
    results['q4_tree_child'] = list(tree_engine.get_element_bounds('child'))

    # Q4：依赖链根查找（共享函数；resolve_relative_chain 是 T6 新增，
    # pre 阶段（改动前代码）记录缺失，post 阶段单独断言）
    results['q4_shared_chain_helper'] = _probe_chain_helper()

    # Q9：九点常量与旧别名拒绝
    results['q9_positions_equal_alignments'] = (
        set(ABSOLUTE_POSITIONS) == set(ABSOLUTE_ALIGNMENTS))
    engine9 = LayoutEngine((100, 100), {})
    for bad, field in ((('top'), 'position'), (('both-center'), 'alignment')):
        try:
            engine9._validate_position(bad) if field == 'position' \
                else engine9._validate_alignment(bad)
            results[f'q9_reject_{field}'] = None
        except ValueError as exc:
            results[f'q9_reject_{field}'] = str(exc)[:80]
    return results


def _probe_chain_helper():
    """Q4 共享链查找探针：正常链与环的根查找行为。"""
    try:
        from src.utils.layout_engine import resolve_relative_chain
    except ImportError:
        return {'available': False}
    cfgs = {
        'a': {'position': 'bottom-left', 'alignment': 'top-left',
              'tree_align': True},
        'b': {'relative_to': 'a', 'relative_position': 'below',
              'cross_alignment': 'left'},
        'c': {'relative_to': 'b', 'relative_position': 'below',
              'cross_alignment': 'left'},
    }
    chain, terminal, cycle = resolve_relative_chain(cfgs, 'c')
    cyclic = {'a': {'relative_to': 'b'}, 'b': {'relative_to': 'a'}}
    _c2, _t2, cycle2 = resolve_relative_chain(cyclic, 'a')
    return {
        'available': True,
        'chain_of_c': chain,
        'terminal_is_root': terminal is cfgs['a'],
        'cycle_none': cycle is None,
        'cycle_detected': cycle2,
    }


def survey_lookup_and_shift():
    """Q11：查找唯一入口与位移传播到真实 key。"""
    results = {}
    engine = LayoutEngine((100, 100), {})
    engine.register_element('author_name', 1, 2, 3, 4)
    engine.register_element('custom_author', 5, 6, 7, 8)
    results['q11_exact'] = list(engine.get_element_bounds('custom_author'))
    results['q11_suffix_match'] = list(engine.get_element_bounds('author'))
    results['q11_missing'] = engine.get_element_bounds('nope')
    # _lookup_position 是 T6 新增的查找唯一入口（Q11），pre 阶段记录缺失
    try:
        key, _bounds = engine._lookup_position('author')
        results['q11_resolved_key'] = key
    except AttributeError:
        results['q11_resolved_key'] = 'helper_absent'

    # 位移传播：相对定位组合盒平移必须命中真实 key
    shift_engine = LayoutEngine((300, 100), {'padding': {'left': 0.1, 'right': 0.1}})
    shift_engine.register_element('root_box', 50, 0, 20, 10)
    x, y = shift_engine.calculate_position(
        20, 10,
        {'relative_to': 'root_box', 'relative_position': 'left-of',
         'cross_alignment': 'top', 'relative_margin': 0.01})
    shift_engine.register_element('leaf', x, y, 20, 10, relative_to='root_box')
    results['q11_shift_leaf'] = [x, y]
    results['q11_root_after_shift'] = list(
        shift_engine.get_element_bounds('root_box'))
    return results


def collect_all():
    return {
        'nine_point_grid': survey_nine_point_grid(),
        'clamp_and_units': survey_clamp_and_units(),
        'lookup_and_shift': survey_lookup_and_shift(),
    }


def main():
    if '--pre' in sys.argv:
        results = collect_all()
        PRE_FILE.write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8')
        print(f"[pre] {len(results['nine_point_grid'])} 个九点组合 + "
              f"夹持/单位/查找基线已写入 {PRE_FILE.name}")
        return

    pre = json.loads(PRE_FILE.read_text(encoding='utf-8'))
    now = collect_all()

    # 这两个探针在改动前代码上不存在（T6 新增实现），不参与全等比对，
    # 由下方 post 专属断言校验
    post_only_keys = {'q4_shared_chain_helper', 'q11_resolved_key'}

    def compare(section):
        pre_flat = pre[section]
        now_flat = now[section]
        assert set(pre_flat) == set(now_flat), \
            f"{section} 场景集合变化"
        diff = {k: (pre_flat[k], now_flat[k])
                for k in pre_flat
                if k not in post_only_keys and pre_flat[k] != now_flat[k]}
        assert not diff, f"{section} 行为变化: {list(diff)[:5]}"
        return len(pre_flat)

    n_grid = compare('nine_point_grid')
    n_clamp = compare('clamp_and_units')
    n_lookup = compare('lookup_and_shift')
    # Q12 的既定保留行为逐值确认（防未来误统一）
    assert now['clamp_and_units']['q12_normal_box'] == [20, 0]
    assert now['clamp_and_units']['q12_single_member_tree'] == [0, 0, 80, 10]
    assert now['clamp_and_units']['q13_padding_int_10'] == 40000
    assert now['clamp_and_units']['q13_margin_int_10'] == 10
    assert now['clamp_and_units']['q13_margin_float_10'] == 40000
    # T6 新增实现的专属断言
    helper = now['clamp_and_units']['q4_shared_chain_helper']
    assert helper == {
        'available': True, 'chain_of_c': ['c', 'b', 'a'],
        'terminal_is_root': True, 'cycle_none': True,
        'cycle_detected': ['a', 'b', 'a']}, f"共享链查找行为异常: {helper}"
    assert now['lookup_and_shift']['q11_resolved_key'] == 'custom_author', \
        "查找唯一入口未解析出真实 key"
    # Q4 三态坐标（新签名下的预期值；pre 阶段按旧语义对照采样同值）
    assert now['clamp_and_units']['q4_exempt_rect'] == [0, 0], \
        "矩形豁免被错误夹持"
    assert now['clamp_and_units']['q4_clamp_text'] == [100, 100], \
        "普通元素未夹持进安全区"
    assert now['clamp_and_units']['q4_tree_root'] == [100, 95, 20, 10], \
        "树根未整树平移夹持"
    assert now['clamp_and_units']['q4_tree_child'] == [124, 95, 20, 10], \
        "树成员未随整树平移"

    POST_FILE.write_text(
        json.dumps(now, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print(f"[post] 九点组合 {n_grid} 项、夹持/单位 {n_clamp} 项、"
          f"查找 {n_lookup} 项全部等价，已写入 {POST_FILE.name}")


if __name__ == '__main__':
    main()
