# Copyright (c) 2026 FrankZhangCC
# MIT License - see LICENSE file for details

"""
HDR图像处理模块
负责HEIF/AVIF格式的HDR图像加载与SDR色调映射
"""
import os
from PIL import Image
import numpy as np
import logging

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_SUPPORT = True
except ImportError:
    HEIF_SUPPORT = False


class HDRHandler:
    """HDR图像处理器 - HEIF/AVIF加载与Reinhard色调映射"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def detect_hdr_format(self, image_path: str) -> bool:
        """检测图像是否为HDR格式（HEIF/HEIC/AVIF）"""
        ext = os.path.splitext(image_path)[1].lower()
        if ext in ('.heif', '.heic', '.avif'):
            return True
        try:
            img = Image.open(image_path)
            return img.format in ('HEIF', 'HEIC', 'AVIF')
        except Exception:
            return False

    def load_image(self, image_path: str) -> Image.Image:
        """加载图像。HEIF/AVIF通过pillow-heif加载并保留ICC profile"""
        if not self.detect_hdr_format(image_path):
            return Image.open(image_path)

        if not HEIF_SUPPORT:
            self.logger.warning("pillow-heif未安装，回退到PIL加载HEIF/AVIF")
            return Image.open(image_path)

        try:
            heif_file = pillow_heif.open_heif(image_path)
            return heif_file.to_pillow()
        except Exception as e:
            self.logger.error(f"pillow-heif加载失败，尝试PIL回退: {e}")
            return Image.open(image_path)

    def convert_hdr_to_sdr(self, image: Image.Image) -> Image.Image:
        """
        使用Reinhard全局色调映射将HDR图像转换为SDR。

        该算法在对数平均亮度的基础上压缩动态范围，
        保留中调区域的同时平滑压缩高光。
        """
        if image.mode != 'RGB':
            image = image.convert('RGB')

        arr = np.array(image, dtype=np.float32) / 255.0

        L = 0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]

        L_avg = np.exp(np.mean(np.log(L + 1e-6)))

        L_scaled = L / L_avg

        L_mapped = L_scaled / (1.0 + L_scaled)

        scale = np.divide(L_mapped, L, out=np.ones_like(L), where=L > 1e-6)
        scale_3ch = np.stack([scale] * 3, axis=-1)

        result = arr * scale_3ch
        result = np.clip(result, 0.0, 1.0)
        result = (result * 255).astype(np.uint8)

        return Image.fromarray(result, 'RGB')
