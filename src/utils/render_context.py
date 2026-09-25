# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

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
                 author: Optional[str] = None, location: Optional[str] = None,
                 lens_display_mode: str = 'combined', use_short_lens: bool = False,
                 custom_text: Optional[str] = None,
                 timestamp_display_mode: str = 'full'):
        self.image_size = image_size
        self.exif_data = exif_data
        self.author = author
        self.location = location
        self.lens_display_mode = lens_display_mode
        self.use_short_lens = use_short_lens
        self.custom_text = custom_text
        self.timestamp_display_mode = timestamp_display_mode

        self._display_data = ExifHelper().get_display_data(exif_data) if exif_data else {}

        width, height = image_size
        self.is_vertical_or_square = height >= width

    def get_text(self, key: str) -> Optional[str]:
        """根据 key 返回对应的显示文本，无数据时返回 None

        支持的 key:
            exif, timestamp, timestamp_author, camera_lens, camera, camera_make, lens, author, location, gps, custom_text,
            focal_length_formatted, aperture_formatted, shutter_speed_formatted, iso_formatted
        """
        if key == 'exif':
            return self._display_data.get('exif_formatted') or None
        elif key == 'timestamp':
            # 根据 timestamp_display_mode 控制拍摄时间的显示格式
            mode = self.timestamp_display_mode
            if mode == 'hide':
                return None
            if self.exif_data and 'datetime_original' in self.exif_data:
                raw = self.exif_data['datetime_original']
                # date_only: 取前10字符 "yyyy.mm.dd"；full: 完整格式 "yyyy.mm.dd hh:mm:ss"
                return raw[:10] if mode == 'date_only' else raw
        elif key == 'timestamp_author':
            ts = self.get_text('timestamp')
            auth = self.author or ''
            if ts and auth:
                # 情况1: 时间 + 作者 → "2024.01.15 by Frank"
                return f"{ts} by {auth}"
            elif ts:
                # 情况3: 仅时间（作者未填）→ "2024.01.15"
                return ts
            elif auth:
                # 情况2: 仅作者（时间不显示）→ "Shot by Frank"
                return f"Shot by {auth}"
            # 情况4: 两者都没有 → 不渲染
            return None
        elif key == 'camera_lens':
            if self.lens_display_mode == 'camera_only':
                return self._display_data.get('camera_combined')
            elif self.lens_display_mode == 'lens_only':
                if self.use_short_lens:
                    return self._display_data.get('short_lens')
                return self._display_data.get('lens_model')
            else:
                if self.use_short_lens:
                    return self._display_data.get('camera_lens_combined_short')
                return self._display_data.get('camera_lens_combined')
        elif key == 'camera':
            return self._display_data.get('camera_combined') or None
        elif key == 'camera_make':
            return self._display_data.get('camera_make') or None
        elif key == 'lens':
            if self.use_short_lens:
                return self._display_data.get('short_lens') or None
            return self._display_data.get('lens_model') or None
        elif key == 'author':
            return self.author or None
        elif key == 'location':
            return self.location or None
        elif key == 'gps':
            if self.exif_data and 'gps' in self.exif_data:
                return self.exif_data['gps']
        elif key == 'focal_length_formatted':
            # 四个曝光元素键全部转发 ExifHelper 的共享格式化方法，
            # 与 exif 组合文本同源（唯一格式化点，禁止在此另行实现）
            return ExifHelper.format_focal_length(self.exif_data)
        elif key == 'aperture_formatted':
            return ExifHelper.format_aperture(self.exif_data)
        elif key == 'shutter_speed_formatted':
            return ExifHelper.format_shutter_speed_text(self.exif_data)
        elif key == 'iso_formatted':
            # 裸值：'ISO' 前缀由样式标签（如 FilmClip defined_text）或组合文本承担
            return ExifHelper.get_iso_value(self.exif_data)
        elif key == 'custom_text':
            return self.custom_text or None
        return None

    @property
    def display_data(self):
        """提供对 display_data 的只读访问"""
        return self._display_data
