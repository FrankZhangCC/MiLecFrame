"""
高斯模糊工具模块
"""
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np

COLOR_OPTIONS = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
}

_BLUR_WORK_MAX = 1200
_BLUR_WORK_MIN = 512
_BOX_BLUR_PASSES = 3


def _box_blur(image: Image.Image, radius: float) -> Image.Image:
    for _ in range(_BOX_BLUR_PASSES):
        image = image.filter(ImageFilter.BoxBlur(radius))
    return image


def _compute_scale_factor(image_long_edge: int) -> float:
    if image_long_edge <= _BLUR_WORK_MAX:
        return 1.0
    return _BLUR_WORK_MAX / image_long_edge


def _enhance_saturation(image: Image.Image, factor: float) -> Image.Image:
    """
    增强图像饱和度（用于补偿高斯模糊叠加覆盖层后的颜色淡化）
    
    Args:
        image: RGB 模式的图像
        factor: 饱和度增强系数（1.0 = 不变，>1.0 = 增强）
        
    Returns:
        增强后的图像（factor ≤ 1.0 时原样返回）
    """
    if factor <= 1.0:
        return image
    return ImageEnhance.Color(image).enhance(factor)


def apply_gaussian_blur_overlay_expansion(
    image: Image.Image,
    canvas_width: int,
    canvas_height: int,
    overlay_color: str,
    opacity: int,
    blur_radius: int = 200,
    saturation: float = 1.0,
) -> Image.Image:
    """
    应用高斯模糊叠加效果（适用于扩展画布）

    Args:
        image: 原始图像
        canvas_width: 画布宽度
        canvas_height: 画布高度
        overlay_color: 叠加颜色
        opacity: 透明度百分比 (0-100)
        blur_radius: 全分辨率下的模糊半径 (默认200)
        saturation: 饱和度增强系数（1.0 = 不变，>1.0 增强，用于补偿覆盖层颜色淡化）

    Returns:
        应用效果后的背景图像
    """
    orig_w, orig_h = image.size
    image_long = max(orig_w, orig_h)

    scale_factor = _compute_scale_factor(image_long)

    blur_img = image.copy().convert('RGB')

    if scale_factor < 1.0:
        scaled_w = max(int(orig_w * scale_factor), _BLUR_WORK_MIN)
        scaled_h = max(int(orig_h * scale_factor), _BLUR_WORK_MIN)
        blur_img = blur_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

    effective_radius = blur_radius * scale_factor
    blur_img = _box_blur(blur_img, effective_radius)

    # 饱和度增强：在叠加覆盖层之前增强模糊图像的色彩，
    # 以补偿白色/黑色覆盖层导致的颜色淡化
    blur_img = _enhance_saturation(blur_img, saturation)

    blur_img = blur_img.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)

    overlay_rgb = COLOR_OPTIONS.get(overlay_color, (255, 255, 255))
    blur_arr = np.array(blur_img, dtype=np.float32)
    alpha = opacity / 100.0
    overlay_arr = np.full_like(blur_arr, fill_value=np.array(overlay_rgb, dtype=np.float32))
    blended = blur_arr * (1.0 - alpha) + overlay_arr * alpha
    blended = np.clip(blended, 0, 255).astype(np.uint8)

    return Image.fromarray(blended, mode='RGB')
