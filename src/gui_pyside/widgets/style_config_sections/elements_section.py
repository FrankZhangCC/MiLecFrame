"""
元素布局区块

动态列表管理 info_position 元素，
每个条目含 key + 定位参数（使用 element_editor 组件）
"""
import logging

from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt, Signal, QTimer

from qfluentwidgets import (
    ExpandGroupSettingCard,
    PushButton, FluentIcon, BodyLabel,
)

from src.gui_pyside.widgets.element_editor import ElementEditor
from ...models.style_config_form import (
    ElementConfig, _next_element_id,
)

logger = logging.getLogger(__name__)


class ElementsSection(ExpandGroupSettingCard):
    """元素布局配置区块"""

    value_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(
            FluentIcon.LAYOUT, '元素布局 info_position',
            '仅配置驱动：在此声明的元素才会渲染',
            parent=parent,
        )
        self._items: list[dict] = []
        self._setup_ui()

    def _setup_ui(self):
        container = QWidget()
        self._content_widget = container
        layout = QVBoxLayout(container)
        layout.setSpacing(8)

        self._container = QVBoxLayout()
        layout.addLayout(self._container)

        add_btn = PushButton(
            FluentIcon.ADD, '添加元素', container)
        add_btn.clicked.connect(self._on_add)
        layout.addWidget(add_btn)

        self.addGroupWidget(container)

    def _on_add(self):
        """添加新元素"""
        elem = ElementConfig(
            id=_next_element_id(
                [x['item'] for x in self._items]),
            key='camera_lens',
        )
        self._add_item_widget(elem)

    def _add_item_widget(self, elem: ElementConfig):
        """为给定元素创建 UI 控件"""
        from PySide6.QtWidgets import QFrame

        frame = QFrame(self._content_widget)
        frame.setStyleSheet(
            "QFrame { border: 1px solid #e0e0e0;"
            " border-radius: 6px; padding: 8px; }")
        vbox = QVBoxLayout(frame)
        vbox.setSpacing(6)

        # 删除按钮
        top_row = QHBoxLayout()
        del_btn = PushButton(
            FluentIcon.DELETE, '删除', frame)
        del_btn.clicked.connect(
            lambda: self._on_delete(frame))
        top_row.addStretch()
        top_row.addWidget(del_btn)
        vbox.addLayout(top_row)

        # 定位编辑器（显示 key 选择器）
        editor = ElementEditor(frame, show_key_selector=True)
        editor.load_element(elem)
        editor.changed.connect(self._on_changed)
        vbox.addWidget(editor)

        # 存储
        record = {
            'frame': frame,
            'item': elem,
            'editor': editor,
        }
        self._items.append(record)
        self._container.addWidget(frame)
        self._on_changed()
        QTimer.singleShot(0, self._adjustViewSize)

    def _on_delete(self, frame):
        """删除元素"""
        for i, rec in enumerate(self._items):
            if rec['frame'] is frame:
                self._items.pop(i)
                self._container.removeWidget(frame)
                frame.deleteLater()
                self._on_changed()
                QTimer.singleShot(0, self._adjustViewSize)
                return

    def _on_changed(self, *args):
        self.value_changed.emit()

    def get_items(self) -> list[ElementConfig]:
        """收集所有元素数据"""
        result = []
        for rec in self._items:
            item = rec['item']
            rec['editor'].save_element(item)
            result.append(item)
        return result

    def set_items(self, items: list[ElementConfig]):
        """设置元素数据"""
        for rec in self._items:
            self._container.removeWidget(rec['frame'])
            rec['frame'].deleteLater()
        self._items.clear()
        for item in items:
            self._add_item_widget(item)

    def load_from_model(self, data):
        self.set_items(data.elements)

    def save_to_model(self, data):
        data.elements = self.get_items()
