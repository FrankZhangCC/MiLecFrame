# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
字体管理器模块
负责字体的加载、缓存和智能选择（中西文检测、系统字体回退）
"""
import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from PIL import ImageFont

logger = logging.getLogger(__name__)

_CJK_CHAR_RE = re.compile(
    r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff'
    r'\u3040-\u309f\u30a0-\u30ff\u31f0-\u31ff'  # 日文仮名
    r'\u3000-\u303f\uff00-\uffef]+'
)

# 系统字体映射（Windows），key = 样式配置中声明的字重值
_SYSTEM_LATIN_FILES = {
    'Light': 'segoeuil.ttf',
    'Book': 'segoeui.ttf',       # 部分系统无 segoebk.ttf，回退到 Regular
    'Regular': 'segoeui.ttf',
    'Medium': 'seguisb.ttf',
    'Semibold': 'seguisb.ttf',
    'Bold': 'segoeuib.ttf',
}
_SYSTEM_CJK_FILES = {
    'Light': 'msjhl.ttc',
    'Regular': 'msjh.ttc',
    'Medium': 'msjhbd.ttc',
    'Bold': 'msjhbd.ttc',
}


class FontManager:
    """字体管理器，负责字体的加载、缓存和智能选择"""

    def __init__(self, fonts_base_path: str = None):
        if fonts_base_path:
            self.fonts_base_path = fonts_base_path
        else:
            project_root = Path(__file__).resolve().parent.parent.parent
            self.fonts_base_path = os.path.join(project_root, 'assets', 'fonts')

        self.font_cache: Dict[tuple, ImageFont.FreeTypeFont] = {}
        self._windows_font_dir = os.path.join(
            os.environ.get('SystemRoot', 'C:\\Windows'), 'Fonts'
        )

    @staticmethod
    def split_mixed_text(text: str) -> List[Tuple[str, bool]]:
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

    def _try_load_font(self, path: str, font_size: int) -> Optional[ImageFont.FreeTypeFont]:
        try:
            font = ImageFont.truetype(path, size=font_size)
            if hasattr(font, 'getmetrics'):
                bbox = font.getbbox("Test")
                if bbox[3] - bbox[1] >= font_size * 0.3:
                    return font
        except (OSError, Exception):
            pass
        return None

    def load_font(
        self,
        fonts_config: Dict,
        original_image_size: Tuple[int, int],
        specific_size_ratio: float = None,
        text_content: str = "",
        force_chinese: bool = None
    ) -> ImageFont.FreeTypeFont:
        """加载响应式字体

        fonts_config 支持格式：
          latin:
            family: Gotham        # 自定义字体名，从 assets/fonts/ 加载 {family}-{weight}.otf
            weight: Medium        # 字重字符串，直接拼入文件名
            # 或用系统字体（二选一）
            # system: Segoe UI
          cjk:
            family: GlowSansSC-Normal
            weight: Medium
            # system: Microsoft JhengHei UI
          size_ratio: 0.015
          weight: Medium           # CLI 全局覆盖
        """
        is_cjk = force_chinese if force_chinese is not None else bool(_CJK_CHAR_RE.search(text_content or ""))

        latin_cfg = fonts_config.get('latin', {})
        cjk_cfg = fonts_config.get('cjk', {})

        # CLI 全局字重覆盖
        global_weight = fonts_config.get('weight')

        size_ratio = specific_size_ratio if specific_size_ratio is not None else fonts_config.get('size_ratio', 0.015)
        reference_side = min(original_image_size)
        font_size = max(12, int(reference_side * size_ratio))

        # 选择配置
        cfg = cjk_cfg if is_cjk else latin_cfg

        # 解析字重：通过 weights 映射表将抽象值转为具体字重字符串
        raw_weight = global_weight or cfg.get('weight', 'medium')
        weights_map = cfg.get('weights', {})
        weight = weights_map.get(raw_weight, raw_weight)  # 映射表中查不到则原样使用

        # 缓存 key
        family = cfg.get('family', '').strip()
        use_system = 'system' in cfg or not family
        if use_system:
            cache_source = f"sys:{('cjk' if is_cjk else 'latin')}:{weight}"
        else:
            cache_source = f"cust:{family}:{weight}"
        cache_key = (cache_source, font_size)

        if cache_key in self.font_cache:
            return self.font_cache[cache_key]

        font = None

        # 优先级 1：自定义字体 assets/fonts/
        if family and not use_system:
            for ext in ('.otf', '.ttf'):
                filepath = os.path.join(self.fonts_base_path, f"{family}-{weight}{ext}")
                if os.path.exists(filepath):
                    font = self._try_load_font(filepath, font_size)
                    if font:
                        break

        # 优先级 2：系统字体（含降级回退）
        if font is None:
            sys_map = _SYSTEM_CJK_FILES if is_cjk else _SYSTEM_LATIN_FILES
            # 要尝试的备选 weight 列表：当前 weight → Regular → 第一个可用
            fallback_weights = [weight] + [w for w in ['Regular', 'Medium', 'Light', 'Bold'] if w != weight]
            for fb_weight in fallback_weights:
                sys_file = sys_map.get(fb_weight)
                if not sys_file:
                    continue
                sys_path = os.path.join(self._windows_font_dir, sys_file)
                if os.path.exists(sys_path):
                    font = self._try_load_font(sys_path, font_size)
                    if font:
                        logger.debug(f"系统字体加载成功: weight={fb_weight}, 文件={sys_file}")
                        break
                    else:
                        logger.debug(f"系统字体加载失败: weight={fb_weight}, 文件={sys_file}")

        # 优先级 3：PIL 默认
        if font is None:
            font = ImageFont.load_default()
            logger.warning(f"字体全部回退失败，使用 PIL 默认字体")

        logger.info(f"字体加载完成: 来源={cache_source}, 字号={font_size}")

        self.font_cache[cache_key] = font
        return font
