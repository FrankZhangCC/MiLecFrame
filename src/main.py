"""
MiLeica Frame - 照片相框程序
=============================

此程序为照片添加包含 EXIF 信息的相框，支持命令行和GUI两种运行模式。

主要功能：
- 解析照片的EXIF信息
- 根据EXIF信息生成相框
- 支持多种相框样式
- 提供GUI界面
"""

import argparse
import sys
import os
from pathlib import Path
import subprocess


def main():
    """程序主入口点"""
    from utils.logging_config import setup_logging
    setup_logging()
    
    from utils.background_fill import BackgroundFillManager

    parser = argparse.ArgumentParser(description="MiLeica Frame - 照片相框程序")
    parser.add_argument("-i", "--input", help="输入图片路径")
    parser.add_argument("-o", "--output", help="输出图片路径")
    parser.add_argument("-s", "--style", help="相框样式名称")
    parser.add_argument("--gui", action="store_true", default=True, help="启动GUI界面（默认）")
    parser.add_argument("--author", help="作者名")
    parser.add_argument("--location", help="拍摄地点")
    parser.add_argument("--bg-fill", choices=BackgroundFillManager.get_keys(), 
                        default=BackgroundFillManager.DEFAULT_FILL, help="背景填充类型")
    parser.add_argument("--font-weight", choices=['light', 'regular', 'medium'], 
                        default='medium', help="字体字重（细体、中等、粗体）")
    parser.add_argument("--batch", action="store_true", help="批量处理模式")
    parser.add_argument("--recursive", action="store_true", help="递归处理子文件夹（仅批量模式）")
    parser.add_argument("--output-format", choices=["JPEG", "PNG"], default="JPEG", help="输出格式（仅批量模式）")
    parser.add_argument("--logo", default="auto", help="Logo选择：auto(自动匹配) / none(无) / 文件名")
    parser.add_argument("--lens-display", choices=['combined', 'camera_only', 'lens_only'],
                        default='combined', help="镜头显示模式")
    parser.add_argument("--use-short-lens", action="store_true", help="使用短版镜头名")
    parser.add_argument("--no-enhance", action="store_true", help="关闭背景增强")
    parser.add_argument("--skip-existing", action="store_true", default=True,
                        help="跳过已存在的输出文件（默认启用）")
    
    args = parser.parse_args()
    
    # 如果没有指定任何参数，则默认启动GUI
    if not args.input and not args.output and not args.batch and not args.recursive:
        args.gui = True
    
    if args.gui:
        try:
            launch_gui()
        except ImportError as e:
            print(f"GUI启动失败，导入错误: {str(e)}")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\n程序已被用户中断。")
            sys.exit(0)
        except Exception as e:
            print(f"GUI启动失败，未知错误: {str(e)}")
            sys.exit(1)
    elif args.batch and args.input and args.output:
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
            )
        except ImportError as e:
            print(f"批量处理模块导入失败: {str(e)}")
            sys.exit(1)
        except Exception as e:
            print(f"批量处理失败，未知错误: {str(e)}")
            sys.exit(1)
    elif args.input and args.output:
        try:
            process_image(args.input, args.output, args.style, args.author, args.location, args.bg_fill, args.font_weight)
        except ImportError as e:
            print(f"图像处理模块导入失败: {str(e)}")
            sys.exit(1)
        except Exception as e:
            print(f"图像处理失败，未知错误: {str(e)}")
            sys.exit(1)
    else:
        parser.print_help()


def launch_gui():
    """启动图形用户界面"""
    print("正在启动GUI界面...")
    print("请在浏览器中打开 http://localhost:8501 查看应用")
    print("按 Ctrl+C 可随时停止服务")
    
    # 获取项目根目录下的gui app文件路径
    gui_app_path = Path(__file__).parent / "gui" / "app.py"
    
    # 获取当前Python解释器路径
    python_executable = sys.executable
    
    # 使用subprocess运行streamlit命令
    try:
        subprocess.run([python_executable, "-m", "streamlit", "run", str(gui_app_path)], check=True)
    except subprocess.CalledProcessError as e:
        if e.returncode in (-2, 1):
            print("\nGUI服务已被用户停止。")
            return
        else:
            print(f"GUI启动失败: {str(e)}")
            sys.exit(1)
    except FileNotFoundError:
        # 如果Python解释器中没有streamlit，尝试直接使用streamlit命令
        try:
            subprocess.run(["streamlit", "run", str(gui_app_path)], check=True)
        except FileNotFoundError:
            print("错误: 未找到streamlit命令，请确保已安装Streamlit")
            print("可通过以下命令安装: pip install streamlit")
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            if e.returncode in (-2, 1):
                print("\nGUI服务已被用户停止。")
                return
            else:
                print(f"GUI启动失败: {str(e)}")
                sys.exit(1)
        except KeyboardInterrupt:
            print("\nGUI服务已被用户中断。")
            return
    except KeyboardInterrupt:
        print("\nGUI服务已被用户中断。")
        return


def process_image(input_path, output_path, style=None, author=None, location=None, bg_fill=None, font_weight='medium'):
    """处理单张图片"""
    print(f"处理图片: {input_path} -> {output_path}")
    # 实现图片处理逻辑
    from core.image_processor import ImageProcessor

    if bg_fill is None:
        from utils.background_fill import BackgroundFillManager
        bg_fill = BackgroundFillManager.DEFAULT_FILL

    processor = ImageProcessor(style_config=style)
    success = processor.process(input_path, output_path, author=author, location=location,
                                style_name=style, bg_fill_type=bg_fill, font_weight=font_weight)
    
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
):
    """批量处理图片"""
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


# 为了兼容旧版本，保留向后兼容的接口
__all__ = ['main', 'launch_gui', 'process_image', 'batch_process_images']

if __name__ == "__main__":
    main()