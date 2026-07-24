# Copyright (c) 2026 FrankZhangCC
# MIT License - see LICENSE file for details

"""
镜头映射管理页面

提供搜索、卡口/品牌筛选、可编辑表格管理镜头映射关系。
"""
import csv
import logging
import os
import re
from collections import defaultdict
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QHeaderView,
    QTableWidgetItem,
)

from qfluentwidgets import (
    PushButton, PrimaryPushButton,
    StrongBodyLabel, BodyLabel, CaptionLabel,
    CardWidget, TableWidget, LineEdit,
    InfoBar, FluentIcon, FlowLayout,
    SmoothScrollArea,
)

from src.utils.device_mapper import DeviceMapper

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

HEADERS = ["原始镜头", "映射镜头", "短版名称", "品牌", "卡口", "时间戳"]
COLUMNS = ["original_lens", "mapped_lens", "short_lens", "brand", "mount", "timestamp"]


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


class LensMappingPage(QWidget):
    """镜头映射管理页面"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._all_data: list[dict] = []
        self._filtered_data: list[dict] = []
        self._search_text: str = ''
        self._active_mount: str | None = None
        self._active_lens_brand: str | None = None

        self._mount_buttons: dict[str, PushButton] = {}
        self._brand_buttons: dict[str, PushButton] = {}
        self._status_label: CaptionLabel | None = None

        self._load_data()
        self._setup_ui()

        logger.info("镜头映射管理页面初始化完成，共 %d 条记录", len(self._all_data))

    def _load_data(self):
        dm = DeviceMapper()
        path = dm.lens_db_path
        self._all_data.clear()
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    clean = {k.strip(): v.strip() for k, v in row.items() if k}
                    self._all_data.append(clean)
        self._filtered_data = self._all_data[:]
        self._refresh_table()

    def _setup_ui(self):
        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = StrongBodyLabel("镜头映射管理")
        layout.addWidget(title)

        # 水平双栏：搜索+筛选 (70%) | 格式规范 (30%)
        h_split = QWidget()
        h_layout = QHBoxLayout(h_split)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(8)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        left_layout.addWidget(self._create_search_bar())

        mount_card = self._create_filter_card("卡口筛选", self._mount_buttons,
                                              LENS_MOUNT_RULES, self._on_mount_filter)
        left_layout.addWidget(mount_card)

        brand_card = self._create_filter_card("品牌筛选", self._brand_buttons,
                                              LENS_BRAND_RULES, self._on_lens_brand_filter)
        left_layout.addWidget(brand_card)

        h_layout.addWidget(left_panel, 7)

        spec_card = CardWidget()
        spec_card_layout = QVBoxLayout(spec_card)
        spec_card_layout.setContentsMargins(12, 6, 12, 6)
        spec_card_layout.setSpacing(0)

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
        spec_text.setWordWrap(True)
        spec_card_layout.addWidget(spec_text)
        h_layout.addWidget(spec_card, 3)

        layout.addWidget(h_split)

        layout.addWidget(self._create_action_bar())
        self._create_data_table()
        layout.addWidget(self._table, stretch=1)

        scroll.setWidget(container)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _create_search_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)

        self._search_input = LineEdit()
        self._search_input.setPlaceholderText("搜索原始镜头、映射镜头或短版名称...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_search)
        self._search_input.setFixedWidth(400)
        layout.addWidget(self._search_input)

        self._status_label = CaptionLabel("")
        layout.addWidget(self._status_label)
        layout.addStretch()

        self._update_status_label()
        return bar

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
        self._setup_btn_style(btn_all)
        buttons_dict["__all__"] = btn_all
        flow.addWidget(btn_all)

        for key, _, label in rules:
            btn = PushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, k=key: slot(k))
            self._setup_btn_style(btn)
            buttons_dict[key] = btn
            flow.addWidget(btn)

        card_layout.addLayout(flow)
        return card

    def _setup_btn_style(self, btn: PushButton):
        btn.setStyleSheet("""
            PushButton { padding: 3px 10px; border: 1px solid #d0d0d0;
                border-radius: 4px; background-color: transparent; font-size: 13px; }
            PushButton:hover { background-color: #e6f0fa; border-color: #0078d4; }
            PushButton:checked { background-color: #0078d4; color: white; border-color: #0078d4; }
        """)

    def _create_action_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        btn_add = PushButton(FluentIcon.ADD, "添加行")
        btn_add.clicked.connect(self._on_add_row)
        layout.addWidget(btn_add)

        btn_delete = PushButton(FluentIcon.DELETE, "删除选中行")
        btn_delete.clicked.connect(self._on_delete_row)
        layout.addWidget(btn_delete)

        btn_sort = PushButton("排序整理")
        btn_sort.clicked.connect(self._on_sort)
        layout.addWidget(btn_sort)

        btn_refresh = PushButton(FluentIcon.SYNC, "刷新")
        btn_refresh.clicked.connect(self._load_data)
        layout.addWidget(btn_refresh)

        layout.addStretch()

        btn_save = PrimaryPushButton(FluentIcon.SAVE, "保存更改")
        btn_save.clicked.connect(self._on_save)
        layout.addWidget(btn_save)

        return bar

    def _create_data_table(self):
        self._table = TableWidget(self)
        self._table.setColumnCount(len(HEADERS))
        self._table.setHorizontalHeaderLabels(HEADERS)
        self._table.setBorderVisible(True)
        self._table.setBorderRadius(8)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(True)
        self._table.setSelectionBehavior(self._table.SelectionBehavior.SelectRows)
        self._table.itemChanged.connect(self._on_table_item_changed)

        self._populate_table()

    def _populate_table(self):
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._filtered_data))
        for row, record in enumerate(self._filtered_data):
            for col, col_name in enumerate(COLUMNS):
                self._table.setItem(row, col, QTableWidgetItem(record.get(col_name, '')))
        self._table.blockSignals(False)

    def _on_table_item_changed(self, item: QTableWidgetItem):
        row, col = item.row(), item.column()
        if 0 <= row < len(self._filtered_data) and 0 <= col < len(COLUMNS):
            self._filtered_data[row][COLUMNS[col]] = item.text()

    def _on_search(self, text: str):
        self._search_text = text.strip()
        self._refresh_table()

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

    def _on_add_row(self):
        new_row = defaultdict(str)
        self._all_data.append(new_row)
        self._refresh_table()
        last_row = len(self._filtered_data) - 1
        if last_row >= 0:
            self._table.scrollToItem(self._table.item(last_row, 0))

    def _on_delete_row(self):
        indexes = self._table.selectedIndexes()
        if not indexes:
            InfoBar.warning(title="提示", content="请先选中要删除的行", parent=self)
            return

        rows = sorted(set(idx.row() for idx in indexes), reverse=True)
        for row in rows:
            if row < len(self._filtered_data):
                target = self._filtered_data[row]
                if target in self._all_data:
                    self._all_data.remove(target)

        self._refresh_table()
        InfoBar.success(title="已删除", content=f"已删除 {len(rows)} 行", parent=self)

    def _on_sort(self):
        self._all_data.sort(key=lambda x: x.get('original_lens', '').lower())
        self._refresh_table()

    def _on_save(self):
        dm = DeviceMapper()
        path = dm.lens_db_path
        now = datetime.now().strftime('%Y/%m/%d %H:%M')
        fieldnames = ['original_lens', 'mapped_lens', 'short_lens', 'brand', 'mount', 'timestamp']

        try:
            for row in self._all_data:
                for col in fieldnames:
                    row.setdefault(col, '')
                if not row.get('timestamp'):
                    row['timestamp'] = now

            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self._all_data)

            dm.refresh()
            InfoBar.success(title="保存成功", content=f"已保存 {len(self._all_data)} 条记录", parent=self)
            logger.info("镜头映射已保存: %s", path)
        except Exception as e:
            InfoBar.error(title="保存失败", content=str(e), parent=self)
            logger.error("保存镜头映射失败: %s", e)

    def _refresh_table(self):
        if not hasattr(self, '_table'):
            return
        filtered = self._all_data[:]

        if self._search_text:
            txt = self._search_text.lower()
            filtered = [
                r for r in filtered
                if any(txt in v.lower() for v in r.values() if isinstance(v, str))
            ]

        if self._active_mount:
            filtered = [r for r in filtered if _row_has_mount(r, self._active_mount)]

        if self._active_lens_brand:
            filtered = [r for r in filtered if _detect_lens_brand_key(r) == self._active_lens_brand]

        self._filtered_data = filtered
        self._populate_table()
        self._update_status_label()

    def _update_status_label(self):
        total = len(self._all_data)
        shown = len(self._filtered_data)
        if self._active_mount or self._active_lens_brand or self._search_text:
            self._status_label.setText(f"{total} 条记录，当前显示 {shown} 条")
        else:
            self._status_label.setText(f"全部镜头  |  {total} 条记录")

    def showEvent(self, event):
        """页面显示时刷新 CSV 数据"""
        super().showEvent(event)
        self._load_data()

    def cleanup(self):
        self._all_data.clear()
        self._filtered_data.clear()
        logger.debug("镜头映射管理页面资源已清理")
