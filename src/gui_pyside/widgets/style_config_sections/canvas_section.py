"""
画布扩展区块

启用开关 + 四边扩展比例设置
"""
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QGridLayout, QWidget
from PySide6.QtCore import Qt, Signal

from qfluentwidgets import (
    ExpandGroupSettingCard,
    DoubleSpinBox, SwitchButton, FluentIcon, BodyLabel,
)


class CanvasSection(ExpandGroupSettingCard):
    """画布扩展配置区块"""

    value_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(
            FluentIcon.FIT_PAGE, '画布扩展 expand_canvas',
            '启用开关 + 四边扩展比例设置',
            parent=parent,
        )
        self._setup_ui()

    def _setup_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(8)

        # 启用开关
        row0 = QHBoxLayout()
        row0.addWidget(BodyLabel('启用画布扩展:', container))
        self.enabled_btn = SwitchButton(container)
        self.enabled_btn.setChecked(True)
        self.enabled_btn.checkedChanged.connect(self._on_changed)
        row0.addWidget(self.enabled_btn)
        row0.addStretch()
        layout.addLayout(row0)

        # 四边比例
        grid = QGridLayout()
        grid.setSpacing(6)

        self.top_sb = self._make_spinbox(0.03, grid, 0, 0, 'top', parent=container)
        self.bottom_sb = self._make_spinbox(0.12, grid, 0, 2, 'bottom', parent=container)
        self.left_sb = self._make_spinbox(0.02, grid, 1, 0, 'left', parent=container)
        self.right_sb = self._make_spinbox(0.02, grid, 1, 2, 'right', parent=container)

        layout.addLayout(grid)

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
        self.enabled_btn.setChecked(data.canvas_enabled)
        self.top_sb.setValue(data.canvas_top)
        self.bottom_sb.setValue(data.canvas_bottom)
        self.left_sb.setValue(data.canvas_left)
        self.right_sb.setValue(data.canvas_right)

    def save_to_model(self, data):
        data.canvas_enabled = self.enabled_btn.isChecked()
        data.canvas_top = self.top_sb.value()
        data.canvas_bottom = self.bottom_sb.value()
        data.canvas_left = self.left_sb.value()
        data.canvas_right = self.right_sb.value()
