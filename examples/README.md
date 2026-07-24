# 示例配置文件

本目录包含从框架中移除但仍可作为参考的样式配置文件示例。这些文件可以作为您创建新样式时的参考。

## 文件列表

### 1. modern.json
现代简约风格的基本配置，使用JSON格式。

### 2. modern_custom_color.yaml
现代风格自定义颜色相框配置，支持在配置中指定文字颜色，使用YAML格式。

### 3. modern_expanded.yaml
现代风格扩展相框配置，具有可调节的扩展画布和灵活的文字布局，使用YAML格式。

### 4. modern_with_font_weights.json
支持字体字重选择的现代简约风格配置，使用JSON格式。

## 配置文件格式说明

### JSON格式特点：
- 结构清晰，易于解析
- 支持嵌套对象和数组
- 适合程序化生成配置

### YAML格式特点：
- 更好的可读性
- 支持注释
- 适合复杂配置结构

## 配置参数详解

### 1. name (名称)
- **含义**: 样式名称，用于在程序中识别此样式
- **类型**: 字符串
- **编写方式**:
  - JSON: `"name": "style_name"`
  - YAML: `name: "style_name"`

### 2. description (描述)
- **含义**: 对样式的简短描述，帮助用户了解样式特点
- **类型**: 字符串
- **编写方式**:
  - JSON: `"description": "样式描述"`
  - YAML: `description: "样式描述"`

### 3. layout (布局配置)
- **含义**: 控制相框的整体布局，包括边框、信息位置等
- **类型**: 对象/字典
- **子参数**:
  - **border_width**: 边框宽度 (数字)
  - **border_position**: 边框位置 ('inner' 或 'outer')
  - **info_position**: 信息位置 ('top', 'bottom', 'left', 'right')
  - **info_height_ratio**: 信息区域高度比例 (0.0-1.0之间的数字)
  - **expand_canvas**: 是否扩展画布 (布尔值)
  - **top/bottom/left/right**: 扩展画布各方向的扩展比例 (浮点数)
- **编写方式**:
  - JSON:
    ```json
    "layout": {
      "border_width": 5,
      "border_position": "outer",
      "info_position": "bottom",
      "info_height_ratio": 0.08,
      "expand_canvas": {
        "enabled": true,
        "top": 0.1,
        "bottom": 0.15,
        "left": 0.05,
        "right": 0.05
      }
    }
    ```
  - YAML:
    ```yaml
    layout:
      border_width: 5
      border_position: "outer"
      info_position: "bottom"
      info_height_ratio: 0.08
      expand_canvas:
        enabled: true
        top: 0.1
        bottom: 0.15
        left: 0.05
        right: 0.05
    ```

### 4. colors (颜色配置)
- **含义**: 定义相框各部分的颜色
- **类型**: 对象/字典
- **子参数**:
  - **border**: 边框颜色 (十六进制颜色代码)
  - **background**: 背景颜色 (十六进制颜色代码)
  - **text**: 文字颜色 (十六进制颜色代码)
  - **accent**: 强调色 (十六进制颜色代码)
  - **custom_text_color**: 自定义文字颜色 (十六进制颜色代码或null)
  - **icon**: 图标颜色 (十六进制颜色代码)
- **编写方式**:
  - JSON:
    ```json
    "colors": {
      "border": "#000000",
      "background": "#FFFFFF",
      "text": "#000000",
      "accent": "#888888",
      "custom_text_color": "#FF6B6B"
    }
    ```
  - YAML:
    ```yaml
    colors:
      border: "#000000"
      background: "#FFFFFF"
      text: "#000000"
      accent: "#888888"
      custom_text_color: "#FF6B6B"
    ```

### 5. fonts (字体配置)
- **含义**: 定义相框中使用的字体属性
- **类型**: 对象/字典
- **子参数**:
  - **family**: 字体家族 (字符串)
  - **weight**: 字体粗细 ('light', 'regular', 'medium')
  - **size_ratio**: 字体大小相对于画布宽度的比例 (0.0-1.0之间的数字)
  - **sizes**: 不同类型文本的独立大小设置
  - **line_spacing**: 行间距倍数 (数字)
- **编写方式**:
  - JSON:
    ```json
    "fonts": {
      "family": "Gotham",
      "weight": "medium",
      "size_ratio": 0.02,
      "sizes": {
        "exif": 0.018,
        "author": 0.015,
        "location": 0.015
      },
      "line_spacing": 1.5
    }
    ```
  - YAML:
    ```yaml
    fonts:
      family: "Gotham"
      weight: "medium"
      size_ratio: 0.02
      sizes:
        exif: 0.018
        author: 0.015
        location: 0.015
      line_spacing: 1.5
    ```

### 6. effects (效果配置)
- **含义**: 定义相框的视觉效果
- **类型**: 数组/列表
- **常用值**:
  - 'rounded_corners': 圆角效果
  - 'shadow': 阴影效果
- **编写方式**:
  - JSON:
    ```json
    "effects": [
      "rounded_corners",
      "shadow"
    ]
    ```
  - YAML:
    ```yaml
    effects:
      - rounded_corners
      - shadow
    ```

### 7. decorations (装饰元素配置)
- **含义**: 控制装饰元素如边框、水印等
- **类型**: 对象/字典
- **子参数**:
  - **border**: 边框配置
    - **enabled**: 是否启用 (布尔值)
    - **width**: 边框宽度 (数字)
    - **color**: 边框颜色 (十六进制颜色代码)
  - **watermark**: 水印配置
    - **enabled**: 是否启用 (布尔值)
    - **text**: 水印文本 (字符串)
    - **position**: 位置 ('top-left', 'top-right', 'bottom-left', 'bottom-right', 'center', **'top-center', 'bottom-center'**)
    - **opacity**: 透明度 (0-100之间的数字)
- **编写方式**:
  - JSON:
    ```json
    "decorations": {
      "border": {
        "enabled": false,
        "width": 2,
        "color": "#000000"
      },
      "watermark": {
        "enabled": false,
        "text": "© MiLeica Frame",
        "position": "bottom-right",
        "opacity": 50
      }
    }
    ```
  - YAML:
    ```yaml
    decorations:
      border:
        enabled: false
        width: 2
        color: "#000000"
      watermark:
        enabled: false
        text: "© MiLeica Frame"
        position: "bottom-right"
        opacity: 50
    ```

### 8. background_fill (背景填充配置)
- **含义**: 控制背景填充方式
- **类型**: 对象/字典
- **子参数**:
  - **type**: 填充类型 (字符串)
  - **gaussian_blur_radius**: 高斯模糊半径 (数字)
  - **gaussian_blur_opacity**: 高斯模糊透明度 (数字)
- **编写方式**:
  - JSON:
    ```json
    "background_fill": {
      "type": "gaussian_white_35",
      "gaussian_blur_radius": 200,
      "gaussian_blur_opacity": 35
    }
    ```
  - YAML:
    ```yaml
    background_fill:
      type: "gaussian_white_35"
      gaussian_blur_radius: 200
      gaussian_blur_opacity: 35
    ```

### 9. logo (Logo配置)
- **含义**: 控制Logo的显示和位置
- **类型**: 对象/字典
- **子参数**:
  - **enabled**: 是否启用 (布尔值)
  - **size_ratio**: Logo大小相对于画布的比例 (数字)
  - **position**: 位置 ('top-left', 'top-right', 'bottom-left', 'bottom-right', **'top-center', 'bottom-center'**, 'center', 'top', 'bottom', 'left', 'right')
  - **margin_top/bottom/left/right**: 各方向的边距 (数字或比例)
  - **relative_to**: 相对于哪个元素定位 (字符串，如 "exif", "timestamp", "camera", "lens", "author", "location")
  - **relative_position**: 相对位置关系 ('after', 'before', 'below', 'above', 'right-of', 'left-of')
  - **relative_margin**: 与目标元素的间距 (浮点数，相对于原图长边的比例)
  - **offset_x_ratio**: X轴偏移量 (浮点数，相对于原图长边的比例)
  - **offset_y_ratio**: Y轴偏移量 (浮点数，相对于原图长边的比例)
- **编写方式**:
  - JSON:
    ```json
    "logo": {
      "enabled": true,
      "size_ratio": 0.05,
      "position": "top-right",
      "margin_top": 0.01,
      "margin_bottom": 0.01,
      "margin_left": 0.01,
      "margin_right": 0.01
    }
    ```
  - YAML:
    ```yaml
    logo:
      enabled: true
      size_ratio: 0.05
      position: "top-right"
      margin_top: 0.01
      margin_bottom: 0.01
      margin_left: 0.01
      margin_right: 0.01
      relative_to: "exif"              # 相对于哪个元素
      relative_position: "right-of"    # 相对位置关系
      relative_margin: 0.01            # 与目标元素的间距（原图长边的1%）
      offset_x_ratio: 0.005            # X轴偏移（原图长边的0.5%）
      offset_y_ratio: 0.005            # Y轴偏移（原图长边的0.5%）
    ```

### 10. info_position (信息位置配置)
- **含义**: 控制各类信息元素的位置，支持绝对定位和相对定位
- **类型**: 对象/字典
- **子参数**:
  - **exif, timestamp, camera, lens, author, location**: 各类信息的定位配置
    - **position**: 位置 ('inside', 'outside', 'top', 'bottom', 'left', 'right', 'tl', 'tr', 'bl', 'br')
    - **alignment**: 对齐方式 ('left', 'center', 'right', 'top-left', 'top-right')
    - **margin**: 传统边距 (数字或比例，用于向后兼容)
    - **margin_top/bottom/left/right**: 各方向独立边距 (数字或比例)
    - **relative_to**: 相对于哪个元素定位 (字符串)
    - **relative_position**: 相对位置关系 ('after', 'before', 'below', 'above', 'right-of', 'left-of')
    - **relative_margin**: 与目标元素的间距 (浮点数，相对于原图长边的比例)
    - **offset_x_ratio**: X轴偏移量 (浮点数，相对于原图长边的比例)
    - **offset_y_ratio**: Y轴偏移量 (浮点数，相对于原图长边的比例)
- **编写方式**:
  - JSON:
    ```json
    "info_position": {
      "exif": {
        "position": "outside",
        "alignment": "center",
        "margin_bottom": 0.015,
        "relative_to": null
      },
      "timestamp": {
        "position": "outside",
        "alignment": "center",
        "margin_bottom": 0.01,
        "relative_to": "exif",           # 相对于exif元素
        "relative_position": "below",    # 位于exif下方
        "relative_margin": 0.01,         # 与exif的间距为原图长边的1%
        "offset_x_ratio": 0.0,           # X轴无偏移
        "offset_y_ratio": 0.01           # Y轴偏移原图长边的1%
      }
    }
    ```
  - YAML:
    ```yaml
    info_position:
      exif:
        position: "outside"
        alignment: "center"
        margin_bottom: 0.015
        relative_to: null
      timestamp:
        position: "outside"
        alignment: "center"
        margin_bottom: 0.01
        relative_to: "exif"              # 相对于exif元素
        relative_position: "below"       # 位于exif下方
        relative_margin: 0.01            # 与exif的间距为原图长边的1%
        offset_x_ratio: 0.0              # X轴无偏移
        offset_y_ratio: 0.01             # Y轴偏移原图长边的1%
    ```

## 开发参考

您可以基于这些示例创建新的样式配置文件。请确保遵循以下原则：
- 保持配置结构的一致性
- 添加必要的注释说明
- 使用合适的颜色和布局参数
- 遵循配置文件管理规范