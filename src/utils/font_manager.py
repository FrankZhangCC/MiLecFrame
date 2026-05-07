"""
字体管理器模块
负责字体的加载、缓存和智能选择（中西文检测、字重映射）
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from PIL import ImageFont

_CJK_CHAR_RE = re.compile(
    r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff'
    r'\u3040-\u309f\u30a0-\u30ff\u31f0-\u31ff'  # 日文仮名
    r'\u3000-\u303f\uff00-\uffef]+'
)


class FontManager:
    """字体管理器，负责字体的加载、缓存和智能选择"""

    def __init__(self, fonts_base_path: str = None):
        if fonts_base_path:
            self.fonts_base_path = fonts_base_path
        else:
            project_root = Path(__file__).resolve().parent.parent.parent
            self.fonts_base_path = os.path.join(project_root, 'assets', 'fonts')

        self.font_cache: Dict[tuple, ImageFont.FreeTypeFont] = {}

    @staticmethod
    def split_mixed_text(text: str) -> List[Tuple[str, bool]]:
        """
        将混排文本拆分为 CJK / 非 CJK 片段序列
        返回 [(segment_text, is_cjk), ...]
        """
        if not text:
            return []
        segments = []
        pos = 0
        for match in _CJK_CHAR_RE.finditer(text):
            if match.start() > pos:
                segments.append((text[pos:match.start()], False))
            segments.append((match.group(), True))
            pos = match.end()
        if pos < len(text):
            segments.append((text[pos:], False))
        return segments

    def _build_font_weight_mapping(self, font_base_name: str) -> Dict[str, Dict[str, str]]:
        return {
            'light': {
                'regular': f'{font_base_name}-Light',
                'chinese': 'GlowSansSC-Normal-Light.otf' if font_base_name == 'Gotham' else f'GlowSansSC-{font_base_name}-Light.otf'
            },
            'medium': {
                'regular': f'{font_base_name}-Medium',
                'chinese': 'GlowSansSC-Normal-Medium.otf' if font_base_name == 'Gotham' else f'GlowSansSC-{font_base_name}-Medium.otf'
            },
            'regular': {
                'regular': f'{font_base_name}-Book',
                'chinese': 'GlowSansSC-Normal-Regular.otf' if font_base_name == 'Gotham' else f'GlowSansSC-{font_base_name}-Regular.otf'
            }
        }

    def load_font(
        self,
        fonts_config: Dict,
        original_image_size: Tuple[int, int],
        specific_size_ratio: float = None,
        text_content: str = "",
        force_chinese: bool = None
    ) -> ImageFont.FreeTypeFont:
        """
         加载响应式字体，使用原始图像的参照边（短边）作为计算基准

        Args:
            fonts_config: 字体配置
            original_image_size: 原始图像尺寸
            specific_size_ratio: 特定的字体大小比例（可选）
            text_content: 文本内容，用于判断使用哪种字体
            force_chinese: 强制使用/不使用中文字体（None 则自动检测）

        Returns:
            字体对象
        """
        font_weight = fonts_config.get('weight', 'medium')
        font_base_name = fonts_config.get('family', 'Gotham')

        font_weight_mapping = self._build_font_weight_mapping(font_base_name)
        weight_config = font_weight_mapping.get(font_weight, font_weight_mapping['medium'])

        size_ratio = specific_size_ratio if specific_size_ratio is not None else fonts_config.get('size_ratio', 0.015)

        reference_side = min(original_image_size)
        font_size = max(12, int(reference_side * size_ratio))

        if force_chinese is not None:
            contains_chinese = force_chinese
        else:
            contains_chinese = bool(_CJK_CHAR_RE.search(text_content))

        cache_key = (
            font_base_name,
            font_weight,
            font_size,
            contains_chinese
        )

        if cache_key in self.font_cache:
            return self.font_cache[cache_key]

        font_name = weight_config['regular']
        if contains_chinese:
            font_candidates = [
                weight_config['chinese'],
                font_name + '.otf',
                font_name + '.ttf',
            ]
        else:
            font_candidates = [
                font_name + '.otf',
                font_name + '.ttf',
            ]

        font_paths = [os.path.join(self.fonts_base_path, font) for font in font_candidates]

        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    font = ImageFont.truetype(font_path, size=font_size)
                    if hasattr(font, 'getmetrics'):
                        bbox = font.getbbox("Test")
                        actual_height = bbox[3] - bbox[1]
                        if actual_height < font_size * 0.3:
                            continue
                        self.font_cache[cache_key] = font
                        return font
                    else:
                        continue
                except (OSError, Exception):
                    continue

        default_font = ImageFont.load_default()
        self.font_cache[cache_key] = default_font
        return default_font
