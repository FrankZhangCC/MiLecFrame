# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
PySide6 GUI 应用入口

负责 QApplication 初始化、主题设置、DPI 适配和主窗口创建。
"""
import sys
import logging
from pathlib import Path

# 将项目根目录加入 sys.path，使 src 包可导入，
# 从而 from src.core.xxx 和 core/__init__.py 的 from .._version 能正确工作。
# 使用统一的路径定位工具：开发环境为项目根，打包环境为 _MEIPASS 资源目录。
from src.utils.app_paths import get_resource_root
_project_root = get_resource_root()
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from qfluentwidgets import setTheme, Theme

from src.utils.logging_config import setup_logging
from .main_window import MainWindow


logger = logging.getLogger(__name__)


def run_pyside_app():
    """启动 PySide6 桌面 GUI 应用

    完整的启动流程：
    1. 初始化日志
    2. 创建 QApplication
    3. 配置高 DPI 缩放
    4. 设置 Fluent 主题
    5. 创建并显示主窗口
    6. 进入事件循环
    """
    setup_logging()
    logger.info("正在启动 PySide6 桌面 GUI...")

    # ── 创建 QApplication ──
    # 高 DPI 缩放必须在 QApplication 创建前设置
    app = QApplication(sys.argv)

    # ── 设置应用元信息 ──
    app.setApplicationName("MiLecFrame")
    app.setApplicationDisplayName("MiLecFrame - 照片相框水印工具")
    app.setOrganizationName("FrankZhangCC")

    # ── 设置全局字体 ──
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # ── 设置 Fluent 主题 ──
    # Theme.AUTO: 跟随系统主题（深色/浅色）
    setTheme(Theme.AUTO)

    # ── 创建主窗口 ──
    window = MainWindow()
    window.show()

    logger.info("PySide6 GUI 启动完成")

    # ── 进入事件循环 ──
    exit_code = app.exec()

    # ── 清理 ──
    logger.info("GUI 已关闭")
    sys.exit(exit_code)
