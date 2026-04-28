"""
GUI应用程序模块
使用Streamlit构建网页版GUI界面
"""
import streamlit as st

from src.utils.logging_config import setup_logging
setup_logging()

# 使用绝对导入
from src.gui.image_processing_page import render_image_processing_page
from src.gui.camera_mapping_page import render_camera_mapping_page
from src.gui.lens_mapping_page import render_lens_mapping_page


def run_app():
    """运行GUI应用程序"""
    
    # 设置页面配置
    st.set_page_config(
        page_title="MiLeica Frame - 照片相框程序",
        page_icon="📷",
        layout="wide"
    )
    
    # 初始化当前页面状态
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "🖼️ 图像处理"
    
    # 侧边栏导航
    st.sidebar.title("🧭 导航")
    
    # 使用按钮进行页面切换
    if st.sidebar.button("🖼️ 图像处理", use_container_width=True):
        st.session_state.current_page = "🖼️ 图像处理"
    if st.sidebar.button("📸 相机映射管理", use_container_width=True):
        st.session_state.current_page = "📸 相机映射管理"
    if st.sidebar.button("🔭 镜头映射管理", use_container_width=True):
        st.session_state.current_page = "🔭 镜头映射管理"
    
    # 根据当前页面状态渲染相应页面
    if st.session_state.current_page == "🖼️ 图像处理":
        render_image_processing_page()
    elif st.session_state.current_page == "📸 相机映射管理":
        render_camera_mapping_page()
    elif st.session_state.current_page == "🔭 镜头映射管理":
        render_lens_mapping_page()

    # 底部信息
    st.markdown("---")
    st.caption("💡 提示：本程序支持设备映射，自动识别并显示相机型号等信息")
    st.caption("📋 版权所有 © 2026 MiLeica Frame 项目组")
    
    with st.expander("🛑 如何停止程序"):
        st.write("当您完成使用后，请在终端中按 `Ctrl+C` 来停止服务。")
        st.code("# 在运行程序的终端中按 Ctrl+C\n^C", language="text")


if __name__ == "__main__":
    run_app()