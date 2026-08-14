# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
样式编辑器页面主容器

负责页面整体布局、工具栏、Pivot 导航、预览渲染管线。
各配置区块实现在 widgets/style_config_sections/ 目录下。
"""
import logging
import os
from pathlib import Path

from PIL import Image as PILImage

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTextEdit,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from qfluentwidgets import (
    PrimaryPushButton, PushButton, ComboBox, EditableComboBox,
    FluentIcon, InfoBar, InfoBarPosition, Pivot,
    ExpandGroupSettingCard, StrongBodyLabel,
    Dialog, SmoothScrollArea,
)

from ..widgets.style_preview import StylePreview
from ..models.style_config_form import (
    StyleConfigFormData,
    NEW_STYLE_PLACEHOLDER,
    _build_yaml_config,
)
from ..data.preview_data import (
    PREVIEW_EXIF_DATA,
    PREVIEW_AUTHOR,
    PREVIEW_LOCATION,
    PREVIEW_CUSTOM_TEXT,
)

# ── 配置区块导入 ──
from ..widgets.style_config_sections.basic_info_section import (
    BasicInfoSection)
from ..widgets.style_config_sections.canvas_section import (
    CanvasSection)
from ..widgets.style_config_sections.padding_section import (
    PaddingSection)
from ..widgets.style_config_sections.corner_radius_section import (
    CornerRadiusSection)
from ..widgets.style_config_sections.fonts_section import (
    FontsSection)
from ..widgets.style_config_sections.logo_section import (
    LogoSection)
from ..widgets.style_config_sections.colors_section import (
    ColorsSection)
from ..widgets.style_config_sections.defined_texts_section import (
    DefinedTextsSection)
from ..widgets.style_config_sections.custom_text_section import (
    CustomTextSection)
from ..widgets.style_config_sections.elements_section import (
    ElementsSection)

logger = logging.getLogger(__name__)


# ── 路径常量（统一的路径定位，兼容开发/打包环境） ──
# 内置样式目录：只读资源，随程序打包（_MEIPASS/src/frame_styles/configs）
# CONFIGS_DIR：样式保存/导出的可写目录。开发环境即内置目录；
#              打包环境为 exe 同目录 styles/（用户样式持久化，升级不丢失）
from src.utils.app_paths import get_resource_root, get_app_dir, is_frozen

_RESOURCE_ROOT = get_resource_root()
ASSETS_PREVIEW_DIR = _RESOURCE_ROOT / 'src' / 'gui_pyside' / 'assets' / 'preview'

if is_frozen():
    CONFIGS_DIR = get_app_dir() / 'styles'
    _BUILTIN_CONFIGS_DIR = _RESOURCE_ROOT / 'src' / 'frame_styles' / 'configs'
else:
    CONFIGS_DIR = _RESOURCE_ROOT / 'src' / 'frame_styles' / 'configs'
    _BUILTIN_CONFIGS_DIR = None

# ── Pivot 导航项定义 ──
_PIVOT_ITEMS = [
    ('basic', '基本信息'),
    ('canvas', '画布'),
    ('padding', '安全区'),
    ('corner', '圆角'),
    ('fonts', '字体'),
    ('logo', 'Logo'),
    ('colors', '颜色'),
    ('defined_texts', '预定义'),
    ('custom_text', '自定义'),
    ('elements', '元素'),
]


class StyleCreatorPage(QWidget):
    """样式编辑器页面主容器

    布局结构：
    ┌─────────────────────────────────────────────────────────┐
    │  ┌── 顶部工具栏 ───────────────────────────────────┐   │
    │  │ [样式选择 ComboBox] [新建] [保存] [导出 YAML]   │   │
    │  └─────────────────────────────────────────────────┘   │
    │  ┌── QSplitter (水平) ─────────────────────────────┐   │
    │  │  ┌─ 左侧: 配置面板 ──┐ ┌─ 右侧: 预览面板 ──┐  │   │
    │  │  │ [Pivot 导航]       │ │ [StylePreview]   │  │   │
    │  │  │ [ScrollArea]       │ │                   │  │   │
    │  │  │  ┌ 10 个 Section ┐ │ │                   │  │   │
    │  │  │  └───────────────┘ │ │                   │  │   │
    │  │  └───────────────────┘ └───────────────────┘  │   │
    │  └───────────────────────────────────────────────┘   │
    └───────────────────────────────────────────────────────┘
    """

    # ── Pivot 路由键 ──
    ROUTE_BASIC = 'basic'
    ROUTE_CANVAS = 'canvas'
    ROUTE_PADDING = 'padding'
    ROUTE_CORNER = 'corner'
    ROUTE_FONTS = 'fonts'
    ROUTE_LOGO = 'logo'
    ROUTE_COLORS = 'colors'
    ROUTE_DEFINED_TEXTS = 'defined_texts'
    ROUTE_CUSTOM_TEXT = 'custom_text'
    ROUTE_ELEMENTS = 'elements'

    def __init__(self, parent=None):
        super().__init__(parent)

        # ── 数据 ──
        self.form_data = StyleConfigFormData()
        self._current_filepath: str = ''
        self._current_style_name: str = ''

        # ── 样本图缓存 ──
        self._sample_landscape: PILImage = None
        self._sample_portrait: PILImage = None

        # ── 初始化核心依赖（延迟加载） ──
        self._renderer = None
        self._style_manager = None

        # ── 配置区块字典 ──
        self.sections: dict[str, ExpandGroupSettingCard] = {}

        # ── 首渲标记：showEvent 设为 False 后首次渲染才真正执行 ──
        self._first_show = True

        # ── 抑制标记：_load_all_sections 执行期间屏蔽 _on_config_changed ──
        self._suppress_config_change = False

        # ── 去抖动定时器（必须在 _setup_ui 之前创建，避免信号提前触发） ──
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._render_preview)

        # ── 初始化 UI ──
        self._setup_ui()

        # ── 加载样本图片 ──
        self._load_sample_images()

        # ── 从默认模型同步到所有区块 ──
        self._load_all_sections()

        logger.info("样式编辑器页面初始化完成")

    def _setup_ui(self):
        """搭建页面整体布局"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 1. 顶部工具栏 ──
        toolbar = self._create_toolbar()
        main_layout.addWidget(toolbar)

        # ── 2. 主内容区（QSpitter 左右分割） ──
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.setChildrenCollapsible(False)
        content_splitter.setHandleWidth(4)
        content_splitter.setStyleSheet("""
            QSplitter::handle { background-color: #e0e0e0; }
            QSplitter::handle:hover { background-color: #0078d4; }
        """)

        left_panel = self._create_config_panel()
        right_panel = self._create_preview_panel()

        content_splitter.addWidget(left_panel)
        content_splitter.addWidget(right_panel)
        content_splitter.setSizes([500, 500])
        content_splitter.setStretchFactor(0, 1)
        content_splitter.setStretchFactor(1, 1)

        content_splitter.splitterMoved.connect(
            lambda pos, idx: self.preview.rescale_pixmap())

        main_layout.addWidget(content_splitter, stretch=1)

        # ── 加载样式列表 ──
        self._refresh_style_list()

    # ── 顶部工具栏 ──────────────────────────────────────────

    def _create_toolbar(self) -> QWidget:
        """创建顶部工具栏"""
        toolbar = QWidget()
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(8)

        # 样式选择器
        self.style_combo = EditableComboBox(toolbar)
        self.style_combo.setPlaceholderText("选择或输入样式名称...")
        self.style_combo.setMinimumWidth(250)
        self.style_combo.currentTextChanged.connect(
            self._on_style_selected)

        # 新建按钮
        self.new_btn = PushButton(FluentIcon.ADD, "新建样式", toolbar)
        self.new_btn.clicked.connect(self._on_new_style)

        # 保存按钮
        self.save_btn = PrimaryPushButton(
            FluentIcon.SAVE, "保存样式", toolbar)
        self.save_btn.clicked.connect(self._on_save_style)

        # 导出 YAML 预览按钮
        self.export_btn = PushButton(
            FluentIcon.CODE, "导出 YAML", toolbar)
        self.export_btn.clicked.connect(self._on_export_yaml)

        layout.addWidget(StrongBodyLabel("样式:"))
        layout.addWidget(self.style_combo, stretch=1)
        layout.addWidget(self.new_btn)
        layout.addWidget(self.save_btn)
        layout.addWidget(self.export_btn)

        return toolbar

    # ── 配置面板（左侧） ────────────────────────────────────

    def _create_config_panel(self) -> QWidget:
        """创建左侧配置面板，含 Pivot 导航 + 10 个配置区块"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Pivot 快速导航
        self.pivot = Pivot(self)
        self.pivot.setStyleSheet(
            "QPushButton { padding: 6px 16px; }")
        for route, text in _PIVOT_ITEMS:
            self.pivot.addItem(
                route, text,
                onClick=lambda r=route: self._scroll_to_section(r))
        layout.addWidget(self.pivot)

        # SmoothScrollArea 包裹配置区块
        self.config_scroll = SmoothScrollArea()
        self.config_scroll.setWidgetResizable(True)
        self.config_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.config_container = QWidget()
        self.config_layout = QVBoxLayout(self.config_container)
        self.config_layout.setContentsMargins(16, 8, 16, 8)
        self.config_layout.setSpacing(4)
        self.config_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop)

        # ── 创建所有配置区块 ──
        sections_data = [
            (self.ROUTE_BASIC, BasicInfoSection),
            (self.ROUTE_CANVAS, CanvasSection),
            (self.ROUTE_PADDING, PaddingSection),
            (self.ROUTE_CORNER, CornerRadiusSection),
            (self.ROUTE_FONTS, FontsSection),
            (self.ROUTE_LOGO, LogoSection),
            (self.ROUTE_COLORS, ColorsSection),
            (self.ROUTE_DEFINED_TEXTS, DefinedTextsSection),
            (self.ROUTE_CUSTOM_TEXT, CustomTextSection),
            (self.ROUTE_ELEMENTS, ElementsSection),
        ]
        for route, section_cls in sections_data:
            card = section_cls(self.config_container)
            card.value_changed.connect(self._on_config_changed)
            self.sections[route] = card
            self.config_layout.addWidget(card)

        self.config_scroll.setWidget(self.config_container)
        layout.addWidget(self.config_scroll, stretch=1)

        return panel

    def _scroll_to_section(self, route: str):
        """滚动到指定配置区块"""
        card = self.sections.get(route)
        if not card:
            return
        # 计算 card 在 ScrollArea 内容中的 Y 偏移
        from PySide6.QtCore import QPoint
        card_y = card.mapTo(self.config_container, QPoint(0, 0)).y()
        self.config_scroll.verticalScrollBar().setValue(card_y)

    def _load_all_sections(self):
        """将所有配置区块的数据加载到 form_data"""
        self._suppress_config_change = True
        try:
            for route, card in self.sections.items():
                try:
                    card.load_from_model(self.form_data)
                except Exception as e:
                    logger.warning(
                        "加载区块 %s 失败: %s", route, e)
        finally:
            self._suppress_config_change = False

    def _save_all_sections(self):
        """从所有配置区块收集数据到 form_data"""
        for route, card in self.sections.items():
            try:
                card.save_to_model(self.form_data)
            except Exception as e:
                logger.warning(
                    "保存区块 %s 失败: %s", route, e)

    # ── 预览面板（右侧） ────────────────────────────────────

    def _create_preview_panel(self) -> QWidget:
        """创建右侧预览面板"""
        self.preview = StylePreview(self)
        self.preview.orientation_changed.connect(
            self._on_preview_orientation_changed)
        self.preview.preview_bg_changed.connect(
            self._on_preview_bg_changed)
        return self.preview

    # ── 样本图加载 ─────────────────────────────────────────

    def _load_sample_images(self):
        """加载横/竖样本图，不存在时生成占位图"""
        landscape_path = ASSETS_PREVIEW_DIR / 'demo_horizontal.png'
        portrait_path = ASSETS_PREVIEW_DIR / 'demo_vertical.png'

        if landscape_path.exists():
            self._sample_landscape = PILImage.open(
                landscape_path).copy()
        else:
            self._sample_landscape = self._create_placeholder_image(
                1200, 800, text='横向样本图\n(请放入 assets/preview/)')

        if portrait_path.exists():
            self._sample_portrait = PILImage.open(
                portrait_path).copy()
        else:
            self._sample_portrait = self._create_placeholder_image(
                800, 1200, text='纵向样本图\n(请放入 assets/preview/)')

    def _create_placeholder_image(
        self, w: int, h: int, text: str
    ):
        """生成占位图像"""
        from PIL import ImageDraw, ImageFont
        img = PILImage.new('RGB', (w, h), color=(200, 200, 200))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("segoeui.ttf", 28)
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.multiline_textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (w - tw) // 2
        y = (h - th) // 2
        draw.multiline_text(
            (x, y), text, fill=(120, 120, 120), font=font,
            align='center')
        return img

    # ── 样式列表管理 ───────────────────────────────────────

    def _get_existing_styles(self) -> list[str]:
        """获取已有样式文件列表（含子目录变体），合并用户目录与内置目录"""
        styles = []
        seen = set()
        # 目录顺序：用户目录（CONFIGS_DIR）在前，内置目录在后；
        # 同名样式（文件夹/文件级）用户目录优先，内置同名自动隐藏
        base_dirs = [CONFIGS_DIR]
        if _BUILTIN_CONFIGS_DIR is not None:
            base_dirs.append(_BUILTIN_CONFIGS_DIR)

        for base in base_dirs:
            if not base.exists():
                continue
            for entry in sorted(os.listdir(str(base))):
                if entry.startswith('_'):
                    continue
                full = base / entry
                if full.is_dir():
                    if entry in seen:
                        continue
                    seen.add(entry)
                    for variant in sorted(os.listdir(str(full))):
                        if variant.lower().endswith('.yaml') \
                                and not variant.startswith('_'):
                            styles.append(f'{entry}/{variant}')
                elif entry.lower().endswith('.yaml'):
                    if entry in seen:
                        continue
                    seen.add(entry)
                    styles.append(entry)
        return styles

    def _resolve_style_filepath(self, rel_text: str) -> str:
        """
        根据下拉框中的相对路径文本解析实际文件路径

        优先在用户目录（CONFIGS_DIR）查找，再回退到内置目录，
        兼容打包环境下加载内置只读样式。

        Args:
            rel_text: 样式相对路径（如 'FilmClip/default.yaml'）

        Returns:
            实际文件绝对路径，不存在则返回 CONFIGS_DIR 下的拼接结果
        """
        for base in [CONFIGS_DIR] + ([_BUILTIN_CONFIGS_DIR] if _BUILTIN_CONFIGS_DIR else []):
            candidate = base / rel_text
            if candidate.exists():
                return str(candidate)
        return str(CONFIGS_DIR / rel_text)

    def _refresh_style_list(self):
        """刷新样式选择下拉列表"""
        self.style_combo.blockSignals(True)
        self.style_combo.clear()
        self.style_combo.addItem(NEW_STYLE_PLACEHOLDER)
        for s in self._get_existing_styles():
            self.style_combo.addItem(s)
        self.style_combo.blockSignals(False)

    # ── 事件处理 ───────────────────────────────────────────

    def _on_style_selected(self, text: str):
        """样式选择变更"""
        if text == NEW_STYLE_PLACEHOLDER:
            self.form_data = StyleConfigFormData()
            self._current_filepath = ''
            self._load_all_sections()
            self._render_preview()
            return

        filepath = self._resolve_style_filepath(text)
        if not os.path.exists(filepath):
            return

        try:
            self.form_data = StyleConfigFormData.load_from_file(
                filepath)
            self._current_filepath = filepath
            self._current_style_name = text
            self._load_all_sections()
            self._render_preview()
            InfoBar.success(
                title='加载成功',
                content=f'已加载样式: {text}',
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
        except Exception as e:
            InfoBar.error(
                title='加载失败',
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )

    def _on_new_style(self):
        """新建样式"""
        self.form_data = StyleConfigFormData()
        self.style_combo.setCurrentText(NEW_STYLE_PLACEHOLDER)
        self._current_filepath = ''
        self._current_style_name = ''
        self._load_all_sections()
        self._render_preview()
        InfoBar.info(
            title='新建样式',
            content='已清空表单，填写参数后点击保存',
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self,
        )

    def _on_save_style(self):
        """保存样式"""
        # 从所有区块收集数据
        self._save_all_sections()

        # 获取文件名
        filename = self.form_data.filename.strip()
        if not filename:
            filename = f"{self.form_data.name.strip()}.yaml" \
                if self.form_data.name.strip() else 'NewStyle.yaml'
        if not filename.lower().endswith('.yaml'):
            filename += '.yaml'

        # 如果当前有加载的文件，使用其路径；否则用默认路径。
        # 打包环境下若当前文件来自内置只读目录，则「另存」到用户样式目录，
        # 保持与原目录相同的相对结构（如 FilmClip/default.yaml）。
        if self._current_filepath:
            filepath = self._current_filepath
            if _BUILTIN_CONFIGS_DIR is not None:
                try:
                    cur_abs = Path(self._current_filepath).resolve()
                    builtin_abs = _BUILTIN_CONFIGS_DIR.resolve()
                    rel = cur_abs.relative_to(builtin_abs)
                    if rel.parts:
                        filepath = str(CONFIGS_DIR / rel)
                except ValueError:
                    pass  # 不在内置目录内，保持原路径
        else:
            filepath = str(CONFIGS_DIR / filename)

        try:
            yaml_str = self.form_data.save_to_file(filepath)
            self._current_filepath = filepath
            self._current_style_name = os.path.relpath(
                filepath, str(CONFIGS_DIR)).replace('\\', '/')
            self._refresh_style_list()
            self.style_combo.setCurrentText(
                self._current_style_name)

            InfoBar.success(
                title='保存成功',
                content=f'已保存: {self._current_style_name}',
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
        except Exception as e:
            InfoBar.error(
                title='保存失败',
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )

    def _on_export_yaml(self):
        """导出 YAML 预览弹窗"""
        from PySide6.QtWidgets import QTextEdit

        try:
            yaml_str = self.form_data.save_to_file(
                str(CONFIGS_DIR / '__temp_preview__.yaml'))
            # 删除临时文件
            temp_path = CONFIGS_DIR / '__temp_preview__.yaml'
            if temp_path.exists():
                temp_path.unlink()
        except Exception as e:
            # 即使保存失败，直接从模型生成
            config = self.form_data.to_yaml_dict()
            yaml_str = _build_yaml_config(config)

        dialog = Dialog(
            'YAML 配置预览',
            '',
            self,
        )
        dialog.yesButton.setText('关闭')
        dialog.cancelButton.hide()

        text_edit = QTextEdit()
        text_edit.setPlainText(yaml_str)
        text_edit.setReadOnly(True)
        text_edit.setFont(QFont(
            'Cascadia Code, Consolas, monospace', 10))
        text_edit.setMinimumSize(700, 500)
        dialog.vBoxLayout.addWidget(text_edit)

        dialog.exec()

    def _on_preview_orientation_changed(self, orientation: str):
        """预览方向切换"""
        self._render_preview()

    def _on_preview_bg_changed(self, bg_type: str):
        """预览背景切换"""
        self._render_preview()

    # ── 预览渲染管线 ───────────────────────────────────────

    def _on_config_changed(self):
        """配置变更时收集 UI 数据 → 启动去抖动定时器"""
        if self._suppress_config_change:
            return
        self._save_all_sections()
        self._debounce_timer.start()

    def _get_renderer(self):
        """延迟加载渲染器"""
        if self._renderer is None:
            from src.core.renderer import FrameRenderer
            self._renderer = FrameRenderer()
        return self._renderer

    def _get_sample_image(self):
        """根据当前预览方向获取样本图"""
        orientation = self.preview.get_current_orientation()
        img = self._sample_landscape \
            if orientation == 'landscape' \
            else self._sample_portrait
        if img is None:
            return PILImage.new('RGB', (1200, 800), color=(200, 200, 200))
        return img.copy()

    def _render_preview(self):
        """执行预览渲染"""
        # 首渲之前跳过 __init__ 阶段的 debounce 触发
        if getattr(self, '_first_show', True):
            return
        try:
            # 获取样式配置
            style_config = self.form_data.to_yaml_dict()

            # 获取样本图
            sample_img = self._get_sample_image()

            # 获取预览背景类型
            bg_fill_type = self.preview.get_current_bg_fill_type()

            # 渲染
            renderer = self._get_renderer()
            result = renderer.render_frame(
                image=sample_img,
                exif_data=PREVIEW_EXIF_DATA,
                author=PREVIEW_AUTHOR,
                location=PREVIEW_LOCATION,
                style_config=style_config,
                bg_fill_type=bg_fill_type,
                logo_filename=None,
                lens_display_mode='combined',
                use_short_lens=False,
                saturation_override=1.0,
                custom_text=PREVIEW_CUSTOM_TEXT,
            )

            # 显示
            self.preview.set_preview_image(result)

        except Exception as e:
            import traceback
            logger.error(
                f"预览渲染失败: {e}\n{traceback.format_exc()}")

    # ── 生命周期 ───────────────────────────────────────────

    def cleanup(self):
        """清理资源"""
        self._sample_landscape = None
        self._sample_portrait = None
        self._renderer = None

    def showEvent(self, event):
        """页面首次显示时触发首渲（等 layout 稳定后再执行）"""
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            QTimer.singleShot(0, self._render_preview)

    def resizeEvent(self, event):
        """窗口大小变化时延迟刷新预览（确保子部件几何已稳定）"""
        super().resizeEvent(event)
        if hasattr(self, 'preview'):
            QTimer.singleShot(
                0, self.preview.rescale_pixmap)



