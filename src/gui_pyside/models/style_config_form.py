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


# ── 常量 ────────────────────────────────────────────────────

ELEMENT_KEYS = [
    'exif', 'timestamp', 'timestamp_author', 'camera', 'lens',
    'camera_lens', 'camera_make', 'author', 'location', 'gps',
    'focal_length_formatted', 'aperture_formatted',
    'shutter_speed_formatted', 'iso_formatted',
    'custom_text', 'defined_text',
]

PLACEMENT_OPTIONS = ['outside', 'inside']

ANCHOR_POSITION_OPTIONS = [
    'bottom-left', 'bottom-center', 'bottom-right',
    'top-left', 'top-center', 'top-right',
    'left', 'right', 'top', 'bottom', 'center',
]

ALIGNMENT_OPTIONS = [
    'left', 'center', 'both-center', 'right',
    'top-left', 'top-right', 'top', 'bottom',
]

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
class ElementConfig:
    """单个 info_position 元素的配置"""
    id: int = 0
    key: str = 'exif'
    mode: str = 'absolute'
    placement: str = 'outside'
    position: str = 'bottom-left'
    alignment: str = 'left'
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


@dataclass
class DefinedTextConfig:
    """单个预定义文本条目"""
    id: int = 0
    key: str = ''
    content: str = ''
    mode: str = 'absolute'
    tree_align: bool = False
    placement: str = 'outside'
    position: str = 'bottom-left'
    alignment: str = 'left'
    margin_top: float = 0.0
    margin_bottom: float = 0.0
    margin_left: float = 0.0
    margin_right: float = 0.0
    relative_to: str = 'exif'
    relative_position: str = 'right-of'
    relative_margin: float = 0.01
    offset_x: float = 0.0
    offset_y: float = 0.0


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


def _build_yaml_config(data: dict) -> str:
    """将 dict 序列化为 YAML 字符串，列表使用 flow_style"""
    def flow_list(dumper, seq):
        return dumper.represent_sequence(
            'tag:yaml.org,2002:seq', seq, flow_style=True)

    dumper = yaml.Dumper
    dumper.add_representer(list, flow_list)

    return yaml.dump(
        data, Dumper=dumper, sort_keys=False,
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
    logo_enabled: bool = False
    logo_mode: str = 'absolute'
    logo_placement: str = 'outside'
    logo_position: str = 'top-right'
    logo_alignment: str = 'top-right'
    logo_size_ratio: float = 0.04
    logo_diagonal_limit: float = 2.0
    logo_mt: float = 0.0
    logo_mb: float = 0.0
    logo_ml: float = 0.0
    logo_mr: float = 0.0
    logo_relative_to: str = ''
    logo_relative_position: str = 'below'
    logo_relative_margin: float = 0.01
    logo_offset_x: float = 0.0
    logo_offset_y: float = 0.0

    # ── 颜色 ──
    color_light: str = ''
    color_dark: str = ''
    color_per_element: dict = field(default_factory=dict)

    # ── 元素布局 ──
    elements: list = field(default_factory=lambda: [_make_default_element()])

    # ── 预定义文本 ──
    defined_texts: list = field(default_factory=list)

    # ── 自定义文本 ──
    custom_text_enabled: bool = False
    custom_text_mode: str = 'absolute'
    custom_text_placement: str = 'outside'
    custom_text_position: str = 'bottom-center'
    custom_text_alignment: str = 'center'
    custom_text_mt: float = 0.0
    custom_text_mb: float = 0.0
    custom_text_ml: float = 0.0
    custom_text_mr: float = 0.0
    custom_text_relative_to: str = ''
    custom_text_relative_position: str = 'below'
    custom_text_relative_margin: float = 0.01
    custom_text_offset_x: float = 0.0
    custom_text_offset_y: float = 0.0
    custom_text_line_spacing: float = 0.005

    def to_yaml_dict(self) -> dict:
        """将表单数据转换为 YAML 配置字典"""
        data = {}

        # name
        name_val = self.name.strip()
        data['name'] = name_val or 'Unnamed Style'

        # colors
        colors = {}
        colors['text'] = '#000000'
        if self.color_light.strip():
            colors['custom_text_light_color'] = _parse_color(self.color_light)
        if self.color_dark.strip():
            colors['custom_text_dark_color'] = _parse_color(self.color_dark)

        for k in COLOR_ELEMENT_KEYS:
            pe = self.color_per_element.get(k, {})
            cl = pe.get('light', '').strip() if isinstance(pe, dict) else ''
            cd = pe.get('dark', '').strip() if isinstance(pe, dict) else ''
            if cl:
                colors[f'custom_{k}_light_color'] = _parse_color(cl)
            if cd:
                colors[f'custom_{k}_dark_color'] = _parse_color(cd)
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

        # info_position
        info_pos = {}
        for elem in self.elements:
            key = elem.key
            if elem.mode == 'absolute':
                entry = {
                    'placement': elem.placement,
                    'position': elem.position,
                    'alignment': elem.alignment,
                    'margin_top': elem.margin_top,
                    'margin_bottom': elem.margin_bottom,
                    'margin_left': elem.margin_left,
                    'margin_right': elem.margin_right,
                }
            else:
                entry = {
                    'relative_to': elem.relative_to,
                    'relative_position': elem.relative_position,
                    'alignment': elem.alignment,
                    'relative_margin': elem.relative_margin,
                }
                if elem.offset_x != 0.0:
                    entry['offset_x_ratio'] = elem.offset_x
                if elem.offset_y != 0.0:
                    entry['offset_y_ratio'] = elem.offset_y
            if elem.tree_align:
                entry['tree_align'] = True
            info_pos[key] = entry
        layout['info_position'] = info_pos

        # defined_texts
        if self.defined_texts:
            defined_cfg = {}
            for dt_item in self.defined_texts:
                dkey = dt_item.key.strip()
                if not dkey:
                    continue
                dentry = {'content': dt_item.content}
                if dt_item.mode == 'absolute':
                    dentry['placement'] = dt_item.placement
                    dentry['position'] = dt_item.position
                    dentry['alignment'] = dt_item.alignment
                    dentry['margin_top'] = dt_item.margin_top
                    dentry['margin_bottom'] = dt_item.margin_bottom
                    dentry['margin_left'] = dt_item.margin_left
                    dentry['margin_right'] = dt_item.margin_right
                    if dt_item.tree_align:
                        dentry['tree_align'] = True
                else:
                    dentry['relative_to'] = dt_item.relative_to
                    dentry['relative_position'] = dt_item.relative_position
                    dentry['alignment'] = dt_item.alignment
                    dentry['relative_margin'] = dt_item.relative_margin
                    if dt_item.offset_x != 0.0:
                        dentry['offset_x_ratio'] = dt_item.offset_x
                    if dt_item.offset_y != 0.0:
                        dentry['offset_y_ratio'] = dt_item.offset_y
                defined_cfg[dkey] = dentry
            if defined_cfg:
                layout['defined_texts'] = defined_cfg

        # custom_text
        if self.custom_text_enabled:
            ct = {'enabled': True}
            if self.custom_text_mode == 'relative' and self.custom_text_relative_to.strip():
                ct['relative_to'] = self.custom_text_relative_to.strip()
                ct['relative_position'] = self.custom_text_relative_position
                ct['alignment'] = self.custom_text_alignment
                ct['relative_margin'] = self.custom_text_relative_margin
                if self.custom_text_offset_x != 0.0:
                    ct['offset_x_ratio'] = self.custom_text_offset_x
                if self.custom_text_offset_y != 0.0:
                    ct['offset_y_ratio'] = self.custom_text_offset_y
            else:
                ct['placement'] = self.custom_text_placement
                ct['position'] = self.custom_text_position
                ct['alignment'] = self.custom_text_alignment
                ct['margin_top'] = self.custom_text_mt
                ct['margin_bottom'] = self.custom_text_mb
                ct['margin_left'] = self.custom_text_ml
                ct['margin_right'] = self.custom_text_mr
            if self.custom_text_line_spacing:
                ct['line_spacing_ratio'] = self.custom_text_line_spacing
            layout['custom_text'] = ct

        data['layout'] = layout

        # logo
        if self.logo_enabled:
            logo = {
                'enabled': True,
                'alignment': self.logo_alignment,
                'size_ratio': self.logo_size_ratio,
                'diagonal_limit_ratio': self.logo_diagonal_limit,
            }
            if self.logo_mode == 'relative' and self.logo_relative_to:
                logo['relative_to'] = self.logo_relative_to
                logo['relative_position'] = self.logo_relative_position
                logo['relative_margin'] = self.logo_relative_margin
                if self.logo_offset_x != 0.0:
                    logo['offset_x_ratio'] = self.logo_offset_x
                if self.logo_offset_y != 0.0:
                    logo['offset_y_ratio'] = self.logo_offset_y
            else:
                logo['placement'] = self.logo_placement
                logo['position'] = self.logo_position
                logo['margin_top'] = self.logo_mt
                logo['margin_bottom'] = self.logo_mb
                logo['margin_left'] = self.logo_ml
                logo['margin_right'] = self.logo_mr
        else:
            logo = {'enabled': False}
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

        # colors
        colors = data.get('colors', {})
        form.color_light = _color_to_text(
            colors.get('custom_text_light_color', ''))
        form.color_dark = _color_to_text(
            colors.get('custom_text_dark_color', ''))

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

        sizes = fonts.get('sizes', {}) or {}
        form.font_sizes = {}
        for k in COLOR_ELEMENT_KEYS:
            if k in sizes:
                form.font_sizes[k] = sizes[k]

        # layout
        layout = data.get('layout', {})

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

        # info_position -> elements
        ip = layout.get('info_position', {})
        elements = []
        elem_id = 1
        for key, entry in ip.items():
            if not isinstance(entry, dict):
                continue
            if 'relative_to' in entry:
                elem = ElementConfig(
                    id=elem_id,
                    key=key,
                    mode='relative',
                    placement=str(entry.get('placement', 'outside')),
                    relative_to=str(entry.get('relative_to', 'exif')),
                    relative_position=str(
                        entry.get('relative_position', 'below')),
                    alignment=str(entry.get('alignment', 'left')),
                    relative_margin=float(
                        entry.get('relative_margin', 0.01)),
                    offset_x=float(entry.get('offset_x_ratio', 0.0)),
                    offset_y=float(entry.get('offset_y_ratio', 0.0)),
                    tree_align=bool(entry.get('tree_align', False)),
                )
            else:
                # 统一 margin 作为独立 margin 的兜底
                default_marg = entry.get('margin')
                elem = ElementConfig(
                    id=elem_id,
                    key=key,
                    mode='absolute',
                    placement=str(entry.get('placement', 'outside')),
                    position=str(entry.get('position', 'bottom-left')),
                    alignment=str(entry.get('alignment', 'left')),
                    margin_top=float(
                        entry.get('margin_top', default_marg
                                  if default_marg is not None else 0.0)),
                    margin_bottom=float(
                        entry.get('margin_bottom', default_marg
                                  if default_marg is not None else 0.0)),
                    margin_left=float(
                        entry.get('margin_left', default_marg
                                  if default_marg is not None else 0.0)),
                    margin_right=float(
                        entry.get('margin_right', default_marg
                                  if default_marg is not None else 0.0)),
                    tree_align=bool(entry.get('tree_align', False)),
                )
            elements.append(elem)
            elem_id += 1
        form.elements = elements if elements else [_make_default_element()]

        # logo
        logo = data.get('logo', {})
        if isinstance(logo, dict):
            form.logo_enabled = bool(logo.get('enabled', False))
            form.logo_placement = str(logo.get('placement', 'outside'))
            form.logo_position = str(logo.get('position', 'top-right'))
            form.logo_alignment = str(logo.get('alignment', 'top-right'))
            form.logo_size_ratio = float(logo.get('size_ratio', 0.04))
            form.logo_diagonal_limit = float(
                logo.get('diagonal_limit_ratio', 2.0))
            _logo_marg = logo.get('margin')
            form.logo_mt = float(
                logo.get('margin_top', _logo_marg
                         if _logo_marg is not None else 0.0))
            form.logo_mb = float(
                logo.get('margin_bottom', _logo_marg
                         if _logo_marg is not None else 0.0))
            form.logo_ml = float(
                logo.get('margin_left', _logo_marg
                         if _logo_marg is not None else 0.0))
            form.logo_mr = float(
                logo.get('margin_right', _logo_marg
                         if _logo_marg is not None else 0.0))
            form.logo_relative_to = str(logo.get('relative_to', ''))
            form.logo_relative_position = str(
                logo.get('relative_position', 'below'))
            form.logo_relative_margin = float(
                logo.get('relative_margin', 0.01))
            form.logo_offset_x = float(logo.get('offset_x_ratio', 0.0))
            form.logo_offset_y = float(logo.get('offset_y_ratio', 0.0))
            form.logo_mode = 'relative' if logo.get(
                'relative_to') else 'absolute'
        else:
            form.logo_enabled = False

        # defined_texts
        defined_texts_config = layout.get('defined_texts', {})
        dt_list = []
        dt_id = 1
        for dt_key, dt_entry in defined_texts_config.items():
            if not isinstance(dt_entry, dict):
                continue
            content = dt_entry.get('content', '')
            rooted = 'relative_to' not in dt_entry or not dt_entry.get(
                'relative_to')
            mode = 'absolute' if rooted else 'relative'
            _dt_marg = dt_entry.get('margin')
            dt_item = DefinedTextConfig(
                id=dt_id,
                key=dt_key,
                content=content,
                mode=mode,
                tree_align=bool(dt_entry.get('tree_align', False)),
                placement=str(dt_entry.get('placement', 'outside')),
                position=str(dt_entry.get('position', 'bottom-left')),
                alignment=str(dt_entry.get('alignment', 'left')),
                margin_top=float(
                    dt_entry.get('margin_top', _dt_marg
                                 if _dt_marg is not None else 0.0)),
                margin_bottom=float(
                    dt_entry.get('margin_bottom', _dt_marg
                                 if _dt_marg is not None else 0.0)),
                margin_left=float(
                    dt_entry.get('margin_left', _dt_marg
                                 if _dt_marg is not None else 0.0)),
                margin_right=float(
                    dt_entry.get('margin_right', _dt_marg
                                 if _dt_marg is not None else 0.0)),
                relative_to=str(dt_entry.get('relative_to', 'exif')),
                relative_position=str(
                    dt_entry.get('relative_position', 'right-of')),
                relative_margin=float(dt_entry.get('relative_margin', 0.01)),
                offset_x=float(dt_entry.get('offset_x_ratio', 0.0)),
                offset_y=float(dt_entry.get('offset_y_ratio', 0.0)),
            )
            dt_list.append(dt_item)
            dt_id += 1
        form.defined_texts = dt_list

        # custom_text
        ct_cfg = layout.get('custom_text', {})
        if isinstance(ct_cfg, dict):
            form.custom_text_enabled = bool(ct_cfg.get('enabled', False))
            form.custom_text_placement = str(
                ct_cfg.get('placement', 'outside'))
            form.custom_text_position = str(
                ct_cfg.get('position', 'bottom-center'))
            form.custom_text_alignment = str(
                ct_cfg.get('alignment', 'center'))
            _ct_marg = ct_cfg.get('margin')
            form.custom_text_mt = float(
                ct_cfg.get('margin_top', _ct_marg
                           if _ct_marg is not None else 0.0))
            form.custom_text_mb = float(
                ct_cfg.get('margin_bottom', _ct_marg
                           if _ct_marg is not None else 0.0))
            form.custom_text_ml = float(
                ct_cfg.get('margin_left', _ct_marg
                           if _ct_marg is not None else 0.0))
            form.custom_text_mr = float(
                ct_cfg.get('margin_right', _ct_marg
                           if _ct_marg is not None else 0.0))
            form.custom_text_line_spacing = float(
                ct_cfg.get('line_spacing_ratio', 0.005))
            form.custom_text_relative_to = str(
                ct_cfg.get('relative_to', ''))
            form.custom_text_relative_position = str(
                ct_cfg.get('relative_position', 'below'))
            form.custom_text_relative_margin = float(
                ct_cfg.get('relative_margin', 0.01))
            form.custom_text_offset_x = float(
                ct_cfg.get('offset_x_ratio', 0.0))
            form.custom_text_offset_y = float(
                ct_cfg.get('offset_y_ratio', 0.0))
            form.custom_text_mode = 'relative' if ct_cfg.get(
                'relative_to') else 'absolute'
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
