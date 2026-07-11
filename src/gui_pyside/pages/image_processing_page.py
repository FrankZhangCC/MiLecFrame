# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
图像处理页面

这是 PySide6 GUI 的核心页面，包含：
- 预览窗口（原图/效果图切换显示）
- EXIF 信息面板
- 操作按钮（导出当前/一键导出/清空所有）
- 胶片栏（底部横向缩略图列表）
- 手风琴式配置面板（5 个折叠 Tab）
"""
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QSplitter,
    QFileDialog, QApplication, QSizePolicy, QLineEdit,
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QEvent, QObject
from PySide6.QtGui import QImage, QPixmap, QWheelEvent, QColorSpace, QDragEnterEvent, QDropEvent, QColor, QKeySequence, QShortcut

from qfluentwidgets import (
    PrimaryPushButton, PushButton, TransparentPushButton,
    StrongBodyLabel, BodyLabel, SubtitleLabel, CaptionLabel,
    InfoBar, InfoBarPosition,
    ExpandSettingCard, ExpandGroupSettingCard, SettingCardGroup, ComboBox,
    FluentIcon, SwitchButton, LineEdit, Slider,
    SmoothScrollArea, StateToolTip, RoundMenu, Action, ScrollArea,
    ExpandLayout,
)
from qfluentwidgets.common.style_sheet import (
    setCustomStyleSheet as _qfw_setCustomStyleSheet,
    addStyleSheet, CustomStyleSheet,
)

from ..models.file_item import FileItem
from ..models.processing_config import ProcessingConfig
from ..utils.temp_manager import TempManager
from ..widgets.style_selector_card import StyleSelectorCard
from src.utils.exif_helper import ExifHelper
from src.utils.logo_selector import LogoSelector
from src.utils.background_fill import BackgroundFillManager
from src.utils.config_manager import default_config_manager
from src.core.image_processor import ImageProcessor
from PIL import Image as PILImage
from PIL import ImageCms
import io

logger = logging.getLogger(__name__)

# 图片文件扩展名白名单（与 _on_add_files 文件对话框过滤器一致）
_ALLOWED_EXT = ('.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.webp')


class FilmStripWheelFilter(QObject):
    """将垂直滚轮事件转为水平滚动（用于胶片栏横向滚动）"""

    def __init__(self, scroll_area):
        super().__init__(scroll_area)
        self.scroll_area = scroll_area

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            if delta != 0:
                self.scroll_area.delegate.hScrollBar.scrollValue(-delta)
                event.accept()
                return True
        return False


class ImageProcessingPage(QWidget):
    """图像处理页面主容器

    布局结构：
    ┌─────────────────────────────────────────┐
    │  ┌── 主内容区 ─────┬── 配置栏 ─────┐    │
    │  │  预览窗口        │  手风琴配置   │    │
    │  │  EXIF 信息       │  (5 个 Tab)   │    │
    │  │  操作按钮        │               │    │
    │  └─────────────────┴───────────────┘    │
    │  ┌── 胶片栏 (底部横向缩略图) ────────┐  │
    │  └────────────────────────────────────┘  │
    └─────────────────────────────────────────┘
    """

    # ── 缩略图边框样式（light / dark 双主题）──
    _STYLE_THUMB_NORMAL = {
        'light': (
            "QLabel { border: 2px solid #ddd; border-radius: 4px; padding: 2px;"
            " background-color: white; }"
            " QLabel:hover { border-color: --ThemeColorPrimary; }"
        ),
        'dark': (
            "QLabel { border: 2px solid #444; border-radius: 4px; padding: 2px;"
            " background-color: #282828; }"
            " QLabel:hover { border-color: --ThemeColorPrimary; }"
        ),
    }
    _STYLE_THUMB_SELECTED = {
        'light': (
            "QLabel { border: 2px solid --ThemeColorPrimary; border-radius: 4px; padding: 2px;"
            " background-color: white; }"
            " QLabel:hover { border-color: --ThemeColorPrimary; }"
        ),
        'dark': (
            "QLabel { border: 2px solid --ThemeColorPrimary; border-radius: 4px; padding: 2px;"
            " background-color: #282828; }"
            " QLabel:hover { border-color: --ThemeColorPrimary; }"
        ),
    }
    # ── 已处理缩略图边框样式（light / dark 双主题）──
    _STYLE_THUMB_PROCESSED = {
        'light': (
            "QLabel { border: 2px solid #00a86b; border-radius: 4px; padding: 2px;"
            " background-color: white; }"
            " QLabel:hover { border-color: --ThemeColorPrimary; }"
        ),
        'dark': (
            "QLabel { border: 2px solid #6ccb5f; border-radius: 4px; padding: 2px;"
            " background-color: #282828; }"
            " QLabel:hover { border-color: --ThemeColorPrimary; }"
        ),
    }

    def __init__(self, parent=None):
        super().__init__(parent)

        # ── 核心依赖 ──
        self.exif_helper = ExifHelper()
        self.logo_selector = LogoSelector()
        self.temp_manager = TempManager()

        # ── 数据 ──
        self.file_items: list[FileItem] = []  # 胶片栏中的所有文件
        self.current_index: int = -1  # 当前选中的文件索引
        self.config = ProcessingConfig()  # 当前共享配置
        self.filmstrip_labels: list[QLabel] = []  # 胶片栏缩略图标签（用于动态缩放）
        self.state_tooltip = None  # 处理状态提示

        # ── 初始化 UI ──
        self._setup_ui()

        # 加载已保存的作者名和配置
        self._load_saved_config()

        # ── 拖放支持 ──
        self.setAcceptDrops(True)
        self._drag_overlay = QWidget(self)
        self._drag_overlay.hide()
        self._drag_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._apply_custom_style(self._drag_overlay,
            lightQss="background: rgba(255,255,255,0.7);",
            darkQss="background: rgba(0,0,0,0.5);")
        overlay_layout = QVBoxLayout(self._drag_overlay)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drag_hint_label = BodyLabel("松开左键以添加图片", self._drag_overlay)
        self._drag_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self._drag_hint_label.font()
        font.setPixelSize(32)
        self._drag_hint_label.setFont(font)
        self._drag_hint_label.setTextColor(QColor(120, 120, 120), QColor(180, 180, 180))
        overlay_layout.addWidget(self._drag_hint_label)

        # ── Delete 键移除图片 ──
        self._delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        self._delete_shortcut.activated.connect(self._on_delete_key)

        logger.info("图像处理页面初始化完成")

    def _setup_ui(self):
        """搭建页面整体布局"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 使用 QSplitter 分割主内容区和胶片栏（可拖拽调高度） ──
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(4)
        self._apply_custom_style(splitter,
            lightQss="""
                QSplitter::handle { background-color: #e0e0e0; }
                QSplitter::handle:hover { background-color: --ThemeColorPrimary; }
            """,
            darkQss="""
                QSplitter::handle { background-color: #3D3D3D; }
                QSplitter::handle:hover { background-color: --ThemeColorPrimary; }
            """,
        )

        # 上部：主内容区（预览 + 配置），用水平 QSplitter 可调宽度
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.setChildrenCollapsible(False)
        content_splitter.setHandleWidth(4)
        self._apply_custom_style(content_splitter,
            lightQss="""
                QSplitter::handle { background-color: #e0e0e0; }
                QSplitter::handle:hover { background-color: --ThemeColorPrimary; }
            """,
            darkQss="""
                QSplitter::handle { background-color: #3D3D3D; }
                QSplitter::handle:hover { background-color: --ThemeColorPrimary; }
            """,
        )

        left_panel = self._create_preview_panel()
        right_panel = self._create_config_panel()
        right_panel.setMinimumWidth(350)
        right_panel.setMaximumWidth(800)

        content_splitter.addWidget(left_panel)
        content_splitter.addWidget(right_panel)
        content_splitter.setSizes([550, 450])
        content_splitter.setStretchFactor(0, 1)  # 左侧预览区域占所有额外空间
        content_splitter.setStretchFactor(1, 0)  # 右侧配置栏保持固定宽度

        splitter.addWidget(content_splitter)

        # 下部：胶片栏
        filmstrip_widget = self._create_filmstrip()
        splitter.addWidget(filmstrip_widget)

        # 设置初始比例：主内容区占 80%，胶片栏占 20%
        splitter.setStretchFactor(0, 8)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([700, 200])

        # 连接分割器移动信号，确保手柄拖拽时也触发缩放
        splitter.splitterMoved.connect(self._on_splitter_moved)
        content_splitter.splitterMoved.connect(self._on_splitter_moved)

        main_layout.addWidget(splitter)

        # 初始化样式依赖控件的显示状态
        self._update_style_dependent_controls()

    # ════════════════════════════════════════════════════════
    #  文件拖放支持
    # ════════════════════════════════════════════════════════

    def dragEnterEvent(self, event: QDragEnterEvent):
        """拖入文件：显示蒙层，仅接受图片文件"""
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls()]
            if any(p.lower().endswith(_ALLOWED_EXT) for p in paths if p):
                self._drag_overlay.setGeometry(self.rect())
                self._drag_overlay.show()
                self._drag_overlay.raise_()
                event.acceptProposedAction()
                return
        event.ignore()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._drag_overlay.hide()

    def dropEvent(self, event: QDropEvent):
        self._drag_overlay.hide()
        file_paths = [url.toLocalFile() for url in event.mimeData().urls()]
        valid_paths = [p for p in file_paths if p and os.path.isfile(p) and p.lower().endswith(_ALLOWED_EXT)]
        skipped = len(file_paths) - len(valid_paths)
        if valid_paths:
            self._load_files(valid_paths)
        if skipped > 0:
            InfoBar.warning(
                title="部分文件未添加",
                content=f"已跳过 {skipped} 个不支持的格式",
                duration=3000,
                parent=self)

    def _on_delete_key(self):
        """Delete 键移除当前选中图片（文本输入时保留原生行为）"""
        focused = QApplication.focusWidget()
        if isinstance(focused, QLineEdit):
            return
        if self.current_index >= 0:
            self._remove_filmstrip_item(self.current_index)

    def _create_preview_panel(self) -> QWidget:
        """创建左侧预览面板（预览窗口 + EXIF 信息 + 操作按钮）"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 8, 16)
        layout.setSpacing(12)

        # ── 预览窗口 ──
        self.preview_label = QLabel("请从底部胶片栏选择图片，或拖拽图片到此处")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(200, 200)
        self.preview_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self._apply_preview_placeholder_style()
        layout.addWidget(self.preview_label, stretch=1)

        # ── EXIF 信息面板（固定高度，两行网格布局） ──
        self.exif_panel = QWidget()
        self.exif_panel.setFixedHeight(60)
        self._apply_custom_style(self.exif_panel,
            lightQss="""
                QWidget#exifPanel {
                    background-color: #f5f5f5;
                    border-radius: 6px;
                    padding: 4px 12px;
                }
            """,
            darkQss="""
                QWidget#exifPanel {
                    background-color: #2B2B2B;
                    border-radius: 6px;
                    padding: 4px 12px;
                }
            """,
        )
        self.exif_panel.setObjectName("exifPanel")

        exif_grid = QGridLayout(self.exif_panel)
        exif_grid.setContentsMargins(12, 6, 12, 6)
        exif_grid.setSpacing(4)

        # 第一行：文件(占两列) | 相机 | 镜头
        self.exif_file = BodyLabel("文件: —")
        self.exif_file.setWordWrap(False)
        self.exif_camera = BodyLabel("相机: —")
        self.exif_camera.setWordWrap(False)
        self.exif_lens = BodyLabel("镜头: —")
        self.exif_lens.setWordWrap(False)
        exif_grid.addWidget(self.exif_file, 0, 0, 1, 2)    # row, col, rowSpan, colSpan
        exif_grid.addWidget(self.exif_camera, 0, 2)
        exif_grid.addWidget(self.exif_lens, 0, 3)

        # 第二行：焦距 | 光圈 | 快门 | ISO
        self.exif_focal = BodyLabel("焦距: —")
        self.exif_aperture = BodyLabel("光圈: —")
        self.exif_shutter = BodyLabel("快门: —")
        self.exif_iso = BodyLabel("ISO: —")
        exif_grid.addWidget(self.exif_focal, 1, 0)
        exif_grid.addWidget(self.exif_aperture, 1, 1)
        exif_grid.addWidget(self.exif_shutter, 1, 2)
        exif_grid.addWidget(self.exif_iso, 1, 3)

        # 列均分：4列等宽
        for col in range(4):
            exif_grid.setColumnStretch(col, 1)

        layout.addWidget(self.exif_panel)

        # ── 操作按钮 ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_export_current = PrimaryPushButton("导出当前图像")
        self.btn_export_current.setEnabled(False)
        self.btn_export_current.clicked.connect(self._on_export_current)
        btn_layout.addWidget(self.btn_export_current)

        self.btn_export_all = PrimaryPushButton("一键导出所有")
        self.btn_export_all.setEnabled(False)
        self.btn_export_all.clicked.connect(self._on_export_all)
        btn_layout.addWidget(self.btn_export_all)

        self.btn_clear_all = TransparentPushButton("清空所有")
        self.btn_clear_all.clicked.connect(self._on_clear_all)
        btn_layout.addWidget(self.btn_clear_all)

        btn_layout.addStretch()

        # 生成相框按钮（右侧）
        self.btn_generate = PrimaryPushButton("生成相框")
        self.btn_generate.setEnabled(False)
        self.btn_generate.clicked.connect(self._on_generate_frame)
        btn_layout.addWidget(self.btn_generate)

        layout.addLayout(btn_layout)

        return panel

    def _create_config_panel(self) -> QWidget:
        """创建右侧配置面板（5 个手风琴折叠 Tab）"""
        panel = ScrollArea()
        panel.setWidgetResizable(True)
        self._apply_custom_style(panel,
            lightQss="QScrollArea { border: none; background-color: #f5f5f5; }",
            darkQss="QScrollArea { border: none; background-color: #2B2B2B; }",
        )

        config_container = QWidget()
        config_layout = QVBoxLayout(config_container)
        config_layout.setContentsMargins(0, 0, 0, 0)

        card_layout = ExpandLayout()
        card_layout.setContentsMargins(8, 16, 8, 16)
        card_layout.setSpacing(8)
        config_layout.addLayout(card_layout)

        # ── Tab 1: 输出设置 ──
        self.output_settings_card = self._create_output_settings_card()
        self.output_settings_card.setParent(config_container)
        card_layout.addWidget(self.output_settings_card)

        # ── Tab 2: 样式选择（缩略图网格） ──
        self.style_selector_card = self._create_style_selection_card()
        self.style_selector_card.setParent(config_container)
        card_layout.addWidget(self.style_selector_card)

        # ── Tab 3: 相框配置 ──
        self.frame_config_card = self._create_frame_config_card()
        self.frame_config_card.setParent(config_container)
        card_layout.addWidget(self.frame_config_card)

        # ── Tab 3: 个性化配置 ──
        self.personalization_card = self._create_personalization_card()
        self.personalization_card.setParent(config_container)
        card_layout.addWidget(self.personalization_card)

        # ── Tab 4: 拍摄信息配置 ──
        self.shot_info_card = self._create_shot_info_card()
        self.shot_info_card.setParent(config_container)
        card_layout.addWidget(self.shot_info_card)

        # ── Tab 5: 文本水印 ──
        self.watermark_card = self._create_watermark_card()
        self.watermark_card.setParent(config_container)
        card_layout.addWidget(self.watermark_card)

        panel.setWidget(config_container)

        return panel

    def _create_filmstrip(self) -> QWidget:
        """创建底部胶片栏（横向缩略图列表）"""
        filmstrip = QWidget()
        filmstrip.setMinimumHeight(100)
        filmstrip.setMaximumHeight(250)
        self._apply_custom_style(filmstrip,
            lightQss=(
                "QWidget {"
                " border-top: 1px solid #e0e0e0;"
                " background-color: #fafafa;"
                " }"
            ),
            darkQss=(
                "QWidget {"
                " border-top: 1px solid #3D3D3D;"
                " background-color: #282828;"
                " }"
            ),
        )

        layout = QVBoxLayout(filmstrip)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(4)

        # 标题栏
        header = QHBoxLayout()
        self.filmstrip_title = CaptionLabel("胶片栏 — 将图片拖拽到此处或点击\"添加图片\"按钮加载")
        header.addWidget(self.filmstrip_title)
        header.addStretch()

        self.btn_add_files = PushButton("添加图片")
        self.btn_add_files.clicked.connect(self._on_add_files)
        header.addWidget(self.btn_add_files)
        layout.addLayout(header)

        # 缩略图滚动区域（无固定高度限制，随胶片栏缩放）
        self.filmstrip_scroll = SmoothScrollArea()
        self.filmstrip_scroll.setWidgetResizable(True)
        self.filmstrip_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.filmstrip_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.filmstrip_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        # 安装滚轮事件过滤器（滚轮向下→图片列表向右）
        self.filmstrip_scroll.viewport().installEventFilter(FilmStripWheelFilter(self.filmstrip_scroll))

        self.filmstrip_container = QWidget()
        self.filmstrip_layout = QHBoxLayout(self.filmstrip_container)
        self.filmstrip_layout.setContentsMargins(0, 0, 0, 0)
        self.filmstrip_layout.setSpacing(8)
        self.filmstrip_layout.addStretch()

        self.filmstrip_scroll.setWidget(self.filmstrip_container)
        layout.addWidget(self.filmstrip_scroll)

        return filmstrip

    # ════════════════════════════════════════════════════════
    #  配置面板 Tab 创建方法
    # ════════════════════════════════════════════════════════

    def _create_output_settings_card(self) -> ExpandSettingCard:
        """Tab 1: 输出设置"""
        card = ExpandGroupSettingCard(FluentIcon.DOWNLOAD, "输出设置", "选择输出文件格式")

        # 输出格式
        self.combo_output_format = ComboBox()
        self.combo_output_format.addItems(["JPEG", "PNG"])
        self.combo_output_format.setCurrentIndex(0)
        card.addGroup(FluentIcon.DOWNLOAD, "输出格式", "JPEG 适合照片，PNG 适合透明背景", self.combo_output_format, 1)

        return card

    def _create_style_selection_card(self) -> ExpandSettingCard:
        """Tab 2: 样式选择（缩略图网格）"""
        from frame_styles.style_manager import StyleManager
        self.style_manager = StyleManager()
        available_styles = self.style_manager.get_available_styles()
        if not available_styles:
            self.style_manager.create_sample_styles()
            available_styles = self.style_manager.get_available_styles()

        card = StyleSelectorCard()
        card.refresh_styles(available_styles, self.style_manager)
        card.style_selected.connect(self._on_style_changed)

        return card

    def _create_frame_config_card(self) -> ExpandSettingCard:
        """Tab 3: 相框配置（背景、字体等，样式选择已独立为 Tab 2）"""
        card = ExpandGroupSettingCard(FluentIcon.PHOTO, "相框配置", "背景填充、字体字重等设置")

        # 背景填充
        bg_choices = BackgroundFillManager.get_choices()
        self.bg_fill_keys = {v: k for k, v in bg_choices.items()}  # label -> key
        self.combo_bg_fill = ComboBox()
        self.combo_bg_fill.addItems(list(bg_choices.keys()))
        default_bg_label = BackgroundFillManager.get_label(BackgroundFillManager.DEFAULT_FILL)
        if default_bg_label in bg_choices:
            self.combo_bg_fill.setCurrentText(default_bg_label)
        self.combo_bg_fill.setMinimumWidth(200)
        card.addGroup(FluentIcon.CHECKBOX, "背景填充样式", "选择背景填充方式", self.combo_bg_fill, 2)

        # 背景增强
        self.chk_enhance = SwitchButton()
        self.chk_enhance.setChecked(True)
        card.addGroup(FluentIcon.CHECKBOX, "背景增强", "仅高斯模糊背景有效", self.chk_enhance)

        # 字重
        self.combo_font_weight = ComboBox()
        self.combo_font_weight.addItems(["中等 (Medium)", "常规 (Regular)", "细体 (Light)"])
        self.combo_font_weight.setCurrentIndex(0)
        self.combo_font_weight.setMinimumWidth(200)
        card.addGroup(FluentIcon.FONT, "字重", "选择文字粗细", self.combo_font_weight, 2)

        return card

    def _create_personalization_card(self) -> ExpandSettingCard:
        """Tab 3: 个性化配置"""
        card = ExpandGroupSettingCard(FluentIcon.PEOPLE, "个性化配置", "作者、地点和自定义文本")

        # 作者姓名
        self.edit_author = LineEdit()
        self.edit_author.setPlaceholderText("请输入作者姓名")
        card.addGroup(FluentIcon.PEOPLE, "作者姓名", "将显示在相框中", self.edit_author, 3)

        # 拍摄地点
        self.edit_location = LineEdit()
        self.edit_location.setPlaceholderText("请输入拍摄地点")
        card.addGroup(FluentIcon.HOME, "拍摄地点", "将显示在相框中", self.edit_location, 3)

        # GPS 替换
        self.chk_use_gps = SwitchButton()
        card.addGroup(FluentIcon.GLOBE, "GPS 替换", "使用 EXIF 中的 GPS 数据", self.chk_use_gps)

        # 自定义文本（始终可见，由样式配置控制启用状态）
        self.edit_custom_text = LineEdit()
        self.edit_custom_text.setPlaceholderText("输入自定义文本...")
        card.addGroup(FluentIcon.EDIT, "自定义文本", "样式启用时可输入", self.edit_custom_text, 3)

        return card

    def _create_shot_info_card(self) -> ExpandSettingCard:
        """Tab 4: 拍摄信息配置"""
        card = ExpandGroupSettingCard(FluentIcon.CAMERA, "拍摄信息配置", "拍摄时间、镜头和 LOGO 设置")

        # 拍摄时间
        self.combo_timestamp = ComboBox()
        self.combo_timestamp.addItems(["显示日期与时刻", "只显示日期", "不显示时间"])
        self.combo_timestamp.setCurrentIndex(0)
        card.addGroup(FluentIcon.DATE_TIME, "拍摄时间", "控制相框中显示的拍摄时间信息", self.combo_timestamp, 1)

        # 镜头显示
        self.combo_lens_display = ComboBox()
        self.combo_lens_display.addItems(["相机+镜头", "只显示相机", "只显示镜头"])
        self.combo_lens_display.setCurrentIndex(0)
        card.addGroup(FluentIcon.CAMERA, "镜头显示", "控制相框中显示的设备信息", self.combo_lens_display, 1)

        # 短版镜头名
        self.chk_short_lens = SwitchButton()
        card.addGroup(FluentIcon.CHECKBOX, "短版镜头名", "使用简洁的镜头名称", self.chk_short_lens)

        # LOGO
        self.combo_logo = ComboBox()
        self.combo_logo.addItems(["自动匹配", "无"])
        # 读取 assets/logos/ 目录下的实际 logo 文件
        logos = self.logo_selector.scan_logos()
        self.combo_logo.addItems(logos)
        card.addGroup(FluentIcon.IMAGE_EXPORT, "LOGO", "根据相机品牌自动匹配", self.combo_logo, 3)

        return card

    def _create_watermark_card(self) -> ExpandSettingCard:
        """Tab 5: 文本水印"""
        card = ExpandGroupSettingCard(FluentIcon.EDIT, "文本水印", "添加自定义文字水印")

        # 启用水印
        self.chk_watermark = SwitchButton()
        card.addGroup(FluentIcon.CHECKBOX, "启用水印", "开启后可在图片上添加文字", self.chk_watermark)

        # 水印内容
        self.edit_watermark_text = LineEdit()
        self.edit_watermark_text.setPlaceholderText("输入水印文字...")
        card.addGroup(FluentIcon.EDIT, "水印内容", "输入要显示的文字", self.edit_watermark_text, 3)

        # 水印位置
        self.combo_wm_position = ComboBox()
        self.combo_wm_position.addItems([
            "左上", "顶部居中", "右上",
            "左下", "底部居中", "右下",
        ])
        self.combo_wm_position.setCurrentIndex(4)  # 默认底部居中
        card.addGroup(FluentIcon.MARKET, "水印位置", "选择水印显示位置", self.combo_wm_position, 1)

        # 不透明度
        self.slider_opacity = Slider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(0, 100)
        self.slider_opacity.setValue(50)
        card.addGroup(FluentIcon.ZOOM, "不透明度", "调节水印透明程度", self.slider_opacity)

        # 颜色
        self.combo_wm_color = ComboBox()
        self.combo_wm_color.addItems(["白色", "黑色"])
        card.addGroup(FluentIcon.PALETTE, "水印颜色", "选择水印文字颜色", self.combo_wm_color, 1)

        return card

    # ════════════════════════════════════════════════════════
    #  样式变更响应
    # ════════════════════════════════════════════════════════

    def _on_style_changed(self, style_name: str):
        """相框样式下拉框变化时，更新依赖样式的控件"""
        self._update_style_dependent_controls()

    def _update_style_dependent_controls(self):
        """根据当前选中的样式配置，更新自定义文本和LOGO的启用状态"""
        style_name = self.style_selector_card.current_style
        if not style_name:
            return

        config = self.style_manager.get_style_config(style_name)
        if not config:
            return

        layout = config.get('layout', {})
        custom_text_cfg = layout.get('custom_text', {})
        logo_cfg = config.get('logo', {})

        # 自定义文本：始终可见，仅控制启用状态
        ct_enabled = isinstance(custom_text_cfg, dict) and custom_text_cfg.get('enabled', False)
        self.edit_custom_text.setEnabled(ct_enabled)

        # LOGO：始终可见，仅控制启用状态
        logo_enabled = isinstance(logo_cfg, dict) and logo_cfg.get('enabled', False)

        # 自定义背景填充色：若样式指定了背景色，禁用 GUI 的背景样式选择
        custom_bg_color = config.get('colors', {}).get('custom_bg_color')
        if custom_bg_color:
            self.combo_bg_fill.setEnabled(False)
            self.chk_enhance.setEnabled(False)
            self.combo_bg_fill.setToolTip(f'背景颜色由样式配置指定: {custom_bg_color}')
        else:
            self.combo_bg_fill.setEnabled(True)
            self.chk_enhance.setEnabled(True)
            self.combo_bg_fill.setToolTip('')

        logger.debug(f"样式变更: {style_name}, 自定义文本: {ct_enabled}, LOGO: {logo_enabled}")

    # ════════════════════════════════════════════════════════
    #  事件处理方法
    # ════════════════════════════════════════════════════════

    def _on_add_files(self):
        """点击\"添加图片\"按钮"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图片文件",
            "",
            "图片文件 (*.jpg *.jpeg *.png *.tiff *.tif *.bmp *.webp);;所有文件 (*)",
        )
        if file_paths:
            self._load_files(file_paths)

    def _load_files(self, file_paths: list[str]):
        """加载图片文件到胶片栏"""
        import io
        import os

        n = len(file_paths)
        tip = self._show_progress('加载中', f'正在加载第 1/{n} 张图片...')

        try:
            for i, path in enumerate(file_paths):
                tip.setContent(f'正在加载第 {i+1}/{n} 张图片...')
                QApplication.processEvents()

                try:
                    item = FileItem(file_path=path)

                    with open(path, 'rb') as f:
                        item.file_bytes = f.read()

                    item.file_name = os.path.basename(path)

                    pil_img = PILImage.open(io.BytesIO(item.file_bytes))
                    item.width, item.height = pil_img.size

                    item.thumbnail = self._create_thumbnail(pil_img)

                    try:
                        item.exif_data = self.exif_helper.extract_exif_data(item.file_bytes)
                        if item.exif_data:
                            item.display_data = self.exif_helper.get_display_data(item.exif_data)
                        item.file_info = self.exif_helper.get_file_info(pil_img)
                    except Exception as e:
                        logger.warning(f"EXIF 提取失败 {item.file_name}: {e}")

                    self.file_items.append(item)
                    self._add_filmstrip_item(item)

                except Exception as e:
                    logger.error(f"加载文件失败 {path}: {e}")
                    InfoBar.error(
                        title="加载失败",
                        content=f"无法加载文件: {os.path.basename(path)}",
                        parent=self,
                    )

            self._update_button_states()
            if self.file_items and self.current_index == -1:
                self._select_item(0)

            tip.setContent('加载完成')
            tip.setState(True)
            QTimer.singleShot(1500, tip.hide)
            logger.info(f"加载了 {n} 个文件")

        except Exception as e:
            logger.error(f"加载文件异常: {e}")
            tip.setContent('加载出错')
            tip.setState(False)
            QTimer.singleShot(1500, tip.hide)
            raise

    def _convert_to_srgb(self, pil_img):
        """将 PIL 图片从嵌入的 ICC 色彩空间转换到 sRGB

        Args:
            pil_img: PIL Image 对象

        Returns:
            转换后的 PIL Image（RGB 模式，sRGB 色彩空间）
        """
        icc = pil_img.info.get('icc_profile')
        if icc:
            try:
                return ImageCms.profileToProfile(
                    pil_img,
                    io.BytesIO(icc),
                    ImageCms.createProfile('sRGB'),
                    outputMode='RGB',
                    renderingIntent=ImageCms.Intent.PERCEPTUAL,
                )
            except Exception:
                # ICC 转换失败时回退到原始图片
                pass
        return pil_img

    def _create_thumbnail(self, pil_img, height: int = 80) -> QImage:
        """从 PIL 图片创建缩略图（含 ICC 色彩转换）

        Args:
            pil_img: PIL Image 对象
            height: 缩略图高度（像素）

        Returns:
            QImage 缩略图
        """
        # ICC 色彩空间转换
        pil_img = self._convert_to_srgb(pil_img)

        # 计算等比缩放尺寸
        w, h = pil_img.size
        ratio = height / h
        new_w = int(w * ratio)
        new_h = height

        # 缩放
        pil_thumb = pil_img.copy()
        pil_thumb.thumbnail((new_w, new_h), PILImage.Resampling.LANCZOS)

        # 转换为 QImage
        if pil_thumb.mode != 'RGB':
            pil_thumb = pil_thumb.convert('RGB')
        data = pil_thumb.tobytes()
        q_img = QImage(data, pil_thumb.width, pil_thumb.height, 3 * pil_thumb.width, QImage.Format.Format_RGB888)
        q_img.setColorSpace(QColorSpace.NamedColorSpace.SRgb)
        return q_img.copy()  # copy() 确保数据独立

    def _add_filmstrip_item(self, item: FileItem):
        """在胶片栏中添加一个缩略图项"""
        # 动态计算缩略图尺寸（基于胶片栏可用高度）
        available_height = max(60, self.filmstrip_scroll.height() - 40)
        thumb_h = min(available_height, 120)
        thumb_w = int(thumb_h * 1.25)

        thumb_label = QLabel()
        thumb_label.setFixedSize(thumb_w, thumb_h)
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_thumb_style(thumb_label, False)

        if item.thumbnail:
            pixmap = QPixmap.fromImage(item.thumbnail)
            thumb_label.setPixmap(
                pixmap.scaled(thumb_w - 4, thumb_h - 4,
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
            )

        # 文件名标签
        name_label = CaptionLabel(item.file_name)
        name_label.setMaximumWidth(thumb_w)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 包装容器
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(4, 2, 4, 2)
        container_layout.setSpacing(2)
        container_layout.addWidget(thumb_label)
        container_layout.addWidget(name_label)

        # 记录缩略图标签引用（用于动态缩放）
        self.filmstrip_labels.append(thumb_label)

        # 点击事件（动态查找索引，避免删除图片后索引错位）
        thumb_label.mousePressEvent = lambda e, lbl=thumb_label: self._select_item_by_label(lbl)

        # 右键菜单（同样使用动态索引）
        container.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        container.customContextMenuRequested.connect(
            lambda pos, lbl=thumb_label: self._show_filmstrip_context_menu(pos, lbl)
        )

        # 插入到 stretch 之前
        self.filmstrip_layout.insertWidget(self.filmstrip_layout.count() - 1, container)

    def _on_splitter_moved(self, pos, index):
        """任意分割器拖拽手柄后重新缩放所有区域"""
        self._do_rescale_all()

    def _do_rescale_all(self):
        """重新缩放胶片栏缩略图和预览图"""
        self._rescale_filmstrip_thumbnails()
        if 0 <= self.current_index < len(self.file_items):
            self._update_preview(self.file_items[self.current_index])

    def resizeEvent(self, event):
        """窗口大小变化时重新缩放所有内容"""
        super().resizeEvent(event)
        # 延迟执行，以确保全部子 widget 布局更新完毕
        QTimer.singleShot(0, self._do_rescale_all)

    def _rescale_filmstrip_thumbnails(self):
        """根据胶片栏当前高度重新缩放所有缩略图"""
        if not self.filmstrip_labels or not self.file_items:
            return

        available_height = max(60, self.filmstrip_scroll.height() - 40)
        thumb_h = min(available_height, 120)
        thumb_w = int(thumb_h * 1.25)

        for i, label in enumerate(self.filmstrip_labels):
            if i >= len(self.file_items):
                break
            item = self.file_items[i]
            if item.thumbnail:
                label.setFixedSize(thumb_w, thumb_h)
                pixmap = QPixmap.fromImage(item.thumbnail)
                label.setPixmap(
                    pixmap.scaled(thumb_w - 4, thumb_h - 4,
                                  Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
                )

    def _apply_custom_style(self, widget, lightQss, darkQss):
        """设置自定义主题样式并确保新 widget 首次即生效"""
        _qfw_setCustomStyleSheet(widget, lightQss, darkQss)
        addStyleSheet(widget, CustomStyleSheet(widget))

    def _set_thumb_style(self, label: QLabel, selected: bool):
        """设置缩略图边框样式：选中=蓝色，未选=灰色（自动适配 light/dark 主题）"""
        if selected:
            self._apply_custom_style(label,
                lightQss=self._STYLE_THUMB_SELECTED['light'],
                darkQss=self._STYLE_THUMB_SELECTED['dark'],
            )
        else:
            self._apply_custom_style(label,
                lightQss=self._STYLE_THUMB_NORMAL['light'],
                darkQss=self._STYLE_THUMB_NORMAL['dark'],
            )

    def _apply_preview_placeholder_style(self):
        """为预览区 QLabel 设置占位样式（自动适配 light/dark 主题）"""
        self._apply_custom_style(self.preview_label,
            lightQss=(
                "QLabel {"
                " border: 2px dashed #ccc;"
                " border-radius: 8px;"
                " color: #888;"
                " font-size: 14px;"
                " background-color: #fafafa;"
                " }"
            ),
            darkQss=(
                "QLabel {"
                " border: 2px dashed #555;"
                " border-radius: 8px;"
                " color: #999;"
                " font-size: 14px;"
                " background-color: #282828;"
                " }"
            ),
        )

    def _select_item(self, index: int):
        """选中胶片栏中的某个项"""
        if index < 0 or index >= len(self.file_items):
            return

        # 取消旧高亮
        if 0 <= self.current_index < len(self.filmstrip_labels):
            self._set_thumb_style(self.filmstrip_labels[self.current_index], False)

        self.current_index = index
        item = self.file_items[index]

        # 新高亮
        if 0 <= index < len(self.filmstrip_labels):
            self._set_thumb_style(self.filmstrip_labels[index], True)

        # 更新预览
        self._update_preview(item)

        # 更新 EXIF 信息
        self._update_exif_info(item)

        # 更新按钮状态
        self._update_button_states()

        logger.debug(f"选中文件: {item.file_name}")

    def _update_preview(self, item: FileItem):
        """更新预览窗口显示（使用缓存 QPixmap 避免重复渲染）"""
        # 生成或读取缓存
        if item.cached_pixmap is None:
            if item.result_path:
                # 使用 PIL 加载大图，避免 Qt QImageIOHandler 的 256MB 分配上限
                pil_img = PILImage.open(item.result_path)
                pil_img = self._convert_to_srgb(pil_img)
                if pil_img.mode != 'RGB':
                    pil_img = pil_img.convert('RGB')
                data = pil_img.tobytes()
                q_img = QImage(data, pil_img.width, pil_img.height,
                               3 * pil_img.width, QImage.Format.Format_RGB888)
                q_img.setColorSpace(QColorSpace.NamedColorSpace.SRgb)
                pixmap = QPixmap.fromImage(q_img)
            elif item.file_bytes:
                pil_img = PILImage.open(io.BytesIO(item.file_bytes))
                pil_img = self._convert_to_srgb(pil_img)
                if pil_img.mode != 'RGB':
                    pil_img = pil_img.convert('RGB')
                data = pil_img.tobytes()
                q_img = QImage(data, pil_img.width, pil_img.height,
                               3 * pil_img.width, QImage.Format.Format_RGB888)
                q_img.setColorSpace(QColorSpace.NamedColorSpace.SRgb)
                pixmap = QPixmap.fromImage(q_img)
            else:
                return
            item.cached_pixmap = pixmap
        else:
            pixmap = item.cached_pixmap

        # 快速缩放缓存图到预览标签的实际尺寸
        if not pixmap.isNull():
            label_size = self.preview_label.size()
            scaled = pixmap.scaled(
                label_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.preview_label.setPixmap(scaled)
            self._apply_custom_style(self.preview_label,
                lightQss="QLabel { border: none; background-color: #fafafa; }",
                darkQss="QLabel { border: none; background-color: #282828; }",
            )
            self.preview_label.setText("")

    def _update_filmstrip_thumbnail(self, item: FileItem):
        """处理完成后更新胶片栏缩略图为效果图"""
        if item.result_path and item.result_thumbnail is None:
            result_img = PILImage.open(item.result_path)
            item.result_thumbnail = self._create_thumbnail(result_img)
            # 更新对应的胶片栏 label
            idx = self.file_items.index(item)
            if idx < len(self.filmstrip_labels):
                label = self.filmstrip_labels[idx]
                pixmap = QPixmap.fromImage(item.result_thumbnail)
                available_height = max(60, self.filmstrip_scroll.height() - 40)
                thumb_h = min(available_height, 120)
                thumb_w = int(thumb_h * 1.25)
                label.setPixmap(
                    pixmap.scaled(thumb_w - 4, thumb_h - 4,
                                  Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
                )
                # 保持高亮：选中=蓝，否则绿
                is_selected = (idx == self.current_index)
                if is_selected:
                    self._set_thumb_style(label, True)
                else:
                    self._apply_custom_style(label,
                        lightQss=self._STYLE_THUMB_PROCESSED['light'],
                        darkQss=self._STYLE_THUMB_PROCESSED['dark'],
                    )

    def _update_exif_info(self, item: FileItem):
        """更新 EXIF 信息面板"""
        if not item.file_info or not item.display_data:
            self.exif_file.setText("文件: <b>—</b>")
            self.exif_camera.setText("相机: <b>—</b>")
            self.exif_lens.setText("镜头: <b>—</b>")
            self.exif_focal.setText("焦距: <b>—</b>")
            self.exif_aperture.setText("光圈: <b>—</b>")
            self.exif_shutter.setText("快门: <b>—</b>")
            self.exif_iso.setText("ISO: <b>—</b>")
            return

        fi = item.file_info
        dd = item.display_data

        # 第一行
        fmt = fi.get('format', '')
        cs = fi.get('color_space', '').strip()
        w = fi.get('width', '')
        h = fi.get('height', '')
        self.exif_file.setText(f"文件: <b>{fmt} | {cs} | {w}×{h} px</b>")

        cam = dd.get('camera_combined', '')
        self.exif_camera.setText(f"相机: <b>{cam}</b>" if cam else "相机: <b>—</b>")

        lens = dd.get('lens_model', '')
        self.exif_lens.setText(f"镜头: <b>{lens}</b>" if lens else "镜头: <b>—</b>")

        # 第二行
        fl = dd.get('raw_focal_length_35mm', '') or dd.get('raw_focal_length', '')
        self.exif_focal.setText(f"焦距: <b>{fl}mm</b>" if fl else "焦距: <b>—</b>")

        ap = dd.get('raw_aperture', '')
        self.exif_aperture.setText(f"光圈: <b>f/{ap}</b>" if ap else "光圈: <b>—</b>")

        ss = dd.get('raw_shutter_speed', '')
        self.exif_shutter.setText(f"快门: <b>{ss}s</b>" if ss else "快门: <b>—</b>")

        iso = dd.get('raw_iso', '')
        self.exif_iso.setText(f"ISO: <b>{iso}</b>" if iso else "ISO: <b>—</b>")

    def _update_button_states(self):
        """根据当前状态更新按钮启用/禁用"""
        has_items = len(self.file_items) > 0
        has_unprocessed = any(not item.is_processed for item in self.file_items)
        has_processed = any(item.is_processed for item in self.file_items)

        current_item = self.file_items[self.current_index] if 0 <= self.current_index < len(self.file_items) else None
        current_is_processed = current_item is not None and current_item.is_processed

        self.btn_export_current.setEnabled(current_is_processed)
        self.btn_export_all.setEnabled(has_processed)
        self.btn_generate.setEnabled(self.current_index >= 0)
        self.filmstrip_title.setText(
            f"胶片栏 — {len(self.file_items)} 张图片"
            if self.file_items else
            "胶片栏 — 将图片拖拽到此处或点击\"添加图片\"按钮加载"
        )

    def _on_export_current(self):
        """导出当前选中的图片到用户选择的位置"""
        if self.current_index < 0 or self.current_index >= len(self.file_items):
            return

        item = self.file_items[self.current_index]
        if not item.is_processed or not item.result_path or not os.path.exists(item.result_path):
            InfoBar.warning(title="提示", content="请先点击\"生成相框\"", parent=self)
            return

        # 弹出文件保存对话框
        ext = Path(item.result_path).suffix
        default_name = Path(item.file_name).stem + '_frame' + ext
        path, _ = QFileDialog.getSaveFileName(
            self, "保存图片", default_name,
            "JPEG 图片 (*.jpg);;PNG 图片 (*.png)"
        )
        if path:
            shutil.copy2(item.result_path, path)
            InfoBar.success(title="导出成功", content=f"已保存到: {path}", parent=self)
            logger.info(f"导出当前图像: {item.file_name} → {path}")

    def _show_progress(self, title: str, content: str) -> StateToolTip:
        """创建并显示带标准样式的进度通知"""
        tip = StateToolTip(title, content, self)
        tip.titleLabel.move(36, 8)
        tip.contentLabel.move(36, 28)
        tip.closeButton.move(tip.width() - 24, 22)
        tip.setFixedHeight(58)
        tip.show()
        QApplication.processEvents()
        return tip

    def _on_generate_frame(self):
        """生成相框：处理当前选中图片"""
        if self.current_index < 0 or self.current_index >= len(self.file_items):
            return

        # 显示处理状态提示
        self.state_tooltip = self._show_progress('处理中', '正在生成相框...')

        try:
            item = self.file_items[self.current_index]

            # 1. 从 GUI 控件收集配置
            bg_options = BackgroundFillManager.get_choices()
            bg_key = bg_options.get(self.combo_bg_fill.currentText(), BackgroundFillManager.DEFAULT_FILL)
            fw_map = {"中等 (Medium)": "medium", "常规 (Regular)": "regular", "细体 (Light)": "light"}
            fw_key = fw_map.get(self.combo_font_weight.currentText(), "medium")
            lens_map = {"相机+镜头": "combined", "只显示相机": "camera_only", "只显示镜头": "lens_only"}
            lens_key = lens_map.get(self.combo_lens_display.currentText(), "combined")
            ts_map = {"显示日期与时刻": "full", "只显示日期": "date_only", "不显示时间": "hide"}
            ts_mode = ts_map.get(self.combo_timestamp.currentText(), "full")

            # GPS 替换逻辑
            gps_on = self.chk_use_gps.isChecked()
            gps_str = item.exif_data.get('gps', '') if item.exif_data else ''
            location = gps_str if (gps_on and gps_str) else self.edit_location.text()

            # LOGO 选择逻辑
            logo_opt = self.combo_logo.currentText()
            logo_filename = None
            if logo_opt == "无":
                logo_filename = ""
            elif logo_opt != "自动匹配":
                logo_filename = logo_opt
            else:
                brand = ExifHelper.get_camera_brand(item.exif_data) if item.exif_data else None
                if brand:
                    logo_filename = self.logo_selector.auto_match_logo(
                        brand, is_dark_bg=BackgroundFillManager.is_dark_bg(bg_key)
                    )

            # 水印装饰
            decorations = []
            if self.chk_watermark.isChecked() and self.edit_watermark_text.text():
                pos_map = {"左上": "top-left", "右上": "top-right", "左下": "bottom-left",
                           "右下": "bottom-right", "顶部居中": "top-center", "底部居中": "bottom-center"}
                col_map = {"白色": (255, 255, 255), "黑色": (0, 0, 0)}
                decorations.append({
                    'type': 'watermark',
                    'params': {
                        'text': self.edit_watermark_text.text(),
                        'position': pos_map.get(self.combo_wm_position.currentText(), 'bottom-right'),
                        'opacity': self.slider_opacity.value(),
                        'color': col_map.get(self.combo_wm_color.currentText(), (255, 255, 255))
                    }
                })

            # 2. 创建临时文件并调用 ImageProcessor
            suffix = os.path.splitext(item.file_name)[1]
            input_path = self.temp_manager.create_temp_file(suffix=suffix)
            output_ext = ".jpg" if self.combo_output_format.currentText() == "JPEG" else ".png"
            output_path = self.temp_manager.create_temp_file(suffix=output_ext)

            # 写入输入文件
            with open(input_path, 'wb') as f:
                f.write(item.file_bytes)

            # 调用处理器
            processor = ImageProcessor()
            success = processor.process(
                input_path=input_path,
                output_path=output_path,
                author=self.edit_author.text() or None,
                location=location or None,
                style_name=self.style_selector_card.current_style or "底部信息条 Bottom Bars",
                bg_fill_type=bg_key,
                decorations=decorations or None,
                font_weight=fw_key,
                logo_filename=logo_filename,
                lens_display_mode=lens_key,
                use_short_lens=self.chk_short_lens.isChecked(),
                saturation_override=None if self.chk_enhance.isChecked() else 1.0,
                custom_text=self.edit_custom_text.text() or None,
                timestamp_display_mode=ts_mode,
            )

            # 清理输入临时文件
            try:
                os.unlink(input_path)
            except OSError:
                pass

            # 3. 更新状态
            if success:
                item.is_processed = True
                item.result_path = output_path
                item.cached_pixmap = None  # 清除缓存，重新从输出图生成预览
                item.result_thumbnail = None  # 清除旧缩略图缓存，强制刷新胶片栏
                self._update_preview(item)
                self._update_filmstrip_thumbnail(item)
                self._update_button_states()
                self.state_tooltip.setContent('生成完成')
                self.state_tooltip.setState(True)
                QTimer.singleShot(1500, self.state_tooltip.hide)
                logger.info(f"生成相框成功: {item.file_name}")
            else:
                self.state_tooltip.setContent('生成失败')
                self.state_tooltip.setState(False)
                QTimer.singleShot(1500, self.state_tooltip.hide)
                logger.error(f"生成相框失败: {item.file_name}")
        except Exception as e:
            logger.error(f"生成相框异常: {e}")
            if self.state_tooltip:
                self.state_tooltip.setContent('出错')
                self.state_tooltip.setState(False)
                QTimer.singleShot(1500, self.state_tooltip.hide)

    def _on_export_all(self):
        """一键导出所有已处理的图片到用户选择的文件夹"""
        processed = [item for item in self.file_items if item.is_processed and item.result_path]
        if not processed:
            InfoBar.warning(title="提示", content="没有已处理的图片可导出", parent=self)
            return

        # 弹出文件夹选择对话框
        folder = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if not folder:
            return

        exported = 0
        for item in processed:
            try:
                ext = Path(item.result_path).suffix
                dest = os.path.join(folder, Path(item.file_name).stem + '_frame' + ext)
                shutil.copy2(item.result_path, dest)
                exported += 1
            except Exception as e:
                logger.error(f"导出失败 {item.file_name}: {e}")

        InfoBar.success(title="批量导出完成", content=f"已导出 {exported} 张图片到 {folder}", parent=self)
        logger.info(f"一键导出 {exported}/{len(processed)} 张图片 → {folder}")

    def _on_clear_all(self):
        """清空所有图片"""
        if not self.file_items:
            return

        self.file_items.clear()
        self.filmstrip_labels.clear()
        self.current_index = -1

        # 清空胶片栏 UI
        while self.filmstrip_layout.count() > 1:  # 保留最后的 stretch
            item = self.filmstrip_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 清空预览
        self.preview_label.clear()
        self.preview_label.setText("请从底部胶片栏选择图片，或拖拽图片到此处")
        self._apply_preview_placeholder_style()

        # 清空 EXIF
        self.exif_file.setText("文件: <b>—</b>")
        self.exif_camera.setText("相机: <b>—</b>")
        self.exif_lens.setText("镜头: <b>—</b>")
        self.exif_focal.setText("焦距: <b>—</b>")
        self.exif_aperture.setText("光圈: <b>—</b>")
        self.exif_shutter.setText("快门: <b>—</b>")
        self.exif_iso.setText("ISO: —")

        self._update_button_states()
        logger.info("已清空所有图片")

    def _show_filmstrip_context_menu(self, pos, label: QLabel):
        """显示胶片栏右键菜单"""
        try:
            index = self.filmstrip_labels.index(label)
        except ValueError:
            return
        menu = RoundMenu("", self)
        menu.addAction(Action(FluentIcon.DELETE, "移除此图片"))
        menu.triggered.connect(lambda action: self._remove_filmstrip_item(index))
        menu.exec(label.mapToGlobal(pos))

    def _select_item_by_label(self, label: QLabel):
        """通过缩略图标签查找当前索引并选中"""
        try:
            idx = self.filmstrip_labels.index(label)
            if idx != self.current_index:
                self._select_item(idx)
        except ValueError:
            pass

    def _remove_filmstrip_item(self, index: int):
        """从胶片栏中移除指定图片"""
        if index < 0 or index >= len(self.file_items):
            return

        # 从布局中移除 UI
        item = self.filmstrip_layout.takeAt(index)
        if item and item.widget():
            item.widget().deleteLater()

        # 从数据中移除
        self.file_items.pop(index)
        self.filmstrip_labels.pop(index)

        # 更新选中索引
        if self.current_index == index:
            self.current_index = -1
            self.preview_label.clear()
            self.preview_label.setText("请从底部胶片栏选择图片，或拖拽图片到此处")
            self._apply_preview_placeholder_style()
        elif self.current_index > index:
            self.current_index -= 1

        self._update_button_states()
        logger.debug(f"已移除图片: 索引 {index}")

    def cleanup(self):
        """清理页面资源（由 MainWindow.closeEvent 调用）"""
        self.file_items.clear()
        self.filmstrip_labels.clear()
        self.current_index = -1
        self.temp_manager.cleanup()
        logger.debug("图像处理页面资源已清理")

    def save_config(self):
        """收集当前控件值并保存到 ConfigManager（由 MainWindow.closeEvent 调用）"""
        # 作者名
        if self.edit_author.text():
            default_config_manager.save_user_author(self.edit_author.text())
        # 最近使用配置
        default_config_manager.save_last_used_settings({
            'style_name': self.style_selector_card.current_style or "底部信息条 Bottom Bars",
            'output_format': self.combo_output_format.currentText(),
            'bg_fill': self.combo_bg_fill.currentText(),
            'enhance_background': self.chk_enhance.isChecked(),
            'font_weight': self.combo_font_weight.currentText(),
            'timestamp_display': self.combo_timestamp.currentText(),
        })
        logger.debug("配置已保存")

    def _load_saved_config(self):
        """加载已保存的配置到控件"""
        # 作者名
        saved_author = default_config_manager.get_saved_author()
        if saved_author:
            self.edit_author.setText(saved_author)
        # 最近使用配置
        saved = default_config_manager.get_last_used_settings()
        if not saved:
            return
        # 先恢复样式（可能触发 _on_style_changed 更新自定义文本/LOGO 启用状态）
        if 'style_name' in saved:
            self.style_selector_card.set_current_style(saved['style_name'])
        if 'output_format' in saved:
            idx = self.combo_output_format.findText(saved['output_format'])
            if idx >= 0:
                self.combo_output_format.setCurrentIndex(idx)
        if 'bg_fill' in saved:
            items = [self.combo_bg_fill.itemText(i) for i in range(self.combo_bg_fill.count())]
            if saved['bg_fill'] in items:
                self.combo_bg_fill.setCurrentText(saved['bg_fill'])
        if 'enhance_background' in saved:
            self.chk_enhance.setChecked(saved['enhance_background'])
        if 'font_weight' in saved:
            idx = self.combo_font_weight.findText(saved['font_weight'])
            if idx >= 0:
                self.combo_font_weight.setCurrentIndex(idx)
        if 'timestamp_display' in saved:
            idx = self.combo_timestamp.findText(saved['timestamp_display'])
            if idx >= 0:
                self.combo_timestamp.setCurrentIndex(idx)

    def refresh_style_list(self):
        """刷新样式网格（样式编辑器中新建/保存样式后调用）"""
        styles = self.style_manager.get_available_styles()
        self.style_selector_card.refresh_styles(styles, self.style_manager)

    def showEvent(self, event):
        """页面显示时刷新样式列表"""
        super().showEvent(event)
        self.refresh_style_list()
