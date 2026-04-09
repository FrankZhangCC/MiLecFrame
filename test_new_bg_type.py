"""
测试新增背景类型列表功能的脚本
"""

from src.core.renderer import FrameRenderer
from src.frame_styles.style_manager import StyleManager
from PIL import Image
import os

def test_new_background_types():
    """
    测试新增背景类型是否能正确被分类处理
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

    # 测试新增的背景类型
    # 添加一些假设的新背景类型到渲染器中
    renderer.dark_bg_types.append('new_dark_bg_type')
    renderer.light_bg_types.append('new_light_bg_type')
    
    new_bg_types = [
        'new_dark_bg_type',
        'new_light_bg_type'
    ]
    
    for bg_type in new_bg_types:
        print(f"\n测试新增背景类型: {bg_type}")
        
        # 确定应该使用的文字颜色
        if any(bg_type.startswith(dark_type) for dark_type in renderer.dark_bg_types):
            expected_color = "白色 (255, 255, 255)"
        else:
            expected_color = "黑色 (0, 0, 0)"
        
        print(f"预期文字颜色: {expected_color}")
        
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
    
    # 验证原来的背景类型仍然正常工作
    print(f"\n验证原来的背景类型是否仍然正常工作...")
    original_bg_types = ['pure_white', 'pure_black']
    
    for bg_type in original_bg_types:
        print(f"测试原背景类型: {bg_type}")
        
        try:
            rendered_image = renderer.render_frame(
                image=test_image,
                exif_data={'make': 'Canon', 'model': 'EOS R5', 'lens_model': 'RF24-70mm'},
                author="Test Author",
                location="Test Location",
                style_config=normal_style_config,
                bg_fill_type=bg_type
            )
            
            output_path = f"test_original_{bg_type}_output.jpg"
            rendered_image.save(output_path)
            print(f"原背景类型渲染完成，输出文件: {output_path}")
            
        except Exception as e:
            print(f"原背景类型渲染过程中出现错误: {e}")
    
    # 移除测试添加的类型
    renderer.dark_bg_types.remove('new_dark_bg_type')
    renderer.light_bg_types.remove('new_light_bg_type')
    
    print(f"\n背景类型列表管理测试完成！")
    print(f"当前深色背景类型: {renderer.dark_bg_types}")
    print(f"当前浅色背景类型: {renderer.light_bg_types}")


if __name__ == "__main__":
    test_new_background_types()