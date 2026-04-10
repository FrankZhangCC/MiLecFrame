# MiLeica Frame - Python照片相框程序

## 快速开始

### 启动程序

#### 环境搭建
1. 克隆项目
2. 创建虚拟环境并安装依赖：
   ```bash
   python setup_env.py
   ```
3. 激活虚拟环境：
   - Windows: `venv\Scripts\activate`
   - Linux/Mac: `source venv/bin/activate`

#### 使用方法

##### 单张图片处理
```bash
python src/main.py --input input.jpg --output output.jpg --style modern --author "Your Name" --bg-fill gaussian_white_65
```

##### 批量处理
```bash
python src/main.py --batch --input /path/to/input/folder --output /path/to/output/folder --style modern --author "Your Name" --bg-fill gaussian_white_65 --recursive
```

##### GUI模式
```bash
streamlit run src/gui/app.py
```

> **注意**: 当使用Streamlit GUI模式时，若要停止程序，请在终端中按下 `Ctrl+C` 来中断服务。关闭浏览器标签页不会自动停止后台服务。

## 功能特性

- **EXIF信息展示**：自动提取并显示照片的拍摄参数（相机型号、焦距、光圈等）
- **多种相框样式**：支持通过配置文件自定义相框样式
- **响应式布局**：相框元素根据图片尺寸自适应调整
- **背景填充选项**：支持纯色、高斯模糊等多种背景填充方式
- **装饰元素**：支持边框、水印等装饰元素
- **多格式支持**：支持JPEG、PNG、TIFF等常见图片格式，以及HEIF、HEIC、AVIF等HDR格式
- **批量处理**：支持批量处理整个文件夹中的图片
- **GUI界面**：提供直观的Web界面进行操作

## 技术栈

- 核心图像处理：Pillow、OpenCV
- EXIF处理：piexif
- GUI界面：Streamlit

## 最新功能更新

### 文字颜色自定义与背景类型管理
- **自定义文字颜色**：现在可以在样式配置文件中通过 `custom_text_color` 字段指定文字颜色
  - 如果配置了 `custom_text_color`，将优先使用此颜色
  - 如果未配置 `custom_text_color` 或设置为 `null`，则使用自适应颜色逻辑
  - 支持十六进制颜色格式（如 "#FF6B6B"）和 RGB 元组格式
- **针对背景类型的自定义颜色**：支持为亮色和暗色背景分别设置不同的自定义颜色
  - 使用 `custom_[text_type]_light_color` 和 `custom_[text_type]_dark_color` 格式配置特定文本类型的亮/暗色背景颜色
  - 例如 `custom_timestamp_light_color` 和 `custom_timestamp_dark_color` 为时间戳分别设置亮色和暗色背景下的颜色
  - 例如 `custom_location_light_color` 和 `custom_location_dark_color` 为地点分别设置亮色和暗色背景下的颜色
- **背景类型管理**：使用预定义的深色和浅色背景类型列表进行管理
  - 深色背景类型包括：`pure_black`, `gaussian_black_65`, `gaussian_black_35`, `gaussian_black`
  - 浅色背景类型包括：`pure_white`, `gaussian_white_65`, `gaussian_white_35`, `gaussian_white`
  - 未来添加新背景类型时，只需将类型名称添加到对应的列表中，无需修改条件判断逻辑
- **自适应颜色逻辑**：
  - 深色背景（包括纯黑和黑色高斯模糊）→ 白色文字
  - 浅色背景（包括纯白和白色高斯模糊）→ 黑色文字

### 字体渲染增强
- **智能字体选择**：根据文本内容自动检测，西文使用Gotham Medium字体，中文使用Glow Sans SC Medium字体
- **字体大小调整**：文字高度现为原图长度的2%，提供更合适的视觉比例
- **无前缀显示**：作者和地点信息不再添加"作者："和"地点："前缀，直接显示原始内容
- **多种字重选项**：支持 light、medium、regular 三种字重选择，其中Gotham的regular字重映射到Gotham-Book，以符合实际视觉效果需求
- **独立边距配置**：支持为每个文本元素单独配置四个方向的边距（`margin_top`, `margin_bottom`, `margin_left`, `margin_right`），确保更精确的定位控制

### 背景与文字颜色优化
- **自适应文字颜色**：根据背景类型自动选择最佳文字颜色
  - 黑色背景（纯黑/黑色模糊）→ 白色文字
  - 白色背景（纯白/白色模糊）→ 黑色文字
- **高对比度保证**：确保文字在各种背景下都有良好的可读性

### EXIF信息优化
- **35mm等效焦距**：显示焦距时使用35mm等效焦距而非物理焦距，更符合摄影习惯
- **精确定位**：文字位置计算使用原始图像长边作为基准，确保定位准确

### 元素相对位置计算功能
- **相对定位**：元素可以相对于另一个元素进行定位，支持多种相对位置：`after`, `before`, `below`, `above`, `right-of`, `left-of`
- **偏移功能**：支持`offset_x_ratio`和`offset_y_ratio`参数，允许在相对定位的基础上进行偏移
- **配置参数**：
  - `relative_to`: 指定参考的目标元素名称（如 "exif", "logo" 等）
  - `relative_position`: 定义相对方位，支持值包括 "after", "before", "below", "above", "right-of", "left-of"
  - `relative_margin`: 定义与目标元素之间的间距，必须为相对于原图长边的比例值（浮点数），例如 0.01 表示原图长边的 1%
  - `offset_x_ratio`: 横向偏移量，相对于原图长边的比例，正值向右，负值向左
  - `offset_y_ratio`: 竖向偏移量，相对于原图长边的比例，正值向下，负值向上
- **布局逻辑**：
  - 优先使用相对位置配置计算坐标
  - 若未配置或目标元素不存在，则回退到绝对定位或默认布局逻辑
  - 支持链式布局，即后续元素可依次相对于前一个已定位的元素进行排列
  - 偏移量在相对位置计算完成后应用，用于微调元素位置
- **适用范围**：此功能可用于任何元素，包括文字、图标、Logo等

### 样式配置更新
- **配置驱动**：通过YAML配置文件灵活管理字体、颜色和布局参数
- **独立边距设置**：左对齐文字（如author）的左margin设为0，右对齐文字（如location）的右margin设为0，实现更紧密的对齐效果

## 开发历史

### 早期版本
- **初始版本**：实现基础的EXIF信息提取和相框渲染功能
- **多格式支持**：集成pillow-heif等库，支持HEIF、AVIF等HDR格式

### 中期发展
- **GUI界面**：集成Streamlit，提供Web界面操作
- **样式管理**：引入配置文件驱动的样式管理系统
- **批量处理**：增加批量处理功能，提升工作效率

### 近期更新

#### 设备映射管理功能
- **顶部标签页导航**：将主要功能导航放置在页面顶部，使用"图像处理"、"相机映射管理"和"镜头映射管理"三个标签页，与侧边栏设置项进行功能分区
- **相机映射管理**：
  - 实现双排品牌筛选按钮，第一排为Canon（佳能）、Nikon（尼康）、Sony（索尼）、Fujifilm（富士）、Hasselblad（哈苏）；第二排为DJI（大疆）、OM System（奥之心）、RICOH（理光）、Xiaomi（小米）、Vivo、Oppo、Huawei（华为）、其它
  - 支持直接在表格中编辑映射数据，实时保存并应用更改
- **镜头映射管理**：
  - 提供搜索框，支持按原始或映射镜头名称搜索
  - 支持直接在表格中编辑映射数据，实时保存并应用更改
- **数据实时同步**：编辑后的映射数据立即保存到CSV文件并刷新内存中的映射

#### Logo自动匹配优化
- **智能匹配**：当选择"自动匹配"选项时，系统会根据相机品牌自动匹配对应的logo文件
- **无匹配处理**：如果无法匹配到对应的图标，系统将不显示logo，保持界面整洁
- **配置驱动**：仅在样式配置中启用Logo功能时才显示Logo选择器

#### 字体渲染增强
- **智能字体选择**：根据文本内容自动检测，西文使用Gotham Medium字体，中文使用Glow Sans SC Medium字体
- **字体大小调整**：文字高度现为原图长度的2%，提供更合适的视觉比例
- **无前缀显示**：作者和地点信息不再添加"作者："和"地点："前缀，直接显示原始内容
- **多种字重选项**：支持 light、medium、regular 三种字重选择，其中Gotham的regular字重映射到Gotham-Book，以符合实际视觉效果需求
- **独立边距配置**：支持为每个文本元素单独配置四个方向的边距（`margin_top`, `margin_bottom`, `margin_left`, `margin_right`），确保更精确的定位控制

#### 背景与文字颜色优化
- **自适应文字颜色**：根据背景类型自动选择最佳文字颜色
  - 深色背景（包括纯黑和黑色高斯模糊）→ 白色文字
  - 浅色背景（包括纯白和白色高斯模糊）→ 黑色文字
- **高对比度保证**：确保文字在各种背景下都有良好的可读性

#### EXIF信息优化
- **35mm等效焦距**：显示焦距时使用35mm等效焦距而非物理焦距，更符合摄影习惯
- **精确定位**：文字位置计算使用原始图像长边作为基准，确保定位准确

#### 样式配置更新
- **配置驱动**：通过YAML配置文件灵活管理字体、颜色和布局参数
- **独立边距设置**：左对齐文字（如author）的左margin设为0，右对齐文字（如location）的右margin设为0，实现更紧密的对齐效果

## 项目结构

```
MiLeica_Frame/
├── src/                    # 源代码目录
│   ├── core/               # 核心处理逻辑
│   │   ├── __init__.py
│   │   ├── image_processor.py  # 图像处理主逻辑
│   │   ├── renderer.py         # 渲染引擎
│   │   ├── hdr_handler.py      # HDR处理
│   │   ├── decorator.py        # 装饰元素处理
│   │   ├── batch_processor.py  # 批量处理
│   │   └── ...
│   ├── gui/                # GUI界面相关
│   │   ├── __init__.py
│   │   ├── app.py          # Streamlit GUI主文件
│   │   └── ...
│   ├── utils/              # 工具函数
│   │   ├── __init__.py
│   │   ├── exif_helper.py  # EXIF数据处理
│   │   ├── device_mapper.py # 设备映射数据库
│   │   ├── config_manager.py # 配置管理
│   │   └── ...
│   ├── frame_styles/       # 相框样式配置
│   │   ├── configs/        # 样式配置文件
│   │   ├── __init__.py
│   │   ├── style_manager.py # 样式管理器
│   │   └── ...
│   ├── frames/             # 相框基类
│   │   └── base_frame.py   # 相框基类定义
│   └── main.py             # 主程序入口
├── assets/                 # 静态资源
│   ├── icons/              # 图标文件
│   └── fonts/              # 字体文件
├── data/                   # 数据文件
│   ├── camera_map.csv      # 相机品牌型号映射
│   └── lens_map.csv        # 镜头映射
├── tests/                  # 测试文件
├── requirements.txt        # 依赖包列表
├── setup_env.py           # 环境配置脚本
├── streamlit_app.py       # Streamlit应用入口
└── README.md
```

## 样式配置规范

样式配置文件支持JSON、YAML和TOML三种格式，存放在[src/frame_styles/configs/](file:///d:/Coding/MiLeica_Frame/src/frame_styles/configs/)目录下。每个配置文件包含以下部分：

### 基本信息
```yaml
name: "样式名称"
description: "样式描述"
version: "版本号"
```

### 布局配置 (layout)
- `expand_canvas`: 扩展画布配置
  - `enabled`: 是否启用扩展画布
  - `top`, `bottom`, `left`, `right`: 四边扩展比例（相对于原图尺寸的百分比）
- `info_position`: 信息位置配置
  - `exif`, `timestamp`, `camera`, `lens`, `author`, `location`, `camera_icon`: 各项信息的位置
    - `position`: 位置（inside 或 outside）
    - `alignment`: 对齐方式（left, center, right, top-left, top-right 等）
    - `margin`: 传统边距（可选，用于向后兼容）
    - **必需的四周独立边距配置**（根据位置和对齐方式设置）：
      - **顶部文字**（如 camera, lens, camera_icon）：必须定义 `margin_top`
      - **底部文字**（如 exif, timestamp）：必须定义 `margin_bottom`
      - **左对齐文字**（如 author, camera, lens, camera_icon）：必须定义 `margin_left`
      - **右对齐文字**（如 location）：必须定义 `margin_right`
      - **所有文字元素**：应当定义完整的四个方向边距（`margin_top`, `margin_bottom`, `margin_left`, `margin_right`）
      - 所有边距值推荐使用浮点数比例（如0.03表示长边的3%），以保持响应式设计特性

### 颜色配置 (colors)
- `text`: 文字颜色（传统颜色设置，保留向后兼容性）
- `custom_text_color`: 通用自定义文字颜色（新功能，如果设置将优先使用此颜色）
  - 支持十六进制颜色格式（如 "#FF6B6B"）
  - 支持 RGB 元组格式（如 [255, 107, 107]）
  - 如设置为 `null`，则使用自适应颜色逻辑
- `custom_text_light_color`: 亮色背景下通用自定义文字颜色
- `custom_text_dark_color`: 暗色背景下通用自定义文字颜色
- `custom_[text_type]_light_color`: 亮色背景下特定文本类型的自定义颜色（如 `custom_timestamp_light_color`, `custom_location_light_color`）
- `custom_[text_type]_dark_color`: 暗色背景下特定文本类型的自定义颜色（如 `custom_timestamp_dark_color`, `custom_location_dark_color`）
- `background`: 背景颜色
- `icon`: 图标颜色

### 字体配置 (fonts)
- `regular`: 字体名称
- `size_ratio`: 默认字体大小相对于画布宽度的比例
- `sizes`: 各类信息的独立字体大小
  - `exif`: EXIF信息字体大小比例
  - `timestamp`: 拍摄时间信息字体大小比例
  - `camera`: 相机型号信息字体大小比例
  - `lens`: 镜头型号信息字体大小比例
  - `author`: 作者信息字体大小比例
  - `location`: 位置信息字体大小比例
- `line_spacing`: 行间距倍数

### 装饰元素配置 (decorations)
- `border`: 边框配置
- `watermark`: 水印配置

### 背景填充配置 (background_fill)
- `type`: 填充类型（pure_black, pure_white, gaussian_black_65, gaussian_white_65, gaussian_black_35, gaussian_white_35）
- `gaussian_blur_radius`: 高斯模糊半径
- `gaussian_blur_opacity`: 高斯模糊叠加透明度

## 命令行选项

- `--input`, `-i`: 输入图片路径
- `--output`, `-o`: 输出图片路径
- `--style`, `-s`: 相框样式
- `--author`: 作者名
- `--location`: 拍摄地点
- `--bg-fill`: 背景填充类型 (pure_black, pure_white, gaussian_black_65, gaussian_white_65, gaussian_black_35, gaussian_white_35)
- `--batch`: 批量处理模式
- `--recursive`: 递归处理子文件夹（仅批量模式）
- `--gui`: 启动GUI界面

## 开发历史

### 项目初始化阶段
- 创建了项目基本目录结构
- 配置了虚拟环境和依赖包
- 设计了模块化架构，包括核心处理、GUI、工具和样式管理模块

### 核心功能开发
1. **EXIF处理模块** (`src/utils/exif_helper.py`)
   - 实现了EXIF数据提取功能
   - 支持相机品牌、型号、镜头、焦距、光圈、快门、ISO、拍摄时间等信息提取
   - 实现了快门速度和日期时间的格式化显示

2. **图像处理核心** (`src/core/image_processor.py`)
   - 实现了图像格式验证和尺寸检查
   - 支持色彩空间转换
   - 实现了图像尺寸比例缩放
   - 创建了基础的相框添加功能
   - 添加了错误处理和日志记录

3. **相框样式管理** (`src/frame_styles/style_manager.py`)
   - 支持JSON、YAML、TOML等多种配置格式
   - 实现了样式配置的加载和验证
   - 提供了示例样式创建功能

4. **GUI界面** (`src/gui/app.py`)
   - 使用Streamlit构建了网页界面
   - 实现了图片上传和预览功能
   - 集成了相框样式选择和参数配置
   - 提供了处理结果下载功能
   - 添加了错误处理机制，防止程序挂起

5. **设备映射数据库** (`src/utils/device_mapper.py`)
   - 实现了CSV格式的设备映射数据库
   - 支持品牌名称和别名的映射
   - 提供了添加和查询功能
   - **设备映射系统重构**：将原有的 `brand_map.csv`、`model_map.csv` 和 `device_records.csv` 合并为 `camera_map.csv`，简化数据管理结构
     - `camera_map.csv` 结构：[原始品牌, 原始机型, 映射品牌, 映射机型, 时间戳]
     - `lens_map.csv` 保持独立，存储镜头映射信息
     - 新增 [get_mapped_brand_and_model](file:///d:/Coding/MiLeica_Frame/src/utils/device_mapper.py#L128-L145) 方法，同时获取品牌和机型的映射
     - 自动记录新设备信息到映射数据库，便于用户后续编辑映射关系

6. **配置管理** (`src/utils/config_manager.py`)
   - 实现了JSON格式的配置文件管理
   - 支持用户偏好设置的保存和读取
   - 提供了作者名等持久化数据管理

### 相框渲染引擎开发
1. **图像渲染引擎** (`src/core/renderer.py`)
   - 实现了图层合成（背景层、原图层、装饰元素层、文字图标层）
   - 支持多种背景填充选项（纯黑、纯白、高斯模糊叠加黑白）
   - 实现了响应式设计，尺寸和字体大小随输出尺寸自动调整
   - 集成了文字渲染和图标显示功能
   - **新增自定义文字颜色功能**：可在样式配置中通过 `custom_text_color` 指定文字颜色，如果未指定则使用自适应颜色逻辑
   - **增强自定义颜色功能**：支持针对亮色和暗色背景分别设置不同的自定义颜色
   - **背景类型管理优化**：使用预定义的深色和浅色背景类型列表进行管理，便于后续扩展新背景类型
   - **特定文本类型颜色配置**：支持为特定文本类型（如时间戳、地点等）配置针对不同背景的自定义颜色

2. **HDR图像处理** (`src/core/hdr_handler.py`)
   - 支持Gainmap HDR JPEG格式和UltraHDR标准图片
   - 实现了HEIF/HEIC/AVIF格式图像的读取
   - 提供了HDR到SDR的转换功能
   - 集成到图像处理主流程

### 装饰元素系统开发
1. **装饰元素处理** (`src/core/decorator.py`)
   - 实现了边框添加功能
   - 实现了文字水印添加功能
   - 实现了Logo添加功能
   - 实现了角落标记添加功能
   - 提供了统一的装饰元素应用接口

### 批量处理功能开发
1. **批量处理器** (`src/core/batch_processor.py`)
   - 实现了多张图像的批量处理
   - 支持并发处理以提高效率
   - 提供了递归处理子文件夹的功能
   - 包含了错误处理和日志记录

### 响应式设计与扩展画布
1. **扩展画布功能**
   - 支持以原图尺寸百分比为基础的画布扩展
   - 支持上下左右四个方向的独立扩展
   - 扩展区支持多种填充方式（纯色、模糊等）
2. **响应式文本布局**
   - 支持文字信息之间的行间距设置
   - 支持多种文字位置配置
   - 字体大小和间距随画布尺寸自适应调整

### 独立信息字体大小配置
- 每种信息（EXIF、作者、位置）可拥有独立的字体大小
- 通过样式配置文件中的 `fonts.sizes` 部分进行设置

### 背景样式运行时选择
- 背景样式可在命令行或GUI中选择
- 不再需要在样式配置文件中固定设置

### 错误处理改进
- 在GUI应用中添加了导入验证功能
- 在图像处理器中添加了日志记录
- 在主程序中添加了异常处理，确保程序在遇到错误时自动退出

## 核心功能规格

### EXIF信息处理
- **必需字段**：相机品牌、相机型号、镜头型号、等效35mm焦距、光圈、快门速度、感光度、拍摄时间
- **格式规则**：
  - 相框数据格式：[焦距]mm, f/[光圈], [快门]s, ISO[感光度]
  - 快门速度格式化：<1秒显示分数，≥1秒显示小数
  - 拍摄时间格式化为：[yyyy].[mm].[dd] [hh]:[mm]:[ss]
  - 相机品牌信息用于自动选择对应品牌图标
- **错误处理**：EXIF缺失则记录警告但仍继续处理

### 新增信息类型
- **拍摄时间信息**：显示在EXIF信息下方，格式为"yyyy.mm.dd hh:mm:ss"
- **相机型号信息**：显示在原图外侧扩展区域的左上角
- **镜头型号信息**：显示在相机型号信息下方，同样在原图外侧扩展区域的左上角

### 统一数据处理与展示
- **分层架构**：采用三层架构处理EXIF数据
  - **底层解析层**（EXIF Helper）：仅负责读取和解析原始二进制数据，返回纯净的原始字段
  - **业务映射层**（Device Mapper/Service）：负责执行品牌/机型映射、字符串拼接（如`品牌 + " " + 型号`）、格式化等业务逻辑
  - **展示层**（GUI/Renderer）：仅负责接收处理后的最终数据对象进行渲染
- **统一数据出口**：通过`exif_helper.get_display_data()`方法提供统一的展示数据
  - 返回标准化的数据结构，包含`raw_value`（原始数据）和`display_value`（映射后数据）
  - 在"相框预览"和"最终渲染"中使用相同的`display_value`，确保一致性
  - GUI的"设备信息"部分显示`raw_value`，"相框显示"部分显示`display_value`
- **结构化排版**：将数据按逻辑类别拆分，使用Markdown标题、分隔线等组织内容，采用"标签+内容"换行展示，每项独立占行，使用明确中文标签（如"相机型号："、"镜头型号："）

### 图像支持格式
- **支持格式**：JPEG、PNG、TIFF
- **特殊支持**：Gainmap HDR JPEG格式、谷歌UltraHDR标准图片、HEIF/HEIC/AVIF格式
- **色彩空间**：自动识别sRGB、AdobeRGB、ProPhotoRGB，非sRGB时显示警告并自动转换至sRGB
- **尺寸处理**：输入最大尺寸12000×12000像素，输出最大尺寸8192×8192像素，超限时等比缩小

### 相框样式系统
- **多格式支持**：支持JSON、YAML、TOML或Python文件作为样式配置
- **扩展画布**：支持以原图尺寸百分比为基础的画布扩展，上下左右可分别设置
- **响应式设计**：以输出尺寸的百分比作为参考比例，文字大小、边距等随输出尺寸自动调整
- **图层顺序**（从上到下）：文字和图标层 → 装饰元素层 → 原图层 → 背景层（含扩展区域）

### 装饰元素系统
- **边框**：可自定义宽度和颜色
- **水印**：可自定义文字内容、位置和透明度
- **Logo**：可自定义位置、大小比例和透明度
- **角落标记**：可自定义文本、位置和样式

### 批量处理功能
- **并发处理**：支持多线程并发处理以提高效率
- **递归处理**：可选择是否递归处理子文件夹
- **进度跟踪**：实时显示处理进度和统计信息
- **错误恢复**：单个文件处理失败不影响其他文件

### 响应式设计特性
- **扩展画布**：以原图尺寸的百分比为基准进行扩展
- **文字布局**：支持行间距设置，文字位置可灵活配置
- **字体适配**：字体大小随画布尺寸自适应调整
- **背景填充**：扩展区域支持多种填充方式

### 独立信息字体大小
- **EXIF信息**：可独立设置字体大小
- **作者信息**：可独立设置字体大小
- **位置信息**：可独立设置字体大小

### 背景样式运行时选择
- **纯黑色**：100%黑色背景填充，覆盖包括扩展区域在内的整个画面
- **纯白色**：100%白色背景填充，覆盖包括扩展区域在内的整个画面
- **高斯模糊叠加黑色 (65%)**：原图半径200像素高斯模糊，等比放大填充至包括扩展区域在内的整个画面，叠加65%透明度黑色 (`gaussian_black_65`)
- **高斯模糊叠加白色 (65%)**：原图半径200像素高斯模糊，等比放大填充至包括扩展区域在内的整个画面，叠加65%透明度白色 (`gaussian_white_65`)
- **高斯模糊叠加黑色 (35%)**：原图半径200像素高斯模糊，等比放大填充至包括扩展区域在内的整个画面，叠加35%透明度黑色 (`gaussian_black_35`)
- **高斯模糊叠加白色 (35%)**：原图半径200像素高斯模糊，等比放大填充至包括扩展区域在内的整个画面，叠加35%透明度白色 (`gaussian_white_35`)
- **背景类型管理**：系统内部使用预定义的深色和浅色背景类型列表进行管理
  - 深色背景类型：`pure_black`, `gaussian_black_65`, `gaussian_black_35`, `gaussian_black`
  - 浅色背景类型：`pure_white`, `gaussian_white_65`, `gaussian_white_35`, `gaussian_white`
  - 新增背景类型时，只需将类型名称添加到对应的列表中，无需修改条件判断逻辑
- **命令行选择**：通过 `--bg-fill` 参数指定
- **GUI选择**：在界面上提供选项

### 资源管理
- **图标支持**：从指定文件夹读取PNG文件列表，支持根据EXIF相机品牌信息自动选择对应品牌图标
- **高斯模糊**：支持半径参数配置（默认200像素），支持透明度叠加（50%透明度）

### 用户输入
- **作者**：手动输入作者姓名，保存到配置文件
- **地点**：手动输入拍摄地点，格式选项包括"从小到大"或"从大到小"，不保存

### 错误日志系统
- **日志文件**：error_log.txt
- **日志格式**：时间戳（精确到秒）、错误文件全路径、详细错误原因
- **用户通知**：程序结束时提示用户查看日志

## 后续开发计划

1. **GPU加速** - 实现图像处理的GPU加速功能

02. **更多相框样式** - 开发更多样式的相框模板
3. **测试和优化** - 编写单元测试，优化性能

## 开发规范

### 项目开发环境
- 所有开发必须在虚拟环境(venv)中进行
- Windows PowerShell激活命令: `.\venv\Scripts\activate`
- 确保在激活虚拟环境后执行依赖安装或脚本运行

### 代码规范
- 代码采用模块化设计，各模块职责明确
- 使用适当的错误处理机制，避免程序挂起
- 添加充分的日志记录以便调试

### 调试规范
- 在PowerShell环境中调试
- 使用绝对路径执行Python脚本
- 避免使用`&&`作为命令连接符

### 技术规范参考
- 项目技术规范详细内容请参见 [project_master_spec.json](./project_master_spec.json)，后续开发必须严格遵循此规范

## 贡献

欢迎提交Issue和Pull Request。