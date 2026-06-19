"""
预定义文本区块

动态列表管理，每个条目含 key/content/定位参数
"""
import logging

from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt, Signal, QTimer

from qfluentwidgets import (
    ExpandGroupSettingCard,
    LineEdit, PushButton, FluentIcon,
    BodyLabel, CaptionLabel,
)

from src.gui_pyside.widgets.element_editor import ElementEditor
from ...models.style_config_form import (
    DefinedTextConfig, _next_element_id,
)

logger = logging.getLogger(__name__)


class DefinedTextsSection(ExpandGroupSettingCard):
    """预定义文本配置区块"""

    value_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(
            FluentIcon.ALIGNMENT, '预定义文本 defined_texts',
            '固定内容文本，key 建议补零编号（如 defined_text_01）',
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
            FluentIcon.ADD, '添加预定义文本', container)
        add_btn.clicked.connect(self._on_add)
        layout.addWidget(add_btn)

        self.addGroupWidget(container)

    def _on_add(self):
        """添加新条目"""
        item = DefinedTextConfig(
            id=_next_element_id(
                [x['item'] for x in self._items]),
            key='',
            content='',
        )
        self._add_item_widget(item)

    def _add_item_widget(self, item: DefinedTextConfig):
        """为给定条目创建 UI 控件"""
        from PySide6.QtWidgets import QFrame

        frame = QFrame(self._content_widget)
        frame.setStyleSheet(
            "QFrame { border: 1px solid #e0e0e0;"
            " border-radius: 6px; padding: 8px; }")
        vbox = QVBoxLayout(frame)
        vbox.setSpacing(6)

        # 顶栏：key 输入 + 删除按钮
        top_row = QHBoxLayout()
        top_row.addWidget(BodyLabel('Key:'))
        key_edit = LineEdit(frame)
        key_edit.setText(item.key)
        key_edit.setPlaceholderText('defined_text_01')
        key_edit.textChanged.connect(self._on_changed)
        top_row.addWidget(key_edit, stretch=1)

        del_btn = PushButton(
            FluentIcon.DELETE, '删除', frame)
        del_btn.clicked.connect(
            lambda: self._on_delete(frame))
        top_row.addWidget(del_btn)
        vbox.addLayout(top_row)

        # 内容
        content_row = QHBoxLayout()
        content_row.addWidget(BodyLabel('content:'))
        content_edit = LineEdit(frame)
        content_edit.setText(item.content)
        content_edit.setPlaceholderText('如: "FL"')
        content_edit.textChanged.connect(self._on_changed)
        content_row.addWidget(content_edit, stretch=1)
        vbox.addLayout(content_row)

        # 定位编辑器（不显示 key 选择器）
        editor = ElementEditor(frame, show_key_selector=False)
        editor.load_defined_text(item)
        editor.changed.connect(self._on_changed)
        vbox.addWidget(editor)

        # 存储
        record = {
            'frame': frame,
            'item': item,
            'key_edit': key_edit,
            'content_edit': content_edit,
            'editor': editor,
        }
        self._items.append(record)
        self._container.addWidget(frame)
        self._on_changed()
        QTimer.singleShot(0, self._adjustViewSize)

    def _on_delete(self, frame):
        """删除条目"""
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

    def get_items(self) -> list[DefinedTextConfig]:
        """收集所有条目数据"""
        result = []
        for rec in self._items:
            item = rec['item']
            item.key = rec['key_edit'].text().strip()
            item.content = rec['content_edit'].text().strip()
            rec['editor'].save_defined_text(item)
            if item.key:
                result.append(item)
        return result

    def set_items(self, items: list[DefinedTextConfig]):
        """设置条目数据"""
        # 清空现有
        for rec in self._items:
            self._container.removeWidget(rec['frame'])
            rec['frame'].deleteLater()
        self._items.clear()

        # 添加新
        for item in items:
            self._add_item_widget(item)

    def load_from_model(self, data):
        self.set_items(data.defined_texts)

    def save_to_model(self, data):
        data.defined_texts = self.get_items()
