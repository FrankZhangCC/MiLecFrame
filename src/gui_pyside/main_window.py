# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
主窗口模块

FluentWindow 是 PySide6 GUI 的主容器，
包含 NavigationInterface 导航栏和 QStackedWidget 页面容器。
"""
import logging

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

from qfluentwidgets import (
    FluentWindow,
    NavigationInterface,
    NavigationItemPosition,
    FluentIcon,
)

from .utils.temp_manager import TempManager
from .pages.image_processing_page import ImageProcessingPage
from .pages.camera_mapping_page import CameraMappingPage
from .pages.lens_mapping_page import LensMappingPage
from .pages.style_creator_page import StyleCreatorPage


class MainWindow(FluentWindow):
    """主窗口

    继承自 QFluentWidgets.FluentWindow，提供：
    - Fluent Design 风格的窗口框架
    - 左侧导航栏（NavigationInterface）
    - 页面切换（QStackedWidget）
    - 状态栏
    - 窗口关闭时自动清理临时文件
    """

    # ── 导航路由键 ──
    ROUTE_IMAGE = "image_processing"
    ROUTE_CAMERA = "camera_mapping"
    ROUTE_LENS = "lens_mapping"
    ROUTE_STYLE = "style_creator"

    def __init__(self, parent=None):
        super().__init__(parent)

        # ── 初始化临时文件管理器 ──
        self.temp_manager = TempManager()

        # ── 窗口基本设置 ──
        self.setWindowTitle("MiLecFrame - 照片相框水印工具")
        self.resize(1280, 960)
        self.setMinimumSize(QSize(1280, 960))

        # ── 窗口居中 ──
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            self.move(
                (sg.width() - 1280) // 2 + sg.x(),
                (sg.height() - 960) // 2 + sg.y(),
            )

        # ── 创建页面 ──
        self._create_pages()

        # ── 设置导航 ──
        self._setup_navigation()

        # ── 设置默认显示页面 ──
        self.stackedWidget.setCurrentWidget(self.image_page)

        logging.getLogger(__name__).info("主窗口初始化完成")

    def _create_pages(self):
        """创建所有页面并添加到 stacked widget"""
        # ── 图像处理页面（已完成开发） ──
        self.image_page = ImageProcessingPage(self)
        self.stackedWidget.addWidget(self.image_page)

        # ── 相机映射管理页面 ──
        self.camera_page = CameraMappingPage(self)
        self.stackedWidget.addWidget(self.camera_page)

        # ── 镜头映射管理页面 ──
        self.lens_page = LensMappingPage(self)
        self.stackedWidget.addWidget(self.lens_page)

        # ── 样式编辑器页面 ──
        self.style_page = StyleCreatorPage(self)
        self.stackedWidget.addWidget(self.style_page)

    def _setup_navigation(self):
        """设置导航栏项目"""
        # ── 顶部导航项 ──
        self.navigationInterface.addItem(
            routeKey=self.ROUTE_IMAGE,
            icon=FluentIcon.PHOTO,
            text="图像处理",
            onClick=lambda: self.stackedWidget.setCurrentWidget(self.image_page),
            position=NavigationItemPosition.TOP,
            tooltip="单张图片处理",
        )

        self.navigationInterface.addItem(
            routeKey=self.ROUTE_CAMERA,
            icon=FluentIcon.CAMERA,
            text="相机映射管理",
            onClick=lambda: self.stackedWidget.setCurrentWidget(self.camera_page),
            position=NavigationItemPosition.TOP,
            tooltip="管理相机品牌和型号映射",
        )

        self.navigationInterface.addItem(
            routeKey=self.ROUTE_LENS,
            icon=FluentIcon.ZOOM_IN,
            text="镜头映射管理",
            onClick=lambda: self.stackedWidget.setCurrentWidget(self.lens_page),
            position=NavigationItemPosition.TOP,
            tooltip="管理镜头型号映射",
        )

        self.navigationInterface.addItem(
            routeKey=self.ROUTE_STYLE,
            icon=FluentIcon.PALETTE,
            text="样式编辑器",
            onClick=lambda: self.stackedWidget.setCurrentWidget(
                self.style_page
            ),
            position=NavigationItemPosition.TOP,
            tooltip="创建和编辑相框样式",
        )

        # ── 底部导航项（设置/关于等预留位置） ──
        self.navigationInterface.addSeparator()
        self.navigationInterface.addItem(
            routeKey="settings",
            icon=FluentIcon.SETTING,
            text="设置",
            onClick=lambda: None,  # 预留
            position=NavigationItemPosition.BOTTOM,
            tooltip="应用设置",
        )

    def closeEvent(self, event):
        """窗口关闭事件

        关闭窗口时自动清理所有临时文件和缓存资源。
        """
        logger = logging.getLogger(__name__)
        logger.info("窗口关闭，开始清理资源...")

        # ── 清理临时文件 ──
        self.temp_manager.cleanup()

        # ── 保存页面配置 ──
        if hasattr(self, 'image_page'):
            self.image_page.save_config()

        # ── 释放缩略图内存 ──
        if hasattr(self, 'image_page'):
            self.image_page.cleanup()
        if hasattr(self, 'camera_page'):
            self.camera_page.cleanup()
        if hasattr(self, 'lens_page'):
            self.lens_page.cleanup()
        if hasattr(self, 'style_page'):
            self.style_page.cleanup()

        logger.info("资源清理完成")
        event.accept()
