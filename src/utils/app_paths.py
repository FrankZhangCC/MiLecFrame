# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
应用路径定位模块
=================

统一解决开发环境与 PyInstaller 打包环境下的路径差异问题：

- 开发环境：所有路径基于项目根目录（本文件向上三级）。
- 打包环境（sys.frozen）：
  - **可写数据**（config.json、data/*.csv、日志等）放在 **exe 同目录**，
    保证便携版解压/拷贝后仍能持久化用户数据。
  - **只读资源**（assets/fonts、assets/logos、内置样式配置等）放在
    PyInstaller 解压目录 ``sys._MEIPASS``（onedir 模式为 _internal 子目录）。

注意：打包环境中 PyInstaller 会以 ``utils.app_paths`` 与 ``src.utils.app_paths``
两种包名各加载一份本模块（因为项目内混用了 ``from src.`` 与无前缀导入），
但两处逻辑完全一致，返回值相同，因此无副作用。
"""
import sys
from pathlib import Path


def is_frozen() -> bool:
    """
    判断当前是否运行在 PyInstaller 打包环境中

    Returns:
        True 表示已打包（exe），False 表示源码开发环境
    """
    return bool(getattr(sys, 'frozen', False))


def get_resource_root() -> Path:
    """
    获取只读资源根目录

    - 打包环境：``sys._MEIPASS``（PyInstaller 运行时解压目录）
    - 开发环境：项目根目录（本文件向上三级：src/utils/ → 项目根）

    Returns:
        资源根目录 Path
    """
    if is_frozen():
        # _MEIPASS 在 frozen 环境下由 PyInstaller 引导器设置
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            return Path(meipass)
        # 兜底：异常情况下退回 exe 所在目录
        return Path(sys.executable).resolve().parent
    # 开发环境：src/utils/app_paths.py → 项目根
    return Path(__file__).resolve().parent.parent.parent


def get_app_dir() -> Path:
    """
    获取可写数据根目录（用户数据目录）

    - 打包环境：exe 所在目录（便携版数据与 exe 共存，随文件夹整体移动）
    - 开发环境：项目根目录（保持原有行为）

    Returns:
        可写数据根目录 Path
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent
