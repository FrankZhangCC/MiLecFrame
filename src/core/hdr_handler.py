"""
HDR图像处理模块
负责处理Gainmap HDR和UltraHDR格式的图像
"""
import os
from PIL import Image
from typing import Optional, Tuple
import numpy as np
import logging

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_SUPPORT = True
except ImportError:
    HEIF_SUPPORT = False
    print("Warning: pillow-heif not installed, UltraHDR support may be limited")

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    print("Warning: opencv-python not installed, some HDR processing may be limited")


class HDRHandler:
    """HDR图像处理器"""
    
    def __init__(self):
        """初始化HDR处理器"""
        self.supported_formats = ['HEIF', 'HEIC', 'AVIF']  # 包含HDR格式
        self.logger = logging.getLogger(__name__)
    
    def is_hdr_format(self, image_path: str) -> bool:
        """
        检测图像是否为HDR格式
        
        Args:
            image_path: 图像路径
            
        Returns:
            是否为HDR格式
        """
        try:
            img = Image.open(image_path)
            format_name = img.format
            
            # 如果是HEIF/HEIC/AVIF格式，很可能是HDR
            if format_name in ['HEIF', 'HEIC', 'AVIF']:
                return True
                
            # 检查EXIF中是否有HDR相关信息
            exif_data = img.info.get('exif', None)
            if exif_data:
                # 这里可以添加更多HDR检测逻辑
                pass
            
            return False
        except Exception as e:
            self.logger.error(f"检测HDR格式时出错: {str(e)}")
            return False
    
    def load_hdr_image(self, image_path: str) -> Optional[Image.Image]:
        """
        加载HDR图像
        
        Args:
            image_path: 图像路径
            
        Returns:
            加载的图像，如果失败则返回None
        """
        try:
            if not self.is_hdr_format(image_path):
                # 如果不是HDR格式，使用普通方式加载
                return Image.open(image_path)
            
            # 尝试使用pillow-heif处理
            if HEIF_SUPPORT:
                heif_file = pillow_heif.open_heif(image_path)
                img = Image.frombytes(
                    heif_file.mode,
                    heif_file.size,
                    heif_file.data,
                    "raw",
                    heif_file.mode,
                    heif_file.stride,
                )
                return img
            
            # 如果pillow-heif不可用，尝试其他方法
            if OPENCV_AVAILABLE:
                # 使用OpenCV读取（支持更多的图像格式）
                cv_img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
                if cv_img is not None:
                    # OpenCV使用BGR，转换为RGB
                    rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                    return Image.fromarray(rgb_img)
            
            # 如果上述方法都不行，尝试直接用PIL打开
            return Image.open(image_path)
            
        except Exception as e:
            self.logger.error(f"加载HDR图像时出错: {str(e)}")
            return None
    
    def convert_hdr_to_standard(self, hdr_image: Image.Image) -> Image.Image:
        """
        将HDR图像转换为标准动态范围图像
        
        Args:
            hdr_image: HDR图像
            
        Returns:
            标准动态范围图像
        """
        try:
            # 确保图像为RGB模式
            if hdr_image.mode != 'RGB':
                hdr_image = hdr_image.convert('RGB')
            
            # 如果有OpenCV支持，使用其色调映射功能
            if OPENCV_AVAILABLE:
                img_array = np.array(hdr_image)
                
                # 尝试使用OpenCV的色调映射算法
                tonemap = cv2.createTonemap(gamma=1.0)
                ldr_array = tonemap.process(img_array.astype(np.float32)/255.0)
                
                # 转换回uint8
                ldr_array = np.clip(ldr_array * 255, 0, 255).astype(np.uint8)
                
                return Image.fromarray(ldr_array)
            else:
                # 如果没有OpenCV，简单地转换为标准图像
                # 这可能不会产生最佳效果，但至少能让图像可用
                return hdr_image
            
        except Exception as e:
            self.logger.error(f"转换HDR图像时出错: {str(e)}")
            # 返回原始图像的RGB版本
            if hdr_image.mode != 'RGB':
                return hdr_image.convert('RGB')
            return hdr_image
    
    def process_hdr_image(self, image_path: str) -> Optional[Image.Image]:
        """
        完整的HDR图像处理流程
        
        Args:
            image_path: 图像路径
            
        Returns:
            处理后的标准图像
        """
        try:
            # 加载HDR图像
            hdr_img = self.load_hdr_image(image_path)
            if hdr_img is None:
                return None
            
            # 转换为标准动态范围
            standard_img = self.convert_hdr_to_standard(hdr_img)
            
            return standard_img
        except Exception as e:
            self.logger.error(f"处理HDR图像时出错: {str(e)}")
            return None