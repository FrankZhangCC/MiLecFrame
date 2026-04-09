"""
测试亮色/暗色自定义颜色功能的脚本
"""

from src.core.renderer import FrameRenderer
from src.frame_styles.style_manager import StyleManager
from PIL import Image
import os

def test_light_dark_colors():
    """
    测试在Default_TestFrame样式中为timestamp和location设置亮色/暗色自定义颜色
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
    print(f"- custom_timestamp_light_color: {colors.get('custom_timestamp_light_color')}")
    print(f"- custom_timestamp_dark_color: {colors.get('custom_timestamp_dark_color')}")
    print(f"- custom_location_light_color: {colors.get('custom_location_light_color')}")
    print(f"- custom_location_dark_color: {colors.get('custom_location_dark_color')}")

    # 测试暗色背景 (gaussian_black_35)
    print(f"\n开始测试暗色背景 (gaussian_black_35)...")
    try:
        rendered_image_dark = renderer.render_frame(
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
        output_path_dark = "test_dark_bg_output.jpg"
        rendered_image_dark.save(output_path_dark)
        print(f"暗色背景渲染完成，输出文件: {output_path_dark}")
        
    except Exception as e:
        print(f"暗色背景渲染过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

    # 测试亮色背景 (gaussian_white_35)
    print(f"\n开始测试亮色背景 (gaussian_white_35)...")
    try:
        rendered_image_light = renderer.render_frame(
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
            bg_fill_type='gaussian_white_35'
        )
        
        # 保存渲染结果
        output_path_light = "test_light_bg_output.jpg"
        rendered_image_light.save(output_path_light)
        print(f"亮色背景渲染完成，输出文件: {output_path_light}")
        
    except Exception as e:
        print(f"亮色背景渲染过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

    print("\n测试完成！请检查输出的两张图片以验证颜色设置。")


if __name__ == "__main__":
    test_light_dark_colors()