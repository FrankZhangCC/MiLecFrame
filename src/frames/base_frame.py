    def calculate_responsive_sizes(self, image: Image.Image) -> Dict[str, int]:
        """
        根据图像尺寸计算响应式参数
        
        Args:
            image: 输入图像
            
        Returns:
            包含各种尺寸参数的字典
        """
        width, height = image.size
        
        # 基于图像尺寸计算文字大小、边距等
        base_font_size = max(24, min(width, height) // 20)  # 从1/50增加到1/20，并将最小字体大小增加到24
        
        # 计算相框边距
        margin_ratio = 0.02  # 边距占图像尺寸的比例
        margin_x = int(width * margin_ratio)
        margin_y = int(height * margin_ratio)
        
        return {
            'font_size': base_font_size,
            'margin_x': margin_x,
            'margin_y': margin_y,
            'line_spacing': int(base_font_size * 1.2),
            'border_width': max(1, base_font_size // 4)
        }