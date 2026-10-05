# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
样式选项状态评估模型（计划 §6，T3：一次算出界面状态和生成参数）

核心入口 evaluate_style_options：给定家族能力快照 + 用户原值 + 照片
事实，一次性算出 11 项 GUI 选项的编辑状态（启禁/原因/说明）与本次
生成使用的有效参数。

设计不变式（§6.2）：
- 驱动布局的输入（作者/地点/文本/时间的编辑能力）按**全部有效变体**
  判定，不随当前布局撤销——不会出现"禁用输入改变条件，条件又反过来
  禁用输入"的循环；
- 用户原值与有效参数分离：控件保留原值、偏好保存原值，本次生成参数
  按"当前家族是否支持"过滤（§6.6）；
- 本模块纯计算：不读文件、不读控件、不修改任何输入与全局表；背景
  是否高斯由调用方查询 BackgroundFillManager.is_gaussian 后传入。
"""
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Optional, Tuple

from src.frame_styles.style_rules import (
    select_variant_candidate,
    build_style_variant_context,
)

# 11 项 GUI 选项 ID（与 RawOptionValues 字段、绑定表一一对应）
OPTION_IDS = (
    'author', 'location', 'use_gps', 'custom_text',
    'timestamp_display_mode', 'lens_display_mode', 'lens_name_mode',
    'logo', 'bg_fill_type', 'enhance_background', 'font_weight',
)

# 合法枚举（与 GUI 下拉 userData 一致；非法值恢复默认项）
_TS_MODES = frozenset({'full', 'date_only', 'hide'})
_LENS_DISPLAY_MODES = frozenset({'combined', 'camera_only', 'lens_only'})
_LENS_NAME_MODES = frozenset({'default', 'full', 'short'})


@dataclass(frozen=True)
class RawOptionValues:
    """用户原值（§6.1：控件实际内容，切样式/切布局不丢）

    logo_filename 三态：None=自动匹配 / ''=禁用 / 其他=指定文件名
    （与 RenderOptions.logo_filename 语义一致，由绑定层从 userData 转换）
    """
    author: str = ''
    location: str = ''
    custom_text: str = ''
    use_gps: bool = False
    timestamp_display_mode: str = 'full'
    lens_display_mode: str = 'combined'
    lens_name_mode: str = 'default'
    logo_filename: Optional[str] = None
    bg_fill_type: str = ''
    enhance_background: bool = True
    font_weight: Optional[str] = None


@dataclass(frozen=True)
class PhotoFacts:
    """照片事实（§6.1：区分"没有照片"与"照片没有 EXIF"）"""
    has_photo: bool = False
    exif_data: Optional[Dict] = None
    gps_text: str = ''


@dataclass(frozen=True)
class OptionState:
    """单个选项的界面状态（§7.2：reason_code 是内部标识，content/tooltip
    是给用户看的中文；文案受单行宽度硬约束，完整语义放 tooltip）"""
    option_id: str
    enabled: bool
    reason_code: str
    content: str = ''
    tooltip: str = ''


@dataclass(frozen=True)
class EffectiveOptionValues:
    """本次生成使用的有效参数（§6.6；与原值分离）"""
    author: Optional[str] = None
    location: Optional[str] = None
    custom_text: Optional[str] = None
    timestamp_display_mode: str = 'full'
    lens_display_mode: str = 'combined'
    lens_name_mode: str = 'default'
    logo_filename: Optional[str] = ''
    bg_fill_type: str = ''
    saturation_override: Optional[float] = None
    font_weight: Optional[str] = None


@dataclass(frozen=True)
class OptionEvaluation:
    """评估结果（§6.1）

    states 每次完整返回 11 项（不只返回变化项，防止旧样式的禁用或
    说明残留）；active_variant_path/valid 记录当前选到哪个配置及是否
    可用；can_render_style 只表示样式可用，页面还要检查当前照片与
    索引才能生成；is_provisional 表示无照片时的预估。
    """
    effective_values: EffectiveOptionValues
    states: Tuple[OptionState, ...]
    active_variant_path: Optional[str]
    active_variant_valid: bool
    can_render_style: bool
    diagnostics: Tuple[str, ...] = ()
    is_provisional: bool = False

    def state_of(self, option_id: str) -> Optional[OptionState]:
        """按 option_id 取单项状态（未返回时为 None，防御未知 ID）"""
        for s in self.states:
            if s.option_id == option_id:
                return s
        return None


# ─────────────────────────────────────────────────────────────
#  内部辅助：reason 文案（§7.2；content 单行短句，tooltip 补全语义）
# ─────────────────────────────────────────────────────────────

_REASON_CONTENT = {
    'no_style': '请先选择样式',
    'invalid_family': '样式配置不可用，无法生成',
    'unsupported': '当前样式的所有布局均不支持此选项',
    'variant_unavailable': '当前布局配置不可用，生成已被阻止',
    'fixed_background': '背景颜色由当前布局指定',
    'non_gaussian': '仅模糊背景支持增强',
    'camera_only': '当前为只显示相机',
    'control_only': '用于选择布局，不直接显示',
    'other_variant_only': '其他布局支持，当前布局未使用',
    'gps_active': '使用照片 GPS，手工地点作为备用',
    'gps_fallback': '照片无 GPS，将使用手工地点',
    'supported': '',
}

_REASON_TOOLTIP = {
    'unsupported': '此样式的全部布局均未使用该信息，填写内容不会显示',
    'variant_unavailable': '当前选中的布局配置损坏，已阻止生成；'
                           '可修改下方输入切换到其他布局',
    'fixed_background': '当前布局声明了固定背景色，背景填充与增强设置'
                        '在生成时被该颜色覆盖',
    'non_gaussian': '背景增强（饱和度提升）只对高斯模糊背景生效，'
                    '纯色背景无此效果',
    'camera_only': '镜头显示为"只显示相机"时组合设备行只输出相机名，'
                   '镜头名模式不参与；切换为其他显示模式后可用',
    'control_only': '此输入只参与变体布局选择（如 no_location），'
                    '当前布局不直接显示它',
    'other_variant_only': '此样式家族中其他布局支持该信息，当前选中的'
                          '布局未使用；保留输入便于切换布局',
    'gps_active': 'GPS 替换已开启且照片含 GPS 坐标，生成时以坐标为准；'
                  '手工地点保留作为无 GPS 照片的备用',
    'gps_fallback': 'GPS 替换已开启，但当前照片无 GPS 坐标，'
                    '生成时使用手工地点',
    'supported': '',
}


def _state(option_id, enabled, reason, extra_tooltip=''):
    """构造 OptionState（统一拼接 reason 文案与补充 tooltip）"""
    return OptionState(
        option_id=option_id,
        enabled=enabled,
        reason_code=reason,
        content=_REASON_CONTENT.get(reason, ''),
        tooltip=extra_tooltip or _REASON_TOOLTIP.get(reason, ''),
    )


def _legal(value, allowed: FrozenSet[str], default: str) -> str:
    """枚举合法性防御：非法值回退默认项（§6.6 恢复语义）"""
    return value if value in allowed else default


def _family_flag(snapshot, attr: str) -> bool:
    """家族级布尔标志：任一有效候选为真即为真"""
    return any(getattr(f, attr) for f in snapshot.candidates if f.valid)


def _active_facts(snapshot, path):
    """按路径取当前候选事实（candidates 与来源候选同序同路径）"""
    for f in snapshot.candidates:
        if f.path == path:
            return f
    return None


def _text_option_supported(snapshot, option: str) -> bool:
    """文本类选项编辑能力：显示支持或条件支持任一即允许编辑（§6.3）"""
    return (option in snapshot.family_display_options
            or option in snapshot.family_condition_options)


def evaluate_style_options(snapshot, raw: RawOptionValues, photo: PhotoFacts,
                           *, selected_bg_is_gaussian: bool) -> OptionEvaluation:
    """计算 11 项选项状态与本次有效参数（计划 §6；纯函数、无副作用）

    Args:
        snapshot: StyleManager.get_style_capabilities 的能力快照；
            None 表示未选择样式
        raw: 用户原值
        photo: 照片事实
        selected_bg_is_gaussian: 当前所选背景填充是否高斯
            （调用方经 BackgroundFillManager.is_gaussian 查询后传入，
            本函数不修改背景注册表）

    Returns:
        OptionEvaluation（states 完整 11 项；详见数据类注释）
    """
    is_provisional = not photo.has_photo
    provisional_tip = ('待加载照片确认' if is_provisional else '')

    # ── no_style：未选择样式 → 全部禁用，无有效参数 ──────────
    if snapshot is None:
        states = tuple(_state(oid, False, 'no_style') for oid in OPTION_IDS)
        return OptionEvaluation(
            effective_values=EffectiveOptionValues(
                bg_fill_type=raw.bg_fill_type,
                saturation_override=1.0 if not raw.enhance_background else None,
            ),
            states=states,
            active_variant_path=None,
            active_variant_valid=False,
            can_render_style=False,
            diagnostics=('未选择样式',),
            is_provisional=is_provisional,
        )

    # ── invalid_family：没有任何有效候选 → 全部禁用并阻止生成 ──
    if snapshot.valid_candidate_count == 0:
        states = tuple(_state(oid, False, 'invalid_family') for oid in OPTION_IDS)
        return OptionEvaluation(
            effective_values=EffectiveOptionValues(bg_fill_type=raw.bg_fill_type),
            states=states,
            active_variant_path=snapshot.source.path or None,
            active_variant_valid=False,
            can_render_style=False,
            diagnostics=snapshot.diagnostics or ('样式的全部布局配置均无效',),
            is_provisional=is_provisional,
        )

    # ── 家族级支持汇总（§6.2 步骤 1：先决定哪些输入与此样式有关）──
    disp = snapshot.family_display_options
    cond = snapshot.family_condition_options
    family_camera_lens = _family_flag(snapshot, 'has_camera_lens')
    family_independent_lens = _family_flag(snapshot, 'has_independent_lens')
    family_logo = snapshot.family_logo_enabled
    family_weight = snapshot.family_has_weighted_text

    # ── 有效值先算（§6.2 步骤 2/3：无效输入用默认值；地点先判支持）──
    author_supported = _text_option_supported(snapshot, 'author')
    location_supported = _text_option_supported(snapshot, 'location')
    text_supported = _text_option_supported(snapshot, 'custom_text')
    ts_supported = _text_option_supported(snapshot, 'timestamp_display_mode')

    eff_author = (raw.author or None) if author_supported else None
    eff_text = (raw.custom_text or None) if text_supported else None
    # 地点：支持时 GPS 开且有坐标用坐标，否则手工原值；不支持时忽略
    # GPS 开关直接置 None（§6.3/§6.6）
    if location_supported:
        if raw.use_gps and photo.gps_text:
            eff_location = photo.gps_text
        else:
            eff_location = raw.location or None
    else:
        eff_location = None
    ts_mode = _legal(raw.timestamp_display_mode, _TS_MODES, 'full')
    eff_ts_mode = ts_mode if ts_supported else 'full'
    lens_display = _legal(raw.lens_display_mode, _LENS_DISPLAY_MODES, 'combined')
    eff_lens_display = lens_display if family_camera_lens else 'combined'

    # ── 当前变体选择（§6.2 步骤 4：从完整候选列表选，不跳过坏候选）──
    context = build_style_variant_context(
        author=eff_author,
        location=eff_location,
        custom_text=eff_text,
        timestamp_display_mode=eff_ts_mode,
        exif_data=photo.exif_data,
    )
    picked = select_variant_candidate(snapshot.source.candidates, context)
    active_path = picked.path if picked else None
    active = _active_facts(snapshot, active_path) if picked else None
    active_valid = bool(active and active.valid)
    can_render = active_valid

    diagnostics = list(snapshot.diagnostics)
    if picked is not None and not active_valid:
        diagnostics.append(
            f'当前布局不可用: {active.filename}（' +
            '；'.join(active.diagnostics) + '）')

    # ── 当前布局说明（§6.2 步骤 5：镜头/背景/字重的局部限制）──────
    active_uses = _active_facts_usage(active)

    states = []

    # 作者（§6.3：显示或条件支持即编辑；当前用→supported，其他布局
    # 用→other_variant_only，仅条件→control_only。经组合行
    # timestamp_author 显示也算当前布局使用——Bottom Bars 场景）
    states.append(_text_state(
        'author', author_supported, disp, 'author',
        active_uses, bool(active.info_keys & {'author', 'timestamp_author'}),
        extra_tooltip=_combo_tip(snapshot, is_provisional)))

    # 拍摄地点 + GPS 替换（§6.3：开关只由 location 的显示或条件支持启用；
    # 直接 info_position.gps 不受控，不能据此启用）
    states.append(_text_state(
        'location', location_supported, disp, 'location',
        active_uses, 'location' in active.info_keys))
    if location_supported:
        if raw.use_gps and photo.gps_text:
            gps_reason = 'gps_active'
        elif raw.use_gps:
            gps_reason = 'gps_fallback'
        else:
            gps_reason = 'supported'
        states.append(_state(
            'use_gps', True, gps_reason,
            extra_tooltip=('照片 GPS 坐标来自 EXIF，开关不控制布局中直接'
                       '声明的 gps 字段' if gps_reason != 'supported' else '')))
    else:
        states.append(_state('use_gps', False, 'unsupported'))

    # 自定义文本（两种支持形态：info_position.custom_text 经依赖表、
    # 专用 custom_text enabled——已在分析区并入 display_options）
    uses_custom_text = (
        'custom_text' in active.info_keys
        or bool(active.display_options & {'custom_text'}))
    states.append(_text_state(
        'custom_text', text_supported, disp, 'custom_text',
        active_uses, uses_custom_text,
        extra_tooltip=('当前布局的专用自定义文本行未启用' if (
            text_supported and not uses_custom_text) else '')))

    # 拍摄时间（与作者共用组合行的说明放 tooltip）
    states.append(_text_state(
        'timestamp_display_mode', ts_supported, disp, 'timestamp_display_mode',
        active_uses,
        bool(active.info_keys & {'timestamp', 'timestamp_author'}),
        extra_tooltip=_combo_tip(snapshot, is_provisional)))

    # 镜头显示（§6.4：家族有 camera_lens 才有此菜单）
    if family_camera_lens:
        if active.has_camera_lens:
            states.append(_state('lens_display_mode', True, 'supported'))
        else:
            states.append(_state('lens_display_mode', True, 'other_variant_only'))
    else:
        states.append(_state('lens_display_mode', False, 'unsupported'))

    # 镜头名（§6.4：独立镜头键存在，或存在 camera_lens 且当前显示模式
    # 非 camera_only；只启禁整个三态菜单，不逐项关闭）
    lens_name_enabled = (
        family_independent_lens
        or (family_camera_lens and lens_display != 'camera_only'))
    if lens_name_enabled:
        if active.has_independent_lens or (
                active.has_camera_lens and lens_display != 'camera_only'):
            states.append(_state('lens_name_mode', True, 'supported'))
        else:
            states.append(_state('lens_name_mode', True, 'other_variant_only'))
    elif (not family_independent_lens and family_camera_lens
          and lens_display == 'camera_only'):
        states.append(_state('lens_name_mode', False, 'camera_only'))
    else:
        states.append(_state('lens_name_mode', False, 'unsupported'))

    # LOGO（家族支持才可编辑；当前布局未启用 → other_variant_only）
    if family_logo:
        if active.logo_enabled:
            states.append(_state('logo', True, 'supported'))
        else:
            states.append(_state('logo', True, 'other_variant_only',
                                 extra_tooltip='当前布局未启用 LOGO 行，'
                                           '其他布局（变体）会显示'))
    else:
        states.append(_state('logo', False, 'unsupported'))

    # 背景填充（§6.5：固定色禁用；当前布局损坏 → variant_unavailable）
    if not active_valid:
        states.append(_state('bg_fill_type', False, 'variant_unavailable'))
    elif active.fixed_background_rgb is not None:
        rgb = active.fixed_background_rgb
        states.append(_state(
            'bg_fill_type', False, 'fixed_background',
            extra_tooltip=f'当前布局固定背景色 #{rgb[0]:02X}{rgb[1]:02X}'
                          f'{rgb[2]:02X}，生成时覆盖此选择'))
    else:
        states.append(_state('bg_fill_type', True, 'supported'))

    # 背景增强（磨砂矩形/效果栈的高斯模糊不属于此开关，不因此启用）
    if not active_valid:
        states.append(_state('enhance_background', False, 'variant_unavailable'))
    elif active.fixed_background_rgb is not None:
        states.append(_state('enhance_background', False, 'fixed_background'))
    elif not selected_bg_is_gaussian:
        states.append(_state('enhance_background', False, 'non_gaussian'))
    else:
        states.append(_state('enhance_background', True, 'supported'))

    # 字重（§6.5：家族有受控文字即可编辑；当前文本为空不撤销能力；
    # 独立水印不贡献字重支持）
    if family_weight:
        if active.has_weighted_text:
            states.append(_state('font_weight', True, 'supported'))
        else:
            states.append(_state('font_weight', True, 'other_variant_only'))
    else:
        states.append(_state('font_weight', False, 'unsupported'))

    # ── 有效参数（§6.6 表；控件保留原值，偏好保存也读原值）────────
    eff_lens_name = _legal(
        raw.lens_name_mode, _LENS_NAME_MODES, 'default') if lens_name_enabled else 'default'
    eff_logo = raw.logo_filename if family_logo else ''
    eff_saturation = (
        None if (selected_bg_is_gaussian and raw.enhance_background) else 1.0)
    eff_weight = raw.font_weight if family_weight else None

    return OptionEvaluation(
        effective_values=EffectiveOptionValues(
            author=eff_author,
            location=eff_location,
            custom_text=eff_text,
            timestamp_display_mode=eff_ts_mode,
            lens_display_mode=eff_lens_display,
            lens_name_mode=eff_lens_name,
            logo_filename=eff_logo,
            bg_fill_type=raw.bg_fill_type,
            saturation_override=eff_saturation,
            font_weight=eff_weight,
        ),
        states=tuple(states),
        active_variant_path=active_path,
        active_variant_valid=active_valid,
        can_render_style=can_render,
        diagnostics=tuple(diagnostics),
        is_provisional=is_provisional,
    )


def _active_facts_usage(active):
    """当前布局实际使用的文本键集合（active.info_keys 的别名，语义化）"""
    return active.info_keys if active is not None else frozenset()


def _text_state(option_id, supported, disp, dep_option, active_uses,
                active_uses_option, extra_tooltip=''):
    """文本类选项状态构造（§6.3：编辑能力与当前使用分开表达）

    Args:
        dep_option: 该选项在依赖表中的选项 ID（用于"其他变体支持"判定）
        active_uses_option: 当前布局是否直接显示/使用该选项
    """
    if not supported:
        return _state(option_id, False, 'unsupported')
    if active_uses_option:
        return _state(option_id, True, 'supported', extra_tooltip=extra_tooltip)
    if dep_option in disp:
        # 其他有效布局显示支持、当前布局未使用
        return _state(option_id, True, 'other_variant_only',
                      extra_tooltip=extra_tooltip)
    # 只出现在文件名条件中（影响布局选择，不直接显示）
    return _state(option_id, True, 'control_only', extra_tooltip=extra_tooltip)


def _combo_tip(snapshot, is_provisional: bool) -> str:
    """时间/作者组合行说明（§7.2：tooltip 补充，不新增禁用原因）"""
    tips = []
    if is_provisional:
        tips.append('待加载照片确认')
    tips.append('拍摄时间与作者共用组合行：任一有值即显示'
                '（"Shot by 作者" / 纯时间 / "时间 by 作者"）')
    return '；'.join(tips)
