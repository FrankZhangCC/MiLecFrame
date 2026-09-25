# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
样式选择器折叠卡片组件
以横向缩略图滚动条的形式展示所有可用样式（与底部胶片栏相同模式）
"""
import logging
from typing import List, Optional

from PySide6.QtWidgets import QWidget, QHBoxLayout, QSizePolicy
from PySide6.QtCore import Qt, Signal, QEvent, QObject

from qfluentwidgets import (
    ExpandGroupSettingCard, FluentIcon, SmoothScrollArea,
)

from .style_thumbnail_card import StyleThumbnailCard, CARD_HEIGHT

logger = logging.getLogger(__name__)

# 滚动区域固定高度：卡片高度 + 上下 padding + 滚动条冗余
SCROLL_AREA_HEIGHT = CARD_HEIGHT + 22


class HorizontalWheelFilter(QObject):
    """将垂直滚轮事件转换为水平滚动，用于横向缩略图列表"""

    def __init__(self, scroll_area: SmoothScrollArea):
        super().__init__(scroll_area)
        self._scroll_area = scroll_area

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            if delta != 0:
                self._scroll_area.delegate.hScrollBar.scrollValue(-delta)
                event.accept()
                return True
        return False


class StyleSelectorCard(ExpandGroupSettingCard):
    """
    样式选择器卡片（横向缩略图滚动条）
    
    信号：
        style_selected(str): 选中某个样式时触发
    """
    style_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(FluentIcon.PHOTO, "样式选择", "点击 (或滚轮浏览) 缩略图选择相框样式", parent)
        self._current_style: Optional[str] = None
        self._cards: List[StyleThumbnailCard] = []
        self._style_manager = None

        # ── 横向滚动区域 + 水平布局 ──
        self._scroll_area = SmoothScrollArea()
        self._scroll_area.setFixedHeight(SCROLL_AREA_HEIGHT)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.setStyleSheet("SmoothScrollArea { border: none; background: transparent; }")

        self._scroll_widget = QWidget()
        self._scroll_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._scroll_widget.setFixedHeight(SCROLL_AREA_HEIGHT - 2)
        self._h_layout = QHBoxLayout(self._scroll_widget)
        self._h_layout.setContentsMargins(8, 4, 8, 4)
        self._h_layout.setSpacing(8)
        self._h_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # 安装滚轮方向转换过滤器
        self._wheel_filter = HorizontalWheelFilter(self._scroll_area)
        self._scroll_area.viewport().installEventFilter(self._wheel_filter)
        self._scroll_area.setWidget(self._scroll_widget)

        # 通过 addGroupWidget 注册到卡片系统（确保 _adjustViewSize 正确计算高度）
        self.addGroupWidget(self._scroll_area)

    def refresh_styles(self, style_names: List[str], style_manager) -> None:
        """
        刷新样式列表
        
        Args:
            style_names: 可用的样式名称列表
            style_manager: StyleManager 实例，用于获取缩略图路径
        """
        self._style_manager = style_manager
        self._clear_cards()

        for name in style_names:
            thumb_path = style_manager.get_style_thumbnail(name) if style_manager else None
            card = StyleThumbnailCard(name, thumb_path)
            card.style_selected.connect(self._on_card_selected)
            self._cards.append(card)
            self._h_layout.addWidget(card)

        # 末尾弹簧（卡片不满时靠左对齐）
        self._h_layout.addStretch()

        # 恢复选中态
        if self._current_style and self._current_style in style_names:
            self._set_selected_card(self._current_style)
        elif style_names:
            self._set_selected_card(style_names[0])

    def _clear_cards(self) -> None:
        """清除所有卡片"""
        # 移除 stretch（最后一个 item）
        if self._h_layout.count() > 0:
            last_item = self._h_layout.takeAt(self._h_layout.count() - 1)
            if last_item.spacerItem():
                del last_item

        for card in self._cards:
            self._h_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

    def _on_card_selected(self, style_name: str) -> None:
        """卡片被点击"""
        self._set_selected_card(style_name)
        self.style_selected.emit(style_name)

    def _set_selected_card(self, style_name: str) -> None:
        """设置选中卡片"""
        self._current_style = style_name
        for card in self._cards:
            card.set_selected(card.style_name == style_name)

    def _adjustViewSize(self):
        """
        覆盖父类：使用滚动区的固定高度而非 sizeHint。
        QScrollArea.sizeHint() 不反映 setFixedHeight() 的值（始终返回 ~8px），
        导致 spaceWidget 高度严重不足，收起动画无法完全隐藏内容。
        """
        # 使用固定高度 + 余量，确保滚动范围足以覆盖全部内容
        h = self._scroll_area.maximumHeight() + 3
        self.spaceWidget.setFixedHeight(h)
        if self.isExpand:
            self.setFixedHeight(self.card.height() + h)

    @property
    def current_style(self) -> Optional[str]:
        """当前选中的样式名称"""
        return self._current_style

    def set_current_style(self, style_name: str, silent: bool = False) -> None:
        """
        编程方式选中某个样式
        
        Args:
            style_name: 样式名称
            silent: 为 True 时不发射 style_selected 信号
        """
        if style_name in {c.style_name for c in self._cards}:
            self._set_selected_card(style_name)
            if not silent:
                self.style_selected.emit(style_name)
