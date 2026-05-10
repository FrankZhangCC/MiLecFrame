# 更新历史

## v1.5.1 (2026-05-09)

> 本版本重构 v1.5.0 的短版镜头名与竖幅自适应为 GUI 可选控制：支持镜头显示模式选择（相机+镜头 / 只显示相机 / 只显示镜头），短版镜头名开关改为全局可选（竖幅默认勾选）。

### 镜头显示模式重构 🟡 功能增强

- `RenderContext` 新增 `lens_display_mode`（combined / camera_only / lens_only）和 `use_short_lens` 参数，替代原 `is_vertical_or_square` 硬编码判断
- `lens_display_mode`：选择 `camera_only` 时 `camera_lens` → 相机；选择 `lens_only` 时 → 镜头
- `use_short_lens`：全局开关，控制 `camera_lens` 和 `lens` 是否使用短版名称，不再限于竖幅
- GUI 装饰元素板块新增：
  - **镜头显示** radio：`相机+镜头` / `只显示相机` / `只显示镜头`
  - **使用短版镜头名** checkbox：上传竖幅/方形图片时默认勾选
- `ImageProcessor.process()` → `FrameRenderer.render_frame()` → `RenderContext` 全链路透传新参数
- CLI（`main.py`）和批量处理（`batch_processor.py`）不改动，默认走 `combined` + 短版关闭，行为无变化

### 数据层优化

- `ExifHelper.get_display_data()` 新增 `camera_lens_combined_short` 字段，数据组装逻辑在 exif_helper 闭环
- `add_lens_mapping()` / `_record_device_info()` 同步写入 `short_lens` 列

### 三栏式 GUI 布局重构 🟡 功能增强

- **布局重组**：顶部四列配置栏 → 右侧独立配置栏（`st.columns([7, 3])`），主栏独占左侧 70% 空间用于预览和操作
- **图片信息移至侧边栏**：文件/相机/镜头/焦距/光圈/快门/ISO/拍摄时间在侧边栏 `📋 图片信息` 区域展示，字体 0.9rem + 行高 2，四项参数独立逐行列出，移除旧版冗余的"相框显示"预览区
- **EXIF 预提取**：利用 Streamlit `session_state` 在 widget 渲染前即可访问的特性，上传后侧边栏信息即时刷新，无需额外点击
- **右侧配置栏**：灰色底色（`#f0f2f6`）+ 圆角 + 白色输入框控件
  - `⚙️ 配置`：相框样式、输出格式（2 列），背景样式、字重（全宽）
  - `🎨 装饰`：作者姓名（全宽），GPS 替换 + 拍摄地点（同行 `[2,1]`），镜头显示 + 短版镜头名（同行 `[2,1]`）
  - `🏷️ Logo`：全宽选择
  - `💧 水印`：折叠 expander（默认收起）
- **控件布局优化**：GPS 替换选框移至拍摄地点输入框右侧、短版镜头名选框移至镜头显示下拉框右侧，CSS `margin-top: 1.5rem` 保证选框与输入框/下拉框纵向基线对齐
- **`st.rerun()` 修复预览时序**：处理成功后调用 `st.rerun()`，确保效果预览图即时显示（原问题：预览在按钮 handler 之前渲染，需下次交互才更新）
- **图片移除自动清理**：`uploaded_file` 为空时主动清除 `exif_data`、`file_info`、`display_data`、`processing_result` 等 session state，避免残留数据
- **所有 widget key 保留**，session state 向前兼容

### Logo 背景明暗自适应 🟢 新功能

- `LogoSelector.auto_match_logo()` 新增 `is_dark_bg` 参数，根据背景类型自动选择 Logo 颜色变体
- **暗色背景**（`text_scheme='dark'`）→ 优先匹配文件名以 `_white` 结尾的 Logo（白色在暗色背景上更醒目）
- **亮色背景**（`text_scheme='light'`）→ 优先匹配非 `_white` 结尾的 Logo（深色在亮色背景上更醒目）
- 新增 `_is_white_logo()` 静态方法检测文件名 `_white` 后缀（不区分大小写）
- 色调判断复用现有 `BackgroundFillManager.is_dark_bg()` 接口，零冗余
- `renderer.py`、`image_processing_page.py` 三处调用点统一传入 `is_dark_bg` 参数
- `is_dark_bg=None` 时行为完全向后兼容，不影响现有调用

### 高斯模糊背景饱和度增强 🟢 新功能

- `gaussian_blur.py` 新增 `_enhance_saturation()` 函数，使用 PIL `ImageEnhance.Color` 在模糊图像与覆盖层混合前增强色彩饱和度
- 4 个高斯模糊填充类型在 `FILL_TYPES` 中新增 `saturation` 字段，按覆盖透明度补偿：
  - 统一调整为 `2.0`（`gaussian_white_80` / `gaussian_white_50` / `gaussian_black_65` / `gaussian_black_35`）
- `BackgroundFillManager.render()` 新增 `saturation` 覆盖参数，`register()` 同步支持
- `renderer.render_frame()` → `image_processor.process()` 全链路新增 `saturation_override` 可选参数
- GUI `⚙️ 配置` 区新增「背景增强」复选框（默认勾选；纯色填充时灰显），取消勾选时传 1.0 禁用增强
- CLI 始终使用 FILL_TYPES 默认饱和度值，无需额外参数

### README 更新

- 版本号 1.5.0 → 1.5.1
- "竖向/方形图片自动适配"重写为"镜头显示模式 & 短版镜头名"，补充完整行为矩阵表
- 相机信息字段从三级扩展为五级（新增 `camera_lens_combined_short`）
- GUI 界面描述更新为三栏式布局

---

## v1.5.0 (2026-05-07)

> 本版本全面重构色彩渲染管线：ICC 转换前置保留原始位深、TIFF 保存路径修复、GUI 原始预览色彩校正、输出嵌入 sRGB ICC、下载文件名匹配、水印展平安全化、GUI 文件信息统一数据出口。响应式基准由原图长边切换为参照边（短边）。

### Logo 对角线保护 (2026-05-09)

- **对角线上限替代长边上限**：`renderer._add_logo()` 中 Logo 尺寸上限从长边改为对角线（`math.hypot`），系数从 2.5 调为 2，对正方形 Logo 无影响，对细长 Logo 提供更均匀的双向约束

### HDR 管线重构 (2026-05-09)

- **移除 OpenCV 依赖**：`hdr_handler.py` 原有的 `cv2.createTonemap(gamma=1.0)` 近似恒等变换被纯 NumPy 实现的 Reinhard 全局色调映射替代，消除对 `opencv-python` 和 `scikit-image` 的依赖
- **修正 HDR 处理顺序**：`image_processor.py` 中 HDR 图像先经 ICC 色彩空间转换（P3/BT.2020 → sRGB），再进行色调映射，避免在原始色域下做错误映射
- **HDR 加载优化**：`HDRHandler.load_image()` 改用 `to_pillow()` 保留 ICC profile，PIL 直读 HEIF/AVIF 时获取完整色彩元数据
- **格式检测重构**：`detect_hdr_format()` 替代 `is_hdr_format()`，检测逻辑收敛至 `HDRHandler`，移除 `image_processor` 中的 `hdr_supported_formats` 硬编码列表
- **移除不实宣称**：README 移除 Gainmap HDR JPEG 和 UltraHDR 的错误支持描述，更新技术栈、格式表和处理管线说明
- **依赖精简**：`requirements.txt` 移除 `opencv-python>=4.6.0` 和 `scikit-image>=0.19.0`（全项目零引用）

### 色彩空间转换管线重构 🔴 关键修复

- **ICC 转换前置**：`_convert_colorspace()` 将 ICC profile 转换从"模式转换之后"改为"模式转换之前"，避免 16-bit TIFF 的 `.convert('RGB')` 截断后再转换导致的精度损失
- **渲染意图显式指定**：`profileToProfile()` 新增 `renderingIntent=ImageCms.Intent.PERCEPTUAL`，解决默认意图可能导致的 ProPhoto RGB 高饱和区域色域裁剪伪影
- **日志可视化**：新增 `ImageCms.getProfileDescription()` 日志输出，可在调试日志中明确看到检测到的 ICC 色彩空间名称和转换成功/失败状态
- 覆盖所有嵌入式 ICC 色彩空间（Adobe RGB、ProPhoto RGB、Display P3、DCI-P3、Apple Image P3 等），通过 ICC profile 精确数学转换至 sRGB

### TIFF 保存路径修复 🔴 致命缺陷

- `_save_image` else 分支原先将 `quality=95, optimize=True` 硬编码传入所有非 JPEG/PNG 格式的 `image.save()`，TIFF 写入器不接受这两个参数，直接抛 `TypeError` 导致处理中断
- else 分支 `save_kwargs` 改为空字典 `{}`，消除 TIFF 输出硬性崩溃

### 输出嵌入 sRGB ICC Profile 🟡

- `process()` 在 `_convert_colorspace` 完成后捕获转换产生的 sRGB ICC 字节（`image.info['icc_profile']`），渲染后传入 `_save_image` 的 `icc_profile` 参数显式写入输出文件
- 确保输出文件始终携带正确的色彩空间标记，下游专业软件不再误判

### Pillow 12.2.0 API 兼容性修复 🔴 关键修复

- Pillow 12.2.0 的 `ImageCms.ImageCmsProfile` 不接受 raw bytes，必须用 `io.BytesIO()` 包装为类文件对象传递
- `_convert_colorspace` 和 GUI 原始预览的 ICC profile 处理统一使用 `io.BytesIO(icc_profile)` 替代直接传 bytes
- `ImageCms.Intent.PERCEPTUAL` 的 API 路径为 `ImageCms.Intent` 枚举（非 PIL 旧版的 `ImageCms.INTENT_PERCEPTUAL` 顶层常量）
- 修复前上述两处 API 不兼容均在 `except Exception` 中被静默捕获，回退到原始像素值（ProPhoto RGB 未转换），导致色彩空间转换看似生效实则完全失败

### GUI 原始预览色彩校正 🔴 用户体验

- 原始图片预览（`st.image()`）新增 ICC 检测与转换：先获取 `uploaded_file.getvalue()`，PIL 打开 → 检测 ICC → `profileToProfile` 转 sRGB → 再交给 Streamlit 渲染
- 解决 ProPhoto RGB TIFF / Display P3 JPEG 上传后预览颜色偏灰的问题

### 下载文件名匹配 🔴 用户体验

- 下载文件名从 `framed_{原始文件名}`（保留 `.tiff` 等原始后缀）改为 `framed_{stem}{输出扩展名}`
- 例如上传 `photo.tiff` 选择 JPEG 输出 → 下载文件名为 `framed_photo.jpg`，文件名与内容格式一致

### 水印展平安全化

- `decorator.add_watermark()` 中 `watermarked_img.convert('RGB')` 使用默认黑色背景展平 RGBA → 替换为显式白色背景 `Image.new('RGB', ..., (255,255,255))` + `paste(mask=alpha)`
- 消除透明像素被混合到黑色上的潜在暗边问题

### GUI 文件信息区域 🟢 新功能

- 原始图片预览下方新增 `📋 文件信息` 区域，3 列展示：编码格式（JPEG/PNG/TIFF 等）、色彩空间（ProPhoto RGB / sRGB / Adobe RGB 等）、像素尺寸（宽×高 px）
- 色彩空间通过 `ImageCms.getProfileDescription()` 读取嵌入式 ICC profile 描述，无 ICC 标记时显示 `sRGB（默认）`
- PIL Image 对象一次性打开，供文件信息 + 预览 ICC 转换复用，消除重复读取

### 文件元数据统一出口

- `ExifHelper` 新增 `get_file_info(image)` 静态方法，返回 `{format, color_space, width, height}` 字典
- GUI 文件信息区域从内联 PIL/ICC 提取逻辑改为调用 `exif_helper.get_file_info(pil_img)`，与 `get_display_data(exif_data)` 并列组成统一数据出口
- 遵循项目既有架构规范：所有显示数据均通过 ExifHelper 集中提供，GUI 层只负责渲染

### 边框功能移除 🟡 架构清理

- `decorator.py` 删除 `add_border()` 方法及 dispatch 分支，边框功能已无调用方
- `image_processing_page.py` 删除边框 UI 控件（checkbox / slider / selectbox）及关联配置条目
- `image_processor.py` 删除 docstring 中边框示例
- Logo 在 README 中从"装饰元素"独立为 `### Logo` 小节，明确其独立渲染管线定位（YAML `logo:` 节 + 文字层之后渲染 + `LogoSelector` 独立工具类）

### 短版镜头名称映射 🟢 新功能

- `lens_map.csv` 新增 `short_lens` 第三列，`DeviceMapper` 新增 `get_short_lens()` 方法
- `ExifHelper.get_display_data()` 输出 `short_lens` 和 `camera_lens_combined_short` 字段
- `RenderContext` 竖幅/方形图片自动适配恢复：`lens` / `camera_lens` 竖幅时使用短版名称
- 镜头映射管理页面新增"短版名称"列
- （v1.5.1 重构为 GUI 可选控制，详见上方）

### README 更新

- 版本号 1.4.1 → 1.5.0
- 处理管线第 5 步"色彩空间检测 → 非 sRGB 转换"修正为"色彩空间检测 → 非 sRGB ICC 数学转换"
- 输出嵌入 sRGB ICC profile 在保存步骤中体现
- GUI 界面上传描述新增"文件信息（编码格式 / 色彩空间 / 像素尺寸）"
- EXIF 架构文档新增 `get_file_info(image)` 静态方法描述，与 `get_display_data()` 并列组成统一数据出口

---

## v1.4.1 (2026-05-06)

> 本版本修复布局引擎 margin 积弊、扩展 alignment 组合格式支持、新增 GPS 坐标提取与 GUI 替换选项。

### 布局引擎 margin 逻辑修复

- **移除布尔闸门**：`_resolve_margins()` 旧逻辑使用 `if margin_top is None or margin_left is None` 作为二选一互斥开关，导致仅定义部分方向时全部独立 margin 值被静默丢弃、回退到统一 `margin`
- 新逻辑改为**逐方向独立回退**：统一 `margin` 作为初始值（未设默认 0），`margin_top` / `margin_bottom` / `margin_left` / `margin_right` 各自覆盖对应方向，不存在互斥激活条件
- 向后兼容：所有现有 YAML 配置均定义了完整四个 margin 方向，计算结果不变
- 影响：新配置可以只定义需要的方向（如仅 `margin_bottom: 0.03`），其余默认 0

### alignment 组合格式扩展

- `_align_x()` 新增 `bottom-left`（→ 左对齐）、`top-right` / `bottom-right`（→ 右对齐）
- `_align_y()` 新增带 `-left`/`-right` 后缀的组合格式（`top-left` / `top-right` → 顶对齐，`bottom-left` / `bottom-right` → 底对齐）
- 组合格式在各轴向上独立解析方向语义，互不干扰

### 相对定位 alignment 文档修正

- README 中相对定位 `alignment` 描述从模糊的"垂直轴对齐"改为按 `relative_position` 方向明确说明：
  - `after`/`below`/`before`/`above` → 控制**水平**方向，以参考元素宽度为基准
  - `right-of`/`left-of` → 控制**垂直**方向，以参考元素高度为基准
- 补充说明相对定位 alignment 以参考元素边界计算，与绝对定位 margin_* 无关

### 定位方式文档结构重构

- README 样式配置规范中新增 `#### 定位方式` (H4) 独立标题
- 下设 `##### 绝对定位` 和 `##### 相对定位` (H5) 子章节，从原 `info_position` 三级列表项中提升
- 定位系统行为规范（拓扑排序、缺失参考保护、组合盒溢出）独立为 `##### 定位系统行为规范`
- margin 体系从"必需"措辞改为逐方向独立描述，补充 float=比例 / int=像素 的详细计算规则和推荐优先级

### GPS 坐标提取 (EXIF GPS IFD) 🟢 新功能

- `ExifHelper._extract_gps()` 新增静态方法，从 piexif `"GPS"` IFD 中提取经纬度 Rational 元组
- `ExifHelper._format_dms()` 新增静态方法，将 `((deg_num,deg_den), (min_num,min_den), (sec_num,sec_den))` 格式化为度分秒字符串（如 `40°26'46.1"N 79°56'56.1"W`）
- `extract_exif_data()` 在 Exif 信息提取完成后自动调用 GPS 提取，写入 `exif_data['gps']` 和 `exif_data['gps_raw']`
- `get_formatted_exif_for_display()` 和 `get_display_data()` 透传 `gps` 字段
- 方向标识（`b'N'`/`b'S'`/`b'E'`/`b'W'`）自动 bytes 解码

### GPS 渲染与 GUI 集成

- `RenderContext.get_text('gps')` 新增 key，从 `exif_data['gps']` 返回 DMS 格式化坐标字符串
- 样式 YAML 中声明 `gps` 即可渲染 GPS 坐标（与 GUI checkbox 独立）
- 样式配置规范中 `info_position` 支持的元素类型、fonts.sizes、color 覆盖列表均新增 `gps`
- GUI 拍摄地点输入上方新增 "使用 GPS 坐标替换拍摄地点" checkbox
  - 图片含 GPS 数据时可选，无 GPS 时灰显 (`disabled=True`)
  - 勾选后显示 GPS 坐标信息，`location` 自动填充为 GPS DMS 字符串
  - 未勾选时保持手动 `st.text_input` 输入

### camera_make 独立暴露与 Logo 匹配统一

- `get_display_data()` 新增 `display_data['camera_make']`，存储 device_mapper 映射后的相机品牌（如 "Leica"、"Nikon"），不再仅用于拼接 `camera_combined` 后丢弃
- `RenderContext.get_text('camera_make')` 新增 key，返回映射后品牌字符串
- 样式 YAML 中声明 `camera_make` 即可独立显示品牌（与 `camera` 返回"品牌 型号"区分）
- Logo 自动匹配链路重构：renderer 不再通过 `ExifHelper.get_camera_brand(exif_data)` 直接读取原始 EXIF，改为 `context.get_text('camera_make')` 经 RenderContext 统一获取
- 匹配时对返回值 `.lower()` 处理，与 LogoSelector 子串匹配逻辑保持一致
- 样式配置规范中 `info_position` 支持的元素类型、fonts.sizes、color 覆盖列表均新增 `camera_make`

### Logo 文档修正

- README 中"装饰元素不通过样式配置 YAML 定义"的描述修正为区分三种装饰元素的配置来源：border/watermark 完全由外部参数控制，Logo 采用混合模式（YAML 定义布局/尺寸/定位，GUI/CLI 决定文件选择）
- 新增 Logo 配置文档小节，列出 `logo:` 节所有支持字段及默认值

### Logo 长边限制收紧

- `renderer._add_logo()` 中长边上限从 `3 × size_ratio × 原图长边` 收紧为 `2.5 × size_ratio × 原图长边`，降低细长 Logo 的视觉失控风险
- `assets/logos/README.md` 中形状建议同步从 `≤ 3:1` 改为 `≤ 2.5:1`

---

## v1.4.0 (2026-05-04)

> 本版本进行大规模架构重构：引入**背景填充管理器**实现填充类型集中注册与渲染解耦；**布局引擎 placement/position 拆分**消除定位语义混淆；**Logo 尺寸逻辑重构**支持非正方形 Logo 并加入长边保护；**FontManager 集成**消除字体加载代码重复；大量死代码清理。**GUI 性能优化**：EXIF 读取零落盘、预览缩略图生成、临时文件生命周期管理。

### EXIF 输出嵌入

- `ImageProcessor._save_image()` 保存时自动将原始 EXIF 嵌入输出图像，通过 `piexif.dump(exif_dict)` 生成二进制数据传入 `image.save(exif=...)`
- 输出扩展名自动判定保存格式（`.jpg` → JPEG, `.png` → PNG），不再依赖输入格式
- `ExifHelper.extract_raw_exif()` 新增方法，返回完整 piexif 字典（不做字段拆解）供嵌入阶段使用
- `ExifHelper.extract_exif_data()` 参数类型扩展为 `Union[str, bytes]`，支持直接传入图片二进制数据

### GUI 性能优化

- **消除 EXIF 临时文件**：上传图片的 EXIF 提取从"写入临时文件 → piexif 读取 → 删除"改为直接从 `uploaded_file.getvalue()` 的 bytes 读取，减少一次磁盘 I/O 及文件清理逻辑
- **预览缩略图**：处理完成后在内存中将输出图缩放到 1200px 长边再传给 `st.image()`，大幅降低传输带宽（全分辨率 ~15MB → 缩略图 ~200KB）
- **孤儿临时文件清理**：创建新 `temp_output_path` 前检查并删除旧输出临时文件，避免系统临时目录堆积
- **悬空引用修复**：删除 `temp_input_path` 后将 `session_state.temp_input_path` 置为 `None`，避免后续代码误用已删除路径

### 背景填充管理器 (BackgroundFillManager) 🔴 新模块

- 新增 `src/utils/background_fill.py`，作为背景填充功能的**唯一入口**
- 所有填充类型在 `FILL_TYPES` 类属性注册表中集中定义，明确定义各类型的 `method`（solid/gaussian）、颜色、透明度、模糊半径、`text_scheme`（dark/light）等属性
- **GUI/CLI 统一**：`get_choices()` 返回 `{label: key}` 映射供 GUI 下拉框，`get_keys()` 返回 key 列表供 CLI argparse
- **文字颜色自适应**：`is_dark_bg(key)` 替代 renderer 中硬编码的 `dark_bg_types`/`light_bg_types` 列表和字符串 `startswith` 判断
- **渲染统一**：`render(image, w, h, fill_type, *, color, opacity, blur_radius)` 封装背景创建逻辑，支持参数覆盖
- **预留扩展**：`register()` 方法支持运行时动态添加新填充类型，新增类型无需修改任何渲染器或界面代码
- **代码精简**：renderer 移除 `_create_background_with_expansion` 方法（24 行）、`dark_bg_types`/`light_bg_types` 列表（12 行）、`bg_fill_config` 参数传递链
- GUI 中 `bg_fill_options` 硬编码字典 → `BackgroundFillManager.get_choices()`；CLI `choices` 列表 → `get_keys()`；默认选项 → `DEFAULT_FILL`

### 布局引擎 placement/position 拆分 🔴 破坏性变更

- `position` 字段原先同时承担 inside/outside + 14 种锚点两维语义，现拆分为三个正交参数：
  - **`placement`**（新增）：`inside`（内部）/ `outside`（外部），默认 `outside`
  - **`position`**（简化）：14 种锚点位置（`top-left` / `top` / `bottom-right` / `left` / `center` 等）
  - **`alignment`**：元素自身对齐方式（`left` / `center` / `right`），语义不变
- `layout_engine._get_anchor()` 重构：新增 `placement` 参数，每个 position 分支拆分 inside/outside 两条 Y 计算路径
- 旧 `position: "inside"` / `position: "outside"` 自动映射为新格式
- 所有 YAML 配置、style_manager fallback 模板、样式创建器同步迁移

### Logo 尺寸逻辑重构

- 取消正方形限制，改为**短边基准等比缩放**：`logo.size_ratio * 原图长边` 确定 Logo 短边尺寸
- 新增长边上限保护：长边 ≤ `3 * size_ratio * 原图长边`，防止细长条 Logo 失控
- `renderer._add_logo()` 和 `decorator.add_logo()` 两处同步更新
- `assets/logos/README.md` 更新：形状建议从"正方形"改为"任意长宽比，建议 ≤ 3:1"

### FontManager 集成

- `Decorator.__init__` 接收 `FontManager` 实例（依赖注入，与 `renderer.py` 一致）
- `add_watermark()` 和 `add_corner_mark()`（已删除）中 ~70 行手写字体检测+路径拼接+逐个加载逻辑 → 替换为 `FontManager.load_font()` 调用
- 字体加载（中西文检测、字重映射、缓存、回退）统一由 `FontManager` 管理

### 死代码清理

- **`corner_mark` 全链路删除**：`decorator.add_corner_mark()` 方法（70 行）、`_calculate_position()` 方法（49 行）、`available_decorations` 中的 `corner_mark` 条目、`apply_decorations` 调度分支。无任何地方构造 `{type: 'corner_mark'}` decoration
- **`Decorator.add_logo()` 删除**（81 行）：唯一调用方 `apply_decorations` logo 分支无人触发。真实 Logo 路径为 `renderer._add_logo()`
- **`camera_icon` 全局移除**：renderer 中显式 `continue` 跳过，属无效元素。从 `ELEMENT_KEYS`、style_manager fallback 模板、3 个 YAML 配置、`_STYLE_TEMPLATE.txt`、README 中清除
- **`background_fill` YAML 段删除**：`background_fill.type` 从未被渲染器读取（由 GUI/CLI 参数决定），`gaussian_blur_radius` 和 `gaussian_blur_opacity` 硬编码到 `BackgroundFillManager` 注册表。从 4 个 YAML 配置、style_manager 验证/模板、样式创建器 UI、`_STYLE_TEMPLATE.txt`、README 中移除
- **`os` / `ImageFilter` / `re` 无用导入清理**

### Logo 相对定位支持

- 样式编辑器中 Logo 配置新增定位方式单选（absolute / relative）
- 相对模式支持 `relative_to`、`relative_position`、`relative_margin`、`offset_x_ratio`/`offset_y_ratio`
- 绝对模式保持原有 `placement`、`position`、alignment、四向 margin
- `_load_existing_style()` / `_collect_config()` 同步支持相对定位字段的读写

### 缺失参考元素预注册修复

- 当 `relative_to` 指向的元素因 EXIF 缺失无文本被跳过时，渲染器自动以 0x0 尺寸预注册其绝对位置锚点
- 避免了依赖元素降级为默认绝对定位导致的位置偏移（如 `timestamp_author` → `camera_lens` 在无 EXIF 时偏移）
- 仅 9 行代码，不修改其他逻辑

### 样式编辑器改进

- 新增 `placement` 下拉框（`outside`/`inside`），应用于元素编辑器和 Logo 编辑器
- `POSITION_OPTIONS` 拆分为 `PLACEMENT_OPTIONS` + `ANCHOR_POSITION_OPTIONS`
- 移除 `_render_background()` 函数及 `BG_TYPE_OPTIONS`（背景填充已由 `BackgroundFillManager` 接管）
- Logo 编辑器新增相对定位 mode radio + 全部相对定位参数 UI

### 内部优化

- `renderer.py`：从 471 行降至 429 行（删除 `_create_background_with_expansion`、`dark/light_bg_types`；替换为 `BackgroundFillManager` 调用）
- `decorator.py`：从 432 行降至 231 行（删除 `add_corner_mark`、`add_logo`、`_calculate_position`、`available_decorations`）
- `style_creator_page.py`：从 874 行降至 837 行（移除 background_fill UI）
- `style_manager.py`：移除 `background_fill` 验证注入和 fallback 模板字段、`camera_icon` 条目
- `main.py`：CLI `choices` 列表 → `BackgroundFillManager.get_keys()`；默认值 → `DEFAULT_FILL`
- 所有 YAML 配置文件精简

---

## v1.3.0 (2026-04-30)

> 本版本引入**样式变体系统**，支持根据数据可用性动态切换布局，无需修改渲染器代码。

### 样式变体系统

#### 文件夹样式组织
- 样式配置不再局限于单文件，支持以**文件夹**形式组织（文件夹名 = 样式名），文件夹内可包含多个变体配置文件
- `get_available_styles()` 同时扫描单文件样式（`.yaml` / `.json` / `.toml`）和文件夹样式，GUI 中统一展示为单个选项，对用户透明
- 同名文件夹与文件共存时，文件夹优先
- 传统单文件样式完全向后兼容，零改动即可继续使用

#### 变体命名规则与匹配
- **命名规则**：
  - `default.yaml` — 默认配置，无匹配变体时的兜底
  - `no_{field}.yaml` — 当 `{field}` 缺失（`None` 或空字符串）时匹配
  - `no_{field1}_no_{field2}.yaml` — 多字段同时缺失时匹配，越具体优先级越高
- **匹配算法**（`_resolve_style_variant()`）：
  1. 从传入的上下文 `{'location': ..., 'author': ...}` 提取实际缺失的字段集合
  2. 解析变体文件名中的所需缺失字段（按 `no_` 片段解析）
  3. 选取所需缺失集合是实际缺失集合子集**且**匹配字段数最多（最具体）的变体
  4. 无匹配时回退到 `default.*`；文件夹内无 `default.*` 时返回首个配置文件

#### 上下文传入
- `get_style_config(style_name, context=None)` — 新增可选 `context` 参数，接受 `{'location': '北京', 'author': '张三'}` 格式
- 不传 `context` 时行为与旧版完全一致，返回默认配置，保证 CLI、GUI 预览等路径的向后兼容
- `ImageProcessor.process()` 在获取样式配置时自动传入 `{'location': location, 'author': author}` 上下文

#### 配置加载重构
- 新增 `_load_config_file(config_path)` — 抽取单文件加载逻辑，消除 `get_style_config` 中的重复代码
- `get_style_config` 拆分流程：先尝试文件夹 → 文件内变体匹配 → 再回退单文件加载

### 内部改进

#### StyleManager 代码清理
- `get_available_styles()` — 从纯文件扫描改为同时扫描文件夹和文件，文件夹名即为样式名，逻辑清晰化
- `get_style_config()` — 行数从约 40 行精简整合，文件夹匹配与单文件加载共用 `_load_config_file()`
- `_resolve_style_variant()` — 独立的变体匹配引擎，解析与匹配逻辑内聚

### 样式编辑器

#### GUI 样式编辑页面
- 新增 `src/gui/style_creator_page.py`，在侧边栏「🎨 样式编辑器」入口，提供可视化表单
- **新建/编辑双模式**：顶部下拉框选择已有样式（含变体文件夹子级）或新建，选中后自动加载配置到表单
- **动态元素列表**：支持增删信息元素（exif / camera_lens / timestamp_author 等 9 种 key），每个元素独立切换绝对/相对定位
- **覆盖全部配置项**：画布扩展、padding、字体族/字重/独立尺寸、颜色（通用 + 按元素类型覆盖）、背景填充、Logo 开关
- **留空字段智能清理**：未填写的颜色、字体尺寸等字段生成 YAML 时不写入，保持配置文件精简
- **变体文件夹支持**：下拉框自动扫描 `configs/` 子目录中的变体 YAML 文件，以 `文件夹名/文件名.yaml` 层级展示

#### 样式模板文件
- 新增 `src/frame_styles/configs/_STYLE_TEMPLATE.txt`，覆盖全部 9 个配置区的填空式模板，填写后交给 AI 即可生成对应 YAML

---

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

#### 渲染上下文 (RenderContext)
- 新增 `src/utils/render_context.py`，将文字数据准备逻辑从 `renderer.py` 中解耦为独立模块
- `RenderContext.get_text(key)` 根据样式配置声明的 key 返回显示文本，内部闭环所有条件逻辑
- `_add_text_and_icons_flexible` 签名从 `(exif_data, author, location)` 简化为 `(context)`，17 行 if-elif 链替换为 for 循环遍历 `info_position` 的 key
- 新增显示字段只需在 `RenderContext.get_text()` 添加分支 + YAML 声明配置，renderer 零改动

#### 竖向/方形图片 camera_lens 自动替换
- `camera_lens` 检测到原始图片纵边 ≥ 横边（竖向或方形构图）时，自动替换为 `camera`，仅显示相机型号
- 横向图片保持原有 `"品牌 型号 | 镜头"` 合并格式
- 判断逻辑内聚于 `RenderContext` 内部，对外透明

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

### Bug 修复

#### 相对定位受特殊字符干扰
- 文字元素在 Phase 1 测量时存储的 `height` 由字形级 `bbox[3] - bbox[1]` 改为字体度量 `ascent + descent`
- 此前包含 `|`、`/` 等纵向跨度较大的字符时 bbox 变大，导致 `ty + th` 计算的下方元素间距异常增大
- 混排文本（`max_ascent + max_descent`）本身即基于字体度量，不受此问题影响

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
