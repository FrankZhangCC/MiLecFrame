# MiLeica Frame - Python照片相框程序 ![Version](https://img.shields.io/badge/version-1.2.0-blue)

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
python src/main.py --input input.jpg --output output.jpg --style modern --author "Your Name" --bg-fill gaussian_white_80
```

##### 批量处理
```bash
python src/main.py --batch --input /path/to/input/folder --output /path/to/output/folder --style modern --author "Your Name" --bg-fill gaussian_white_80 --recursive
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

## 最近更新 (v1.2.0)

- **相对定位溢出保护**：相对定位元素与参考元素合并为组合盒，超出安全区域时整体平移，不影响对齐关系
- **依赖簇级联平移**：多个元素 `relative_to` 同一参考时，组合盒自动扩展至全部已注册从属，移位时递归级联确保整体不脱钩
- **三阶段渲染管线**：Phase 1 测量 → Phase 2 拓扑序计算+注册 → Phase 3 绘制，彻底解决依赖顺序问题
- **拓扑依赖解析**：通过 Kahn 算法自动解析 `relative_to` 依赖关系，无需手动调整元素注册顺序
- **Padding 安全区域**：新增 `padding` 配置，控制叠加元素的绘制边界，优先级高于 margin
- **绝对定位边界约束**：绝对定位元素同样受 padding 边界截断保护
- **样式配置精简**：清理 `effects`、`fonts.regular`、`line_spacing`、`border_*` 等无效参数；字体配置拆分为 `family` + `weight`；颜色改为按文本类型独立覆盖
- **配置驱动渲染**：仅渲染 `info_position` 中声明的元素，未声明自动跳过；不再通过 `style_manager` 注入默认条目
- **相机+镜头合并**：`camera_lens` 合并输出格式 "品牌 型号 | 镜头"，同时保留 `camera`/`lens` 分开排版
- **时间作者合并**：`timestamp_author` 合并输出 "时间 by 作者"
- **Logo 相对定位**：Logo 渲染移至文字层后，使其 `relative_to` 可引用已注册的文字元素坐标

> 完整更新历史请参见 [CHANGELOG.md](./CHANGELOG.md)

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
│   │   ├── exif_helper.py       # EXIF数据处理
│   │   ├── device_mapper.py     # 设备映射数据库
│   │   ├── config_manager.py    # 配置管理
│   │   ├── font_manager.py      # 字体管理器
│   │   ├── layout_engine.py     # 布局引擎
│   │   ├── logo_selector.py     # Logo选择器
│   │   ├── gaussian_blur.py     # 高斯模糊与抖动算法
│   │   ├── logging_config.py    # 日志配置
│   │   └── ...
│   ├── frame_styles/       # 相框样式配置
│   │   ├── configs/        # 样式配置文件
│   │   ├── __init__.py
│   │   ├── style_manager.py # 样式管理器
│   │   └── ...
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
name: "样式名称"         # 必需字段，用于标识样式
```

### 布局配置 (layout)
- `expand_canvas`: 扩展画布配置
  - `enabled`: 是否启用扩展画布
  - `top`, `bottom`, `left`, `right`: 四边扩展比例（相对于原图尺寸的百分比）
- `padding`: 叠加元素安全区域配置（v1.2.0 新增，优先级高于 margin）
  - `top`, `bottom`, `left`, `right`: 从画布四边向内收缩的比例（相对于原图长边），默认值为 0（= 画布边界）
  - 不影响原始图像位置，仅限制文字、Logo 等叠加元素的绘制范围
  - 绝对定位与相对定位元素均受 padding 约束
- `info_position`: 信息位置配置
  - **配置驱动原则**：仅 `info_position` 中声明的元素会被渲染，未声明自动跳过
  - 支持的元素类型：`exif`, `timestamp`, `timestamp_author`, `camera`, `lens`, `camera_lens`, `author`, `location`, `camera_icon`
  - `camera_lens` 输出合并格式 "品牌 型号 | 镜头"；`camera` + `lens` 则分开两行
  - `timestamp_author` 输出格式 "时间 by 作者"；`timestamp` 则仅显示时间
    - **绝对定位**：
      - `position`: 位置（inside, outside, top-left, top-right, bottom-left, bottom-right, top-center, bottom-center, top, bottom, left, right, center）
      - `alignment`: 对齐方式（left, center, right, top-left, top-right, top, bottom）
      - `margin`: 传统边距（可选，用于向后兼容）
      - **必需的四周独立边距配置**（根据位置和对齐方式设置）：
        - **顶部文字**（如 camera, lens, camera_icon）：必须定义 `margin_top`
        - **底部文字**（如 exif, timestamp）：必须定义 `margin_bottom`
        - **左对齐文字**（如 author, camera, lens, camera_icon）：必须定义 `margin_left`
        - **右对齐文字**（如 location）：必须定义 `margin_right`
        - **所有文字元素**：应当定义完整的四个方向边距（`margin_top`, `margin_bottom`, `margin_left`, `margin_right`）
        - 所有边距值推荐使用浮点数比例（如0.03表示长边的3%），以保持响应式设计特性
    - **相对定位**（v1.2.0 新增）：
      - `relative_to`: 参考元素名称（如 `"exif"`, `"author"`），设置后 `position` 和独立 margin 失效
      - `relative_position`: 相对位置，可选 `after`/`below`（下方）、`before`/`above`（上方）、`right-of`（右侧）、`left-of`（左侧）
      - `relative_margin`: 与参考元素的间距比例（相对于原图长边），默认 0.01
      - `alignment`: 在相对方向垂直轴上的对齐（如 `relative_position: below` + `alignment: left` 表示置于参考元素下方且左对齐）
      - `offset_x_ratio` / `offset_y_ratio`: 微调偏移比例（默认 0）
      - 相对定位元素与参考元素合并为组合盒，超出 padding 安全区域时整体平移
      - 元素注册顺序由拓扑排序自动解析，无需手动调整

### 颜色配置 (colors)

颜色由背景类型自动适配，支持按文本类型分别覆盖：

- **通用自定义颜色（作为所有文本类型的兜底）**：
  - `custom_text_light_color`: 亮色背景下的文字颜色
  - `custom_text_dark_color`: 暗色背景下的文字颜色
  - 支持十六进制格式（如 `"#FF6B6B"`）或 RGB 数组（如 `[255, 107, 107]`）
- **按文本类型独立覆盖**：`custom_{text_type}_light_color` / `custom_{text_type}_dark_color`
  - `text_type` 可选值：`exif`、`timestamp`、`timestamp_author`、`camera`、`lens`、`camera_lens`、`author`、`location`
  - 示例：`custom_exif_light_color: [51, 51, 51]`、`custom_timestamp_dark_color: "#CCCCCC"`
- **最终兜底**：若以上均未设置，深色背景使用白色 `(255,255,255)`，浅色背景使用黑色 `(0,0,0)`

### 字体配置 (fonts)

- `family`: 字体族名（默认 `"Gotham"`，对应 `assets/fonts/` 下的 Gotham 系列）
- `weight`: 字重，可选 `"light"`、`"regular"`、`"medium"`（默认 `"medium"`）
  - 可通过命令行 `--font-weight` 参数运行时覆盖
- `size_ratio`: 默认字体大小比例（相对于原图长边像素数）
- `sizes`: 各类信息的独立字体大小比例（相对于原图长边）
  - `exif`、`timestamp`、`timestamp_author`、`camera`、`lens`、`camera_lens`、`author`、`location`
  - 未设置的字段默认使用 `size_ratio`

### 装饰元素配置 (decorations)

装饰元素（边框、水印、Logo、角落标记）**不通过样式配置 YAML 定义**，而是作为独立参数传入 `render_frame()`。支持的类型：
- `border`: 边框（可自定义宽度和颜色）
- `watermark`: 水印
- `logo`: 品牌 Logo（支持根据 EXIF 相机品牌自动匹配）
- `corner_mark`: 角落标记

在 GUI 模式下，装饰元素由界面控件动态组装并传入渲染器。

### 背景填充配置 (background_fill)
- `type`: 填充类型（pure_black, pure_white, gaussian_black_65, gaussian_white_80, gaussian_black_35, gaussian_white_50, 以及格式为 `gaussian_{color}_{opacity}` 的自定义组合）
- `gaussian_blur_radius`: 高斯模糊半径（默认 200，原图全分辨率下的等效值；实际计算时按缩放比例递减）
- `gaussian_blur_opacity`: 叠加透明度百分比（0-100，作为 `type` 中已编码透明度的回退默认值）

## 命令行选项

- `--input`, `-i`: 输入图片路径
- `--output`, `-o`: 输出图片路径
- `--style`, `-s`: 相框样式
- `--author`: 作者名
- `--location`: 拍摄地点
- `--bg-fill`: 背景填充类型 (pure_black, pure_white, gaussian_black_65, gaussian_white_80, gaussian_black_35, gaussian_white_50)
- `--batch`: 批量处理模式
- `--recursive`: 递归处理子文件夹（仅批量模式）
- `--font-weight`: 字体字重 (light, regular, medium，默认 medium)
- `--gui`: 启动GUI界面

> 完整开发历史请参见 [CHANGELOG.md](./CHANGELOG.md)

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
- **多格式支持**：支持JSON、YAML、TOML文件作为样式配置
- **扩展画布**：支持以原图尺寸百分比为基础的画布扩展，上下左右可分别设置
- **响应式设计**：以输出尺寸的百分比作为参考比例，文字大小、边距等随输出尺寸自动调整
- **图层顺序**（从上到下）：文字和图标层 → 装饰元素层 → 原图层 → 背景层（含扩展区域）
- **相对定位**（v1.2.0）：支持将元素相对于其他已注册元素定位（after/below/before/above/right-of/left-of），由拓扑排序自动解析依赖顺序
- **Padding 安全区域**（v1.2.0）：叠加元素的绘制边界约束，优先级高于 margin
- **组合盒溢出保护**（v1.2.0）：相对定位元素与参考元素（及其全部已注册从属）合并为组合盒，整体平移确保不超出安全区域

### 装饰元素系统
- **边框**：可自定义宽度和颜色
- **水印**：可自定义文字内容、位置和透明度
- **Logo**：可自定义位置、大小比例和透明度
- **角落标记**：可自定义文本、位置和样式
- **图标支持**：从指定文件夹读取 PNG 文件列表，支持根据 EXIF 相机品牌信息自动选择对应品牌图标

### 批量处理功能
- **并发处理**：支持多线程并发处理以提高效率
- **递归处理**：可选择是否递归处理子文件夹
- **进度跟踪**：实时显示处理进度和统计信息
- **错误恢复**：单个文件处理失败不影响其他文件

### 响应式设计特性
- **扩展画布**：以原图尺寸的百分比为基准进行扩展
- **文字布局**：文字位置可灵活配置
- **字体适配**：字体大小随画布尺寸自适应调整
- **背景填充**：扩展区域支持多种填充方式
- **三阶段渲染管线**（v1.2.0）：Phase 1 测量所有元素尺寸 → Phase 2 拓扑序计算位置并注册 → Phase 3 统一绘制，确保依赖有序、溢出可修正

### 独立信息字体大小
- **EXIF信息**：可独立设置字体大小
- **相机/镜头**：可独立或合并（`camera_lens`）设置
- **时间作者**：可独立或合并（`timestamp_author`）设置
- **位置信息**：可独立设置字体大小

### 背景样式系统
- **纯黑色**：100%黑色背景填充，覆盖包括扩展区域在内的整个画面
- **纯白色**：100%白色背景填充，覆盖包括扩展区域在内的整个画面
- **高斯模糊叠加**：原图使用3-pass Box Blur 近似高斯模糊（默认全分辨率等效半径200px），等比放大填充至包括扩展区域在内的整个画面；叠加透明度支持 50% / 80% / 自定义，如在 `gaussian_{color}_{opacity}` 中编码
- **背景类型管理**：系统内部使用预定义的深色和浅色背景类型列表进行管理
  - 深色背景类型：`pure_black`, `gaussian_black_65`, `gaussian_black_35`, `gaussian_black`
  - 浅色背景类型：`pure_white`, `gaussian_white_80`, `gaussian_white_50`, `gaussian_white`
  - 新增背景类型时，只需将类型名称添加到对应的列表中，无需修改条件判断逻辑
- **性能优化**：大图自动降采样至1200px中间分辨率计算模糊；模糊叠加混合在 float32 空间完成，通过 PIL 内置 Floyd-Steinberg 量化消除色彩断层
- **配置参数**：通过 `gaussian_blur_radius` 和 `gaussian_blur_opacity` 在样式配置中自定义模糊强度和叠加透明度
- **命令行选择**：通过 `--bg-fill` 参数指定
- **GUI选择**：在界面上提供选项

### 用户输入
- **作者**：手动输入作者姓名，保存到配置文件
- **地点**：手动输入拍摄地点，格式选项包括"从小到大"或"从大到小"，不保存

### 错误日志系统
- **调试日志**：`debug_log.txt` — 包含所有 DEBUG 级别日志（渲染流程、定位计算等详细信息）
- **日志格式**：`时间 - 模块名 - 级别 - 消息`
- **控制台输出**：INFO 及以上级别的日志同步输出到 stderr
- **配置入口**：`src/utils/logging_config.py` 中的 `setup_logging()` 函数统一管理，CLI 和 GUI 入口均已集成

## 后续开发计划

1. **GPU加速** - 实现图像处理的GPU加速功能
2. **更多相框样式** - 开发更多样式的相框模板
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