# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
样式规则与能力分析模块（计划 §4.2/§4.3/§5，单文件两区）

本模块是样式加载管线的纯函数层，分两个区：

【变体规则区】（§4.2/§4.3）——文件名条件解析、变体选择评分、
  字段可用性上下文构建。被 core/image_processor（每次输入变化）与
  StyleManager（加载选择）共享，是"GUI 与处理器同一套变体规则"的
  单一实现点。

【能力分析区】（§5）——从加载后的配置提取单候选能力事实
  （VariantFacts）与家族能力快照（StyleCapabilitySnapshot），
  由 StyleManager.get_style_capabilities 调用。

依赖约束（§4.3，健壮性红线）：
- 全模块不读取文件、不导入 Qt、不导入 core、不反向导入 StyleManager；
- 唯一渲染语义依赖是 utils/render_context 的类级查询入口（选项依赖表，
  仅供能力分析区使用；已核实 render_context → exif_helper 无回边）；
- 【变体规则区严禁引用 render_context 或任何渲染语义】——core 经
  _build_style_context 高频导入本模块会连带模块顶部 import，规则区
  保持零渲染依赖可防止 frame_styles → utils 的耦合继续扩散。
"""
import os
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Optional, Tuple

# ─────────────────────────────────────────────────────────────
#  变体规则区（§4.2/§4.3）
# ─────────────────────────────────────────────────────────────

# 组合字段缺失蕴含其组成部分全部缺失（如 timestamp_author 缺失 ⟹
# timestamp 与 author 均缺失）。评分时展开组合字段，使更严格的组合变体
# （no_timestamp_author）在与单字段变体（no_author）同时匹配
# （"时间与作者均无值"场景）时凭更高分胜出，避免同分取舍不确定。
# 注意：此展开只用于评分，不合成命中条件——上下文未显式出现的字段
# 不进入缺失集合，不能自动让组合条件命中。
IMPLIED_MISSING: Dict[str, Tuple[str, ...]] = {
    'timestamp_author': ('timestamp', 'author'),
}


@dataclass(frozen=True)
class VariantCandidate:
    """单个变体配置文件的候选事实（不可变）

    Attributes:
        path: 配置文件绝对路径
        filename: 文件名（含扩展名；选择评分与 default 判定的依据）
        ordinal: 原始枚举序号（os.listdir 顺序）——default 兜底与
            "无 default 取首文件"都按此顺序，必须保留给兜底逻辑
        required_missing: 文件名解析出的缺失条件集合（空集 = default
            或不带 no 片段的普通文件）
    """
    path: str
    filename: str
    ordinal: int
    required_missing: FrozenSet[str]


@dataclass(frozen=True)
class StyleSource:
    """样式来源定位结果（不可变，计划 §4.1）

    Attributes:
        kind: 来源类型——'directory'（目录样式）/ 'single_file'（单文件）
            / 'missing'（不存在）
        path: 目录或单文件绝对路径；missing 为空字符串
        candidates: 目录样式的候选序列（保持原始枚举顺序）；单文件与
            missing 为空元组
        diagnostics: 来源级诊断（如目录为空），由调用方决定如何呈现
    """
    kind: str
    path: str
    candidates: Tuple[VariantCandidate, ...] = ()
    diagnostics: Tuple[str, ...] = ()


def parse_missing_fields(filename: str) -> FrozenSet[str]:
    """从变体文件名解析 no_{field} 条件片段（计划 §4.2）

    规则与拆分前逐字一致：default 名（不区分大小写）返回空集；
    连续非 no 片段合并为含下划线字段名（保留 custom_text、
    timestamp_author 等）；未知 no_x 条件原样保留（通用选择器兜底）。

    Args:
        filename: 变体文件名（如 'no_location_no_timestamp_author.yaml'）

    Returns:
        缺失条件字段集合（frozenset，不可变）
    """
    name = os.path.splitext(filename)[0]
    if name.lower() == 'default':
        return frozenset()
    parts = name.split('_')
    fields = set()
    i = 0
    while i < len(parts):
        if parts[i].lower() == 'no' and i + 1 < len(parts):
            i += 1
            field_parts = []
            while i < len(parts) and parts[i].lower() != 'no':
                field_parts.append(parts[i])
                i += 1
            if field_parts:
                fields.add('_'.join(field_parts))
        else:
            i += 1
    return frozenset(fields)


def _expand_missing(fields: FrozenSet[str]) -> set:
    """评分展开：合并条件与组合字段蕴含项（§4.2；只评分、不合成命中）"""
    expanded = set(fields)
    for f in fields:
        expanded.update(IMPLIED_MISSING.get(f, ()))
    return expanded


def select_variant_candidate(candidates: Tuple[VariantCandidate, ...],
                             context: Optional[Dict]) -> Optional[VariantCandidate]:
    """从完整候选列表选择当前变体（计划 §4.2：保留两套顺序）

    与拆分前 _resolve_style_variant 行为逐字一致：
    - 上下文缺失判定：显式值为 None 或空字符串的字段才算缺失，
      未出现的字段不算缺失（context 没有 iso 不能选 no_iso）；
    - 条件候选按文件名排序遍历，评分（展开蕴含后计数）高者胜，
      同分取排序后的首个；
    - 无条件命中：按原始枚举顺序取首个 default；
    - 无 default：按原始枚举顺序取首文件；
    - 不检查配置是否有效——选到损坏文件由调用方报告不可用，
      绝不静默跳到另一个有效配置。

    Args:
        candidates: 候选序列（保持原始枚举顺序）
        context: 字段可用性字典（None 表示无上下文，等价空缺失集）

    Returns:
        命中的 VariantCandidate；候选列表为空时返回 None
    """
    if not candidates:
        return None

    # 确定缺失的字段集合（显式 None / 空字符串才算缺失）
    missing_fields = set()
    if context:
        for f, value in context.items():
            if value is None or value == '':
                missing_fields.add(f)

    # 条件候选：文件名排序保证同分取舍确定（listdir 顺序不保证）；
    # 严格大于使同分保持排序后首个，与拆分前行为一致
    best: Optional[VariantCandidate] = None
    best_score = -1
    for cand in sorted(candidates, key=lambda c: c.filename):
        required = cand.required_missing
        if not required:
            # default 与无条件的普通文件不参与条件匹配（最低优先级）
            continue
        if required.issubset(missing_fields):
            score = len(_expand_missing(required))
            if score > best_score:
                best_score = score
                best = cand
    if best is not None:
        return best

    # 兜底 1：原始枚举顺序中的首个 default（不能把列表排序后再兜底）
    for cand in candidates:
        if os.path.splitext(cand.filename)[0].lower() == 'default':
            return cand

    # 兜底 2：无 default 时取原始枚举顺序首文件
    return candidates[0]


def build_style_variant_context(
        *, author, location, custom_text,
        timestamp_display_mode: str, exif_data: Optional[Dict]) -> Dict:
    """构建变体匹配上下文（计划 §4.3；与 _build_style_context 行为一致）

    上下文以"字段可用性"为语义：值为 None/'' 表示该字段无值，进入
    变体缺失字段集合，驱动 no_{field} 变体匹配。各字段可用性定义：

    - location / author：用户输入可用性（原样写入，None 即缺失）；
    - custom_text：为空（含空串）时显式加入 None，非空时不加入
      （保持 `value or None` 语义，不 trim，空格与空串有区别）；
    - timestamp：时间模式不是 hide 且 EXIF 有 datetime_original 才可用，
      否则加入 None（匹配 no_timestamp 类变体）；
    - timestamp_author：组合字段 = 时间或作者任一有值即可用（与
      RenderContext.get_text('timestamp_author') 的三段 fallback 一致）；
      仅当两者都无值时传 None，匹配 no_timestamp_author（整行不渲染）。
      有作者无时间仍可显示作者，有时间无作者仍可显示时间——不能只看
      "隐藏时间"开关，也不能把作者为空等同于组合行为空。

    纯函数：不读文件、不解包 RenderMetadata（由调用方解包传入），
    避免与 core 的循环依赖。
    """
    context = {'location': location, 'author': author}
    if not custom_text:
        context['custom_text'] = None
    # 拍摄时间可用性：hide 模式或 EXIF 无拍摄时间时视为缺失
    ts_available = (
        timestamp_display_mode != 'hide'
        and bool(exif_data and exif_data.get('datetime_original'))
    )
    if not ts_available:
        context['timestamp'] = None
    # 组合字段可用性 = 时间或作者任一有值（fallback 归一设计的核心约定）
    if not (ts_available or author):
        context['timestamp_author'] = None
    return context


# ─────────────────────────────────────────────────────────────
#  能力分析区（§5）
# ─────────────────────────────────────────────────────────────
# 本区依赖顶部导入的 RenderContext 类级查询入口（选项依赖表），
# 变体规则区不得引用（见模块头依赖约束）。
from src.utils.render_context import RenderContext  # noqa: E402

# 文件名缺失条件 → 受影响的用户选项 ID（§5.2：条件支持从文件名提取；
# GPS 是地点输入的来源，不是另一种缺失条件；未知条件无 GUI 选项映射）
_CONDITION_TO_OPTIONS: Dict[str, FrozenSet[str]] = {
    'author': frozenset({'author'}),
    'location': frozenset({'location'}),
    'custom_text': frozenset({'custom_text'}),
    'timestamp': frozenset({'timestamp_display_mode'}),
    'timestamp_author': frozenset({'author', 'timestamp_display_mode'}),
}


def condition_options_from_filename(filename: str) -> FrozenSet[str]:
    """从文件名条件提取受影响的选项 ID 集合（§5.2 条件支持）"""
    options = set()
    for f in parse_missing_fields(filename):
        options.update(_CONDITION_TO_OPTIONS.get(f, ()))
    return frozenset(options)


@dataclass(frozen=True)
class VariantFacts:
    """单候选能力事实（§5.3，不可变；字段按用途组织）

    Attributes:
        path / filename / ordinal: 候选身份（坏候选也保留，供选择器照常选择）
        required_missing: 文件名缺失条件（坏候选同样保留给共享选择器）
        condition_options: 文件名条件映射到的用户选项（坏候选也贡献条件支持，
            让用户能通过修改输入避开坏布局）
        valid: 是否通过现有加载器与已知结构检查（不是完整渲染成功保证）
        diagnostics: 结构诊断（invalid 时非空；不外泄完整配置内容）
        info_keys: info_position 中实际声明为字典的文本键
        display_options: 本候选显示层面用到的用户选项（info_position 键的
            依赖表并集 + 启用的专用 custom_text）
        has_weighted_text: 存在受全局字重控制的文字（动态文本 / 合法非空
            固定文字 / 启用的专用文本）
        has_independent_lens / has_camera_lens: 独立镜头键与组合设备键
        logo_enabled: 顶层 logo 为字典且 enabled 为真
        fixed_background_rgb: colors.custom_bg_color 经共享 parse_color_value
            解析的 RGB（None = 无固定色；解析行为与渲染端一致、不收紧校验）
        portrait_adaptation_default: 本候选声明的竖图旋转适配默认值
            （validate_style_default 结果；供页面提示复用快照，省一次加载）
    """
    path: str
    filename: str
    ordinal: int
    required_missing: FrozenSet[str]
    condition_options: FrozenSet[str]
    valid: bool
    diagnostics: Tuple[str, ...] = ()
    info_keys: FrozenSet[str] = frozenset()
    display_options: FrozenSet[str] = frozenset()
    has_weighted_text: bool = False
    has_independent_lens: bool = False
    has_camera_lens: bool = False
    logo_enabled: bool = False
    fixed_background_rgb: Optional[Tuple[int, int, int]] = None
    portrait_adaptation_default: Optional[str] = None


@dataclass(frozen=True)
class StyleCapabilitySnapshot:
    """家族能力快照（§5.3/§5.4，不可变；family = 该样式的全部变体）

    Attributes:
        style_name: 样式名
        source: 来源定位结果（与渲染加载同一来源，不合并其他同名来源）
        candidates: 各候选的 VariantFacts（含坏候选，保持枚举顺序）
        family_display_options: 全部有效候选显示支持的选项并集
        family_condition_options: 全部候选（含坏候选）条件支持并集——
            有有效变体时条件输入保持可编辑，用户才能改输入离开坏布局
        family_has_weighted_text / family_logo_enabled: 家族级字重与 LOGO 支持
        valid_candidate_count / total_candidate_count: 有效与全部候选数
        diagnostics: 家族级诊断（来源为空目录 / 全部候选无效等）
    """
    style_name: str
    source: StyleSource
    candidates: Tuple[VariantFacts, ...]
    family_display_options: FrozenSet[str]
    family_condition_options: FrozenSet[str]
    family_has_weighted_text: bool
    family_logo_enabled: bool
    valid_candidate_count: int
    total_candidate_count: int
    diagnostics: Tuple[str, ...] = ()


def analyze_variant(config: Dict, candidate: VariantCandidate,
                    diagnostics: Tuple[str, ...] = ()) -> VariantFacts:
    """从加载后的配置提取单候选能力事实（§5.1/§5.3，纯函数）

    config 必须已经过加载器（注入默认字段并完成定位校验）：info_position
    缺失/为 null/非字典时加载器已注入 exif/author/location 默认信息，显式
    空字典则不注入——两者在这里天然呈现为不同的 info_keys，不做二次猜测。

    已知结构补充检查（§5.3：加载器可能接受、但当前渲染会出错的结构）：
    - info_position 子项不是字典 → 整份候选不可用（渲染端 all_positions
      合并后 .get 会崩溃），不静默删除字段；
    - defined_texts 整体不是字典 → 不可用；内部非字典项按 TextRenderer
      现有规则跳过，不误判整份失败；
    - 实际参与渲染的非空固定 content 必须是字符串，否则不可用。

    Args:
        config: 加载后的配置字典（本函数只读，不修改、不缓存引用）
        candidate: 候选身份与文件名条件
        diagnostics: 加载阶段已有的诊断（如加载失败原因）
    """
    diags = list(diagnostics)
    valid = True

    if config is None:
        # 加载失败（语法错误 / 校验拒绝 / 非字典）：仍保留身份与文件名
        # 条件，让共享选择器照常选择；不贡献显示能力
        return VariantFacts(
            path=candidate.path,
            filename=candidate.filename,
            ordinal=candidate.ordinal,
            required_missing=candidate.required_missing,
            condition_options=condition_options_from_filename(candidate.filename),
            valid=False,
            diagnostics=diags or ('配置加载失败（语法或校验错误），详见 debug 日志',),
        )

    layout = config.get('layout', {})
    if not isinstance(layout, dict):
        # 加载器已保证 layout 为字典；防御分支保留（不可达即不生效）
        layout = {}

    info = layout.get('info_position', {})
    info_keys = frozenset()
    display_options = set()
    if isinstance(info, dict):
        # 只统计实际声明为字典的子项；存在非字典子项则整份候选不可用
        # （渲染端按合并键直接使用，非字典会让渲染代码崩溃）
        bad_children = [k for k, v in info.items() if not isinstance(v, dict)]
        if bad_children:
            valid = False
            diags.append(
                f'info_position 子项不是字典: {sorted(bad_children)}'
                '（渲染将失败，整份候选标记为不可用）')
        info_keys = frozenset(k for k, v in info.items() if isinstance(v, dict))
        for key in info_keys:
            display_options.update(RenderContext.get_option_dependencies(key))
    else:
        # 加载器保证 info_position 为字典（缺失/非字典会被注入默认），
        # 此分支为不可达防御
        valid = False
        diags.append('layout.info_position 不是字典（加载器注入缺失）')

    # 专用 custom_text：字典且 enabled 为真时支持自定义文本；
    # 非字典按现有渲染行为视为未启用（不算错误）
    custom_text_cfg = layout.get('custom_text')
    custom_text_enabled = (
        isinstance(custom_text_cfg, dict) and bool(custom_text_cfg.get('enabled')))
    if custom_text_enabled:
        display_options.add('custom_text')

    # defined_texts：固定文字。整体非字典 → 不可用；内部非字典项按
    # TextRenderer 现有规则跳过（不判失败）；实际参与渲染的非空 content
    # 必须是字符串（TextRenderer 会把真值 content 直接送进渲染管线）
    defined_texts = layout.get('defined_texts', {})
    has_fixed_weighted = False
    if defined_texts is None:
        defined_texts = {}
    if not isinstance(defined_texts, dict):
        valid = False
        diags.append(f'defined_texts 应为字典，实际为 {type(defined_texts).__name__}')
    else:
        for _key, entry in defined_texts.items():
            if not isinstance(entry, dict):
                continue  # TextRenderer 现有规则：非字典项跳过
            content = entry.get('content', '')
            if content and not isinstance(content, str):
                valid = False
                diags.append(
                    f'defined_texts.{_key}.content 非空但不是字符串'
                    f'（{type(content).__name__}），渲染将失败')
            elif content:
                has_fixed_weighted = True

    has_weighted_text = bool(info_keys) or has_fixed_weighted or custom_text_enabled

    # 顶层 logo：字典且 enabled 为真才支持 LOGO
    logo_cfg = config.get('logo')
    logo_enabled = isinstance(logo_cfg, dict) and bool(logo_cfg.get('enabled'))

    # 固定背景色：直接复用共享 parse_color_value（宽松行为与渲染端一致，
    # 不收紧校验）；非 None 才记录。分析不调用 register_custom_solid、
    # 不修改 FILL_TYPES——固定色注册仍由 renderer 完成。
    from src.utils.color_utils import parse_color_value
    colors = config.get('colors', {})
    fixed_bg = None
    if isinstance(colors, dict):
        fixed_bg = parse_color_value(colors.get('custom_bg_color'))

    # 竖图旋转适配声明（validate_style_default 在加载校验中已拒绝非法值）
    from src.utils.orientation_adaptation import validate_style_default
    try:
        adapt_default = validate_style_default(config)
    except ValueError:
        # 加载器已拒绝非法声明，此处防御：不中断分析，视为未声明
        adapt_default = None

    return VariantFacts(
        path=candidate.path,
        filename=candidate.filename,
        ordinal=candidate.ordinal,
        required_missing=candidate.required_missing,
        condition_options=condition_options_from_filename(candidate.filename),
        valid=valid,
        diagnostics=tuple(diags),
        info_keys=info_keys,
        display_options=frozenset(display_options),
        has_weighted_text=has_weighted_text,
        has_independent_lens=bool(info_keys & {'lens', 'short_lens'}),
        has_camera_lens='camera_lens' in info_keys,
        logo_enabled=logo_enabled,
        fixed_background_rgb=fixed_bg,
        portrait_adaptation_default=adapt_default,
    )


def build_capability_snapshot(
        style_name: str, source: StyleSource,
        facts_seq: Tuple[VariantFacts, ...],
        extra_diagnostics: Tuple[str, ...] = ()) -> StyleCapabilitySnapshot:
    """聚合单候选事实为家族能力快照（§5.3；纯函数）

    聚合规则：
    - 家族显示支持 = 全部**有效**候选的 display_options 并集；
    - 家族条件支持 = 全部候选（**含坏候选**）的 condition_options 并集——
      有其他有效变体时保留条件输入可编辑，用户才能通过修改输入避开
      坏布局；全部候选无效时该并集仍给出，由消费端按"无有效候选"
      关闭相关输入（§5.3/§6.3）。
    """
    valid_facts = [f for f in facts_seq if f.valid]
    family_display = frozenset().union(
        *(f.display_options for f in valid_facts)) if valid_facts else frozenset()
    family_condition = frozenset().union(
        *(f.condition_options for f in facts_seq)) if facts_seq else frozenset()
    return StyleCapabilitySnapshot(
        style_name=style_name,
        source=source,
        candidates=tuple(facts_seq),
        family_display_options=family_display,
        family_condition_options=family_condition,
        family_has_weighted_text=any(f.has_weighted_text for f in valid_facts),
        family_logo_enabled=any(f.logo_enabled for f in valid_facts),
        valid_candidate_count=len(valid_facts),
        total_candidate_count=len(facts_seq),
        diagnostics=tuple(extra_diagnostics),
    )
