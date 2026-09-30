# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
样式编辑器表单数据模型

StyleConfigFormData 封装了样式编辑器中所有配置参数，
替代 Streamlit 版 ~100 个 session_state 键，集中管理。
"""
import copy
import os
import ast
import yaml
from dataclasses import dataclass, field
from typing import Optional

# 竖图方向适配默认值（方案 docs/plans/PORTRAIT_ORIENTATION_ADAPTATION_PLAN.md §7.1）
from src.utils.orientation_adaptation import (
    ADAPT_NONE, validate_style_default,
)


# ── 常量 ────────────────────────────────────────────────────

ELEMENT_KEYS = [
    'exif', 'timestamp', 'timestamp_author', 'camera', 'lens',
    'camera_lens', 'camera_make', 'author', 'location', 'gps',
    'focal_length_formatted', 'aperture_formatted',
    'shutter_speed_formatted', 'iso_formatted',
    'custom_text', 'defined_text',
]

PLACEMENT_OPTIONS = ['outside', 'inside']

# 绝对定位 position 九点规范值（照片九点参考位）
ANCHOR_POSITION_OPTIONS = [
    'top-left', 'top-center', 'top-right',
    'center-left', 'center', 'center-right',
    'bottom-left', 'bottom-center', 'bottom-right',
]

# 绝对定位 alignment 九点规范值（元素布局盒相对元素锚点的自对齐）
ALIGNMENT_OPTIONS = [
    'top-left', 'top-center', 'top-right',
    'center-left', 'center', 'center-right',
    'bottom-left', 'bottom-center', 'bottom-right',
]

# 多行文本块内部行对齐（与元素 alignment 完全分离）
LINE_ALIGNMENT_OPTIONS = ['left', 'center', 'right']

# 相对定位交叉轴三值：above/below 用水平组，left-of/right-of 用垂直组
HORIZONTAL_CROSS_OPTIONS = ['left', 'center', 'right']
VERTICAL_CROSS_OPTIONS = ['top', 'center', 'bottom']

RELATIVE_POSITION_OPTIONS = ['below', 'above', 'left-of', 'right-of']

WEIGHT_OPTIONS = ['medium', 'regular', 'light']

COLOR_ELEMENT_KEYS = [
    'exif', 'timestamp', 'timestamp_author', 'camera', 'camera_make',
    'lens', 'camera_lens', 'author', 'location', 'gps',
    'focal_length_formatted', 'aperture_formatted',
    'shutter_speed_formatted', 'iso_formatted', 'custom_text',
]

NEW_STYLE_PLACEHOLDER = '--- 新建样式 ---'


# ── 子数据模型 ──────────────────────────────────────────────

@dataclass
class PositionedSpec:
    """定位参数单元（G1 收敛：四份模型拷贝的单点定义与单点序列化）

    "一个带定位参数的元素"的全部字段：绝对分支（placement / position /
    九点 alignment / 四向 margin / tree_align）与相对分支（relative_to /
    relative_position / cross_alignment / relative_margin / offset_x/y），
    外加与定位模式无关的 line_alignment（STYLE_GUIDE：文字专用字段）。

    序列化规则单点收敛在 to_entry() / update_from_entry()，四个宿主
    （info_position 元素 / 预定义文本 / Logo / 自定义文本）共用；
    规则吸收 G15 修复（line_alignment 与模式无关地读写）。
    各宿主的差异化默认值由子类覆写或构造参数给出，缺失键的填充以
    实例当前值为回退（见 update_from_entry）。
    """
    mode: str = 'absolute'
    placement: str = 'outside'
    position: str = 'bottom-left'
    # 绝对定位时元素布局盒的九点自对齐；相对定位时不写此字段
    absolute_alignment: str = 'top-left'
    # 相对定位时参考元素对应轴上的三值交叉轴对齐；绝对定位时不写此字段
    cross_alignment: str = 'left'
    # 多行文本块内部行对齐（单行文字渲染时忽略；非默认时才序列化）
    line_alignment: str = 'left'
    margin_top: float = 0.0
    margin_bottom: float = 0.02
    margin_left: float = 0.0
    margin_right: float = 0.0
    relative_to: str = 'exif'
    relative_position: str = 'below'
    relative_margin: float = 0.01
    offset_x: float = 0.0
    offset_y: float = 0.0
    tree_align: bool = False

    def _absolute_entry(self) -> dict:
        """绝对分支定位字段（不含 line_alignment / tree_align 修饰）"""
        return {
            'placement': self.placement,
            'position': self.position,
            'alignment': self.absolute_alignment,
            'margin_top': self.margin_top,
            'margin_bottom': self.margin_bottom,
            'margin_left': self.margin_left,
            'margin_right': self.margin_right,
        }

    def _relative_entry(self) -> dict:
        """相对分支定位字段（不含 relative_to 与 line_alignment）

        relative_to 由调用方写（自定义文本需 strip 后写入）。
        """
        entry = {
            'relative_position': self.relative_position,
            'cross_alignment': self.cross_alignment,
            'relative_margin': self.relative_margin,
        }
        if self.offset_x != 0.0:
            entry['offset_x_ratio'] = self.offset_x
        if self.offset_y != 0.0:
            entry['offset_y_ratio'] = self.offset_y
        return entry

    def to_entry(self) -> dict:
        """单点序列化为完整 YAML entry（按模式分支 + 公共修饰）

        绝对分支只写九点 alignment，相对分支只写 cross_alignment；
        line_alignment 与模式无关、非默认才写；tree_align 只属于
        绝对定位节点（Logo/自定义文本不消费 line_alignment 与
        tree_align，直接用两个分支方法自行组合）。
        """
        if self.mode == 'absolute':
            entry = self._absolute_entry()
            if self.line_alignment != 'left':
                entry['line_alignment'] = self.line_alignment
            if self.tree_align:
                entry['tree_align'] = True
            return entry
        entry = {'relative_to': self.relative_to}
        entry.update(self._relative_entry())
        if self.line_alignment != 'left':
            entry['line_alignment'] = self.line_alignment
        return entry

    def update_from_entry(self, entry: dict,
                          *, relative_if_present: bool = True):
        """单点反序列化：按 YAML entry 填充定位字段（G1 单点）

        缺失键回退到实例当前值（宿主差异化默认值由此保留）；margin
        统一兜底键缺失回退 0.0（与既有行为一致——margin_bottom 的
        0.02 默认只在表单新建元素时生效，YAML 缺失一律 0.0）。

        Args:
            entry: info_position / defined_texts 子项，或 logo /
                custom_text 段（多余键自动忽略）
            relative_if_present: 模式判定策略。True（元素列表语义）：
                entry 含 relative_to 键即相对模式（含空串）；
                False（logo/custom_text 段语义）：relative_to 为非空
                值才判相对模式（'relative_to' in entry 且 truthy 的
                差异按既有行为保留）。
        """
        if relative_if_present:
            is_relative = 'relative_to' in entry
        else:
            is_relative = bool(entry.get('relative_to'))
        if is_relative:
            # 相对模式只读 cross_alignment（旧 alignment 字段不透传，
            # 含旧字段的样式应由 StyleManager 校验拒绝加载）
            self.mode = 'relative'
            self.relative_to = str(
                entry.get('relative_to', self.relative_to))
            self.relative_position = str(
                entry.get('relative_position', self.relative_position))
            # cross 缺失默认规则（原四处内联规则的收敛点）：
            # left-of/right-of → center；above/below → left
            default_cross = 'center' if str(
                entry.get('relative_position')) in ('left-of', 'right-of') else 'left'
            self.cross_alignment = str(
                entry.get('cross_alignment', default_cross))
            self.line_alignment = str(
                entry.get('line_alignment', self.line_alignment))
            self.relative_margin = float(
                entry.get('relative_margin', self.relative_margin))
            self.offset_x = float(entry.get('offset_x_ratio', self.offset_x))
            self.offset_y = float(entry.get('offset_y_ratio', self.offset_y))
        else:
            self.mode = 'absolute'
            self.placement = str(entry.get('placement', self.placement))
            self.position = str(entry.get('position', self.position))
            self.absolute_alignment = str(
                entry.get('alignment', self.absolute_alignment))
            self.line_alignment = str(
                entry.get('line_alignment', self.line_alignment))
            marg = entry.get('margin')
            fallback = marg if marg is not None else 0.0
            self.margin_top = float(entry.get('margin_top', fallback))
            self.margin_bottom = float(entry.get('margin_bottom', fallback))
            self.margin_left = float(entry.get('margin_left', fallback))
            self.margin_right = float(entry.get('margin_right', fallback))
            self.tree_align = bool(entry.get('tree_align', False))


@dataclass
class ElementConfig(PositionedSpec):
    """单个 info_position 元素的配置（定位字段继承 PositionedSpec）"""
    id: int = 0
    key: str = 'exif'


@dataclass
class DefinedTextConfig(PositionedSpec):
    """单个预定义文本条目（定位字段继承 PositionedSpec）

    覆写两个差异化默认值：预定义文本默认无下边距、相对定位默认
    挂在参考元素右侧。
    """
    id: int = 0
    key: str = ''
    content: str = ''
    margin_bottom: float = 0.0
    relative_position: str = 'right-of'


def _default_logo_spec() -> PositionedSpec:
    """Logo 定位默认值（九点默认 bottom-right：Logo 底边贴照片上方外侧锚点）"""
    return PositionedSpec(
        position='top-right',
        absolute_alignment='bottom-right',
        # Logo 的 left-of/right-of 相对定位默认交叉轴居中
        cross_alignment='center',
    )


def _default_custom_text_spec() -> PositionedSpec:
    """自定义文本定位默认值（九点默认 top-center：文字顶边贴照片下方外侧锚点）"""
    return PositionedSpec(position='bottom-center')


# ── 工具函数 ────────────────────────────────────────────────

def _clean_dict(d: dict) -> dict:
    """递归清理字典：移除值为 None / 空字符串 / 空 dict 的键"""
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            cleaned = _clean_dict(v)
            if cleaned:
                result[k] = cleaned
        elif v is None:
            continue
        elif isinstance(v, str) and v == '':
            continue
        else:
            result[k] = v
    return result


def _parse_color(value: str):
    """解析颜色字符串，支持 #RRGGBB 或 [r,g,b] 格式"""
    v = value.strip() if value else ''
    if not v:
        return None
    if v.startswith('['):
        try:
            return ast.literal_eval(v)
        except (ValueError, SyntaxError):
            return v
    return v


def _color_to_text(val) -> str:
    """将颜色值转为文本框显示字符串"""
    if val is None or val == '':
        return ''
    if isinstance(val, list):
        return str(val)
    return str(val)


def _flow_list(dumper, seq):
    """列表 representer：序列化为 flow style（[1, 2] 而非逐行块列表）"""
    return dumper.represent_sequence(
        'tag:yaml.org,2002:seq', seq, flow_style=True)


class _FlowListDumper(yaml.Dumper):
    """列表使用 flow_style 的专用 Dumper（G5 修复：序列化隔离）

    此前实现直接对全局 yaml.Dumper 类调用 add_representer(list, ...)，
    修改的是类级 representer 表——进程内之后所有 yaml.dump() 调用的
    列表输出都被改成 flow style，且每次导出重复注册。改为模块级专用
    子类单点注册，全局 Dumper 行为保持不变。
    """


_FlowListDumper.add_representer(list, _flow_list)


def _build_yaml_config(data: dict) -> str:
    """将 dict 序列化为 YAML 字符串，列表使用 flow_style

    使用模块级专用 Dumper（G5：不污染全局 yaml.Dumper 的
    representer 表，进程内其他 yaml.dump 调用不受影响）。
    """
    return yaml.dump(
        data, Dumper=_FlowListDumper, sort_keys=False,
        allow_unicode=True, default_flow_style=False, width=120,
    )


def _make_default_element() -> ElementConfig:
    """创建默认元素"""
    return ElementConfig(id=0)


def _next_element_id(elements: list) -> int:
    """计算下一个可用元素 ID"""
    max_id = max((e.id for e in elements), default=0)
    return max_id + 1


# ── 主数据模型 ──────────────────────────────────────────────

@dataclass
class StyleConfigFormData:
    """样式编辑器表单数据模型

    替代 Streamlit 版的 ~100 个 sc_ 前缀 session_state 键。
    提供 YAML 序列化/反序列化，与 StyleManager 兼容。
    """

    # ── 基本信息 ──
    name: str = ''
    filename: str = ''
    # 竖图方向适配样式默认值（none/clockwise/counterclockwise）：
    # 样式设计者声明的建议方向，用户运行时选项 default 时生效。
    # 本控件本身定义样式默认值，故无 'default' 递归值（方案 §7.2）
    default_portrait_adaptation: str = ADAPT_NONE

    # ── 画布扩展 ──
    canvas_enabled: bool = True
    canvas_top: float = 0.03
    canvas_bottom: float = 0.12
    canvas_left: float = 0.02
    canvas_right: float = 0.02

    # ── 安全区域 ──
    pad_top: float = 0.02
    pad_bottom: float = 0.02
    pad_left: float = 0.02
    pad_right: float = 0.02

    # ── 圆角 ──
    cr_enabled: bool = False
    cr_tl: float = 0.01
    cr_tr: float = 0.01
    cr_bl: float = 0.01
    cr_br: float = 0.01

    # ── 字体 ──
    font_latin_family: str = 'Gotham'
    font_latin_weight: str = 'medium'
    font_latin_system: bool = False
    font_cjk_family: str = 'GlowSansSC-Normal'
    font_cjk_weight: str = 'medium'
    font_cjk_system: bool = False
    font_size_ratio: float = 0.015
    font_line_spacing: float = 0.005
    font_sizes: dict = field(default_factory=dict)
    font_latin_weights: dict = field(
        default_factory=lambda: {'light': 'Light', 'regular': 'Book', 'medium': 'Medium'})
    font_cjk_weights: dict = field(
        default_factory=lambda: {'light': 'Light', 'regular': 'Regular', 'medium': 'Medium'})

    # ── Logo ──
    # 定位参数收拢为 PositionedSpec 成员（G1：flat 字段拷贝消除）；
    # enabled/mode/尺寸等非定位字段仍为平铺字段
    logo_enabled: bool = False
    logo_mode: str = 'absolute'
    logo_spec: PositionedSpec = field(default_factory=_default_logo_spec)
    logo_size_ratio: float = 0.04
    logo_diagonal_limit: float = 2.0

    # ── 颜色 ──
    color_light: str = ''
    color_dark: str = ''
    custom_bg_color: str = ''
    custom_bg_text_scheme: str = ''
    color_per_element: dict = field(default_factory=dict)

    # ── 透传容器（字段保留，本期不支持 GUI 编辑） ──
    # from_yaml_dict() 时保留未识别的 layout 键（如 rectangles），
    # to_yaml_dict() 原样回写。保证"加载→保存"不丢矩形等新特性配置。
    _passthrough_layout: dict = field(default_factory=dict)
    # colors 下不在 COLOR_ELEMENT_KEYS 白名单的键（如 custom_rect_01_*），
    # 同样加载后原样回写
    _passthrough_colors: dict = field(default_factory=dict)
    # logo 段不在已识别键集合的键（如 max_dim_limit_ratio——core
    # renderer 优先消费它、回退 diagonal_limit_ratio），同样加载后
    # 原样回写，避免 Logo 长边限制等配置经 GUI 读写后静默丢失（G15c）
    _passthrough_logo: dict = field(default_factory=dict)

    # ── 元素布局 ──
    elements: list = field(default_factory=lambda: [_make_default_element()])

    # ── 预定义文本 ──
    defined_texts: list = field(default_factory=list)

    # ── 自定义文本 ──
    # 定位参数（含与模式无关的 line_alignment）收拢为 PositionedSpec
    # 成员（G1）；enabled/mode/行间距为非定位字段，保持平铺
    custom_text_enabled: bool = False
    custom_text_mode: str = 'absolute'
    custom_text_spec: PositionedSpec = field(
        default_factory=_default_custom_text_spec)
    custom_text_line_spacing: float = 0.005

    def to_yaml_dict(self) -> dict:
        """将表单数据转换为 YAML 配置字典"""
        data = {}

        # name
        name_val = self.name.strip()
        data['name'] = name_val or 'Unnamed Style'

        # 竖图方向适配默认值（顶层可选字段，方案 §7.1）：
        # none 时显式省略字段保证旧样式输出简洁——不能依赖 _clean_dict()
        # 完成省略（'none' 是非空字符串不会被清理），必须是显式分支
        if self.default_portrait_adaptation != ADAPT_NONE:
            data['default_portrait_adaptation'] = self.default_portrait_adaptation

        # colors
        colors = {}
        colors['text'] = '#000000'
        if self.color_light.strip():
            colors['custom_text_light_color'] = _parse_color(self.color_light)
        if self.color_dark.strip():
            colors['custom_text_dark_color'] = _parse_color(self.color_dark)

        # 自定义背景填充色
        if self.custom_bg_color.strip():
            colors['custom_bg_color'] = _parse_color(self.custom_bg_color)
        if self.custom_bg_text_scheme.strip():
            colors['custom_bg_text_scheme'] = self.custom_bg_text_scheme

        for k in COLOR_ELEMENT_KEYS:
            pe = self.color_per_element.get(k, {})
            cl = pe.get('light', '').strip() if isinstance(pe, dict) else ''
            cd = pe.get('dark', '').strip() if isinstance(pe, dict) else ''
            if cl:
                colors[f'custom_{k}_light_color'] = _parse_color(cl)
            if cd:
                colors[f'custom_{k}_dark_color'] = _parse_color(cd)

        # 合并透传容器（colors 白名单外键原样回写；表单生成的键放在
        # 后面，正常情况下两集合不相交，此处仅防御同名冲突）
        colors = {**self._passthrough_colors, **colors}
        data['colors'] = colors

        # fonts
        fonts = {'size_ratio': self.font_size_ratio}

        # Latin
        latin = {}
        if self.font_latin_system:
            latin['system'] = 'Segoe UI'
        else:
            latin_family = self.font_latin_family.strip()
            if latin_family:
                latin['family'] = latin_family
                latin['weights'] = self.font_latin_weights
        latin['weight'] = self.font_latin_weight
        if latin:
            fonts['latin'] = latin

        # CJK
        cjk = {}
        if self.font_cjk_system:
            cjk['system'] = 'Microsoft JhengHei UI'
        else:
            cjk_family = self.font_cjk_family.strip()
            if cjk_family:
                cjk['family'] = cjk_family
                cjk['weights'] = self.font_cjk_weights
        cjk['weight'] = self.font_cjk_weight
        if cjk:
            fonts['cjk'] = cjk

        if self.font_line_spacing:
            fonts['line_spacing_ratio'] = self.font_line_spacing

        sizes = {k: v for k, v in self.font_sizes.items() if v is not None}
        if sizes:
            fonts['sizes'] = sizes
        data['fonts'] = fonts

        # layout
        layout = {}

        # expand_canvas
        layout['expand_canvas'] = {
            'enabled': self.canvas_enabled,
            'top': self.canvas_top,
            'bottom': self.canvas_bottom,
            'left': self.canvas_left,
            'right': self.canvas_right,
        }

        # padding
        layout['padding'] = {
            'top': self.pad_top,
            'bottom': self.pad_bottom,
            'left': self.pad_left,
            'right': self.pad_right,
        }

        # corner_radius
        if self.cr_enabled:
            layout['corner_radius'] = {
                'enabled': True,
                'top_left': self.cr_tl,
                'top_right': self.cr_tr,
                'bottom_left': self.cr_bl,
                'bottom_right': self.cr_br,
            }

        # info_position（G1：序列化单点在 PositionedSpec.to_entry）
        info_pos = {}
        for elem in self.elements:
            info_pos[elem.key] = elem.to_entry()
        layout['info_position'] = info_pos

        # defined_texts
        if self.defined_texts:
            defined_cfg = {}
            for dt_item in self.defined_texts:
                dkey = dt_item.key.strip()
                if not dkey:
                    continue
                dentry = {'content': dt_item.content}
                dentry.update(dt_item.to_entry())
                defined_cfg[dkey] = dentry
            if defined_cfg:
                layout['defined_texts'] = defined_cfg

        # custom_text
        if self.custom_text_enabled:
            spec = self.custom_text_spec
            ct = {'enabled': True}
            # 相对模式且引用非空才写相对分支；引用为空回退绝对
            # 分支（既有行为保留）
            use_relative = (spec.mode == 'relative'
                            and spec.relative_to.strip())
            if use_relative:
                ct['relative_to'] = spec.relative_to.strip()
                ct.update(spec._relative_entry())
            else:
                ct.update(spec._absolute_entry())
            # 行内对齐与模式无关（to_entry 的公共修饰在分支外重做，
            # 因本段 relative_to 的 strip 写法不经过 to_entry）
            if spec.line_alignment != 'left':
                ct['line_alignment'] = spec.line_alignment
            if self.custom_text_line_spacing:
                ct['line_spacing_ratio'] = self.custom_text_line_spacing
            layout['custom_text'] = ct

        # 合并透传容器（layout 未识别子字典如 rectangles 原样回写；
        # 表单生成的键放在后面，正常情况下两集合不相交）
        layout = {**self._passthrough_layout, **layout}
        data['layout'] = layout

        # logo（G1：定位字段经 PositionedSpec 分支方法单点序列化；
        # Logo 不消费 line_alignment/tree_align，故不经 to_entry）
        if self.logo_enabled:
            spec = self.logo_spec
            logo = {
                'enabled': True,
                'size_ratio': self.logo_size_ratio,
                'diagonal_limit_ratio': self.logo_diagonal_limit,
            }
            # 相对模式且引用非空才写相对分支（既有行为保留）
            use_relative = (self.logo_mode == 'relative'
                            and spec.relative_to)
            if use_relative:
                logo['relative_to'] = spec.relative_to
                logo.update(spec._relative_entry())
            else:
                logo.update(spec._absolute_entry())
        else:
            logo = {'enabled': False}
        # 合并透传容器（logo 未识别键原样回写；表单生成的键放在后面，
        # 正常情况下两集合不相交，此处仅防御同名冲突）
        logo = {**self._passthrough_logo, **logo}
        data['logo'] = logo

        return _clean_dict(data)

    def save_to_file(self, filepath: str) -> str:
        """序列化为 YAML 并写入文件，返回 YAML 字符串"""
        config = self.to_yaml_dict()
        yaml_str = _build_yaml_config(config)

        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(yaml_str)

        return yaml_str

    def clone(self):
        """深拷贝"""
        return copy.deepcopy(self)

    @classmethod
    def from_yaml_dict(cls, data: dict):
        """从 YAML 配置字典加载表单数据"""
        if not isinstance(data, dict):
            return cls()

        form = cls()

        # name
        form.name = str(data.get('name', ''))

        # 竖图方向适配默认值（方案 §7.1）：字段缺失加载为 none；存在但
        # 非法时 raise ValueError——StyleCreatorPage._on_style_selected()
        # 的既有 try/except 会以 InfoBar"加载失败"呈现，无需在此回退
        form.default_portrait_adaptation = validate_style_default(data)

        # colors
        colors = data.get('colors', {})

        # 收集 colors 白名单外键（如 custom_rect_01_light_color 等
        # 自定义矩形颜色），to_yaml_dict() 时原样回写。
        # deepcopy 避免与外部传入的 config dict 共享可变引用。
        consumed_color_keys = {
            'text',
            'custom_text_light_color', 'custom_text_dark_color',
            'custom_bg_color', 'custom_bg_text_scheme',
        }
        for k in COLOR_ELEMENT_KEYS:
            consumed_color_keys.add(f'custom_{k}_light_color')
            consumed_color_keys.add(f'custom_{k}_dark_color')
        form._passthrough_colors = {
            k: copy.deepcopy(v) for k, v in colors.items()
            if k not in consumed_color_keys
        }

        form.color_light = _color_to_text(
            colors.get('custom_text_light_color', ''))
        form.color_dark = _color_to_text(
            colors.get('custom_text_dark_color', ''))

        form.custom_bg_color = _color_to_text(
            colors.get('custom_bg_color', ''))
        form.custom_bg_text_scheme = str(
            colors.get('custom_bg_text_scheme', ''))

        for k in COLOR_ELEMENT_KEYS:
            pe = {}
            cl = colors.get(f'custom_{k}_light_color')
            cd = colors.get(f'custom_{k}_dark_color')
            if cl:
                pe['light'] = _color_to_text(cl)
            if cd:
                pe['dark'] = _color_to_text(cd)
            if pe:
                form.color_per_element[k] = pe

        # fonts
        fonts = data.get('fonts', {})
        latin_cfg = fonts.get('latin', {})
        cjk_cfg = fonts.get('cjk', {})
        # 向后兼容：旧格式 {family, weight}
        if 'family' in fonts and 'latin' not in fonts:
            latin_cfg = {
                'family': fonts['family'],
                'weight': fonts.get('weight', 'medium'),
            }

        form.font_latin_family = latin_cfg.get('family', '')
        form.font_latin_weight = latin_cfg.get('weight', 'medium')
        form.font_latin_system = bool(latin_cfg.get('system'))
        form.font_cjk_family = cjk_cfg.get('family', '')
        form.font_cjk_weight = cjk_cfg.get('weight', 'medium')
        form.font_cjk_system = bool(cjk_cfg.get('system'))
        form.font_latin_weights = latin_cfg.get(
            'weights', {}) or {'light': 'Light', 'regular': 'Book', 'medium': 'Medium'}
        form.font_cjk_weights = cjk_cfg.get(
            'weights', {}) or {'light': 'Light', 'regular': 'Regular', 'medium': 'Medium'}
        form.font_size_ratio = float(fonts.get('size_ratio', 0.015))
        form.font_line_spacing = float(
            fonts.get('line_spacing_ratio', 0.005))

        # 逐元素字号不设白名单：白名单会丢弃 defined_text_01 等实例键，
        # 而 core text_renderer 按 key（含实例键）查逐元素字号
        # （G15b 修复：实例字号经 GUI 读写后静默丢失）。未识别键原样保留。
        form.font_sizes = dict(fonts.get('sizes', {}) or {})

        # layout
        layout = data.get('layout', {})

        # 收集表单未识别的 layout 子字典（如 rectangles——矩形配置本期
        # 不支持 GUI 编辑），to_yaml_dict() 时原样回写，保证"加载→保存"
        # 不丢配置。deepcopy 避免与外部传入的 config dict 共享可变引用。
        consumed_layout_keys = {
            'expand_canvas', 'padding', 'corner_radius',
            'info_position', 'defined_texts', 'custom_text',
        }
        form._passthrough_layout = {
            k: copy.deepcopy(v) for k, v in layout.items()
            if k not in consumed_layout_keys
        }

        # expand_canvas
        ec = layout.get('expand_canvas', {})
        form.canvas_enabled = bool(ec.get('enabled', True))
        form.canvas_top = float(ec.get('top', 0.0))
        form.canvas_bottom = float(ec.get('bottom', 0.0))
        form.canvas_left = float(ec.get('left', 0.0))
        form.canvas_right = float(ec.get('right', 0.0))

        # padding
        pad = layout.get('padding', {})
        if pad:
            form.pad_top = float(pad.get('top', 0.0))
            form.pad_bottom = float(pad.get('bottom', 0.0))
            form.pad_left = float(pad.get('left', 0.0))
            form.pad_right = float(pad.get('right', 0.0))
        else:
            form.pad_top = form.pad_bottom = form.pad_left = form.pad_right = 0.0

        # corner_radius
        cr = layout.get('corner_radius', {})
        if cr:
            form.cr_enabled = bool(cr.get('enabled', False))
            form.cr_tl = float(cr.get('top_left', 0.01))
            form.cr_tr = float(cr.get('top_right', 0.01))
            form.cr_bl = float(cr.get('bottom_left', 0.01))
            form.cr_br = float(cr.get('bottom_right', 0.01))
        else:
            form.cr_enabled = False

        # info_position -> elements（G1：反序列化单点在 update_from_entry）
        ip = layout.get('info_position', {})
        elements = []
        elem_id = 1
        for key, entry in ip.items():
            if not isinstance(entry, dict):
                continue
            elem = ElementConfig(id=elem_id, key=key)
            # 元素列表语义：含 relative_to 键即相对模式（含空串）
            elem.update_from_entry(entry, relative_if_present=True)
            elements.append(elem)
            elem_id += 1
        form.elements = elements if elements else [_make_default_element()]

        # logo（G1：定位字段经 PositionedSpec.update_from_entry 单点填充，
        # 以 Logo 默认 spec 为基础，缺失键保留宿主默认值）
        logo = data.get('logo', {})
        if isinstance(logo, dict):
            # logo 段未识别键透传（G15c：如 max_dim_limit_ratio），
            # to_yaml_dict() 时原样回写。deepcopy 避免与外部传入的
            # config dict 共享可变引用。
            consumed_logo_keys = {
                'enabled', 'size_ratio', 'diagonal_limit_ratio',
                'placement', 'position', 'alignment', 'margin',
                'margin_top', 'margin_bottom', 'margin_left', 'margin_right',
                'relative_to', 'relative_position', 'cross_alignment',
                'relative_margin', 'offset_x_ratio', 'offset_y_ratio',
            }
            form._passthrough_logo = {
                k: copy.deepcopy(v) for k, v in logo.items()
                if k not in consumed_logo_keys
            }
            form.logo_enabled = bool(logo.get('enabled', False))
            form.logo_size_ratio = float(logo.get('size_ratio', 0.04))
            form.logo_diagonal_limit = float(
                logo.get('diagonal_limit_ratio', 2.0))
            form.logo_spec = _default_logo_spec()
            # logo/custom_text 段语义：relative_to 为非空值才判相对模式
            form.logo_spec.update_from_entry(logo, relative_if_present=False)
            form.logo_mode = form.logo_spec.mode
        else:
            form.logo_enabled = False

        # defined_texts（G1：反序列化单点在 update_from_entry）
        defined_texts_config = layout.get('defined_texts', {})
        dt_list = []
        dt_id = 1
        for dt_key, dt_entry in defined_texts_config.items():
            if not isinstance(dt_entry, dict):
                continue
            dt_item = DefinedTextConfig(
                id=dt_id, key=dt_key,
                content=dt_entry.get('content', ''))
            # 预定义文本语义：relative_to 非空才判相对模式
            #（空串视为 rooted 绝对定位，既有行为保留）
            dt_item.update_from_entry(dt_entry, relative_if_present=False)
            dt_list.append(dt_item)
            dt_id += 1
        form.defined_texts = dt_list

        # custom_text（G1：定位 + line_alignment 收拢于 custom_text_spec）
        ct_cfg = layout.get('custom_text', {})
        if isinstance(ct_cfg, dict):
            form.custom_text_enabled = bool(ct_cfg.get('enabled', False))
            form.custom_text_line_spacing = float(
                ct_cfg.get('line_spacing_ratio', 0.005))
            form.custom_text_spec = _default_custom_text_spec()
            form.custom_text_spec.update_from_entry(
                ct_cfg, relative_if_present=False)
            form.custom_text_mode = form.custom_text_spec.mode
        else:
            form.custom_text_enabled = False

        return form

    @classmethod
    def load_from_file(cls, filepath: str):
        """从 YAML 文件加载表单数据"""
        with open(filepath, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        form = cls.from_yaml_dict(config)
        return form
