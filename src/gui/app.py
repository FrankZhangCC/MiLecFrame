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
from src.gui.style_creator_page import render_style_creator_page
from src.gui.batch_processing_page import render_batch_processing_page


def run_app():
    """运行GUI应用程序"""
    
    # 设置页面配置
    st.set_page_config(
        page_title="MiLecFrame - 照片相框程序",
        page_icon="📷",
        layout="wide"
    )

    # 全局 CSS：压缩顶栏、隐藏 Deploy、减少顶部留白
    st.markdown("""
<style>
header[data-testid="stHeader"] {
    height: auto !important;
    min-height: 1.5rem !important;
    padding: 0.2rem 1rem !important;
}
button[kind="header"] {
    display: none !important;
}
div.block-container {
    padding-top: 0.5rem !important;
}
</style>
    """, unsafe_allow_html=True)

    # 初始化当前页面状态
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "🖼️ 图像处理"
    
    # 侧边栏导航
    st.sidebar.markdown("""
<div style="line-height: 1.3; margin-bottom: 0.5rem;">
    <h1 style="margin: 0 0 2px 0; padding: 0; font-size: 1.5rem;">MiLecFrame</h1>
    <p style="font-size: 0.75rem; color: #888; margin: 0; padding: 0;">©FrankZCC 2026</p>
    <p style="font-size: 0.75rem; color: #888; margin: 0; padding: 0;">使用 DeepSeek V4 系列模型开发。</p>
</div>
""", unsafe_allow_html=True)
    st.sidebar.markdown("---")
    st.sidebar.caption("🧭 导航")
    
    # 使用按钮进行页面切换
    if st.sidebar.button("🖼️ 图像处理", width='stretch'):
        st.session_state.current_page = "🖼️ 图像处理"
    if st.sidebar.button("📦 批量处理", width='stretch'):
        st.session_state.current_page = "📦 批量处理"
    if st.sidebar.button("📸 相机映射管理", width='stretch'):
        st.session_state.current_page = "📸 相机映射管理"
    if st.sidebar.button("🔭 镜头映射管理", width='stretch'):
        st.session_state.current_page = "🔭 镜头映射管理"
    if st.sidebar.button("🎨 样式编辑器", width='stretch'):
        st.session_state.current_page = "🎨 样式编辑器"
    
    # 根据当前页面状态渲染相应页面
    if st.session_state.current_page == "🖼️ 图像处理":
        render_image_processing_page()
    elif st.session_state.current_page == "📦 批量处理":
        render_batch_processing_page()
    elif st.session_state.current_page == "📸 相机映射管理":
        render_camera_mapping_page()
    elif st.session_state.current_page == "🔭 镜头映射管理":
        render_lens_mapping_page()
    elif st.session_state.current_page == "🎨 样式编辑器":
        render_style_creator_page()
    
    # 侧边栏停止按钮（放在页面渲染之后，以便页面可以向侧边栏注入内容）
    st.sidebar.markdown("---")
    if 'confirm_stop' not in st.session_state:
        st.session_state.confirm_stop = False
    
    if not st.session_state.confirm_stop:
        if st.sidebar.button("🛑 停止程序", width='stretch'):
            st.session_state.confirm_stop = True
            st.rerun()
    else:
        col_stop1, col_stop2 = st.sidebar.columns(2)
        with col_stop1:
            if st.button("✅ 确认停止", width='stretch', type="primary"):
                import os, sys, subprocess
                if sys.platform == "win32":
                    server_pid = os.getppid()
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(server_pid)], capture_output=True)
                else:
                    import signal
                    os.kill(os.getppid(), signal.SIGTERM)
                os._exit(0)
        with col_stop2:
            if st.button("❌ 取消", width='stretch'):
                st.session_state.confirm_stop = False
                st.rerun()

    # 底部信息
    st.markdown("---")
    st.caption("💡 提示：本程序支持设备映射，自动识别并显示相机型号等信息")
    st.caption("📋 ©FrankZCC 2026")
    st.caption("📋 使用 DeepSeek V4 系列模型开发。")


if __name__ == "__main__":
    run_app()
