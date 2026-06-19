# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
相机映射管理页面模块
"""
import streamlit as st
import os
import pandas as pd
from src.utils.device_mapper import DeviceMapper


_BRANDS = [
    ('canon',      'Canon',       r'Canon|佳能'),
    ('nikon',      'Nikon',       r'Nikon|尼康'),
    ('sony',       'Sony',        r'Sony|索尼'),
    ('fuji',       'Fujifilm',    r'Fujifilm|富士'),
    ('hasselblad', 'Hasselblad',  r'Hasselblad|哈苏'),
    ('dji',        'DJI',         r'DJI|大疆'),
    ('om',         'OM System',   r'OM System|奥之心|Olympus'),
    ('ricoh',      'RICOH',       r'RICOH|理光'),
    ('xiaomi',     'Xiaomi',      r'Xiaomi|小米'),
    ('vivo',       'Vivo',        r'Vivo'),
    ('oppo',       'Oppo',        r'Oppo'),
    ('huawei',     'Huawei',      r'Huawei|华为'),
]

_OTHER_EXCLUDE = '|'.join(p for _, _, p in _BRANDS)


def render_camera_mapping_page():
    """渲染相机映射管理页面"""
    device_mapper = DeviceMapper()

    if 'camera_df' not in st.session_state:
        camera_data = []
        if os.path.exists(device_mapper.camera_db_path):
            with open(device_mapper.camera_db_path, 'r', encoding='utf-8') as f:
                import csv
                reader = csv.DictReader(f)
                for row in reader:
                    camera_data.append(row)
        st.session_state.camera_df = pd.DataFrame(camera_data)

    if 'camera_filter' not in st.session_state:
        st.session_state.camera_filter = None

    st.header("📸 相机映射管理")
    st.markdown("在此管理相机品牌和型号的映射关系，用于将原始EXIF数据转换为更美观的显示格式")

    # ── CSS 强制品牌行自适应零间距 ──
    st.markdown("""
<style>
    div.brand-row div[data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
        gap: 0 !important;
    }
    div.brand-row div[data-testid="column"] {
        flex: 0 0 auto !important;
        width: auto !important;
        padding: 0 !important;
    }
    div.brand-row button {
        padding: 0.2rem 0.6rem !important;
        font-size: 0.82rem !important;
        border-radius: 0 !important;
        margin: 0 !important;
        border-right: 1px solid rgba(0,0,0,0.08) !important;
    }
    div.brand-row button p {
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        margin: 0 !important;
    }
</style>
""", unsafe_allow_html=True)

    # ── 品牌筛选按钮行 ──
    st.markdown('<div class="brand-row">', unsafe_allow_html=True)
    keys = [''] + [k for k, _, _ in _BRANDS] + ['other']
    labels = ['All'] + [l for _, l, _ in _BRANDS] + ['其它']
    cols = st.columns(len(keys))
    for i, (key, label) in enumerate(zip(keys, labels)):
        with cols[i]:
            active = st.session_state.camera_filter == key or (key == '' and st.session_state.camera_filter is None)
            active |= (key == 'other' and st.session_state.camera_filter == 'other')
            if st.button(label, key=f"cf_{key or 'all'}", use_container_width=True):
                if active and key != '':
                    st.session_state.camera_filter = None
                else:
                    st.session_state.camera_filter = key if key else None
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # ── 筛选逻辑 ──
    df = st.session_state.camera_df.copy()
    active = st.session_state.camera_filter
    if active == 'other':
        df = df[~df['original_brand'].str.contains(_OTHER_EXCLUDE, case=False, na=False)]
    elif active:
        pattern = dict((k, p) for k, _, p in _BRANDS)[active]
        df = df[df['original_brand'].str.contains(pattern, case=False, na=False)]

    # ── 筛选提示 ──
    if st.session_state.camera_filter:
        if st.session_state.camera_filter == 'other':
            active_label = '其它'
        else:
            active_label = dict((k, l) for k, l, _ in _BRANDS).get(
                st.session_state.camera_filter,
                st.session_state.camera_filter)
        st.caption(f"当前筛选: {active_label}  |  {len(df)} 条记录")
    else:
        st.caption(f"全部品牌  |  {len(df)} 条记录")

    # ── 可编辑表格 ──
    edited_df = st.data_editor(
        df, key="camera_editor", num_rows="dynamic",
        width='stretch', height=600,
        column_config={
            "original_brand": st.column_config.TextColumn("原始品牌", width="medium"),
            "original_model": st.column_config.TextColumn("原始型号", width="medium"),
            "mapped_brand":   st.column_config.TextColumn("映射品牌", width="medium"),
            "mapped_model":   st.column_config.TextColumn("映射型号", width="medium"),
            "timestamp":      st.column_config.TextColumn("时间戳", width="small"),
        },
    )

    # ── 保存 ──
    if st.button("保存相机映射更改", key="save_camera_changes"):
        st.session_state.camera_df = edited_df
        edited_df.to_csv(device_mapper.camera_db_path, index=False, encoding='utf-8')
        device_mapper.refresh()
        st.success("相机映射已保存并应用！")
