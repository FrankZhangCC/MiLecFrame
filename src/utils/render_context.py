"""
渲染上下文模块
负责收集和准备所有显示文本数据，将数据准备逻辑从渲染器中解耦

样式配置通过 info_position 的 key 声明需要哪些信息，
RenderContext 根据 key 返回对应的显示文本，内部处理所有条件逻辑。
新增显示字段只需在此类中添加 get_text 分支即可。
"""
from typing import Dict, Optional, Tuple
from .exif_helper import ExifHelper


class RenderContext:
    """渲染上下文，统一管理所有可显示文本信息"""

    def __init__(self, image_size: Tuple[int, int], exif_data: Optional[Dict] = None,
                 author: Optional[str] = None, location: Optional[str] = None):
        self.image_size = image_size
        self.exif_data = exif_data
        self.author = author
        self.location = location

        self._display_data = ExifHelper().get_display_data(exif_data) if exif_data else {}

        width, height = image_size
        self.is_vertical_or_square = height >= width

    def get_text(self, key: str) -> Optional[str]:
        """根据 key 返回对应的显示文本，无数据时返回 None

        支持的 key:
            exif, timestamp, timestamp_author, camera_lens, camera, camera_make, lens, author, location, gps
        """
        if key == 'exif':
            return self._display_data.get('exif_formatted') or None
        elif key == 'timestamp':
            if self.exif_data and 'datetime_original' in self.exif_data:
                return self.exif_data['datetime_original']
        elif key == 'timestamp_author':
            if self.exif_data and 'datetime_original' in self.exif_data:
                ts = self.exif_data['datetime_original']
                auth = self.author or ''
                return f"{ts} by {auth}" if auth else ts
        elif key == 'camera_lens':
            combined = self._display_data.get('camera_lens_combined')
            #   if self.is_vertical_or_square and self._display_data.get('camera_combined'):
            #       return self._display_data['camera_combined']
            return combined
        elif key == 'camera':
            return self._display_data.get('camera_combined') or None
        elif key == 'camera_make':
            return self._display_data.get('camera_make') or None
        elif key == 'lens':
            return self._display_data.get('lens_model') or None
        elif key == 'author':
            return self.author or None
        elif key == 'location':
            return self.location or None
        elif key == 'gps':
            if self.exif_data and 'gps' in self.exif_data:
                return self.exif_data['gps']
        return None

    @property
    def display_data(self):
        """提供对 display_data 的只读访问"""
        return self._display_data
