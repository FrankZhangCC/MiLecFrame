# -*- mode: python ; coding: utf-8 -*-
# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details
#
# MiLecFrame PyInstaller 打包配置（onedir 便携版）
#
# 使用方式（推荐通过 build_release.py 一键构建）：
#   .venv\Scripts\pyinstaller MiLecFrame.spec
#
# 目录规划（与 src/utils/app_paths.py 的路径约定一一对应）：
#   - 只读资源 → 打进 _MEIPASS（onedir 下为 dist/MiLecFrame/_internal）：
#       assets/                    字体、Logo 图片
#       src/frame_styles/configs/  内置相框样式配置
#       src/gui_pyside/assets/     样式编辑器样本图
#   - 可写数据 → 由 build_release.py 复制到 exe 同目录（dist/MiLecFrame/）：
#       data/*.csv、data/logo_scale.yaml    设备映射库（GUI 内可编辑）
#       config.json / debug_log.txt 等由程序首次运行时自动创建

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# ── 基础路径：spec 文件所在目录即项目根 ──
PROJECT_ROOT = Path(SPECPATH)

# ── 版本号：保持 src/_version.py 单点一致（含 -dev 后缀的字符串不能直接用作
#    Windows 文件版本，故映射为纯数字元组，字符串用于 ProductVersion） ──
_version_ns = {}
exec(
    (PROJECT_ROOT / 'src' / '_version.py').read_text(encoding='utf-8'),
    _version_ns,
)
VERSION_STR = _version_ns['__version__']
VERSION_TUPLE = tuple(
    int(x) if str(x).isdigit() else 0
    for x in list(_version_ns['__version_info__'])[:4]
)
# 补齐为 4 段（Windows 版本资源要求 a.b.c.d）
VERSION_TUPLE = (VERSION_TUPLE + (0, 0, 0, 0))[:4]

# ── 收集第三方库资源（qss 样式表、图标、字体、动态库等） ──
# 注意：不使用 collect_all()，因其会把 qfluentwidgets 全部子模块作为
# hidden import 收集，其中 multimedia 子模块会连带拖入 scipy、
# QtMultimedia 等约 200MB 的未使用依赖。
datas = []
binaries = []
for _pkg in ('qfluentwidgets', 'pillow_heif'):
    datas += collect_data_files(_pkg)
    binaries += collect_dynamic_libs(_pkg)

# pillow-heif 通过 PIL 插件机制被动态加载，必须显式声明 hidden import，
# 否则打包后无法读取 HEIC/AVIF 图像。
hiddenimports = ['pillow_heif.HeifImagePlugin']

# ── 只读资源：打进 _MEIPASS，由 src/utils/app_paths.py 的 get_resource_root() 定位 ──
# 字体采用精简清单：font_manager 按 "{family}-{weight}.otf" 动态加载，
# 样式配置实际引用的字重如下（新增字重时把对应文件加进 RELEASE_FONT_FILES）：
#   Gotham: light->Light, medium->Medium, regular->Book
#   GlowSansSC-Normal: light->Light, medium->Medium, regular->Regular
RELEASE_FONT_FILES = [
    'Gotham-Light.otf',
    'Gotham-Book.otf',
    'Gotham-Medium.otf',
    'GlowSansSC-Normal-Regular.otf',
    'GlowSansSC-Normal-Light.otf',
    'GlowSansSC-Normal-Medium.otf',
]

datas += [
    # Logo 图片（只读，按品牌自动匹配）
    (str(PROJECT_ROOT / 'assets' / 'logos'), 'assets/logos'),
    # 应用图标（GUI 运行时加载，用于任务栏/标题栏图标）
    # 注意：datas 的目标参数是「目标目录」，不能写完整文件路径，
    # 否则会被当作目录创建（曾导致 QIcon 加载失败、任务栏图标丢失）
    (str(PROJECT_ROOT / 'assets' / 'app_icon.ico'), 'assets'),
    # 内置相框样式配置
    (str(PROJECT_ROOT / 'src' / 'frame_styles' / 'configs'),
     'src/frame_styles/configs'),
    # 样式编辑器样本图
    (str(PROJECT_ROOT / 'src' / 'gui_pyside' / 'assets'),
     'src/gui_pyside/assets'),
]

# 精简字体清单（避免全量 391MB 字体全部入包）
for _font_name in RELEASE_FONT_FILES:
    _font_path = PROJECT_ROOT / 'assets' / 'fonts' / _font_name
    if _font_path.exists():
        datas.append((str(_font_path), 'assets/fonts'))
    else:
        print(f'警告: 字体文件不存在，已跳过: {_font_name}')

# ── 应用图标：assets/app_icon.ico 存在则使用，否则用 PyInstaller 默认图标 ──
_icon_path = PROJECT_ROOT / 'assets' / 'app_icon.ico'

a = Analysis(
    [str(PROJECT_ROOT / 'src' / 'main.py')],
    # 项目根使「from src.xxx」可解析；src/ 使顶层包导入兼容
    pathex=[str(PROJECT_ROOT), str(PROJECT_ROOT / 'src')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 明确排除未使用/已封存的重量级依赖，减小发行体积
        'pandas',        # 仅 gui_legacy（已封存）使用
        'streamlit',     # gui_legacy 时代的 Web GUI
        'scipy',         # 仅 qfluentwidgets.multimedia（未使用）间接依赖
        'pyqtgraph',
        'tkinter', 'matplotlib', 'IPython', 'jupyter',
        'pytest', 'PyInstaller',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MiLecFrame',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                  # 便携发行版：双击不弹控制台窗口
    disable_windowed_traceback=True,  # windowed 模式下崩溃时不弹错误框
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(_icon_path) if _icon_path.exists() else None,
    version=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MiLecFrame',
)
