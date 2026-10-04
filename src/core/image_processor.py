# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
图像处理器模块
负责图像的基本处理、色彩空间转换、尺寸调整等
"""
import os
import io
import re
import copy
import logging
import tempfile
import time
from pathlib import Path
from typing import Tuple, Optional, Dict, List, Union

from PIL import Image, ImageOps, ImageCms, ImageDraw, ImageFont
# 设置PIL最大图像像素限制，解决解压炸弹警告
Image.MAX_IMAGE_PIXELS = 200000000  # 2亿像素，可根据需要调整

import piexif

from src.utils.exif_helper import ExifHelper
from src.utils.device_mapper import DeviceMapper
from src.utils.background_fill import BackgroundFillManager
from src.utils.output_metadata import (
    BRANDED_FORMATS,
    OutputMetadataError,
    prepare_output_metadata,
    read_output_software,
    verify_output_metadata,
)
from src.frame_styles.style_manager import StyleManager
from src.core.renderer import FrameRenderer, RenderMetadata, RenderOptions
from src.core.hdr_handler import HDRHandler

# piexif 以"文件路径"方式可解析的输入格式；其余容器（PNG/HEIC/AVIF 等）
# 必须改用已加载图像对象捕获的 EXIF 字节（见 process() 中的来源选择）
PIEXIF_PATH_FORMATS = ("JPEG", "TIFF", "MPO")


class ImageProcessor:
    """图像处理器"""
    
    def __init__(self, style_config: Optional[str] = None):
        """
        初始化图像处理器
        
        Args:
            style_config: 相框样式配置
        """
        self.style_config = style_config
        self.supported_formats = ['JPEG', 'PNG', 'TIFF', 'MPO']
        self.max_input_size = (12000, 12000)  # 最大输入尺寸
        self.max_output_size = (8192, 8192)   # 最大输出尺寸
        
        # 初始化组件
        self.exif_helper = ExifHelper()
        self.renderer = FrameRenderer()
        self.style_manager = StyleManager()
        self.device_mapper = DeviceMapper()
        self.hdr_handler = HDRHandler()
        
        self.logger = logging.getLogger(__name__)
    
    def process(self, input_path: str, output_path: str,
                style_name: Optional[str] = None,
                metadata: Optional[RenderMetadata] = None,
                options: Optional[RenderOptions] = None,
                font_weight: Optional[str] = None) -> bool:
        """
        处理图像并添加相框

        Args:
            input_path: 输入图像路径
            output_path: 输出图像路径
            style_name: 样式名称
            metadata: 渲染元数据（拍摄相关信息；exif_data 由本处理器从文件提取后覆盖）
            options: 渲染行为选项（背景/装饰/Logo 等）
            font_weight: 字体字重 (light, regular, medium)。
                保持平铺：它在函数内改写 style_config['fonts']['weight']，
                是样式改写而非渲染选项，不进 RenderOptions。

        Returns:
            是否处理成功
        """
        # 哨兵解包：避免可变默认值陷阱，也兼容 None 直传
        metadata = metadata or RenderMetadata()
        options = options or RenderOptions()
        try:
            # 1. 验证输入文件
            if not os.path.exists(input_path):
                error_msg = f"错误: 输入文件不存在 - {input_path}"
                self.logger.error(error_msg)
                print(error_msg)
                return False
            
            # 2. 检查图像格式支持
            img_format = self._check_image_format(input_path)
            if not img_format:
                error_msg = f"错误: 不支持的图像格式 - {input_path}"
                self.logger.error(error_msg)
                print(error_msg)
                return False
            
            # 3. 根据图像类型读取图像
            is_hdr = self.hdr_handler.detect_hdr_format(input_path)
            if is_hdr:
                image = self.hdr_handler.load_image(input_path)
                if image is None:
                    error_msg = f"错误: 无法加载HDR图像 - {input_path}"
                    self.logger.error(error_msg)
                    print(error_msg)
                    return False
            else:
                image = Image.open(input_path)

            # 3-pre. 捕获源图像元数据（必须早于方向转正、色彩转换与 HDR 转换：
            #        convert_hdr_to_sdr / _convert_colorspace 会生成丢失 info 的新对象）
            #        PNG/HEIC/AVIF 的原始 EXIF 字节与软件字段在此以不可变副本留下，
            #        不保留会随对象转换失效的 info 引用。
            source_exif_bytes, software_hint = self._capture_source_metadata(image)

            # 3a. 应用 EXIF Orientation 转置（竖拍照片方向修正）
            # 佳能等相机的竖拍照片以"横向像素数据 + EXIF Orientation(274) 旋转
            # 标记"存储，PIL 的 Image.open() 不解析该标记，直接渲染会得到横图。
            # 此处统一按 Orientation 标签将像素转正（HDR/HEIF/AVIF 路径同样覆盖）。
            image, orientation_transposed = self._apply_exif_orientation(image)

            # 4. 检查EXIF信息
            #    piexif 以"文件路径"方式只支持 JPEG/TIFF（含 MPO）；PNG/HEIC/AVIF
            #    等已知容器直接使用加载阶段捕获的 EXIF 字节作为来源，避免对已知
            #    不支持的容器反复调用路径解析并记录可预期的失败（方案 §1.1）。
            can_use_path = img_format in PIEXIF_PATH_FORMATS
            if can_use_path:
                exif_data = self.exif_helper.extract_exif_data(input_path)
            elif source_exif_bytes:
                exif_data = self.exif_helper.extract_exif_data(source_exif_bytes)
            else:
                # 该容器没有可解析的 EXIF 字节：跳过必然失败的路径解析
                exif_data = None
                self.logger.debug(
                    f"[output-metadata] 源容器无可解析 EXIF 字节，跳过路径解析: {input_path}"
                )
            if not exif_data:
                warn_msg = f"警告: 未找到EXIF信息 - {input_path}"
                self.logger.warning(warn_msg)
                print(warn_msg)

            # EXIF 由处理器从输入文件提取，覆盖 metadata 中可能存在的值
            # （与旧签名行为一致：调用方原本没有传入 EXIF 的途径）
            metadata.exif_data = exif_data

            # 4a. 原始 EXIF：JPEG/TIFF 沿用文件路径解析；PNG/HEIC/AVIF 直接用
            #     加载阶段捕获的源 EXIF 字节（保原软件名与拍摄字段）。
            if can_use_path:
                raw_exif = self.exif_helper.extract_raw_exif(input_path)
            else:
                raw_exif = None

            # 4b. 容器补读：文件路径解析失败（或不可用）时，改用源 EXIF 字节，
            #     使 PNG/HEIC/AVIF 的原软件名得以保留。
            if raw_exif is None and source_exif_bytes:
                raw_exif = self.exif_helper.extract_raw_exif_from_bytes(source_exif_bytes)
                if raw_exif is not None:
                    self.logger.debug("[output-metadata] 从已加载图像补读到源 EXIF 字节")

            # 3b. 像素转正后同步修正 raw_exif 中的 Orientation 标签
            # 输出文件嵌入的 raw_exif 从原文件提取；若像素已按旧标签旋转到位，
            # 必须把标签重置为 1（正常方向），否则查看器会按旧标签再旋转一次，
            # 造成"输出竖图仍带旋转标记"的二次旋转问题。
            if orientation_transposed and raw_exif:
                try:
                    # piexif 字典的 0th IFD 承载图像级标签，Orientation 固定在此
                    if "0th" not in raw_exif:
                        raw_exif["0th"] = {}
                    raw_exif["0th"][piexif.ImageIFD.Orientation] = 1

                    # EXIF 缩略图是转正前的旧方向，与重置后的 Orientation=1
                    # 冲突（查看器会显示方向错误的缩略图）；像素已转正，
                    # 直接丢弃旧缩略图，保持输出内部方向语义一致。
                    if raw_exif.get("thumbnail"):
                        raw_exif["thumbnail"] = None
                        self.logger.info(
                            "[output-metadata] 方向转正后丢弃旧方向的 EXIF 缩略图"
                        )
                except Exception as e:
                    self.logger.warning(f"重置输出 EXIF Orientation 标签失败: {e}")
            
            # 获取格式化的EXIF数据用于显示（如果需要传递给renderer或后续处理）
            # 注意：如果renderer仍然需要原始exif_data，我们保留它。
            # 如果renderer更新为使用格式化后的文本，可以在这里准备。
            # 目前保持兼容，但展示了新helper的使用。
            formatted_exif = self.exif_helper.get_formatted_exif_for_display(exif_data) if exif_data else {}
            
            # 5. 验证图像尺寸
            if not self._validate_image_size(image.size):
                warn_msg = f"警告: 图像尺寸超出限制 - {image.size}"
                self.logger.warning(warn_msg)
                print(warn_msg)
                # 缩放图像
                image = self._resize_image_proportionally(image)
            
            # 6. 处理色彩空间（ICC转换在色调映射之前，确保色域已校正至sRGB）
            image = self._convert_colorspace(image)
            sRGB_icc_bytes = image.info.get('icc_profile')

            # 6a. HDR色调映射（色彩空间已统一为sRGB后再压缩动态范围）
            if is_hdr:
                image = self.hdr_handler.convert_hdr_to_sdr(image)
            
            # 7. 获取样式配置（传入上下文以便文件夹样式自动选择变体）
            if style_name:
                context = self._build_style_context(metadata, exif_data)
                style_config = self.style_manager.get_style_config(style_name, context)
            else:
                style_config = self.style_manager.get_default_style()

            if not style_config:
                error_msg = f"错误: 无法获取样式配置 - {style_name or 'default'}"
                self.logger.error(error_msg)
                print(error_msg)
                return False

            # 8. 如果指定了字体字重，则更新样式配置
            if font_weight:
                style_config['fonts']['weight'] = font_weight

            # 9. 渲染图像（元数据与选项对象整体透传）
            rendered_image = self.renderer.render_frame(
                image=image,
                style_config=style_config,
                metadata=metadata,
                options=options,
            )
            
            # 10. 保存图像（software_hint 仅在 EXIF 软件值不可用时参与标识构建）
            self._save_image(rendered_image, output_path, img_format, raw_exif,
                             sRGB_icc_bytes, software_hint=software_hint)
            
            success_msg = f"成功处理图像: {input_path} -> {output_path}"
            self.logger.info(success_msg)
            print(success_msg)
            return True
            
        except Exception as e:
            error_msg = f"处理图像时出错: {str(e)}"
            self.logger.error(error_msg)
            print(error_msg)
            # 记录详细错误信息
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def _build_style_context(self, metadata: RenderMetadata,
                             exif_data: Optional[Dict]) -> Dict:
        """
        构建样式变体匹配用的上下文（纯函数，便于独立测试）

        上下文以"字段可用性"为语义：值为 None/'' 表示该字段无值，
        进入变体缺失字段集合，驱动 StyleManager._resolve_style_variant
        的 no_{field} 变体匹配。

        各字段可用性定义：
        - location / custom_text：用户输入可用性（沿用原行为）；
        - author：作者可用性；
        - timestamp：拍摄时间可用性——hide 模式或 EXIF 无拍摄时间为 None，
          通知变体系统拍摄时间不可用（匹配 no_timestamp 类变体）；
        - timestamp_author：组合字段可用性 = 拍摄时间或作者任一有值
          （与 RenderContext.get_text('timestamp_author') 的三段 fallback
          语义一致）。author 为空但时间有值（或时间不可用但作者有值）时
          该字段仍有值——组合字段 fallback 会自动降级为纯时间 / "Shot by
          作者"，行结构不变，沿用原布局；仅当时间与作者均无值时传 None，
          匹配 no_timestamp_author 类变体（时间+作者整行不渲染）。
        """
        context = {'location': metadata.location, 'author': metadata.author}
        if not metadata.custom_text:
            context['custom_text'] = None
        # 拍摄时间可用性：hide 模式或 EXIF 无拍摄时间时视为缺失
        ts_available = (
            metadata.timestamp_display_mode != 'hide'
            and bool(exif_data and exif_data.get('datetime_original'))
        )
        if not ts_available:
            context['timestamp'] = None
        # 组合字段可用性 = 时间或作者任一有值（fallback 归一设计的核心约定）
        if not (ts_available or metadata.author):
            context['timestamp_author'] = None
        return context

    def _capture_source_metadata(
            self, image: Image.Image
    ) -> Tuple[Optional[bytes], Optional[Union[str, bytes]]]:
        """
        在方向转正/色彩转换/HDR 转换之前捕获源图像的 EXIF 字节与软件字段

        必须在 `_apply_exif_orientation()` 之前调用：后续的
        `convert_hdr_to_sdr()`、`_convert_colorspace()` 都会生成不继承 info
        的新图像对象，届时原 EXIF 字节与文本字段将无法找回。

        Args:
            image: 加载器（Image.open / HDRHandler.load_image）返回的原始图像

        Returns:
            (source_exif_bytes, software_hint) 二元组；缺失项为 None。
            source_exif_bytes 是不可变字节副本，不持有 image.info 引用。
        """
        # 1. 原始 EXIF 字节：拷贝为不可变 bytes（PNG/HEIC/AVIF/JPEG 均为
        #    带 "Exif\\0\\0" 头的完整 EXIF，可直接交给 piexif.load）
        raw_bytes = image.info.get('exif')
        source_exif_bytes = (bytes(raw_bytes)
                             if isinstance(raw_bytes, (bytes, bytearray)) else None)

        # 2. 软件字段单值补充（仅当 EXIF Software 不可用时由构建阶段选用）
        hint = self.exif_helper.extract_software_hint(image)

        # 3. PNG 文本可能位于 IDAT 之后，未解码前 info 读不到；此时复用渲染
        #    本来就需要的那一次解码后再读取（load 幂等，不会额外解码第二遍，
        #    也不为此重新打开文件）。
        if hint is None and (image.format or '').upper() == 'PNG':
            try:
                image.load()
                hint = self.exif_helper.extract_software_hint(image)
            except Exception as e:
                self.logger.debug(f"[output-metadata] 源 PNG 补读文本 Software 失败: {e}")

        return source_exif_bytes, hint

    def _apply_exif_orientation(self, image: Image.Image) -> Tuple[Image.Image, bool]:
        """
        按 EXIF Orientation 标签转置图像像素（方向修正的唯一入口）

        佳能等相机的竖拍照片在文件中通常以"横向像素数据 + EXIF Orientation(274)
        旋转标记"存储，PIL 的 Image.open() 不解析该标记，直接渲染会得到横图。
        本方法使用 Pillow 的 ImageOps.exif_transpose() 将像素旋转到位：
        - 标签缺失或为 1 时图像内容保持不变（exif_transpose 为无操作）；
        - 标签为 2-8 时按标记旋转/翻转像素。

        Args:
            image: 原始打开的图像

        Returns:
            (转正后的图像, 是否发生了旋转/翻转) 二元组。
            "是否转置"依据原始 Orientation 标签值判断——实测 Pillow 对
            无标签图像也返回副本，不能以对象同一性判断。
        """
        try:
            # 读取原始 Orientation 标签（274 = 0x0112），2-8 表示需要旋转/翻转
            orientation = image.getexif().get(0x0112)
            # exif_transpose 无论是否发生转置都返回新 Image 对象，且新对象
            # 不继承 format 属性（PIL 的 _new() 不拷贝该字段），先记录原图
            # 格式并在转正后回填，避免下游 get_file_info 读取到 None
            img_format = image.format
            transposed = ImageOps.exif_transpose(image)
            transposed.format = img_format
            was_transposed = orientation not in (None, 1)
            if was_transposed:
                self.logger.info(
                    f"检测到 EXIF Orientation={orientation}，已将图像像素转正 "
                    f"({image.size} -> {transposed.size})"
                )
            return transposed, was_transposed
        except Exception as e:
            # 转置失败时回退为原始图像，不阻断主流程
            self.logger.warning(f"EXIF Orientation 转置失败，使用原始方向: {e}")
            return image, False

    def _check_image_format(self, image_path: str) -> Optional[str]:
        """
        检查图像格式是否支持
        
        Args:
            image_path: 图像路径
            
        Returns:
            图像格式，如果不支持则返回None
        """
        try:
            img_format = Image.open(image_path).format
            if img_format and (img_format in self.supported_formats or
                              self.hdr_handler.detect_hdr_format(image_path)):
                return img_format
            return None
        except Exception:
            return None
    
    def _validate_image_size(self, size: Tuple[int, int]) -> bool:
        """
        验证图像尺寸是否在支持范围内
        
        Args:
            size: 图像尺寸 (宽, 高)
            
        Returns:
            尺寸是否有效
        """
        width, height = size
        max_width, max_height = self.max_input_size
        return width <= max_width and height <= max_height
    
    def _resize_image_proportionally(self, image: Image.Image) -> Image.Image:
        """
        按比例缩放图像
        
        Args:
            image: 原始图像
            
        Returns:
            缩放后的图像
        """
        max_width, max_height = self.max_input_size
        width, height = image.size
        
        # 计算缩放比例
        scale_w = max_width / width
        scale_h = max_height / height
        scale = min(scale_w, scale_h)
        
        new_width = int(width * scale)
        new_height = int(height * scale)
        
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    def _convert_colorspace(self, image: Image.Image) -> Image.Image:
        """
        转换图像色彩空间到sRGB

        处理流程：
        1. ICC 色彩配置文件转换（Adobe RGB / ProPhoto RGB / Display P3 等 → sRGB）
        2. 像素模式转换（P/RGBA/LA/非RGB → RGB）

        Args:
            image: 原始图像

        Returns:
            转换后的 sRGB 图像
        """
        icc_profile = image.info.get('icc_profile')

        # 步骤1: ICC色彩空间转换（前置，在模式转换之前保留原始位深）
        if icc_profile:
            try:
                icc_stream = io.BytesIO(icc_profile)
                profile_desc = ImageCms.getProfileDescription(icc_stream)
                self.logger.info(f"检测到ICC色彩空间: {profile_desc}，转换为sRGB")
                icc_stream.seek(0)
                srgb_profile = ImageCms.createProfile('sRGB')
                image = ImageCms.profileToProfile(
                    image, icc_stream, srgb_profile,
                    outputMode='RGB',
                    renderingIntent=ImageCms.Intent.PERCEPTUAL
                )
                self.logger.info("ICC色彩空间转换成功")
            except Exception as e:
                self.logger.warning(f"ICC色彩空间转换失败，使用像素模式转换: {e}")

        # 步骤2: 像素模式转换（此时已在sRGB空间内）
        if image.mode in ('RGBA', 'LA', 'P'):
            if image.mode == 'P':
                image = image.convert('RGBA')
            if image.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'RGBA':
                    background.paste(image, mask=image.split()[-1])
                else:
                    background.paste(image, mask=image.split()[-1])
                image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')

        return image
    
    def _save_image(self, image: Image.Image, output_path: str,
                    original_format: str, raw_exif: Optional[Dict] = None,
                    icc_profile_bytes: Optional[bytes] = None,
                    *, software_hint=None) -> None:
        """
        保存图像（临时写入 → 读回验证 → 发布）

        JPEG/PNG 走品牌元数据事务：
          1. 内存中构建含 MiLecFrame 标识的元数据（分级降级：preserved/cleaned/minimal）；
          2. 在目标同目录创建唯一临时文件写入；
          3. 只读读回验证 Software 字段（PNG 还要验证文本字段）；
          4. 验证通过后 os.replace() 发布为最终输出，失败则清理临时文件并保留原输出。

        非 JPEG/PNG 的实际编码（标准入口不会产生）保留既有保存能力与旧元数据
        路径，并输出明确告警：该格式未启用品牌元数据保证。

        Args:
            image: 要保存的图像
            output_path: 输出路径
            original_format: 原始图像格式
            raw_exif: 原始EXIF字典（piexif格式），用于嵌入输出图；函数不修改该对象
            icc_profile_bytes: sRGB ICC profile字节，用于嵌入输出图
            software_hint: 仅关键字参数；源图像软件字段补充值，
                仅当 EXIF Software 不可用时参与标识构建

        Raises:
            OutputMetadataError: 元数据构建或读回验证失败
            OSError/ValueError 等: 临时写入或最终替换失败
        """
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # 1. 按实际输出后缀决定编码（沿用现有显式输出路径规则）
        output_ext = os.path.splitext(output_path)[1].lower()
        if output_ext in ('.jpg', '.jpeg'):
            save_format = 'JPEG'
            save_kwargs = {'quality': 95, 'optimize': True}
        elif output_ext == '.png':
            save_format = 'PNG'
            save_kwargs = {'optimize': True}
        else:
            save_format = original_format
            save_kwargs = {}

        # 嵌入 sRGB ICC profile（ICC 独立于 EXIF 管理，不随 EXIF 降级被删除）
        if icc_profile_bytes:
            save_kwargs['icc_profile'] = icc_profile_bytes

        # 2. 非 JPEG/PNG 的实际编码：明确告警 + 既有兼容路径（不套用本方案的
        #    构建/验证器，也不宣称通过品牌验收；见方案 §5.4）
        if save_format.upper() not in BRANDED_FORMATS:
            self.logger.warning(
                f"[output-metadata] 输出格式 {save_format} 未启用品牌元数据保证"
                f"（保证范围为 JPEG/PNG），走既有兼容路径"
            )
            self._save_legacy(image, output_path, save_format, raw_exif, save_kwargs)
            return

        timings: Dict[str, float] = {}
        try:
            # 3. 内存中构建元数据（深拷贝入参、清理、容量检查、最小兜底）
            stage_start = time.perf_counter()
            prepared = prepare_output_metadata(raw_exif, save_format, software_hint)
            timings['prepare'] = (time.perf_counter() - stage_start) * 1000.0

            save_kwargs['exif'] = prepared.exif_bytes
            if prepared.pnginfo is not None:
                # PNG 文本只包含本功能需要的 Software 字段，不复制源图其他文本
                save_kwargs['pnginfo'] = prepared.pnginfo

            # 4. 同目录唯一临时文件：写入 → 只读验证 → 发布
            tmp_path: Optional[str] = None
            try:
                # Windows 下必须先关闭 mkstemp 句柄，再交给 Pillow 写入，
                # 否则同一文件会被占用导致写入失败
                fd, tmp_path = tempfile.mkstemp(
                    prefix='.mlecframe_', suffix=output_ext or '.tmp',
                    dir=output_dir or '.'
                )
                os.close(fd)

                stage_start = time.perf_counter()
                image.save(tmp_path, format=save_format, **save_kwargs)
                timings['save'] = (time.perf_counter() - stage_start) * 1000.0

                # 读回验证（只读、严格比较；禁止在验证阶段重新推导软件值）
                stage_start = time.perf_counter()
                verify_output_metadata(tmp_path, save_format, prepared.software_text)
                timings['verify'] = (time.perf_counter() - stage_start) * 1000.0

                # 验证通过才替换最终输出；替换失败不删除既有输出
                stage_start = time.perf_counter()
                os.replace(tmp_path, output_path)
                tmp_path = None
                timings['publish'] = (time.perf_counter() - stage_start) * 1000.0
            finally:
                # 无论哪一步失败，只清理本次创建的临时文件
                if tmp_path is not None and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except OSError as cleanup_error:
                        # 清理失败单独告警，不掩盖原始异常
                        self.logger.warning(
                            f"[output-metadata] 临时文件清理失败 {tmp_path}: {cleanup_error}"
                        )

            # 5. 记录结果：只写格式、级别、原因码、移除标签 ID 与阶段耗时，
            #    不输出整份 EXIF 或照片隐私数据
            self.logger.info(
                "[output-metadata] format=%s level=%s reasons=%s removed=%s "
                "build=%.1fms prepare=%.1fms save=%.1fms verify=%.1fms publish=%.1fms",
                save_format, prepared.level,
                ",".join(prepared.reasons) or "-",
                ",".join(prepared.removed_tags) or "-",
                prepared.build_ms,
                timings.get('prepare', 0.0), timings.get('save', 0.0),
                timings.get('verify', 0.0), timings.get('publish', 0.0),
            )
            if prepared.level == 'minimal':
                self.logger.warning(
                    "[output-metadata] 原 EXIF 无法完整序列化，已降级为最小标识 "
                    f"(format={save_format}, reasons={','.join(prepared.reasons)})"
                )
        except OutputMetadataError as e:
            self.logger.error(f"[output-metadata] 标识写入/验证失败: {e}")
            raise
        except Exception as e:
            error_msg = f"保存图像时出错: {str(e)}"
            self.logger.error(error_msg)
            raise

    def _save_legacy(self, image: Image.Image, output_path: str,
                     save_format: str, raw_exif: Optional[Dict],
                     save_kwargs: Dict) -> None:
        """
        非 JPEG/PNG 实际编码的既有保存路径（不提供品牌标识保证）

        保留旧有元数据行为：有原始 EXIF 才尝试嵌入，失败或过大则跳过。
        与品牌路径的差异：本方法不写标识、不做事后读回验证。
        操作 EXIF 时使用副本，避免修改调用方传入的对象（M17）。

        Args:
            image: 要保存的图像
            output_path: 输出路径
            save_format: 实际编码格式
            raw_exif: 原始EXIF字典（只读）
            save_kwargs: 已确定的保存参数（会被就地补充 exif）

        Raises:
            保存失败时上抛原始异常
        """
        try:
            if raw_exif:
                try:
                    # 使用副本：不在调用方对象上删除标签
                    exif_copy = copy.deepcopy(raw_exif)

                    # 移除 MakerNote（厂商私有数据段，易导致 EXIF 总大小超出限制）
                    if "Exif" in exif_copy and piexif.ExifIFD.MakerNote in exif_copy["Exif"]:
                        del exif_copy["Exif"][piexif.ExifIFD.MakerNote]

                    # 容错式序列化：遇到类型不兼容的标签自动丢弃并重试
                    def _try_dump_exif(exif_dict):
                        """尝试序列化EXIF，丢弃无法写入的标签后重试。"""
                        removed = []
                        while True:
                            try:
                                result = piexif.dump(exif_dict)
                                if removed:
                                    self.logger.info(
                                        f"已移除 {len(removed)} 个不兼容的EXIF标签: {removed}"
                                    )
                                return result
                            except (ValueError, TypeError) as e:
                                msg = str(e)
                                # 从异常消息中解析问题标签，格式:
                                #   "dump" got wrong type of exif value.
                                #   41729 in Exif IFD. Got as <class 'int'>.
                                match = re.search(r'(\d+) in (\w+) IFD', msg)
                                if not match:
                                    raise
                                tag_id = int(match.group(1))
                                ifd_name = match.group(2)
                                if (exif_dict.get(ifd_name) and
                                        tag_id in exif_dict[ifd_name]):
                                    del exif_dict[ifd_name][tag_id]
                                    removed.append(f"{ifd_name}.{tag_id}")
                                else:
                                    raise

                    exif_bytes = _try_dump_exif(exif_copy)
                    if len(exif_bytes) > 65533:
                        self.logger.warning(
                            f"EXIF 数据过大 ({len(exif_bytes)} 字节)，超出 JPEG 限制，已跳过 EXIF 嵌入"
                        )
                    else:
                        save_kwargs['exif'] = exif_bytes
                except Exception as e:
                    self.logger.warning(f"嵌入EXIF信息失败: {e}")

            image.save(output_path, format=save_format, **save_kwargs)
        except Exception as e:
            error_msg = f"保存图像时出错: {str(e)}"
            self.logger.error(error_msg)
            raise e