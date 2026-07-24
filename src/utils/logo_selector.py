"""
Logo选择器模块
负责扫描logo目录、验证logo格式和根据相机品牌自动匹配logo
"""
import os
from pathlib import Path
from typing import List, Optional
import re
from PIL import Image


class LogoSelector:
    """Logo选择器类"""
    
    def __init__(self, logos_dir: str = None):
        """
        初始化Logo选择器
        
        Args:
            logos_dir: logos目录路径，默认为assets/logos/
        """
        if logos_dir is None:
            # 设置默认logos目录
            project_root = Path(__file__).resolve().parent.parent.parent
            self.logos_dir = project_root / 'assets' / 'logos'
        else:
            self.logos_dir = Path(logos_dir)
        
        # 确保目录存在
        self.logos_dir.mkdir(parents=True, exist_ok=True)
    
    def scan_logos(self) -> List[str]:
        """
        扫描logos目录中的PNG文件
        
        Returns:
            PNG文件名列表
        """
        logos = []
        for file_path in self.logos_dir.glob("*.png"):
            logos.append(file_path.name)
        return sorted(logos)
    
    def validate_logo(self, logo_path: str) -> tuple[bool, str]:
        """
        验证logo文件是否为正方形PNG文件
        
        Args:
            logo_path: logo文件路径
            
        Returns:
            (是否有效, 错误信息)
        """
        try:
            with Image.open(logo_path) as img:
                if img.format.lower() != 'png':
                    return False, "文件不是PNG格式"
                
                width, height = img.size
                if width != height:
                    return False, f"图片不是正方形，宽高比为 {width}:{height}"
                
                return True, "验证通过"
        except Exception as e:
            return False, f"无法打开图片文件: {str(e)}"
    
    def auto_match_logo(self, camera_brand: str) -> Optional[str]:
        """
        根据相机品牌自动匹配logo（忽略大小写）
        
        Args:
            camera_brand: 相机品牌名称
            
        Returns:
            匹配的logo文件名，如果没有匹配则返回None
        """
        if not camera_brand:
            return None
        
        # 获取所有logo文件
        logos = self.scan_logos()
        
        # 移除文件扩展名并转换为小写进行比较
        logo_names = [os.path.splitext(logo)[0].lower() for logo in logos]
        
        # 规范化品牌名称
        normalized_brand = self._normalize_brand_name(camera_brand).lower()
        
        # 查找精确匹配（忽略大小写）
        for i, logo_name in enumerate(logo_names):
            if normalized_brand == logo_name:
                return logos[i]
        
        # 如果没有精确匹配，尝试部分匹配（忽略大小写）
        for i, logo_name in enumerate(logo_names):
            if normalized_brand in logo_name or logo_name in normalized_brand:
                return logos[i]
        
        return None
    
    def _normalize_brand_name(self, brand: str) -> str:
        """
        标准化品牌名称，去除特殊字符和空格
        
        Args:
            brand: 原始品牌名称
            
        Returns:
            标准化后的品牌名称
        """
        # 移除特殊字符，只保留字母数字和空格
        cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', brand)
        # 移除多余空格
        return ' '.join(cleaned.split())