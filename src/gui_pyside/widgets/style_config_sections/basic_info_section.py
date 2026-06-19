"""
基本信息区块

样式名称 + 文件名输入
"""
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from PySide6.QtCore import Qt, Signal

from qfluentwidgets import (
    ExpandGroupSettingCard,
    LineEdit, FluentIcon, BodyLabel,
)


class BasicInfoSection(ExpandGroupSettingCard):
    """基本信息配置区块"""

    value_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(
            FluentIcon.INFO, '基本信息',
            '样式名称 + 文件名输入',
            parent=parent,
        )
        self._setup_ui()

    def _setup_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(8)

        # 样式名称
        row1 = QHBoxLayout()
        row1.addWidget(BodyLabel('样式名称 (name):', container))
        self.name_edit = LineEdit(container)
        self.name_edit.setPlaceholderText('如: 宝丽来风格 Polaroid')
        self.name_edit.textChanged.connect(self._on_changed)
        row1.addWidget(self.name_edit, stretch=1)
        layout.addLayout(row1)

        # 文件名
        row2 = QHBoxLayout()
        row2.addWidget(BodyLabel('文件名:', container))
        self.filename_edit = LineEdit(container)
        self.filename_edit.setPlaceholderText('如: Polaroid.yaml')
        self.filename_edit.textChanged.connect(self._on_changed)
        row2.addWidget(self.filename_edit, stretch=1)
        layout.addLayout(row2)

        self.addGroupWidget(container)

    def _on_changed(self, *args):
        self.value_changed.emit()

    def load_from_model(self, data):
        self.name_edit.setText(data.name)
        self.filename_edit.setText(data.filename)

    def save_to_model(self, data):
        data.name = self.name_edit.text().strip()
        data.filename = self.filename_edit.text().strip()
