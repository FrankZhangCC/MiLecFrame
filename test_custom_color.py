"""
测试自定义文字颜色功能的脚本
"""

from src.core.renderer import FrameRenderer
from src.frame_styles.style_manager import StyleManager
from PIL import Image
import os

def test_custom_color_feature():
    """
    测试自定义颜色功能
    """
    # 初始化渲染器和样式管理器
    renderer = FrameRenderer()
    style_manager = StyleManager()
    
    # 创建一个简单的测试图像
    test_image = Image.new('RGB', (800, 600), color='white')
    
    # 获取自定义颜色样式配置
    custom_style_config = style_manager.get_style_config('modern_custom_color')
    
    if custom_style_config:
        print("找到自定义颜色样式配置")
        print(f"样式名称: {custom_style_config.get('name')}")
        print(f"颜色配置: {custom_style_config.get('colors', {})}")
        
        # 尝试渲染带有自定义颜色的图像
        try:
            rendered_image = renderer.render_frame(
                image=test_image,
                exif_data={'make': 'Canon', 'model': 'EOS R5', 'lens_model': 'RF24-70mm'},
                author="Test Author",
                location="Test Location",
                style_config=custom_style_config,
                bg_fill_type="pure_white"
            )
            
            # 保存渲染结果
            output_path = "test_custom_color_output.jpg"
            rendered_image.save(output_path)
            print(f"渲染完成，输出文件: {output_path}")
            
        except Exception as e:
            print(f"渲染过程中出现错误: {e}")
    else:
        print("未找到自定义颜色样式配置")
    
    # 获取普通样式配置进行对比
    normal_style_config = style_manager.get_style_config('modern_expanded')
    
    if normal_style_config:
        print("\n找到普通样式配置")
        print(f"样式名称: {normal_style_config.get('name')}")
        print(f"颜色配置: {normal_style_config.get('colors', {})}")
        
        # 尝试渲染带有普通颜色的图像
        try:
            rendered_image_normal = renderer.render_frame(
                image=test_image,
                exif_data={'make': 'Canon', 'model': 'EOS R5', 'lens_model': 'RF24-70mm'},
                author="Test Author",
                location="Test Location",
                style_config=normal_style_config,
                bg_fill_type="pure_white"
            )
            
            # 保存渲染结果
            output_path_normal = "test_normal_color_output.jpg"
            rendered_image_normal.save(output_path_normal)
            print(f"普通样式渲染完成，输出文件: {output_path_normal}")
            
        except Exception as e:
            print(f"普通样式渲染过程中出现错误: {e}")


if __name__ == "__main__":
    test_custom_color_feature()