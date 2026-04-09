"""
测试自定义文本颜色功能的脚本
"""

from src.core.renderer import FrameRenderer
from src.frame_styles.style_manager import StyleManager
from PIL import Image
import os

def test_custom_text_colors():
    """
    测试在Default_TestFrame样式中为timestamp和location设置自定义颜色
    """
    # 初始化渲染器和样式管理器
    renderer = FrameRenderer()
    style_manager = StyleManager()
    
    # 创建一个简单的测试图像
    test_image = Image.new('RGB', (800, 600), color='white')
    
    # 获取Default_TestFrame样式配置
    testframe_style_config = style_manager.get_style_config('Default_TestFrame')
    
    if not testframe_style_config:
        print("未找到Default_TestFrame样式配置")
        return

    print(f"Default_TestFrame配置中包含自定义颜色设置:")
    colors = testframe_style_config.get('colors', {})
    print(f"- custom_timestamp_color: {colors.get('custom_timestamp_color')}")
    print(f"- custom_location_color: {colors.get('custom_location_color')}")

    # 渲染图像
    print(f"\n开始渲染图像...")
    try:
        rendered_image = renderer.render_frame(
            image=test_image,
            exif_data={
                'make': 'Canon', 
                'model': 'EOS R5', 
                'lens_model': 'RF24-70mm',
                'datetime_original': '2023.06.15 14:30:45'  # 使用正确的键名
            },
            author="Test Author",
            location="Test Location",
            style_config=testframe_style_config,
            bg_fill_type='gaussian_black_35'
        )
        
        # 保存渲染结果
        output_path = "test_custom_text_colors_output.jpg"
        rendered_image.save(output_path)
        print(f"渲染完成，输出文件: {output_path}")
        
    except Exception as e:
        print(f"渲染过程中出现错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_custom_text_colors()