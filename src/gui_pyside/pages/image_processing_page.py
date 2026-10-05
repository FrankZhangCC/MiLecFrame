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
import hashlib
import logging
import os
import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QSplitter,
    QFileDialog, QApplication, QSizePolicy, QLineEdit,
)
from PySide6.QtCore import Qt, Signal, QTimer, QEvent, QObject
from PySide6.QtGui import QImage, QPixmap, QColorSpace, QDragEnterEvent, QDropEvent, QColor, QKeySequence, QShortcut

from qfluentwidgets import (
    PrimaryPushButton, PushButton, TransparentPushButton,
    StrongBodyLabel, BodyLabel, SubtitleLabel, CaptionLabel,
    InfoBar,
    ExpandSettingCard, ExpandGroupSettingCard, ComboBox,
    FluentIcon, SwitchButton, LineEdit, Slider,
    SmoothScrollArea, StateToolTip, RoundMenu, Action, ScrollArea,
    ExpandLayout,
)
from qfluentwidgets.common.style_sheet import (
    setCustomStyleSheet as _qfw_setCustomStyleSheet,
    addStyleSheet, CustomStyleSheet,
)

from ..models.file_item import FileItem, compute_cache_key
from ..utils.temp_manager import TempManager
from ..widgets.style_selector_card import StyleSelectorCard
from ..widgets.wheel_filter import HorizontalWheelFilter
from ..utils.image_convert import pil_to_qimage, filmstrip_thumb_size
# G2 拆分：六张配置卡构建与渲染配置收集收敛于独立模块（控件仍归属
# 页面属性，本页不重复定义）；下拉选项表与历史别名表同源于此
from .image_processing_config_cards import (
    create_output_settings_card, create_style_selection_card,
    create_frame_config_card, create_personalization_card,
    create_shot_info_card, create_watermark_card,
    collect_render_options, normalize_option_rows, PORTRAIT_ADAPTATION_ITEMS,
    LENS_NAME_ITEMS,
    _LEGACY_TEXT_ALIASES,
)
# 样式选项能力（计划 T3/T4）：状态评估模型与控件绑定
from ..models.style_option_state import (
    PhotoFacts, evaluate_style_options,
)
from ..utils import style_option_bindings
from src.utils.exif_helper import ExifHelper
from src.utils.logo_selector import LogoSelector
from src.utils.background_fill import BackgroundFillManager
from src.utils.config_manager import default_config_manager
from src.core.image_processor import ImageProcessor
from src.core.blur_cache import PreparedBlurLRU
# 输出导出服务（G2 拆分：校验与发布流程收敛于 utils/export_service；
# GUI 只调用服务，不自行拼接或修复任何元数据字段）
from src.utils.export_service import export_verified, OutputMetadataError
# 竖图方向适配（方案 docs/plans/PORTRAIT_ORIENTATION_ADAPTATION_PLAN.md §6）：
# 枚举值单点来源于 utils 工具模块，GUI 不自定义第二份合法值集合
from src.utils.orientation_adaptation import (
    ADAPT_DEFAULT, ADAPT_NONE, ADAPT_CLOCKWISE, ADAPT_COUNTERCLOCKWISE,
    USER_ADAPTATION_VALUES, validate_style_default,
)
from PIL import Image as PILImage
from PIL import ImageCms
from PIL import ImageOps as PILImageOps
import io

logger = logging.getLogger(__name__)

# 图片文件扩展名白名单（与 _on_add_files 文件对话框过滤器一致）
_ALLOWED_EXT = ('.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.webp')


# ── 下拉框选项与历史别名表：定义单点在 image_processing_config_cards
# （G2/G3：稳定 key 选项表随配置卡构建收敛；页面经下方 import 引用）


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

        # ── 二级模糊缓存生命周期（页面级持有，跨生成复用卷积） ──
        # 页面级可复用处理器：替代每次点击新建（否则二级缓存随处理器
        # 一起被丢弃，跨生成复用无从谈起）
        self._processor: ImageProcessor = None
        # 页面级 LRU：按 nbytes 预算（默认 64 MiB）缓存工作分辨率卷积
        self._blur_lru = PreparedBlurLRU()
        # G3/D5：历史文本别名表 = 静态表 ∪ bg_fill 注册表反查
        # （get_choices 返回 {label: key}，旧 config 的 bg label
        # 正好可经此迁移；注册表 label 文案调整后需把旧 label
        # 追加进 _LEGACY_TEXT_ALIASES）
        self._legacy_aliases = {
            **_LEGACY_TEXT_ALIASES,
            **BackgroundFillManager.get_choices(),
        }

        # ── 数据 ──
        self.file_items: list[FileItem] = []  # 胶片栏中的所有文件
        self.current_index: int = -1  # 当前选中的文件索引
        self.filmstrip_labels: list[QLabel] = []  # 胶片栏缩略图标签（用于动态缩放）
        self.state_tooltip = None  # 处理状态提示

        # ── 样式选项状态（计划 §8.1/§8.2：单一刷新入口的工作集）──
        # 页面缓存的能力快照：输入/照片变化不重读（§5.4，零 IO）；
        # 切样式 / refresh / showEvent / 生成前才重读
        self._style_capabilities = None        # StyleCapabilitySnapshot
        self._style_capabilities_for = None    # 快照对应的样式名
        self._style_evaluation = None          # 最近一次 OptionEvaluation
        # 恢复配置期间暂缓中间响应（§8.2：全部卡片创建后再连接和刷新）
        self._restoring_config = False

        # ── 初始化 UI ──
        self._setup_ui()

        # 全部卡片创建完成后连接选项信号（§8.2：信号必须等控件就绪）
        self._connect_option_signals()

        # 加载已保存的作者名和配置（restoring 包裹：暂缓中间响应，
        # 结束后统一重算，含无 saved 配置的路径）
        self._restoring_config = True
        try:
            self._load_saved_config()
        finally:
            self._restoring_config = False
        self._refresh_style_option_state(reload_snapshot=True)

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
        self.output_settings_card = create_output_settings_card(self)
        self.output_settings_card.setParent(config_container)
        card_layout.addWidget(self.output_settings_card)

        # ── Tab 2: 样式选择（缩略图网格） ──
        self.style_selector_card = create_style_selection_card(self)
        self.style_selector_card.setParent(config_container)
        card_layout.addWidget(self.style_selector_card)

        # ── Tab 3: 相框配置 ──
        self.frame_config_card = create_frame_config_card(self)
        self.frame_config_card.setParent(config_container)
        card_layout.addWidget(self.frame_config_card)

        # ── Tab 3: 个性化配置 ──
        self.personalization_card = create_personalization_card(self)
        self.personalization_card.setParent(config_container)
        card_layout.addWidget(self.personalization_card)

        # ── Tab 4: 拍摄信息配置 ──
        self.shot_info_card = create_shot_info_card(self)
        self.shot_info_card.setParent(config_container)
        card_layout.addWidget(self.shot_info_card)

        # ── Tab 5: 文本水印 ──
        self.watermark_card = create_watermark_card(self)
        self.watermark_card.setParent(config_container)
        card_layout.addWidget(self.watermark_card)

        # 跨卡片对齐（计划 v14）：全部卡片创建完成后统一标签列宽与
        # 行边距，使各行控件左缘/右缘跨卡逐像素对齐
        normalize_option_rows(self)

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
        self.filmstrip_scroll.viewport().installEventFilter(HorizontalWheelFilter(self.filmstrip_scroll))

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
        self.filmstrip_scroll.viewport().installEventFilter(HorizontalWheelFilter(self.filmstrip_scroll))

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

        # 输出格式（G3：userData 绑定稳定 key）
        self.combo_output_format = ComboBox()
        for _text, _key in OUTPUT_FORMAT_ITEMS:
            self.combo_output_format.addItem(_text, userData=_key)
        self.combo_output_format.setCurrentIndex(0)
        card.addGroup(FluentIcon.DOWNLOAD, "输出格式", "JPEG 适合照片，PNG 适合透明背景", self.combo_output_format, 1)

        return card

    def _create_style_selection_card(self) -> ExpandSettingCard:
        """Tab 2: 样式选择（缩略图网格）"""
        from src.frame_styles.style_manager import StyleManager
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

        # 背景填充（G3：userData 绑定稳定 fill key，显示 label 仅作文案；
        # 旧代码的 bg_fill_keys 反查表由 userData 取代）
        bg_choices = BackgroundFillManager.get_choices()
        self.combo_bg_fill = ComboBox()
        for _label, _key in bg_choices.items():
            self.combo_bg_fill.addItem(_label, userData=_key)
        self.combo_bg_fill.setCurrentIndex(
            self.combo_bg_fill.findData(BackgroundFillManager.DEFAULT_FILL))
        # 相框配置卡三个下拉框统一双端宽度约束（200–260）：上限容纳最长
        # 选项"模糊背景 (深色 65%)"文本 182px + 箭头与内边距；下限保持原
        # 可收缩性——窄侧边栏下收缩回原基线，避免硬性宽度过高时整组
        # 最小需求超过侧边栏宽度造成水平溢出
        self.combo_bg_fill.setMinimumWidth(200)
        self.combo_bg_fill.setMaximumWidth(260)
        bg_group = card.addGroup(FluentIcon.CHECKBOX, "背景填充样式", "选择背景填充方式", self.combo_bg_fill, 2)

        # 背景增强
        self.chk_enhance = SwitchButton()
        self.chk_enhance.setChecked(True)
        card.addGroup(FluentIcon.CHECKBOX, "背景增强", "仅高斯模糊背景有效", self.chk_enhance)

        # 旋转适配（方案 §6.2/§6.3）：渲染期整帧方向适配。默认模式
        # 跟随样式声明（预设仅对竖图生效）；显式选择顺/逆时针对所有
        # 图片生效。addGroup 返回 GroupWidget 并存引用，供内容行动态
        # 提示使用。历史命名 portrait_adaptation 与 config 键保持兼容
        self.combo_portrait_adaptation = ComboBox()
        for _text, _value in PORTRAIT_ADAPTATION_ITEMS:
            self.combo_portrait_adaptation.addItem(_text, userData=_value)
        self.combo_portrait_adaptation.setMinimumWidth(200)
        self.combo_portrait_adaptation.setMaximumWidth(260)
        self.combo_portrait_adaptation.setCurrentIndex(
            self.combo_portrait_adaptation.findData(ADAPT_DEFAULT))
        self.combo_portrait_adaptation.currentIndexChanged.connect(
            self._on_portrait_adaptation_changed)
        self.combo_portrait_adaptation.setAccessibleName('旋转适配')
        self.portrait_adaptation_group = card.addGroup(
            FluentIcon.ROTATE,
            '旋转适配',
            # content 行保持短文案（contentLabel 不换行，长文案会把
            # GroupWidget 撑宽超出侧边栏）；完整语义放 tooltip
            '默认跟随样式',
            self.combo_portrait_adaptation,
            2,
        )
        _adapt_tip = ('默认模式遵循当前样式的适配声明，仅对竖图生效；'
                      '显式选择顺/逆时针适配时对所有图片生效，并覆盖样式声明')
        self.combo_portrait_adaptation.setToolTip(_adapt_tip)
        self.portrait_adaptation_group.setToolTip(_adapt_tip)

        # 字重（G3：userData 绑定稳定 key）
        self.combo_font_weight = ComboBox()
        for _text, _key in FONT_WEIGHT_ITEMS:
            self.combo_font_weight.addItem(_text, userData=_key)
        self.combo_font_weight.setCurrentIndex(0)
        self.combo_font_weight.setMinimumWidth(200)
        self.combo_font_weight.setMaximumWidth(260)
        fw_group = card.addGroup(FluentIcon.FONT, "字重", "选择文字粗细", self.combo_font_weight, 2)

        # ── 三个带下拉框的组统一标签列宽 ─────────────────────────
        # GroupWidget 按剩余空间拉伸 ComboBox，各标签列宽不同会导致
        # 下拉框宽度/左缘参差（用户反馈"上下对齐"）。取三组标题与描述
        # 理想宽度的最大值统一设为标签最小宽：三组标签列严格等宽后，
        # 结构参数完全一致 → 任意容器宽度下三个下拉框宽度与边缘
        # 必然对齐（分配规则无关性），且不抬高整组最小需求
        combo_groups = (bg_group, self.portrait_adaptation_group, fw_group)
        label_w = max(
            label.sizeHint().width()
            for group in combo_groups
            for label in (group.titleLabel, group.contentLabel)
        )
        for group in combo_groups:
            group.titleLabel.setMinimumWidth(label_w)
            group.contentLabel.setMinimumWidth(label_w)

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

        # 拍摄时间（G3：userData 绑定稳定 key）
        self.combo_timestamp = ComboBox()
        for _text, _key in TIMESTAMP_DISPLAY_ITEMS:
            self.combo_timestamp.addItem(_text, userData=_key)
        self.combo_timestamp.setCurrentIndex(0)
        card.addGroup(FluentIcon.DATE_TIME, "拍摄时间", "控制相框中显示的拍摄时间信息", self.combo_timestamp, 1)

        # 镜头显示（G3：userData 绑定稳定 key）
        self.combo_lens_display = ComboBox()
        for _text, _key in LENS_DISPLAY_ITEMS:
            self.combo_lens_display.addItem(_text, userData=_key)
        self.combo_lens_display.setCurrentIndex(0)
        card.addGroup(FluentIcon.CAMERA, "镜头显示", "控制相框中显示的设备信息", self.combo_lens_display, 1)

        # 镜头名（三态下拉；注意：本方法当前无调用点——实际卡片由
        # image_processing_config_cards.create_shot_info_card 构建，
        # 此处构造保持与其一致，避免残留旧控件名误导后续维护）
        self.combo_lens_name = ComboBox()
        for _text, _key in LENS_NAME_ITEMS:
            self.combo_lens_name.addItem(_text, userData=_key)
        self.combo_lens_name.setCurrentIndex(0)
        card.addGroup(FluentIcon.CAMERA, "镜头名", "默认按样式键取值；可强制完整名或短版名", self.combo_lens_name, 1)

        # LOGO（G3：哨兵文案改 userData 稳定 key，动态 logo 项以文件名
        # 为 userData——文案调整不再使渲染分支静默失效）
        self.combo_logo = ComboBox()
        self.combo_logo.addItem('自动匹配', userData=LOGO_AUTO)
        self.combo_logo.addItem('无', userData=LOGO_NONE)
        # 读取 assets/logos/ 目录下的实际 logo 文件
        logos = self.logo_selector.scan_logos()
        for _logo in logos:
            self.combo_logo.addItem(_logo, userData=_logo)
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

        # 水印位置（G3：userData 绑定稳定 key）
        self.combo_wm_position = ComboBox()
        for _text, _key in WATERMARK_POSITION_ITEMS:
            self.combo_wm_position.addItem(_text, userData=_key)
        self.combo_wm_position.setCurrentIndex(4)  # 默认底部居中
        card.addGroup(FluentIcon.MARKET, "水印位置", "选择水印显示位置", self.combo_wm_position, 1)

        # 不透明度
        self.slider_opacity = Slider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(0, 100)
        self.slider_opacity.setValue(50)
        card.addGroup(FluentIcon.ZOOM, "不透明度", "调节水印透明程度", self.slider_opacity)

        # 颜色（G3：userData 绑定稳定 key，渲染时经 _WM_COLOR_RGB 取 RGB）
        self.combo_wm_color = ComboBox()
        for _text, _key in WATERMARK_COLOR_ITEMS:
            self.combo_wm_color.addItem(_text, userData=_key)
        card.addGroup(FluentIcon.PALETTE, "水印颜色", "选择水印文字颜色", self.combo_wm_color, 1)

        return card

    # ════════════════════════════════════════════════════════
    #  样式变更响应
    # ════════════════════════════════════════════════════════

    # ════════════════════════════════════════════════════════
    #  样式选项单一刷新入口（计划 §8.1，T5）
    # ════════════════════════════════════════════════════════

    def _connect_option_signals(self):
        """连接 11 项选项控件的输入信号（§8.2：全部卡片创建后调用）

        输入变化只重算状态与有效参数（零 IO，§5.4），不重读能力快照。
        """
        for attr, sig_name in (
                ("edit_author", "textChanged"),
                ("edit_location", "textChanged"),
                ("edit_custom_text", "textChanged"),
                ("chk_use_gps", "checkedChanged"),
                ("combo_timestamp", "currentIndexChanged"),
                ("combo_lens_display", "currentIndexChanged"),
                ("combo_lens_name", "currentIndexChanged"),
                ("combo_logo", "currentIndexChanged"),
                ("combo_bg_fill", "currentIndexChanged"),
                ("chk_enhance", "checkedChanged"),
                ("combo_font_weight", "currentIndexChanged"),
        ):
            widget = getattr(self, attr, None)
            if widget is None:
                continue
            signal = getattr(widget, sig_name, None)
            if signal is None:
                logger.warning(f"选项控件缺少信号: {attr}.{sig_name}（跳过）")
                continue
            signal.connect(self._on_option_input_changed)

    def _on_option_input_changed(self, *_args):
        """输入变化 → 只重算状态与有效参数（§8.1 事件表：不读磁盘）"""
        if self._restoring_config:
            return  # 恢复配置期间暂缓中间响应（§8.2）
        self._refresh_style_option_state()

    def _refresh_style_option_state(self, invalidate_files: bool = False,
                                    reload_snapshot: bool = False):
        """样式选项单一刷新入口（计划 §8.1：读取原值→按需重载能力→
        计算 evaluation→更新控件与按钮；页面唯一联动路径，无第二套）

        Args:
            invalidate_files: 先失效文件与来源缓存（refresh_style_list /
                showEvent / 生成前为 True，§4.4 显式失效点）
            reload_snapshot: 强制重读能力快照。切样式、refresh、showEvent、
                生成前为 True（同名也读取）；输入与照片变化为 False——
                复用页面缓存的快照重算，输入变化零 IO（§5.4）。

        不自动生成；旋转适配提示调用链在此保留（§8.1：独立规则不并入
        reason 体系），数据源复用当前评估的当前变体声明。
        """
        style_name = self.style_selector_card.current_style
        if invalidate_files:
            self.style_manager.invalidate_all()
        if reload_snapshot or self._style_capabilities_for != style_name:
            self._style_capabilities = (
                self.style_manager.get_style_capabilities(style_name)
                if style_name else None)
            self._style_capabilities_for = style_name

        # 读取原值与照片事实（§6.1：区分没有照片与照片没有 EXIF）
        raw = style_option_bindings.read_raw_values(self)
        item = (self.file_items[self.current_index]
                if 0 <= self.current_index < len(self.file_items) else None)
        gps_text = (item.exif_data.get("gps", "") if item.exif_data
                    else "") if item else ""
        photo = PhotoFacts(
            has_photo=item is not None,
            exif_data=item.exif_data if item else None,
            gps_text=gps_text,
        )
        is_gaussian = BackgroundFillManager.is_gaussian(raw.bg_fill_type)

        self._style_evaluation = evaluate_style_options(
            self._style_capabilities, raw, photo,
            selected_bg_is_gaussian=is_gaussian)

        # 应用控件状态与说明（只改启用与说明，不清空原值，§7.1）
        style_option_bindings.apply_states(self, self._style_evaluation)
        # 坏变体全局诊断放样式说明处（§7.2：不逐项掩盖、不弹 InfoBar）
        if self._style_evaluation.can_render_style:
            style_option_bindings.clear_page_style_hint(self)
        else:
            style_option_bindings.set_page_style_hint(self, self._style_evaluation)

        # 旋转适配提示跟随刷新（§8.1：保留调用链）；不修改菜单当前选项：
        # default 在渲染时解析样式默认值，显式覆盖值继续生效
        self._update_portrait_adaptation_hint()

        # 更新按钮（使用当前 evaluation，不反向触发完整刷新，防递归）
        self._update_button_states()

    def _on_style_changed(self, style_name: str):
        """样式选择变化 → 强制重读能力快照并刷新（§8.1 事件表：同名也读取）"""
        if self._restoring_config:
            return  # §8.2：恢复配置期间暂缓，__init__ 末尾统一重算
        self._refresh_style_option_state(reload_snapshot=True)

    def _update_style_dependent_controls(self):
        """（兼容转调）旧入口只转发新刷新入口，§8.1：不能两套联动并存"""
        self._refresh_style_option_state(reload_snapshot=True)

    # ── 旋转适配（方案 §6.4/§6.5） ──────────────────────

    def _get_portrait_adaptation(self) -> str:
        """返回 GUI 当前旋转适配稳定值；异常状态安全回退 default

        页面唯一读取出口：生成、保存共用，防止各自实现不同容错。
        """
        value = self.combo_portrait_adaptation.currentData()
        if value in USER_ADAPTATION_VALUES:
            return value
        return ADAPT_DEFAULT

    def _on_portrait_adaptation_changed(self, _index: int):
        """旋转适配选项变化 → 刷新内容行提示（不弹 InfoBar）"""
        self._update_portrait_adaptation_hint()

    def _update_portrait_adaptation_hint(self):
        """刷新旋转适配组的辅助文案（方案 §6.5；计划 §8.1 v11 数据源优化）

        数据源改为复用当前能力快照的**当前（预估）变体**声明
        （VariantFacts.portrait_adaptation_default）：省去每次切换单独
        get_style_config 的一次加载；各变体声明一致时与旧行为无差异，
        不一致时新行为更准确。无快照（空列表/无样式/未刷新）时回退
        通用文案，不中断样式切换流程。旋转适配的渲染行为本身不变。
        """
        suffix_map = {
            ADAPT_NONE: '不旋转',
            ADAPT_CLOCKWISE: '顺时针适配',
            ADAPT_COUNTERCLOCKWISE: '逆时针适配',
        }
        user_choice = self._get_portrait_adaptation()
        style_default = None
        # 从当前评估的当前变体读取声明（复用快照，零额外加载）
        evaluation = getattr(self, "_style_evaluation", None)
        snapshot = getattr(self, "_style_capabilities", None)
        if evaluation is not None and snapshot is not None \
                and evaluation.active_variant_path:
            for facts in snapshot.candidates:
                if facts.path == evaluation.active_variant_path:
                    style_default = facts.portrait_adaptation_default
                    break

        if user_choice == ADAPT_DEFAULT:
            if style_default is not None:
                # 短文案：前缀"仅对竖图生效"固定在组描述中，此处只表达
                # 动态语义，防止 contentLabel 撑宽侧边栏（用户反馈 2026-09-21）
                content = f'样式默认：{suffix_map[style_default]}'
            else:
                content = '遵循当前样式'
        else:
            content = f'已覆盖：{suffix_map[user_choice]}'
        self.portrait_adaptation_group.setContent(content)

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
        n = len(file_paths)
        tip = self._show_progress('加载中', f'正在加载第 1/{n} 张图片...')

        try:
            # 记录本次导入前已有的文件数，用于定位本次新导入的第一张图
            first_new_index = len(self.file_items)
            for i, path in enumerate(file_paths):
                tip.setContent(f'正在加载第 {i+1}/{n} 张图片...')
                QApplication.processEvents()

                try:
                    item = FileItem(file_path=path)

                    with open(path, 'rb') as f:
                        item.file_bytes = f.read()

                    # 导入时一次性计算内容摘要，作为二级模糊缓存的
                    # 稳定 source_cache_key（后续生成直接复用）
                    item.cache_key = compute_cache_key(item.file_bytes)

                    item.file_name = os.path.basename(path)

                    pil_img = PILImage.open(io.BytesIO(item.file_bytes))
                    # 应用 EXIF Orientation 转置：佳能等相机竖拍照片以"横向像素
                    # + 旋转标记"存储，不转置会导致缩略图与宽高信息横竖颠倒
                    # 注意：exif_transpose 无论是否发生转置都返回新 Image 对象，
                    # 且新对象不继承 format 属性（PIL 的 _new() 不拷贝该字段），
                    # 转正后需从原图回填，否则信息栏"格式"会兜底显示"未知"
                    img_format = pil_img.format
                    pil_img = PILImageOps.exif_transpose(pil_img)
                    pil_img.format = img_format
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

            # 竖图自动启用"短版镜头名"（移植自旧版 Streamlit GUI 的原设计：
            # 新图片导入时按 h >= w 判定，竖图与方形图均自动勾选；仅在导入
            # 新图时设置一次，之后尊重用户手动修改，切换胶片栏选中图时不
            # 重复覆盖。item.width/height 为 EXIF 转正后的真实方向，佳能等
            # 竖拍照片（横向存储+旋转标记）的判断因此可靠。）
            # 三态映射（勾选框升级为下拉后沿用原方向判定）：竖幅/方形 →
            # "短版镜头名"(short)，横幅 → "默认"(default)。
            if first_new_index < len(self.file_items):
                first_item = self.file_items[first_new_index]
                auto_name_mode = 'short' if first_item.height >= first_item.width else 'default'
                self.combo_lens_name.setCurrentIndex(self.combo_lens_name.findData(auto_name_mode))
                logger.info(
                    f"按首图方向自动设置镜头名模式: {first_item.file_name} "
                    f"({first_item.width}x{first_item.height}) -> {auto_name_mode}"
                )

            self._update_button_states()
            if self.file_items and self.current_index == -1:
                self._select_item(0)
            else:
                # 照片导入事件：重算选项状态（§8.1 事件表；首图选中路径
                # 已在 _select_item 内刷新，此处覆盖增量导入场景）
                self._refresh_style_option_state()

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

        # G8：PIL→QImage 转换单点在 utils/image_convert（含 sRGB 与副本语义）
        return pil_to_qimage(pil_thumb)

    def _add_filmstrip_item(self, item: FileItem):
        """在胶片栏中添加一个缩略图项"""
        # 动态计算缩略图尺寸（基于胶片栏可用高度）
        thumb_w, thumb_h = filmstrip_thumb_size(self.filmstrip_scroll.height())

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

        thumb_w, thumb_h = filmstrip_thumb_size(self.filmstrip_scroll.height())

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

        # 照片事件：先重算选项状态（GPS/时间/预估），再更新按钮（§8.1：
        # 避免使用上一张照片的状态）
        self._refresh_style_option_state()

        logger.debug(f"选中文件: {item.file_name}")

    def _update_preview(self, item: FileItem):
        """更新预览窗口显示（使用缓存 QPixmap 避免重复渲染）"""
        # 生成或读取缓存
        if item.cached_pixmap is None:
            if item.result_path:
                # 使用 PIL 加载大图，避免 Qt QImageIOHandler 的 256MB 分配上限
                pil_img = PILImage.open(item.result_path)
                pil_img = self._convert_to_srgb(pil_img)
                pixmap = QPixmap.fromImage(pil_to_qimage(pil_img))
            elif item.file_bytes:
                pil_img = PILImage.open(io.BytesIO(item.file_bytes))
                # 原图预览同样需按 EXIF Orientation 转正（与导入缩略图保持一致；
                # 结果图分支无需处理，输出文件在保存时已将 Orientation 重置为 1）
                pil_img = PILImageOps.exif_transpose(pil_img)
                pil_img = self._convert_to_srgb(pil_img)
                pixmap = QPixmap.fromImage(pil_to_qimage(pil_img))
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
                thumb_w, thumb_h = filmstrip_thumb_size(
                    self.filmstrip_scroll.height())
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
        """根据当前状态更新按钮启用/禁用（§8.1：只读当前 evaluation，
        不反向触发完整刷新，防递归）"""
        has_items = len(self.file_items) > 0
        has_unprocessed = any(not item.is_processed for item in self.file_items)
        has_processed = any(item.is_processed for item in self.file_items)

        current_item = self.file_items[self.current_index] if 0 <= self.current_index < len(self.file_items) else None
        current_is_processed = current_item is not None and current_item.is_processed

        self.btn_export_current.setEnabled(current_is_processed)
        self.btn_export_all.setEnabled(has_processed)
        # 生成按钮 = 当前照片及索引有效 且 样式可用（§8.4：evaluation
        # 已在刷新入口算好，此处只读，不重算）
        style_ok = (self._style_evaluation is not None
                    and self._style_evaluation.can_render_style)
        self.btn_generate.setEnabled(self.current_index >= 0 and style_ok)
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
            try:
                export_verified(item.result_path, path)
            except Exception as e:
                # 本次导出失败：不宣称成功，目标位置不留下未通过校验的文件
                logger.error(f"[output-metadata] 导出校验失败 {item.file_name} -> {path}: {e}")
                InfoBar.error(title="导出失败",
                              content=f"导出校验失败: {e}", parent=self)
                return
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
        """生成相框：处理当前选中图片（§8.4：函数级守卫 + 生成前重读）"""
        if self.current_index < 0 or self.current_index >= len(self.file_items):
            return

        # §8.4：生成前失效文件缓存、重读能力、重算评估——在状态提示与
        # 临时文件创建**之前**检查；函数级守卫必须存在，防止直接调用
        # 绕过禁用按钮
        self._refresh_style_option_state(invalidate_files=True,
                                         reload_snapshot=True)
        evaluation = self._style_evaluation
        if not evaluation.can_render_style:
            reason = (evaluation.diagnostics[0]
                      if evaluation.diagnostics else "当前样式配置不可用")
            InfoBar.warning(title="无法生成", content=reason, parent=self)
            logger.warning(f"生成被守卫阻止: {reason}")
            return

        # 显示处理状态提示（守卫通过后才创建）
        self.state_tooltip = self._show_progress('处理中', '正在生成相框...')

        try:
            item = self.file_items[self.current_index]

            # 1. 从评估结果收集渲染配置（§7.3：同一次计算的有效参数）
            metadata, options, fw_key = collect_render_options(self, item,
                                                               evaluation)

            # 2. 创建临时文件并调用 ImageProcessor
            suffix = os.path.splitext(item.file_name)[1]
            input_path = self.temp_manager.create_temp_file(suffix=suffix)
            output_ext = ".jpg" if self.combo_output_format.currentData() == "JPEG" else ".png"
            output_path = self.temp_manager.create_temp_file(suffix=output_ext)

            # 写入输入文件
            with open(input_path, 'wb') as f:
                f.write(item.file_bytes)

            # 调用处理器（本调用点是二级模糊缓存的接入位置：
            # source_cache_key 用 FileItem 导入摘要，LRU 页面级持有）
            if self._processor is None:
                self._processor = ImageProcessor()
            success = self._processor.process(
                input_path=input_path,
                output_path=output_path,
                # §8.3/§8.4：移除硬编码样式兜底——无样式时 evaluation.
                # can_render_style 必为 False，守卫已在此前拦截
                style_name=self.style_selector_card.current_style,
                metadata=metadata,
                options=options,
                font_weight=fw_key,
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
                # 本次生成失败：不设置本次 result_path / is_processed，
                # 上次有效结果保持原状（方案 §6.4）
                self.state_tooltip.setContent('生成失败')
                self.state_tooltip.setState(False)
                QTimer.singleShot(1500, self.state_tooltip.hide)
                if item.is_processed and item.result_path:
                    InfoBar.warning(title="生成失败",
                                    content="本次生成失败，已保留上次结果", parent=self)
                else:
                    InfoBar.warning(title="生成失败",
                                    content="生成失败", parent=self)
                logger.error(f"生成相框失败: {item.file_name}")
        except Exception as e:
            logger.error(f"生成相框异常: {e}")
            if self.state_tooltip:
                self.state_tooltip.setContent('出错')
                self.state_tooltip.setState(False)
                QTimer.singleShot(1500, self.state_tooltip.hide)
            # 异常同样不代表本次成功：有上次有效结果时明确说明保留状态
            current = (self.file_items[self.current_index]
                       if 0 <= self.current_index < len(self.file_items) else None)
            if current is not None and current.is_processed and current.result_path:
                InfoBar.error(title="生成失败",
                              content="本次生成失败，已保留上次结果", parent=self)
            else:
                InfoBar.error(title="生成失败", content="生成失败", parent=self)

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
        export_failed = []
        for item in processed:
            try:
                ext = Path(item.result_path).suffix
                dest = os.path.join(folder, Path(item.file_name).stem + '_frame' + ext)
                # 复制 + 哈希/标识校验 + 验证后发布（与单张导出同一路径）
                export_verified(item.result_path, dest)
                exported += 1
            except Exception as e:
                export_failed.append(item.file_name)
                logger.error(f"[output-metadata] 导出失败 {item.file_name}: {e}")

        logger.info(f"一键导出 {exported}/{len(processed)} 张图片 → {folder}")
        if export_failed:
            InfoBar.warning(
                title="批量导出完成",
                content=f"已导出 {exported} 张，{len(export_failed)} 张校验失败",
                parent=self)
        else:
            InfoBar.success(title="批量导出完成",
                            content=f"已导出 {exported} 张图片到 {folder}", parent=self)

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

        # 清空照片事件：重算选项状态（§8.1：无照片时按无 EXIF 预估）
        self._refresh_style_option_state()
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

        # 照片删除事件：重算选项状态（GPS 不使用已删除照片的值），再更新按钮
        self._refresh_style_option_state()
        logger.debug(f"已移除图片: 索引 {index}")

    def cleanup(self):
        """清理页面资源（由 MainWindow.closeEvent 调用）"""
        self.file_items.clear()
        self.filmstrip_labels.clear()
        self.current_index = -1
        # 页面关闭时清空页面级二级缓存（设计文档 §5.3 失效规则）
        self._blur_lru.clear()
        self._processor = None
        self.temp_manager.cleanup()
        logger.debug("图像处理页面资源已清理")

    def _restore_combo_value(self, combo, saved_value):
        """按 config.json 存储值恢复下拉选中项（G3/D5）

        恢复顺序：稳定 key（findData）→ 历史文本别名表迁移（覆盖
        修复前以中文文本持久化的旧配置）→ 都失败保持默认项。
        """
        if saved_value is None:
            return
        idx = combo.findData(saved_value)
        if idx < 0:
            key = self._legacy_aliases.get(str(saved_value))
            if key is not None:
                idx = combo.findData(key)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def save_config(self):
        """收集当前控件值并保存到 ConfigManager（由 MainWindow.closeEvent 调用）"""
        # 作者名（D6 决策：显式写空——用户清空输入框后旧值不再残留，
        # ConfigManager 对空串正常存取，加载端空串不回填、控件默认即空）
        default_config_manager.save_user_author(self.edit_author.text())
        # 最近使用配置（G3：下拉框一律写稳定 key，不写中文显示文本）
        # §8.3：保存真实样式名称或 None（null）——移除硬编码
        # "底部信息条 Bottom Bars" 兜底，不再保存幽灵样式
        default_config_manager.save_last_used_settings({
            'style_name': self.style_selector_card.current_style,
            'output_format': self.combo_output_format.currentData(),
            'bg_fill': self.combo_bg_fill.currentData(),
            'enhance_background': self.chk_enhance.isChecked(),
            'font_weight': self.combo_font_weight.currentData(),
            'timestamp_display': self.combo_timestamp.currentData(),
            # 旋转适配：保存稳定内部值（非中文显示文本），
            # 未来调整文案不影响已有 config.json 的恢复（方案 §6.6）
            'portrait_adaptation': self._get_portrait_adaptation(),
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
        # G3/D5：恢复顺序 = 稳定 key（findData）→ 历史文本别名表迁移 →
        # 回退默认项。旧 config 存中文文本，经 _legacy_aliases 迁移。
        if 'output_format' in saved:
            self._restore_combo_value(self.combo_output_format,
                                      saved['output_format'])
        if 'bg_fill' in saved:
            self._restore_combo_value(self.combo_bg_fill, saved['bg_fill'])
        if 'enhance_background' in saved:
            self.chk_enhance.setChecked(saved['enhance_background'])
        if 'font_weight' in saved:
            self._restore_combo_value(self.combo_font_weight,
                                      saved['font_weight'])
        if 'timestamp_display' in saved:
            self._restore_combo_value(self.combo_timestamp,
                                      saved['timestamp_display'])
        # 旋转适配：按 userData 恢复稳定内部值（方案 §6.6）；
        # 缺失/旧版本配置/非法值均经 findData<0 回退 default
        if 'portrait_adaptation' in saved:
            saved_value = saved['portrait_adaptation']
            index = self.combo_portrait_adaptation.findData(saved_value)
            if index < 0:
                index = self.combo_portrait_adaptation.findData(ADAPT_DEFAULT)
            self.combo_portrait_adaptation.blockSignals(True)
            self.combo_portrait_adaptation.setCurrentIndex(index)
            self.combo_portrait_adaptation.blockSignals(False)
        # 内容行提示在恢复完成后统一刷新（含 saved 为空的首次加载路径）
        self._update_portrait_adaptation_hint()

    def refresh_style_list(self):
        """刷新样式网格（样式编辑器中新建/保存样式后调用）

        §8.1/§4.4：先失效文件与来源缓存（同名配置更新必须重读），
        再重建网格；随后强制重读能力快照——refresh_styles 恢复选中
        不发信号（样式卡内部行为），此处显式触发刷新保证联动。
        """
        self.style_manager.invalidate_all()
        styles = self.style_manager.get_available_styles()
        self.style_selector_card.refresh_styles(styles, self.style_manager)
        self._refresh_style_option_state(reload_snapshot=True)

    def showEvent(self, event):
        """页面显示时刷新样式列表"""
        super().showEvent(event)
        self.refresh_style_list()
