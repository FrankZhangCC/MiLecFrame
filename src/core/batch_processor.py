"""
批量图像处理器模块
负责批量处理多张图像并添加相框
"""
import os
import sys
import concurrent.futures
from pathlib import Path
from typing import List, Optional, Dict
from PIL import Image
import logging

# 添加项目根目录到sys.path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from utils.exif_helper import ExifHelper
from core.image_processor import ImageProcessor


class BatchProcessor:
    """批量图像处理器"""
    
    def __init__(self, max_workers: int = 4):
        """
        初始化批量处理器
        
        Args:
            max_workers: 最大并发数
        """
        self.max_workers = max_workers
        self.image_processor = ImageProcessor()
        
        # 设置日志
        self.logger = logging.getLogger(__name__)
    
    def batch_process(
        self, 
        input_folder: str, 
        output_folder: str, 
        author: Optional[str] = None, 
        location: Optional[str] = None,
        style_name: Optional[str] = None,
        bg_fill_type: str = "white",
        decorations: Optional[List[Dict]] = None,
        font_weight: Optional[str] = None,
        recursive: bool = False
    ) -> bool:
        """
        批量处理图像
        
        Args:
            input_folder: 输入文件夹路径
            output_folder: 输出文件夹路径
            author: 作者姓名
            location: 拍摄地点
            style_name: 样式名称
            bg_fill_type: 背景填充类型
            decorations: 装饰元素列表
            font_weight: 字体字重 (light, regular, medium)
            recursive: 是否递归处理子文件夹
            
        Returns:
            是否处理成功
        """
        try:
            # 获取所有支持的图像文件
            image_files = self._get_image_files(input_folder, recursive)
            
            if not image_files:
                self.logger.warning(f"在 {input_folder} 中未找到支持的图像文件")
                return False
            
            self.logger.info(f"找到 {len(image_files)} 张图像文件")
            
            # 确保输出文件夹存在
            os.makedirs(output_folder, exist_ok=True)
            
            # 创建进度跟踪变量
            total_count = len(image_files)
            processed_count = 0
            failed_count = 0
            
            # 并行处理图像
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # 提交任务
                future_to_file = {
                    executor.submit(
                        self._process_single_image,
                        img_file,
                        output_folder,
                        author,
                        location,
                        style_name,
                        bg_fill_type,
                        decorations,
                        font_weight
                    ): img_file for img_file in image_files
                }
                
                # 处理结果
                for future in concurrent.futures.as_completed(future_to_file):
                    img_file = future_to_file[future]
                    try:
                        success = future.result()
                        if success:
                            processed_count += 1
                            self.logger.info(f"成功处理: {img_file}")
                        else:
                            failed_count += 1
                            self.logger.error(f"处理失败: {img_file}")
                    except Exception as e:
                        failed_count += 1
                        self.logger.error(f"处理 {img_file} 时发生异常: {str(e)}")
            
            self.logger.info(f"批量处理完成: 总计 {total_count}, 成功 {processed_count}, 失败 {failed_count}")
            return failed_count == 0
            
        except Exception as e:
            self.logger.error(f"批量处理时发生错误: {str(e)}")
            return False
    
    def _get_image_files(self, folder_path: str, recursive: bool) -> List[str]:
        """
        获取文件夹中的所有图像文件
        
        Args:
            folder_path: 文件夹路径
            recursive: 是否递归搜索
            
        Returns:
            图像文件路径列表
        """
        image_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.heic', '.heif', '.avif'}
        image_files = []
        
        folder = Path(folder_path)
        
        if recursive:
            # 递归搜索所有子文件夹
            for ext in image_extensions:
                image_files.extend([str(p) for p in folder.rglob(f'*{ext}')])
                image_files.extend([str(p) for p in folder.rglob(f'*{ext.upper()}')])
        else:
            # 只搜索当前文件夹
            for ext in image_extensions:
                image_files.extend([str(p) for p in folder.glob(f'*{ext}')])
                image_files.extend([str(p) for p in folder.glob(f'*{ext.upper()}')])
        
        return sorted(image_files)
    
    def _process_single_image(
        self,
        input_path: str,
        output_folder: str,
        author: Optional[str],
        location: Optional[str],
        style_name: Optional[str],
        bg_fill_type: str,
        decorations: Optional[List[Dict]],
        font_weight: Optional[str] = None
    ) -> bool:
        """
        处理单个图像
        
        Args:
            input_path: 输入图像路径
            output_folder: 输出文件夹
            author: 作者姓名
            location: 拍摄地点
            style_name: 样式名称
            bg_fill_type: 背景填充类型
            decorations: 装饰元素列表
            font_weight: 字体字重 (light, regular, medium)
            
        Returns:
            是否处理成功
        """
        try:
            # 构造输出路径
            input_filename = Path(input_path).stem
            output_path = os.path.join(output_folder, f"{input_filename}_framed.jpg")
            
            # 处理图像
            return self.image_processor.process(
                input_path=input_path,
                output_path=output_path,
                author=author,
                location=location,
                style_name=style_name,
                bg_fill_type=bg_fill_type,
                decorations=decorations,
                font_weight=font_weight
            )
        except Exception as e:
            self.logger.error(f"处理单个图像时发生错误 {input_path}: {str(e)}")
            return False