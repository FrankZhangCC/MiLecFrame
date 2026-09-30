# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
横向滚轮过滤器（G8 去样板：两处相同组件单点化）

image_processing_page 的 FilmStripWheelFilter 与
style_selector_card 的 HorizontalWheelFilter 语义一致（垂直滚轮
转水平滚动），合并为本组件；delegate.hScrollBar 为 qfluentwidgets
内部实现（契约 B：访问方式原样保留，升级版本时最先失效的点）。
"""
from PySide6.QtCore import QEvent, QObject


class HorizontalWheelFilter(QObject):
    """将垂直滚轮事件转换为水平滚动（用于横向缩略图列表）"""

    def __init__(self, scroll_area):
        super().__init__(scroll_area)
        self.scroll_area = scroll_area

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            if delta != 0:
                # SmoothScrollArea.delegate.hScrollBar 是 qfluentwidgets
                # 内部实现（版本耦合点，升级时最先失效）
                self.scroll_area.delegate.hScrollBar.scrollValue(-delta)
                event.accept()
                return True
        return False
