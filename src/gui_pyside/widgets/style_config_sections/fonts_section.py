"""
字体配置区块

Latin/CJK 字体、字重、系统字体开关、全局尺寸、行间距、元素独立尺寸
"""
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QGridLayout, QWidget,
)
from PySide6.QtCore import Qt, Signal

from qfluentwidgets import (
    ExpandGroupSettingCard,
    ComboBox, LineEdit, DoubleSpinBox, SwitchButton,
    FluentIcon, BodyLabel,
)

from ...models.style_config_form import (
    WEIGHT_OPTIONS, COLOR_ELEMENT_KEYS,
)


class FontsSection(ExpandGroupSettingCard):
    """字体配置区块"""

    value_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(
            FluentIcon.FONT, '字体 fonts',
            'Latin/CJK 字体、字重、系统字体、全局尺寸、行间距、元素独立尺寸',
            parent=parent,
        )
        self._size_spinboxes = {}
        self._setup_ui()

    def _setup_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)

        # ── Latin 字体 ──
        layout.addWidget(BodyLabel('拉丁字体 (Latin)', container))
        lat_row0 = QHBoxLayout()
        lat_row0.addWidget(BodyLabel('family:', container))
        self.latin_family = LineEdit(container)
        self.latin_family.setText('Gotham')
        self.latin_family.setPlaceholderText('留空=系统字体 Segoe UI')
        self.latin_family.textChanged.connect(self._on_changed)
        lat_row0.addWidget(self.latin_family, stretch=1)
        layout.addLayout(lat_row0)

        lat_row1 = QHBoxLayout()
        lat_row1.addWidget(BodyLabel('weight:', container))
        self.latin_weight = ComboBox(container)
        self.latin_weight.addItems(WEIGHT_OPTIONS)
        self.latin_weight.setCurrentText('medium')
        self.latin_weight.currentTextChanged.connect(
            self._on_changed)
        lat_row1.addWidget(self.latin_weight)
        lat_row1.addStretch()

        self.latin_system_btn = SwitchButton(container)
        self.latin_system_btn.checkedChanged.connect(
            self._on_changed)
        lat_row1.addWidget(BodyLabel('系统字体 (Segoe UI):', container))
        lat_row1.addWidget(self.latin_system_btn)
        layout.addLayout(lat_row1)

        # ── Latin 字重映射 ──
        lat_weights_label = BodyLabel('字重映射 (weights):', container)
        layout.addWidget(lat_weights_label)
        lat_weights_grid = QGridLayout()
        lat_weights_grid.setSpacing(4)
        self.latin_weight_light = LineEdit(container)
        self.latin_weight_light.setPlaceholderText('Light')
        lat_weights_grid.addWidget(BodyLabel('light:', container), 0, 0)
        lat_weights_grid.addWidget(self.latin_weight_light, 0, 1)
        self.latin_weight_regular = LineEdit(container)
        self.latin_weight_regular.setPlaceholderText('Book')
        lat_weights_grid.addWidget(BodyLabel('regular:', container), 1, 0)
        lat_weights_grid.addWidget(self.latin_weight_regular, 1, 1)
        self.latin_weight_medium = LineEdit(container)
        self.latin_weight_medium.setPlaceholderText('Medium')
        lat_weights_grid.addWidget(BodyLabel('medium:', container), 2, 0)
        lat_weights_grid.addWidget(self.latin_weight_medium, 2, 1)
        lat_weights_grid.setColumnStretch(1, 1)
        for w in [self.latin_weight_light, self.latin_weight_regular, self.latin_weight_medium]:
            w.textChanged.connect(self._on_changed)
        layout.addLayout(lat_weights_grid)

        # ── CJK 字体 ──
        layout.addWidget(BodyLabel('CJK 字体 (中文/日文)', container))
        cjk_row0 = QHBoxLayout()
        cjk_row0.addWidget(BodyLabel('family:', container))
        self.cjk_family = LineEdit(container)
        self.cjk_family.setText('GlowSansSC-Normal')
        self.cjk_family.setPlaceholderText('留空=系统字体 Microsoft JhengHei UI')
        self.cjk_family.textChanged.connect(self._on_changed)
        cjk_row0.addWidget(self.cjk_family, stretch=1)
        layout.addLayout(cjk_row0)

        cjk_row1 = QHBoxLayout()
        cjk_row1.addWidget(BodyLabel('weight:', container))
        self.cjk_weight = ComboBox(container)
        self.cjk_weight.addItems(WEIGHT_OPTIONS)
        self.cjk_weight.setCurrentText('medium')
        self.cjk_weight.currentTextChanged.connect(
            self._on_changed)
        cjk_row1.addWidget(self.cjk_weight)
        cjk_row1.addStretch()

        self.cjk_system_btn = SwitchButton(container)
        self.cjk_system_btn.checkedChanged.connect(
            self._on_changed)
        cjk_row1.addWidget(
            BodyLabel('系统字体 (Microsoft JhengHei UI):', container))
        cjk_row1.addWidget(self.cjk_system_btn)
        layout.addLayout(cjk_row1)

        # ── CJK 字重映射 ──
        cjk_weights_label = BodyLabel('字重映射 (weights):', container)
        layout.addWidget(cjk_weights_label)
        cjk_weights_grid = QGridLayout()
        cjk_weights_grid.setSpacing(4)
        self.cjk_weight_light = LineEdit(container)
        self.cjk_weight_light.setPlaceholderText('Light')
        cjk_weights_grid.addWidget(BodyLabel('light:', container), 0, 0)
        cjk_weights_grid.addWidget(self.cjk_weight_light, 0, 1)
        self.cjk_weight_regular = LineEdit(container)
        self.cjk_weight_regular.setPlaceholderText('Regular')
        cjk_weights_grid.addWidget(BodyLabel('regular:', container), 1, 0)
        cjk_weights_grid.addWidget(self.cjk_weight_regular, 1, 1)
        self.cjk_weight_medium = LineEdit(container)
        self.cjk_weight_medium.setPlaceholderText('Medium')
        cjk_weights_grid.addWidget(BodyLabel('medium:', container), 2, 0)
        cjk_weights_grid.addWidget(self.cjk_weight_medium, 2, 1)
        cjk_weights_grid.setColumnStretch(1, 1)
        for w in [self.cjk_weight_light, self.cjk_weight_regular, self.cjk_weight_medium]:
            w.textChanged.connect(self._on_changed)
        layout.addLayout(cjk_weights_grid)

        # ── 全局尺寸 ──
        layout.addWidget(BodyLabel('全局参数', container))
        global_grid = QGridLayout()
        global_grid.setSpacing(6)

        global_grid.addWidget(
            BodyLabel('默认尺寸 size_ratio:', container), 0, 0)
        self.size_ratio_sb = DoubleSpinBox(container)
        self.size_ratio_sb.setRange(0.001, 0.2)
        self.size_ratio_sb.setDecimals(3)
        self.size_ratio_sb.setSingleStep(0.001)
        self.size_ratio_sb.setValue(0.015)
        self.size_ratio_sb.valueChanged.connect(self._on_changed)
        global_grid.addWidget(self.size_ratio_sb, 0, 1)

        global_grid.addWidget(
            BodyLabel('行间距 line_spacing_ratio:', container), 1, 0)
        self.line_spacing_sb = DoubleSpinBox(container)
        self.line_spacing_sb.setRange(0.0, 0.1)
        self.line_spacing_sb.setDecimals(3)
        self.line_spacing_sb.setSingleStep(0.001)
        self.line_spacing_sb.setValue(0.005)
        self.line_spacing_sb.valueChanged.connect(self._on_changed)
        global_grid.addWidget(self.line_spacing_sb, 1, 1)
        global_grid.setColumnStretch(1, 1)

        layout.addLayout(global_grid)

        # ── 元素独立尺寸 ──
        layout.addWidget(BodyLabel(
            '元素独立尺寸（留空使用默认值）', container))
        sizes_grid = QGridLayout()
        sizes_grid.setSpacing(4)

        r = 0
        cols = 2
        for i, k in enumerate(COLOR_ELEMENT_KEYS):
            c = i % cols
            if c == 0 and i > 0:
                r += 1
            sizes_grid.addWidget(BodyLabel(k, container), r, c * 2)
            sb = DoubleSpinBox(container)
            sb.setRange(0.0, 0.2)
            sb.setDecimals(3)
            sb.setSingleStep(0.001)
            sb.setSpecialValueText('默认')
            sb.setValue(0.0)
            sb.valueChanged.connect(self._on_changed)
            sizes_grid.addWidget(sb, r, c * 2 + 1)
            self._size_spinboxes[k] = sb
        sizes_grid.setColumnStretch(1, 1)
        sizes_grid.setColumnStretch(3, 1)

        layout.addLayout(sizes_grid)

        self.addGroupWidget(container)

    def _on_changed(self, *args):
        self.value_changed.emit()

    def load_from_model(self, data):
        self.latin_family.setText(data.font_latin_family)
        self.latin_weight.setCurrentText(data.font_latin_weight)
        self.latin_system_btn.setChecked(data.font_latin_system)
        self.latin_weight_light.setText(
            data.font_latin_weights.get('light', ''))
        self.latin_weight_regular.setText(
            data.font_latin_weights.get('regular', ''))
        self.latin_weight_medium.setText(
            data.font_latin_weights.get('medium', ''))
        self.cjk_family.setText(data.font_cjk_family)
        self.cjk_weight.setCurrentText(data.font_cjk_weight)
        self.cjk_system_btn.setChecked(data.font_cjk_system)
        self.cjk_weight_light.setText(
            data.font_cjk_weights.get('light', ''))
        self.cjk_weight_regular.setText(
            data.font_cjk_weights.get('regular', ''))
        self.cjk_weight_medium.setText(
            data.font_cjk_weights.get('medium', ''))
        self.size_ratio_sb.setValue(data.font_size_ratio)
        self.line_spacing_sb.setValue(data.font_line_spacing)
        for k in COLOR_ELEMENT_KEYS:
            sb = self._size_spinboxes.get(k)
            if sb:
                sb.setValue(float(data.font_sizes.get(k, 0.0)))

    def save_to_model(self, data):
        data.font_latin_family = self.latin_family.text().strip()
        data.font_latin_weight = self.latin_weight.currentText()
        data.font_latin_system = self.latin_system_btn.isChecked()
        data.font_latin_weights = {
            'light': self.latin_weight_light.text().strip(),
            'regular': self.latin_weight_regular.text().strip(),
            'medium': self.latin_weight_medium.text().strip(),
        }
        data.font_cjk_family = self.cjk_family.text().strip()
        data.font_cjk_weight = self.cjk_weight.currentText()
        data.font_cjk_system = self.cjk_system_btn.isChecked()
        data.font_cjk_weights = {
            'light': self.cjk_weight_light.text().strip(),
            'regular': self.cjk_weight_regular.text().strip(),
            'medium': self.cjk_weight_medium.text().strip(),
        }
        data.font_size_ratio = self.size_ratio_sb.value()
        data.font_line_spacing = self.line_spacing_sb.value()
        sizes = {}
        for k in COLOR_ELEMENT_KEYS:
            sb = self._size_spinboxes.get(k)
            if sb and sb.value() > 0.0:
                sizes[k] = sb.value()
        data.font_sizes = sizes
