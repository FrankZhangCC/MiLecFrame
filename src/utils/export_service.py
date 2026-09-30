# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
导出服务（G2 页面拆分：导出流程自 ImageProcessingPage 收敛于此）

搬运自 image_processing_page 的 _file_sha256 / _export_verified
（G13 修复后版本）：期望格式取源文件实际编码、目标扩展名契约校验、
哈希一致性 + 生产只读验证器双重校验，通过后才发布目标文件。
"""
import hashlib
import logging
import os
import shutil
from pathlib import Path

from src.utils.output_metadata import (
    read_output_branding, verify_output_metadata, OutputMetadataError,
)

logger = logging.getLogger(__name__)

# 导出目标扩展名 → 实际编码映射（G13 扩展名契约：导出是"已验证结果的
# 字节副本"，不做转码，目标后缀必须与源实际编码一致，否则拒绝发布）
_EXPORT_SUFFIX_FORMATS = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG'}


def file_sha256(path: str) -> str:
    """计算文件 SHA-256（用于导出副本与源结果的一致性校验）"""
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def export_verified(src_path: str, dst_path: str) -> None:
    """
    导出结果文件并验证：先复制到同目录临时文件，校验通过才发布到目标

    校验两项（方案 §6.4）：
      1. 副本与源结果的 SHA-256 完全一致（证明复制完整、未经二次编码）；
      2. 用生产只读验证器读回标识（Software 字段必须有效且与源一致）。

    期望编码取源文件实际编码而非路径后缀（G13 修复：'.part' 临时
    后缀曾被当作格式判断依据，导致 PNG 导出必然验证失败）；目标
    扩展名与源实际编码不一致时拒绝导出（导出不转码，不发布内容与
    扩展名不符的文件——转码会破坏哈希一致性校验的前提）。

    校验失败时只清理本次临时副本，不动目标位置可能已存在的旧文件。
    本服务只调用验证器，不自行拼接或修复任何元数据字段。

    Args:
        src_path: 已成功生成的结果文件
        dst_path: 用户选择的导出目标路径

    Raises:
        OutputMetadataError/OSError: 扩展名契约不符、复制或校验失败
    """
    tmp_path = dst_path + '.part'
    try:
        # G13 扩展名契约：先于任何 I/O 校验目标后缀与源编码一致
        suffix = Path(dst_path).suffix.lower()
        suffix_format = _EXPORT_SUFFIX_FORMATS.get(suffix)
        if suffix_format is None:
            raise OutputMetadataError(
                f"不支持的导出扩展名 {suffix!r}（仅支持 .jpg/.jpeg/.png）")

        shutil.copy2(src_path, tmp_path)

        # 1) 哈希一致：排除复制不完整或被二次编码
        if file_sha256(src_path) != file_sha256(tmp_path):
            raise OutputMetadataError("导出副本与源结果哈希不一致")

        # 2) 读回标识：源文件的软件值与实际编码作为期望值，验证副本一致
        #    （副本是源的字节拷贝，期望编码取源文件实际编码）
        expected, source_format = read_output_branding(src_path)
        if suffix_format != source_format:
            raise OutputMetadataError(
                f"目标扩展名 {suffix!r} 与源图像格式 {source_format} 不符；"
                f"导出不转码，请选择与源格式一致的扩展名")
        verify_output_metadata(tmp_path, source_format, expected)

        # 验证通过才替换目标输出
        os.replace(tmp_path, dst_path)
        tmp_path = None
    finally:
        if tmp_path is not None and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError as e:
                logger.warning(f"[output-metadata] 导出临时文件清理失败 {tmp_path}: {e}")
