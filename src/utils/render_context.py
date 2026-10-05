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

    # ── 文本键 → 用户选项依赖注册表（计划 §5.2，只读）──────────
    # 回答"这个文本键受哪些用户选项影响"：键为 get_text 支持的全部
    # 文本键，值为选项 ID 集合（与 GUI RawOptionValues 字段名对齐）。
    # 空集 = 已知文本键但无输入依赖（属于相框文字，如 exif/camera）；
    # 未注册的键 = 未知键（不提供输入能力，也不能据此认定有文字）。
    # 新增文本键时必须同步更新此表，并用真实 get_text 输出验证关系
    # （C08/C12 据此断言）。
    _OPTION_DEPENDENCIES = {
        'author': frozenset({'author'}),
        'location': frozenset({'location'}),
        'custom_text': frozenset({'custom_text'}),
        'timestamp': frozenset({'timestamp_display_mode'}),
        'timestamp_author': frozenset({'author', 'timestamp_display_mode'}),
        'camera_lens': frozenset({'lens_display_mode', 'lens_name_mode'}),
        'lens': frozenset({'lens_name_mode'}),
        'short_lens': frozenset({'lens_name_mode'}),
        # 以下为相框文字：无本次用户选项依赖
        'exif': frozenset(),
        'camera': frozenset(),
        'camera_make': frozenset(),
        'gps': frozenset(),
        'focal_length_formatted': frozenset(),
        'aperture_formatted': frozenset(),
        'shutter_speed_formatted': frozenset(),
        'iso_formatted': frozenset(),
    }

    @classmethod
    def get_option_dependencies(cls, key: str) -> frozenset:
        """查询文本键受哪些用户选项影响（类级只读，无需实例化）

        未知键返回空集——与"已知但无输入依赖"的键返回值相同，区分
        二者请用 supports_text_key。
        """
        return cls._OPTION_DEPENDENCIES.get(key, frozenset())

    @classmethod
    def supports_text_key(cls, key: str) -> bool:
        """区分"已知文本键（含无输入依赖的相框文字）"与未知键"""
        return key in cls._OPTION_DEPENDENCIES

    def __init__(self, image_size: Tuple[int, int], exif_data: Optional[Dict] = None,
                 author: Optional[str] = None, location: Optional[str] = None,
                 lens_display_mode: str = 'combined', lens_name_mode: str = 'default',
                 custom_text: Optional[str] = None,
                 timestamp_display_mode: str = 'full'):
        self.image_size = image_size
        self.exif_data = exif_data
        self.author = author
        self.location = location
        self.lens_display_mode = lens_display_mode
        # 镜头名模式（三态）：default=键归位（lens 出完整名、short_lens 出短版名）/
        # full=强制完整镜头名（short_lens 键的输出被 lens_model 替代）/
        # short=强制短版镜头名（lens、camera_lens 键的输出被短版名替代）
        self.lens_name_mode = lens_name_mode
        self.custom_text = custom_text
        self.timestamp_display_mode = timestamp_display_mode

        self._display_data = ExifHelper().get_display_data(exif_data) if exif_data else {}

        width, height = image_size
        self.is_vertical_or_square = height >= width

    def get_text(self, key: str) -> Optional[str]:
        """根据 key 返回对应的显示文本，无数据时返回 None

        支持的 key:
            exif, timestamp, timestamp_author, camera_lens, camera, camera_make, lens, short_lens, author, location, gps, custom_text,
            focal_length_formatted, aperture_formatted, shutter_speed_formatted, iso_formatted

        lens_name_mode（default/full/short）控制镜头长短名的替代关系：
        short_lens 键在 full 下输出 lens_model；lens、camera_lens 键在 short 下输出短版名。
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
                # "短版镜头名"模式下输出短版名，否则完整镜头名
                if self.lens_name_mode == 'short':
                    return self._display_data.get('short_lens')
                return self._display_data.get('lens_model')
            else:
                # "短版镜头名"模式下输出短版组合名，否则完整组合名
                if self.lens_name_mode == 'short':
                    return self._display_data.get('camera_lens_combined_short')
                return self._display_data.get('camera_lens_combined')
        elif key == 'camera':
            return self._display_data.get('camera_combined') or None
        elif key == 'camera_make':
            return self._display_data.get('camera_make') or None
        elif key == 'short_lens':
            # 短版镜头名（键归位：默认输出短版名）。
            # 三态"完整镜头名"（'full'）下被完整镜头名替代——
            # 即用户强制统一为完整名时，样式里的 short_lens 行也显示完整名。
            if self.lens_name_mode == 'full':
                return self._display_data.get('lens_model') or None
            return self._display_data.get('short_lens') or None
        elif key == 'lens':
            # 镜头型号（键归位：默认输出完整镜头名）。
            # 三态"短版镜头名"（'short'）下被短版名替代——
            # 保留 short_lens 作为 lens 替代的能力，GUI 下拉照常生效。
            if self.lens_name_mode == 'short':
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
