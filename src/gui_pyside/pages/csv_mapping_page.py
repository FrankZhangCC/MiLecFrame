# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
CSV 映射管理页基类（G7：相机/镜头映射页公共骨架单点化）

两页原先各自复制约 250 行的加载/搜索/表格/增删/保存/刷新逻辑
（非字节级，存在字段、排序键、筛选维度差异）。本基类把完全一致的
部分单点化，差异以显式扩展点参数化，子类保留各自的筛选规则与文案。

扩展点（子类显式提供）：
  - TITLE / ALL_LABEL / LOG_NAME：标题、状态栏"全部"文案、保存日志名
  - HEADERS / COLUMNS / SAVE_FIELDNAMES：表头、数据列、保存字段
  - DB_PATH_ATTR：DeviceMapper 上的数据库路径属性名
  - _create_filter_area()：页首左栏筛选区构建（含各自搜索栏位置）
  - _spec_text()：右侧"格式规范"HTML 文案
  - _add_bars(layout)：筛选区与表格之间的操作条（搜索栏位置差异）
  - _sort_key(row)：排序整理的键函数
  - _apply_filters(filtered)：搜索之外的维度筛选
  - _has_active_filters()：状态栏"筛选中/全部"判定

初始化顺序显式设计：先 _setup_ui() 再 _load_data()——表格先于数据
存在，_refresh_table 不再需要 hasattr 守卫（G11 守卫的根治）。
按钮 QSS 未做 dark 适配，保持历史视觉原样（单点收敛，不顺手改）。
"""
import csv
import logging
import os
from collections import defaultdict
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QHeaderView,
    QTableWidgetItem,
)

from qfluentwidgets import (
    PushButton, PrimaryPushButton,
    StrongBodyLabel, CaptionLabel,
    CardWidget, TableWidget, LineEdit,
    InfoBar, FluentIcon,
    SmoothScrollArea,
)

from src.utils.device_mapper import DeviceMapper

logger = logging.getLogger(__name__)


class CsvMappingPage(QWidget):
    """CSV 映射管理页基类"""

    TITLE = ''
    ALL_LABEL = ''
    LOG_NAME = ''
    HEADERS: list = []
    COLUMNS: list = []
    SAVE_FIELDNAMES: list = []
    DB_PATH_ATTR = ''

    # 筛选按钮 QSS 单点（历史视觉原样：未做 dark 适配，另行处理）
    _BTN_QSS = """
        PushButton { padding: 3px 10px; border: 1px solid #d0d0d0;
            border-radius: 4px; background-color: transparent; font-size: 13px; }
        PushButton:hover { background-color: #e6f0fa; border-color: #0078d4; }
        PushButton:checked { background-color: #0078d4; color: white; border-color: #0078d4; }
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._all_data: list[dict] = []
        self._filtered_data: list[dict] = []
        self._search_text: str = ''
        self._status_label: CaptionLabel | None = None

        # G7 初始化顺序统一：先建 UI（表格存在）再加载数据，
        # _refresh_table 首次调用时 _table 已就绪，无需守卫
        self._setup_ui()
        self._load_data()

        logger.info("%s初始化完成，共 %d 条记录", self.TITLE, len(self._all_data))

    # ── UI 构建 ─────────────────────────────────────────────

    def _setup_ui(self):
        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel(self.TITLE))

        # 水平双栏：筛选区 (70%) | 格式规范 (30%)
        h_split = QWidget()
        h_layout = QHBoxLayout(h_split)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(8)

        h_layout.addWidget(self._create_filter_area(), 7)

        spec_card = CardWidget()
        spec_card_layout = QVBoxLayout(spec_card)
        spec_card_layout.setContentsMargins(12, 6, 12, 6)
        spec_card_layout.setSpacing(0)

        spec_text = self._spec_label()
        spec_text.setWordWrap(True)
        spec_card_layout.addWidget(spec_text)
        h_layout.addWidget(spec_card, 3)

        layout.addWidget(h_split)

        self._add_bars(layout)
        self._create_data_table()
        layout.addWidget(self._table, stretch=1)

        scroll.setWidget(container)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _spec_label(self):
        """右侧"格式规范"标签（子类提供文案）"""
        raise NotImplementedError

    def _create_filter_area(self) -> QWidget:
        """页首左栏筛选区（子类构建各自的筛选卡）"""
        raise NotImplementedError

    def _add_bars(self, layout):
        """筛选区与表格之间的操作条（搜索栏位置差异由子类决定）"""
        raise NotImplementedError

    def _apply_btn_style(self, btn: PushButton):
        btn.setStyleSheet(self._BTN_QSS)

    def _create_search_bar(self, placeholder: str) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)

        self._search_input = LineEdit()
        self._search_input.setPlaceholderText(placeholder)
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
        self._table.setColumnCount(len(self.HEADERS))
        self._table.setHorizontalHeaderLabels(self.HEADERS)
        self._table.setBorderVisible(True)
        self._table.setBorderRadius(8)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(True)
        self._table.setSelectionBehavior(self._table.SelectionBehavior.SelectRows)
        self._table.itemChanged.connect(self._on_table_item_changed)

        self._populate_table()

    # ── 数据加载与保存 ──────────────────────────────────────

    def _load_data(self):
        dm = DeviceMapper()
        path = getattr(dm, self.DB_PATH_ATTR)
        self._all_data.clear()
        if os.path.exists(path):
            # utf-8-sig 读：自动剥离 BOM，兼容有/无 BOM 两种历史文件
            with open(path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    clean = {k.strip(): v.strip() for k, v in row.items() if k}
                    self._all_data.append(clean)
        self._filtered_data = self._all_data[:]
        self._refresh_table()

    def _on_save(self):
        dm = DeviceMapper()
        path = getattr(dm, self.DB_PATH_ATTR)
        now = datetime.now().strftime('%Y/%m/%d %H:%M')

        try:
            for row in self._all_data:
                if not row.get('timestamp'):
                    row['timestamp'] = now
                for col in self.SAVE_FIELDNAMES:
                    row.setdefault(col, '')

            # utf-8-sig 写：写出 BOM，保证 Excel 直接打开不乱码
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=self.SAVE_FIELDNAMES)
                writer.writeheader()
                writer.writerows(self._all_data)

            dm.refresh()
            InfoBar.success(title="保存成功", content=f"已保存 {len(self._all_data)} 条记录", parent=self)
            logger.info("%s已保存: %s", self.LOG_NAME, path)
        except Exception as e:
            InfoBar.error(title="保存失败", content=str(e), parent=self)
            logger.error("保存%s失败: %s", self.LOG_NAME, e)

    # ── 表格与行操作 ────────────────────────────────────────

    def _populate_table(self):
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._filtered_data))
        for row, record in enumerate(self._filtered_data):
            for col, col_name in enumerate(self.COLUMNS):
                self._table.setItem(row, col, QTableWidgetItem(record.get(col_name, '')))
        self._table.blockSignals(False)

    def _on_table_item_changed(self, item: QTableWidgetItem):
        row, col = item.row(), item.column()
        if 0 <= row < len(self._filtered_data) and 0 <= col < len(self.COLUMNS):
            self._filtered_data[row][self.COLUMNS[col]] = item.text()

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
        self._all_data.sort(key=self._sort_key)
        self._refresh_table()

    # ── 筛选与刷新 ──────────────────────────────────────────

    def _refresh_table(self):
        filtered = self._all_data[:]

        if self._search_text:
            txt = self._search_text.lower()
            filtered = [
                r for r in filtered
                if any(txt in v.lower() for v in r.values() if isinstance(v, str))
            ]

        filtered = self._apply_filters(filtered)

        self._filtered_data = filtered
        self._populate_table()
        self._update_status_label()

    def _apply_filters(self, filtered: list) -> list:
        """搜索之外的维度筛选（子类实现；默认原样返回）"""
        return filtered

    def _has_active_filters(self) -> bool:
        """状态栏"筛选中/全部"判定（子类叠加各自维度）"""
        return bool(self._search_text)

    def _update_status_label(self):
        total = len(self._all_data)
        shown = len(self._filtered_data)
        if self._has_active_filters():
            self._status_label.setText(f"{total} 条记录，当前显示 {shown} 条")
        else:
            self._status_label.setText(f"{self.ALL_LABEL}  |  {total} 条记录")

    def _sort_key(self, row: dict):
        """排序整理的键函数（子类实现）"""
        raise NotImplementedError

    # ── 生命周期 ────────────────────────────────────────────

    def showEvent(self, event):
        """页面显示时刷新 CSV 数据"""
        super().showEvent(event)
        self._load_data()

    def cleanup(self):
        self._all_data.clear()
        self._filtered_data.clear()
        logger.debug("%s资源已清理", self.TITLE)
