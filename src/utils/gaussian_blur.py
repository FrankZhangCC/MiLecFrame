"""
高斯模糊工具模块
"""
from PIL import Image, ImageFilter
import numpy as np
from typing import Tuple


COLOR_OPTIONS = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "gray": (128, 128, 128)
}


def apply_gaussian_blur_overlay_expansion(
    image: Image.Image,
    canvas_width: int,
    canvas_height: int,
    overlay_color: str,
    opacity: int
) -> Image.Image:
    """
    应用高斯模糊叠加效果（适用于扩展画布）
    
    Args:
        image: 原始图像
        canvas_width: 画布宽度
        canvas_height: 画布高度
        overlay_color: 叠加颜色
        opacity: 透明度百分比
        
    Returns:
        应用效果后的背景图像
    """
    blur_img = image.copy()
    
    original_width, original_height = blur_img.size
    target_size = min(canvas_width, canvas_height)
    
    scale_factor = min(1.0, 2000.0 / max(target_size, 2000))
    scaled_width = max(int(original_width * scale_factor), 512)
    scaled_height = max(int(original_height * scale_factor), 512)
    
    if scale_factor < 1.0:
        blur_img = blur_img.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
    
    blur_radius = 200 * scale_factor
    blur_img = blur_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    
    blur_img = blur_img.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)
    
    overlay = Image.new('RGBA', (canvas_width, canvas_height),
                        color=(*COLOR_OPTIONS.get(overlay_color, (255, 255, 255)), int(255 * opacity / 100)))
    
    if blur_img.mode != 'RGBA':
        blur_img = blur_img.convert('RGBA')
    
    result = Image.alpha_composite(blur_img, overlay)
    
    result = result.convert('RGB')
    
    result = apply_dithering(result)
    
    return result


def apply_dithering(image: Image.Image) -> Image.Image:
    """
    应用抖动算法以减少色彩断层
    
    Args:
        image: 输入图像
        
    Returns:
        应用抖动后的图像
    """
    img_array = np.array(image, dtype=np.float64)
    
    height, width, channels = img_array.shape
    
    if height * width > 2000000:
        return image
    
    for y in range(height - 1):
        for x in range(width - 1):
            old_pixel = img_array[y, x].copy()
            
            new_pixel = np.round(np.clip(old_pixel, 0, 255))
            
            img_array[y, x] = new_pixel
            
            quant_error = old_pixel - new_pixel
            
            img_array[y, x + 1] += quant_error * (7 / 16)
            
            img_array[y + 1, x] += quant_error * (5 / 16)
            
            if x > 0:
                img_array[y + 1, x - 1] += quant_error * (3 / 16)
            
            img_array[y + 1, x + 1] += quant_error * (1 / 16)
    
    img_array = np.clip(img_array, 0, 255)
    img_array = img_array.astype(np.uint8)
    
    return Image.fromarray(img_array, mode='RGB')
