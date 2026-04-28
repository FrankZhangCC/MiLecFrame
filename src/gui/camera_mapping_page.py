"""
相机映射管理页面模块
"""
import streamlit as st
import os
import pandas as pd
from src.utils.device_mapper import DeviceMapper  # 导入设备映射器


def render_camera_mapping_page():
    """渲染相机映射管理页面"""
    device_mapper = DeviceMapper()  # 初始化设备映射器
    
    # 初始化session state变量
    if 'camera_df' not in st.session_state:
        # 读取相机映射数据
        camera_data = []
        if os.path.exists(device_mapper.camera_db_path):
            with open(device_mapper.camera_db_path, 'r', encoding='utf-8') as f:
                import csv
                reader = csv.DictReader(f)
                for row in reader:
                    camera_data.append(row)
        st.session_state.camera_df = pd.DataFrame(camera_data)

    st.header("📸 相机映射管理")
    st.markdown("在此管理相机品牌和型号的映射关系，用于将原始EXIF数据转换为更美观的显示格式")
    
    # 第一排品牌筛选按钮
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        canon_filter = st.button("Canon (佳能)", key="canon_filter")
    with col2:
        nikon_filter = st.button("Nikon (尼康)", key="nikon_filter")
    with col3:
        sony_filter = st.button("Sony (索尼)", key="sony_filter")
    with col4:
        fuji_filter = st.button("Fujifilm (富士)", key="fuji_filter")
    with col5:
        hasselblad_filter = st.button("Hasselblad (哈苏)", key="hasselblad_filter")
    
    # 第二排品牌筛选按钮
    col6, col7, col8, col9, col10 = st.columns(5)
    with col6:
        dji_filter = st.button("DJI (大疆)", key="dji_filter")
    with col7:
        om_filter = st.button("OM System (奥之心)", key="om_filter")
    with col8:
        ricoh_filter = st.button("RICOH (理光)", key="ricoh_filter")
    with col9:
        other_filter = st.button("其它", key="other_filter")
    
    # 为了放置最后两个按钮，需要额外一行或在现有行中添加
    col11, col12, col13, col14, col15 = st.columns(5)
    with col11:
        xiaomi_filter = st.button("Xiaomi (小米)", key="xiaomi_filter")
    with col12:
        vivo_filter = st.button("Vivo", key="vivo_filter")
    with col13:
        oppo_filter = st.button("Oppo", key="oppo_filter")
    with col14:
        huawei_filter = st.button("Huawei (华为)", key="huawei_filter")
    
    # 根据筛选条件显示数据
    filtered_camera_df = st.session_state.camera_df.copy()
    if canon_filter:
        filtered_camera_df = st.session_state.camera_df[st.session_state.camera_df['original_brand'].str.contains('Canon|佳能', case=False, na=False)]
    elif nikon_filter:
        filtered_camera_df = st.session_state.camera_df[st.session_state.camera_df['original_brand'].str.contains('Nikon|尼康', case=False, na=False)]
    elif sony_filter:
        filtered_camera_df = st.session_state.camera_df[st.session_state.camera_df['original_brand'].str.contains('Sony|索尼', case=False, na=False)]
    elif fuji_filter:
        filtered_camera_df = st.session_state.camera_df[st.session_state.camera_df['original_brand'].str.contains('Fujifilm|富士', case=False, na=False)]
    elif hasselblad_filter:
        filtered_camera_df = st.session_state.camera_df[st.session_state.camera_df['original_brand'].str.contains('Hasselblad|哈苏', case=False, na=False)]
    elif dji_filter:
        filtered_camera_df = st.session_state.camera_df[st.session_state.camera_df['original_brand'].str.contains('DJI|大疆', case=False, na=False)]
    elif om_filter:
        filtered_camera_df = st.session_state.camera_df[st.session_state.camera_df['original_brand'].str.contains('OM System|奥之心|Olympus', case=False, na=False)]
    elif ricoh_filter:
        filtered_camera_df = st.session_state.camera_df[st.session_state.camera_df['original_brand'].str.contains('RICOH|理光', case=False, na=False)]
    elif xiaomi_filter:
        filtered_camera_df = st.session_state.camera_df[st.session_state.camera_df['original_brand'].str.contains('Xiaomi|小米', case=False, na=False)]
    elif vivo_filter:
        filtered_camera_df = st.session_state.camera_df[st.session_state.camera_df['original_brand'].str.contains('Vivo', case=False, na=False)]
    elif oppo_filter:
        filtered_camera_df = st.session_state.camera_df[st.session_state.camera_df['original_brand'].str.contains('Oppo', case=False, na=False)]
    elif huawei_filter:
        filtered_camera_df = st.session_state.camera_df[st.session_state.camera_df['original_brand'].str.contains('Huawei|华为', case=False, na=False)]
    elif other_filter:
        # 显示除上述品牌外的所有品牌
        exclude_brands = ['Canon', '佳能', 'Nikon', '尼康', 'Sony', '索尼', 'Fujifilm', '富士', 
                         'Hasselblad', '哈苏', 'DJI', '大疆', 'OM System', '奥之心', 'Olympus', 
                         'RICOH', '理光', 'Xiaomi', '小米', 'Vivo', 'Oppo', 'Huawei', '华为']
        pattern = '|'.join(exclude_brands)
        filtered_camera_df = st.session_state.camera_df[~st.session_state.camera_df['original_brand'].str.contains(pattern, case=False, na=False)]

    # 显示可编辑的相机映射表格
    edited_camera_df = st.data_editor(
        filtered_camera_df,
        key="camera_editor",
        num_rows="dynamic",  # 允许添加和删除行
        width='stretch',
        height=600,
        column_config={
            "original_brand": st.column_config.TextColumn("原始品牌", width="medium"),
            "original_model": st.column_config.TextColumn("原始型号", width="medium"),
            "mapped_brand": st.column_config.TextColumn("映射品牌", width="medium"),
            "mapped_model": st.column_config.TextColumn("映射型号", width="medium"),
            "timestamp": st.column_config.TextColumn("时间戳", width="small"),
        },
    )
    
    # 保存更改到Session State和文件
    if st.button("保存相机映射更改", key="save_camera_changes"):
        st.session_state.camera_df = edited_camera_df
        # 保存到CSV文件
        edited_camera_df.to_csv(device_mapper.camera_db_path, index=False, encoding='utf-8')
        # 刷新设备映射器
        device_mapper.refresh()
        st.success("相机映射已保存并应用！")