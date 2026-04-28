# 更新历史

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

- 支持样式配置文件中的 `custom_text_color`，优先于自适应逻辑
- 支持为亮色/暗色背景分别设置颜色：`custom_text_light_color` / `custom_text_dark_color`
- 支持按文本类型细分配置：`custom_timestamp_light_color`、`custom_location_dark_color` 等
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
