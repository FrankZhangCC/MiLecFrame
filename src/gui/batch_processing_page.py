# Copyright (c) 2026 FrankZhangCC
# MIT License - see LICENSE file for details

"""
批量处理页面模块
提供多文件上传、配置设置、一键批处理和实时进度显示
"""
import streamlit as st
import os
import io
import tempfile
import shutil
import sys
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
from PIL import Image as PILImage

from src.core.batch_processor import BatchProcessor, BatchResult
from src.frame_styles.style_manager import StyleManager
from src.utils.config_manager import ConfigManager
from src.utils.exif_helper import ExifHelper
from src.utils.logo_selector import LogoSelector
from src.utils.background_fill import BackgroundFillManager


# ==================== 缓存工具函数（与单张处理页面共享底层逻辑，独立缓存） ====================

@st.cache_resource
def _get_style_manager():
    """获取样式管理器（缓存资源）"""
    return StyleManager()


@st.cache_resource
def _get_config_manager():
    """获取配置管理器（缓存资源）"""
    return ConfigManager()


@st.cache_resource
def _get_exif_helper():
    """获取 EXIF 助手（缓存资源）"""
    return ExifHelper()


@st.cache_resource
def _get_logo_selector():
    """获取 Logo 选择器（缓存资源）"""
    return LogoSelector()


@st.cache_data(ttl=60)
def _get_available_styles():
    """获取可用样式列表（缓存 60 秒）"""
    sm = StyleManager()
    styles = sm.get_available_styles()
    if not styles:
        sm.create_sample_styles()
        styles = sm.get_available_styles()
    return styles


@st.cache_data(ttl=300)
def _get_bg_fill_choices():
    """获取背景填充选项字典（缓存 300 秒）"""
    return BackgroundFillManager.get_choices()


@st.cache_data(ttl=60)
def _get_cached_style_config(style_name: str):
    """获取样式配置（缓存 60 秒）"""
    return StyleManager().get_style_config(style_name)


@st.cache_data(ttl=60)
def _scan_logos():
    """扫描 logos 目录（缓存 60 秒）"""
    return LogoSelector().scan_logos()


# ==================== 支持的文件扩展名 ====================

_SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.webp'}


# ==================== 文件夹选择对话框 ====================

def _open_folder_dialog() -> Optional[str]:
    """
    打开原生文件夹选择对话框（在独立子进程中运行 tkinter）

    必须用子进程而非直接调用：Streamlit 脚本运行在工作线程，而 macOS 要求
    GUI 操作必须在主线程，直接在本进程 tk.Tk() 会卡死整个服务。子进程拥有
    独立主线程，可正常弹窗。仅在本地运行（浏览器与服务同机）时有效；
    无 tkinter / 用户取消 / 超时均返回 None。

    Returns:
        选定的文件夹路径，或 None
    """
    script = (
        "import tkinter as tk; from tkinter import filedialog; "
        "root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True); "
        "p = filedialog.askdirectory(title='选择输出文件夹', mustexist=False); "
        "root.destroy(); print(p)"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=120
        )
        path = result.stdout.strip()
        return path if path else None
    except Exception:
        return None


# ==================== 工具函数 ====================

def _format_file_size(size_bytes: int) -> str:
    """
    将字节数格式化为可读的文件大小字符串

    Args:
        size_bytes: 文件大小（字节）

    Returns:
        格式化字符串，如 "12.5 MB"
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _extract_file_infos(uploaded_files) -> Tuple[List[dict], List]:
    """
    从上传文件列表中提取尺寸和大小信息

    仅读取图像头部获取宽高（不解码像素），速度很快。
    无法读取的图像标记为 can_read=False。

    Args:
        uploaded_files: UploadedFile 对象列表

    Returns:
        (file_infos, valid_files): 文件信息列表 + 可读取文件列表
    """
    file_infos = []
    valid_files = []
    for uf in uploaded_files:
        # 验证扩展名
        ext = Path(uf.name).suffix.lower()
        if ext not in _SUPPORTED_EXTENSIONS:
            continue
        valid_files.append(uf)

        info = {
            'name': uf.name,
            'size': uf.size or 0,
            'width': None,
            'height': None,
            'can_read': False,
        }
        try:
            data = uf.getvalue()
            img = PILImage.open(io.BytesIO(data))
            info['width'], info['height'] = img.size
            info['can_read'] = True
        except Exception:
            pass
        file_infos.append(info)
    return file_infos, valid_files


# ==================== 页面渲染函数 ====================

def render_batch_processing_page():
    """渲染批量处理页面"""

    # ===== 初始化 session_state 变量 =====
    if 'batch_output_folder' not in st.session_state:
        st.session_state.batch_output_folder = str(Path.home() / "MiLeica_Output")
    if 'batch_scanned_files' not in st.session_state:
        st.session_state.batch_scanned_files = []  # List[UploadedFile]
    if 'batch_file_infos' not in st.session_state:
        st.session_state.batch_file_infos = []      # List[dict]
    if 'batch_file_ids' not in st.session_state:
        st.session_state.batch_file_ids = set()     # set of str (file_id)
    if 'batch_result' not in st.session_state:
        st.session_state.batch_result: BatchResult | None = None

    # ===== 初始化工具实例 =====
    style_manager = _get_style_manager()
    config_manager = _get_config_manager()

    # ===== CSS：右侧配置栏样式（复用单张处理页面的样式风格） =====
    st.markdown("""
<style>
.stHorizontalBlock:first-of-type > [data-testid="column"]:nth-child(2) {
    background-color: #f0f2f6;
    border-radius: 12px;
    padding: 0.75rem;
}
.stHorizontalBlock:first-of-type > [data-testid="column"]:nth-child(2) [data-testid="column"]:nth-child(2) div[data-testid="stCheckbox"] {
    margin-top: 1.5rem;
}
/* 文件列表行样式 */
.batch-file-row {
    display: flex;
    align-items: center;
    padding: 2px 0;
    font-size: 0.85rem;
}
.batch-file-name {
    flex: 2;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.batch-file-dim {
    flex: 1;
    text-align: center;
    color: #666;
}
.batch-file-size {
    flex: 0 0 90px;
    text-align: right;
    color: #666;
}
.batch-file-warn {
    flex: 1;
    text-align: center;
    color: #e67e22;
}
</style>
    """, unsafe_allow_html=True)

    # ===== 主布局：左操作区 (7) + 右配置栏 (3) =====
    main_col, config_col = st.columns([7, 3])

    # ======================== 右侧配置栏 ========================
    with config_col:
        st.markdown("### ⚙️ 批处理配置")

        available_styles = _get_available_styles()

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            default_style = "底部信息条 Bottom Bars"
            default_style_index = available_styles.index(default_style) if default_style in available_styles else 0
            selected_style = st.selectbox(
                "相框样式", available_styles, index=default_style_index,
                key='batch_style_select'
            )
        with col_c2:
            output_format = st.selectbox("输出格式", ["JPEG", "PNG"], index=0, key='batch_output_format')

        bg_fill_options = _get_bg_fill_choices()
        default_bg_label = BackgroundFillManager.get_label(BackgroundFillManager.DEFAULT_FILL)
        default_bg_index = list(bg_fill_options.keys()).index(default_bg_label) if default_bg_label in bg_fill_options else 0
        selected_bg_fill_label = st.selectbox(
            "背景样式", list(bg_fill_options.keys()),
            index=default_bg_index, key='batch_bg_fill_select'
        )
        selected_bg_fill = bg_fill_options[selected_bg_fill_label]

        font_weight_options = {
            "细体 (Light)": "light",
            "常规 (Regular)": "regular",
            "中等 (Medium)": "medium"
        }
        selected_font_weight_label = st.selectbox(
            "字重", list(font_weight_options.keys()), index=2,
            key='batch_font_weight_select'
        )
        selected_font_weight = font_weight_options[selected_font_weight_label]

        # 背景增强开关（仅高斯模糊类型有效）
        _selected_bg_cfg = BackgroundFillManager.FILL_TYPES.get(selected_bg_fill, {})
        _is_gaussian = _selected_bg_cfg.get('method') == 'gaussian'
        _enhance_help = "增强模糊背景的色彩饱和度，补偿白色/黑色覆盖层的颜色淡化"
        if not _is_gaussian:
            _enhance_help += "（仅高斯模糊背景有效，当前选择为纯色填充）"
        enable_saturation = st.checkbox(
            "背景增强", value=True, key='batch_enable_saturation',
            disabled=not _is_gaussian, help=_enhance_help
        )

        st.markdown("---")

        # ---- 🎨 作者与地点 ----
        st.markdown("### 🎨 作者与地点")

        saved_author = config_manager.get_saved_author()
        default_author = saved_author if saved_author else ""
        author = st.text_input(
            "作者姓名", value=default_author, placeholder="请输入作者姓名",
            key='batch_author_input'
        )
        if author:
            config_manager.save_user_author(author)

        col_loc_gps = st.columns([2, 1])
        with col_loc_gps[0]:
            location = st.text_input(
                "拍摄地点", placeholder="请输入拍摄地点（可为空，逐张使用GPS）",
                key='batch_location_input'
            )
        with col_loc_gps[1]:
            use_gps = st.checkbox(
                "GPS替换",
                help="逐张照片使用各自的 GPS 数据替换手动输入的拍摄地点",
                key='batch_use_gps_location'
            )

        col_lens_short = st.columns([2, 1])
        with col_lens_short[0]:
            lens_display_option = st.selectbox(
                "镜头显示", ["相机+镜头", "只显示相机", "只显示镜头"],
                index=0, key='batch_lens_display_option'
            )
        with col_lens_short[1]:
            use_short_lens = st.checkbox("短版镜头名", key='batch_use_short_lens')

        mode_map = {"相机+镜头": "combined", "只显示相机": "camera_only", "只显示镜头": "lens_only"}
        lens_display_mode = mode_map[lens_display_option]

        st.markdown("---")

        # ---- ✏️ 自定义文本 ----
        current_style_config = _get_cached_style_config(selected_style)
        custom_text_cfg = current_style_config.get('layout', {}).get('custom_text', {})
        is_custom_text_enabled = isinstance(custom_text_cfg, dict) and custom_text_cfg.get('enabled', False)

        custom_text = None
        if is_custom_text_enabled:
            st.markdown("### ✏️ 自定义文本")
            default_custom = "Always believe that something wonderful\nis about to happen."
            custom_text = st.text_input(
                "输入自定义文本",
                value=default_custom.replace('\n', ' '),
                placeholder="输入要显示的自定义文本...",
                key='batch_custom_text_input',
            )
            st.markdown("---")
        else:
            # 样式不支持时，确保 session_state 中不留残留值
            st.session_state.pop('batch_custom_text_input', None)

        # ---- 🏷️ Logo ----
        st.markdown("### 🏷️ Logo")

        is_logo_enabled_by_config = current_style_config.get('logo', {}).get('enabled', False)

        selected_logo = None
        if is_logo_enabled_by_config:
            available_logos = ["自动匹配", "无"] + _scan_logos()
            selected_logo_option = st.selectbox(
                "选择Logo", available_logos, index=0, key='batch_logo_select'
            )
            if selected_logo_option == "无":
                selected_logo = "none"
            elif selected_logo_option == "自动匹配":
                selected_logo = "auto"
            else:
                selected_logo = selected_logo_option
        else:
            st.info("当前样式未启用Logo")
            selected_logo = "none"

        st.markdown("---")

        # ---- 💧 水印 ----
        with st.expander("💧 水印", expanded=False):
            enable_watermark = st.checkbox("启用水印", key='batch_enable_watermark')
            watermark_text = ""
            watermark_position = "bottom-right"
            watermark_opacity = 50
            watermark_color = (255, 255, 255)
            if enable_watermark:
                watermark_text = st.text_input("内容", value="© MiLeica Frame", key='batch_watermark_text')
                col_w1, col_w2 = st.columns(2)
                with col_w1:
                    watermark_position_option = st.selectbox(
                        "位置", ["左上", "顶部居中", "右上", "左下", "底部居中", "右下"],
                        key="batch_watermark_pos"
                    )
                    position_map = {
                        "左上": "top-left", "右上": "top-right", "左下": "bottom-left",
                        "右下": "bottom-right", "顶部居中": "top-center", "底部居中": "bottom-center"
                    }
                    watermark_position = position_map[watermark_position_option]
                    watermark_opacity = st.slider("不透明度 (%)", 0, 100, 50, key="batch_watermark_opacity")
                with col_w2:
                    watermark_color_option = st.selectbox("颜色", ["白色", "黑色"], key="batch_watermark_color")
                    color_map = {"白色": (255, 255, 255), "黑色": (0, 0, 0)}
                    watermark_color = color_map[watermark_color_option]

    # ======================== 主内容列（左侧操作区） ========================
    with main_col:
        st.markdown("### 📂 选择文件")

        # ---- 文件上传器 ----
        uploaded_files = st.file_uploader(
            "选择多张图片（可直接进入文件夹 Ctrl+A 全选）",
            type=["jpg", "jpeg", "png", "tiff", "tif", "bmp", "webp"],
            accept_multiple_files=True,
            key='batch_file_uploader',
        )

        has_files = False
        file_infos: List[dict] = []

        if uploaded_files:
            # ===== 检测文件列表是否变更（通过 file_id 集合比对） =====
            current_ids = {uf.file_id for uf in uploaded_files}
            if current_ids != st.session_state.batch_file_ids:
                # 文件列表变更 → 重新提取信息
                with st.spinner("正在读取文件信息..."):
                    file_infos, valid_files = _extract_file_infos(uploaded_files)
                st.session_state.batch_file_ids = current_ids
                st.session_state.batch_file_infos = file_infos
                st.session_state.batch_scanned_files = valid_files
                st.session_state.batch_result = None  # 清空旧结果
            else:
                file_infos = st.session_state.batch_file_infos

            has_files = bool(file_infos)
            total_count = len(file_infos)
            readable_count = sum(1 for info in file_infos if info['can_read'])

            if has_files:
                st.success(f"✅ 已选择 **{total_count}** 个文件（其中 {readable_count} 个可读取）")

                # ===== 文件列表（含尺寸和大小） =====
                with st.expander(f"📋 文件列表 ({total_count} 个)", expanded=total_count <= 20):
                    max_display = 50
                    for info in file_infos[:max_display]:
                        _render_file_row(info)
                    if total_count > max_display:
                        st.caption(f"  ... 还有 {total_count - max_display} 个文件未显示")
        else:
            # 无文件时清空状态
            if st.session_state.batch_file_ids:
                st.session_state.batch_file_ids = set()
                st.session_state.batch_file_infos = []
                st.session_state.batch_scanned_files = []
            st.info("👆 请选择要处理的图片文件（可进入文件夹后 Ctrl+A 全选）")

        # ---- 输出文件夹设置 ----
        st.markdown("### 📁 输出文件夹")

        col_out, col_browse = st.columns([4, 1])
        with col_out:
            output_folder = st.text_input(
                "输出文件夹路径（不存在则自动创建）",
                value=st.session_state.batch_output_folder,
                placeholder="点击右侧「浏览」选择，或手动输入绝对路径",
                label_visibility="collapsed"
            )
            # 同步 widget 当前值 → session_state（无 key 时手动管理）
            st.session_state.batch_output_folder = output_folder
        with col_browse:
            if st.button("📂 浏览", key='batch_browse_output_btn', width='stretch',
                         help="打开系统文件夹选择对话框（仅本地运行时有效）"):
                selected_path = _open_folder_dialog()
                if selected_path:
                    st.session_state.batch_output_folder = selected_path
                    st.rerun()

        st.markdown("---")

        # ---- 操作按钮与进度 ----
        effective_file_count = sum(1 for info in file_infos if info['can_read'])
        can_start = has_files and effective_file_count > 0 and bool(st.session_state.batch_output_folder)

        col_btn, col_count = st.columns([1, 1])
        with col_btn:
            start_clicked = st.button(
                f"🚀 开始批量处理 ({effective_file_count} 张)",
                disabled=not can_start,
                width='stretch',
                key='batch_start_btn',
                type="primary" if can_start else "secondary"
            )
        with col_count:
            if has_files:
                st.caption(f"共 {effective_file_count} 张待处理")

        # ---- 执行批处理 ----
        if start_clicked and can_start:
            _execute_batch_processing(
                output_format=output_format,
                author=author,
                location=location,
                selected_style=selected_style,
                selected_bg_fill=selected_bg_fill,
                selected_font_weight=selected_font_weight,
                enable_saturation=enable_saturation,
                use_gps=use_gps,
                lens_display_mode=lens_display_mode,
                use_short_lens=use_short_lens,
                selected_logo=selected_logo,
                enable_watermark=enable_watermark,
                watermark_text=watermark_text,
                watermark_position=watermark_position,
                watermark_opacity=watermark_opacity,
                watermark_color=watermark_color,
                custom_text=st.session_state.get('batch_custom_text_input', '') or None,
            )

        # ---- 显示处理结果 ----
        if st.session_state.batch_result is not None:
            _display_results(st.session_state.batch_result)


# ==================== 文件列表渲染 ====================

def _render_file_row(info: dict):
    """
    渲染单个文件行（使用 HTML 实现三列对齐布局）

    Args:
        info: 文件信息字典，含 name / width / height / size / can_read
    """
    name = info['name']
    size_str = _format_file_size(info['size'])
    if info['can_read']:
        dim_str = f"{info['width']} × {info['height']}"
    else:
        dim_str = "无法读取"

    if not info['can_read']:
        dim_class = "batch-file-warn"
        icon = "⚠"
    else:
        dim_class = "batch-file-dim"
        icon = "📄"

    st.markdown(
        f'<div class="batch-file-row">'
        f'<span class="batch-file-name">{icon} {name}</span>'
        f'<span class="{dim_class}">{dim_str}</span>'
        f'<span class="batch-file-size">{size_str}</span>'
        f'</div>',
        unsafe_allow_html=True
    )


# ==================== 辅助函数 ====================

def _collect_input_files(file_list: List) -> Tuple[List[str], str]:
    """
    将 UploadedFile 列表保存到临时目录，返回临时路径列表

    Args:
        file_list: UploadedFile 对象列表

    Returns:
        (文件路径列表, 临时目录路径)
    """
    temp_dir = tempfile.mkdtemp(prefix="mileica_batch_")
    temp_paths = []
    for uf in file_list:
        name = getattr(uf, 'name', 'unknown.jpg')
        temp_path = os.path.join(temp_dir, name)
        try:
            with open(temp_path, 'wb') as f:
                f.write(uf.getvalue())
            temp_paths.append(temp_path)
        except Exception:
            pass
    return temp_paths, temp_dir


def _execute_batch_processing(
    output_format: str,
    author: str,
    location: str,
    selected_style: str,
    selected_bg_fill: str,
    selected_font_weight: str,
    enable_saturation: bool,
    use_gps: bool,
    lens_display_mode: str,
    use_short_lens: bool,
    selected_logo: Optional[str],
    enable_watermark: bool,
    watermark_text: str,
    watermark_position: str,
    watermark_opacity: int,
    watermark_color: tuple,
    custom_text: Optional[str] = None,
):
    """
    执行批量处理

    收集配置参数 → 准备输入文件 → 创建 BatchProcessor → 逐张处理 → 存储结果
    """
    # ===== 组装 decorations 参数 =====
    decorations = None
    if enable_watermark and watermark_text:
        decorations = [{
            'type': 'watermark',
            'params': {
                'text': watermark_text,
                'position': watermark_position,
                'opacity': watermark_opacity,
                'color': watermark_color,
            }
        }]

    # ===== 组装 saturation_override =====
    saturation_override = None if enable_saturation else 1.0

    # ===== 准备输入文件 =====
    file_list = st.session_state.batch_scanned_files
    if not file_list:
        st.error("没有可处理的文件")
        return

    input_files, temp_dir = _collect_input_files(file_list)

    if not input_files:
        st.error("无法收集输入文件")
        return

    output_folder = st.session_state.batch_output_folder

    # ===== 创建进度 UI 占位符 =====
    progress_bar = st.progress(0)
    progress_text = st.empty()
    status_text = st.empty()

    # 进度回调函数
    def on_progress(done: int, total: int, filename: str, status: str):
        progress_bar.progress(done / total)
        progress_text.text(f"正在处理 ({done}/{total}): {filename}")
        status_text.text(status)

    # ===== 执行批量处理 =====
    bp = BatchProcessor()
    result = bp.batch_process(
        input_files=input_files,
        output_folder=output_folder,
        author=author or None,
        location=location or None,
        style_name=selected_style or None,
        bg_fill_type=selected_bg_fill,
        output_format=output_format,
        decorations=decorations,
        font_weight=selected_font_weight,
        logo_selection=selected_logo or 'auto',
        lens_display_mode=lens_display_mode,
        use_short_lens=use_short_lens,
        saturation_override=saturation_override,
        use_gps_location=use_gps,
        progress_callback=on_progress,
        skip_existing=True,
        custom_text=custom_text or None,
    )

    # 更新最终进度
    progress_bar.progress(1.0)
    progress_text.text("处理完成！")
    status_text.empty()

    # 存储结果
    st.session_state.batch_result = result

    # 清理临时文件
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass


def _display_results(result: BatchResult):
    """
    显示批量处理结果汇总

    Args:
        result: BatchResult 对象
    """
    st.markdown("---")
    st.markdown("### 📊 处理结果")

    # 统计卡片
    col_success, col_fail, col_skip = st.columns(3)
    with col_success:
        st.metric("✅ 成功", result.success_count)
    with col_fail:
        st.metric("❌ 失败", result.fail_count, delta=None)
    with col_skip:
        st.metric("⏭ 跳过", result.skip_count, delta=None)

    # 进度条形图
    total_processed = result.success_count + result.fail_count + result.skip_count
    if total_processed > 0:
        st.caption(f"成功率: {result.success_count}/{total_processed} ({result.success_count / total_processed * 100:.0f}%)")
        st.progress(result.success_count / total_processed)

    # 失败详情
    if result.failed_files:
        with st.expander(f"📋 失败详情 ({len(result.failed_files)} 个)", expanded=False):
            for file_path, error_msg in result.failed_files:
                file_name = Path(file_path).name
                st.text(f"❌ {file_name}")
                st.caption(f"   {error_msg}")

    # 输出文件夹快捷入口
    output_folder = st.session_state.batch_output_folder
    if output_folder:
        st.info(f"📁 输出文件夹: `{output_folder}`")

    # 清空结果按钮
    if st.button("🔄 清除结果，开始新批处理", key='batch_clear_result'):
        st.session_state.batch_result = None
        st.session_state.batch_scanned_files = []
        st.session_state.batch_file_infos = []
        st.session_state.batch_file_ids = set()
        st.rerun()
