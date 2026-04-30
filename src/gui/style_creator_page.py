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
                'camera_lens', 'author', 'location', 'camera_icon']

POSITION_OPTIONS = ['bottom-left', 'bottom-right', 'top-left', 'top-right',
                    'bottom-center', 'top-center', 'center', 'inside', 'outside',
                    'top', 'bottom', 'left', 'right']

ALIGNMENT_OPTIONS = ['left', 'center', 'right', 'top-left', 'top-right', 'top', 'bottom']

RELATIVE_POSITION_OPTIONS = ['below', 'above', 'left-of', 'right-of']

WEIGHT_OPTIONS = ['medium', 'regular', 'light']
FAMILY_OPTIONS = ['Gotham']

BG_TYPE_OPTIONS = [
    'gaussian_black_35', 'gaussian_white_50',
    'gaussian_black_65', 'gaussian_white_80',
    'pure_black', 'pure_white',
]

CONFIGS_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), '..', 'frame_styles', 'configs'))

NEW_STYLE_PLACEHOLDER = '--- 新建样式 ---'

DEFAULT_ELEMENT = {
    'id': 0,
    'key': 'exif',
    'mode': 'absolute',
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
        'sc_font_family': 'Gotham', 'sc_font_weight': 'medium',
        'sc_font_size': 0.015,
        'sc_bg_type': 'gaussian_black_35', 'sc_bg_radius': 200, 'sc_bg_opacity': 35,
        'sc_logo_enabled': False,
        'sc_logo_position': 'top-right', 'sc_logo_alignment': 'top-right',
        'sc_logo_size': 0.04, 'sc_logo_mt': 0.0, 'sc_logo_mb': 0.0,
        'sc_logo_ml': 0.0, 'sc_logo_mr': 0.0,
        'sc_color_light': '', 'sc_color_dark': '',
        'style_elements': [DEFAULT_ELEMENT.copy()],
        'sc_loaded_style': NEW_STYLE_PLACEHOLDER,
    }
    # per-element font sizes
    for k in ['exif', 'timestamp', 'timestamp_author', 'camera',
              'lens', 'camera_lens', 'author', 'location']:
        defaults[f'sc_font_{k}'] = ''
    # per-element colors
    for k in ['exif', 'timestamp', 'timestamp_author', 'camera',
              'lens', 'camera_lens', 'author', 'location']:
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
    for k in ['exif', 'timestamp', 'timestamp_author', 'camera',
              'lens', 'camera_lens', 'author', 'location']:
        st.session_state[f'sc_color_{k}_light'] = color_to_text(
            colors.get(f'custom_{k}_light_color', ''))
        st.session_state[f'sc_color_{k}_dark'] = color_to_text(
            colors.get(f'custom_{k}_dark_color', ''))

    # fonts
    fonts = config.get('fonts', {})
    st.session_state.sc_font_family = str(fonts.get('family', 'Gotham'))
    st.session_state.sc_font_weight = str(fonts.get('weight', 'medium'))
    st.session_state.sc_font_size = float(fonts.get('size_ratio', 0.015))
    sizes = fonts.get('sizes', {}) or {}
    for k in ['exif', 'timestamp', 'timestamp_author', 'camera',
              'lens', 'camera_lens', 'author', 'location']:
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

    # background_fill
    bg = config.get('background_fill', {})
    st.session_state.sc_bg_type = str(bg.get('type', 'gaussian_black_35'))
    st.session_state.sc_bg_radius = int(bg.get('gaussian_blur_radius', 200))
    st.session_state.sc_bg_opacity = int(bg.get('gaussian_blur_opacity', 35))

    # logo
    logo = config.get('logo', {})
    if isinstance(logo, dict):
        st.session_state.sc_logo_enabled = bool(logo.get('enabled', False))
        st.session_state.sc_logo_position = str(logo.get('position', 'top-right'))
        st.session_state.sc_logo_alignment = str(logo.get('alignment', 'top-right'))
        st.session_state.sc_logo_size = float(logo.get('size_ratio', 0.04))
        st.session_state.sc_logo_mt = float(logo.get('margin_top', 0.0))
        st.session_state.sc_logo_mb = float(logo.get('margin_bottom', 0.0))
        st.session_state.sc_logo_ml = float(logo.get('margin_left', 0.0))
        st.session_state.sc_logo_mr = float(logo.get('margin_right', 0.0))
    else:
        st.session_state.sc_logo_enabled = False

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


def _render_fonts():
    """字体配置"""
    st.subheader('字体 fonts')
    c1, c2, c3 = st.columns(3)
    with c1:
        st.selectbox('字体族 (family)', FAMILY_OPTIONS, key='sc_font_family')
    with c2:
        st.selectbox('字重 (weight)', WEIGHT_OPTIONS, key='sc_font_weight')
    with c3:
        st.number_input('默认尺寸 (size_ratio)', min_value=0.001, max_value=0.2,
                        step=0.001, format='%.3f', key='sc_font_size')

    st.caption('各元素独立尺寸（留空使用默认值）')
    cols = st.columns(4)
    size_keys = ['exif', 'timestamp', 'timestamp_author', 'camera',
                 'lens', 'camera_lens', 'author', 'location']
    for i, k in enumerate(size_keys):
        with cols[i % 4]:
            st.text_input(k, key=f'sc_font_{k}', placeholder='留空=默认')


def _render_background():
    """背景填充"""
    st.subheader('背景填充 background_fill')
    c1, c2, c3 = st.columns(3)
    with c1:
        st.selectbox('type', BG_TYPE_OPTIONS, key='sc_bg_type')
    with c2:
        st.number_input('gaussian_blur_radius', min_value=0, max_value=500,
                        step=10, key='sc_bg_radius')
    with c3:
        st.number_input('gaussian_blur_opacity', min_value=0, max_value=100,
                        step=5, key='sc_bg_opacity')


def _render_logo():
    """Logo 配置"""
    st.subheader('Logo')
    st.checkbox('启用 Logo', key='sc_logo_enabled')

    if st.session_state.get('sc_logo_enabled'):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.selectbox('position', POSITION_OPTIONS, key='sc_logo_position')
        with c2:
            st.selectbox('alignment', ALIGNMENT_OPTIONS, key='sc_logo_alignment')
        with c3:
            st.number_input('size_ratio', min_value=0.001, max_value=0.2,
                            step=0.001, format='%.3f', key='sc_logo_size')

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
                pos = st.selectbox('position', POSITION_OPTIONS,
                                   index=POSITION_OPTIONS.index(elem['position'])
                                   if elem['position'] in POSITION_OPTIONS else 0,
                                   key=f'elem_pos_{eid}')
                st.session_state.style_elements[idx]['position'] = pos
            with c2:
                al = st.selectbox('alignment', ALIGNMENT_OPTIONS,
                                  index=ALIGNMENT_OPTIONS.index(elem['alignment'])
                                  if elem['alignment'] in ALIGNMENT_OPTIONS else 0,
                                  key=f'elem_align_{eid}')
                st.session_state.style_elements[idx]['alignment'] = al

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
    color_keys = ['exif', 'timestamp', 'timestamp_author', 'camera',
                  'lens', 'camera_lens', 'author', 'location']
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

    for k in ['exif', 'timestamp', 'timestamp_author', 'camera', 'lens',
              'camera_lens', 'author', 'location']:
        cl = st.session_state.get(f'sc_color_{k}_light', '').strip()
        cd = st.session_state.get(f'sc_color_{k}_dark', '').strip()
        if cl:
            colors[f'custom_{k}_light_color'] = parse_color(cl)
        if cd:
            colors[f'custom_{k}_dark_color'] = parse_color(cd)
    data['colors'] = colors

    # fonts
    fonts = {
        'family': st.session_state.get('sc_font_family', 'Gotham'),
        'weight': st.session_state.get('sc_font_weight', 'medium'),
        'size_ratio': st.session_state.get('sc_font_size', 0.015),
    }
    sizes = {}
    for k in ['exif', 'timestamp', 'timestamp_author', 'camera',
              'lens', 'camera_lens', 'author', 'location']:
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

    info_pos = {}
    elements = st.session_state.get('style_elements', [])
    for elem in elements:
        key = elem['key']
        if elem['mode'] == 'absolute':
            entry = {
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
        info_pos[key] = entry
    layout['info_position'] = info_pos

    data['layout'] = layout

    # background_fill
    data['background_fill'] = {
        'type': st.session_state.get('sc_bg_type', 'gaussian_black_35'),
        'gaussian_blur_radius': st.session_state.get('sc_bg_radius', 200),
        'gaussian_blur_opacity': st.session_state.get('sc_bg_opacity', 35),
    }

    # logo
    logo_enabled = st.session_state.get('sc_logo_enabled', False)
    if logo_enabled:
        logo = {
            'enabled': True,
            'position': st.session_state.get('sc_logo_position', 'top-right'),
            'alignment': st.session_state.get('sc_logo_alignment', 'top-right'),
            'size_ratio': st.session_state.get('sc_logo_size', 0.04),
            'margin_top': st.session_state.get('sc_logo_mt', 0.0),
            'margin_bottom': st.session_state.get('sc_logo_mb', 0.0),
            'margin_left': st.session_state.get('sc_logo_ml', 0.0),
            'margin_right': st.session_state.get('sc_logo_mr', 0.0),
        }
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

    st.markdown('---')
    _render_fonts()

    st.markdown('---')
    c1, c2 = st.columns(2)
    with c1:
        _render_background()
    with c2:
        _render_logo()

    st.markdown('---')
    _render_colors()

    st.markdown('---')
    _render_elements()

    st.markdown('---')
    st.caption(f'配置文件目录: `{CONFIGS_DIR}`')
