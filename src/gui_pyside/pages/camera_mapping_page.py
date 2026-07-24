# Copyright (c) 2026 FrankZhangCC
# MIT License - see LICENSE file for details

"""
相机映射管理页面

提供品牌筛选、搜索、可编辑表格管理相机品牌和型号的映射关系。
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

HEADERS = ["原始品牌", "原始型号", "映射品牌", "映射型号"]
COLUMNS = ["original_brand", "original_model", "mapped_brand", "mapped_model"]


class CameraMappingPage(QWidget):
    """相机映射管理页面"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._all_data: list[dict] = []
        self._filtered_data: list[dict] = []
        self._active_brand: str | None = None
        self._search_text: str = ''
        self._brand_buttons: dict[str, PushButton] = {}
        self._status_label: CaptionLabel | None = None

        self._load_data()
        self._setup_ui()

        logger.info("相机映射管理页面初始化完成，共 %d 条记录", len(self._all_data))

    def _load_data(self):
        dm = DeviceMapper()
        path = dm.camera_db_path
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

        title = StrongBodyLabel("相机映射管理")
        layout.addWidget(title)

        # 水平双栏：品牌筛选 (70%) | 格式规范 (30%)
        h_split = QWidget()
        h_layout = QHBoxLayout(h_split)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(8)

        h_layout.addWidget(self._create_brand_filter(), 7)

        spec_card = CardWidget()
        spec_card_layout = QVBoxLayout(spec_card)
        spec_card_layout.setContentsMargins(12, 6, 12, 6)
        spec_card_layout.setSpacing(0)

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
        spec_text.setWordWrap(True)
        spec_card_layout.addWidget(spec_text)
        h_layout.addWidget(spec_card, 3)

        layout.addWidget(h_split)
        layout.addWidget(self._create_search_bar())
        layout.addWidget(self._create_action_bar())
        self._create_data_table()
        layout.addWidget(self._table, stretch=1)

        scroll.setWidget(container)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _create_brand_filter(self) -> QWidget:
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
                btn.setStyleSheet("""
                    PushButton { padding: 3px 10px; border: 1px solid #d0d0d0;
                        border-radius: 4px; background-color: transparent; font-size: 13px; }
                    PushButton:hover { background-color: #e6f0fa; border-color: #0078d4; }
                    PushButton:checked { background-color: #0078d4; color: white; border-color: #0078d4; }
                """)
                self._brand_buttons[key] = btn
                flow.addWidget(btn)

            other_btn = PushButton("其它")
            other_btn.setCheckable(True)
            other_btn.clicked.connect(lambda: self._on_brand_filter("other"))
            other_btn.setStyleSheet("""
                PushButton { padding: 3px 10px; border: 1px solid #d0d0d0;
                    border-radius: 4px; background-color: transparent; font-size: 13px; }
                PushButton:hover { background-color: #e6f0fa; border-color: #0078d4; }
                PushButton:checked { background-color: #0078d4; color: white; border-color: #0078d4; }
            """)
            self._brand_buttons["other"] = other_btn
            flow.addWidget(other_btn)

            card_layout.addLayout(flow)
            wrapper_layout.addWidget(card)

        return wrapper

    def _create_search_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)

        self._search_input = LineEdit()
        self._search_input.setPlaceholderText("搜索原始品牌/型号或映射品牌/型号...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_search)
        self._search_input.setFixedWidth(400)
        layout.addWidget(self._search_input)

        self._status_label = CaptionLabel("")
        layout.addWidget(self._status_label)
        layout.addStretch()

        self._update_status_label()
        return bar

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

    def _on_search(self, text: str):
        self._search_text = text.strip()
        self._refresh_table()

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
        self._all_data.sort(
            key=lambda x: (
                x.get('original_brand', '').lower(),
                x.get('original_model', '').lower(),
            )
        )
        self._refresh_table()

    def _on_save(self):
        dm = DeviceMapper()
        path = dm.camera_db_path
        now = datetime.now().strftime('%Y/%m/%d %H:%M')
        fieldnames = ['original_brand', 'original_model', 'mapped_brand', 'mapped_model', 'timestamp']

        try:
            for row in self._all_data:
                if not row.get('timestamp'):
                    row['timestamp'] = now
                for col in fieldnames:
                    row.setdefault(col, '')

            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self._all_data)

            dm.refresh()
            InfoBar.success(title="保存成功", content=f"已保存 {len(self._all_data)} 条记录", parent=self)
            logger.info("相机映射已保存: %s", path)
        except Exception as e:
            InfoBar.error(title="保存失败", content=str(e), parent=self)
            logger.error("保存相机映射失败: %s", e)

    def _refresh_table(self):
        if not hasattr(self, '_table'):
            return
        filtered = self._all_data[:]

        if self._active_brand:
            pattern = _BRAND_PATTERNS.get(self._active_brand)
            if self._active_brand == "other":
                filtered = [r for r in filtered
                            if not re.search(_OTHER_EXCLUDE, r.get('original_brand', ''), re.I)]
            elif pattern:
                filtered = [r for r in filtered
                            if re.search(pattern, r.get('original_brand', ''), re.I)]

        if self._search_text:
            txt = self._search_text.lower()
            filtered = [
                r for r in filtered
                if any(txt in v.lower() for v in r.values() if isinstance(v, str))
            ]

        self._filtered_data = filtered
        self._populate_table()
        self._update_status_label()

    def _update_status_label(self):
        total = len(self._all_data)
        shown = len(self._filtered_data)
        if self._active_brand or self._search_text:
            self._status_label.setText(f"{total} 条记录，当前显示 {shown} 条")
        else:
            self._status_label.setText(f"全部品牌  |  {total} 条记录")

    def showEvent(self, event):
        """页面显示时刷新 CSV 数据"""
        super().showEvent(event)
        self._load_data()

    def cleanup(self):
        self._all_data.clear()
        self._filtered_data.clear()
        logger.debug("相机映射管理页面资源已清理")
