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
    parser = argparse.ArgumentParser(description="MiLeica照片相框程序")
    parser.add_argument("--input", "-i", help="输入图片路径")
    parser.add_argument("--output", "-o", help="输出图片路径")
    parser.add_argument("--style", "-s", help="相框样式")
    parser.add_argument("--gui", action="store_true", default=True, help="启动GUI界面（默认）")
    parser.add_argument("--author", help="作者名")
    parser.add_argument("--location", help="拍摄地点")
    parser.add_argument("--bg-fill", choices=['pure_black', 'pure_white', 'gaussian_black_65', 'gaussian_white_65', 'gaussian_black_35', 'gaussian_white_35'], 
                        default='pure_white', help="背景填充类型")
    parser.add_argument("--font-weight", choices=['light', 'regular', 'medium'], 
                        default='medium', help="字体字重（细体、中等、粗体）")
    parser.add_argument("--batch", action="store_true", help="批量处理模式")
    parser.add_argument("--recursive", action="store_true", help="递归处理子文件夹（仅批量模式）")
    
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
                args.input, 
                args.output, 
                args.style, 
                args.author, 
                args.location, 
                args.bg_fill, 
                args.recursive
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
        if e.returncode == -2:  # 用户中断
            print("\nGUI服务已被用户中断。")
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
            if e.returncode == -2:  # 用户中断
                print("\nGUI服务已被用户中断。")
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


def process_image(input_path, output_path, style=None, author=None, location=None, bg_fill='pure_white', font_weight='medium'):
    """处理单张图片"""
    print(f"处理图片: {input_path} -> {output_path}")
    # 实现图片处理逻辑
    from core.image_processor import ImageProcessor
    
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
    bg_fill='pure_white',
    font_weight='medium',
    recursive=False
):
    """批量处理图片"""
    print(f"批量处理图片: {input_folder} -> {output_folder}")
    
    from core.batch_processor import BatchProcessor
    
    processor = BatchProcessor()
    success = processor.batch_process(
        input_folder=input_folder,
        output_folder=output_folder,
        author=author,
        location=location,
        style_name=style,
        bg_fill_type=bg_fill,
        font_weight=font_weight,
        recursive=recursive
    )
    
    if not success:
        print("批量处理失败")
        sys.exit(1)
    else:
        print("批量处理完成")


# 为了兼容旧版本，保留向后兼容的接口
__all__ = ['main', 'launch_gui', 'process_image', 'batch_process_images']

if __name__ == "__main__":
    main()