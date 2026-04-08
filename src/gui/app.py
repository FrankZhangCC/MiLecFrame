"""
GUI应用程序模块
使用Streamlit构建网页版GUI界面
"""
import streamlit as st
import os
import sys
import tempfile
import io
from pathlib import Path
from PIL import Image as PILImage

# 使用绝对导入
from src.core.image_processor import ImageProcessor
from src.frame_styles.style_manager import StyleManager
from src.utils.config_manager import ConfigManager
from src.utils.exif_helper import ExifHelper
from src.utils.logo_selector import LogoSelector  # 导入Logo选择器


def run_app():
    """运行GUI应用程序"""
    
    # 初始化工具类实例
    style_manager = StyleManager()
    config_manager = ConfigManager()
    exif_helper = ExifHelper()
    logo_selector = LogoSelector()  # 初始化Logo选择器
    
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
        st.session_state.current_config = {}
    
    st.set_page_config(
        page_title="MiLeica Frame - 照片相框程序",
        page_icon="📷",
        layout="wide"
    )
    
    # 设置标题
    st.title("📷 MiLeica Frame - 照片相框程序")
    st.markdown("---")
    
    # 侧边栏配置
    with st.sidebar:
        st.header("⚙️ 配置选项")
        
        # 相框样式选择
        available_styles = style_manager.get_available_styles()
        if not available_styles:
            # 如果没有样式，创建示例样式
            style_manager.create_sample_styles()
            available_styles = style_manager.get_available_styles()
        
        selected_style = st.selectbox("选择相框样式", available_styles, key='style_select')
        
        # 背景填充类型选择
        bg_fill_options = {
            "纯白背景": "pure_white",
            "纯黑背景": "pure_black", 
            "模糊背景 (深色 65%)": "gaussian_black_65",
            "模糊背景 (浅色 65%)": "gaussian_white_65",
            "模糊背景 (深色 35%)": "gaussian_black_35",
            "模糊背景 (浅色 35%)": "gaussian_white_35"
        }
        # 设置默认选项为"模糊背景 (浅色 65%)"
        default_bg_label = "模糊背景 (浅色 65%)"
        default_bg_index = list(bg_fill_options.keys()).index(default_bg_label)
        selected_bg_fill_label = st.selectbox("背景样式", list(bg_fill_options.keys()), index=default_bg_index, key='bg_fill_select')
        selected_bg_fill = bg_fill_options[selected_bg_fill_label]
        
        # 装饰元素选项
        st.subheader("🎨 装饰元素")
        
        # 边框配置
        enable_border = st.checkbox("添加边框", key='enable_border')
        border_width = 0
        border_color = (255, 255, 255)
        if enable_border:
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                border_width = st.slider("边框宽度 (px)", 1, 20, 5, key='border_width')
            with col_b2:
                border_color_option = st.selectbox("边框颜色", ["白色", "黑色", "灰色"], key='border_color')
                color_map = {"白色": (255, 255, 255), "黑色": (0, 0, 0), "灰色": (128, 128, 128)}
                border_color = color_map[border_color_option]
        
        # 水印配置
        enable_watermark = st.checkbox("添加水印", key='enable_watermark')
        watermark_text = ""
        watermark_position = "bottom-right"
        watermark_opacity = 50
        if enable_watermark:
            watermark_text = st.text_input("水印内容", value="© MiLeica Frame", key='watermark_text')
            col_w1, col_w2 = st.columns(2)
            with col_w1:
                watermark_position_option = st.selectbox(
                    "水印位置", 
                    ["左上", "右上", "左下", "右下", "居中"],
                    key="watermark_pos"
                )
                position_map = {
                    "左上": "top-left",
                    "右上": "top-right", 
                    "左下": "bottom-left",
                    "右下": "bottom-right",
                    "居中": "center"
                }
                watermark_position = position_map[watermark_position_option]
            with col_w2:
                watermark_opacity = st.slider("不透明度 (%)", 0, 100, 50, key="watermark_opacity")
        
        # 获取当前样式配置以确定是否启用了Logo
        current_style_config = style_manager.get_style_config(selected_style)
        is_logo_enabled_by_config = current_style_config.get('logo', {}).get('enabled', False)
        
        # 如果样式配置中启用了Logo，则显示Logo选择器
        selected_logo = None
        if is_logo_enabled_by_config:
            st.subheader("🏷️ Logo设置")
            available_logos = ["自动匹配"] + logo_selector.scan_logos()
            
            # 检查是否有EXIF数据以确定相机品牌
            camera_brand = None
            if 'exif_data' in st.session_state and st.session_state.exif_data:
                camera_brand = ExifHelper.get_camera_brand(st.session_state.exif_data)
            if camera_brand:
                matched_logo = logo_selector.auto_match_logo(camera_brand)
                if matched_logo:
                    # 如果找到匹配的logo，默认选择该logo
                    default_logo_index = 0 if available_logos[0] == "自动匹配" else available_logos.index(matched_logo)
                else:
                    default_logo_index = 0  # 默认为"自动匹配"
            else:
                default_logo_index = 0  # 默认为"自动匹配"
            
            selected_logo_option = st.selectbox(
                "选择Logo", 
                available_logos,
                index=default_logo_index,
                key='logo_select'
            )
            # 如果选择了具体的logo文件而不是"自动匹配"，则使用该文件名
            if selected_logo_option != "自动匹配":
                selected_logo = selected_logo_option
            else:
                selected_logo = None
        
        # 作者输入
        # 尝试从配置中获取保存的作者名
        saved_author = config_manager.get_saved_author()
        default_author = saved_author if saved_author else ""
        author = st.text_input("作者姓名", value=default_author, placeholder="请输入作者姓名", key='author_input')
        
        # 保存作者名到配置
        if author:
            config_manager.save_user_author(author)
        
        # 拍摄地点输入
        location = st.text_input("拍摄地点", placeholder="请输入拍摄地点", key='location_input')
        
        # 字体字重选择
        st.subheader("🔤 文字样式")
        font_weight_options = {
            "细体 (Light)": "light",
            "常规 (Regular)": "regular", 
            "中等 (Medium)": "medium"
        }
        selected_font_weight_label = st.selectbox("字重", list(font_weight_options.keys()), index=1, key='font_weight_select')
        selected_font_weight = font_weight_options[selected_font_weight_label]
        
        # 输出格式选择
        output_format = st.selectbox("输出格式", ["JPEG", "PNG"], index=0, key='output_format')

    # 主内容区
    col1, col2 = st.columns(2)
    
    with col1:
        st.header("📤 上传图片")
        
        # 文件上传器
        uploaded_file = st.file_uploader(
            "请选择一张图片",
            type=["jpg", "jpeg", "png", "tiff", "bmp"],
            accept_multiple_files=False,
            key='file_uploader'
        )
        
        if uploaded_file is not None:
            # 显示原始图片
            st.image(uploaded_file, caption="原始图片", width='stretch')
            
            # 显示文件信息和EXIF
            # 保存临时文件以读取EXIF
            temp_exif_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp:
                    tmp.write(uploaded_file.getvalue())
                    temp_exif_path = tmp.name
                
                # 提取EXIF数据
                exif_data = exif_helper.extract_exif_data(temp_exif_path)
                
                # 保存EXIF数据到session state
                st.session_state.exif_data = exif_data
                
                # 显示EXIF信息
                if exif_data:
                    # 获取显示数据
                    display_data = exif_helper.get_display_data(exif_data)
                    
                    # 以更优雅的方式显示EXIF信息
                    with st.container():
                        # 设备信息部分 - 显示原始数据
                        st.markdown("#### 📷 设备信息")
                        device_cols = st.columns(3)
                        
                        with device_cols[0]:
                            if 'raw_camera_make' in display_data:
                                # 显示原始品牌数据
                                st.markdown(f"**品牌**: {display_data['raw_camera_make']}")

                        with device_cols[1]:
                            if 'raw_camera_model' in display_data:
                                # 显示原始型号数据
                                st.markdown(f"**型号**: {display_data['raw_camera_model']}")

                        with device_cols[2]:
                            if 'raw_lens_model' in display_data:
                                # 显示原始镜头数据
                                st.markdown(f"**镜头**: {display_data['raw_lens_model']}")
                            
                        # 拍摄参数部分
                        st.markdown("#### 📐 拍摄参数")
                        param_cols = st.columns(4)
                        
                        with param_cols[0]:
                            if 'raw_focal_length' in display_data:
                                st.markdown(f"**焦距**: {display_data['raw_focal_length']}mm")
                        
                        with param_cols[1]:
                            if 'raw_aperture' in display_data:
                                st.markdown(f"**光圈**: f/{display_data['raw_aperture']}")
                        
                        with param_cols[2]:
                            if 'raw_shutter_speed' in display_data:
                                st.markdown(f"**快门**: {display_data['raw_shutter_speed']}s")
                        
                        with param_cols[3]:
                            if 'raw_iso' in display_data:
                                st.markdown(f"**ISO**: {display_data['raw_iso']}")
                        
                        # 时间信息部分
                        if 'raw_datetime_original' in display_data:
                            st.markdown("#### 📅 拍摄时间")
                            st.markdown(f"**{display_data['raw_datetime_original']}**")
                        
                        # 显示格式化的EXIF信息（用于相框显示）
                        formatted_display = display_data.get('exif_formatted', '')
                        if formatted_display:
                            st.markdown("#### 💬 相框显示")
                            
                            # 显示组合后的相机型号（品牌+型号）
                            if 'camera_combined' in display_data:
                                st.markdown(f"**相机型号**: {display_data['camera_combined']}")
                            
                            # 显示映射后的镜头型号
                            if 'lens_model' in display_data:
                                st.markdown(f"**镜头型号**: {display_data['lens_model']}")
                            
                            # 显示格式化的曝光参数
                            st.markdown(f"**曝光参数**: {formatted_display}")
                else:
                    # 如果没有EXIF，至少显示基本文件信息
                    image = PILImage.open(io.BytesIO(uploaded_file.getvalue()))
                    width, height = image.size
                    st.info(f"📄 文件: {uploaded_file.name} | 尺寸: {width} x {height}px")
                    
            except Exception as e:
                st.warning(f"读取EXIF信息时出错: {str(e)}")
            finally:
                if temp_exif_path and os.path.exists(temp_exif_path):
                    os.unlink(temp_exif_path)
                    
        else:
            st.info("👆 请先上传一张图片")
    
    with col2:
        st.header("🖼️ 预览")
        
        if uploaded_file is not None:
            # 当前配置
            current_config = {
                'selected_style': selected_style,
                'selected_bg_fill': selected_bg_fill,
                'enable_border': enable_border,
                'border_width': border_width,
                'border_color': border_color,
                'enable_watermark': enable_watermark,
                'watermark_text': watermark_text,
                'watermark_position': watermark_position,
                'watermark_opacity': watermark_opacity,
                'selected_logo': selected_logo,
                'author': author,
                'location': location,
                'font_weight': selected_font_weight,
                'output_format': output_format
            }
            
            # 检查配置是否发生变化
            config_changed = (
                st.session_state.current_config != {} and
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
            button_style = f"<style>div.stButton > button:first-child {{ background-color: {'#ff6b6b' if config_changed and st.session_state.processing_result else '#80ed99'}; }}</style>"
            st.markdown(button_style, unsafe_allow_html=True)
            
            # 生成相框按钮
            if st.button(button_label, key='process_button'):
                st.session_state.button_clicked = True
                with st.spinner("正在处理图片..."):
                    try:
                        # 创建临时文件来保存上传的图片
                        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as temp_input:
                            temp_input.write(uploaded_file.getvalue())
                            temp_input_path = temp_input.name
                        
                        # 创建临时输出文件
                        output_ext = ".jpg" if output_format == "JPEG" else ".png"
                        with tempfile.NamedTemporaryFile(delete=False, suffix=output_ext) as temp_output:
                            temp_output_path = temp_output.name
                        
                        # 构建装饰元素列表
                        decorations = []
                        if enable_border:
                            decorations.append({
                                'type': 'border',
                                'params': {
                                    'width': border_width,
                                    'color': border_color
                                }
                            })
                        if enable_watermark and watermark_text:
                            decorations.append({
                                'type': 'watermark',
                                'params': {
                                    'text': watermark_text,
                                    'position': watermark_position,
                                    'opacity': watermark_opacity,
                                    'color': (255, 255, 255)  # 白色字体
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
                            logo_filename=selected_logo  # 传递logo参数
                        )
                        
                        if success:
                            # 保存处理结果到session state
                            st.session_state.temp_input_path = temp_input_path
                            st.session_state.temp_output_path = temp_output_path
                            st.session_state.processing_result = temp_output_path
                            
                            # 显示下载按钮
                            with open(temp_output_path, "rb") as result_file:
                                st.download_button(
                                    label="💾 下载处理后的图片",
                                    data=result_file,
                                    file_name=f"framed_{uploaded_file.name}",
                                    mime="image/jpeg" if output_format == "JPEG" else "image/png",
                                    key="download_processed_image_new"
                                )
                            
                            st.success("✅ 图片处理成功！")
                            st.image(temp_output_path, caption="添加相框后的图片", width='stretch')
                        else:
                            st.error("❌ 图片处理失败，请查看错误日志")
                    
                    except Exception as e:
                        st.error(f"❌ 处理过程中出现错误: {str(e)}")
                        import traceback
                        error_details = traceback.format_exc()
                        st.code(error_details)
                    
                    finally:
                        # 清理临时输入文件，保留输出文件供后续使用
                        if 'temp_input_path' in locals() and os.path.exists(temp_input_path):
                            os.unlink(temp_input_path)
            
            # 如果已经处理过且没有配置变更，显示之前的预览
            if (not st.session_state.button_clicked and
                st.session_state.processing_result and 
                not config_changed and 
                st.session_state.temp_output_path and 
                os.path.exists(st.session_state.temp_output_path)):
                
                with open(st.session_state.temp_output_path, "rb") as result_file:
                    st.download_button(
                        label="💾 下载处理后的图片",
                        data=result_file,
                        file_name=f"framed_{uploaded_file.name}",
                        mime="image/jpeg" if output_format == "JPEG" else "image/png",
                        key="download_processed_image_cached"
                    )
                
                st.success("✅ 图片处理成功！")
                st.image(st.session_state.temp_output_path, caption="添加相框后的图片", width='stretch')
            else:
                if not st.session_state.processing_result:
                    st.info("👆 请配置选项并点击“生成相框”按钮")
    
    # 底部信息
    st.markdown("---")
    st.caption("💡 提示：本程序支持设备映射，自动识别并显示相机型号等信息")
    st.caption("📋 版权所有 © 2026 MiLeica Frame 项目组")
    
    with st.expander("🛑 如何停止程序"):
        st.write("当您完成使用后，请在终端中按 `Ctrl+C` 来停止服务。")
        st.code("# 在运行程序的终端中按 Ctrl+C\n^C", language="text")


if __name__ == "__main__":
    run_app()