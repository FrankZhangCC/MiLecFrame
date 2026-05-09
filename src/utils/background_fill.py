"""
背景填充管理器模块
负责背景填充类型的注册、渲染和查询，是背景填充相关功能的唯一入口。
"""
from typing import Dict, List, Optional, Tuple

from PIL import Image

from .gaussian_blur import apply_gaussian_blur_overlay_expansion


class BackgroundFillManager:
    """背景填充管理器，集中管理所有背景填充类型及其渲染逻辑"""

    FILL_TYPES: Dict[str, Dict] = {
        # ── 纯色填充 ──
        'pure_black': {
            'label': '纯黑背景',
            'method': 'solid',
            'color': (0, 0, 0),
            'text_scheme': 'dark',
        },
        'pure_white': {
            'label': '纯白背景',
            'method': 'solid',
            'color': (255, 255, 255),
            'text_scheme': 'light',
        },
        # ── 高斯模糊叠加 ──
        'gaussian_black_65': {
            'label': '模糊背景 (深色 65%)',
            'method': 'gaussian',
            'overlay_color': 'black',
            'opacity': 65,
            'blur_radius': 200,
            'saturation': 1.8,
            'text_scheme': 'dark',
        },
        'gaussian_white_80': {
            'label': '模糊背景 (浅色 80%)',
            'method': 'gaussian',
            'overlay_color': 'white',
            'opacity': 80,
            'blur_radius': 200,
            'saturation': 2.0,
            'text_scheme': 'light',
        },
        'gaussian_black_35': {
            'label': '模糊背景 (深色 35%)',
            'method': 'gaussian',
            'overlay_color': 'black',
            'opacity': 35,
            'blur_radius': 200,
            'saturation': 1.3,
            'text_scheme': 'dark',
        },
        'gaussian_white_50': {
            'label': '模糊背景 (浅色 50%)',
            'method': 'gaussian',
            'overlay_color': 'white',
            'opacity': 50,
            'blur_radius': 200,
            'saturation': 1.5,
            'text_scheme': 'light',
        },
    }

    DEFAULT_FILL = 'gaussian_white_80'

    # ── 查询接口 ──────────────────────────────────────

    @classmethod
    def get_choices(cls) -> Dict[str, str]:
        """
        GUI 用：返回 {label: key} 映射，供下拉框使用
        """
        return {v['label']: k for k, v in cls.FILL_TYPES.items()}

    @classmethod
    def get_keys(cls) -> List[str]:
        """
        CLI / 校验用：返回所有 fill type key 列表
        """
        return list(cls.FILL_TYPES.keys())

    @classmethod
    def get_label(cls, key: str) -> str:
        """根据 key 获取中文标签"""
        cfg = cls.FILL_TYPES.get(key)
        return cfg['label'] if cfg else key

    @classmethod
    def is_dark_bg(cls, fill_type: str) -> bool:
        """判断是否为深色背景（用于文字颜色自动适配）"""
        cfg = cls.FILL_TYPES.get(fill_type)
        return cfg['text_scheme'] == 'dark' if cfg else False

    # ── 渲染接口 ──────────────────────────────────────

    @classmethod
    def render(
        cls,
        image: Image.Image,
        canvas_width: int,
        canvas_height: int,
        fill_type: str,
        *,
        color: Optional[Tuple[int, int, int]] = None,
        opacity: Optional[int] = None,
        blur_radius: Optional[int] = None,
        saturation: Optional[float] = None,
    ) -> Image.Image:
        """
        创建背景层

        Args:
            image: 原始图像（高斯模糊需要）
            canvas_width: 画布宽度
            canvas_height: 画布高度
            fill_type: 填充类型 key
            color: 覆盖默认颜色（纯色填充时为 RGB 元组）
            opacity: 覆盖默认透明度 (0-100)
            blur_radius: 覆盖默认模糊半径
            saturation: 覆盖默认饱和度增强系数（>1.0 增强，1.0 不变）

        Returns:
            RGB 模式的背景图像
        """
        cfg = cls.FILL_TYPES.get(fill_type)
        if not cfg:
            raise ValueError(f"未知背景填充类型: {fill_type}")

        if cfg['method'] == 'solid':
            c = color if color is not None else cfg['color']
            return Image.new('RGB', (canvas_width, canvas_height), color=c)
        else:
            overlay = cfg['overlay_color']
            o = opacity if opacity is not None else cfg['opacity']
            r = blur_radius if blur_radius is not None else cfg.get('blur_radius', 200)
            s = saturation if saturation is not None else cfg.get('saturation', 1.0)
            return apply_gaussian_blur_overlay_expansion(
                image, canvas_width, canvas_height, overlay,
                opacity=o,
                blur_radius=r,
                saturation=s,
            )

    # ── 管理接口（预留扩展）────────────────────────────

    @classmethod
    def register(
        cls,
        key: str,
        label: str,
        method: str,
        text_scheme: str,
        *,
        color: Optional[Tuple[int, int, int]] = None,
        overlay_color: Optional[str] = None,
        opacity: Optional[int] = None,
        blur_radius: Optional[int] = 200,
        saturation: Optional[float] = None,
    ):
        """
        注册新的填充类型（预留：支持未来运行时或插件扩展）

        Args:
            key: 唯一标识符
            label: 中文标签
            method: 'solid' 或 'gaussian'
            text_scheme: 'dark' 或 'light'
            color: 纯色 RGB 元组（method='solid' 时必需）
            overlay_color: 叠加颜色名（method='gaussian' 时必需）
            opacity: 透明度百分比
            blur_radius: 模糊半径
            saturation: 饱和度增强系数（>1.0 增强，1.0 不变，None 默认 1.0）
        """
        entry = {'label': label, 'method': method, 'text_scheme': text_scheme}
        if method == 'solid':
            entry['color'] = color
        else:
            entry['overlay_color'] = overlay_color
            entry['opacity'] = opacity
            entry['blur_radius'] = blur_radius
            if saturation is not None:
                entry['saturation'] = saturation
        cls.FILL_TYPES[key] = entry
