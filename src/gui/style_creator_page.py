"""
样式编辑器页面模块
通过可视化表单创建和编辑相框样式 YAML 配置文件
"""
import streamlit as st
import os
import re
import ast
import yaml
import glob as glob_module


# ── 常量 ────────────────────────────────────────────────────

ELEMENT_KEYS = ['exif', 'timestamp', 'timestamp_author', 'camera', 'lens',
                'camera_lens', 'camera_make', 'author', 'location', 'gps',
                'focal_length_formatted', 'aperture_formatted',
                'shutter_speed_formatted', 'iso_formatted',
                'custom_text', 'defined_text']

PLACEMENT_OPTIONS = ['outside', 'inside']

ANCHOR_POSITION_OPTIONS = ['bottom-left', 'bottom-center', 'bottom-right',
                            'top-left', 'top-center', 'top-right',
                            'left', 'right', 'top', 'bottom', 'center']

ALIGNMENT_OPTIONS = ['left', 'center', 'right', 'top-left', 'top-right', 'top', 'bottom']

RELATIVE_POSITION_OPTIONS = ['below', 'above', 'left-of', 'right-of']

WEIGHT_OPTIONS = ['medium', 'regular', 'light']

CONFIGS_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), '..', 'frame_styles', 'configs'))

NEW_STYLE_PLACEHOLDER = '--- 新建样式 ---'

DEFAULT_ELEMENT = {
    'id': 0,
    'key': 'exif',
    'mode': 'absolute',
    'placement': 'outside',
    'position': 'bottom-left',
    'alignment': 'left',
    'margin_top': 0.0,
    'margin_bottom': 0.02,
    'margin_left': 0.0,
    'margin_right': 0.0,
    'relative_to': 'exif',
    'relative_position': 'below',
    'relative_margin': 0.01,
    'offset_x': 0.0,
    'offset_y': 0.0,
}


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


def _next_id():
    max_id = max((e['id'] for e in st.session_state.style_elements), default=0)
    return max_id + 1


def color_to_text(val) -> str:
    """将解析后的颜色值转为文本框显示字符串"""
    if val is None or val == '':
        return ''
    if isinstance(val, list):
        return str(val)
    return str(val)


def parse_color(value: str):
    v = value.strip()
    if not v:
        return None
    if v.startswith('['):
        try:
            return ast.literal_eval(v)
        except (ValueError, SyntaxError):
            return v
    return v


def parse_float_str(value: str, default=None):
    v = value.strip()
    if not v:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def sanitize_filename(name: str) -> str:
    """清理文件名，保留 / 以支持子目录"""
    name = name.strip()
    if not name:
        return 'NewStyle'
    name = re.sub(r'[\\*?:"<>|]', '', name)
    if not name.lower().endswith('.yaml'):
        name += '.yaml'
    return name.replace('\\', '/')


def build_yaml_config(data: dict) -> str:
    def flow_list(dumper, seq):
        return dumper.represent_sequence(
            'tag:yaml.org,2002:seq', seq, flow_style=True)

    dumper = yaml.Dumper
    dumper.add_representer(list, flow_list)

    return yaml.dump(data, Dumper=dumper, sort_keys=False,
                     allow_unicode=True, default_flow_style=False, width=120)


def _get_existing_styles():
    """返回 CONFIGS_DIR 下所有 .yaml 文件的相对路径列表 (含子目录变体, 排除 template)"""
    styles = []
    if not os.path.isdir(CONFIGS_DIR):
        return styles
    for entry in sorted(os.listdir(CONFIGS_DIR)):
        if entry.startswith('_'):
            continue
        full = os.path.join(CONFIGS_DIR, entry)
        if os.path.isdir(full):
            for variant in sorted(os.listdir(full)):
                if variant.lower().endswith('.yaml') and not variant.startswith('_'):
                    styles.append(os.path.join(entry, variant).replace('\\', '/'))
        elif entry.lower().endswith('.yaml'):
            styles.append(entry)
    return styles


# ── 加载 / 初始化 ────────────────────────────────────────────

def _init_new_style():
    """重置所有表单字段为默认值"""
    defaults = {
        'sc_name': '',
        'sc_filename': '',
        'sc_canvas_enabled': True,
        'sc_canvas_top': 0.03, 'sc_canvas_bottom': 0.12,
        'sc_canvas_left': 0.02, 'sc_canvas_right': 0.02,
        'sc_pad_top': 0.02, 'sc_pad_bottom': 0.02,
        'sc_pad_left': 0.02, 'sc_pad_right': 0.02,
        'sc_font_latin_family': '', 'sc_font_latin_weight': 'medium', 'sc_font_latin_system': False,
        'sc_font_cjk_family': '', 'sc_font_cjk_weight': 'medium', 'sc_font_cjk_system': False,
        'sc_font_size': 0.015,
        'sc_logo_enabled': False,
        'sc_logo_placement': 'outside', 'sc_logo_position': 'top-right',
        'sc_logo_alignment': 'top-right',
        'sc_logo_size': 0.04, 'sc_logo_mt': 0.0, 'sc_logo_mb': 0.0,
        'sc_logo_ml': 0.0, 'sc_logo_mr': 0.0,
        'sc_logo_relative_to': '', 'sc_logo_relative_position': 'below',
        'sc_logo_relative_margin': 0.01, 'sc_logo_offset_x': 0.0, 'sc_logo_offset_y': 0.0,
        'sc_logo_mode': 'absolute',
        'sc_color_light': '', 'sc_color_dark': '',
        'sc_font_line_spacing': 0.005,
        'style_elements': [DEFAULT_ELEMENT.copy()],
        'sc_defined_texts': [],
        'sc_ct_enabled': False,
        'sc_ct_placement': 'outside',
        'sc_ct_position': 'bottom-center',
        'sc_ct_alignment': 'center',
        'sc_ct_mt': 0.0, 'sc_ct_mb': 0.0, 'sc_ct_ml': 0.0, 'sc_ct_mr': 0.0,
        'sc_ct_line_spacing': 0.005,
        'sc_ct_relative_to': '', 'sc_ct_relative_position': 'below',
        'sc_ct_relative_margin': 0.01,
        'sc_ct_offset_x': 0.0, 'sc_ct_offset_y': 0.0,
        'sc_ct_mode': 'absolute',
        'sc_loaded_style': NEW_STYLE_PLACEHOLDER,
    }
    # per-element font sizes
    for k in ['exif', 'timestamp', 'timestamp_author', 'camera', 'camera_make',
              'lens', 'camera_lens', 'author', 'location', 'gps',
              'focal_length_formatted', 'aperture_formatted',
              'shutter_speed_formatted', 'iso_formatted', 'custom_text']:
        defaults[f'sc_font_{k}'] = ''
    # per-element colors
    for k in ['exif', 'timestamp', 'timestamp_author', 'camera', 'camera_make',
              'lens', 'camera_lens', 'author', 'location', 'gps',
              'focal_length_formatted', 'aperture_formatted',
              'shutter_speed_formatted', 'iso_formatted', 'custom_text']:
        defaults[f'sc_color_{k}_light'] = ''
        defaults[f'sc_color_{k}_dark'] = ''
    for key, val in defaults.items():
        st.session_state[key] = val


def _load_existing_style(filename: str):
    """从 YAML 文件加载配置到 session_state"""
    filepath = os.path.join(CONFIGS_DIR, filename)
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        st.error(f'加载失败: {e}')
        return

    if not isinstance(config, dict):
        st.error('无效的配置文件格式')
        return

    # name
    st.session_state.sc_name = str(config.get('name', ''))

    # filename
    st.session_state.sc_filename = filename

    # colors
    colors = config.get('colors', {})
    st.session_state.sc_color_light = color_to_text(
        colors.get('custom_text_light_color', ''))
    st.session_state.sc_color_dark = color_to_text(
        colors.get('custom_text_dark_color', ''))
    for k in ['exif', 'timestamp', 'timestamp_author', 'camera', 'camera_make',
              'lens', 'camera_lens', 'author', 'location', 'gps',
              'focal_length_formatted', 'aperture_formatted',
              'shutter_speed_formatted', 'iso_formatted', 'custom_text']:
        st.session_state[f'sc_color_{k}_light'] = color_to_text(
            colors.get(f'custom_{k}_light_color', ''))
        st.session_state[f'sc_color_{k}_dark'] = color_to_text(
            colors.get(f'custom_{k}_dark_color', ''))

    # fonts
    fonts = config.get('fonts', {})
    latin_cfg = fonts.get('latin', {})
    cjk_cfg = fonts.get('cjk', {})
    # 向后兼容：旧格式 {family, weight}
    if 'family' in fonts and 'latin' not in fonts:
        latin_cfg = {'family': fonts['family'], 'weight': fonts.get('weight', 'medium')}
    st.session_state.sc_font_latin_family = latin_cfg.get('family', '')
    st.session_state.sc_font_latin_weight = latin_cfg.get('weight', 'medium')
    st.session_state.sc_font_latin_system = bool(latin_cfg.get('system'))
    st.session_state.sc_font_cjk_family = cjk_cfg.get('family', '')
    st.session_state.sc_font_cjk_weight = cjk_cfg.get('weight', 'medium')
    st.session_state.sc_font_cjk_system = bool(cjk_cfg.get('system'))
    st.session_state.sc_font_size = float(fonts.get('size_ratio', 0.015))
    st.session_state.sc_font_line_spacing = float(fonts.get('line_spacing_ratio', 0.005))
    sizes = fonts.get('sizes', {}) or {}
    for k in ['exif', 'timestamp', 'timestamp_author', 'camera', 'camera_make',
              'lens', 'camera_lens', 'author', 'location', 'gps',
              'focal_length_formatted', 'aperture_formatted',
              'shutter_speed_formatted', 'iso_formatted', 'custom_text']:
        if k in sizes:
            st.session_state[f'sc_font_{k}'] = str(sizes[k])
        else:
            st.session_state[f'sc_font_{k}'] = ''

    # layout
    layout = config.get('layout', {})

    # expand_canvas
    ec = layout.get('expand_canvas', {})
    st.session_state.sc_canvas_enabled = bool(ec.get('enabled', True))
    st.session_state.sc_canvas_top = float(ec.get('top', 0.0))
    st.session_state.sc_canvas_bottom = float(ec.get('bottom', 0.0))
    st.session_state.sc_canvas_left = float(ec.get('left', 0.0))
    st.session_state.sc_canvas_right = float(ec.get('right', 0.0))

    # padding
    pad = layout.get('padding', {})
    if pad:
        st.session_state.sc_pad_top = float(pad.get('top', 0.0))
        st.session_state.sc_pad_bottom = float(pad.get('bottom', 0.0))
        st.session_state.sc_pad_left = float(pad.get('left', 0.0))
        st.session_state.sc_pad_right = float(pad.get('right', 0.0))
    else:
        st.session_state.sc_pad_top = 0.0
        st.session_state.sc_pad_bottom = 0.0
        st.session_state.sc_pad_left = 0.0
        st.session_state.sc_pad_right = 0.0

    # corner_radius
    cr = layout.get('corner_radius', {})
    st.session_state.sc_cr_enabled = bool(cr.get('enabled', False)) if cr else False
    st.session_state.sc_cr_tl = float(cr.get('top_left', 0.01)) if cr else 0.01
    st.session_state.sc_cr_tr = float(cr.get('top_right', 0.01)) if cr else 0.01
    st.session_state.sc_cr_bl = float(cr.get('bottom_left', 0.01)) if cr else 0.01
    st.session_state.sc_cr_br = float(cr.get('bottom_right', 0.01)) if cr else 0.01

    # info_position → style_elements
    ip = layout.get('info_position', {})
    elements = []
    elem_id = 1
    for key, entry in ip.items():
        if not isinstance(entry, dict):
            continue
        if 'relative_to' in entry:
            elem = {
                'id': elem_id,
                'key': key,
                'mode': 'relative',
                'placement': str(entry.get('placement', 'outside')),
                'relative_to': str(entry.get('relative_to', 'exif')),
                'relative_position': str(entry.get('relative_position', 'below')),
                'alignment': str(entry.get('alignment', 'left')),
                'relative_margin': float(entry.get('relative_margin', 0.01)),
                'offset_x': float(entry.get('offset_x_ratio', 0.0)),
                'offset_y': float(entry.get('offset_y_ratio', 0.0)),
                # keep absolute defaults for potential mode switch
                'position': 'bottom-left',
                'margin_top': 0.0, 'margin_bottom': 0.0,
                'margin_left': 0.0, 'margin_right': 0.0,
            }
        else:
            elem = {
                'id': elem_id,
                'key': key,
                'mode': 'absolute',
                'placement': str(entry.get('placement', 'outside')),
                'position': str(entry.get('position', 'bottom-left')),
                'alignment': str(entry.get('alignment', 'left')),
                'margin_top': float(entry.get('margin_top', 0.0)),
                'margin_bottom': float(entry.get('margin_bottom', 0.0)),
                'margin_left': float(entry.get('margin_left', 0.0)),
                'margin_right': float(entry.get('margin_right', 0.0)),
                # keep relative defaults for potential mode switch
                'relative_to': 'exif',
                'relative_position': 'below',
                'relative_margin': 0.01,
                'offset_x': 0.0, 'offset_y': 0.0,
            }
        elements.append(elem)
        elem_id += 1
    st.session_state.style_elements = elements if elements else [DEFAULT_ELEMENT.copy()]

    # logo
    logo = config.get('logo', {})
    if isinstance(logo, dict):
        st.session_state.sc_logo_enabled = bool(logo.get('enabled', False))
        st.session_state.sc_logo_placement = str(logo.get('placement', 'outside'))
        st.session_state.sc_logo_position = str(logo.get('position', 'top-right'))
        st.session_state.sc_logo_alignment = str(logo.get('alignment', 'top-right'))
        st.session_state.sc_logo_size = float(logo.get('size_ratio', 0.04))
        st.session_state.sc_logo_mt = float(logo.get('margin_top', 0.0))
        st.session_state.sc_logo_mb = float(logo.get('margin_bottom', 0.0))
        st.session_state.sc_logo_ml = float(logo.get('margin_left', 0.0))
        st.session_state.sc_logo_mr = float(logo.get('margin_right', 0.0))
        st.session_state.sc_logo_relative_to = str(logo.get('relative_to', ''))
        st.session_state.sc_logo_relative_position = str(logo.get('relative_position', 'below'))
        st.session_state.sc_logo_relative_margin = float(logo.get('relative_margin', 0.01))
        st.session_state.sc_logo_offset_x = float(logo.get('offset_x_ratio', 0.0))
        st.session_state.sc_logo_offset_y = float(logo.get('offset_y_ratio', 0.0))
        st.session_state.sc_logo_mode = 'relative' if logo.get('relative_to') else 'absolute'
    else:
        st.session_state.sc_logo_enabled = False

    # defined_texts
    defined_texts_config = layout.get('defined_texts', {})
    dt_list = []
    dt_id = 1
    for dt_key, dt_entry in defined_texts_config.items():
        if not isinstance(dt_entry, dict):
            continue
        content = dt_entry.get('content', '')
        rooted = 'relative_to' not in dt_entry or not dt_entry.get('relative_to')
        mode = 'absolute' if rooted else 'relative'
        dt_item = {
            'id': dt_id, 'key': dt_key, 'content': content,
            'mode': mode,
            'tree_align': bool(dt_entry.get('tree_align', False)),
            'placement': str(dt_entry.get('placement', 'outside')),
            'position': str(dt_entry.get('position', 'bottom-left')),
            'alignment': str(dt_entry.get('alignment', 'left')),
            'margin_top': float(dt_entry.get('margin_top', 0.0)),
            'margin_bottom': float(dt_entry.get('margin_bottom', 0.0)),
            'margin_left': float(dt_entry.get('margin_left', 0.0)),
            'margin_right': float(dt_entry.get('margin_right', 0.0)),
            'relative_to': str(dt_entry.get('relative_to', 'exif')),
            'relative_position': str(dt_entry.get('relative_position', 'right-of')),
            'relative_margin': float(dt_entry.get('relative_margin', 0.01)),
            'offset_x': float(dt_entry.get('offset_x_ratio', 0.0)),
            'offset_y': float(dt_entry.get('offset_y_ratio', 0.0)),
        }
        dt_list.append(dt_item)
        dt_id += 1
    st.session_state.sc_defined_texts = dt_list

    # custom_text
    ct_cfg = layout.get('custom_text', {})
    if isinstance(ct_cfg, dict):
        st.session_state.sc_ct_enabled = bool(ct_cfg.get('enabled', False))
        st.session_state.sc_ct_placement = str(ct_cfg.get('placement', 'outside'))
        st.session_state.sc_ct_position = str(ct_cfg.get('position', 'bottom-center'))
        st.session_state.sc_ct_alignment = str(ct_cfg.get('alignment', 'center'))
        st.session_state.sc_ct_mt = float(ct_cfg.get('margin_top', 0.0))
        st.session_state.sc_ct_mb = float(ct_cfg.get('margin_bottom', 0.0))
        st.session_state.sc_ct_ml = float(ct_cfg.get('margin_left', 0.0))
        st.session_state.sc_ct_mr = float(ct_cfg.get('margin_right', 0.0))
        st.session_state.sc_ct_line_spacing = float(ct_cfg.get('line_spacing_ratio', 0.005))
        st.session_state.sc_ct_relative_to = str(ct_cfg.get('relative_to', ''))
        st.session_state.sc_ct_relative_position = str(ct_cfg.get('relative_position', 'below'))
        st.session_state.sc_ct_relative_margin = float(ct_cfg.get('relative_margin', 0.01))
        st.session_state.sc_ct_offset_x = float(ct_cfg.get('offset_x_ratio', 0.0))
        st.session_state.sc_ct_offset_y = float(ct_cfg.get('offset_y_ratio', 0.0))
        st.session_state.sc_ct_mode = 'relative' if ct_cfg.get('relative_to') else 'absolute'
    else:
        st.session_state.sc_ct_enabled = False

    # tree_align on info_position roots
    for elem in st.session_state.style_elements:
        k = elem['key']
        ip_entry = layout.get('info_position', {}).get(k, {})
        if isinstance(ip_entry, dict):
            elem['tree_align'] = bool(ip_entry.get('tree_align', False))

    st.session_state.sc_loaded_style = filename


# ── 表单渲染 ────────────────────────────────────────────────

def _render_basic_info():
    """基本信息"""
    st.subheader('基本信息')
    c1, c2 = st.columns(2)
    with c1:
        st.text_input('样式名称 (name)', key='sc_name',
                      placeholder='如: 宝丽来风格 Polaroid')
    with c2:
        st.text_input('文件名', key='sc_filename',
                      placeholder='如: Polaroid.yaml')


def _render_canvas():
    """画布扩展"""
    st.subheader('画布扩展 expand_canvas')
    st.checkbox('启用画布扩展', key='sc_canvas_enabled')
    cols = st.columns(4)
    with cols[0]:
        st.number_input('top', min_value=0.0, max_value=1.0,
                        step=0.005, format='%.3f', key='sc_canvas_top')
    with cols[1]:
        st.number_input('bottom', min_value=0.0, max_value=1.0,
                        step=0.005, format='%.3f', key='sc_canvas_bottom')
    with cols[2]:
        st.number_input('left', min_value=0.0, max_value=1.0,
                        step=0.005, format='%.3f', key='sc_canvas_left')
    with cols[3]:
        st.number_input('right', min_value=0.0, max_value=1.0,
                        step=0.005, format='%.3f', key='sc_canvas_right')


def _render_padding():
    """安全区域"""
    st.subheader('安全区域 padding')
    cols = st.columns(4)
    with cols[0]:
        st.number_input('top', min_value=0.0, max_value=1.0,
                        step=0.005, format='%.3f', key='sc_pad_top')
    with cols[1]:
        st.number_input('bottom', min_value=0.0, max_value=1.0,
                        step=0.005, format='%.3f', key='sc_pad_bottom')
    with cols[2]:
        st.number_input('left', min_value=0.0, max_value=1.0,
                        step=0.005, format='%.3f', key='sc_pad_left')
    with cols[3]:
        st.number_input('right', min_value=0.0, max_value=1.0,
                        step=0.005, format='%.3f', key='sc_pad_right')


def _render_corner_radius():
    """原图四角圆角"""
    st.subheader('原图圆角 corner_radius')
    st.checkbox('启用圆角', key='sc_cr_enabled')
    cols = st.columns(4)
    with cols[0]:
        st.number_input('top_left', min_value=0.0, max_value=0.5,
                        step=0.005, format='%.3f', key='sc_cr_tl')
    with cols[1]:
        st.number_input('top_right', min_value=0.0, max_value=0.5,
                        step=0.005, format='%.3f', key='sc_cr_tr')
    with cols[2]:
        st.number_input('bottom_left', min_value=0.0, max_value=0.5,
                        step=0.005, format='%.3f', key='sc_cr_bl')
    with cols[3]:
        st.number_input('bottom_right', min_value=0.0, max_value=0.5,
                        step=0.005, format='%.3f', key='sc_cr_br')
    st.caption('半径系数 = 实际像素 / 原图短边；0.01 ≈ 短边的 1%')


def _render_fonts():
    """字体配置"""
    st.subheader('字体 fonts')

    st.markdown('**拉丁字体 (Latin)**')
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        st.text_input('family (留空=系统字体 Segoe UI)', key='sc_font_latin_family', placeholder='例: Gotham')
    with c2:
        st.selectbox('weight', WEIGHT_OPTIONS, key='sc_font_latin_weight')
    with c3:
        st.checkbox('使用系统字体', key='sc_font_latin_system', help='勾选后忽略 family，直接使用 Segoe UI')
    with c4:
        pass

    st.markdown('**CJK 字体 (中文/日文)**')
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        st.text_input('family (留空=系统字体 Microsoft JhengHei UI)', key='sc_font_cjk_family', placeholder='例: GlowSansSC-Normal')
    with c2:
        st.selectbox('weight', WEIGHT_OPTIONS, key='sc_font_cjk_weight')
    with c3:
        st.checkbox('使用系统字体', key='sc_font_cjk_system', help='勾选后忽略 family，直接使用 Microsoft JhengHei UI')
    with c4:
        pass

    c1, c2 = st.columns(2)
    with c1:
        st.number_input('默认尺寸 (size_ratio)', min_value=0.001, max_value=0.2,
                        step=0.001, format='%.3f', key='sc_font_size')
    with c2:
        st.number_input('行间距 (line_spacing_ratio)', min_value=0.0, max_value=0.1,
                        step=0.001, format='%.3f', key='sc_font_line_spacing')

    st.caption('各元素独立尺寸（留空使用默认值）')
    cols = st.columns(4)
    size_keys = ['exif', 'timestamp', 'timestamp_author', 'camera', 'camera_make',
                 'lens', 'camera_lens', 'author', 'location', 'gps',
                 'focal_length_formatted', 'aperture_formatted',
                 'shutter_speed_formatted', 'iso_formatted', 'custom_text']
    for i, k in enumerate(size_keys):
        with cols[i % 4]:
            st.text_input(k, key=f'sc_font_{k}', placeholder='留空=默认')


def _render_logo():
    """Logo 配置"""
    st.subheader('Logo')
    st.checkbox('启用 Logo', key='sc_logo_enabled')

    if st.session_state.get('sc_logo_enabled'):
        # 定位方式
        mode_options = ['absolute', 'relative']
        mode_idx = mode_options.index(st.session_state.get('sc_logo_mode', 'absolute'))
        logo_mode = st.radio('定位方式', mode_options, index=mode_idx,
                             horizontal=True, key='sc_logo_mode')

        c1, c2 = st.columns(2)
        with c1:
            st.number_input('size_ratio', min_value=0.001, max_value=0.2,
                            step=0.001, format='%.3f', key='sc_logo_size')
        with c2:
            st.selectbox('alignment', ALIGNMENT_OPTIONS, key='sc_logo_alignment')

        if logo_mode == 'absolute':
            c1, c2 = st.columns(2)
            with c1:
                st.selectbox('placement', PLACEMENT_OPTIONS, key='sc_logo_placement')
            with c2:
                st.selectbox('position', ANCHOR_POSITION_OPTIONS, key='sc_logo_position')

            cols = st.columns(4)
            with cols[0]:
                st.number_input('margin_top', min_value=0.0, max_value=1.0,
                                step=0.005, format='%.3f', key='sc_logo_mt')
            with cols[1]:
                st.number_input('margin_bottom', min_value=0.0, max_value=1.0,
                                step=0.005, format='%.3f', key='sc_logo_mb')
            with cols[2]:
                st.number_input('margin_left', min_value=0.0, max_value=1.0,
                                step=0.005, format='%.3f', key='sc_logo_ml')
            with cols[3]:
                st.number_input('margin_right', min_value=0.0, max_value=1.0,
                                step=0.005, format='%.3f', key='sc_logo_mr')
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.selectbox('relative_to', ELEMENT_KEYS,
                             index=ELEMENT_KEYS.index(st.session_state.get('sc_logo_relative_to', 'exif'))
                             if st.session_state.get('sc_logo_relative_to', 'exif') in ELEMENT_KEYS else 0,
                             key='sc_logo_relative_to')
            with c2:
                st.selectbox('relative_position', RELATIVE_POSITION_OPTIONS, key='sc_logo_relative_position')

            c1, c2 = st.columns(2)
            with c1:
                st.number_input('relative_margin', min_value=0.0, max_value=1.0,
                                step=0.005, format='%.3f', key='sc_logo_relative_margin')
            with c2:
                st.write('')

            c1, c2 = st.columns(2)
            with c1:
                st.number_input('offset_x', step=0.001, format='%.3f', key='sc_logo_offset_x')
            with c2:
                st.number_input('offset_y', step=0.001, format='%.3f', key='sc_logo_offset_y')


def _render_one_element(idx: int, elem: dict):
    """渲染单个元素的配置表单"""
    eid = elem['id']
    with st.expander(f"元素 #{idx + 1}: {elem['key']}", expanded=(idx == 0)):
        _, del_col = st.columns([10, 1])
        with del_col:
            if st.button('✕ 删除', key=f'del_{eid}'):
                st.session_state.style_elements.pop(idx)
                st.rerun()

        c1, c2 = st.columns([1, 2])
        with c1:
            new_key = st.selectbox('元素类型 (key)', ELEMENT_KEYS,
                                   index=ELEMENT_KEYS.index(elem['key'])
                                   if elem['key'] in ELEMENT_KEYS else 0,
                                   key=f'elem_key_{eid}')
            st.session_state.style_elements[idx]['key'] = new_key
        with c2:
            mode = st.radio('定位方式', ['absolute', 'relative'],
                            index=0 if elem['mode'] == 'absolute' else 1,
                            horizontal=True, key=f'elem_mode_{eid}')
            st.session_state.style_elements[idx]['mode'] = mode

        if mode == 'absolute':
            c1, c2 = st.columns(2)
            with c1:
                placement = st.selectbox('placement', PLACEMENT_OPTIONS,
                                         index=PLACEMENT_OPTIONS.index(elem.get('placement', 'outside'))
                                         if elem.get('placement', 'outside') in PLACEMENT_OPTIONS else 0,
                                         key=f'elem_placement_{eid}')
                st.session_state.style_elements[idx]['placement'] = placement
            with c2:
                pos = st.selectbox('position', ANCHOR_POSITION_OPTIONS,
                                   index=ANCHOR_POSITION_OPTIONS.index(elem['position'])
                                   if elem['position'] in ANCHOR_POSITION_OPTIONS else 0,
                                   key=f'elem_pos_{eid}')
                st.session_state.style_elements[idx]['position'] = pos

            c1, c2 = st.columns(2)
            with c1:
                al = st.selectbox('alignment', ALIGNMENT_OPTIONS,
                                  index=ALIGNMENT_OPTIONS.index(elem['alignment'])
                                  if elem['alignment'] in ALIGNMENT_OPTIONS else 0,
                                  key=f'elem_align_{eid}')
                st.session_state.style_elements[idx]['alignment'] = al
            with c2:
                st.write('')

            cols = st.columns(4)
            for j, (label, field) in enumerate(
                [('margin_top', 'margin_top'), ('margin_bottom', 'margin_bottom'),
                 ('margin_left', 'margin_left'), ('margin_right', 'margin_right')]):
                with cols[j]:
                    val = st.number_input(label, value=elem.get(field, 0.0),
                                          min_value=0.0, max_value=1.0,
                                          step=0.005, format='%.3f',
                                          key=f'elem_{field}_{eid}')
                    st.session_state.style_elements[idx][field] = val
            ta = st.checkbox('tree_align (整链组合定位)', 
                             value=elem.get('tree_align', False),
                             key=f'elem_treealign_{eid}')
            st.session_state.style_elements[idx]['tree_align'] = ta
        else:
            c1, c2 = st.columns(2)
            with c1:
                rel_to = st.selectbox('relative_to', ELEMENT_KEYS,
                                      index=ELEMENT_KEYS.index(elem['relative_to'])
                                      if elem['relative_to'] in ELEMENT_KEYS else 0,
                                      key=f'elem_relto_{eid}')
                st.session_state.style_elements[idx]['relative_to'] = rel_to
            with c2:
                rel_pos_idx = (RELATIVE_POSITION_OPTIONS.index(elem['relative_position'])
                               if elem['relative_position'] in RELATIVE_POSITION_OPTIONS
                               else 0)
                rel_pos = st.selectbox('relative_position', RELATIVE_POSITION_OPTIONS,
                                       index=rel_pos_idx, key=f'elem_relpos_{eid}')
                st.session_state.style_elements[idx]['relative_position'] = rel_pos

            c1, c2, c3 = st.columns(3)
            with c1:
                al = st.selectbox('alignment', ALIGNMENT_OPTIONS,
                                  index=ALIGNMENT_OPTIONS.index(elem['alignment'])
                                  if elem['alignment'] in ALIGNMENT_OPTIONS else 0,
                                  key=f'elem_ralign_{eid}')
                st.session_state.style_elements[idx]['alignment'] = al
            with c2:
                rm = st.number_input('relative_margin',
                                     value=elem.get('relative_margin', 0.01),
                                     min_value=0.0, max_value=1.0,
                                     step=0.005, format='%.3f',
                                     key=f'elem_rmargin_{eid}')
                st.session_state.style_elements[idx]['relative_margin'] = rm
            with c3:
                c3a, c3b = st.columns(2)
                with c3a:
                    ox = st.number_input('offset_x', value=elem.get('offset_x', 0.0),
                                         step=0.001, format='%.3f',
                                         key=f'elem_ox_{eid}')
                    st.session_state.style_elements[idx]['offset_x'] = ox
                with c3b:
                    oy = st.number_input('offset_y', value=elem.get('offset_y', 0.0),
                                         step=0.001, format='%.3f',
                                         key=f'elem_oy_{eid}')
                    st.session_state.style_elements[idx]['offset_y'] = oy


def _render_elements():
    """动态元素列表"""
    st.subheader('元素布局 info_position')
    st.caption('仅配置驱动：在此声明的元素才会渲染')

    # 确保 style_elements 已初始化
    if 'style_elements' not in st.session_state:
        st.session_state.style_elements = [DEFAULT_ELEMENT.copy()]

    for i, elem in enumerate(st.session_state.style_elements):
        _render_one_element(i, elem)

    if st.button('+ 添加元素', width='stretch'):
        new_elem = DEFAULT_ELEMENT.copy()
        new_elem['id'] = _next_id()
        new_elem['key'] = 'camera_lens'
        st.session_state.style_elements.append(new_elem)
        st.rerun()


def _render_one_defined_text(idx: int, item: dict):
    """渲染单个预定义文本条目"""
    eid = item['id']
    with st.expander(f"预定义文本 #{idx + 1}: {item.get('key', '')}", expanded=(idx == 0)):
        _, del_col = st.columns([10, 1])
        with del_col:
            if st.button('✕ 删除', key=f'dtdel_{eid}'):
                st.session_state.sc_defined_texts.pop(idx)
                st.rerun()

        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            new_key = st.text_input('Key 名称', value=item.get('key', ''),
                                    key=f'dtkey_{eid}')
            st.session_state.sc_defined_texts[idx]['key'] = new_key
        with c2:
            new_content = st.text_input('文本内容 (content)', value=item.get('content', ''),
                                        key=f'dtcnt_{eid}')
            st.session_state.sc_defined_texts[idx]['content'] = new_content
        with c3:
            ta = st.checkbox('tree_align', value=item.get('tree_align', False),
                             key=f'dtta_{eid}')
            st.session_state.sc_defined_texts[idx]['tree_align'] = ta

        mode = st.radio('定位方式', ['absolute', 'relative'],
                        index=0 if item.get('mode') == 'absolute' else 1,
                        horizontal=True, key=f'dtmode_{eid}')
        st.session_state.sc_defined_texts[idx]['mode'] = mode

        if mode == 'absolute':
            c1, c2 = st.columns(2)
            with c1:
                p = st.selectbox('placement', PLACEMENT_OPTIONS, key=f'dtpl_{eid}')
                st.session_state.sc_defined_texts[idx]['placement'] = p
            with c2:
                pos = st.selectbox('position', ANCHOR_POSITION_OPTIONS, key=f'dtpos_{eid}')
                st.session_state.sc_defined_texts[idx]['position'] = pos
            c1, c2 = st.columns(2)
            with c1:
                al = st.selectbox('alignment', ALIGNMENT_OPTIONS, key=f'dtal_{eid}')
                st.session_state.sc_defined_texts[idx]['alignment'] = al
            with c2:
                st.write('')
            cols = st.columns(4)
            for j, (lab, fld) in enumerate([('margin_top','margin_top'),('margin_bottom','margin_bottom'),
                                            ('margin_left','margin_left'),('margin_right','margin_right')]):
                with cols[j]:
                    v = st.number_input(lab, value=item.get(fld, 0.0), min_value=0.0, max_value=1.0,
                                        step=0.005, format='%.3f', key=f'dt{fld}_{eid}')
                    st.session_state.sc_defined_texts[idx][fld] = v
        else:
            c1, c2 = st.columns(2)
            with c1:
                rt = st.selectbox('relative_to', ELEMENT_KEYS, key=f'dtrt_{eid}')
                st.session_state.sc_defined_texts[idx]['relative_to'] = rt
            with c2:
                rp = st.selectbox('relative_position', RELATIVE_POSITION_OPTIONS, key=f'dtrp_{eid}')
                st.session_state.sc_defined_texts[idx]['relative_position'] = rp
            c1, c2, c3 = st.columns(3)
            with c1:
                al = st.selectbox('alignment', ALIGNMENT_OPTIONS, key=f'dtral_{eid}')
                st.session_state.sc_defined_texts[idx]['alignment'] = al
            with c2:
                rm = st.number_input('relative_margin', value=item.get('relative_margin', 0.01),
                                     min_value=0.0, max_value=1.0, step=0.005, format='%.3f',
                                     key=f'dtrm_{eid}')
                st.session_state.sc_defined_texts[idx]['relative_margin'] = rm
            with c3:
                c3a, c3b = st.columns(2)
                with c3a:
                    ox = st.number_input('offset_x', value=item.get('offset_x', 0.0),
                                         step=0.001, format='%.3f', key=f'dtox_{eid}')
                    st.session_state.sc_defined_texts[idx]['offset_x'] = ox
                with c3b:
                    oy = st.number_input('offset_y', value=item.get('offset_y', 0.0),
                                         step=0.001, format='%.3f', key=f'dtoy_{eid}')
                    st.session_state.sc_defined_texts[idx]['offset_y'] = oy


def _render_defined_texts_section():
    """预定义文本 defined_texts 编辑区域"""
    st.subheader('预定义文本 defined_texts')
    st.caption('固定内容文本，key 建议使用补零编号，如 defined_text_01')

    if 'sc_defined_texts' not in st.session_state:
        st.session_state.sc_defined_texts = []

    for i, item in enumerate(st.session_state.sc_defined_texts):
        _render_one_defined_text(i, item)

    if st.button('+ 添加预定义文本', width='stretch'):
        max_id = max((e.get('id', 0) for e in st.session_state.sc_defined_texts), default=0)
        st.session_state.sc_defined_texts.append({
            'id': max_id + 1, 'key': '', 'content': '',
            'mode': 'absolute', 'tree_align': False,
            'placement': 'outside', 'position': 'bottom-left', 'alignment': 'left',
            'margin_top': 0.0, 'margin_bottom': 0.0, 'margin_left': 0.0, 'margin_right': 0.0,
            'relative_to': 'exif', 'relative_position': 'right-of',
            'relative_margin': 0.01, 'offset_x': 0.0, 'offset_y': 0.0,
        })
        st.rerun()


def _render_custom_text_section():
    """自定义文本 custom_text 编辑区域"""
    st.subheader('自定义文本 custom_text')
    st.checkbox('启用 (enabled)', key='sc_ct_enabled')

    if st.session_state.get('sc_ct_enabled'):
        mode = st.radio('定位方式', ['absolute', 'relative'],
                        index=0 if st.session_state.get('sc_ct_mode', 'absolute') == 'absolute' else 1,
                        horizontal=True, key='sc_ct_mode')

        c1, c2 = st.columns(2)
        with c1:
            st.number_input('line_spacing_ratio', min_value=0.0, max_value=0.1,
                            step=0.001, format='%.3f', key='sc_ct_line_spacing')
        with c2:
            al = st.selectbox('alignment', ALIGNMENT_OPTIONS, key='sc_ct_alignment')

        if mode == 'absolute':
            c1, c2 = st.columns(2)
            with c1:
                st.selectbox('placement', PLACEMENT_OPTIONS, key='sc_ct_placement')
            with c2:
                st.selectbox('position', ANCHOR_POSITION_OPTIONS, key='sc_ct_position')
            cols = st.columns(4)
            for j, (lab, fld) in enumerate([('margin_top','sc_ct_mt'),('margin_bottom','sc_ct_mb'),
                                            ('margin_left','sc_ct_ml'),('margin_right','sc_ct_mr')]):
                with cols[j]:
                    st.number_input(lab, min_value=0.0, max_value=1.0,
                                    step=0.005, format='%.3f', key=fld)
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.selectbox('relative_to', ELEMENT_KEYS, key='sc_ct_relative_to')
            with c2:
                st.selectbox('relative_position', RELATIVE_POSITION_OPTIONS,
                             key='sc_ct_relative_position')
            c1, c2, c3 = st.columns(3)
            with c1:
                st.selectbox('alignment', ALIGNMENT_OPTIONS,
                             key='sc_ct_alignment')
            with c2:
                st.number_input('relative_margin', min_value=0.0, max_value=1.0,
                                step=0.005, format='%.3f', key='sc_ct_relative_margin')
            with c3:
                c3a, c3b = st.columns(2)
                with c3a:
                    st.number_input('offset_x', step=0.001, format='%.3f',
                                    key='sc_ct_offset_x')
                with c3b:
                    st.number_input('offset_y', step=0.001, format='%.3f',
                                    key='sc_ct_offset_y')


def _render_colors():
    """颜色配置"""
    st.subheader('颜色 colors')
    st.caption('支持十六进制 "#030303" 或 RGB 数组 "[51,51,51]"')

    c1, c2 = st.columns(2)
    with c1:
        st.text_input('custom_text_light_color', key='sc_color_light',
                      placeholder='[51,51,51] 或 "#030303"')
    with c2:
        st.text_input('custom_text_dark_color', key='sc_color_dark',
                      placeholder='[204,204,204] 或 "#C0C0C0"')

    st.markdown('##### 按元素类型独立覆盖（留空跳过）')
    color_keys = ['exif', 'timestamp', 'timestamp_author', 'camera', 'camera_make',
                  'lens', 'camera_lens', 'author', 'location', 'gps',
                  'focal_length_formatted', 'aperture_formatted',
                  'shutter_speed_formatted', 'iso_formatted', 'custom_text']
    cols = st.columns(4)
    for i, k in enumerate(color_keys):
        with cols[i % 4]:
            st.markdown(f"**{k}**")
            st.text_input('light', key=f'sc_color_{k}_light',
                          placeholder='留空', label_visibility='collapsed')
            st.text_input('dark', key=f'sc_color_{k}_dark',
                          placeholder='留空', label_visibility='collapsed')


# ── YAML 生成 ────────────────────────────────────────────────

def _collect_config() -> dict:
    """从 session_state 收集配置数据，构建 YAML 字典"""
    data = {}

    # name
    name_val = st.session_state.get('sc_name', '').strip()
    data['name'] = name_val or 'Unnamed Style'

    # colors
    colors = {}
    colors['text'] = '#000000'
    lt = st.session_state.get('sc_color_light', '').strip()
    dk = st.session_state.get('sc_color_dark', '').strip()
    if lt:
        colors['custom_text_light_color'] = parse_color(lt)
    if dk:
        colors['custom_text_dark_color'] = parse_color(dk)

    for k in ['exif', 'timestamp', 'timestamp_author', 'camera', 'camera_make',
              'lens', 'camera_lens', 'author', 'location', 'gps',
              'focal_length_formatted', 'aperture_formatted',
              'shutter_speed_formatted', 'iso_formatted', 'custom_text']:
        cl = st.session_state.get(f'sc_color_{k}_light', '').strip()
        cd = st.session_state.get(f'sc_color_{k}_dark', '').strip()
        if cl:
            colors[f'custom_{k}_light_color'] = parse_color(cl)
        if cd:
            colors[f'custom_{k}_dark_color'] = parse_color(cd)
    data['colors'] = colors

    # fonts
    fonts = {
        'size_ratio': st.session_state.get('sc_font_size', 0.015),
    }
    # Latin 字体
    latin = {}
    if st.session_state.get('sc_font_latin_system', False):
        latin['system'] = 'Segoe UI'
    else:
        latin_family = st.session_state.get('sc_font_latin_family', '').strip()
        if latin_family:
            latin['family'] = latin_family
            latin['weights'] = {'light': 'Light', 'regular': 'Book', 'medium': 'Medium'}
    latin['weight'] = st.session_state.get('sc_font_latin_weight', 'medium')
    if latin:
        fonts['latin'] = latin
    # CJK 字体
    cjk = {}
    if st.session_state.get('sc_font_cjk_system', False):
        cjk['system'] = 'Microsoft JhengHei UI'
    else:
        cjk_family = st.session_state.get('sc_font_cjk_family', '').strip()
        if cjk_family:
            cjk['family'] = cjk_family
            cjk['weights'] = {'light': 'Light', 'regular': 'Regular', 'medium': 'Medium'}
    cjk['weight'] = st.session_state.get('sc_font_cjk_weight', 'medium')
    if cjk:
        fonts['cjk'] = cjk
    ls_val = st.session_state.get('sc_font_line_spacing', 0.005)
    if ls_val:
        fonts['line_spacing_ratio'] = ls_val
    sizes = {}
    for k in ['exif', 'timestamp', 'timestamp_author', 'camera', 'camera_make',
              'lens', 'camera_lens', 'author', 'location', 'gps',
              'focal_length_formatted', 'aperture_formatted',
              'shutter_speed_formatted', 'iso_formatted', 'custom_text']:
        v = st.session_state.get(f'sc_font_{k}', '').strip()
        if v:
            fv = parse_float_str(v)
            if fv is not None:
                sizes[k] = fv
    if sizes:
        fonts['sizes'] = sizes
    data['fonts'] = fonts

    # layout
    layout = {}
    canvas_enabled = st.session_state.get('sc_canvas_enabled', True)
    layout['expand_canvas'] = {
        'enabled': canvas_enabled,
        'top': st.session_state.get('sc_canvas_top', 0.0),
        'bottom': st.session_state.get('sc_canvas_bottom', 0.0),
        'left': st.session_state.get('sc_canvas_left', 0.0),
        'right': st.session_state.get('sc_canvas_right', 0.0),
    }

    layout['padding'] = {
        'top': st.session_state.get('sc_pad_top', 0.0),
        'bottom': st.session_state.get('sc_pad_bottom', 0.0),
        'left': st.session_state.get('sc_pad_left', 0.0),
        'right': st.session_state.get('sc_pad_right', 0.0),
    }

    if st.session_state.get('sc_cr_enabled', False):
        layout['corner_radius'] = {
            'enabled': True,
            'top_left': st.session_state.get('sc_cr_tl', 0.01),
            'top_right': st.session_state.get('sc_cr_tr', 0.01),
            'bottom_left': st.session_state.get('sc_cr_bl', 0.01),
            'bottom_right': st.session_state.get('sc_cr_br', 0.01),
        }

    info_pos = {}
    elements = st.session_state.get('style_elements', [])
    for elem in elements:
        key = elem['key']
        if elem['mode'] == 'absolute':
            entry = {
                'placement': elem.get('placement', 'outside'),
                'position': elem['position'],
                'alignment': elem['alignment'],
                'margin_top': elem.get('margin_top', 0.0),
                'margin_bottom': elem.get('margin_bottom', 0.0),
                'margin_left': elem.get('margin_left', 0.0),
                'margin_right': elem.get('margin_right', 0.0),
            }
        else:
            entry = {
                'relative_to': elem['relative_to'],
                'relative_position': elem['relative_position'],
                'alignment': elem['alignment'],
                'relative_margin': elem.get('relative_margin', 0.01),
            }
            if elem.get('offset_x', 0.0) != 0.0:
                entry['offset_x_ratio'] = elem['offset_x']
            if elem.get('offset_y', 0.0) != 0.0:
                entry['offset_y_ratio'] = elem['offset_y']
        # tree_align on root elements
        if elem.get('tree_align'):
            entry['tree_align'] = True
        info_pos[key] = entry
    layout['info_position'] = info_pos

    # defined_texts
    dt_list_raw = st.session_state.get('sc_defined_texts', [])
    if dt_list_raw:
        defined_cfg = {}
        for dt_item in dt_list_raw:
            dkey = dt_item.get('key', '').strip()
            if not dkey:
                continue
            dentry = {'content': dt_item.get('content', '')}
            if dt_item.get('mode') == 'absolute':
                dentry['placement'] = dt_item.get('placement', 'outside')
                dentry['position'] = dt_item.get('position', 'bottom-left')
                dentry['alignment'] = dt_item.get('alignment', 'left')
                dentry['margin_top'] = dt_item.get('margin_top', 0.0)
                dentry['margin_bottom'] = dt_item.get('margin_bottom', 0.0)
                dentry['margin_left'] = dt_item.get('margin_left', 0.0)
                dentry['margin_right'] = dt_item.get('margin_right', 0.0)
                if dt_item.get('tree_align'):
                    dentry['tree_align'] = True
            else:
                dentry['relative_to'] = dt_item.get('relative_to', 'exif')
                dentry['relative_position'] = dt_item.get('relative_position', 'right-of')
                dentry['alignment'] = dt_item.get('alignment', 'left')
                dentry['relative_margin'] = dt_item.get('relative_margin', 0.01)
                if dt_item.get('offset_x', 0.0) != 0.0:
                    dentry['offset_x_ratio'] = dt_item['offset_x']
                if dt_item.get('offset_y', 0.0) != 0.0:
                    dentry['offset_y_ratio'] = dt_item['offset_y']
            defined_cfg[dkey] = dentry
        if defined_cfg:
            layout['defined_texts'] = defined_cfg

    # custom_text
    if st.session_state.get('sc_ct_enabled', False):
        ct = {'enabled': True}
        ct_mode = st.session_state.get('sc_ct_mode', 'absolute')
        if ct_mode == 'relative' and st.session_state.get('sc_ct_relative_to', '').strip():
            ct['relative_to'] = st.session_state.get('sc_ct_relative_to', '').strip()
            ct['relative_position'] = st.session_state.get('sc_ct_relative_position', 'below')
            ct['alignment'] = st.session_state.get('sc_ct_alignment', 'center')
            ct['relative_margin'] = st.session_state.get('sc_ct_relative_margin', 0.01)
            ox = st.session_state.get('sc_ct_offset_x', 0.0)
            oy = st.session_state.get('sc_ct_offset_y', 0.0)
            if ox != 0.0: ct['offset_x_ratio'] = ox
            if oy != 0.0: ct['offset_y_ratio'] = oy
        else:
            ct['placement'] = st.session_state.get('sc_ct_placement', 'outside')
            ct['position'] = st.session_state.get('sc_ct_position', 'bottom-center')
            ct['alignment'] = st.session_state.get('sc_ct_alignment', 'center')
            ct['margin_top'] = st.session_state.get('sc_ct_mt', 0.0)
            ct['margin_bottom'] = st.session_state.get('sc_ct_mb', 0.0)
            ct['margin_left'] = st.session_state.get('sc_ct_ml', 0.0)
            ct['margin_right'] = st.session_state.get('sc_ct_mr', 0.0)
        cls = st.session_state.get('sc_ct_line_spacing', 0.005)
        if cls:
            ct['line_spacing_ratio'] = cls
        layout['custom_text'] = ct

    data['layout'] = layout

    # logo
    logo_enabled = st.session_state.get('sc_logo_enabled', False)
    if logo_enabled:
        logo_mode = st.session_state.get('sc_logo_mode', 'absolute')
        logo = {
            'enabled': True,
            'alignment': st.session_state.get('sc_logo_alignment', 'top-right'),
            'size_ratio': st.session_state.get('sc_logo_size', 0.04),
        }
        if logo_mode == 'relative' and st.session_state.get('sc_logo_relative_to'):
            logo['relative_to'] = st.session_state.get('sc_logo_relative_to', '')
            logo['relative_position'] = st.session_state.get('sc_logo_relative_position', 'below')
            logo['relative_margin'] = st.session_state.get('sc_logo_relative_margin', 0.01)
            if st.session_state.get('sc_logo_offset_x', 0.0) != 0.0:
                logo['offset_x_ratio'] = st.session_state.get('sc_logo_offset_x', 0.0)
            if st.session_state.get('sc_logo_offset_y', 0.0) != 0.0:
                logo['offset_y_ratio'] = st.session_state.get('sc_logo_offset_y', 0.0)
        else:
            logo['placement'] = st.session_state.get('sc_logo_placement', 'outside')
            logo['position'] = st.session_state.get('sc_logo_position', 'top-right')
            logo['margin_top'] = st.session_state.get('sc_logo_mt', 0.0)
            logo['margin_bottom'] = st.session_state.get('sc_logo_mb', 0.0)
            logo['margin_left'] = st.session_state.get('sc_logo_ml', 0.0)
            logo['margin_right'] = st.session_state.get('sc_logo_mr', 0.0)
    else:
        logo = {'enabled': False}
    data['logo'] = logo

    return data


def _generate_and_save():
    """生成 YAML 并保存"""
    if not st.session_state.get('style_elements'):
        st.error('请至少添加一个元素')
        return

    filename = sanitize_filename(
        st.session_state.get('sc_filename', 'NewStyle.yaml'))
    config = _collect_config()
    config = _clean_dict(config)

    try:
        yaml_str = build_yaml_config(config)
    except Exception as e:
        st.error(f'YAML 生成失败: {e}')
        return

    os.makedirs(CONFIGS_DIR, exist_ok=True)
    filepath = os.path.join(CONFIGS_DIR, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(yaml_str)
    except Exception as e:
        st.error(f'文件写入失败: {e}')
        return

    st.success(f'配置文件已保存: {filepath}')
    st.code(yaml_str, language='yaml')

    # 刷新下拉列表，标记当前已加载
    st.session_state.sc_loaded_style = filename


# ── 主渲染函数 ──────────────────────────────────────────────

def render_style_creator_page():
    """渲染样式编辑器页面"""
    st.header('样式编辑器')

    # 冷启动：初始化所有表单字段为合理默认值
    if 'style_elements' not in st.session_state:
        _init_new_style()

    # 确保切换页面后这些关键键仍存在
    if 'sc_selected_style' not in st.session_state:
        st.session_state.sc_selected_style = NEW_STYLE_PLACEHOLDER
    if 'sc_loaded_style' not in st.session_state:
        st.session_state.sc_loaded_style = NEW_STYLE_PLACEHOLDER

    existing = _get_existing_styles()
    style_options = [NEW_STYLE_PLACEHOLDER] + existing

    # 顶部选择栏 + 按钮
    sel_col, btn_col = st.columns([3, 1])
    with sel_col:
        st.selectbox('选择样式', style_options,
                     index=style_options.index(st.session_state.sc_selected_style)
                     if st.session_state.sc_selected_style in style_options else 0,
                     key='sc_selected_style')
    with btn_col:
        st.write('')
        if st.button('💾 新建 / 保存样式', width='stretch', type='primary'):
            _generate_and_save()

    # 检测选择变化 → 加载
    if st.session_state.sc_selected_style != st.session_state.sc_loaded_style:
        if st.session_state.sc_selected_style == NEW_STYLE_PLACEHOLDER:
            _init_new_style()
        else:
            _load_existing_style(st.session_state.sc_selected_style)

    st.markdown('---')
    _render_basic_info()

    st.markdown('---')
    c1, c2 = st.columns(2)
    with c1:
        _render_canvas()
    with c2:
        _render_padding()

    _render_corner_radius()

    st.markdown('---')
    _render_fonts()

    st.markdown('---')
    _render_logo()

    st.markdown('---')
    _render_colors()

    st.markdown('---')
    _render_defined_texts_section()

    st.markdown('---')
    _render_custom_text_section()

    st.markdown('---')
    _render_elements()

    st.markdown('---')
    st.caption(f'配置文件目录: `{CONFIGS_DIR}`')
