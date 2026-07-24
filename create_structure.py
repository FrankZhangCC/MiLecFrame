# Copyright (c) 2026 FrankZhangCC
# MIT License - see LICENSE file for details

import os

def create_project_structure():
    """创建项目目录结构"""
    directories = [
        'src',
        'src/core',
        'src/gui',
        'src/utils',
        'src/frame_styles',
        'assets',
        'assets/icons',
        'assets/fonts',
        'data',
        'tests'
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"创建目录: {directory}")
        
        # 在每个目录下创建__init__.py文件（除了assets和data）
        if directory.startswith('src'):
            init_file = os.path.join(directory, '__init__.py')
            with open(init_file, 'w', encoding='utf-8') as f:
                f.write('"""MiLeica Frame - %s module"""\n' % directory.split('/')[-1])
            print(f"创建初始化文件: {init_file}")
    
    print("\n项目目录结构创建完成!")

if __name__ == "__main__":
    create_project_structure()