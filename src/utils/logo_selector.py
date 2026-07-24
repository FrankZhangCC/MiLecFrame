# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
Logo选择器模块
负责扫描logo目录、验证logo格式和根据相机品牌自动匹配logo
"""
import logging
import os
from pathlib import Path
from typing import List, Optional

import yaml
from PIL import Image

logger = logging.getLogger(__name__)


class LogoSelector:
    """Logo选择器类"""

    # 默认品牌缩放系数 YAML 内容（仅在配置文件不存在时写入）
    DEFAULT_SCALE_CONFIG = """# LOGO 品牌尺寸补偿系数
# keyword: 文件名匹配关键字（不区分大小写）
# scale_factor: 缩放系数（1.0=不变，<1.0 缩小，>1.0 放大）
# 细长条 LOGO（如索尼/佳能/富士）需缩小，紧凑型 LOGO（如哈苏）需放大

hasselblad_logo: 1.5
sony_logo: 0.7
canon_logo: 0.7
fujifilm_logo: 0.7
"""

    def __init__(self, logos_dir: str = None, scale_config_path: str = None):
        """
        初始化Logo选择器
        
        Args:
            logos_dir: logos目录路径，默认为assets/logos/
            scale_config_path: 品牌缩放系数配置文件路径，默认为data/logo_scale.yaml
        """
        project_root = Path(__file__).resolve().parent.parent.parent

        if logos_dir is None:
            self.logos_dir = project_root / 'assets' / 'logos'
        else:
            self.logos_dir = Path(logos_dir)
        self.logos_dir.mkdir(parents=True, exist_ok=True)

        # 品牌缩放系数配置文件
        if scale_config_path is None:
            self.scale_config_path = project_root / 'data' / 'logo_scale.yaml'
        else:
            self.scale_config_path = Path(scale_config_path)
        self._ensure_scale_file_exists()
        self.brand_scale_factors = self._load_scale_factors()

    def _ensure_scale_file_exists(self) -> None:
        """
        如果品牌缩放系数配置文件不存在，则创建默认文件
        """
        if self.scale_config_path.exists():
            return
        self.scale_config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.scale_config_path.write_text(self.DEFAULT_SCALE_CONFIG, encoding='utf-8')
            logger.info(f"已创建默认品牌缩放系数配置文件: {self.scale_config_path}")
        except Exception as e:
            logger.error(f"无法创建品牌缩放系数配置文件: {e}")

    def _load_scale_factors(self) -> dict:
        """
        从YAML文件加载品牌缩放系数
        """
        try:
            with open(self.scale_config_path, 'r', encoding='utf-8') as f:
                factors = yaml.safe_load(f)
            if not isinstance(factors, dict):
                logger.warning(
                    f"品牌缩放系数配置文件格式错误，期望 dict，实际为 {type(factors).__name__}"
                )
                return {}
            for key, val in list(factors.items()):
                if not isinstance(val, (int, float)):
                    logger.warning(f"品牌缩放系数无效: '{key}' = {val}，已跳过")
                    del factors[key]
            return factors
        except Exception as e:
            logger.error(f"无法加载品牌缩放系数配置文件: {e}")
            return {}

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
    
    @staticmethod
    def _is_white_logo(filename: str) -> bool:
        """
        检测logo文件名是否为白色变体（用于暗色背景）
        
        Args:
            filename: logo文件名（如 "canon_logo_white.png"）
            
        Returns:
            是否以 _white 结尾（不区分大小写）
        """
        name = os.path.splitext(filename)[0].lower()
        return name.endswith('_white')

    def auto_match_logo(
        self, camera_brand: str, is_dark_bg: Optional[bool] = None
    ) -> Optional[str]:
        """
        根据相机品牌自动匹配logo（不区分大小写，逐词匹配）
        
        Args:
            camera_brand: 相机品牌名称
            is_dark_bg: 背景是否为暗色（用于自动选择logo颜色变体）
                        - True → 暗色背景，优先选择 _white 后缀的logo
                        - False → 亮色背景，优先选择非 _white 后缀的logo
                        - None → 不区分颜色变体，返回第一个匹配（向后兼容）
            
        Returns:
            匹配的logo文件名，如果没有匹配则返回None
        """
        if not camera_brand:
            return None
        
        logos = self.scan_logos()
        brand_words = camera_brand.lower().split()
        
        # 优先匹配较长单词（品牌核心词），跳过过短的无意义词（如 AG、KG、Co 等）
        brand_words = [w for w in brand_words if len(w) >= 3]
        brand_words.sort(key=len, reverse=True)
        
        # 收集所有匹配品牌名称的logo
        matched_logos = []
        for logo in logos:
            logo_name = os.path.splitext(logo)[0].lower()
            for word in brand_words:
                if word in logo_name:
                    matched_logos.append(logo)
                    break
        
        if not matched_logos:
            return None
        
        # 根据背景明暗筛选logo颜色变体
        if is_dark_bg is not None:
            white_logos = [l for l in matched_logos if self._is_white_logo(l)]
            dark_logos = [l for l in matched_logos if not self._is_white_logo(l)]
            
            if is_dark_bg:
                # 暗色背景 → 优先白色logo（白色在暗色背景上更醒目）
                selected = white_logos or dark_logos
            else:
                # 亮色背景 → 优先非白色logo（深色在亮色背景上更醒目）
                selected = dark_logos or white_logos
            
            return selected[0] if selected else None
        
        # 未指定背景类型时，返回第一个匹配（保持向后兼容）
        return matched_logos[0]

    def get_brand_scale_factor(self, logo_filename: str) -> float:
        """
        根据logo文件名获取品牌独立缩放系数
        关键字匹配时不区分大小写
        """
        logo_lower = os.path.splitext(logo_filename)[0].lower()
        for keyword, factor in self.brand_scale_factors.items():
            if keyword.lower() in logo_lower:
                logger.debug(f"品牌缩放系数匹配: '{keyword}' → {factor} (logo: {logo_filename})")
                return factor
        return 1.0