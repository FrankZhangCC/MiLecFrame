"""
GUI应用程序模块
使用Streamlit构建网页版GUI界面
"""
import streamlit as st
import os
import sys
import tempfile
from pathlib import Path

# 添加项目根目录到sys.path（在任何导入之前）
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

def run_app():
    """运行GUI应用程序"""
    try:
        # 导入模块
        from core.image_processor import ImageProcessor
        from frame_styles.style_manager import default_style_manager
        from utils.config_manager import default_config_manager
    except ImportError as e:
        st.error(f"❌ 导入错误: {str(e)}")
        st.error("程序因导入错误而终止，请检查安装和导入路径")
        raise e
    
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
        available_styles = default_style_manager.get_available_styles()
        if not available_styles:
            # 如果没有样式，创建示例样式
            default_style_manager.create_sample_styles()
            available_styles = default_style_manager.get_available_styles()
        
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
        
        # 作者输入
        # 尝试从配置中获取保存的作者名
        saved_author = default_config_manager.get_saved_author()
        default_author = saved_author if saved_author else ""
        author = st.text_input("作者姓名", value=default_author, placeholder="请输入作者姓名", key='author_input')
        
        # 保存作者名到配置
        if author:
            default_config_manager.save_user_author(author)
        
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
            
            # 显示文件信息
            import io
            from PIL import Image as PILImage
            try:
                import piexif
            except ImportError:
                piexif = None
            
            # 打开图片获取尺寸和EXIF信息
            image = PILImage.open(io.BytesIO(uploaded_file.getvalue()))
            width, height = image.size
            
            # 尝试获取EXIF信息
            exif_data = {}
            exif_dict = {}
            try:
                exif_bytes = image.info.get("exif")
                if exif_bytes and piexif:
                    exif_dict = piexif.load(exif_bytes)
                    # 提取常用EXIF信息
                    if "0th" in exif_dict:
                        exif_0th = exif_dict["0th"]
                        if piexif.ImageIFD.Make in exif_0th:
                            try: exif_data["制造商"] = exif_0th[piexif.ImageIFD.Make].decode()
                            except: pass
                        if piexif.ImageIFD.Model in exif_0th:
                            try: exif_data["型号"] = exif_0th[piexif.ImageIFD.Model].decode()
                            except: pass
                        if piexif.ImageIFD.DateTime in exif_0th:
                            try: exif_data["拍摄时间"] = exif_0th[piexif.ImageIFD.DateTime].decode()
                            except: pass
                    if "Exif" in exif_dict:
                        exif_exif = exif_dict["Exif"]
                        if piexif.ExifIFD.LensModel in exif_exif:
                            try: exif_data["镜头"] = exif_exif[piexif.ExifIFD.LensModel].decode()
                            except: pass
                        if piexif.ExifIFD.ExposureTime in exif_exif:
                            exposure_time = exif_exif[piexif.ExifIFD.ExposureTime]
                            if isinstance(exposure_time, tuple):
                                try:
                                    num, den = exposure_time
                                    if den != 0:
                                        val = num / den
                                        if val < 1:
                                            exif_data["曝光时间"] = f"1/{int(1/val)}s"
                                        else:
                                            exif_data["曝光时间"] = f"{val:.1f}s"
                                except: exif_data["曝光时间"] = str(exposure_time)
                            else:
                                exif_data["曝光时间"] = str(exposure_time)
                        if piexif.ExifIFD.FNumber in exif_exif:
                            fnumber = exif_exif[piexif.ExifIFD.FNumber]
                            if isinstance(fnumber, tuple):
                                try: exif_data["光圈"] = f"f/{fnumber[0]/fnumber[1]:.1f}"
                                except: pass
                            else:
                                # FNumber is usually a rational number stored as (num, den) but sometimes just float/int depending on loader
                                # piexif usually returns tuple for rationals. If it's a raw value, it might need adjustment.
                                # Standard EXIF FNumber is rational.
                                if isinstance(fnumber, (int, float)):
                                     exif_data["光圈"] = f"f/{fnumber:.1f}"
                                else:
                                     try: exif_data["光圈"] = f"f/{fnumber/100:.1f}" if fnumber > 100 else f"f/{fnumber:.1f}"
                                     except: pass
                        if piexif.ExifIFD.ISOSpeedRatings in exif_exif:
                            exif_data["ISO"] = exif_exif[piexif.ExifIFD.ISOSpeedRatings]
                        if piexif.ExifIFD.FocalLengthIn35mmFilm in exif_exif:
                            focal_length_35mm = exif_exif[piexif.ExifIFD.FocalLengthIn35mmFilm]
                            if isinstance(focal_length_35mm, tuple):
                                try: exif_data["等效35mm焦距"] = f"{focal_length_35mm[0]/focal_length_35mm[1]}mm"
                                except: pass
                            else:
                                exif_data["等效35mm焦距"] = f"{focal_length_35mm}mm"
            except Exception as e:
                # 如果无法解析EXIF信息，不显示错误，只是不显示EXIF数据
                pass
            
            # 检测HDR特性
            hdr_info = {}
            try:
                # 检查是否为HEIF/AVIF格式，这些格式可能包含HDR信息
                file_extension = uploaded_file.name.lower()
                if file_extension in ['.heic', '.avif', '.heif']:
                    # 检查是否有HDR gain map信息
                    try:
                        import pillow_heif
                        # 检查是否有HDR gain map信息
                        if hasattr(image, '_getexif') and image._getexif():
                            exif_tags = image._getexif()
                            if 50839 in exif_tags:  # GainMap标签
                                hdr_info["HDR格式"] = "Gain Map HDR (HEIF/AVIF)"
                            else:
                                hdr_info["HDR格式"] = "HEIF/AVIF格式"
                        else:
                            hdr_info["HDR格式"] = "HEIF/AVIF格式"
                    except ImportError:
                        hdr_info["HDR格式"] = "HEIF/AVIF格式"
                # 检查普通图像格式中的HDR信息
                else:
                    # 对于JPEG等格式，检查EXIF中是否有关于HDR的信息
                    if exif_bytes:
                        # 检查图像是否为多帧合成的HDR照片
                        if "0th" in exif_dict:
                            exif_0th = exif_dict["0th"]
                            if piexif.ImageIFD.SceneCaptureType in exif_0th:
                                capture_type = exif_0th[piexif.ImageIFD.SceneCaptureType]
                                if capture_type == 1:  # 风景模式，有时用于HDR
                                    hdr_info["HDR格式"] = "可能为合成HDR"
            except Exception as e:
                # 忽略HDR检测错误
                pass
            
            file_details = {
                "文件名": uploaded_file.name,
                "文件类型": uploaded_file.type,
                "文件大小": f"{len(uploaded_file.getvalue()) / (1024 * 1024):.2f} MB",
                "图片尺寸": f"{width} × {height}px"
            }
            
            # 合并EXIF信息到详情中
            file_details.update(exif_data)
            # 合并HDR信息到详情中
            file_details.update(hdr_info)
            
            st.json(file_details)
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
                        processor = ImageProcessor()  # 修正初始化参数
                        
                        success = processor.process(
                            input_path=temp_input_path,
                            output_path=temp_output_path,
                            author=author if author else None,
                            location=location if location else None,
                            style_name=selected_style,
                            bg_fill_type=selected_bg_fill,
                            decorations=decorations if decorations else None,
                            font_weight=selected_font_weight
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
                                    key="download_processed_image_new"  # 添加唯一key
                                )
                            
                            st.success("✅ 图片处理成功！")
                            st.image(temp_output_path, caption="添加相框后的图片", width='stretch')
                        else:
                            st.error("❌ 图片处理失败，请查看错误日志")
                    
                    except Exception as e:
                        st.error(f"❌ 处理过程中出现错误: {str(e)}")
                        # 记录错误到日志
                        import traceback
                        error_details = traceback.format_exc()
                        st.code(error_details)
                    
                    finally:
                        # 清理临时输入文件，保留输出文件供后续使用
                        if 'temp_input_path' in locals() and os.path.exists(temp_input_path):
                            os.unlink(temp_input_path)
            
            # 如果已经处理过且没有配置变更，显示之前的预览
            # 这里要确保不会和上面的实时结果显示同时出现
            if (not st.session_state.button_clicked and  # 没有正在进行处理
                st.session_state.processing_result and 
                not config_changed and 
                st.session_state.temp_output_path and 
                os.path.exists(st.session_state.temp_output_path)):
                
                # 显示下载按钮
                with open(st.session_state.temp_output_path, "rb") as result_file:
                    st.download_button(
                        label="💾 下载处理后的图片",
                        data=result_file,
                        file_name=f"framed_{uploaded_file.name}",
                        mime="image/jpeg" if output_format == "JPEG" else "image/png",
                        key="download_processed_image_cached"  # 添加唯一key
                    )
                
                st.success("✅ 图片处理成功！")
                st.image(st.session_state.temp_output_path, caption="添加相框后的图片", width='stretch')
            else:
                # 只有在没有处理结果时才显示提示信息
                # 由于此代码块在 uploaded_file is not None 内部，所以用户已上传图片
                if not st.session_state.processing_result:
                    st.info("👆 请配置选项并点击“生成相框”按钮")
    
    # 底部信息
    st.markdown("---")
    st.caption("💡 提示：本程序会自动提取并显示照片的EXIF信息，如相机型号、焦距、光圈等")
    st.caption("📋 版权所有 © 2026 MiLeica Frame 项目组")
    
    # 添加停止程序的说明
    with st.expander("🛑 如何停止程序"):
        st.write("当您完成使用后，请在终端中按 `Ctrl+C` 来停止服务。")
        st.code("# 在运行程序的终端中按 Ctrl+C\n^C", language="text")


if __name__ == "__main__":
    run_app()