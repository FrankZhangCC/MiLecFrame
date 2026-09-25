# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
样式预览面板

包含 SegmentedWidget（横图/竖图切换）和 QLabel（QPixmap 显示），
接收 PIL Image 并转换为 QPixmap 显示。
"""
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap, QColorSpace

from qfluentwidgets import SegmentedWidget, ComboBox, setCustomStyleSheet
from qfluentwidgets.common.style_sheet import addStyleSheet, CustomStyleSheet

from PIL import Image as PILImage

logger = logging.getLogger(__name__)


class StylePreview(QWidget):
    """样式预览面板

    信号：
        orientation_changed(str): 横/竖预览切换时触发，值为 "landscape" / "portrait"
        preview_bg_changed(str): 预览背景切换时触发
    """

    orientation_changed = Signal(str)
    preview_bg_changed = Signal(str)

    ORIENTATION_LANDSCAPE = 'landscape'
    ORIENTATION_PORTRAIT = 'portrait'

    def __init__(self, parent=None):
        super().__init__(parent)

        self._current_image: PILImage.Image = None
        self._cached_pixmap: QPixmap = None
        self._current_orientation = self.ORIENTATION_LANDSCAPE

        self._setup_ui()

    def _setup_ui(self):
        """搭建预览面板 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── 顶部工具栏：横竖切换 + 预览背景选择 ──
        toolbar = QWidget()
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)

        # 横/竖切换
        self.segment_widget = SegmentedWidget(self)
        self.segment_widget.addItem(
            self.ORIENTATION_LANDSCAPE, '横图预览')
        self.segment_widget.addItem(
            self.ORIENTATION_PORTRAIT, '竖图预览')
        self.segment_widget.setCurrentItem(self.ORIENTATION_LANDSCAPE)
        self.segment_widget.currentItemChanged.connect(
            self._on_orientation_changed)

        # 预览背景选择
        self.bg_combo = ComboBox(self)
        from src.utils.background_fill import BackgroundFillManager
        bg_labels = list(BackgroundFillManager.get_choices().keys())
        self.bg_combo.addItems(bg_labels)
        self.bg_combo.setCurrentText('模糊背景 (深色 35%)')
        self.bg_combo.currentTextChanged.connect(
            self._on_bg_changed)

        toolbar_layout.addWidget(self.segment_widget)
        toolbar_layout.addWidget(self.bg_combo)

        layout.addWidget(toolbar)

        # ── 预览图像 ──
        self.preview_label = QLabel("请先在左侧配置样式参数\n预览将在您输入时实时更新")
        self.preview_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(200, 200)
        self.preview_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        setCustomStyleSheet(self.preview_label,
            lightQss=(
                "QLabel {"
                " border: 1px solid #e0e0e0;"
                " border-radius: 8px;"
                " color: #888;"
                " font-size: 14px;"
                " background-color: #fafafa;"
                " }"
            ),
            darkQss=(
                "QLabel {"
                " border: 1px solid #404040;"
                " border-radius: 8px;"
                " color: #999;"
                " font-size: 14px;"
                " background-color: #282828;"
                " }"
            ),
        )
        addStyleSheet(self.preview_label, CustomStyleSheet(self.preview_label))
        layout.addWidget(self.preview_label, stretch=1)

    def _on_orientation_changed(self, route_key: str):
        """横竖切换处理"""
        self._current_orientation = route_key
        self.orientation_changed.emit(route_key)

    def _on_bg_changed(self, label: str):
        """预览背景切换处理"""
        from src.utils.background_fill import BackgroundFillManager
        bg_choices = BackgroundFillManager.get_choices()
        key = bg_choices.get(label)
        if key:
            self.preview_bg_changed.emit(key)

    def get_current_orientation(self) -> str:
        """返回当前选中的预览方向"""
        return self._current_orientation

    def get_current_bg_fill_type(self) -> str:
        """返回当前选中的预览背景类型 key"""
        from src.utils.background_fill import BackgroundFillManager
        bg_choices = BackgroundFillManager.get_choices()
        label = self.bg_combo.currentText()
        return bg_choices.get(label, 'gaussian_black_35')

    def _do_scale_pixmap(self):
        """将缓存的 pixmap 缩放到当前标签尺寸"""
        if self._cached_pixmap is None or self._cached_pixmap.isNull():
            return
        label_size = self.preview_label.size()
        if label_size.width() <= 0 or label_size.height() <= 0:
            return
        scaled = self._cached_pixmap.scaled(
            label_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)

    def rescale_pixmap(self):
        """仅缩放已缓存的 pixmap，不重新转换 PIL"""
        self._do_scale_pixmap()

    def set_preview_image(self, pil_image: PILImage.Image):
        """设置预览图像（PIL Image → QPixmap → QLabel，缓存 pixmap）"""
        self._current_image = pil_image
        if pil_image is None:
            self._cached_pixmap = None
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("预览渲染失败")
            return

        # PIL → QImage → QPixmap
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')
        data = pil_image.tobytes()
        qimage = QImage(
            data, pil_image.width, pil_image.height,
            3 * pil_image.width, QImage.Format.Format_RGB888,
        )
        qimage.setColorSpace(QColorSpace.NamedColorSpace.SRgb)
        pixmap = QPixmap.fromImage(qimage)
        if pixmap.isNull():
            self._cached_pixmap = None
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("预览渲染失败")
            return

        # 缓存原始 pixmap
        self._cached_pixmap = pixmap
        setCustomStyleSheet(self.preview_label,
            lightQss="QLabel { border: none; border-radius: 8px; background-color: #fafafa; }",
            darkQss="QLabel { border: none; border-radius: 8px; background-color: #282828; }",
        )
        addStyleSheet(self.preview_label, CustomStyleSheet(self.preview_label))
        self.preview_label.setText("")
        self._do_scale_pixmap()
