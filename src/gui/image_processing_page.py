"""
图像处理页面模块
"""
import streamlit as st
import os
import sys
import tempfile
import io
import pandas as pd
from pathlib import Path
from PIL import Image as PILImage, ImageCms

# 使用绝对导入
from src.core.image_processor import ImageProcessor
from src.frame_styles.style_manager import StyleManager
from src.utils.config_manager import ConfigManager
from src.utils.exif_helper import ExifHelper
from src.utils.logo_selector import LogoSelector
from src.utils.background_fill import BackgroundFillManager


def render_image_processing_page():
    """渲染图像处理页面"""
    
    # 初始化工具类实例
    style_manager = StyleManager()
    config_manager = ConfigManager()
    exif_helper = ExifHelper()
    logo_selector = LogoSelector()
    
    # 初始化session state变量
    if 'processing_result' not in st.session_state:
        st.session_state.processing_result = None
    if 'temp_input_path' not in st.session_state:
        st.session_state.temp_input_path = None
    if 'temp_output_path' not in st.session_state:
        st.session_state.temp_output_path = None
    if 'button_clicked' not in st.session_state:
        st.session_state.button_clicked = False
    if 'current_config' not in st.session_state:
        st.session_state.current_config = None

    # ===== 预提取 EXIF（session_state 中的文件在 widget 渲染前就已可用） =====
    sess_file = st.session_state.get('file_uploader')
    if sess_file is not None and not st.session_state.get('display_data'):
        try:
            raw_bytes = sess_file.getvalue()
            pil_img = PILImage.open(io.BytesIO(raw_bytes))
            st.session_state.file_info = exif_helper.get_file_info(pil_img)
            exif_data = exif_helper.extract_exif_data(raw_bytes)
            if exif_data:
                st.session_state.exif_data = exif_data
                st.session_state.display_data = exif_helper.get_display_data(exif_data)
        except Exception:
            pass

    # ===== 侧边栏：📋 图片信息 =====
    st.sidebar.caption("📋 图片信息")
    if (st.session_state.get('display_data') and
        st.session_state.get('file_info')):
        fi = st.session_state.file_info
        dd = st.session_state.display_data
        parts = ['<div style="font-size:0.9rem;line-height:2;">']
        parts.append(f"<b>文件</b>: {fi['format']} | {fi.get('color_space','')}<br>")
        make = dd.get('raw_camera_make', '')
        model = dd.get('raw_camera_model', '')
        cam = f"{make} {model}".strip()
        if cam:
            parts.append(f"<b>相机</b>: {cam}<br>")
        lens = dd.get('lens_model', '')
        if lens:
            parts.append(f"<b>镜头</b>: {lens}<br>")
        fl = dd.get('raw_focal_length', '')
        if fl:
            parts.append(f"<b>焦距</b>: {fl}mm<br>")
        ap = dd.get('raw_aperture', '')
        if ap:
            parts.append(f"<b>光圈</b>: f/{ap}<br>")
        ss = dd.get('raw_shutter_speed', '')
        if ss:
            parts.append(f"<b>快门</b>: {ss}s<br>")
        iso = dd.get('raw_iso', '')
        if iso:
            parts.append(f"<b>ISO</b>: {iso}<br>")
        dt = dd.get('raw_datetime_original', '')
        if dt:
            parts.append(f"<b>时间</b>: {dt}")
        parts.append('</div>')
        st.sidebar.markdown(''.join(parts), unsafe_allow_html=True)
    else:
        st.sidebar.markdown("*上传图片后显示信息*")

    # ===== CSS：配置栏样式 =====
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
</style>
    """, unsafe_allow_html=True)

    # ===== 主布局 =====
    main_col, config_col = st.columns([7, 3])

    # ======================== 右侧配置栏 ========================
    with config_col:
        # ---- ⚙️ 配置 ----
        st.markdown("### ⚙️ 配置")

        available_styles = style_manager.get_available_styles()
        if not available_styles:
            style_manager.create_sample_styles()
            available_styles = style_manager.get_available_styles()

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            selected_style = st.selectbox("相框样式", available_styles, key='style_select')
        with col_c2:
            output_format = st.selectbox("输出格式", ["JPEG", "PNG"], index=0, key='output_format')

        bg_fill_options = BackgroundFillManager.get_choices()
        default_bg_label = BackgroundFillManager.get_label(BackgroundFillManager.DEFAULT_FILL)
        default_bg_index = list(bg_fill_options.keys()).index(default_bg_label)
        selected_bg_fill_label = st.selectbox(
            "背景样式", list(bg_fill_options.keys()),
            index=default_bg_index, key='bg_fill_select'
        )
        selected_bg_fill = bg_fill_options[selected_bg_fill_label]

        font_weight_options = {
            "细体 (Light)": "light",
            "常规 (Regular)": "regular",
            "中等 (Medium)": "medium"
        }
        selected_font_weight_label = st.selectbox(
            "字重", list(font_weight_options.keys()), index=1, key='font_weight_select'
        )
        selected_font_weight = font_weight_options[selected_font_weight_label]

        st.markdown("---")

        # ---- 🎨 装饰 ----
        st.markdown("### 🎨 装饰")

        saved_author = config_manager.get_saved_author()
        default_author = saved_author if saved_author else ""

        author = st.text_input("作者姓名", value=default_author, placeholder="请输入作者姓名", key='author_input')

        if author:
            config_manager.save_user_author(author)

        # GPS状态提前计算（选框渲染在右侧，但左侧输入框需提前知道状态）
        has_gps = False
        gps_str = ""
        if st.session_state.get('exif_data'):
            gps_str = st.session_state.exif_data.get('gps', '')
            has_gps = bool(gps_str)
        _gps_active = st.session_state.get('use_gps_location', False) and has_gps

        col_loc_gps = st.columns([2, 1])
        with col_loc_gps[0]:
            if _gps_active:
                st.text_input("拍摄地点", value=gps_str, disabled=True, key='location_input')
                location = gps_str
            else:
                location = st.text_input("拍摄地点", placeholder="请输入拍摄地点", key='location_input')
        with col_loc_gps[1]:
            use_gps = st.checkbox("GPS替换", disabled=not has_gps, key='use_gps_location')

        col_lens_short = st.columns([2, 1])
        with col_lens_short[0]:
            lens_display_option = st.selectbox(
                "镜头显示", ["相机+镜头", "只显示相机", "只显示镜头"],
                index=0, key='lens_display_option'
            )
        with col_lens_short[1]:
            if 'use_short_lens' not in st.session_state:
                st.session_state.use_short_lens = False
            if '_pending_use_short_lens' in st.session_state:
                st.session_state.use_short_lens = st.session_state.pop('_pending_use_short_lens')
            use_short_lens = st.checkbox("短版镜头名", key='use_short_lens')

        mode_map = {"相机+镜头": "combined", "只显示相机": "camera_only", "只显示镜头": "lens_only"}
        lens_display_mode = mode_map[lens_display_option]

        st.markdown("---")

        # ---- 🏷️ Logo ----
        st.markdown("### 🏷️ Logo")

        current_style_config = style_manager.get_style_config(selected_style)
        is_logo_enabled_by_config = current_style_config.get('logo', {}).get('enabled', False)

        selected_logo = None
        if is_logo_enabled_by_config:
            available_logos = ["自动匹配", "无"] + logo_selector.scan_logos()

            camera_brand = None
            if st.session_state.get('exif_data'):
                camera_brand = ExifHelper.get_camera_brand(st.session_state.exif_data)

            selected_logo_option = st.selectbox("选择Logo", available_logos, index=0, key='logo_select')

            if selected_logo_option == "无":
                selected_logo = ""
            elif selected_logo_option != "自动匹配":
                selected_logo = selected_logo_option
            else:
                if camera_brand:
                    matched_logo = logo_selector.auto_match_logo(camera_brand)
                    if matched_logo:
                        selected_logo = matched_logo
        else:
            st.info("当前样式未启用Logo")

        st.markdown("---")

        # ---- 💧 水印 ----
        with st.expander("💧 水印", expanded=False):
            enable_watermark = st.checkbox("启用水印", key='enable_watermark')
            watermark_text = ""
            watermark_position = "bottom-right"
            watermark_opacity = 50
            watermark_color = (255, 255, 255)
            if enable_watermark:
                watermark_text = st.text_input("内容", value="© MiLeica Frame", key='watermark_text')
                col_w1, col_w2 = st.columns(2)
                with col_w1:
                    watermark_position_option = st.selectbox(
                        "位置", ["左上", "顶部居中", "右上", "左下", "底部居中", "右下"],
                        key="watermark_pos"
                    )
                    position_map = {
                        "左上": "top-left", "右上": "top-right", "左下": "bottom-left",
                        "右下": "bottom-right", "顶部居中": "top-center", "底部居中": "bottom-center"
                    }
                    watermark_position = position_map[watermark_position_option]
                    watermark_opacity = st.slider("不透明度 (%)", 0, 100, 50, key="watermark_opacity")
                with col_w2:
                    watermark_color_option = st.selectbox("颜色", ["白色", "黑色"], key="watermark_color")
                    color_map = {"白色": (255, 255, 255), "黑色": (0, 0, 0)}
                    watermark_color = color_map[watermark_color_option]

    # ======================== 主内容列 ========================
    with main_col:
        st.markdown("### 📤 上传图片")

        # 文件上传器
        uploaded_file = st.file_uploader(
            "请选择一张图片",
            type=["jpg", "jpeg", "png", "tiff", "bmp"],
            accept_multiple_files=False,
            key='file_uploader'
        )

        # 图片移除时自动清除相关数据
        if uploaded_file is None:
            for key in ['exif_data', 'file_info', 'display_data', 'last_file_id',
                        'processing_result', 'temp_input_path', 'temp_output_path']:
                st.session_state.pop(key, None)

        if uploaded_file is not None:
            # 一次性读取并打开图像
            raw_bytes = uploaded_file.getvalue()
            pil_img = PILImage.open(io.BytesIO(raw_bytes))

            w, h = pil_img.size

            # 新图片上传时按方向设置短版镜头名勾选
            if st.session_state.get('last_file_id') != uploaded_file.file_id:
                st.session_state.last_file_id = uploaded_file.file_id
                st.session_state._pending_use_short_lens = (h >= w)

            # 文件信息
            file_info = exif_helper.get_file_info(pil_img)
            st.session_state.file_info = file_info

            # 提取EXIF数据
            try:
                exif_data = exif_helper.extract_exif_data(raw_bytes)
                st.session_state.exif_data = exif_data
                if exif_data:
                    st.session_state.display_data = exif_helper.get_display_data(exif_data)
            except Exception:
                pass

            # ---- 响应式预览 ----
            def _render_original():
                try:
                    preview_img = pil_img
                    icc = pil_img.info.get('icc_profile')
                    if icc:
                        preview_img = ImageCms.profileToProfile(
                            preview_img, io.BytesIO(icc), ImageCms.createProfile('sRGB'),
                            outputMode='RGB',
                            renderingIntent=ImageCms.Intent.PERCEPTUAL
                        )
                    st.image(preview_img, caption="原始图片", width='stretch')
                except Exception:
                    st.image(uploaded_file, caption="原始图片", width='stretch')

            def _render_effect():
                if (st.session_state.processing_result and
                    st.session_state.temp_output_path and
                    os.path.exists(st.session_state.temp_output_path)):
                    result_img = PILImage.open(st.session_state.temp_output_path)
                    result_img.thumbnail((1200, 1200), PILImage.Resampling.LANCZOS)
                    st.image(result_img, caption="效果预览", width='stretch')
                else:
                    st.info("👆 请配置选项并点击\"生成相框\"按钮")

            is_wide = w > h

            if is_wide:
                # 横向构图：上下排列，缩至 75% 宽度居中
                col_l, col_img, col_r = st.columns([1, 6, 1])
                with col_img:
                    _render_original()
                    _render_effect()
            else:
                # 竖向/方形：左右排列
                preview_left, preview_right = st.columns(2)
                with preview_left:
                    _render_original()
                with preview_right:
                    _render_effect()

            # ---- 按钮 + 状态 ----
            current_config = {
                'selected_style': selected_style,
                'selected_bg_fill': selected_bg_fill,
                'enable_watermark': enable_watermark,
                'watermark_text': watermark_text,
                'watermark_position': watermark_position,
                'watermark_opacity': watermark_opacity,
                'selected_logo': selected_logo,
                'author': author,
                'location': location,
                'font_weight': selected_font_weight,
                'output_format': output_format,
                'lens_display_mode': lens_display_mode,
                'use_short_lens': use_short_lens
            }

            # 检查配置是否发生变化
            config_changed = (
                st.session_state.current_config is not None and
                st.session_state.current_config != current_config
            )

            # 更新当前配置
            st.session_state.current_config = current_config

            # 根据配置是否变化更新按钮状态
            if config_changed:
                st.session_state.button_clicked = False

            # 按钮显示逻辑
            button_label = "重新生成" if config_changed and st.session_state.processing_result else "生成相框"

            # 按钮样式
            button_color = '#ff6b6b' if config_changed and st.session_state.processing_result else '#80ed99'
            st.markdown(f"""
<style>
div.stButton > button:first-child {{
    background-color: {button_color} !important;
}}
[data-testid="stSidebar"] div.stButton > button:first-child {{
    background-color: inherit !important;
    color: inherit !important;
    border-color: inherit !important;
}}
</style>
            """, unsafe_allow_html=True)

            # 生成相框按钮
            output_ext = ".jpg" if output_format == "JPEG" else ".png"
            if st.button(button_label, key='process_button'):
                st.session_state.button_clicked = True
                error_info = None
                error_detail = None
                processing_success = False
                with st.spinner("正在处理图片..."):
                    try:
                        # 创建临时文件来保存上传的图片
                        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as temp_input:
                            temp_input.write(uploaded_file.getvalue())
                            temp_input_path = temp_input.name

                        # 创建临时输出文件（先清理旧的）
                        if st.session_state.temp_output_path and os.path.exists(st.session_state.temp_output_path):
                            try:
                                os.unlink(st.session_state.temp_output_path)
                            except OSError:
                                pass
                        with tempfile.NamedTemporaryFile(delete=False, suffix=output_ext) as temp_output:
                            temp_output_path = temp_output.name

                        # 构建装饰元素列表
                        decorations = []
                        if enable_watermark and watermark_text:
                            decorations.append({
                                'type': 'watermark',
                                'params': {
                                    'text': watermark_text,
                                    'position': watermark_position,
                                    'opacity': watermark_opacity,
                                    'color': watermark_color
                                }
                            })

                        # 处理图像
                        processor = ImageProcessor()

                        success = processor.process(
                            input_path=temp_input_path,
                            output_path=temp_output_path,
                            author=author if author else None,
                            location=location if location else None,
                            style_name=selected_style,
                            bg_fill_type=selected_bg_fill,
                            decorations=decorations if decorations else None,
                            font_weight=selected_font_weight,
                            logo_filename=selected_logo,
                            lens_display_mode=lens_display_mode,
                            use_short_lens=use_short_lens
                        )

                        if success:
                            st.session_state.temp_input_path = temp_input_path
                            st.session_state.temp_output_path = temp_output_path
                            st.session_state.processing_result = temp_output_path
                            processing_success = True
                        else:
                            error_info = "❌ 图片处理失败，请查看错误日志"

                    except Exception as e:
                        error_info = f"❌ 处理过程中出现错误: {str(e)}"
                        import traceback
                        error_detail = traceback.format_exc()

                    finally:
                        # 清理临时输入文件
                        if 'temp_input_path' in locals() and os.path.exists(temp_input_path):
                            os.unlink(temp_input_path)
                            st.session_state.temp_input_path = None

                if error_info:
                    st.error(error_info)
                    if error_detail:
                        st.code(error_detail)
                elif processing_success:
                    st.rerun()

            # 已有处理结果时始终显示下载按钮和状态
            if (st.session_state.processing_result and
                st.session_state.temp_output_path and
                os.path.exists(st.session_state.temp_output_path)):

                with open(st.session_state.temp_output_path, "rb") as result_file:
                    st.download_button(
                        label="💾 下载处理后的图片",
                        data=result_file,
                        file_name=f"framed_{Path(uploaded_file.name).stem}{output_ext}",
                        mime="image/jpeg" if output_format == "JPEG" else "image/png",
                        key="download_processed_image_cached"
                    )

                if config_changed:
                    st.warning('⚠️ 配置已更改，请点击"重新生成"按钮更新预览')
                else:
                    st.success("✅ 图片处理成功！")

        else:
            st.info("👆 请先上传一张图片")
