# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
批量处理器模块（重写版）
负责批量处理图像，添加相框和EXIF信息
支持进度回调、逐张独立Logo匹配、GPS替换等完整功能
"""
import os
import logging
from pathlib import Path
from typing import Optional, List, Dict, Callable
from dataclasses import dataclass, field

from src.utils.exif_helper import ExifHelper
from src.utils.background_fill import BackgroundFillManager
from src.utils.logo_selector import LogoSelector
from src.core.image_processor import ImageProcessor

logger = logging.getLogger(__name__)

# 支持的图像扩展名
_SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.webp'}


@dataclass
class BatchResult:
    """
    批量处理结果

    Attributes:
        total: 总文件数
        success_count: 成功处理的文件数
        fail_count: 处理失败的文件数
        skip_count: 跳过的文件数（输出已存在）
        failed_files: 失败文件列表，每项为 (文件路径, 错误信息)
    """
    total: int = 0
    success_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    failed_files: List[tuple] = field(default_factory=list)


class BatchProcessor:
    """
    批量处理器（重写版）

    职责：
    - 接收文件路径列表，逐张调用 ImageProcessor.process() 处理
    - 每张图片独立进行 Logo 自动匹配（读取 EXIF → 提取品牌 → 匹配 Logo）
    - 每张图片独立进行 GPS 替换（读取 EXIF → 提取 GPS 坐标 → 覆盖地点）
    - 通过 progress_callback 提供实时进度反馈
    - 单张失败不影响整批，结果汇总到 BatchResult
    """

    def __init__(self):
        """初始化批量处理器"""
        self.exif_helper = ExifHelper()
        self.logo_selector = LogoSelector()

    @staticmethod
    def discover_files(
        folder_path: str,
        recursive: bool = False
    ) -> List[Path]:
        """
        发现文件夹中的图片文件（供 CLI/GUI 共用）

        Args:
            folder_path: 文件夹路径
            recursive: 是否递归扫描子目录

        Returns:
            图片文件 Path 列表（已排序）
        """
        folder = Path(folder_path)
        if not folder.is_dir():
            logger.warning(f"文件夹不存在: {folder_path}")
            return []

        if recursive:
            files = [f for f in folder.rglob("*") if f.suffix.lower() in _SUPPORTED_EXTENSIONS]
        else:
            files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in _SUPPORTED_EXTENSIONS]

        return sorted(files, key=lambda f: f.name)

    def batch_process(
        self,
        input_files: List[str],
        output_folder: str,
        author: Optional[str] = None,
        location: Optional[str] = None,
        style_name: Optional[str] = None,
        bg_fill_type: Optional[str] = None,
        output_format: str = "JPEG",
        decorations: Optional[List[Dict]] = None,
        font_weight: str = 'medium',
        logo_selection: str = 'auto',
        lens_display_mode: str = 'combined',
        use_short_lens: bool = False,
        saturation_override: Optional[float] = None,
        use_gps_location: bool = False,
        progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
        skip_existing: bool = True,
        custom_text: Optional[str] = None,
        timestamp_display_mode: str = 'full',
    ) -> BatchResult:
        """
        批量处理图像

        Args:
            input_files: 输入文件路径列表（绝对或相对路径）
            output_folder: 输出文件夹路径（不存在则自动创建）
            author: 作者名
            location: 拍摄地点（手动输入，可被 GPS 数据覆盖）
            style_name: 相框样式名称
            bg_fill_type: 背景填充类型，默认 BackgroundFillManager.DEFAULT_FILL
            output_format: 输出格式 ("JPEG" 或 "PNG")
            decorations: 装饰元素列表，每项 {'type': 'watermark', 'params': {...}}
            font_weight: 字体字重 ('light' / 'regular' / 'medium')
            logo_selection: Logo 选择策略
                - 'auto' → 逐张自动匹配 (读取 EXIF 品牌 → LogoSelector.auto_match_logo)
                - 'none' → 所有图片不使用 Logo
                - '<filename>' → 所有图片统一使用指定 Logo 文件
            lens_display_mode: 镜头显示模式 ('combined' / 'camera_only' / 'lens_only')
            use_short_lens: 是否使用短版镜头名
            saturation_override: 饱和度覆盖 (None=默认, 1.0=不做增强)
            use_gps_location: 是否使用 GPS 数据替换手动输入的地点
            progress_callback: 进度回调函数
                签名: callback(processed_count: int, total_count: int, filename: str, status_msg: str)
            skip_existing: 是否跳过已存在的输出文件
            custom_text: 自定义文本内容（仅当样式配置 custom_text.enabled=True 时生效）
            timestamp_display_mode: 拍摄时间显示模式（'full'=日期与时刻, 'date_only'=仅日期, 'hide'=不显示）

        Returns:
            BatchResult: 包含成功/失败/跳过计数及失败详情的结果对象
        """
        # 默认背景填充类型
        if bg_fill_type is None:
            bg_fill_type = BackgroundFillManager.DEFAULT_FILL

        result = BatchResult(total=len(input_files))

        # 确保输出目录存在
        os.makedirs(output_folder, exist_ok=True)

        # 确定输出文件扩展名
        output_ext = ".jpg" if output_format.upper() == "JPEG" else ".png"

        # 创建可复用的 ImageProcessor
        processor = ImageProcessor()

        for i, input_path_str in enumerate(input_files):
            input_path = Path(input_path_str)
            current_index = i + 1

            # ===== 构造输出路径 =====
            output_filename = f"{input_path.stem}_framed{output_ext}"
            output_path = Path(output_folder) / output_filename

            # ===== 跳过已存在的输出文件 =====
            if skip_existing and output_path.exists():
                result.skip_count += 1
                if progress_callback:
                    progress_callback(current_index, result.total, input_path.name, "⏭ 跳过（输出文件已存在）")
                continue

            # ===== 逐张决定 location（GPS 替换）和 logo_filename（自动匹配）=====
            current_location = location
            current_logo: Optional[str] = None

            # 是否需要读取 EXIF（GPS 替换或 Logo 自动匹配时）
            need_exif = use_gps_location or logo_selection == 'auto'
            exif_data = None

            if need_exif:
                try:
                    exif_data = self.exif_helper.extract_exif_data(str(input_path))
                except Exception as e:
                    logger.debug(f"提取 EXIF 数据失败 [{input_path.name}]: {e}")

            # ---- GPS 替换逻辑 ----
            if use_gps_location and exif_data:
                gps_value = exif_data.get('gps', '')
                if gps_value:
                    current_location = gps_value

            # ---- Logo 选择逻辑 ----
            if logo_selection == 'auto':
                # 逐张自动匹配：读取 EXIF 品牌 → LogoSelector.auto_match_logo
                if exif_data:
                    camera_brand = ExifHelper.get_camera_brand(exif_data)
                    if camera_brand:
                        current_logo = self.logo_selector.auto_match_logo(
                            camera_brand,
                            is_dark_bg=BackgroundFillManager.is_dark_bg(bg_fill_type)
                        )
                    # 如果品牌为空或匹配失败，current_logo 保持 None（使用样式默认）
            elif logo_selection == 'none':
                current_logo = ""  # 空字符串表示不使用 Logo
            else:
                # 手动指定：所有图片统一使用
                current_logo = logo_selection

            # ===== 调用 ImageProcessor 处理 =====
            try:
                success = processor.process(
                    input_path=str(input_path),
                    output_path=str(output_path),
                    author=author,
                    location=current_location,
                    style_name=style_name,
                    bg_fill_type=bg_fill_type,
                    decorations=decorations,
                    font_weight=font_weight,
                    logo_filename=current_logo,
                    lens_display_mode=lens_display_mode,
                    use_short_lens=use_short_lens,
                    saturation_override=saturation_override,
                    custom_text=custom_text,
                    timestamp_display_mode=timestamp_display_mode,
                )

                if success:
                    result.success_count += 1
                    if progress_callback:
                        progress_callback(
                            current_index, result.total,
                            input_path.name,
                            f"✅ 处理成功 → {output_filename}"
                        )
                else:
                    result.fail_count += 1
                    result.failed_files.append((str(input_path), "ImageProcessor 返回失败"))
                    if progress_callback:
                        progress_callback(
                            current_index, result.total,
                            input_path.name,
                            "❌ 处理失败（ImageProcessor 返回 False）"
                        )

            except Exception as e:
                result.fail_count += 1
                error_msg = f"{type(e).__name__}: {str(e)}"
                result.failed_files.append((str(input_path), error_msg))
                logger.error(f"处理失败 [{input_path.name}]: {error_msg}")
                if progress_callback:
                    progress_callback(
                        current_index, result.total,
                        input_path.name,
                        f"❌ 异常: {error_msg}"
                    )

        return result
