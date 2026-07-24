# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
样式预览预置样本数据

提供预构建的 EXIF 数据字典、作者、地点、Logo 文件名等，
使预览渲染器可以跳过 ExifHelper/LogoSelector 等模块的直接调用，
提高实时预览效率。
"""

# 预置 EXIF 数据
# 全部使用字符串值，模拟真实 extract_exif_data() 的输出格式，
# 避免引擎内 ExifHelper 解码时出现 int/float → text_renderer 类型不匹配。
# shutter_speed 使用 "1/125"（格式化字符串）而非 0.008（秒数），
# 使最终渲染效果展示 1/125s 而非 0.008s。
PREVIEW_EXIF_DATA = {
    # ── 设备信息（需通过 device_mapper 的 pass-through，使返回同值） ──
    'camera_make': 'Leica',
    'camera_model': 'Q3 43',
    'lens_model': 'Summilux 28mm f/1.7',
    'short_lens': 'Summilux 28mm',

    # ── 曝光参数（全字符串，避免 raw_* 字段出现 int/float） ──
    'focal_length': '28',
    'focal_length_35mm': '28',
    'aperture': '1.7',
    'shutter_speed': '1/125',
    'iso': '200',

    # ── 拍摄时间（EXIF 标准格式：冒号分隔） ──
    'datetime_original': '2025:06:15 14:30:00',

    # ── GPS ──
    'gps': "31°13'51.1\"N 121°28'19.8\"E",
}

# 预置作者姓名
PREVIEW_AUTHOR = 'Frank Zhang'

# 预置拍摄地点
PREVIEW_LOCATION = 'Shanghai'

# 预置自定义文本（供 custom_text 预览）
PREVIEW_CUSTOM_TEXT = "Always believe that something wonderful\nis about to happen."
