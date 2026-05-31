# Copyright (c) 2026 FrankZhangCC
# MIT License - see LICENSE file for details

"""
Streamlit入口点
用于启动MiLeica Frame的GUI界面
"""

import sys
from pathlib import Path

# 添加项目根目录到sys.path
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

def main():
    """Streamlit入口点"""
    try:
        from src.gui.app import run_app
        run_app()
    except ImportError as e:
        print(f"GUI启动失败，导入错误: {str(e)}")
        raise e
    except Exception as e:
        print(f"GUI启动失败，未知错误: {str(e)}")
        raise e

if __name__ == "__main__":
    main()