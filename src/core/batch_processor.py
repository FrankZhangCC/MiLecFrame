"""
批量处理器模块
负责批量处理图像，添加相框和EXIF信息
"""
import os
from PIL import Image
from pathlib import Path
from typing import Optional
import shutil

# 修改导入路径，使用绝对导入
from src.utils.exif_helper import ExifHelper
from src.utils.config_manager import ConfigManager
from src.core.image_processor import ImageProcessor


class BatchProcessor:
    """批量处理器"""
    
    def __init__(self):
        """初始化批量处理器"""
        self.exif_helper = ExifHelper()
        self.config_manager = ConfigManager()
    
    def batch_process(
        self,
        input_folder: str,
        output_folder: str,
        author: Optional[str] = None,
        location: Optional[str] = None,
        style_name: Optional[str] = None,
        bg_fill_type: str = 'pure_white',
        font_weight: str = 'medium',
        recursive: bool = False
    ) -> bool:
        """
        批量处理图像
        
        Args:
            input_folder: 输入文件夹路径
            output_folder: 输出文件夹路径
            author: 作者名
            location: 拍摄地点
            style_name: 样式名称
            bg_fill_type: 背景填充类型
            font_weight: 字体字重
            recursive: 是否递归处理子文件夹
            
        Returns:
            处理是否成功
        """
        try:
            # 确保输出目录存在
            os.makedirs(output_folder, exist_ok=True)
            
            # 支持的图像格式
            supported_formats = ('.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.webp')
            
            # 获取要处理的文件列表
            image_files = []
            input_path = Path(input_folder)
            
            if recursive:
                # 递归查找图像文件
                for ext in supported_formats:
                    image_files.extend(input_path.rglob(f"*{ext}"))
            else:
                # 只查找当前目录的图像文件
                for ext in supported_formats:
                    image_files.extend(input_path.glob(f"*{ext}"))
            
            if not image_files:
                print("未找到支持的图像文件")
                return False
            
            # 处理每个图像文件
            processor = ImageProcessor(style_config=style_name)
            
            for i, img_path in enumerate(image_files):
                try:
                    print(f"正在处理 ({i+1}/{len(image_files)}): {img_path.name}")
                    
                    # 构造输出路径
                    rel_path = img_path.relative_to(input_path)
                    output_img_path = Path(output_folder) / rel_path
                    
                    # 确保子目录存在
                    output_img_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # 处理图像
                    success = processor.process(
                        input_path=str(img_path),
                        output_path=str(output_img_path),
                        author=author,
                        location=location,
                        style_name=style_name,
                        bg_fill_type=bg_fill_type,
                        font_weight=font_weight
                    )
                    
                    if not success:
                        print(f"处理失败: {img_path.name}")
                    
                except Exception as e:
                    print(f"处理文件 {img_path.name} 时出错: {str(e)}")
                    continue
            
            return True
            
        except Exception as e:
            print(f"批量处理错误: {str(e)}")
            return False