"""
测试自适应颜色功能的脚本
"""

from src.core.renderer import FrameRenderer
from src.frame_styles.style_manager import StyleManager
from PIL import Image
import os

def test_adaptive_colors():
    """
    测试自适应颜色功能在不同背景类型下的表现
    """
    # 初始化渲染器和样式管理器
    renderer = FrameRenderer()
    style_manager = StyleManager()
    
    # 创建一个简单的测试图像
    test_image = Image.new('RGB', (800, 600), color='white')
    
    # 获取普通样式配置（不使用自定义颜色）
    normal_style_config = style_manager.get_style_config('modern_expanded')
    
    if not normal_style_config:
        print("未找到现代扩展样式配置")
        return

    # 测试不同的背景类型
    bg_types = [
        'pure_white',
        'pure_black', 
        'gaussian_white_35',
        'gaussian_black_35',
        'gaussian_white_65',
        'gaussian_black_65'
    ]
    
    for bg_type in bg_types:
        print(f"\n测试背景类型: {bg_type}")
        
        try:
            # 渲染图像
            rendered_image = renderer.render_frame(
                image=test_image,
                exif_data={'make': 'Canon', 'model': 'EOS R5', 'lens_model': 'RF24-70mm'},
                author="Test Author",
                location="Test Location",
                style_config=normal_style_config,
                bg_fill_type=bg_type
            )
            
            # 保存渲染结果
            output_path = f"test_{bg_type}_output.jpg"
            rendered_image.save(output_path)
            print(f"渲染完成，输出文件: {output_path}")
            
        except Exception as e:
            print(f"渲染过程中出现错误: {e}")
    
    # 测试自定义颜色是否优先于自适应颜色
    custom_style_config = style_manager.get_style_config('modern_custom_color')
    
    if custom_style_config:
        print(f"\n测试自定义颜色是否优先于自适应颜色")
        
        for bg_type in ['pure_white', 'pure_black', 'gaussian_white_35', 'gaussian_black_35']:
            try:
                # 渲染图像
                rendered_image = renderer.render_frame(
                    image=test_image,
                    exif_data={'make': 'Canon', 'model': 'EOS R5', 'lens_model': 'RF24-70mm'},
                    author="Test Author",
                    location="Test Location",
                    style_config=custom_style_config,
                    bg_fill_type=bg_type
                )
                
                # 保存渲染结果
                output_path = f"test_custom_overrides_{bg_type}.jpg"
                rendered_image.save(output_path)
                print(f"自定义颜色渲染完成({bg_type})，输出文件: {output_path}")
                
            except Exception as e:
                print(f"渲染过程中出现错误: {e}")
    else:
        print("未找到自定义颜色样式配置")


if __name__ == "__main__":
    test_adaptive_colors()