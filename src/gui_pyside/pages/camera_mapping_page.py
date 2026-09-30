# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
相机映射管理页面

提供品牌筛选、搜索、可编辑表格管理相机品牌和型号的映射关系。
页面骨架（加载/搜索/表格/增删/保存/刷新）由 CsvMappingPage 基类
提供（G7），本类只保留相机页的扩展点：品牌分组筛选、格式规范
文案、排序键与筛选逻辑。
"""
import logging
import re

from PySide6.QtWidgets import QVBoxLayout, QWidget

from qfluentwidgets import (
    PushButton, BodyLabel, CaptionLabel, CardWidget, FlowLayout,
)

from src.utils.device_mapper import DeviceMapper
from .csv_mapping_page import CsvMappingPage

logger = logging.getLogger(__name__)

# ── 品牌分组定义 ──
_BRAND_GROUPS = {
    "传统影像厂商": [
        ("canon", "Canon | 佳能", r'Canon|佳能'),
        ("nikon", "Nikon | 尼康", r'Nikon|尼康'),
        ("sony", "Sony | 索尼", r'Sony|索尼'),
        ("fuji", "Fujifilm | 富士", r'Fujifilm|富士'),
        ("panasonic", "Panasonic | 松下", r'Panasonic|松下'),
        ("leica", "Leica | 徕卡", r'Leica|徕卡'),
        ("hasselblad", "Hasselblad | 哈苏", r'Hasselblad|哈苏'),
        ("om", "OM SYSTEM | OLYMPUS | 奥之心", r'OM System|奥之心|Olympus|OLYMPUS'),
        ("ricoh", "RICOH | 理光", r'RICOH|理光'),
        ("pentax", "Pentax | 宾得", r'Pentax|宾得'),
    ],
    "新兴影像厂商": [
        ("dji", "DJI | 大疆", r'DJI|大疆'),
        ("insta360", "Insta360 | 影石", r'Insta360|影石'),
        ("gopro", "GoPro", r'GoPro'),
    ],
    "手机及移动设备": [
        ("apple", "Apple | 苹果", r'Apple|苹果'),
        ("xiaomi", "Xiaomi | 小米", r'Xiaomi|小米'),
        ("huawei", "Huawei | 华为", r'Huawei|华为'),
        ("vivo", "VIVO", r'Vivo'),
        ("oppo", "OPPO", r'Oppo'),
        ("samsung", "Samsung | 三星", r'Samsung|三星'),
        ("google", "Google | 谷歌", r'Google|谷歌'),
    ],
}

_OTHER_EXCLUDE = '|'.join(
    p for group in _BRAND_GROUPS.values() for _, _, p in group
)
_BRAND_PATTERNS = {
    key: pattern
    for group in _BRAND_GROUPS.values()
    for key, _, pattern in group
}


class CameraMappingPage(CsvMappingPage):
    """相机映射管理页面"""

    TITLE = "相机映射管理"
    ALL_LABEL = "全部品牌"
    LOG_NAME = "相机映射"
    HEADERS = ["原始品牌", "原始型号", "映射品牌", "映射型号"]
    COLUMNS = ["original_brand", "original_model", "mapped_brand", "mapped_model"]
    SAVE_FIELDNAMES = ['original_brand', 'original_model', 'mapped_brand', 'mapped_model', 'timestamp']
    DB_PATH_ATTR = 'camera_db_path'

    def __init__(self, parent=None):
        self._active_brand: str | None = None
        self._brand_buttons: dict[str, PushButton] = {}
        super().__init__(parent)

    # ── 基类扩展点 ──────────────────────────────────────────

    def _create_filter_area(self) -> QWidget:
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(8)

        for group_name, brands in _BRAND_GROUPS.items():
            card = CardWidget()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 8, 16, 8)
            card_layout.setSpacing(6)

            group_title = CaptionLabel(group_name)
            group_title.setStyleSheet("font-size: 12px; color: #666;")
            card_layout.addWidget(group_title)

            flow = FlowLayout()
            flow.setSpacing(4)
            for key, label, _ in brands:
                btn = PushButton(label)
                btn.setCheckable(True)
                btn.clicked.connect(lambda checked, k=key: self._on_brand_filter(k))
                self._apply_btn_style(btn)
                self._brand_buttons[key] = btn
                flow.addWidget(btn)

            other_btn = PushButton("其它")
            other_btn.setCheckable(True)
            other_btn.clicked.connect(lambda: self._on_brand_filter("other"))
            self._apply_btn_style(other_btn)
            self._brand_buttons["other"] = other_btn
            flow.addWidget(other_btn)

            card_layout.addLayout(flow)
            wrapper_layout.addWidget(card)

        return wrapper

    def _spec_label(self):
        spec_text = BodyLabel()
        spec_text.setText(
            "<b>格式规范</b><br>"
            "<b>品牌：</b>跟随品牌官方拼写习惯<br>"
            "  · 全大写：SONY、FUJIFILM<br>"
            "  · 首字母大写：Hasselblad<br>"
            "  · 标准拼写：Canon、Nikon<br>"
            "<b>型号：</b>跟随官方市场名称，而非 EXIF 内部编号<br>"
            "  · ILCE-7M3 → α7 III<br>"
            "  · X-HF1 → X Half<br>"
            "  · Canon EOS R5m2 → EOS R5 II<br>"
            "  · GFX100 II → GFX 100 II<br>"
            "  · NIKON Z 9 → Z9"
        )
        return spec_text

    def _add_bars(self, layout):
        # 相机页：搜索栏独立于筛选区，位于筛选区与操作条之间
        layout.addWidget(self._create_search_bar(
            "搜索原始品牌/型号或映射品牌/型号..."))
        layout.addWidget(self._create_action_bar())

    def _sort_key(self, row: dict):
        return (
            row.get('original_brand', '').lower(),
            row.get('original_model', '').lower(),
        )

    def _apply_filters(self, filtered: list) -> list:
        if self._active_brand:
            pattern = _BRAND_PATTERNS.get(self._active_brand)
            if self._active_brand == "other":
                filtered = [r for r in filtered
                            if not re.search(_OTHER_EXCLUDE, r.get('original_brand', ''), re.I)]
            elif pattern:
                filtered = [r for r in filtered
                            if re.search(pattern, r.get('original_brand', ''), re.I)]
        return filtered

    def _has_active_filters(self) -> bool:
        return super()._has_active_filters() or bool(self._active_brand)

    # ── 相机页自有交互 ──────────────────────────────────────

    def _on_brand_filter(self, key: str):
        btn = self._brand_buttons.get(key)
        if not btn:
            return

        if self._active_brand == key:
            self._active_brand = None
            btn.setChecked(False)
        else:
            if self._active_brand and self._active_brand in self._brand_buttons:
                self._brand_buttons[self._active_brand].setChecked(False)
            self._active_brand = key
            btn.setChecked(True)

        self._refresh_table()
