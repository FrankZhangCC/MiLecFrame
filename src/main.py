# Copyright (c) 2026 FrankZhangCC
# MIT License - see LICENSE file for details

"""
MiLec Frame - 照片相框程序
=============================

此程序为照片添加包含 EXIF 信息的相框，支持命令行和 PySide6 GUI 两种运行模式。

主要功能：
- 解析照片的EXIF信息
- 根据EXIF信息生成相框
- 支持多种相框样式
- 提供 PySide6 桌面 GUI
"""

import argparse
import sys
import os
from pathlib import Path


def main():
    """程序主入口点"""
    from utils.logging_config import setup_logging
    setup_logging()
    
    from utils.background_fill import BackgroundFillManager

    parser = argparse.ArgumentParser(description="MiLeica Frame - 照片相框程序")
    parser.add_argument("-i", "--input", help="输入图片路径")
    parser.add_argument("-o", "--output", help="输出图片路径")
    parser.add_argument("-s", "--style", help="相框样式名称")
    parser.add_argument("--author", help="作者名")
    parser.add_argument("--location", help="拍摄地点")
    parser.add_argument("--bg-fill", choices=BackgroundFillManager.get_keys(), 
                        default=BackgroundFillManager.DEFAULT_FILL, help="背景填充类型")
    parser.add_argument("--font-weight", choices=['light', 'regular', 'medium'], 
                        default='medium', help="字体字重（细体、中等、粗体）")
    parser.add_argument("--batch", action="store_true", help="批量处理模式")
    parser.add_argument("--recursive", action="store_true", help="递归处理子文件夹（仅批量模式）")
    parser.add_argument("--output-format", choices=["JPEG", "PNG"], default="JPEG", help="输出格式")
    parser.add_argument("--logo", default="auto", help="Logo选择：auto(自动匹配) / none(无) / 文件名")
    parser.add_argument("--lens-display", choices=['combined', 'camera_only', 'lens_only'],
                        default='combined', help="镜头显示模式")
    parser.add_argument("--use-short-lens", action="store_true", help="使用短版镜头名")
    parser.add_argument("--no-enhance", action="store_true", help="关闭背景增强")
    parser.add_argument("--skip-existing", action="store_true", default=True,
                        help="跳过已存在的输出文件（默认启用）")
    parser.add_argument("--watermark-text", default=None, help="水印文字内容（为空则不启用水印）")
    parser.add_argument("--watermark-position", choices=['top-left', 'top-right', 'bottom-left',
                        'bottom-right', 'top-center', 'bottom-center'], default='bottom-right',
                        help="水印位置（默认: bottom-right）")
    parser.add_argument("--watermark-opacity", type=int, default=50, choices=range(0, 101),
                        metavar="[0-100]", help="水印不透明度，0-100（默认: 50）")
    parser.add_argument("--watermark-color", choices=['white', 'black'], default='white',
                        help="水印颜色（默认: white）")
    parser.add_argument("--use-gps-location", action="store_true",
                        help="使用GPS坐标替换手动拍摄地点（批量模式逐张处理）")
    parser.add_argument("--custom-text", default=None, help="自定义文本内容（支持多行，用双引号包裹）")
    
    args = parser.parse_args()
    
    # 如果没有指定任何参数，则默认启动 PySide6 桌面 GUI
    if not args.input and not args.output and not args.batch and not args.recursive:
        try:
            launch_pyside_gui()
        except ImportError as e:
            print(f"PySide6 GUI 启动失败，导入错误: {str(e)}")
            print("请确保已安装 PySide6-Fluent-Widgets: pip install \"PySide6-Fluent-Widgets[full]\"")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\n程序已被用户中断。")
            sys.exit(0)
        except Exception as e:
            print(f"PySide6 GUI 启动失败，未知错误: {str(e)}")
            sys.exit(1)
    
    if args.batch and args.input and args.output:
        try:
            batch_process_images(
                input_folder=args.input,
                output_folder=args.output,
                style=args.style,
                author=args.author,
                location=args.location,
                bg_fill=args.bg_fill,
                font_weight=args.font_weight,
                recursive=args.recursive,
                output_format=args.output_format,
                logo=args.logo,
                lens_display=args.lens_display,
                use_short_lens=args.use_short_lens,
                no_enhance=args.no_enhance,
                skip_existing=args.skip_existing,
                use_gps_location=args.use_gps_location,
                watermark_text=args.watermark_text,
                watermark_position=args.watermark_position,
                watermark_opacity=args.watermark_opacity,
                watermark_color=args.watermark_color,
                custom_text=args.custom_text,
            )
        except ImportError as e:
            print(f"批量处理模块导入失败: {str(e)}")
            sys.exit(1)
        except Exception as e:
            print(f"批量处理失败，未知错误: {str(e)}")
            sys.exit(1)
    elif args.input and args.output:
        try:
            process_image(
                input_path=args.input,
                output_path=args.output,
                style=args.style,
                author=args.author,
                location=args.location,
                bg_fill=args.bg_fill,
                font_weight=args.font_weight,
                logo=args.logo,
                lens_display=args.lens_display,
                use_short_lens=args.use_short_lens,
                no_enhance=args.no_enhance,
                output_format=args.output_format,
                skip_existing=args.skip_existing,
                watermark_text=args.watermark_text,
                watermark_position=args.watermark_position,
                watermark_opacity=args.watermark_opacity,
                watermark_color=args.watermark_color,
                custom_text=args.custom_text,
            )
        except ImportError as e:
            print(f"图像处理模块导入失败: {str(e)}")
            sys.exit(1)
        except Exception as e:
            print(f"图像处理失败，未知错误: {str(e)}")
            sys.exit(1)
    else:
        parser.print_help()


def launch_pyside_gui():
    """启动 PySide6 原生桌面 GUI"""
    print("正在启动 PySide6 桌面 GUI...")
    print("按 Ctrl+C 可随时停止")

    from gui_pyside.app import run_pyside_app
    run_pyside_app()

def process_image(input_path, output_path, style=None, author=None, location=None, bg_fill=None,
                  font_weight='medium', logo="auto", lens_display='combined',
                  use_short_lens=False, no_enhance=False, output_format="JPEG",
                  skip_existing=True, watermark_text=None, watermark_position='bottom-right',
                  watermark_opacity=50, watermark_color='white', custom_text=None):
    """
    处理单张图片

    Args:
        input_path: 输入图片路径
        output_path: 输出图片路径
        style: 相框样式名称
        author: 作者姓名
        location: 拍摄地点
        bg_fill: 背景填充类型
        font_weight: 字体字重 (light/regular/medium)
        logo: Logo选择：auto(自动匹配) / none(无) / 文件名
        lens_display: 镜头显示模式 (combined/camera_only/lens_only)
        use_short_lens: 是否使用短版镜头名
        no_enhance: 关闭背景增强
        output_format: 输出格式 (JPEG/PNG)
        skip_existing: 跳过已存在的输出文件
        watermark_text: 水印文字内容（None/空字符串表示不启用水印）
        watermark_position: 水印位置
        watermark_opacity: 水印不透明度 (0-100)
        watermark_color: 水印颜色 (white/black)
    """
    # ===== 跳过已存在的输出文件 =====
    if skip_existing and os.path.exists(output_path):
        print(f"⏭ 跳过（输出文件已存在）: {output_path}")
        return

    print(f"处理图片: {input_path} -> {output_path}")

    from core.image_processor import ImageProcessor

    if bg_fill is None:
        from utils.background_fill import BackgroundFillManager
        bg_fill = BackgroundFillManager.DEFAULT_FILL

    # ===== 组装水印装饰参数 =====
    decorations = None
    if watermark_text and watermark_text.strip():
        color_map = {'white': (255, 255, 255), 'black': (0, 0, 0)}
        decorations = [{
            'type': 'watermark',
            'params': {
                'text': watermark_text.strip(),
                'position': watermark_position,
                'opacity': watermark_opacity,
                'color': color_map.get(watermark_color, (255, 255, 255))
            }
        }]

    # ===== 组装 logo 参数 =====
    logo_filename = None  # None=使用样式默认配置
    if logo == "none":
        logo_filename = ""  # 空字符串=不使用Logo
    elif logo != "auto":
        logo_filename = logo  # 手动指定文件名

    # ===== 组装饱和度覆盖 =====
    saturation_override = 1.0 if no_enhance else None

    # ===== 强制输出格式（单张模式下通过对输出路径扩展名处理） =====
    actual_output_path = output_path
    output_ext = output_path.rsplit('.', 1)[-1].upper() if '.' in output_path else ''
    if output_format.upper() == "PNG" and output_ext != "PNG":
        actual_output_path = output_path.rsplit('.', 1)[0] + '.png'
        print(f"  输出格式为 PNG，输出路径调整为: {actual_output_path}")
    elif output_format.upper() == "JPEG" and output_ext not in ("JPG", "JPEG"):
        actual_output_path = output_path.rsplit('.', 1)[0] + '.jpg'
        print(f"  输出格式为 JPEG，输出路径调整为: {actual_output_path}")

    processor = ImageProcessor(style_config=style)
    success = processor.process(input_path, actual_output_path,
                                author=author, location=location,
                                style_name=style, bg_fill_type=bg_fill,
                                font_weight=font_weight,
                                decorations=decorations,
                                logo_filename=logo_filename,
                                lens_display_mode=lens_display,
                                use_short_lens=use_short_lens,
                                saturation_override=saturation_override,
                                custom_text=custom_text)

    if not success:
        print("图片处理失败")
        sys.exit(1)


def batch_process_images(
    input_folder,
    output_folder,
    style=None,
    author=None,
    location=None,
    bg_fill=None,
    font_weight='medium',
    recursive=False,
    output_format="JPEG",
    logo="auto",
    lens_display='combined',
    use_short_lens=False,
    no_enhance=False,
    skip_existing=True,
    use_gps_location=False,
    watermark_text=None,
    watermark_position='bottom-right',
    watermark_opacity=50,
    watermark_color='white',
    custom_text=None,
):
    """
    批量处理图片

    Args:
        input_folder: 输入文件夹路径
        output_folder: 输出文件夹路径
        style: 相框样式名称
        author: 作者姓名
        location: 拍摄地点
        bg_fill: 背景填充类型
        font_weight: 字体字重 (light/regular/medium)
        recursive: 递归处理子文件夹
        output_format: 输出格式 (JPEG/PNG)
        logo: Logo选择策略 (auto/none/文件名)
        lens_display: 镜头显示模式 (combined/camera_only/lens_only)
        use_short_lens: 是否使用短版镜头名
        no_enhance: 关闭背景增强
        skip_existing: 跳过已存在的输出文件
        use_gps_location: 使用GPS坐标替换手动拍摄地点
        watermark_text: 水印文字内容（None/空字符串表示不启用水印）
        watermark_position: 水印位置
        watermark_opacity: 水印不透明度 (0-100)
        watermark_color: 水印颜色 (white/black)
    """
    print(f"批量处理图片: {input_folder} -> {output_folder}")

    from core.batch_processor import BatchProcessor

    # 使用默认背景填充类型
    if bg_fill is None:
        from utils.background_fill import BackgroundFillManager
        bg_fill = BackgroundFillManager.DEFAULT_FILL

    # 发现输入文件
    input_files = BatchProcessor.discover_files(input_folder, recursive=recursive)
    if not input_files:
        print("未找到支持的图像文件")
        sys.exit(1)

    print(f"找到 {len(input_files)} 个文件待处理")
    input_paths = [str(f) for f in input_files]

    # 进度回调（CLI 用 print 输出）
    def cli_progress(done, total, filename, status):
        print(f"  [{done}/{total}] {filename} - {status}")

    # ===== 组装水印装饰参数 =====
    decorations = None
    if watermark_text and watermark_text.strip():
        color_map = {'white': (255, 255, 255), 'black': (0, 0, 0)}
        decorations = [{
            'type': 'watermark',
            'params': {
                'text': watermark_text.strip(),
                'position': watermark_position,
                'opacity': watermark_opacity,
                'color': color_map.get(watermark_color, (255, 255, 255))
            }
        }]

    saturation_override = 1.0 if no_enhance else None

    processor = BatchProcessor()
    result = processor.batch_process(
        input_files=input_paths,
        output_folder=output_folder,
        author=author,
        location=location,
        style_name=style,
        bg_fill_type=bg_fill,
        output_format=output_format,
        font_weight=font_weight,
        logo_selection=logo,
        lens_display_mode=lens_display,
        use_short_lens=use_short_lens,
        saturation_override=saturation_override,
        progress_callback=cli_progress,
        skip_existing=skip_existing,
        use_gps_location=use_gps_location,
        decorations=decorations,
        custom_text=custom_text,
    )

    # 输出结果汇总
    print(f"\n===== 批量处理完成 =====")
    print(f"  总计: {result.total} 张")
    print(f"  成功: {result.success_count} 张")
    print(f"  失败: {result.fail_count} 张")
    print(f"  跳过: {result.skip_count} 张")

    if result.failed_files:
        print(f"\n失败详情:")
        for file_path, error in result.failed_files:
            from pathlib import Path
            print(f"  - {Path(file_path).name}: {error}")

    if result.fail_count > 0:
        sys.exit(1)
    else:
        print("全部处理完成！")


__all__ = ['main', 'launch_pyside_gui', 'process_image', 'batch_process_images']

if __name__ == "__main__":
    main()