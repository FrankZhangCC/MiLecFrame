"""
基本信息区块

样式名称 + 文件名输入 + 默认竖图适配
"""
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from PySide6.QtCore import Qt, Signal

from qfluentwidgets import (
    ExpandGroupSettingCard,
    LineEdit, ComboBox, FluentIcon, BodyLabel,
)

# 竖图方向适配样式默认值枚举（方案 §7.2）：
# 只含样式层三个实际默认值，不提供 'default'——本控件本身就在定义
# 样式的默认值，再加一层 default 会造成递归语义
from src.utils.orientation_adaptation import (
    ADAPT_NONE, ADAPT_CLOCKWISE, ADAPT_COUNTERCLOCKWISE,
)

_STYLE_ADAPT_ITEMS = (
    ('不启用', ADAPT_NONE),
    ('顺时针适配', ADAPT_CLOCKWISE),
    ('逆时针适配', ADAPT_COUNTERCLOCKWISE),
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

        # 默认竖图适配（方案 §7.2）：样式设计者声明的建议方向，
        # 与图片处理页的用户运行时选项不是同一个控件。
        # userData 绑定稳定枚举值，模型往返不依赖中文文本
        row3 = QHBoxLayout()
        row3.addWidget(BodyLabel('默认竖图适配:', container))
        self.default_portrait_adaptation_combo = ComboBox(container)
        for _text, _value in _STYLE_ADAPT_ITEMS:
            self.default_portrait_adaptation_combo.addItem(_text, userData=_value)
        self.default_portrait_adaptation_combo.setMinimumWidth(200)
        self.default_portrait_adaptation_combo.setCurrentIndex(
            self.default_portrait_adaptation_combo.findData(ADAPT_NONE))
        # 样式预设的作用范围说明：仅竖图生效（用户在图片处理页显式
        # 选择适配时才对所有图片生效）
        self.default_portrait_adaptation_combo.setToolTip(
            '样式对竖拍构图的默认建议方向，仅对竖图生效；'
            '横图/方形图保持原方向。用户显式选择适配时不受此限')
        self.default_portrait_adaptation_combo.currentIndexChanged.connect(
            self._on_changed)
        row3.addWidget(self.default_portrait_adaptation_combo, stretch=1)
        layout.addLayout(row3)

        self.addGroupWidget(container)

    def _on_changed(self, *args):
        self.value_changed.emit()

    def load_from_model(self, data):
        self.name_edit.setText(data.name)
        self.filename_edit.setText(data.filename)
        # 未知模型值经 findData<0 回退 none（方案 §7.2）
        index = self.default_portrait_adaptation_combo.findData(
            data.default_portrait_adaptation)
        if index < 0:
            index = self.default_portrait_adaptation_combo.findData(ADAPT_NONE)
        self.default_portrait_adaptation_combo.setCurrentIndex(index)

    def save_to_model(self, data):
        data.name = self.name_edit.text().strip()
        data.filename = self.filename_edit.text().strip()
        value = self.default_portrait_adaptation_combo.currentData()
        data.default_portrait_adaptation = (
            value if value in (ADAPT_NONE, ADAPT_CLOCKWISE, ADAPT_COUNTERCLOCKWISE)
            else ADAPT_NONE
        )
