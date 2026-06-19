# Copyright (c) 2026 FrankZhangCC
# MIT License - see LICENSE file for details

import os
import sys
import subprocess
import venv

def create_virtual_environment():
    """创建虚拟环境"""
    env_dir = os.path.join(os.getcwd(), 'venv')
    
    print("正在创建虚拟环境...")
    venv.create(env_dir, with_pip=True)
    print(f"虚拟环境已创建在: {env_dir}")
    
    # 获取虚拟环境中pip的路径
    if os.name == 'nt':  # Windows
        pip_path = os.path.join(env_dir, 'Scripts', 'pip.exe')
        python_path = os.path.join(env_dir, 'Scripts', 'python.exe')
    else:  # Unix/Linux/MacOS
        pip_path = os.path.join(env_dir, 'bin', 'pip')
        python_path = os.path.join(env_dir, 'bin', 'python')
    
    # 升级pip
    print("正在升级pip...")
    subprocess.check_call([python_path, '-m', 'pip', 'install', '--upgrade', 'pip'])
    
    # 尝试使用信任的主机安装依赖
    print("正在安装依赖包...")
    try:
        subprocess.check_call([
            pip_path, 'install', 
            '--trusted-host', 'pypi.org', 
            '--trusted-host', 'pypi.python.org', 
            '--trusted-host', 'files.pythonhosted.org',
            '-r', 'requirements.txt'
        ])
    except subprocess.CalledProcessError:
        print("通过信任主机方式安装失败，尝试逐个安装依赖...")
        # 如果批量安装失败，尝试逐个安装关键依赖
        packages = ['Pillow>=9.0.0', 'piexif>=1.1.3', 'numpy>=1.21.0', 'streamlit>=1.20.0']
        for package in packages:
            try:
                subprocess.check_call([
                    pip_path, 'install', 
                    '--trusted-host', 'pypi.org', 
                    '--trusted-host', 'pypi.python.org', 
                    '--trusted-host', 'files.pythonhosted.org',
                    package
                ])
            except subprocess.CalledProcessError:
                print(f"警告: 无法安装 {package}，继续下一个...")
    
    print("\n虚拟环境设置完成！")
    print(f"激活方式:")
    print(f"  Windows: venv\\Scripts\\activate")
    print(f"  Linux/Mac: source venv/bin/activate")
    
    return env_dir

if __name__ == "__main__":
    create_virtual_environment()