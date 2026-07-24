"""
安全区域区块

四边 padding 比例设置
"""
from PySide6.QtWidgets import QGridLayout, QWidget
from PySide6.QtCore import Qt, Signal

from qfluentwidgets import (
    ExpandGroupSettingCard,
    DoubleSpinBox, FluentIcon, BodyLabel,
)


class PaddingSection(ExpandGroupSettingCard):
    """安全区域配置区块"""

    value_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(
            FluentIcon.ALIGNMENT, '安全区域 padding',
            '从画布边缘向内收缩比例',
            parent=parent,
        )
        self._setup_ui()

    def _setup_ui(self):
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(6)

        self.top_sb = self._make_spinbox(0.02, grid, 0, 0, 'top', parent=container)
        self.bottom_sb = self._make_spinbox(0.02, grid, 0, 2, 'bottom', parent=container)
        self.left_sb = self._make_spinbox(0.02, grid, 1, 0, 'left', parent=container)
        self.right_sb = self._make_spinbox(0.02, grid, 1, 2, 'right', parent=container)

        self.addGroupWidget(container)

    def _make_spinbox(self, default, grid, row, col, label, parent=None):
        if parent is None:
            parent = self
        grid.addWidget(BodyLabel(label, parent), row, col)
        sb = DoubleSpinBox(parent)
        sb.setRange(0.0, 1.0)
        sb.setDecimals(3)
        sb.setSingleStep(0.005)
        sb.setValue(default)
        sb.valueChanged.connect(self._on_changed)
        grid.addWidget(sb, row, col + 1)
        return sb

    def _on_changed(self, *args):
        self.value_changed.emit()

    def load_from_model(self, data):
        self.top_sb.setValue(data.pad_top)
        self.bottom_sb.setValue(data.pad_bottom)
        self.left_sb.setValue(data.pad_left)
        self.right_sb.setValue(data.pad_right)

    def save_to_model(self, data):
        data.pad_top = self.top_sb.value()
        data.pad_bottom = self.bottom_sb.value()
        data.pad_left = self.left_sb.value()
        data.pad_right = self.right_sb.value()
