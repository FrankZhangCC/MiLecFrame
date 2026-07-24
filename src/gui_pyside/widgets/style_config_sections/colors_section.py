"""
颜色配置区块

通用 light/dark 颜色 + 按元素类型独立覆盖（15 种元素 × light/dark）
"""
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QGridLayout, QWidget
from PySide6.QtCore import Qt, Signal

from qfluentwidgets import (
    ExpandGroupSettingCard,
    LineEdit, ComboBox, FluentIcon, BodyLabel,
)

from ...models.style_config_form import COLOR_ELEMENT_KEYS


class ColorsSection(ExpandGroupSettingCard):
    """颜色配置区块"""

    value_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(
            FluentIcon.PALETTE, '颜色 colors',
            '通用 light/dark 颜色 + 按元素类型独立覆盖',
            parent=parent,
        )
        self._per_element_inputs: dict = {}
        self._setup_ui()

    def _setup_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)

        # ── 通用颜色 ──
        layout.addWidget(BodyLabel('通用兜底颜色', container))
        hint = BodyLabel(
            '支持十六进制 "#030303" 或 RGB 数组 "[51,51,51]"',
            container)
        hint.setStyleSheet('color: #888;')
        layout.addWidget(hint)

        row1 = QHBoxLayout()
        row1.addWidget(BodyLabel('custom_text_light_color:', container))
        self.color_light = LineEdit(container)
        self.color_light.setPlaceholderText(
            '[51,51,51] 或 "#030303"')
        self.color_light.textChanged.connect(self._on_changed)
        row1.addWidget(self.color_light, stretch=1)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(BodyLabel('custom_text_dark_color:', container))
        self.color_dark = LineEdit(container)
        self.color_dark.setPlaceholderText(
            '[204,204,204] 或 "#C0C0C0"')
        self.color_dark.textChanged.connect(self._on_changed)
        row2.addWidget(self.color_dark, stretch=1)
        layout.addLayout(row2)

        # ── 自定义背景填充色 ──
        layout.addSpacing(8)
        sep = BodyLabel('─── 自定义背景填充 ───', container)
        sep.setStyleSheet('color: #888; font-weight: bold;')
        layout.addWidget(sep)
        bg_hint = BodyLabel(
            '若指定，GUI 背景样式不可选。支持 "#FF6B6B" 或 [255,107,107]，留空则使用 GUI 背景样式',
            container)
        bg_hint.setStyleSheet('color: #888;')
        layout.addWidget(bg_hint)

        row_bg = QHBoxLayout()
        row_bg.addWidget(BodyLabel('custom_bg_color:', container))
        self.bg_color = LineEdit(container)
        self.bg_color.setPlaceholderText('"#FF6B6B" 或 [255,107,107]')
        self.bg_color.textChanged.connect(self._on_changed)
        row_bg.addWidget(self.bg_color, stretch=1)
        layout.addLayout(row_bg)

        row_bg_scheme = QHBoxLayout()
        row_bg_scheme.addWidget(BodyLabel('custom_bg_text_scheme:', container))
        self.bg_text_scheme = ComboBox(container)
        self.bg_text_scheme.addItems(['（自动检测）', 'dark', 'light'])
        self.bg_text_scheme.currentTextChanged.connect(self._on_changed)
        row_bg_scheme.addWidget(self.bg_text_scheme, stretch=1)
        layout.addLayout(row_bg_scheme)

        # ── 按元素类型独立覆盖 ──
        layout.addWidget(BodyLabel(
            '按元素类型独立覆盖（留空跳过）', container))
        grid = QGridLayout()
        grid.setSpacing(4)

        cols = 2
        for i, k in enumerate(COLOR_ELEMENT_KEYS):
            c = i % cols
            row = i // cols
            col_offset = c * 3

            grid.addWidget(BodyLabel(k, container), row, col_offset)
            lt_edit = LineEdit(container)
            lt_edit.setPlaceholderText('light')
            lt_edit.textChanged.connect(self._on_changed)
            grid.addWidget(lt_edit, row, col_offset + 1)

            dk_edit = LineEdit(container)
            dk_edit.setPlaceholderText('dark')
            dk_edit.textChanged.connect(self._on_changed)
            grid.addWidget(dk_edit, row, col_offset + 2)

            self._per_element_inputs[k] = (lt_edit, dk_edit)

        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(4, 1)

        layout.addLayout(grid)

        self.addGroupWidget(container)

    def _on_changed(self, *args):
        self.value_changed.emit()

    def load_from_model(self, data):
        self.color_light.setText(data.color_light)
        self.color_dark.setText(data.color_dark)
        self.bg_color.setText(data.custom_bg_color)
        scheme_text = data.custom_bg_text_scheme
        self.bg_text_scheme.setCurrentText(
            scheme_text if scheme_text in ('dark', 'light') else '（自动检测）')
        for k, (lt_edit, dk_edit) in \
                self._per_element_inputs.items():
            pe = data.color_per_element.get(k, {})
            lt_edit.setText(
                pe.get('light', '') if isinstance(pe, dict) else '')
            dk_edit.setText(
                pe.get('dark', '') if isinstance(pe, dict) else '')

    def save_to_model(self, data):
        data.color_light = self.color_light.text().strip()
        data.color_dark = self.color_dark.text().strip()
        data.custom_bg_color = self.bg_color.text().strip()
        scheme_text = self.bg_text_scheme.currentText()
        data.custom_bg_text_scheme = scheme_text if scheme_text in ('dark', 'light') else ''
        data.color_per_element = {}
        for k, (lt_edit, dk_edit) in \
                self._per_element_inputs.items():
            lt = lt_edit.text().strip()
            dk = dk_edit.text().strip()
            if lt or dk:
                pe = {}
                if lt:
                    pe['light'] = lt
                if dk:
                    pe['dark'] = dk
                data.color_per_element[k] = pe
