# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
MiLecFrame 一键打包脚本（onedir 便携版）
========================================

功能：
1. 可选：从 PNG 生成多尺寸 ICO 应用图标（assets/app_icon.ico）
2. 调用 PyInstaller 按 MiLecFrame.spec 构建 onedir 便携版
3. 将可写数据种子文件（data/*.csv、logo_scale.yaml）复制到
   dist/MiLecFrame/data/（exe 同目录，与 src/utils/app_paths.py 约定一致）
4. 可选：压缩为发行用 zip 包 dist/MiLecFrame_v<版本>_win64_portable.zip

用法（需在 venv 激活后运行）：
    python build_release.py                  # 普通打包
    python build_release.py --zip            # 打包并生成 zip 发行包
    python build_release.py --icon path/to/icon.png   # 从 PNG 生成图标并打包
    python build_release.py --no-clean       # 不清除 build 缓存（增量调试用）
"""
import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from PIL import Image

# ── 路径常量 ──
PROJECT_ROOT = Path(__file__).resolve().parent
SPEC_FILE = PROJECT_ROOT / 'MiLecFrame.spec'
DIST_DIR = PROJECT_ROOT / 'dist'
APP_DIR = DIST_DIR / 'MiLecFrame'
ICON_ICO_PATH = PROJECT_ROOT / 'assets' / 'app_icon.ico'

# ── 可写数据种子文件：打包后复制到 exe 同目录 data/ ──
SEED_DATA_FILES = [
    'camera_map.csv',
    'lens_map.csv',
    'logo_scale.yaml',
]

# ICO 图标包含的尺寸集合（Windows 资源管理器/任务栏各档位）
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def read_version() -> str:
    """从 src/_version.py 读取版本号（保持单点一致）"""
    ns = {}
    exec((PROJECT_ROOT / 'src' / '_version.py').read_text(encoding='utf-8'), ns)
    return ns['__version__']


def generate_ico(png_path: Path) -> Path:
    """
    从 PNG 生成多尺寸 ICO 图标

    Args:
        png_path: 源 PNG 文件路径（建议 ≥256x256）

    Returns:
        生成的 ICO 路径（assets/app_icon.ico）
    """
    png_path = Path(png_path)
    if not png_path.exists():
        raise FileNotFoundError(f'PNG 图标不存在: {png_path}')

    print(f'[1/4] 从 PNG 生成 ICO 图标: {png_path.name}')
    img = Image.open(png_path)
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    # Pillow 会根据 sizes 列表生成包含多个尺寸帧的 ICO
    img.save(ICON_ICO_PATH, format='ICO', sizes=ICO_SIZES)
    print(f'      已生成: {ICON_ICO_PATH}')
    return ICON_ICO_PATH


def run_pyinstaller(no_clean: bool) -> None:
    """调用 PyInstaller 按 spec 构建"""
    print('[2/4] 调用 PyInstaller 构建 onedir 便携版...')
    cmd = [sys.executable, '-m', 'PyInstaller', str(SPEC_FILE), '--noconfirm']
    if not no_clean:
        cmd.append('--clean')
    # 继承当前环境，实时输出构建日志
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        raise RuntimeError(f'PyInstaller 构建失败，退出码 {result.returncode}')


def seed_writable_data() -> None:
    """将可写数据种子文件复制到 dist/MiLecFrame/data/"""
    print('[3/4] 复制可写数据种子文件到 exe 同目录 data/ ...')
    target_dir = APP_DIR / 'data'
    target_dir.mkdir(parents=True, exist_ok=True)

    source_dir = PROJECT_ROOT / 'data'
    for name in SEED_DATA_FILES:
        src = source_dir / name
        dst = target_dir / name
        if src.exists():
            shutil.copy2(src, dst)
            print(f'      已复制: {name}')
        else:
            print(f'      跳过（不存在）: {name}')

    # config.json 若已存在则一并带入（首次运行无 config 时程序会自动创建）
    config_src = PROJECT_ROOT / 'config.json'
    if config_src.exists():
        shutil.copy2(config_src, APP_DIR / 'config.json')
        print('      已复制: config.json')


def make_zip_package(version: str) -> Path:
    """将 dist/MiLecFrame 压缩为发行 zip 包"""
    print('[4/4] 生成 zip 发行包...')
    zip_path = DIST_DIR / f'MiLecFrame_v{version}_win64_portable.zip'
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(APP_DIR.rglob('*')):
            if file.is_file():
                # zip 内保留 MiLecFrame/ 顶层目录，解压后即为完整便携文件夹
                arcname = file.relative_to(DIST_DIR)
                zf.write(file, arcname)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f'      已生成: {zip_path.name}（{size_mb:.1f} MB）')
    return zip_path


def main():
    """打包主流程"""
    parser = argparse.ArgumentParser(description='MiLecFrame 一键打包（onedir 便携版）')
    parser.add_argument('--icon', metavar='PNG', default=None,
                        help='从指定 PNG 生成应用图标（建议 >=256x256）')
    parser.add_argument('--zip', action='store_true',
                        help='打包完成后生成 zip 发行包')
    parser.add_argument('--no-clean', action='store_true',
                        help='不清除 build 缓存（增量调试用）')
    args = parser.parse_args()

    version = read_version()
    print(f'===== MiLecFrame 便携版打包 v{version} =====')

    # 1. 图标生成
    if args.icon:
        generate_ico(args.icon)
    elif ICON_ICO_PATH.exists():
        print('[1/4] 使用已有图标: assets/app_icon.ico')
    else:
        print('[1/4] 未提供图标，将使用 PyInstaller 默认图标')
        print('      提示: python build_release.py --icon <png路径> 可生成应用图标')

    # 2. PyInstaller 构建
    run_pyinstaller(no_clean=args.no_clean)

    # 3. 种子数据
    seed_writable_data()

    # 4. zip 发行包
    if args.zip:
        make_zip_package(version)

    print(f'===== 打包完成：{APP_DIR} =====')
    print('便携版使用说明：')
    print('  - 双击 MiLecFrame.exe 启动 GUI')
    print('  - data/ 为设备映射库，styles/ 为用户自建样式，均可随文件夹整体移动')
    print('  - 整个 MiLecFrame 文件夹拷贝到任意 Windows 电脑即可运行（无需安装）')


if __name__ == '__main__':
    main()
