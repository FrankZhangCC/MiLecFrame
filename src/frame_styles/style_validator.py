# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
样式定位校验模块（从 StyleManager 纯搬运拆分，计划 §4.0）

职责边界：五类定位元素（layout.info_position / defined_texts / custom_text /
rectangles / 顶层 logo）的定位语义校验——九点 position / alignment 枚举、
旧单轴别名拒绝、相对定位字段与交叉轴轴向匹配、relative_to 依赖环检测。

本模块是纯函数集合：不读文件、不打日志、不依赖 StyleManager / core / Qt，
错误通过返回值（字符串列表）交给调用方输出。日志格式
`[StyleValidation] [source] ...` 由 StyleManager 侧的薄包装保持，文本与
顺序与拆分前逐字节一致（T0 基线逐条比对验收）。

依赖方向：只依赖 layout_engine 的定位枚举（与 LayoutEngine 单一来源一致），
保持 frame_styles 包不依赖渲染语义与 GUI。
"""
from src.utils.layout_engine import (
    ABSOLUTE_POSITIONS,
    ABSOLUTE_ALIGNMENTS,
    HORIZONTAL_CROSS_ALIGNMENTS,
    VERTICAL_CROSS_ALIGNMENTS,
    RELATIVE_POSITIONS,
    resolve_relative_chain,
)

# 旧 position 单轴别名 → 新九点迁移建议（唯一映射，直接给出目标值）
_POSITION_OLD_ALIAS_HINT = {
    'top': 'top-center',
    'tc': 'top-center',
    'bottom': 'bottom-center',
    'bc': 'bottom-center',
    'left': 'center-left',
    'right': 'center-right',
    'tl': 'top-left',
    'tr': 'top-right',
    'bl': 'bottom-left',
    'br': 'bottom-right',
}

# 旧 alignment 单轴值 → 新九点候选（单轴值无法唯一决定迁移结果，
# 只给候选集，由用户结合元素实际位置选择）
_ALIGNMENT_OLD_ALIAS_HINT = {
    'left': 'top-left / center-left / bottom-left',
    'right': 'top-right / center-right / bottom-right',
    'top': 'top-left / top-center / top-right',
    'bottom': 'bottom-left / bottom-center / bottom-right',
    'both-center': 'center',
}


def iter_positioned_elements(config):
    """
    统一遍历五类定位元素，产出 (字段路径, 定位配置) 元组。

    覆盖：layout.info_position.* / layout.defined_texts.* /
    layout.custom_text / layout.rectangles.* / 顶层 logo。
    未启用的 custom_text / logo（enabled: false）不参与渲染，跳过校验。

    注意：此处**不假设**子项结构合法——非字典子项被跳过（与渲染端
    TextRenderer 的容忍策略一致）；"info_position 子项不是字典"属于
    加载器接受但渲染会出错的缝隙，由能力分析区（style_rules）判为
    候选不可用，不在本校验中处理（保持纯搬运行为）。
    """
    layout = config.get('layout', {})
    if not isinstance(layout, dict):
        return

    info_positions = layout.get('info_position', {})
    if isinstance(info_positions, dict):
        for key, cfg in info_positions.items():
            if isinstance(cfg, dict):
                yield f"layout.info_position.{key}", cfg

    defined_texts = layout.get('defined_texts', {})
    if isinstance(defined_texts, dict):
        for key, cfg in defined_texts.items():
            if isinstance(cfg, dict):
                yield f"layout.defined_texts.{key}", cfg

    custom_text = layout.get('custom_text', {})
    if isinstance(custom_text, dict) and custom_text.get('enabled', False):
        yield 'layout.custom_text', custom_text

    rectangles = layout.get('rectangles', {})
    if isinstance(rectangles, dict):
        for key, cfg in rectangles.items():
            if isinstance(cfg, dict):
                yield f"layout.rectangles.{key}", cfg

    logo = config.get('logo', {})
    if isinstance(logo, dict) and logo.get('enabled', False):
        yield 'logo', logo


def validate_absolute_position_config(path: str, cfg: dict) -> list:
    """
    绝对定位节点校验：必须显式提供九点 position 与九点 alignment，
    拒绝一切旧单轴别名 / both-center（返回错误信息列表）。
    """
    errors = []

    position = cfg.get('position', None)
    if position is None:
        errors.append(
            f"{path}.position 缺失：绝对定位节点必须显式提供九点 position"
            f"（{sorted(ABSOLUTE_POSITIONS)}）")
    elif position not in ABSOLUTE_POSITIONS:
        hint = _POSITION_OLD_ALIAS_HINT.get(str(position))
        extra = f"；建议迁移为 {hint}" if hint else ""
        errors.append(
            f"{path}.position 值非法: {position!r}{extra}。"
            f"合法九点值为 {sorted(ABSOLUTE_POSITIONS)}")

    alignment = cfg.get('alignment', None)
    if alignment is None:
        errors.append(
            f"{path}.alignment 缺失：绝对定位节点必须显式提供九点 alignment"
            f"（{sorted(ABSOLUTE_ALIGNMENTS)}）")
    elif alignment not in ABSOLUTE_ALIGNMENTS:
        hint = _ALIGNMENT_OLD_ALIAS_HINT.get(str(alignment))
        extra = f"；单轴旧值无法唯一迁移，请结合元素实际位置选择：{hint}" if hint else ""
        errors.append(
            f"{path}.alignment 值非法: {alignment!r}{extra}。"
            f"合法九点值为 {sorted(ABSOLUTE_ALIGNMENTS)}")

    return errors


def validate_relative_position_config(path: str, cfg: dict) -> list:
    """
    相对定位节点校验：只接受 relative_to + relative_position +
    cross_alignment；出现旧 alignment 字段直接报错并提示改名为
    cross_alignment；cross_alignment 与方向轴必须匹配。
    """
    errors = []

    if 'alignment' in cfg:
        errors.append(
            f"{path}.alignment: 相对定位节点不允许使用 alignment 字段"
            f"（当前值: {cfg['alignment']!r}），请将该字段改名为 "
            f"cross_alignment（三值交叉轴对齐）")

    relative_position = cfg.get('relative_position', None)
    if relative_position is None:
        errors.append(
            f"{path}.relative_position 缺失：相对定位节点必须显式提供"
            f"（{sorted(RELATIVE_POSITIONS)}）")
    elif relative_position not in RELATIVE_POSITIONS:
        hint = {'after': 'below', 'before': 'above'}.get(
            str(relative_position))
        extra = f"；建议迁移为 {hint}" if hint else ""
        errors.append(
            f"{path}.relative_position 值非法: {relative_position!r}{extra}。"
            f"合法值为 {sorted(RELATIVE_POSITIONS)}")

    cross_alignment = cfg.get('cross_alignment', None)
    if cross_alignment is None:
        errors.append(
            f"{path}.cross_alignment 缺失：相对定位节点必须显式提供交叉轴"
            f"对齐（above/below → left/center/right；"
            f"left-of/right-of → top/center/bottom）")
    elif relative_position in ('above', 'below'):
        if cross_alignment not in HORIZONTAL_CROSS_ALIGNMENTS:
            errors.append(
                f"{path}.cross_alignment 值非法: {cross_alignment!r} 与 "
                f"relative_position={relative_position!r} 轴向不匹配；"
                f"合法值为 {sorted(HORIZONTAL_CROSS_ALIGNMENTS)}")
    elif relative_position in ('left-of', 'right-of'):
        if cross_alignment not in VERTICAL_CROSS_ALIGNMENTS:
            errors.append(
                f"{path}.cross_alignment 值非法: {cross_alignment!r} 与 "
                f"relative_position={relative_position!r} 轴向不匹配；"
                f"合法值为 {sorted(VERTICAL_CROSS_ALIGNMENTS)}")

    if cfg.get('tree_align', False):
        errors.append(
            f"{path}.tree_align: 相对定位节点不允许声明 tree_align"
            f"（tree_align 只属于绝对定位的树根节点）")

    return errors


def detect_relative_cycles(positioned: dict) -> list:
    """
    相对定位依赖环检测（审计 Q14-12）：单节点字段校验无法发现成环的
    relative_to 链，而渲染端向上找根的遍历遇环无法结束，必须在样式
    加载阶段拒绝。

    链遍历复用 layout_engine.resolve_relative_chain（审计 Q4：根查找
    与环检测同一实现）。每个节点至多声明一个 relative_to（函数图）；
    错误信息给出完整环链，已报告环的成员不再作为起点重复报告。
    """
    errors = []
    reported = set()
    for start_name in positioned:
        if start_name in reported:
            continue
        _chain, _terminal, cycle = resolve_relative_chain(
            positioned, start_name)
        if cycle:
            errors.append(
                f"layout.{cycle[0]}.relative_to: 定位依赖存在环"
                f"（{' → '.join(cycle)}）；相对定位链必须终止于"
                f"绝对定位元素，请修正 relative_to 配置")
            reported.update(cycle[:-1])
    return errors


def validate_positioning(config: dict, source: str = '') -> list:
    """
    遍历五类定位元素执行新语义校验（纯函数，返回错误列表）。

    错误策略：任何旧别名、未知枚举、绝对/相对字段混用、轴向不匹配、
    relative_to 依赖环均为错误；错误信息包含字段路径、错误值和人工
    迁移建议。日志输出由调用方完成（保持 `[StyleValidation] [source]`
    前缀格式）。

    裸名 → 配置：与渲染端 all_positions 的合并键一致（后写覆盖），
    relative_to 引用的就是这一命名空间的名字。
    """
    all_errors = []
    positioned = {}
    for path, cfg in iter_positioned_elements(config):
        if cfg.get('relative_to'):
            all_errors.extend(
                validate_relative_position_config(path, cfg))
        else:
            all_errors.extend(
                validate_absolute_position_config(path, cfg))
        positioned[path.rsplit('.', 1)[-1]] = cfg

    # 依赖环检测（Q14-12）：无论环节点是否有实际文本，配置边界一律
    # 拒绝；渲染端另有直调路径的运行时有界防御兜底
    all_errors.extend(detect_relative_cycles(positioned))
    return all_errors
