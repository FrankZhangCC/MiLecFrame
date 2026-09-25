"""
原图圆角区块

启用开关 + 四角独立半径系数
"""
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QGridLayout, QWidget
from PySide6.QtCore import Qt, Signal

from qfluentwidgets import (
    ExpandGroupSettingCard,
    DoubleSpinBox, SwitchButton, FluentIcon, BodyLabel, CaptionLabel,
)


class CornerRadiusSection(ExpandGroupSettingCard):
    """原图圆角配置区块"""

    value_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(
            FluentIcon.ADD_TO, '原图圆角 corner_radius',
            '启用开关 + 四角独立半径系数',
            parent=parent,
        )
        self._setup_ui()

    def _setup_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(8)

        # 启用
        row0 = QHBoxLayout()
        row0.addWidget(BodyLabel('启用圆角:', container))
        self.enabled_btn = SwitchButton(container)
        self.enabled_btn.checkedChanged.connect(self._on_changed)
        row0.addWidget(self.enabled_btn)
        row0.addStretch()
        layout.addLayout(row0)

        # 四角
        grid = QGridLayout()
        grid.setSpacing(6)

        self.tl_sb = self._make_spinbox(0.01, grid, 0, 0, 'top_left', parent=container)
        self.tr_sb = self._make_spinbox(0.01, grid, 0, 2, 'top_right', parent=container)
        self.bl_sb = self._make_spinbox(0.01, grid, 1, 0, 'bottom_left', parent=container)
        self.br_sb = self._make_spinbox(0.01, grid, 1, 2, 'bottom_right', parent=container)

        layout.addLayout(grid)

        hint = CaptionLabel(
            '半径系数 = 实际像素 / 原图短边；0.01 ≈ 短边的 1%')
        layout.addWidget(hint)

        self.addGroupWidget(container)

    def _make_spinbox(self, default, grid, row, col, label, parent=None):
        if parent is None:
            parent = self
        grid.addWidget(BodyLabel(label, parent), row, col)
        sb = DoubleSpinBox(parent)
        sb.setRange(0.0, 0.5)
        sb.setDecimals(3)
        sb.setSingleStep(0.005)
        sb.setValue(default)
        sb.valueChanged.connect(self._on_changed)
        grid.addWidget(sb, row, col + 1)
        return sb

    def _on_changed(self, *args):
        self.value_changed.emit()

    def load_from_model(self, data):
        self.enabled_btn.setChecked(data.cr_enabled)
        self.tl_sb.setValue(data.cr_tl)
        self.tr_sb.setValue(data.cr_tr)
        self.bl_sb.setValue(data.cr_bl)
        self.br_sb.setValue(data.cr_br)

    def save_to_model(self, data):
        data.cr_enabled = self.enabled_btn.isChecked()
        data.cr_tl = self.tl_sb.value()
        data.cr_tr = self.tr_sb.value()
        data.cr_bl = self.bl_sb.value()
        data.cr_br = self.br_sb.value()
