# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
样式缩略图卡片组件
显示单个样式的缩略图（或文字占位）+ 样式名称，支持选中态高亮
"""
import logging
import os

from PySide6.QtWidgets import QVBoxLayout, QSizePolicy
from PySide6.QtCore import Qt, Signal, QSize, QRect
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QFontMetrics, QPen

from qfluentwidgets import (
    ElevatedCardWidget, ImageLabel, BodyLabel, CaptionLabel,
    themeColor, isDarkTheme
)

logger = logging.getLogger(__name__)

CARD_WIDTH = 136
CARD_HEIGHT = 160
THUMBNAIL_SIZE = 120


class StyleThumbnailCard(ElevatedCardWidget):
    """
    单个样式缩略图卡片
    
    信号：
        style_selected(str): 点击卡片时发出，携带样式名称
    """
    style_selected = Signal(str)

    def __init__(self, style_name: str, thumbnail_path: str = None, parent=None):
        super().__init__(parent)
        self.style_name = style_name
        self._selected = False

        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setClickEnabled(True)
        self.setBorderRadius(8)
        self.clicked.connect(self._on_card_clicked)

        self._setup_ui(thumbnail_path)

    def _setup_ui(self, thumbnail_path: str = None):
        """搭建卡片内部布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ── 缩略图区域 ──
        self.thumbnail_label = ImageLabel(self)
        self.thumbnail_label.setFixedSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE)
        self.thumbnail_label.setBorderRadius(8, 8, 8, 8)
        self.thumbnail_label.setScaledSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))
        self.thumbnail_label.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        # 让 ImageLabel 不拦截鼠标事件，由卡片统一处理点击
        self.thumbnail_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        if thumbnail_path and os.path.isfile(thumbnail_path):
            pixmap = QPixmap(thumbnail_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    THUMBNAIL_SIZE, THUMBNAIL_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                # 浅色描边
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(QPen(QColor(0, 0, 0, 38), 2))
                painter.drawRoundedRect(pixmap.rect().adjusted(0, 0, -1, -1), 8, 8)
                painter.end()
                self.thumbnail_label.setImage(pixmap)
            else:
                self.thumbnail_label.setImage(self._create_placeholder_pixmap())
        else:
            # 无缩略图时显示文字占位
            self.thumbnail_label.setImage(self._create_placeholder_pixmap())

        layout.addWidget(self.thumbnail_label, 0, Qt.AlignmentFlag.AlignCenter)

        # ── 样式名称 ──
        self.name_label = CaptionLabel(self.style_name, self)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setMaximumWidth(THUMBNAIL_SIZE)
        layout.addWidget(self.name_label, 0, Qt.AlignmentFlag.AlignCenter)

    def _create_placeholder_pixmap(self) -> QPixmap:
        """
        创建占位图：在浅灰/深灰背景上居中绘制样式名称
        返回的 QPixmap 尺寸为 THUMBNAIL_SIZE × THUMBNAIL_SIZE
        """
        pixmap = QPixmap(THUMBNAIL_SIZE, THUMBNAIL_SIZE)
        dark = isDarkTheme()
        bg_color = QColor(50, 50, 50) if dark else QColor(220, 220, 220)
        text_color = QColor(200, 200, 200) if dark else QColor(120, 120, 120)

        pixmap.fill(bg_color)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setPen(text_color)
        font = QFont("Microsoft YaHei", 10)
        painter.setFont(font)

        # 文字自动换行适应
        rect = QRect(8, 0, THUMBNAIL_SIZE - 16, THUMBNAIL_SIZE)
        fm = QFontMetrics(font)
        # 分行绘制
        text = self.style_name
        lines = []
        for char in text:
            if lines and fm.horizontalAdvance(lines[-1] + char) < THUMBNAIL_SIZE - 16:
                lines[-1] += char
            else:
                lines.append(char)
        if not lines:
            lines = [text]

        total_h = len(lines) * fm.height()
        y = (THUMBNAIL_SIZE - total_h) // 2 + fm.ascent()
        for line in lines:
            x = (THUMBNAIL_SIZE - fm.horizontalAdvance(line)) // 2
            painter.drawText(x, y, line)
            y += fm.height()

        # 浅色描边
        painter.setPen(QPen(QColor(0, 0, 0, 38), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(pixmap.rect().adjusted(0, 0, -1, -1), 8, 8)

        painter.end()
        return pixmap

    def _on_card_clicked(self):
        """卡片被点击"""
        self.style_selected.emit(self.style_name)

    def paintEvent(self, e):
        super().paintEvent(e)
        if self._selected:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(themeColor(), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 8, 8)
            painter.end()

    def set_selected(self, selected: bool):
        """设置选中状态"""
        self._selected = selected
        self.update()

    def is_selected(self) -> bool:
        return self._selected
