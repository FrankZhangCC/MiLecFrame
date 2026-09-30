# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
镜头映射管理页面

提供搜索、卡口/品牌筛选、可编辑表格管理镜头映射关系。
页面骨架（加载/搜索/表格/增删/保存/刷新）由 CsvMappingPage 基类
提供（G7），本类只保留镜头页的扩展点：卡口/品牌双维筛选、格式
规范文案、排序键与筛选逻辑。
"""
import logging
import re

from PySide6.QtWidgets import QVBoxLayout, QWidget

from qfluentwidgets import (
    PushButton, BodyLabel, CaptionLabel, CardWidget, FlowLayout,
)

from .csv_mapping_page import CsvMappingPage

logger = logging.getLogger(__name__)

# ── 镜头卡口检测规则 ──
LENS_MOUNT_RULES = [
    ("RF", r'^RF', "RF (佳能无反)"),
    ("EF", r'^EF', "EF (佳能单反)"),
    ("FE", r'^FE\s', "FE (索尼全幅)"),
    ("E", r'^E\s\d', "E (索尼C幅)"),
    ("GF", r'^GF', "GF (富士中画幅)"),
    ("X", r'^X[FC]', "X (富士全幅)"),
    ("XCD", r'^XCD', "XCD (哈苏)"),
    ("Z", r'^NIKKOR Z', "Z (尼康无反)"),
    ("F", r'^NIKKOR\s(?!Z)', "F (尼康单反)"),
    ("L", r'[Ll]\s?[Mm]ount', "L (马徕松联盟)"),
]

# ── 镜头品牌检测规则 ──
LENS_BRAND_RULES = [
    ("canon",     r'\bCanon\b',                    "Canon | 佳能"),
    ("sony",      r'\bSony\b|\bSONY\b',            "Sony | 索尼"),
    ("fujifilm",  r'\bFujifilm\b|\bFUJIFILM\b',   "FUJIFILM | 富士"),
    ("nikon",     r'\bNikon\b|\bNIKKOR\b',         "Nikon | 尼康"),
    ("panasonic", r'\bPanasonic\b',                "Panasonic | 松下"),
    ("leica",     r'\bLeica\b',                    "Leica | 徕卡"),
    ("hasselblad",r'\bHasselblad\b',               "Hasselblad | 哈苏"),
    ("sigma",     r'SIGMA|Sigma|σ',                "SIGMA | 适马"),
    ("tamron",    r'TAMRON|Tamron',                "TAMRON | 腾龙"),
]


def _detect_lens_mount_key(row: dict) -> str | None:
    """检测镜头所属的卡口 key

    优先读取 mount 列的值（多卡口以逗号分隔），
    若无则回退到正则匹配 original_lens 的前缀。
    """
    mount_col = row.get('mount', '').strip()
    if mount_col:
        return mount_col
    original = row.get('original_lens', '')
    for key, pattern, _ in LENS_MOUNT_RULES:
        if re.search(pattern, original):
            return key
    return None


def _row_has_mount(row: dict, target: str) -> bool:
    """检查行是否包含指定卡口（支持 mount 列逗号分隔多值）"""
    mount_col = row.get('mount', '').strip()
    if mount_col:
        mounts = [m.strip() for m in mount_col.split(',')]
        if target in mounts:
            return True
        return False
    return _detect_lens_mount_key(row) == target


def _detect_lens_brand_key(row: dict) -> str | None:
    """检测镜头所属的品牌 key

    优先读取 brand 列的值，
    若无则回退到正则匹配 mapped_lens/original_lens 文本。
    """
    brand_col = row.get('brand', '').strip()
    if brand_col:
        return brand_col.lower()
    original = row.get('original_lens', '')
    mapped = row.get('mapped_lens', '')
    combined = f"{original} {mapped}"
    for key, pattern, _ in LENS_BRAND_RULES:
        if re.search(pattern, combined, re.I):
            return key
    return None


class LensMappingPage(CsvMappingPage):
    """镜头映射管理页面"""

    TITLE = "镜头映射管理"
    ALL_LABEL = "全部镜头"
    LOG_NAME = "镜头映射"
    HEADERS = ["原始镜头", "映射镜头", "短版名称", "品牌", "卡口", "时间戳"]
    COLUMNS = ["original_lens", "mapped_lens", "short_lens", "brand", "mount", "timestamp"]
    SAVE_FIELDNAMES = ['original_lens', 'mapped_lens', 'short_lens', 'brand', 'mount', 'timestamp']
    DB_PATH_ATTR = 'lens_db_path'

    def __init__(self, parent=None):
        self._active_mount: str | None = None
        self._active_lens_brand: str | None = None
        self._mount_buttons: dict[str, PushButton] = {}
        self._brand_buttons: dict[str, PushButton] = {}
        super().__init__(parent)

    # ── 基类扩展点 ──────────────────────────────────────────

    def _create_filter_card(self, title_text: str, buttons_dict: dict,
                            rules: list, slot) -> QWidget:
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 8, 16, 8)
        card_layout.setSpacing(6)

        group_title = CaptionLabel(title_text)
        group_title.setStyleSheet("font-size: 12px; color: #666;")
        card_layout.addWidget(group_title)

        flow = FlowLayout()
        flow.setSpacing(4)

        btn_all = PushButton("全部")
        btn_all.setCheckable(True)
        btn_all.setChecked(True)
        btn_all.clicked.connect(lambda: slot(None))
        self._apply_btn_style(btn_all)
        buttons_dict["__all__"] = btn_all
        flow.addWidget(btn_all)

        for key, _, label in rules:
            btn = PushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, k=key: slot(k))
            self._apply_btn_style(btn)
            buttons_dict[key] = btn
            flow.addWidget(btn)

        card_layout.addLayout(flow)
        return card

    def _create_filter_area(self) -> QWidget:
        # 镜头页：搜索栏在左栏内、双筛选卡之上（与相机页位置差异）
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        left_layout.addWidget(self._create_search_bar(
            "搜索原始镜头、映射镜头或短版名称..."))

        mount_card = self._create_filter_card("卡口筛选", self._mount_buttons,
                                              LENS_MOUNT_RULES, self._on_mount_filter)
        left_layout.addWidget(mount_card)

        brand_card = self._create_filter_card("品牌筛选", self._brand_buttons,
                                              LENS_BRAND_RULES, self._on_lens_brand_filter)
        left_layout.addWidget(brand_card)

        return left_panel

    def _spec_label(self):
        spec_text = BodyLabel()
        spec_text.setText(
            "<b>格式规范</b><br>"
            "<b>完整映射名：</b>跟随品牌官方市场名称拼写<br>"
            "<b>短版映射名：</b>保留焦距和光圈信息<br>"
            "  · 原厂镜头：保留系列/定位标识，去掉防抖/马达/镀膜描述<br>"
            "    例：Z 85mm f/1.8 S、FE 85mm F1.4 GM<br>"
            "  · 副厂镜头：不保留品牌和卡口，仅保留焦距和光圈<br>"
            "    例：100-400mm F5-6.3、28-200mm F2.8-5.6"
        )
        return spec_text

    def _add_bars(self, layout):
        # 镜头页：搜索栏已在筛选区内，这里只加操作条
        layout.addWidget(self._create_action_bar())

    def _sort_key(self, row: dict):
        return row.get('original_lens', '').lower()

    def _apply_filters(self, filtered: list) -> list:
        if self._active_mount:
            filtered = [r for r in filtered if _row_has_mount(r, self._active_mount)]

        if self._active_lens_brand:
            filtered = [r for r in filtered if _detect_lens_brand_key(r) == self._active_lens_brand]
        return filtered

    def _has_active_filters(self) -> bool:
        return (super()._has_active_filters()
                or bool(self._active_mount)
                or bool(self._active_lens_brand))

    # ── 镜头页自有交互 ──────────────────────────────────────

    def _on_mount_filter(self, key: str | None):
        if key is None:
            self._active_mount = None
        elif self._active_mount == key:
            self._active_mount = None
        else:
            self._active_mount = key
        self._sync_filter_buttons(self._mount_buttons, self._active_mount)
        self._refresh_table()

    def _on_lens_brand_filter(self, key: str | None):
        if key is None:
            self._active_lens_brand = None
        elif self._active_lens_brand == key:
            self._active_lens_brand = None
        else:
            self._active_lens_brand = key
        self._sync_filter_buttons(self._brand_buttons, self._active_lens_brand)
        self._refresh_table()

    def _sync_filter_buttons(self, buttons: dict, active_key: str | None):
        for k, btn in buttons.items():
            if k == "__all__":
                btn.setChecked(active_key is None)
            else:
                btn.setChecked(k == active_key)
