# MiLeica Frame - Python照片相框程序 ![Version](https://img.shields.io/badge/version-1.4.1-blue)

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

#### 命令行选项

| 参数              | 简写   | 说明                                           |
| ----------------- | ------ | ---------------------------------------------- |
| `--input`       | `-i` | 输入图片路径                                   |
| `--output`      | `-o` | 输出图片路径                                   |
| `--style`       | `-s` | 相框样式名称                                   |
| `--author`      |        | 作者姓名                                       |
| `--location`    |        | 拍摄地点                                       |
| `--bg-fill`     |        | 背景填充类型                                   |
| `--batch`       |        | 启用批量处理模式                               |
| `--recursive`   |        | 递归处理子文件夹（仅批量模式）                 |
| `--font-weight` |        | 字体字重：`light` / `regular` / `medium` |
| `--gui`         |        | 启动 Streamlit GUI 界面                        |

`--bg-fill` 可选值由 `BackgroundFillManager.FILL_TYPES` 注册表管理，当前支持：`pure_black`, `pure_white`, `gaussian_black_65`, `gaussian_white_80`, `gaussian_black_35`, `gaussian_white_50`

## 功能特性

### 图像处理

- **EXIF 信息提取**：自动读取相机品牌/型号、镜头、焦距、光圈、快门、ISO、拍摄时间、GPS 坐标（度分秒格式化）
- **多格式支持**：JPEG、PNG、TIFF、MPO，以及 HEIF/HEIC/AVIF 等 HDR 格式
- **色彩空间自动转换**：sRGB / AdobeRGB / ProPhotoRGB 自动识别并转换至 sRGB

### 相框与布局

- **多种相框样式**：JSON / YAML / TOML 配置文件，支持单文件或文件夹变体组织
- **样式变体系统**：根据 location / author 等字段的数据可用性自动匹配最佳布局变体
- **响应式布局**：画布扩展、文字大小、边距、间距均以原图长边比例为基准自适应
- **绝对与相对定位**：元素可固定位置或相对于其他元素排列（after / below / left-of 等），拓扑排序自动解析依赖
- **背景填充**：纯色（黑/白）或高斯模糊叠加，深色/浅色背景类型自动适配文字颜色。由 `BackgroundFillManager` 集中管理，GUI/CLI 统一从注册表获取可选类型

### 装饰元素

- **边框**：可自定义宽度与颜色
- **水印**：可自定义文字、位置、透明度与颜色
- **Logo**：支持手动选择或根据 EXIF 相机品牌自动匹配（逐词匹配，兼容多词品牌名如 "NIKON CORPORATION"）

### 使用方式

- **CLI 命令行**：单张图片或批量文件夹处理
- **Streamlit GUI**：Web 界面上传、预览、参数配置、结果下载
- **批量处理**：多线程并发、递归子文件夹、实时进度统计、单文件失败不中断其余任务

## 技术栈

- 核心图像处理：Pillow、OpenCV
- EXIF处理：piexif
- GUI界面：Streamlit

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
│   │   ├── app.py                    # Streamlit GUI主文件
│   │   ├── image_processing_page.py  # 图像处理页面
│   │   ├── camera_mapping_page.py    # 相机映射管理页面
│   │   ├── lens_mapping_page.py      # 镜头映射管理页面
│   │   ├── style_creator_page.py     # 样式编辑器页面
│   │   └── ...
│   ├── utils/              # 工具函数
│   │   ├── __init__.py
│   │   ├── exif_helper.py       # EXIF数据处理
│   │   ├── device_mapper.py     # 设备映射数据库
│   │   ├── config_manager.py    # 配置管理
│   │   ├── font_manager.py      # 字体管理器
│   │   ├── layout_engine.py     # 布局引擎
│   │   ├── background_fill.py   # 背景填充管理器（v1.4.0）
│   │   ├── logo_selector.py     # Logo选择器
│   │   ├── gaussian_blur.py     # 高斯模糊与抖动算法
│   │   ├── logging_config.py    # 日志配置
│   │   ├── render_context.py    # 渲染上下文（统一文本数据入口）
│   │   └── ...
│   ├── frame_styles/       # 相框样式配置
│   │   ├── configs/        # 样式配置文件（支持单文件样式和文件夹变体样式）
│   │   │   ├── _STYLE_TEMPLATE.txt   # 规格化填空模板
│   │   │   ├── 照片底部信息水印/  # 文件夹变体样式（示例）
│   │   │   │   ├── default.yaml       # 默认变体（所有字段有数据）
│   │   │   │   └── no_location.yaml   # location 缺失时的变体
│   │   │   └── ...
│   │   ├── __init__.py
│   │   ├── style_manager.py # 样式管理器（含变体匹配引擎）
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

样式配置文件支持JSON、YAML和TOML三种格式，存放在[src/frame_styles/configs/](file:///d:/Coding/MiLeica_Frame/src/frame_styles/configs/)目录下。

> **快速新建样式**：该目录下的 [`_STYLE_TEMPLATE.txt`](file:///d:/Coding/MiLeica_Frame/src/frame_styles/configs/_STYLE_TEMPLATE.txt) 是规格化填空模板，覆盖所有配置项（画布扩展、padding、字体、元素定位、颜色、背景、Logo、变体等），填写后交给 AI 即可生成对应 YAML 配置文件。

### 文件夹变体样式 (v1.3.0)

当需要根据数据可用性动态切换布局时，可将样式组织为**文件夹**（文件夹名 = 样式名），内放多个变体配置文件：

```
configs/
  照片底部信息水印/
    default.yaml              # 默认配置（兜底，所有字段有数据时使用）
    no_location.yaml          # location 缺失时的变体
    no_author.yaml            # author 缺失时的变体
    no_location_no_author.yaml # 多字段同时缺失时的变体（越具体越优先）
  OtherStyle.yaml             # 传统单文件样式（向后兼容）
```

#### 命名规则

| 文件名                           | 匹配条件                                        |
| -------------------------------- | ----------------------------------------------- |
| `default.yaml`                 | 兜底，无可匹配变体时使用                        |
| `no_{field}.yaml`              | 当 `{field}` 的值为 `None` 或空字符串时匹配 |
| `no_{field1}_no_{field2}.yaml` | 当多个字段同时缺失时匹配，优先级高于单字段变体  |

支持的 `{field}` 名称与 `RenderContext.get_text()` 的 key 一致：`location`、`author` 等。

#### 匹配算法

1. 从上下文（`{'location': ..., 'author': ...}`）提取**实际缺失的字段集合**
2. 扫描文件夹内所有变体文件（排除 `default.*`），解析每个文件所需缺失字段
3. 选择**缺失字段集是实际缺失子集**且**匹配字段数最多**（最具体）的变体
4. 无匹配变体时回退到 `default.*`

#### 变体配置精简规范

变体文件中**与缺失字段相关的所有配置项应全部移除**，包括但不限于：

- `colors` 中的 `custom_{field}_{light/dark}_color`
- `fonts.sizes` 中的 `{field}` 条目
- `layout.info_position` 中的 `{field}` 条目

仅保留实际渲染时会生效的配置。这既是代码清洁要求，也是可维护性保障。

#### 调用方式

```python
# 运行时自动选择变体
style_config = style_manager.get_style_config(
    '照片底部信息水印',
    context={'location': location, 'author': author}
)
# location=None → 自动选取 no_location.yaml
# location='北京' → 自动选取 default.yaml

# 不带 context 时（如 GUI 预览）返回 default.yaml，确保向后兼容
style_config = style_manager.get_style_config('照片底部信息水印')
```

### 基本信息

```yaml
name: "样式名称"         # 必需字段，用于标识样式
```

### 布局配置 (layout)

- `expand_canvas`: 扩展画布配置
  - `enabled`: 是否启用扩展画布
  - `top`, `bottom`, `left`, `right`: 四边扩展比例（相对于原图尺寸的百分比）
- `padding`: 叠加元素安全区域配置（v1.2.0 新增，**推荐优先使用 padding 控制全局边距**）
  - `top`, `bottom`, `left`, `right`: 从画布四边向内收缩的比例（相对于原图长边），默认值为 0（= 画布边界）
  - 不影响原始图像位置，仅限制文字、Logo 等叠加元素的绘制范围
  - padding 对所有元素具有最终截断权：无论绝对/相对定位计算出的坐标如何，最终结果均被 clamp 在 padding 边界内，即 **padding 优先级高于 margin**
- `info_position`: 信息位置配置
  - **配置驱动原则**：仅 `info_position` 中声明的元素会被渲染，未声明自动跳过
  - 支持的元素类型：`exif`, `timestamp`, `timestamp_author`, `camera`, `camera_make`, `lens`, `camera_lens`, `author`, `location`, `gps`
  - `camera_lens` 输出合并格式 "品牌 型号 | 镜头"；`camera` + `lens` 则分开两行
  - `timestamp_author` 输出格式 "时间 by 作者"；`timestamp` 则仅显示时间
  - 元素的定位参数见下方 [定位方式](#定位方式)

#### 定位方式

元素的定位方式分为绝对定位和相对定位，二者互斥（`relative_to` 有值时优先采用相对定位）。

##### 绝对定位

以**原始图片边界**为参考坐标系，元素通过锚点绑定到图片边界上，再通过 margin 偏移。

- `placement`: 元素位于原图内部 (`inside`) 或外部 (`outside`)，默认 `outside`
  - `inside`：元素绘制在原图矩形内部，margin 从边界向内偏移
  - `outside`：元素绘制在原图矩形外部，margin 从边界向外偏移
- `position`: 锚点相对于原图边界的位置，支持 14 种：
  `top-left` / `tl`, `top-center` / `tc`, `top-right` / `tr`, `top`, `left`, `center`, `right`, `bottom-left` / `bl`, `bottom-center` / `bc`, `bottom-right` / `br`, `bottom`
  - 注：`center` 锚点以画布中心为基准，不受 `placement` / margin 影响
- `alignment`: 元素自身对齐到锚点的方式
  - 横向：`left` / `top-left` / `bottom-left`（左对齐）、`right` / `top-right` / `bottom-right`（右对齐）、其他值居中
  - 纵向：`top` / `top-left` / `top-right`（顶对齐）、`bottom` / `bottom-left` / `bottom-right`（底对齐）、其他值居中
  - 带 `-left`/`-right`/`-top`/`-bottom` 后缀的组合格式会按对应轴向被正确解析

**margin 边距体系**：

margin 是元素相对于原始图片对应边界的偏移距离，每个方向**独立计算、互不影响**。

- `margin`：统一边距，值为浮点数时按原图长边比例计算（如 `0.02` = 长边的 2%），值为整数时表示绝对像素。未设置时默认 `0`
  - 此为向后兼容选项，设置后覆盖四个方向的初始值
- `margin_top` / `margin_bottom` / `margin_left` / `margin_right`：独立四周边距，每个方向分别覆盖 `margin` 统一值
  - 值类型规则与 `margin` 相同：浮点数 → 比例，整数 → 像素，不设默认 `0`
  - 四个方向**完全独立**，不存在互斥激活条件，可以只定义需要的方向
  - **推荐使用浮点数比例**（如 `0.03` 表示长边的 3%）以保持响应式设计特性
- 计算优先级：`margin_*`（逐方向精调）> `margin`（统一兜底）> 默认 `0`
- 全局约束：padding 对最终坐标有截断权，margin 的计算结果可能被 padding clamp 修正

定位元素在 `info_position` 中的绝对定位声明示例：

```yaml
camera_lens:
  placement: outside
  position: "bottom-left"
  alignment: "left"
  margin_top: 0.01
  margin_bottom: 0.022
  margin_left: 0.02
  margin_right: 0.01
```

##### 相对定位

以**另一已注册元素**为参考坐标系，元素相对于该参考元素排列。

- `relative_to`: 参考元素名称（如 `"exif"`, `"camera_lens"`）。有值时 `position` 和 `margin_*` 系列失效，转而使用相对定位
- `relative_position`: 相对位置：
  `after` / `below`（下方）、`before` / `above`（上方）、`right-of`（右侧）、`left-of`（左侧）
- `relative_margin`: 与参考元素的间距比例（相对于原图长边），默认 `0.01`，**推荐使用浮点数比例**
- `alignment`: 元素在参考元素范围内的对齐方式，默认 `center`
  - `relative_position` 为 `after` / `below` / `before` / `above` 时，控制**水平方向**：`left`（左对齐）、`right`（右对齐）、其他值居中，以参考元素宽度为基准
  - `relative_position` 为 `right-of` / `left-of` 时，控制**垂直方向**：`top`（顶对齐）、`bottom`（底对齐）、其他值居中，以参考元素高度为基准
  - 注：相对定位中的 `alignment` 以参考元素边界计算，与绝对定位的 `margin_*` 无关
- `offset_x_ratio` / `offset_y_ratio`: 微调偏移比例（相对于原图长边，默认 `0`）

定位元素在 `info_position` 中的相对定位声明示例：

```yaml
timestamp_author:
  relative_to: "camera_lens"
  relative_position: "below"
  alignment: "left"
  relative_margin: 0.010
```

##### 定位系统行为规范

- 元素注册顺序由拓扑排序（Kahn 算法）自动解析，基于 `relative_to` 依赖关系决定处理顺序，无需手动调整
- 缺失参考元素保护（v1.4.0）：当 `relative_to` 指向的元素因无文本被跳过时，以其绝对定位参数预注册 0×0 锚点，避免依赖元素降级偏移
- 组合盒溢出保护（v1.2.0）：相对定位元素与参考元素（及其全部从属）合并为组合盒，超出 padding 边界时整体平移，保持对齐关系不变
- 所有定位坐标均以原图长边比例为基准，确保响应式自适应

### 渲染上下文 (RenderContext)

`src/utils/render_context.py` 是渲染文本数据的**统一入口**。它将原本分散在 `renderer.py` 中的数据准备逻辑集中管理，实现样式配置与数据供给的解耦。

#### 核心接口

```python
context = RenderContext(image.size, exif_data, author, location)
text = context.get_text('camera_lens')  # 一行调用获取显示文本
```

- `get_text(key)` 根据 `info_position` 中声明的 key 返回对应的显示文本，无数据时返回 `None`
- 所有条件逻辑（数据校验、相机+镜头合并/替换、时间+作者拼接等）在内部闭环，渲染器无需感知数据来源

#### 支持的 key

| key                  | 输出格式                                         | 数据来源           |
| -------------------- | ------------------------------------------------ | ------------------ |
| `exif`             | `"35mm, f/2.8, 1/125s, ISO200"`                | EXIF 格式化        |
| `timestamp`        | `"2025.01.15 14:30:00"`                        | EXIF 拍摄时间      |
| `timestamp_author` | `"2025.01.15 14:30:00 by Frank"`               | 时间 + 作者合并    |
| `camera_lens`      | `"Leica Q3"` 或 `"Leica Q3 \| Summilux 28mm"` | 见下方"竖向自适应" |
| `camera`           | `"Leica Q3"`                                   | 相机品牌+型号      |
| `camera_make`      | `"Leica"`                                      | 映射后相机品牌     |
| `lens`             | `"Summilux 28mm f/1.7"`                        | 镜头型号           |
| `author`           | `"Frank"`                                      | 用户输入           |
| `location`         | `"Shanghai"`                                   | 用户输入           |
| `gps`              | `"40°26'46.1\"N 79°56'56.1\"W"`              | EXIF GPS（DMS）    |

#### 竖向/方形图片自动适配

当 `camera_lens` 检测到原始图片为**竖向构图**或**方形图片**（纵边 ≥ 横边）时，自动将 `camera_lens` 替换为 `camera`，即仅显示相机型号，不拼接镜头信息。避免竖幅窄图空间不足时文字过长的问题。

此逻辑内聚在 `RenderContext.get_text('camera_lens')` 中：

- 横向图片 → 返回 `"品牌 型号 | 镜头"`（完整合并格式）
- 竖向/方形图片 → 返回 `"品牌 型号"`（仅相机信息）

#### 新增显示字段指南

后续若需新增显示字段（如 GPS 坐标、海拔高度等），遵循以下步骤：

1. **`RenderContext.get_text()`** — 添加 `elif key == 'xxx':` 分支，组装并返回文本
2. **样式 YAML** — 在 `info_position` 中声明字段及其位置/字体配置
3. **`fonts.sizes`** — 按需为新字段添加独立字体大小（可选，回退到 `size_ratio`）

渲染器 (`renderer.py`) 无需任何修改——它只遍历 `info_position` 的 key 并通过 `context.get_text()` 取值。

### 颜色配置 (colors)

颜色由背景类型自动适配，支持按文本类型分别覆盖：

- **通用自定义颜色（作为所有文本类型的兜底）**：
  - `custom_text_light_color`: 亮色背景下的文字颜色
  - `custom_text_dark_color`: 暗色背景下的文字颜色
  - 支持十六进制格式（如 `"#FF6B6B"`）或 RGB 数组（如 `[255, 107, 107]`）
- **按文本类型独立覆盖**：`custom_{text_type}_light_color` / `custom_{text_type}_dark_color`
  - `text_type` 可选值：`exif`、`timestamp`、`timestamp_author`、`camera`、`camera_make`、`lens`、`camera_lens`、`author`、`location`、`gps`
  - 示例：`custom_exif_light_color: [51, 51, 51]`、`custom_timestamp_dark_color: "#CCCCCC"`
- **最终兜底**：若以上均未设置，深色背景使用白色 `(255,255,255)`，浅色背景使用黑色 `(0,0,0)`

### 字体配置 (fonts)

- `family`: 字体族名（默认 `"Gotham"`，对应 `assets/fonts/` 下的 Gotham 系列）
- `weight`: 字重，可选 `"light"`、`"regular"`、`"medium"`（默认 `"medium"`）
  - 可通过命令行 `--font-weight` 参数运行时覆盖
- `size_ratio`: 默认字体大小比例（相对于原图长边像素数）
- `sizes`: 各类信息的独立字体大小比例（相对于原图长边）
  - `exif`、`timestamp`、`timestamp_author`、`camera`、`camera_make`、`lens`、`camera_lens`、`author`、`location`、`gps`
  - 未设置的字段默认使用 `size_ratio`

### 装饰元素配置 (decorations)

边框和水印完全由 GUI/CLI 外部参数控制，不通过样式 YAML 定义。Logo 采用**混合模式**：布局、尺寸、定位由 YAML 中 `logo:` 节定义，具体文件选择由 GUI（自动匹配 / 手动选择 / 无）或 CLI 传入。

- `border`: 边框（可自定义宽度和颜色），完全外部参数
- `watermark`: 水印（可自定义文字、位置、透明度、颜色），完全外部参数
- `logo`: 品牌 Logo，YAML 控制表现形式，文件选择由外部传入（见下方 [Logo 配置](#logo-配置)）

在 GUI 模式下，装饰元素由界面控件动态组装并传入渲染器。

#### Logo 配置

样式 YAML 中 `logo:` 节定义 Logo 的表现形式：

```yaml
logo:
  enabled: true                 # 是否启用
  size_ratio: 0.05              # 短边占原图长边比例
  placement: outside            # inside / outside
  position: "bottom-right"      # 14 种锚点位置
  alignment: "center"           # 对齐方式
  margin_top: 0                 # 四周边距（float=比例，int=像素）
  margin_bottom: 0
  margin_left: 0
  margin_right: 0
  # 相对定位（与绝对定位互斥）
  relative_to: "camera_lens"    # 参考元素名
  relative_position: "below"    # after / before / below / above / right-of / left-of
  relative_margin: 0.01         # 与参考元素的间距比例
  offset_x_ratio: 0             # 微调偏移比例
  offset_y_ratio: 0
```

- Logo 短边 = `size_ratio × 原图长边`，长边自动限制 ≤ `2.5 × size_ratio × 原图长边`（防止细长 Logo 失控），默认 `size_ratio = 0.05`
- 支持绝对定位和相对定位，可引用文字元素（如 `relative_to: "camera_lens"`）
- Logo 在文字层之后渲染，渲染后以 `"logo"` 注册，供后续元素通过 `relative_to: logo` 引用
- Logo 文件来源：GUI 三选一（自动匹配 / 手动选择 / 无）；自动匹配时通过 `context.get_text('camera_make')` 获取相机品牌后由 `LogoSelector.auto_match_logo()` 逐词子串匹配 `assets/logos/` 下 PNG 文件

## 核心功能规格

### EXIF 信息处理与渲染上下文

#### EXIF 提取与格式化

**必需字段**：相机品牌（Make）、相机型号（Model）、镜头型号（LensModel）、35mm 等效焦距、光圈（FNumber）、快门速度（ExposureTime）、感光度（ISO）、拍摄时间（DateTimeOriginal）。

**格式规则**：

| 字段     | 输出格式                                                                                           | 说明                                   |
| -------- | -------------------------------------------------------------------------------------------------- | -------------------------------------- |
| 曝光参数 | `35mm, f/2.8, 1/125s, ISO200`                                                                    | 逗号分隔，单行字符串                   |
| 快门速度 | `<1s` 显示分数（`1/125`），`≥1s` 显示小数（`2.5`）                                        | `_format_shutter_speed()`            |
| 拍摄时间 | `yyyy.mm.dd hh:mm:ss`                                                                            | 原始 EXIF 格式 `yyyy:mm:dd HH:MM:SS` |
| 相机品牌 | 经 `_safe_decode()` 多编码（utf-8 / latin-1 / shift-jis 等）兼容处理后，小写化用于 Logo 逐词匹配 | `get_camera_brand()`                 |

**三层数据处理架构**：

```
EXIF Helper（解析原始二进制 → 纯净字段，_safe_decode 多编码容错）
  → Device Mapper（品牌/机型/镜头映射、字符串拼接 "品牌 型号"、格式化）
    → Renderer / GUI（展示层，仅消费最终数据，不感知数据来源）
```

统一数据出口 `exif_helper.get_display_data()`，同时提供 `raw_*`（原始值，GUI 设备信息区展示）和映射后字段（相机/镜头组合、格式化曝光参数），确保 GUI 预览与最终渲染数据一致。

#### 渲染上下文（RenderContext）

`src/utils/render_context.py` 是渲染文本数据的**统一入口**，将数据准备逻辑从渲染器中完全解耦：

```python
context = RenderContext(image.size, exif_data, author, location)
text = context.get_text('camera_lens')  # 一行调用获取最终显示文本
```

`get_text(key)` 根据样式 YAML 中 `info_position` 声明的 key 返回对应文本，内部闭环所有条件逻辑（数据校验、相机+镜头合并/替换、时间+作者拼接、竖向自适应等），无数据时返回 `None` 自动跳过渲染。

**支持的 key**：

| key                  | 输出格式                                         | 说明                                         |
| -------------------- | ------------------------------------------------ | -------------------------------------------- |
| `exif`             | `"35mm, f/2.8, 1/125s, ISO200"`                | EXIF 格式化曝光参数                          |
| `timestamp`        | `"2025.01.15 14:30:00"`                        | EXIF 拍摄时间                                |
| `timestamp_author` | `"2025.01.15 14:30:00 by Frank"`               | 时间 + 作者合并（作者为空时仅显示时间）      |
| `camera_lens`      | `"Leica Q3 \| Summilux 28mm"` 或 `"Leica Q3"` | 相机+镜头合并，竖向/方形图片自动替换为仅相机 |
| `camera`           | `"Leica Q3"`                                   | 相机品牌+型号                                |
| `camera_make`      | `"Leica"`                                      | 映射后相机品牌（v1.4.1）                     |
| `lens`             | `"Summilux 28mm f/1.7"`                        | 镜头型号                                     |
| `author`           | `"Frank"`                                      | 用户输入                                     |
| `location`         | `"Shanghai"`                                   | 用户输入                                     |
| `gps`              | `"40°26'46.1\"N 79°56'56.1\"W"`              | EXIF GPS 度分秒格式化坐标（v1.4.1）          |

**相机信息的三级字段**（`get_display_data()` 内部构造，按粒度递增）：

| 内部字段                 | 对外 key        | 输出示例                       | 说明               |
| ------------------------ | --------------- | ------------------------------ | ------------------ |
| `camera_make`          | `camera_make` | `"Leica"`                    | 映射后品牌名       |
| `camera_combined`      | `camera`      | `"Leica Q3"`                 | 品牌 + 型号        |
| `camera_lens_combined` | `camera_lens` | `"Leica Q3 \| Summilux 28mm"` | 品牌 + 型号 + 镜头 |

**竖向/方形图片自动适配**：当原始图片纵边 ≥ 横边时，`camera_lens` 自动替换为 `camera`（仅显示相机型号），避免竖幅窄图空间不足。

**新增显示字段**：只需在 `RenderContext.get_text()` 添加 `elif key == 'xxx':` 分支 + 在 YAML 的 `info_position` 中声明配置，渲染器零改动。

**中英日混排**：字符串自动按 CJK / 拉丁片段拆分，各片段使用对应字体（GlowSansSC / Gotham）渲染，以拉丁字体基线对齐确保视觉统一。

#### 错误处理

EXIF 缺失时记录警告，不中断处理流程；`_safe_decode()` 对不可解码字节使用多编码回退 + 控制字符过滤，保证程序鲁棒性。

---

### 图像支持与处理管线

#### 支持的格式

| 类别     | 格式                                         | 处理方式                            |
| -------- | -------------------------------------------- | ----------------------------------- |
| 常规     | JPEG、PNG、TIFF、MPO                         | PIL 直接打开                        |
| HDR      | HEIF、HEIC、AVIF、Gainmap HDR JPEG、UltraHDR | `HDRHandler` 预处理后转为 SDR     |
| 色彩空间 | sRGB、AdobeRGB、ProPhotoRGB                  | 自动识别，非 sRGB 警告并转换至 sRGB |

#### 尺寸限制

| 阶段 | 上限            | 超限行为         |
| ---- | --------------- | ---------------- |
| 输入 | 12000×12000 px | 等比缩小至限制内 |
| 输出 | 8192×8192 px   | 等比缩小至限制内 |

#### 处理管线

```
1. 验证输入文件存在 + 格式支持
2. HDR 检测 → HDRHandler 预处理（Gainmap/UltraHDR/HEIF/AVIF）
3. EXIF 提取（piexif + 多编码解码）→ 设备映射 → 记录到 camera_map.csv / lens_map.csv
4. 尺寸验证 → 超限等比缩小
5. 色彩空间检测 → 非 sRGB 转换
6. 加载样式配置（StyleManager，含变体上下文匹配）
7. 渲染相框（FrameRenderer — 详见下方相框渲染系统）
8. 保存输出（JPEG/PNG，quality=95，optimize=True，自动嵌入原始 EXIF）
```

---

### 相框与装饰渲染系统

#### 布局引擎（LayoutEngine）

`src/utils/layout_engine.py` 负责画布计算与元素定位：

- **画布扩展**：以原图长边比例扩展四边（`expand_canvas`），上下左右独立设置
- **安全区域**：`padding` 约束所有叠加元素的绘制边界，优先级高于 margin，原图位置不受影响
- **绝对定位**（v1.4.0 重构）：`placement`（`inside`/`outside`，元素在图片内/外）+ `position`（14 种锚点位置）+ `alignment`（元素自对齐）+ 独立四周 margin（比例或像素）。三参数正交，替代旧版 `position` 字段同时承载 inside/outside/锚点的混乱设计
- **相对定位**（v1.2.0）：`relative_to` + `relative_position`（`below` / `above` / `right-of` / `left-of`），`relative_margin` 间距 + `offset` 微调
- **拓扑排序**：基于 `relative_to` 依赖关系自动解析处理顺序（Kahn 算法），无需手动调整元素声明顺序
- **三阶段渲染管线**（v1.2.0）：Phase 1 测量所有元素尺寸 → Phase 2 拓扑序计算位置并注册 → Phase 3 从注册表读取最终坐标统一绘制，确保依赖有序、溢出可修正
- **缺失参考元素保护**（v1.4.0）：当 `relative_to` 指向的元素因无文本被跳过时，自动以 0x0 尺寸预注册其绝对位置锚点，避免依赖元素降级为绝对定位导致位置偏移
- **组合盒溢出保护**（v1.2.0）：相对定位元素与参考元素（及其全部从属）合并为组合盒，超出 padding 边界时整体平移，保持对齐关系不变

#### 渲染器（FrameRenderer）

`src/core/renderer.py` 负责图层合成与元素绘制：

- **背景填充**：
  - 由 `BackgroundFillManager` 统一管理（`src/utils/background_fill.py`），所有填充类型在 `FILL_TYPES` 注册表中集中定义
  - 纯色：`pure_black` / `pure_white`，覆盖含扩展区域的全画布
  - 高斯模糊叠加：3-pass Box Blur 近似（O(n)），全分辨率等效半径 200px，大图自动降采样至 1200px 计算；float32 混合 + PIL 内置 Floyd-Steinberg 量化消除色彩断层
  - 每种填充类型同时声明 `text_scheme`（`dark`/`light`），渲染器通过 `BackgroundFillManager.is_dark_bg()` 自动适配文字颜色
  - 支持运行时覆盖 `color`、`opacity`、`blur_radius` 参数，预留自定义背景注册接口 `register()`
- **文字颜色**：根据背景类型自动选择深/浅色方案，支持按文本类型独立覆盖（`custom_{type}_{dark/light}_color`），兜底白色/黑色
- **字体系统**：Gotham（拉丁）+ GlowSansSC（CJK/日文）双字体引擎，支持 light / regular / medium 三种字重；每种信息类型可独立设置字体大小比例；字体按 `(系列, 字重, 字号, 是否 CJK)` 键值缓存
- **文字渲染顺序**：配置驱动——仅 `info_position` 中声明的元素被渲染，由拓扑排序保证依赖正确
- **Logo 渲染**：支持 PNG（RGBA 透明背景），尺寸以短边为基准（`logo.size_ratio * 原图长边`），长边自动限制 ≤ `2.5 * size_ratio * 原图长边`。通过 `relative_to` 绝对/相对定位，在文字层之后渲染以确保可引用文字元素坐标
- **Logo 自动匹配**（`LogoSelector.auto_match_logo()`）：将相机品牌按空格拆词，逐词与 `assets/logos/` 下 PNG 文件名进行子串匹配，过滤 ≤2 字符的无意义词（AG、KG 等），支持 "NIKON CORPORATION" 等复合品牌名

#### 背景填充管理器 (BackgroundFillManager) (v1.4.0)

`src/utils/background_fill.py` 是背景填充功能的**唯一入口**，集中管理所有填充类型的注册、查询和渲染。

##### 核心职责

- **类型注册**：所有可用背景类型在 `FILL_TYPES` 类属性中统一定义，包括纯色和高斯模糊两种方法
- **GUI/CLI 统一**：`get_choices()` 返回 `{label: key}` 供 GUI 下拉框使用，`get_keys()` 返回 key 列表供 CLI argparse 使用
- **深色/浅色判断**：`is_dark_bg(key)` 根据注册的 `text_scheme` 判断，供渲染器自动适配文字颜色
- **背景渲染**：`render(image, w, h, fill_type)` 根据注册表配置创建背景图像
- **预留扩展**：`register()` 方法支持运行时动态添加新填充类型

##### 注册表结构

```python
FILL_TYPES = {
    'pure_black': {
        'label': '纯黑背景', 'method': 'solid',
        'color': (0, 0, 0), 'text_scheme': 'dark'
    },
    'gaussian_black_65': {
        'label': '模糊背景 (深色 65%)', 'method': 'gaussian',
        'overlay_color': 'black', 'opacity': 65, 'blur_radius': 200,
        'text_scheme': 'dark'
    },
    # ...
}
```

##### 扩展方式

```python
# 新增背景类型只需注册，GUI 下拉和 CLI 自动同步
BackgroundFillManager.register(
    'pure_gray', label='纯灰背景', method='solid',
    text_scheme='dark', color=(128, 128, 128)
)
```

#### 装饰器（Decorator）

`src/core/decorator.py` 独立于样式 YAML，由 GUI 或 CLI 动态传入：

- **边框**：自定义宽度（px）与颜色（RGB 元组），作用于原图外缘
- **水印**：自定义文字内容、位置（9 种锚点）、不透明度（0-100%）、颜色

#### 样式变体系统（v1.3.0）

- 样式可组织为文件夹（文件夹名 = 样式名），内含多个变体 YAML 文件
- 命名规则 `no_{field}.yaml`（如 `no_location.yaml`），由 `StyleManager._resolve_style_variant()` 根据运行时上下文自动选取最佳匹配
- GUI 中统一展示为单个样式选项，对用户透明

---

### GUI 界面

基于 Streamlit 的 Web 界面（`src/gui/app.py`），提供以下功能区域：

- **图片上传与预览**：支持拖拽上传，实时显示原图及 EXIF 信息（设备信息 + 拍摄参数 + 相框显示预览）；上传阶段 EXIF 直接从内存读取，无需落盘临时文件
- **缩略图预览**：处理完成后自动生成 1200px 长边缩略图用于页面预览，大幅降低传输带宽；下载按钮提供全分辨率原始输出
- **样式选择**：下拉菜单列出所有可用样式（含文件夹变体样式），配置变更时按钮自动切换为"重新生成"
- **文字与装饰**：作者姓名（自动保存）、拍摄地点（支持 GPS 坐标替换）、字体字重选择；边框（宽度/颜色）、水印（内容/位置/透明度/颜色）独立控制
- **Logo 设置**：自动匹配（根据相机品牌）/ 手动选择 / 无，三选一；自动匹配无结果时不显示
- **背景样式**：6 种预定义背景类型（纯黑/纯白 + 4 种高斯模糊组合）
- **输出格式**：JPEG / PNG 可选
- **结果下载**：处理后图片预览 + 一键下载
- **设备映射管理**：独立的相机/镜头映射表界面，支持品牌筛选、表格内编辑实时保存
- **样式编辑器**：可视化表单页面，支持新建与编辑已有样式配置文件，填参后可一键生成 YAML

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
- 避免使用 `&&`作为命令连接符

### 技术规范参考

- 项目技术规范详细内容请参见 [project_master_spec.json](./project_master_spec.json)，后续开发必须严格遵循此规范

## 贡献

欢迎提交Issue和Pull Request。

> 完整更新历史请参见 [CHANGELOG.md](./CHANGELOG.md)
