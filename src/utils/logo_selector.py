"""
Logo选择器模块
负责扫描logo目录、验证logo格式和根据相机品牌自动匹配logo
"""
import os
from pathlib import Path
from typing import List, Optional
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
        根据相机品牌自动匹配logo（不区分大小写，文件名包含品牌名称即可）
        
        Args:
            camera_brand: 相机品牌名称
            
        Returns:
            匹配的logo文件名，如果没有匹配则返回None
        """
        if not camera_brand:
            return None
        
        logos = self.scan_logos()
        brand_lower = camera_brand.lower()
        
        for logo in logos:
            logo_name = os.path.splitext(logo)[0].lower()
            if brand_lower in logo_name or logo_name in brand_lower:
                return logo
        
        return None