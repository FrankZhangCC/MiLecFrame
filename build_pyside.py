"""
PyInstaller 构建脚本 — MiLecFrame PySide6 桌面版

使用方法：
    python build_pyside.py

或在激活的 venv 中：
    pyinstaller build_pyside.py

输出位置：dist/MiLecFrame/
"""
import sys
import os
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve()
PROJECT = ROOT.parent

# ── 收集数据资源 ──
# 格式：(源路径, 目标目录) → PyInstaller --add-data
datas = [
    # 相机/镜头映射表
    (str(PROJECT / "data" / "camera_map.csv"), "data"),
    (str(PROJECT / "data" / "lens_map.csv"), "data"),
    # 相框样式配置
    (str(PROJECT / "src" / "frame_styles" / "configs"), "frame_styles/configs"),
    # Logo 图片
    (str(PROJECT / "assets" / "logos"), "assets/logos"),
]

# ── 字体说明 ──
# 字体由用户自行放入 assets/fonts/，不强制打包。
# 无自定义字体时自动使用系统预装字体。

add_data_args = []
for src, dst in datas:
    add_data_args.extend(["--add-data", f"{src}{os.pathsep}{dst}"])

# ── 构建参数 ──
# 入口点：新建 run.py 调用 gui_pyside.app.run_pyside_app()
# 或直接用 main.py → launch_pyside_gui()
entry_point = str(PROJECT / "src" / "main.py")

args = [
    entry_point,
    "--name", "MiLecFrame",
    "--onedir",                     # 单目录模式（比 onefile 更可靠）
    "--windowed",                   # 无控制台窗口（GUI 应用）
    "--clean",                      # 清理缓存
    "--noconfirm",                  # 覆盖旧输出
    "--log-level", "INFO",
    # Python 源码路径
    "--paths", str(PROJECT / "src"),
] + add_data_args

# ── 排除不需要的模块（减小体积） ──
excludes = [
    "tkinter", "test", "pdb", "idlelib",
    "matplotlib", "notebook", "ipykernel",
]
for mod in excludes:
    args.extend(["--exclude-module", mod])

print("=" * 60)
print("MiLecFrame PyInstaller 构建")
print("=" * 60)
print(f"入口点: {entry_point}")
print(f"输出: dist/MiLecFrame/")
print(f"数据文件: {len(datas)} 项")

PyInstaller.__main__.run(args)

print("\n构建完成！")
print("将字体文件放入 dist/MiLecFrame/assets/fonts/ 后即可运行")
