# 更新历史

## v1.2.0 (2026-04-29)

> 本版本引入相对定位系统、Padding 安全区域和三阶段渲染管线，大幅提升布局灵活性和元素溢出保护能力。

### 布局引擎

#### 相对定位元素溢出保护
- `_calculate_relative` 新增组合盒约束：将参考元素 A 和相对元素 B 合并为最小包围盒 `A ∪ B`
- 组合盒超出 padding 安全区域时整体平移，参考元素坐标自动回写至 `self.positions`，保证两者对齐关系不变
- 平移量由溢出方向计算：左/上溢出取负偏移修正，右/下溢出取边界差值修正
- 安全夹持 `max(pad_left, min(x, pad_right - w))` 兜底

#### 依赖簇级联平移
- 多个元素 `relative_to` 同一参考时，组合盒自动扩展至全部已注册从属元素，防止先注册的从属被后续移位甩开
- `register_element()` 新增 `relative_to` 参数，自动维护 `self._dependents` 反向映射表
- 新增 `_shift_dependents()` 递归级联平移：移位参考元素时自动沿依赖树向下传播至所有从属
- 处理顺序示例：A(绝对) → B(relative_to=A) → C(relative_to=A)，C 计算时组合盒 = A ∪ B ∪ C，移位 A 时 B 和 C 同步平移

#### Padding 安全区域
- 新增 `_calculate_padding_bounds()` 方法，从 `layout.padding` 配置计算 `(left, top, right, bottom)` 边界
- padding 值以 `original_longer_side` 比例计算，未配置时默认 0（= 画布边界），向后兼容
- 绝对定位元素（`_calculate_absolute`）在计算完毕后应用 padding 截断，不再允许越界
- 优先级：padding > margin，即 margin 参与位置计算但最终坐标受 padding 约束

#### 拓扑依赖解析
- 新增 `_resolve_element_order()` 方法，基于 Kahn 算法（入度计数）对 `text_elements` 进行拓扑排序
- 从 `info_position` 中读取 `relative_to` 构建依赖图，无依赖元素（绝对定位）优先处理
- 循环依赖或其他未覆盖元素兜底原序追加，保证全部元素参与渲染
- 彻底消除手动调序需求：`text_elements` 按 append 自然序构建，渲染时自动按拓扑序执行

### 渲染引擎

#### 三阶段渲染管线
- `_add_text_and_icons_flexible` 拆分为三阶段：
  - **Phase 1 (测量)**：加载字体、测量尺寸、解析颜色，存入 `draw_items` dict，不触碰 `layout_engine`
  - **Phase 2 (计算+注册)**：按拓扑序 `calculate_position` → 基线调整 → `register_element`，保证 `relative_to` 引用立即可用
  - **Phase 3 (绘制)**：从 `layout_engine.positions` 读取最终坐标（含溢出修正后的变更）统一绘制
- 解决了旧版"边算边画"模式中参考元素已被绘制无法回写的问题

#### 渲染顺序修正
- Logo 渲染移至文字层之后，确保 `relative_to` 可正确引用已注册的文字元素（如 `relative_to: "exif"`）
- 此前 Logo 先于文字层执行，`get_element_bounds` 返回 `None` 导致回退到绝对定位

#### 相机+镜头合并
- `get_display_data()` 新增 `camera_lens_combined` 字段，格式 `"品牌 型号 | 镜头"`
- 渲染器按 `info_position` 中是否有 `camera_lens` 键决定使用合并或分开模式

#### timestamp_author 合并元素
- 新增 `timestamp_author` 元素，按 `info_position` 声明驱动，输出格式 `"时间 by 作者"`

#### 配置驱动渲染
- 所有文字元素改为由 `info_position` 声明驱动：配置中有对应键则渲染，否则跳过
- `author`、`location`、`exif`、`timestamp` 不再无条件渲染

### Logo

#### Logo 选择器增加"无"选项
- GUI 下拉菜单新增 "无" 选项，允许用户显式禁用 Logo
- 选中"无"时 `logo_filename` 传递空字符串 `""`，renderer 跳过自动匹配和渲染
- "无"与自动匹配行为解耦：前者显式跳过，后者 `None` 仍触发子串匹配

#### 自动匹配逻辑优化
- `auto_match_logo()` 简化为双向子串匹配（`brand_lower in logo_name or logo_name in brand_lower`），不区分大小写
- 移除 `_normalize_brand_name()` 方法（曾剥离特殊字符，可能导致误剔除有效匹配片段）及不再使用的 `re` 导入
- 文件名中包含品牌名称片段即可匹配（如品牌 "NIKON CORPORATION" 可匹配 `Nikon.png`）

#### 渲染器匹配守卫修正
- Logo 自动匹配条件由 `if not logo_filename` 改为 `if logo_filename is None`
- 空字符串（GUI "无"选项）不再触发自动匹配回退，仅 `None`（自动匹配模式）执行品牌匹配

### 样式配置

#### 相对定位字段
```yaml
info_position:
  timestamp:
    relative_to: "author"        # 相对于作者名称
    relative_position: "below"   # after/below/before/above/right-of/left-of
    alignment: "left"            # 相对方向垂直轴的对齐
    relative_margin: 0.02        # 间距比例，默认 0.01
    offset_x_ratio: 0.0          # X 轴微调（可选）
    offset_y_ratio: 0.0          # Y 轴微调（可选）
```

#### 新增元素类型
- `camera_lens`：相机+镜头合并单行输出（格式 `"品牌 型号 | 镜头"`），配置后替代 `camera` + `lens` 分开模式
- `timestamp_author`：时间+作者合并输出（格式 `"时间 by 作者"`），配置后替代独立 `timestamp`
- 以上均通过 `info_position` 中声明驱动，配置即渲染

#### 配置驱动渲染
- `info_position` 中声明的元素才渲染，未声明自动跳过
- `style_manager._validate_config` 移除默认条目注入（此前强行添加 `exif`/`author`/`location`/`camera_icon`）

#### Padding 配置
```yaml
layout:
  padding:
    left: 0.03     # 叠加元素不超出左边界
    right: 0.03    # 叠加元素不超出右边界
    top: 0         # 叠加元素不超出上边界
    bottom: 0      # 叠加元素不超出下边界
```
- 独立于 `expand_canvas` 和 `margin`，不影响原始图像位置
- 默认四边均为 0，与旧版行为完全兼容

#### 配置精简
- `colors`：移除无效字段 `background`、`accent`、`border`、`icon`（均零引用）；颜色系统改为 `custom_{text_type}_{dark/light}_color` + `custom_text_{dark/light}_color` 两级覆盖
- `fonts`：移除无效字段 `regular`、`line_spacing`；拆分为 `family`（字体族名）+ `weight`（字重 light/regular/medium），可通过 `--font-weight` 运行时覆盖
- `layout`：移除无效字段 `border_position`、`border_width`（边框由 decorator 独立处理）、`info_height_ratio`（零引用）
- `effects`：整节移除（零引用）
- `description`：移除（非必需元数据）
- `style_manager.py` 默认值与示例配置同步更新，移除 `_validate_config` 中的默认条目注入

### 高斯模糊

#### 色彩断层修复
- `apply_dithering()` 由 Python 逐像素 Floyd-Steinberg 循环（O(n²)，且限制 ≤200万像素）改为 PIL 内置 `image.quantize(dither=Image.Dither.FLOYDSTEINBERG)`，支持任意分辨率
- 叠加混合从 8-bit `Image.alpha_composite()` 改为 float32 numpy 逐通道混合，消除色彩量化断层
- 模糊计算由 PIL `GaussianBlur`（O(n²)）替换为 3-pass `BoxBlur`（O(n)），视觉效果几乎一致，性能大幅提升
- 新增 `_compute_scale_factor()` 自动降采样逻辑：原图长边 ≤1200px 不降采样，超过则缩放到 1200px，下限保护 512px
- `blur_radius` 按缩放比例动态递减，配置值（默认 200）始终代表全分辨率等效半径

#### 浅色背景模糊透明度调整
- 浅色模糊背景默认透明度调整：`gaussian_white_35` → `gaussian_white_50`，`gaussian_white_65` → `gaussian_white_80`
- GUI 下拉选项标签同步更新："模糊背景 (浅色 35%)" → "模糊背景 (浅色 50%)"，"模糊背景 (浅色 65%)" → "模糊背景 (浅色 80%)"
- 默认选项由 "模糊背景 (浅色 65%)" 改为 "模糊背景 (浅色 80%)"
- CLI `--bg-fill` 可选值同步更新
- `renderer.py` 中 `light_bg_types` 列表同步更新

### 代码清理

- 移除 `src/frames/base_frame.py` 及 `src/frames/` 目录：该文件仅有孤立法且无类定义，全项目零引用，功能已由 `LayoutEngine` + `FontManager` 替代
- 移除 `examples/` 目录（5 个历史残留示例文件），实际示例由 `src/frame_styles/configs/Default_TestFrame.yaml` 担任

---

## v1.1.0 (2026-04-29)

> 本版本使用 **DeepSeek V4 Pro** 模型进行了大规模的核心组件重构。

### 字体渲染

#### 中英日混排
- 中英文混排字符串（如 "焦距 24mm"）自动按 CJK / 拉丁片段拆分，各片段使用对应字体（GlowSansSC / Gotham）渲染，不再全文统一 fallback
- 混排以拉丁字体基线为基准，CJK 字符自动上移适配，确保中英日混排时视觉基线一致
- CJK 检测码位扩展覆盖ひらがな（U+3040–U+309F）、カタカナ（U+30A0–U+30FF）及カタカナ拡張（U+31F0–U+31FF），日文不再错误回退到西文字体
- `FontManager.split_mixed_text()` 与 `load_font()` 复用同一 `_CJK_CHAR_RE` 正则，保证拆分和字体选择逻辑一致

#### 智能字体选择
- 根据文本内容自动检测，西文使用 Gotham Medium，中文/日文使用 GlowSansSC
- 支持 light、medium、regular 三种字重，Gotham regular 自动映射到 Gotham-Book
- 基于 `(字体系列, 字重, 字号, 是否CJK)` 键值缓存字体，避免重复加载
- 字体大小以原图长边为基准按比例计算（最小 12px）
- 每种信息（EXIF、作者、位置等）可独立配置字体大小

### 渲染引擎

#### 高斯模糊模块
- 高斯模糊叠加和 Floyd-Steinberg 抖动算法独立为 `src/utils/gaussian_blur.py`
- 用 3-pass Box Blur 近似高斯模糊，时间复杂度 O(n)，视觉效果几乎一致
- `apply_dithering` 改用 PIL 内置 `image.quantize(dither=Image.Dither.FLOYDSTEINBERG)`，消除逐像素 Python 循环
- 中间分辨率根据原图长边动态调整（≤1200px 不降采样，超过 1200px 固定缩放到 1200px）
- Overlay 叠加从 8-bit `alpha_composite` 改为 float32 numpy 混合，减少色彩断层
- `gaussian_blur_radius` 和 `gaussian_blur_opacity` 配置参数真正生效

#### 渲染器优化
- `renderer.py` 通过 FontManager / LayoutEngine 抽取，从 1234 行精简至约 570 行
- `_parse_color_value()` 和 `_resolve_color_from_config()` 消除 40 行重复颜色解析逻辑
- `_create_background_with_expansion` 用字符串解析替代 6 分支 if/elif
- 调试 `print()` 替换为 `logging` 模块

#### 日志系统
- `src/utils/logging_config.py` 提供 `setup_logging()` 统一初始化
- DEBUG 级别输出到 `debug_log.txt`，INFO 及以上输出到控制台
- 幂等守卫，CLI 和 GUI 入口均已集成

### 文字颜色

- 支持样式配置文件中的 `custom_text_dark_color` / `custom_text_light_color`，根据背景类型自动选择
- 支持按文本类型细分配置：`custom_timestamp_light_color`、`custom_exif_dark_color` 等（`{text_type}` 可选 exif/timestamp/camera/lens/author/location）
- 背景类型使用预定义深色/浅色列表管理，新增类型只需添加名称

### 布局引擎

- `LayoutEngine` 独立类（`src/utils/layout_engine.py`），统一绝对/相对定位逻辑
- 绝对定位支持：top-left, top-right, bottom-left, bottom-right, top-center, bottom-center, top, bottom, left, right, center, inside, outside
- 相对定位支持：after, before, below, above, right-of, left-of
- 支持 `offset_x_ratio` / `offset_y_ratio` 偏移微调和 `relative_margin` 间距
- 元素注册表支持链式布局
- `calculate_position(width, height, config)` 统一适用于文字与非文字元素

---

## v1.0.1 (2026-04-10)

### EXIF 处理

- 提取相机品牌、型号、镜头、35mm 等效焦距、光圈、快门、ISO、拍摄时间
- 快门速度 <1 秒显示分数，≥1 秒显示小数
- 三层架构：EXIF Helper（解析）→ Device Mapper（映射）→ GUI/Renderer（展示）
- 统一数据出口 `get_display_data()`，GUI 预览与最终渲染数据一致

### HDR / 图像格式

- 支持 Gainmap HDR JPEG、UltraHDR、HEIF/HEIC/AVIF
- 色彩空间自动识别（sRGB / AdobeRGB / ProPhotoRGB），非 sRGB 自动转换
- 输入最大 12000×12000 px，输出最大 8192×8192 px，超限等比缩小

### 装饰元素

- 边框：可自定义宽度和颜色
- 水印：可自定义文字内容、位置和透明度
- Logo：可自定义位置、大小比例，支持根据相机品牌自动匹配
- 角落标记：可自定义文本、位置和样式

### GUI / 批量处理

- Streamlit Web 界面，支持图片上传/预览、样式选择、参数配置、结果下载
- 设备映射管理（相机/镜头），双排品牌筛选按钮，表格内编辑实时保存
- Logo 自动匹配，无匹配时不显示
- 批量处理支持多线程并发、递归子文件夹、进度跟踪、错误恢复

### 样式配置

- 支持 JSON / YAML / TOML 三种格式
- 扩展画布：以原图尺寸百分比为基础，四边独立设置
- 响应式设计：文字大小、边距等随输出尺寸自适应
- 独立边距配置：每个文字元素可单独设置四个方向的 margin

---

## v1.0.0 (早期开发)

- 项目初始化和目录结构搭建
- EXIF 处理模块、图像处理核心、相框样式管理
- GUI 界面、设备映射数据库、配置管理
- 相框渲染引擎、HDR 图像处理
- 装饰元素系统、批量处理
- 响应式设计与扩展画布
- 独立信息字体大小配置
- 背景样式运行时选择
- 错误处理改进
