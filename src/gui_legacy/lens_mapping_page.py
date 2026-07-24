# Copyright (c) 2026 FrankZhangCC
# MIT License - see LICENSE file for details

"""
镜头映射管理页面模块
"""
import streamlit as st
import os
import pandas as pd
from src.utils.device_mapper import DeviceMapper  # 导入设备映射器


def render_lens_mapping_page():
    """渲染镜头映射管理页面"""
    device_mapper = DeviceMapper()  # 初始化设备映射器
    
    # 初始化session state变量
    if 'lens_df' not in st.session_state:
        # 读取镜头映射数据
        lens_data = []
        if os.path.exists(device_mapper.lens_db_path):
            with open(device_mapper.lens_db_path, 'r', encoding='utf-8') as f:
                import csv
                reader = csv.DictReader(f)
                for row in reader:
                    lens_data.append(row)
        st.session_state.lens_df = pd.DataFrame(lens_data)

    st.header("🔭 镜头映射管理")
    st.markdown("在此管理镜头型号的映射关系，用于将原始EXIF数据转换为更美观的显示格式")
    
    # 搜索框
    search_term = st.text_input("搜索镜头", placeholder="输入原始或映射镜头名称...", key="lens_search")
    
    # 根据搜索条件过滤数据
    filtered_lens_df = st.session_state.lens_df.copy()
    if search_term:
        cols = ['original_lens', 'mapped_lens', 'short_lens', 'brand', 'mount']
        mask = pd.Series(False, index=filtered_lens_df.index)
        for col in cols:
            if col in filtered_lens_df.columns:
                mask |= filtered_lens_df[col].astype(str).str.contains(search_term, case=False, na=False)
        filtered_lens_df = filtered_lens_df[mask]
    
    # 显示可编辑的镜头映射表格
    edited_lens_df = st.data_editor(
        filtered_lens_df,
        key="lens_editor",
        num_rows="dynamic",  # 允许添加和删除行
        width='stretch',
        height=600,
        column_config={
            "original_lens": st.column_config.TextColumn("原始镜头", width="medium"),
            "mapped_lens": st.column_config.TextColumn("映射镜头", width="medium"),
            "short_lens": st.column_config.TextColumn("短版名称", width="medium"),
            "brand": st.column_config.TextColumn("品牌", width="medium"),
            "mount": st.column_config.TextColumn("卡口", width="medium"),
            "timestamp": st.column_config.TextColumn("时间戳", width="small"),
        },
    )
    
    # 保存更改到Session State和文件
    if st.button("保存镜头映射更改", key="save_lens_changes"):
        st.session_state.lens_df = edited_lens_df
        # 保存到CSV文件
        edited_lens_df.to_csv(device_mapper.lens_db_path, index=False, encoding='utf-8')
        # 刷新设备映射器
        device_mapper.refresh()
        st.success("镜头映射已保存并应用！")