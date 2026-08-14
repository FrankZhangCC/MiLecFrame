# 更新历史（开发版）

> 本文件记录所有开发版本的详细变更。发布版本摘要见 [CHANGELOG_RELEASE.md](./CHANGELOG_RELEASE.md)。

## v2.4.0-dev (2026-08-14)

> 便携版打包发行支持，统一资源路径定位，新增矩形装饰元素，文档重构。

### 🟢 便携版打包发行支持 (feat)

- 新增 `MiLecFrame.spec`（PyInstaller onedir 配置）与 `build_release.py` 一键打包脚本
- 新增 `src/utils/app_paths.py` 统一路径定位：可写数据（config.json、设备映射 CSV、日志、用户样式）位于 exe 同目录，只读资源（字体、Logo、内置样式）随包打包，整个文件夹拷贝即用
- 支持从 PNG 一键生成多尺寸 ICO 应用图标（`--icon` 参数）
- 发行版字体精简打包：仅打包样式配置实际引用的 6 个字重文件（原 391MB → 约 30MB）
- 无控制台窗口模式：`main.py` 增加标准输出保护，windowed 模式下 print 输出重定向至 `MiLecFrame_console.log`

### 🔴 修复：CLI 模式导入崩溃 (fix)

- 修复 `python src/main.py -i ... -o ...` 单张/批量处理模式的 `attempted relative import beyond top-level package` 错误
- 统一入口导入为 `src.` 前缀，`main.py` 顶部插入项目根目录到 sys.path

### 🟢 新增自定义矩形（rectangles）装饰功能 (feat, fdd4d92)

- 样式配置支持半透明装饰色块，可用于画面装饰与文字底衬

### 🟢 文档重构 (docs, 7d8059a)

- README 拆分，新增样式配置指南与开发参考文档

## v2.3.0-dev (2026-07-18)

> 新增拍摄时间显示模式控制，EXIF 焦距改用 35mm 等效值，LOGO 品牌尺寸补偿系数独立为外部 YAML 文件。

### 🟢 拍摄时间显示模式控制 (feat, 8f7e2cf)

用户可通过 GUI「拍摄信息配置」折叠栏内的 ComboBox 或 CLI `--timestamp-display` 参数控制拍摄时间的显示方式：

- `'full'`（默认）：显示完整日期与时刻（yyyy.mm.dd hh:mm:ss）
- `'date_only'`：仅显示日期（yyyy.mm.dd），通过 `[:10]` 切片实现
- `'hide'`：不显示拍摄时间，自动注入 `context['timestamp'] = None` 使 `StyleManager` 匹配 `no_timestamp.yaml` 变体

`timestamp_author` 组合文本三段 fallback 逻辑：
1. 时间 + 作者 → `'ts by author'`
2. 仅时间 → `'ts'`
3. 仅作者（时间隐藏）→ `'Shot by author'`
4. 两者皆无 → `None`（不渲染）

### 🔴 修复：EXIF 信息栏焦距改用 35mm 等效焦距 (fix, c5ef21a)

- `image_processing_page.py`：`_update_exif_info` 中焦距显示从 `raw_focal_length`（物理焦距）改为 `raw_focal_length_35mm`（35mm 等效焦距），无 35mm 数据时回退到物理焦距，与 `RenderContext.get_text()` 行为一致
- `胶片夹风格 FilmClip`：`default.yaml` 和 `no_custom_text.yaml` 的 `corner_radius` 圆角从 `0.04` 调小至 `0.025`

### 🟢 Logo 品牌尺寸补偿系数独立为外部 YAML (refactor, c907006)

**背景**：此前品牌补偿系数硬编码在 `LogoSelector.BRAND_SCALE_FACTORS` 类字典中，程序编译后系数不便更改，也不便添加新 LOGO 支持。

**设计要点**：
- 所有系数迁移至 `data/logo_scale.yaml` 外部配置文件，支持注释，用户可直接编辑增删
- YAML 格式（避免 CSV 编码问题），与项目已有的样式 YAML 配置体系一致
- `LogoSelector.__init__` 新增可选参数 `scale_config_path`，默认指向 `data/logo_scale.yaml`
- 新增 `_ensure_scale_file_exists()` 方法：文件不存在时自动创建带注释的默认版本
- 新增 `_load_scale_factors()` 方法：安全加载 YAML，含类型校验 + 错误 fallback 为空字典
- `.gitignore` 新增 `!data/logo_scale.yaml` 允许 Git 追踪

**向后兼容**：
- `LogoSelector()` 无参调用完全不变，原有 import 和调用代码零改动
- `get_brand_scale_factor()` 签名不变，返回行为完全一致
- YAML 损坏时静默 fallback 为空字典（均返回 1.0），不影响渲染流程

### 📝 文档

- `CHANGELOG.md`：本页更新

## v2.2.0-dev (2026-06-19)

> 样式选择器从文字下拉列表重构为**横向缩略图滚动选择**。所有样式配置文件迁移至独立文件夹，支持在每个样式目录下放置 `thumbnail.png` 作为预览图。新增 `StyleManager.get_style_thumbnail()`、`layout_debug` 调试工具、`ExpandGroupSettingCard` 开发铁律。

### 🟢 样式选择器重构（文字列表 → 缩略图滚动）

**`src/gui_pyside/widgets/style_selector_card.py`** — 完全重写：

- 移除 `FlowContainer` + `FlowLayout` 实现，改用 `SmoothScrollArea` + `QHBoxLayout` 横向滚动条模式（与底部胶片栏同架构）
- 新增 `HorizontalWheelFilter`：将垂直滚轮事件转为水平平滑滚动，复用 `SmoothScrollDelegate.hScrollBar.scrollValue()`
- 固定高度 `SCROLL_AREA_HEIGHT = CARD_HEIGHT + 22`，`_adjustViewSize()` 使用 `maximumHeight()` 而非 `sizeHint().height()` 计算 spaceWidget 高度
- 图片加载时通过 `QPixmap.scaled(THUMBNAIL_SIZE, THUMBNAIL_SIZE, KeepAspectRatio, SmoothTransformation)` 将 512×512 原图缩放到 120×120

**`src/gui_pyside/pages/image_processing_page.py`**：

- 配置面板新增独立 Tab 2「样式选择」`StyleSelectorCard`，原「相框配置」Tab 中的样式 `ComboBox` 已移除
- 所有 `self.combo_style` 引用替换为 `self.style_selector_card.current_style`

### 🟢 样式缩略图系统

**`src/frame_styles/style_manager.py`**：

- 新增 `get_style_thumbnail(style_name)` 方法：在样式文件夹中查找 `thumbnail.png/jpg/jpeg`，返回绝对路径或 `None`
- `get_available_styles()` 返回 `sorted(styles)` 字母序排列

**`src/gui_pyside/widgets/style_thumbnail_card.py`**：

- 选中态从 `setCustomStyleSheet`（QSS 渲染）改为 `paintEvent` 中 `QPainter.drawRoundedRect` 直接绘制 2px 主题色圆角边框，解决 `CardWidget` 基类 paintEvent 不执行 QFrame 默认绘制导致 QSS 边框无效的问题
- 缩略图尺寸调整：`CARD_WIDTH=156`、`CARD_HEIGHT=185`、`THUMBNAIL_SIZE=140` → `CARD_WIDTH=136`、`CARD_HEIGHT=160`、`THUMBNAIL_SIZE=120`
- 样式名称从 `BodyLabel` 改为 `CaptionLabel`（更小字号适配窄卡）
- 图片加载后绘制 2px `rgba(0,0,0,38)` 圆角描边

### 🟢 新增文件

- `src/gui_pyside/utils/layout_debug.py`：`dump_expand_card(card)` 调试工具，打印卡片各层尺寸并自动检测收起间隙、滚动范围不足等异常

### 🟢 configs 存储结构重构

所有单文件样式迁移为独立文件夹（文件夹名 = 样式名）：

| 之前 | 之后 |
|------|------|
| `configs/裁剪胶片 FilmCut.yaml` | `configs/裁剪胶片 FilmCut/default.yaml` |
| `configs/简洁信息 SimpleInfo.yaml` | `configs/简洁信息 SimpleInfo/default.yaml` |
| `configs/宝丽来风格 Polaroid.yaml` | `configs/宝丽来风格 Polaroid/default.yaml` |
| `configs/底部信息条 Bottom Bars/`（已是文件夹） | 不变，新增 `thumbnail.png` 目录 |
| `configs/胶片夹风格 FilmClip/`（已是文件夹） | 不变，新增 `thumbnail.png` 目录 |

`StyleManager.get_style_config()` 保留单文件 fallback 逻辑以向后兼容。

### 🟢 文档与工具

- `README.md`：版本徽标更新至 v2.2.0-dev；样式配置规范新增"文件夹组织"要求；新增「样式缩略图」配置说明（512×512 PNG/JPG 预置）
- `AGENTS.md`：新增「ExpandGroupSettingCard 开发铁律」6 条规则 + layout_debug 调试验证流程

### 🐛 修复

- **StyleSelectorCard 展开后大片灰色区域**：`FlowLayout.sizeHint()` 仅返回 max 子控件尺寸，被 `_adjustViewSize()` 取用后 spaceWidget 高度不足，改为 `smoothScrollArea.maximumHeight() + 3`
- **StyleSelectorCard 收起时底部间隙**：`QScrollArea.sizeHint()` 不反映 `setFixedHeight()`（始终 ~8px），spaceWidget 仅 ~11px 滚动范围不足，改为 `_adjustViewSize()` 覆盖
- **缩略图超出卡片右边界**：`CARD_WIDTH` 从 140 增加到 `THUMBNAIL_SIZE + 左/右边距 = 136`，ImageLabel 嵌入卡片内容区内
- **512×512 缩略图未缩放**：`QPixmap` 加载后未调用 `.scaled()`，直接以原生分辨率设置导致溢出。加载后等比缩放至 `THUMBNAIL_SIZE × THUMBNAIL_SIZE`

### 🟢 拖放支持

**`src/gui_pyside/pages/image_processing_page.py`**：

- 页面级 `setAcceptDrops(True)` + `dragEnterEvent` / `dragMoveEvent` / `dragLeaveEvent` / `dropEvent` 完整拖放事件链
- 图片扩展名白名单 `_ALLOWED_EXT` 过滤（与文件对话框一致），非图片文件自动跳过并 `InfoBar.warning` 提示
- 拖入文件时显示半透明蒙层覆盖全页面，中央显示"松开左键以添加图片"（`BodyLabel`，32px 浅色文字），`dragLeaveEvent` / `dropEvent` 后自动隐藏
- `WA_TransparentForMouseEvents` 确保蒙层不拦截拖放事件传递
- 拖放文件路径直接复现有 `_load_files()` 方法，零改动

### 🟢 Delete 键移除图片

- 新增 `QShortcut(QKeySequence.Delete, self)` 全局快捷键，`_on_delete_key()` 回调
- 回调中检测焦点控件类型：若焦点在 `QLineEdit` 时跳过（保留文字删除原生行为），否则调用 `_remove_filmstrip_item(self.current_index)`

## v2.1.1-dev (2026-06-13)

> 新增 **GUI 色彩管理（QColorSpace）** 与 **深色模式适配**。修复在广色域显示器（如 Display P3）上 sRGB 图片显示过饱和的问题；所有硬编码的 `setStyleSheet` 浅色背景色替换为 QFluentWidgets 的 `setCustomStyleSheet(lightQss, darkQss)` 双主题方案，自动跟随系统深色/浅色主题切换，无需手动监听信号。

### 🟢 QColorSpace 色彩管理

**`src/gui_pyside/pages/image_processing_page.py`**：

- `_create_thumbnail()`：生成缩略图 QImage 后调用 `setColorSpace(QColorSpace.NamedColorSpace.SRgb)`，告知 Qt 渲染管道的色彩空间
- `_update_preview()`：预览大图两处 QImage 创建（`result_path` 和 `file_bytes` 分支）同样添加 `setColorSpace()`

**`src/gui_pyside/widgets/style_preview.py`**：

- `set_preview_image()`：样式编辑器的预览 QImage 同样标记 SRgb 色彩空间

**原理**：Qt 6 在 `QPainter.drawImage()` 时会自动读取 `QImage.colorSpace()` 进行色域映射。在 sRGB 屏上原样显示，在 Display P3 等广色域屏上做正确的色域转换，消除颜色拉伸导致的过饱和。

### 🟢 深色模式适配（`setCustomStyleSheet`）

**`image_processing_page.py`**（11 处样式 → `setCustomStyleSheet` 双主题）：

| 位置 | 样式对象 | Light | Dark |
|------|---------|-------|------|
| 类常量 | `_STYLE_THUMB_NORMAL` | 边框 `#ddd`，背景 `white` | 边框 `#444`，背景 `#282828` |
| 类常量 | `_STYLE_THUMB_SELECTED` | 边框 `#0078d4`，背景 `white` | 边框 `#4da6ff`，背景 `#282828` |
| 常量 | `_STYLE_THUMB_PROCESSED` | 边框 `#00a86b`，背景 `white` | 边框 `#6ccb5f`，背景 `#282828` |
| `_setup_ui()` | 主 QSplitter 手柄 | 背景 `#e0e0e0`，hover `#0078d4` | 背景 `#3D3D3D`，hover `#4da6ff` |
| `_setup_ui()` | 内容 QSplitter 手柄 | 同上 | 同上 |
| `_create_preview_panel()` | EXIF 面板 | `#f5f5f5` | `#2B2B2B` |
| `_create_config_panel()` | ScrollArea 配置面板 | `#f5f5f5` | `#2B2B2B` |
| `_create_filmstrip()` | 胶片栏背景 | 顶边 `#e0e0e0`，底 `#fafafa` | 顶边 `#3D3D3D`，底 `#282828` |
| `_update_preview()` | 显示图后预览背景 | `#fafafa` | `#282828` |
| `_update_filmstrip_thumbnail()` | 已处理缩略图 | 绿色 `#00a86b`，hover 蓝 | 绿 `#6ccb5f`，hover `#4da6ff` |

- 预览占位样式（虚线边框、灰色文字、近白背景）从 3 处硬编码（`_create_preview_panel` / `_on_clear_all` / `_remove_filmstrip_item`）抽取为 `_apply_preview_placeholder_style()` 方法，统一维护
- `_set_thumb_style()` 从 `setStyleSheet` 字符串切换到 `setCustomStyleSheet` 双主题，引用类常量 dict 中的 `'light'` / `'dark'` 键

**`style_preview.py`**（2 处样式 → `setCustomStyleSheet` 双主题）：

| 位置 | Light | Dark |
|------|-------|------|
| `__init__()` 预览占位 | 边框 `#e0e0e0`，字 `#888`，底 `#fafafa` | 边框 `#404040`，字 `#999`，底 `#282828` |
| `set_preview_image()` 渲染后背景 | `#fafafa` | `#282828` |

**颜色设计依据**：Dark 色值参考 QFluentWidgets 源码标准：
- `#282828` = Flyout 背景（比主窗口 `#202020` 略亮，适合卡片/预览区域）
- `#2B2B2B` = Dialog 面板背景（适合功能面板）
- `#3D3D3D` = Separator 分割线颜色
- `#4da6ff` = 亮蓝强调色（Fluent Design Blue 在深色背景上的变体）
- `#6ccb5f` = `FluentSystemColor.SUCCESS_FOREGROUND` 深色值

### 🔴 修复：`setCustomStyleSheet` 未对新建 widget 生效

`setCustomStyleSheet(widget, lightQss, darkQss)` 是 QFluentWidgets 提供的双主题样式接口，但其内部实现**只将 QSS 字符串存储为 widget 的动态属性**（`lightCustomQss` / `darkCustomQss`），并不调用 `widget.setStyleSheet()`。实际样式生效依赖 `CustomStyleSheetWatcher` 事件过滤器监听 `DynamicPropertyChange` 事件后触发 `addStyleSheet()`——而该事件过滤器由 `styleSheetManager.register()` 安装。

**根因**：`_add_filmstrip_item()` 等场景中，thumb_label 是新创建的 QLabel，从未经过 `styleSheetManager.register()`，事件过滤器未被安装。`setCustomStyleSheet` 存储了属性但 `setStyleSheet()` 从未被调用，边框样式不生效。

**修复**（`image_processing_page.py`）：
- 新增 `_apply_custom_style(widget, lightQss, darkQss)` 辅助方法，在 `setCustomStyleSheet` 之后立即调用 `addStyleSheet(widget, CustomStyleSheet(widget))` 完成注册和应用
- 所有 10 处 `setCustomStyleSheet` 调用替换为 `self._apply_custom_style`

**`style_preview.py`**：两处 `setCustomStyleSheet` 调用后追加 `addStyleSheet(self.preview_label, CustomStyleSheet(self.preview_label))`

**验证**：测试脚本确认新建 QLabel 调用 `setCustomStyleSheet` 后 `styleSheet()` 为空，`addStyleSheet` 后 `styleSheet()` 正确返回 QSS。

### 🟢 硬编码强调色统一为 QFW 主题色变量

所有缩略图选中/悬停边框色从硬编码 `#0078d4` / `#4da6ff` 替换为 QFluentWidgets 的 `--ThemeColorPrimary` QSS 变量：

| 常量 | 替换项 | 语义 |
|------|--------|------|
| `_STYLE_THUMB_NORMAL` | `QLabel:hover { border-color }` | 悬停预览色 |
| `_STYLE_THUMB_SELECTED` | `QLabel { border }` + `QLabel:hover { border-color }` | 选中强调色 |
| `_STYLE_THUMB_PROCESSED` | `QLabel:hover { border-color }` | 悬停统一 |

`--ThemeColorPrimary` 由 QFW 的 `renderQss()` 在 `StyleSheetCompose.content()` 拼接后统一替换为当前主题色值（默认 `#009faa`），主题切换和主题色变更时自动跟随，无需额外代码连接信号。绿色已处理边框（`#00a86b` / `#6ccb5f`）保留为语义状态色。

### ⚙️ 架构: `setCustomStyleSheet` 机制

使用 QFluentWidgets 内置 `setCustomStyleSheet(widget, lightQss, darkQss)` 替代 `widget.setStyleSheet(qss)`。该函数自动将 dark/light QSS 分别作为动态属性存储，通过 `CustomStyleSheetWatcher` 监听 `DynamicPropertyChange` 事件，在主题切换时自动刷新。无需手动连接 `qconfig.themeChanged` 信号。

### 📝 文档

- `README.md` 版本徽标更新至 v2.1.1-dev
- `CHANGELOG.md`：本页更新

## v2.1.0-dev (2026-06-12)

> 新增**样式配置自定义背景填充色**特性。样式可在 `colors` 区块中声明 `custom_bg_color`（支持 `#RRGGBB` 十六进制或 `[R,G,B]` 数组），指定后渲染器自动使用纯色背景覆盖 GUI 的 `bg_fill_type` 选择，同时 GUI 的背景样式下拉框自动禁用。新增 `custom_bg_text_scheme`（`dark`/`light`）可显式声明背景明暗类型以决定文字和 Logo 配色，未声明时自动根据颜色亮度检测。

### 🟢 新增：样式配置自定义背景填充色

**配置方式**（`src/frame_styles/configs/样式名.yaml`）：

```yaml
colors:
  custom_bg_color: "#28180B"           # 支持 "#RRGGBB" 或 [R,G,B]
  custom_bg_text_scheme: "dark"        # 可选：dark / light，留空自动检测
```

- `colors` 区块下新增两个可选字段，与现有 `custom_text_light_color` / `custom_text_dark_color` 平级
- `custom_bg_color` 接受两种格式：十六进制字符串（如 `"#FF6B6B"`）或 RGB 数组（如 `[255,107,107]`），与现有颜色配置风格一致
- `custom_bg_text_scheme` 可选声明 `dark` 或 `light`，未声明时使用相对亮度公式（`luminance = 0.299R + 0.587G + 0.114B`）自动判定
- 样式指定 `custom_bg_color` 后，`BackgroundFillManager.render()` 使用纯色填充覆盖扩展画布，完全不依赖用户选择的 `bg_fill_type`

### 🟢 渲染器核心支持

**`src/core/renderer.py`**：

- `render_frame()` 在解析 `style_config` 后检测 `colors.custom_bg_color`，若存在则：
  1. 调用 `_parse_hex_or_rgb()` 解析颜色值
  2. 读取 `custom_bg_text_scheme`（可选），未设置时自动计算亮度判定
  3. 调用 `BackgroundFillManager.register_custom_solid()` 动态注册填充类型
  4. 使用注册返回的 key 作为 `effective_bg_type` 覆盖原有 `bg_fill_type`
- 后续 `text_renderer.render()` / `logo` 自动匹配 / `is_dark_bg()` 均使用 `effective_bg_type`，零额外适配
- 颜色解析失败时自动回退到用户选择的 `bg_fill_type`，保证鲁棒性

**`src/utils/background_fill.py`**：

- 新增 `register_custom_solid(color, text_scheme)` 方法：注册自定义纯色填充并返回 key
- **预留接口**：后续 GUI 自定义颜色功能可通过同一入口调用，保证行为一致

**`src/core/text_renderer.py`** — 关键修复：

- `_resolve_color_from_config()` 此前强制要求 `dark_key` 和 `light_key` **成对存在**（`if dark_key not in colors_config or light_key not in colors_config: return None`），导致仅声明单侧颜色（如仅 `custom_text_dark_color`）时无法生效
- 改为只检查当前背景明暗对应的 key，允许单侧声明，与设计意图一致

### 🟢 图像处理页面 GUI

**`src/gui_pyside/pages/image_processing_page.py`**：

- `_update_style_dependent_controls()` 新增 `custom_bg_color` 检测：
  - 样式有自定义背景色 → `combo_bg_fill.setEnabled(False)` + `chk_enhance.setEnabled(False)` + tooltip 显示颜色值
  - 样式无自定义背景色 → 恢复正常可操作状态
- 背景增强复选框（仅高斯模糊有效）同步禁用，因纯色背景无需增强

### 🟢 样式编辑器支持

**`src/gui_pyside/widgets/style_config_sections/colors_section.py`**：

- 在通用兜底颜色和按元素覆盖之间新增"自定义背景填充" UI 区块：
  - `custom_bg_color` `LineEdit`：支持 `"#FF6B6B"` 或 `[255,107,107]` 输入
  - `custom_bg_text_scheme` `ComboBox`：三选项（自动检测 / dark / light）
- `load_from_model()` / `save_to_model()` 同步读写新字段

**`src/gui_pyside/models/style_config_form.py`**：

- `StyleConfigFormData` 新增 `custom_bg_color: str` 和 `custom_bg_text_scheme: str` 字段
- `to_yaml_dict()`：在 `colors` 区块中写入 `custom_bg_color` / `custom_bg_text_scheme`
- `from_yaml_dict()`：从 YAML 读取并恢复字段值

### 🟢 演示样式

**`src/frame_styles/configs/裁剪胶片 FilmCut.yaml`**：

- 作为新特性演示样式，配置深褐暖色调背景：
  - `custom_bg_color: "#28180B"` — 深棕色背景
  - `custom_bg_text_scheme: "dark"` — 暗色背景，使用浅色文字
  - `custom_text_dark_color: "#DFAE81"` — 所有文字显示为暖金色
- 此样式加载后，GUI 背景样式下拉框自动禁用，背景增强开关同时禁用

### 🟢 文档更新

- `README.md` 版本徽标更新至 v2.1.0-dev
- `src/frame_styles/configs/_STYLE_TEMPLATE.txt`：颜色配置节新增 `custom_bg_color` 和 `custom_bg_text_scheme` 填写示例
- `CHANGELOG.md`：本页更新

## v2.0.0-dev (2026-06-09)

> **里程碑版本**。GUI 从 Streamlit Web 界面全面迁移至 PySide6 + QFluentWidgets 原生桌面应用，实现 Fluent Design 风格界面。Streamlit 版已封存，批量处理页面因胶片栏功能覆盖而取消。新增 PyInstaller 编译支持，为独立 exe 发布奠定基础。

### 🔴 架构变革：GUI 框架迁移 (Streamlit → PySide6)

**Streamlit Web GUI 已封存**（`src/gui/` → `src/gui_legacy/`），PySide6 原生桌面 GUI 成为唯一默认入口：

- 新建 `src/gui_pyside/` 完整应用目录：
  - `app.py` — QApplication 初始化 + Fluent 主题设置 + 高 DPI 适配
  - `main_window.py` — `FluentWindow` 主容器，`NavigationInterface` 导航栏 + `QStackedWidget` 页面路由
  - `models/` — `FileItem`（图片文件数据模型）、`ProcessingConfig`（处理配置）、`StyleConfigFormData`（样式编辑器表单）
  - `utils/temp_manager.py` — 临时文件生命周期管理器，窗口关闭时自动清理
- **移除** `types.ModuleType` hack：`src/gui_pyside/app.py` 不再需要伪造 `src` 模块，因 `src/__init__.py` 不再自动导入 streamlit

**入口简化**（`src/main.py`）：

| 项目 | 之前 | 之后 |
|---|---|---|
| 无参数启动 | 弹出 tkinter 对话框选模式 | **默认启动 PySide6** |
| `--gui` 参数 | 启动 Streamlit | **已删除** |
| `--mode` 参数 | streamlit/pyside 二选一 | **已删除** |
| `launch_gui()` | Streamlit subprocess 启动 | **已删除** |
| `_free_port()` | 释放 Streamlit 端口 | **已删除** |

**取消批量处理页面**：因图像处理页面中的胶片栏已支持多图排队处理，批处理页面不再需要。CLI `--batch` 模式与 `BatchProcessor` 核心模块保留不变。

### 🟢 图像处理页面（`image_processing_page.py`）

完整 PySide6 实现，基于 QFluentWidgets 组件：

**页面布局**：上下垂直分割器（主内容区 80% + 胶片栏 20%），主内容区再水平分割（预览 55% + 配置栏 45%）

**预览窗口**：
- 单图显示（非分栏），加载时显示原图，处理后自动切换为效果图
- 使用 PIL 加载大图绕过 Qt 256MB QImageIOHandler 分配上限
- 压缩到预览标签尺寸，保持宽高比
- ICC 色彩空间自动转换（`_convert_to_srgb`）

**EXIF 信息面板**：
- 两行四列网格布局：第一行 = 文件格式/色彩空间/尺寸、相机、镜头；第二行 = 焦距、光圈、快门、ISO
- 支持 `<b>HTML</b>` 富文本高亮值字段
- 无数据时显示 `—` 占位符

**胶片栏（FilmStrip，页面底部）**：
- 横向滚动缩略图列表，等比缩略图（高度自适应 60–120px）
- 三种状态指示：灰色边框=未处理、蓝色高亮=已选中、绿色边框=已处理
- 滚轮事件过滤器将垂直滚动转为水平滚动
- 右键菜单 → 移除此图片
- 动态重新缩放：窗口/分割器变化时自动调整缩略图尺寸
- `_rescale_filmstrip_thumbnails()` + `QTimer.singleShot` 防抖

**配置面板（5 个手风琴折叠 Tab，`ExpandGroupSettingCard`）**：

| Tab | 控件 | 条件控制 |
|---|---|---|
| 输出设置 | 输出格式 `ComboBox`（JPEG/PNG） | ✅ 始终可用 |
| 相框配置 | 相框样式、背景填充、背景增强 `SwitchButton`、字重 | ✅ 始终可用 |
| 个性化配置 | 作者姓名、拍摄地点、GPS 替换、自定义文本 | 🔹 自定义文本仅样式 `custom_text.enabled` 时启用 |
| 拍摄信息配置 | 镜头显示、短版镜头名、LOGO 选择 | 🔹 LOGO 仅样式 `logo.enabled` 时显示 |
| 文本水印 | 启用水印 `SwitchButton`、内容、位置、不透明度 `Slider`（0-100）、颜色 | 🔹 水印内容/位置/不透明度/颜色仅启用时可编辑 |

**操作按钮**：
- `PrimaryPushButton`：导出当前图像、一键导出所有、生成相框
- `TransparentPushButton`：清空所有
- 按钮启用状态自动管理：有图片选中→启用生成；处理完成→启用导出

**处理流程**（`_on_generate_frame`）：
1. 从 GUI 控件收集所有配置参数（背景/字重/镜头/LED 映射等）
2. GPS 替换逻辑：勾选且 EXIF 含 GPS → 用 GPS 覆盖地点
3. LOGO 选择：自动匹配（`LogoSelector.auto_match_logo`）/手动指定/无
4. 水印装饰组装：位置映射 + 颜色映射 + 不透明度
5. 创建临时文件 → `ImageProcessor.process()` → 清理输入临时文件
6. 成功：更新 `FileItem.is_processed` / `result_path` → 刷新预览 + 胶片栏缩略图 + 按钮状态
7. `StateToolTip` 进度通知（处理中 / 完成 / 失败）

**状态管理**：
- `save_config()` 窗口关闭时保存作者名 + 四项最近配置到 `ConfigManager`
- `cleanup()` 窗口关闭时清理所有文件项和临时文件
- `_on_clear_all()` 清空胶片栏 + 预览 + EXIF + 按钮状态
- 支持多文件加载（`QFileDialog.getOpenFileNames`）+ `_show_progress` 进度提示

### 🟢 相机/镜头映射管理页面

**相机映射管理**（`CameraMappingPage`）：
- 品牌筛选按钮行（Canon/Nikon/Sony/Fuji/Hasselblad/DJI/OM/Ricoh/Xiaomi/Vivo/Oppo/Huawei + 其他）
- 可编辑表格（`TableView` + 自定义模型）
- 保存到 `data/camera_map.csv`
- 手动刷新按钮 + `showEvent` 自动刷新

**镜头映射管理**（`LensMappingPage`）：
- 搜索过滤 + 可编辑表格
- 保存到 `data/lens_map.csv`
- 同步手动刷新 + 自动刷新

### 🟢 样式编辑器页面（`StyleCreatorPage`）

完成 10 个配置区块 + 实时预览 + Pivot 导航：

**架构**：
- `QSplitter` 水平分割 → 左侧配置面板 + 右侧实时预览
- 配置面板：`SmoothScrollArea` 包裹，`Pivot` 快速导航标签（点击自动滚动到对应区块）
- 10 个 `ExpandGroupSettingCard` 折叠卡片，每区块一个独立文件：
  - 基本信息、画布扩展、安全区域、原图圆角、字体、Logo、颜色、预定义文本、自定义文本、元素布局

**数据模型**（`StyleConfigFormData` `@dataclass`）：
- 替代 Streamlit 版 ~100 个 `session_state` 键
- `to_yaml_dict()` / `from_yaml_dict()` / `save_to_file()` / `clone()` 完整方法
- `ElementConfig` + `DefinedTextConfig` 子数据类
- 元素定位编辑器（`element_editor.py`）：绝对/相对定位切换，`tree_align`，margin 四边，offset 偏移

**实时预览系统**：
- 300ms `QTimer.singleShot` debounce 防抖
- `FrameRenderer.render_frame()` 直接复用，通过 `saturation_override=1.0` 关闭饱和度增强加速
- 预置 `PREVIEW_EXIF_DATA`（跳过错综的 ExifHelper 解析链路）
- `SegmentedWidget` 横图/竖图样本图切换
- 预置 Logo + 作者 + 地点（跳过 LogoSelector 匹配）
- 1200px 样本图渲染 < 200ms

**样式加载/保存/导出**：
- 样式选择器 `ComboBox` 列出已有样式文件
- 新建清空表单 → 设定 filename → 写入文件
- YAML 导出预览 `Dialog` + 只读 `TextEdit`
- `flow_style=True` 保持颜色列表流式格式

**已修复的 Bug（样式编辑器）**：
- `SegmentedWidget.currentItem()` 返回对象而非字符串
- 预览不刷新（`_on_config_changed` 未回写 UI → form_data）
- 加载样式后数据被覆盖（`_save_all_sections` 在加载期间触发）
- `margin` 统一边距字段未解析
- ElementEditor 自引用导致渲染无限循环
- 动态添加元素后卡片高度不更新（`_adjustViewSize` 未调用）
- 配置滚动面板使用 Qt 原生 `QScrollArea` 而非 `SmoothScrollArea`

### 🟢 Logo 系统增强

- **品牌独立缩放系数**（`LogoSelector.BRAND_SCALE_FACTORS`）：为特定品牌叠加缩放系数，与 `size_ratio` 和长边限制计算相乘。例如 `'hasselblad_logo': 0.6` 使哈苏 logo 缩小 40%
- **长边限制替代对角线限制**：Logo 尺寸上限从对角线系数 `2.0` 改为 `diagonal_limit_ratio` 可配置字段，默认 `2.0`，样式 YAML 中通过 `logo.diagonal_limit_ratio` 独立控制
- 样式编辑器 GUI 新增 `diagonal_limit_ratio` 输入框

### 🟢 依赖与构建

- `requirements.txt`：移除 `streamlit`，加入 `PySide6>=6.5.0`、`PySide6-Fluent-Widgets[full]>=1.11.0`、`pyinstaller>=6.0`
- `setup_env.py`：同步依赖更新
- `build_pyside.py`：**新建** PyInstaller 编译脚本（`--onedir` + 资源文件打包：CSV 映射表、YAML 样式配置、Logo PNG）
- `streamlit_app.py`：**已删除**
- `.gitignore`：添加 `dist/`、`build/`、`*.spec`

### 🧹 清理与废弃

| 项目 | 状态 |
|---|---|
| `src/gui/`（Streamlit GUI） | → `src/gui_legacy/`（已封存，原地保留可恢复） |
| `src/gui_pyside/app.py` `types.ModuleType` hack | 已删除 |
| `main.py --gui` / `--mode` 参数 | 已删除 |
| `main.py launch_gui()` / `_free_port()` 函数 | 已删除 |
| 批量处理 PySide6 页面 | 已取消（交互逻辑由胶片栏覆盖） |
| `streamlit_app.py` | 已删除 |
| `project_master_spec.json` 引用（README） | 已删除 |
| Linux/macOS 启动说明 | 已移除，标注仅 Windows 测试 |

### 📝 文档更新

- `README.md`：运行方式（默认 PySide6）、项目结构更新、GUI 界面章节重写、技术栈更新
- `AGENTS.md`：架构速览更新、入口命令更新
- `docs/GUI_REFACTORING_PLAN.md`：版本 v1.3，Streamlit 已封存，批量处理已取消
- `CHANGELOG.md`：本页更新

## v1.12.0-dev (2026-05-25)

> 内部开发版本。新增布局引擎 `alignment: "both-center"` 双轴居中模式，支持元素中心点与锚点完全重合。

### 🟢 新增 `alignment: "both-center"` 双轴居中

`LayoutEngine._get_anchor()` 新增 `alignment: "both-center"` 值，使元素在**水平和垂直方向同时**居中于锚点：

- `position='bottom'` + `alignment='both-center'`：元素整体中心与原图底部边缘中点重合
- `position='top'` + `alignment='both-center'`：元素整体中心与原图顶部边缘中点重合
- `position='left'` / `'right'` + `alignment='both-center'`：对应方向的双轴居中
- `_resolve_tree_ref()` 拦截 `both-center` → 返回 `('center', 'center')`，树级定位也支持双轴居中
- `_align_x()` / `_align_y()` / `layout_multiline_lines()` 兼容 `both-center`（等效于 `center`）

**向后兼容**：现有 `alignment: "center"` 行为完全不变，`both-center` 是新增可选值。仅影响显式配置 `both-center` 的元素。

### 🟢 `diagonal_limit_ratio` Logo 配置化

- `renderer.py:_add_logo()` 中的硬编码 `2` 抽取为样式 YAML `logo.diagonal_limit_ratio` 字段，默认 `2.0`
- 样式编辑器 GUI 新增 `diagonal_limit_ratio` 输入框（范围 1.0–5.0，步长 0.1），与 `size_ratio` / `alignment` 同行三列布局
- 4 个启用 Logo 的样式文件同步写入了 `diagonal_limit_ratio: 2.0`
- README / `_STYLE_TEMPLATE.txt` 文档同步更新

### 🟢 样式更新

- `胶片夹风格 FilmClip/default.yaml`：Logo 改为 `alignment: "both-center"`，`margin_bottom` 从 `0.04` 调整为 `0.07` 补偿视觉效果
- `胶片夹风格 FilmClip/no_custom_text.yaml`：Logo 改为 `position: "top"` + `alignment: "both-center"`，`margin_top` 从 `0.045` 调整为 `0.083` 补偿视觉效果

### 🟢 GUI & 文档

- 样式编辑器 `ALIGNMENT_OPTIONS` 新增 `both-center` 选项，所有 8 个 alignment 下拉框自动同步
- `_STYLE_TEMPLATE.txt` 中 alignment 说明补充 `both-center`
- README.md 版本徽标更新至 v1.12.0-dev
- `layout_engine.md` 更新至 v1.12.0-dev，alignment 参数表补充 `both-center`，_resolve_tree_ref 表新增 both-center 行

## v1.11.0-dev (2026-05-23)

> 内部开发版本。架构重构：将文字排版从 FrameRenderer 中拆分为独立的 TextRenderer 模块，LayoutEngine 新增多行行位计算方法。

### 🔴 架构重构：三模块拆分

**LayoutEngine** — 职责收窄为纯几何计算。新增：

- `layout_multiline_lines()` — 计算多行文本块内每行的绘制坐标（纯整数运算，不涉及字体/文本/绘制）

**TextRenderer**（`src/core/text_renderer.py`） — **新建模块**，承担原 `FrameRenderer._add_text_and_icons_flexible()` 的全部职责：

- 三源文本收集、字体加载、文本测量、颜色解析
- 拓扑排序 + 定位注册 + 绘制
- 多行绘制改调 `LayoutEngine.layout_multiline_lines()`

**FrameRenderer** — 变薄，仅保留编排层：

- 背景 → 原图圆角 → 装饰 → 文字委托 → Logo
- `_parse_color_value`、`_resolve_color_from_config`、`_determine_text_color`、`_resolve_element_order`、`_add_text_and_icons_flexible` 全部移入 TextRenderer

### 🟢 文件夹变体样式

`胶片夹风格 FilmClip` 转为文件夹变体样式：

- `default.yaml` — 含自定义文本，Logo 关闭
- `no_custom_text.yaml` — 无自定义文本，顶部替换为 Logo

变体系统现在支持多词字段名（如 `no_custom_text` → 正确解析为 `{'custom_text'}`）。

### 🧹 清理

- 移除 `custom_text` 的多行文本支持（后端 + GUI 全部改为单行输入）
- `image_processor.py`、`batch_processor.py` 样式上下文传递 `custom_text` 可用性以支持变体自动选择

### 🟢 文档更新

- README.md 版本徽标更新至 v1.11.0-dev
- `layout_engine.md` 更新至 v1.11.0-dev

## v1.10.0-dev (2026-05-21)

> 内部开发版本。重写字体加载系统，支持系统字体回退和多行混排基线统一。

### 🔴 重构：统一多行文本绘制路径

此前多行文本中的非混排行（纯拉丁）和混排行（Latin + CJK 混合）使用两套不同的公式计算 `current_y`：

- 非混排行：`current_y = y - descent`（y 作为 PIL `draw.text()` 的传入值）
- 混排行：`current_y = y + ref_ascent - ref_descent`（y 作为包围盒顶，绘制前转基线）

两套公式的基线位置不同，导致混排行和非混排行交替时行间视觉间隙不一致（偏大或偏小），表现为混排行"上移"。

**根因**：`draw.text((x, current_y), text)` 中 PIL 对 `current_y` 的解释方式与显式 `baseline_y - seg_ascent` 的计算方式不一致。

**修复**（`src/core/renderer.py`）：

- Phase 1 测量中，非混排行也生成 `seg_info`（单段），标注 `mixed: True`
- Phase 3 绘制中，删除独立的 `draw.text` 分支，所有行通入统一的 `seg_info` 循环
- `current_y` 统一使用 `y + ref_ascent - ref_descent` 初始化

### 🟢 字体系统重构

- Latin 和 CJK 字体独立配置，支持样式 YAML 中分别声明 `latin`/`cjk` 子段
- 无自定义字体时自动回退到系统预装字体（Segoe UI / Microsoft JhengHei UI）
- 样式 YAML 新增 `weights:` 映射段，显式声明三档字重（light/regular/medium）对应的具体字重字符串，`weight` 字段使用抽象值引用此映射
- CLI `--font-weight` 与 GUI 字重选择均通过此映射表解析，无需硬编码
- 系统字体多级降级回退链：`当前weight → Regular → Medium → Light → Bold`
- 旧格式 `fonts.family` + `fonts.weight` 不再支持（迁移到新格式）

### 🟢 GUI 样式编辑器

- Latin/CJK 各自由文本输入 + 字重下拉 + 系统字体复选框控制
- GUI 默认字重调整为 `Medium`

### 🐛 修复

- `segoebk.ttf` 不存在时 Latin 回退失败（改指向 `segoeui.ttf`）
- `_SYSTEM_CJK` 变量名错误（应为 `_SYSTEM_CJK_FILES`）
- CJK 系统字体后缀 `.ttf` 应为 `.ttc`（TrueType Collection）
- `style_manager.py` `_validate_config()` 默认补全旧格式导致无 `fonts` 样式的回退失效

## v1.9.0-dev (2026-05-19)

> 本版本新增**原图四角独立圆角**功能并修复多行混排基线偏移 bug。

### 🔧 工程化调整

- 新建 `src/_version.py` 作为版本单点入口；版本标记规范：公开 Release 版 `v0.x.x`，内部开发版 `v1.x.x-dev`
- `data/camera_map.csv`、`data/lens_map.csv` 纳入版本控制，作为预置数据随仓库分发
- 添加 MIT License
- 在 `launch_gui()` 中新增 `_free_port()` 函数，启动时自动释放被旧 Streamlit 实例占用的端口（仅杀命令行含 streamlit 的进程）
- `src/core/__init__.py` 的 `__version__` 改用从 `_version.py` 导入，消除双源版本号

### 🟢 原图四角独立圆角 (Corner Radius)

在渲染管线中新增原图圆角裁切步骤（位于背景填充之后、装饰/文字/Logo 层之前），通过在 RGBA 通道写入圆角蒙版实现四角透明切除。

**配置格式**（`src/frame_styles/configs/胶片夹风格 FilmClip.yaml` 已启用测试）：

```yaml
layout:
  corner_radius:
    enabled: true          # 开关，缺省视为关闭
    top_left: 0.01         # 四角独立半径系数（相对于短边比例）
    top_right: 0.01
    bottom_left: 0.01
    bottom_right: 0.01
```

- `enabled: false` 或整个字段缺失时完全跳过，零额外开销
- 所有半径系数同时为 0 时等同于禁用，不会创建蒙版

**实现细节**（`src/core/renderer.py`）：

- 新增模块级函数 `_rounded_corner_mask(w, h, r_tl, r_tr, r_bl, r_br)`，利用 **numpy SDF（signed distance field）** 在四个 r×r 角区域内计算像素到圆心的距离，通过 `np.clip(r - dist + 0.5, 0, 1)` 在圆弧边界产生 1px 线性过渡，同时间实现几何切除效果与抗锯齿软边过渡
- 在 `render_frame()` 中：检测到 `corner_radius.enabled == true` 后，将原图转为 RGBA + `putalpha(mask)`，再使用 RGBA 透明通道粘贴到背景画布
- 与 `expand_canvas`、`padding` 等现有布局参数完全兼容，四角半径与 `reference_side`（原图短边）成正比，保持响应式设计

### 🐛 修复：多行混排文本基线偏移

修复 `自定义文本 (custom_text)` 中输入中文时整体下移的问题。在多行文本的混排行绘制中，`_add_text_and_icons_flexible()` Phase 3 的基线计算重复加了 `ref_ascent`（`renderer.py:610`），导致实际基线位置比预期偏移了约一个字的高度。

**根因**：多行混排第一行的 `current_y` 已在 line 587 正确计算为基线（`y + ref_ascent - ref_descent`），但 line 610 在绘制时又加了 `line_info['ref_ascent']`，形成 `y + 2*ref_ascent - ref_descent` 的错误基线。

**修复**：将 `baseline_y = current_y + line_info['ref_ascent']` 改为 `baseline_y = current_y`，对齐单行混排的基线约定。

### 🟢 文档更新

- README.md 版本徽标更新至 v1.9.0-dev
- `layout_engine.md` 更新至 v1.9.0-dev，新增第 16 节「原图圆角裁切」，含抗锯齿算法说明
- 样式编辑器 GUI 新增 `corner_radius` 配置界面

## v1.8.0-dev (2026-05-19)

> 本版本新增**原图圆角裁切**功能。在样式配置中通过 `corner_radius` 参数即可为原始照片的四角独立裁切圆角，半径系数基于参照边（短边）响应式计算，支持独立调节每个角的弧度。

### 🟢 原图四角独立圆角 (Corner Radius)

在渲染管线中新增原图圆角裁切步骤（位于背景填充之后、装饰/文字/Logo 层之前），通过在 RGBA 通道写入圆角蒙版实现四角透明切除。

**配置格式**（`src/frame_styles/configs/胶片夹风格 FilmClip.yaml` 已启用测试）：

```yaml
layout:
  corner_radius:
    enabled: true          # 开关，缺省视为关闭
    top_left: 0.01         # 四角独立半径系数（相对于短边比例）
    top_right: 0.01
    bottom_left: 0.01
    bottom_right: 0.01
```

- `enabled: false` 或整个字段缺失时完全跳过，零额外开销
- 所有半径系数同时为 0 时等同于禁用，不会创建蒙版

**实现细节**（`src/core/renderer.py`）：

- 新增模块级函数 `_rounded_corner_mask(w, h, r_tl, r_tr, r_bl, r_br)`，利用 **numpy SDF（signed distance field）** 在四个 r×r 角区域内计算像素到圆心的距离，通过 `np.clip(r - dist + 0.5, 0, 1)` 在圆弧边界产生 1px 线性过渡，同时间实现几何切除效果与抗锯齿软边过渡
- 在 `render_frame()` 中：检测到 `corner_radius.enabled == true` 后，将原图转为 RGBA + `putalpha(mask)`，再使用 RGBA 透明通道粘贴到背景画布
- 与 `expand_canvas`、`padding` 等现有布局参数完全兼容，四角半径与 `reference_side`（原图短边）成正比，保持响应式设计

### 🟢 修复：多行混排文本基线偏移 (Bug Fix)

修复 `自定义文本 (custom_text)` 中输入中文时整体下移的问题。在多行文本的混排行绘制中，`_add_text_and_icons_flexible()` Phase 3 的基线计算重复加了 `ref_ascent`（`renderer.py:610`），导致实际基线位置比预期偏移了约一个字的高度。

**根因**：多行混排第一行的 `current_y` 已在 line 587 正确计算为基线（`y + ref_ascent - ref_descent`），但 line 610 在绘制时又加了 `line_info['ref_ascent']`，形成 `y + 2*ref_ascent - ref_descent` 的错误基线。单行混排（line 623）和单行单字体（line 619）无此问题。

**修复**：将 `baseline_y = current_y + line_info['ref_ascent']` 改为 `baseline_y = current_y`，对齐单行混排的基线约定。

### 🟢 文档更新

- README.md 版本号更新至 v1.8.0，新增 `corner_radius` 配置说明
- `layout_engine.md` 更新至 v1.8.0，新增第 16 节「原图圆角裁切」

## v1.7.0-dev (2026-05-18)

> 本版本为重大功能更新，引入**预定义文本与自定义文本系统**、**独立格式化 EXIF 字段**、**依赖树组合定位**三大新能力。从根本上解决了"多个文本块组合后整体定位"这一长期需求。同时修复相对定位中基线偏移导致的对齐偏差积弊。

### 🔴 架构级重构：依赖树组合定位 (Tree Positioning)

一直以来，元素的定位只有「自身绝对定位」和「相对于另一个元素定位」两种模式。当用户需要将多个文本块组成一条链（如 `FL 35mm Aperture f/2.8 Shutter 1/125s ISO ISO200`）并整体居中时，由于链中除根元素外均使用 `relative_to` 跟随前一个元素，根元素只能影响自身位置，整条链必然偏向一侧。

`LayoutEngine.apply_tree_positioning()` 新增 **Phase 2.5** 定位阶段（Phase 2 独立注册之后，Phase 3 绘制之前），将每棵依赖树视作整体，按根元素的 `position` / `alignment` / `margin_*` 参数对整棵树进行一次绝对定位。

**算法流程**（三步法，`src/utils/layout_engine.py`）：

1. **收集树成员**：从 `positions` 注册表 + `_dependents` 依赖图递归获取根及所有子孙
2. **计算视觉包围盒**：遍历树成员，使用注册的 `ascent` 校正基线偏移，得到 (tree_left, tree_top, tree_right, tree_bottom)
3. **平移整棵树**：
   - 调用 `_calculate_absolute(tree_w, tree_h, root_cfg)` 获取目标左上角
   - `_resolve_tree_ref(position, alignment)` 解析水平/垂直参考方向
   - `shift = target_ref - current_ref`，通过 `_shift_dependents()` 级联平移
   - 最终 padding 约束保护

**opt-in 机制**：树级组合定位仅在根元素添加显式标记 `tree_align: true` 后生效。未声明的依赖树（如原版 `exif → timestamp_author` 垂直链）完全不受影响，行为与 v1.6.3 一致。

```yaml
defined_texts:
  defined_text_01:
    content: "FL"
    position: "bottom"
    alignment: "center"
    tree_align: true       # ← 启用
    margin_bottom: 0.07
```

**设计关键**：

- `_resolve_tree_ref()` 完全对齐 `_get_anchor()` 的 14 种 position + alignment 组合行为
- 单元素树自动跳过，不影响现有所有样式配置
- 支持多条独立依赖树，互不干扰

### 🔴 架构重构：统一坐标注册 + 绘制时基线转换

此前 `renderer.py` Phase 2 在每个元素定位后做 `y -= descent` 将包围盒顶注册为基线，导致 `positions` 中的 y 坐标语义混乱。`_calculate_relative` 读取时不得不做 `ref_ascent` 校正来推测真实视觉边界；`_compute_visual_bounds` 也需做相同校正。整个系统被"基线偏移"问题长期困扰。

**根治**：取消 Phase 2 的 `y -= descent`，`positions` 统一存储包围盒顶（bounding box top）坐标。所有元素——无论文字还是非文字——遵循同一注册规则。基线偏移仅在 Phase 3 绘制时单点应用：

- `_calculate_relative()`：回归 v1.6.3 原始公式，使用最简洁的 `_align_y` + `ty + th`，累计砍掉约 30 行 ascent 校正代码
- `_compute_visual_bounds()`：回归 `y + height`，砍掉 8 行 ascent 校正
- `register_element()`：不再需要 `ascent` 参数（保留为可选，但不参与运算）
- Phase 3 绘制：单字体 `draw.text(x, y - descent)`，混排 `baseline_y = y + ref_ascent - ref_descent`
- 多行文本：第一行基线 = `y - first_line_descent` 或 `y + (ref_ascent - ref_descent)`

**净效果**：总代码减少约 40 行，positions 语义统一，`_calculate_relative` 可读性回归原始水平，所有已知样式配置视觉输出完全不变。

### 🟢 预定义文本 (defined_texts) 与自定义文本 (custom_text)

**`defined_texts`**（`src/core/renderer.py`）：

- 样式配置中写死文本内容，适合固定标签（如 "FL"、"Aperture" 等）
- Key 采用**补零编号命名**：`defined_text_01`, `defined_text_02`, ... 避免与 `info_position` 的保留 key 冲突
- 定位参数与 `info_position` 完全相同（绝对/相对定位均可），`relative_to` 可跨区域引用

**`custom_text`**：

- `layout.custom_text.enabled: true` 时，GUI 显示多行文本输入框（`st.text_area`）
- 默认内容 "Always believe that something wonderful\nis about to happen."
- 完整透传链：GUI → `ImageProcessor.process()` → `FrameRenderer.render_frame()` → `RenderContext.get_text('custom_text')`
- CLI 通过 `--custom-text` 参数传入

**三源文本统一管线**（`_add_text_and_icons_flexible`）：

- 三种文本来源使用同一 `all_positions` 注册表和 `text_elements` 列表
- 共用 Phase 1 测量 → Phase 2 拓扑排序 → Phase 2.5 树定位 → Phase 3 绘制
- 字体大小复用 `fonts.sizes.{key}`，颜色复用 `colors.custom_{key}_light/dark_color`

### 🟢 独立格式化 EXIF 字段

新增 4 个 `RenderContext.get_text()` key，将原本仅以组合字符串 `exif` 输出的焦距/光圈/快门/ISO 拆分为独立字段：

| Key                         | 格式         | 数据来源                                                        |
| --------------------------- | ------------ | --------------------------------------------------------------- |
| `focal_length_formatted`  | `"35mm"`   | `exif_data['focal_length_35mm']` → 回退 `raw_focal_length` |
| `aperture_formatted`      | `"f/2.8"`  | `raw_aperture`                                                |
| `shutter_speed_formatted` | `"1/125s"` | `raw_shutter_speed`（已由 `_format_shutter_speed` 格式化）  |
| `iso_formatted`           | `"ISO200"` | `raw_iso`                                                     |

- `exif_helper.py:373` 的 raw keys 循环补充 `'focal_length_35mm'` 字段
- 焦距优先使用 35mm 等效值，缺失时回退到物理焦距
- 支持在 `info_position` / `defined_texts` 中通过 `relative_to` 组合进链式排版

### 🟢 多行文本行间距

- `fonts.line_spacing_ratio` 新增字段（默认 `0.005`），行间距 = `reference_side * ratio`
- 可在 `custom_text` 或 `defined_texts` 元素配置中覆盖全局值
- 行间距仅在文本包含 `\n` 时生效

### 🔴 演示样式配置

新增 `扩展宝丽来风格 Polaroid Motto.yaml`，是首个展示全部 v1.7.0 新功能的示例样式：

- 用 `defined_text_01-04` + `focal_length_formatted` / `aperture_formatted` / `shutter_speed_formatted` / `iso_formatted` 组成 8 元素水平链
- 整链通过 `apply_tree_positioning()` 居中，替换原有 4 行独立 EXIF 显示
- `custom_text` 展示多行自定义文本

### 已修改文件清单

| 文件                                                            | 改动内容                                                                                                                                                |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/utils/render_context.py`                                 | 新增 `custom_text` 参数 + 4 个独立格式化 EXIF key                                                                                                     |
| `src/core/renderer.py`                                        | 三源文本收集 + 多行测量绘制 + Phase 2 移除 desc 偏移 + Phase 3 绘制时转基线 + Phase 2.5 调用                                                            |
| `src/core/image_processor.py`                                 | `process()` 透传 `custom_text`                                                                                                                      |
| `src/core/batch_processor.py`                                 | `batch_process()` 透传 `custom_text`                                                                                                                |
| `src/utils/layout_engine.py`                                  | `_calculate_relative` 回归原始公式 + `_compute_visual_bounds` 简化 + `_collect_tree_members` + `_resolve_tree_ref` + `apply_tree_positioning` |
| `src/utils/exif_helper.py`                                    | raw keys 补充 `focal_length_35mm`                                                                                                                     |
| `src/gui/image_processing_page.py`                            | 条件显示 `custom_text` 输入框                                                                                                                         |
| `src/gui/batch_processing_page.py`                            | 同上                                                                                                                                                    |
| `src/main.py`                                                 | 添加 `--custom-text` CLI 参数                                                                                                                         |
| `src/frame_styles/style_manager.py`                           | `fonts.line_spacing_ratio` 默认值                                                                                                                     |
| `src/frame_styles/configs/_STYLE_TEMPLATE.txt`                | 模板新增 defined_texts / custom_text / line_spacing_ratio                                                                                               |
| `src/frame_styles/configs/扩展宝丽来风格 Polaroid Motto.yaml` | 新建：v1.7.0 演示样式                                                                                                                                   |
| `README.md`                                                   | 文档补充                                                                                                                                                |
| `CHANGELOG.md`                                                | 更新记录                                                                                                                                                |

### 样式配置规范更新

```yaml
# 预定义文本
layout:
  defined_texts:
    defined_text_01:
      content: "FL"
      position: "bottom"            # 树级定位根
      alignment: "center"
      margin_bottom: 0.035

# 独立 EXIF 字段
info_position:
  focal_length_formatted:
    relative_to: "defined_text_01"
    relative_position: "right-of"

# 行间距
fonts:
  line_spacing_ratio: 0.008

# 自定义文本
layout:
  custom_text:
    enabled: true
    position: "bottom-center"
    alignment: "center"
    line_spacing_ratio: 0.008
```

### 向后兼容保证

- 无 `defined_texts` / `custom_text` 字段的旧配置：行为完全不变
- 单元素树（无 `relative_to` + 无子元素）：`apply_tree_positioning` 自动跳过
- `register_element.ascent` 可选参数（默认 None）：Logo / 占位锚点不受影响
- 所有现有 3 个样式配置文件通过验证

> 本版本修复非标准 EXIF 类型导致写入失败的问题，并为 debug_log 引入行数滚动机制。

### 🔴 修复：非标准 EXIF 标签类型导致写入失败

- `src/core/image_processor.py` 新增 `_try_dump_exif()` 容错式序列化函数：hook `piexif.dump()` 异常并正则解析问题标签，自动丢弃后重试，最大化保留可写入标签，而非整体放弃 EXIF 嵌入
- 修复 `exif_failed.jpg` 等由相机以非标准数据类型（SHORT 而非 UNDEFINED）写入 SceneType(0xA301) 时，`piexif.dump()` 抛出 `Got wrong type of exif value` 导致整个 EXIF 丢失的问题

### 🟢 debug_log.txt 滚动更新机制

- `src/utils/logging_config.py` 新增 `LineCountRotatingFileHandler`：继承 `logging.FileHandler`，每次写入后追踪行数，超出 1000 行时自动删除最旧记录，文件始终保持最新 1000 行
- 通过文件行数实时统计校准计数器，支持多行消息（如 traceback）计数偏差的自动修正
- 异常静默降级：滚动失败时重新统计文件行数确保计数器不漂移

## v1.6.2-dev (2026-05-16)

> 本版本修复 float32 模糊管线中 zero-padding 边界导致的画布四周发黑问题。

### 🔴 修复：float32 管线边界处理

- `src/utils/gaussian_blur.py` 中 `_box_blur_numpy()` 初始实现使用了 `np.convolve(mode='same')`，其 zero-padding 边界策略导致画布边缘像素与黑色 0 平均 → 发暗。修正为 edge-padding（`np.pad(mode='edge')` + `mode='valid'`），边界行为与 PIL `BoxBlur` 一致

## v1.6.1-dev (2026-05-16)

> 本版本统一软件名称为 MiLecFrame，新增版权信息；将高斯模糊与饱和度增强管线迁移至 float32 域运算，消除 uint8 量化误差在饱和度倍增（2×）时被放大导致的色彩断层；修复 CSV 编码异常导致设备映射失效的问题。

### 🟡 软件名称统一 & 版权信息

- `README.md`、`src/__init__.py`、`src/gui/app.py` 三处软件名称统一改为「MiLecFrame」
- `src/gui/app.py` 侧边栏标题下方新增版权信息（`st.sidebar.caption`），底部版权同步更新
- `README.md` 标题下方、`src/__init__.py` 模块 docstring 中加入版权信息
- `src/__init__.py` / `__author__` 从 "MiLeica Frame Project" 改为 "Frank Zhang"

### 🔴 重构：高斯模糊管线 float32 化

- `src/utils/gaussian_blur.py` 将 box blur 从 PIL `ImageFilter.BoxBlur`（uint8）替换为纯 numpy float32 实现（`np.convolve`），消除 3-pass blur → 饱和度 2× 过程中量化误差逐级放大的问题
- `_enhance_saturation()` 从 PIL `ImageEnhance.Color`（uint8 域）替换为 numpy 感知亮度色度缩放法（float32 域），避免饱和度倍增时的量化放大
- 保留 PIL LANCZOS 降采样用于缩小到工作尺寸（max 1200px），模糊后 LANCZOS 上采样回画布尺寸

### 🔴 修复：CSV 编码异常导致设备映射失效

- `src/utils/exif_helper.py:_record_device_info()` 消除冗余 CSV 读取，改用 `DeviceMapper` 已加载的 dict 做存在性检查，避免 CSV 编码错误导致 `extract_exif_data()` 返回 None
- `extract_exif_data()` 将 `_record_device_info()` 移出 try/except 核心块，设备信息记录失败不再影响 EXIF 提取结果
- `_get_exif_helper()` 移除 `@st.cache_resource`，确保 ExifHelper/DeviceMapper 每次 rerun 重新读取最新 CSV 映射数据
- `print()` → `logging` 统一：`exif_helper.py`、`device_mapper.py` 全部异常/信息输出纳入日志系统
- `README.md` 设备映射规范新增 UTF-8 编码警告说明，α7 → a7 示例变更，防止非 UTF-8 保存再次引发解码错误

### 🟢 侧边栏图片信息补充宽×高

- `image_processing_page.py` 侧边栏文件信息行补充 `| {width}×{height} px`，恢复原 GUI 文件信息区域中的像素尺寸显示

## v1.6.0-dev (2026-05-10)

> 本版本完全重写批量处理系统，新增 GUI 批处理页面，支持多文件上传、完整参数配置、实时进度条和结果汇总。批处理核心参数与单张处理管线完全对齐。

### 🔴 批量处理器完全重写

- `src/core/batch_processor.py` 从 112 行完全重写为 247 行，参数与 `ImageProcessor.process()` 完全对齐
- 新增 `BatchResult` 数据类：`total` / `success_count` / `fail_count` / `skip_count` / `failed_files`
- 新增 `BatchProcessor.discover_files(folder_path, recursive)` 静态方法，供 CLI/GUI 共用
- `batch_process()` 参数从 6 个扩展至 15 个，新增：
  - `output_format`（JPEG/PNG）、`decorations`（水印）、`logo_selection`（auto/none/文件名）
  - `lens_display_mode` / `use_short_lens` / `saturation_override` / `use_gps_location`
  - `progress_callback(done, total, filename, status)` — 实时进度回调接口
  - `skip_existing` — 跳过已存在输出文件（默认启用）
- Logo 自动匹配（`logo_selection='auto'`）：逐张读取 EXIF 相机品牌 → `LogoSelector.auto_match_logo()`，支持混合品牌文件夹
- GPS 替换（`use_gps_location=True`）：逐张提取 GPS DMS 坐标 → 覆盖手动输入地点，无 GPS 时回退
- 进度回调接口统一：CLI 通过 `print()` 输出进度行，GUI 通过 `st.progress()` 实时更新
- 默认 `bg_fill_type` 修正为 `BackgroundFillManager.DEFAULT_FILL`（`gaussian_black_35`），与单张处理一致

### 🟢 GUI 批量处理页面

- 新增 `src/gui/batch_processing_page.py`（658 行），侧边栏「📦 批量处理」标签页
- **文件选择**：`st.file_uploader(accept_multiple_files=True)`，支持文件夹 Ctrl+A 全选
- **文件信息提取**：上传后通过 `file_id` 集合比对检测文件变更，PIL 仅读头部获取宽高（不解码像素），`UploadedFile.size` 获取文件大小
- **文件列表展示**：三列布局（📄 文件名 | 宽×高 | 大小），无法读取文件标注 ⚠，>50 个折叠
- **配置栏**：与单张处理页面风格一致的右侧灰色配置栏，包含全部配置项：
  - ⚙️ 相框样式 / 输出格式 / 背景样式 / 字重 / 背景增强
  - 🎨 作者姓名（自动记忆） / 拍摄地点 / GPS 替换 / 镜头显示 / 短版镜头名
  - 🏷️ Logo（自动匹配 / 无 / 手动指定）
  - 💧 水印（折叠扩展区）
- **输出文件夹**：`st.text_input` + 📂 浏览按钮（tkinter 原生文件夹对话框），默认路径 `~/MiLeica_Output`
- **实时进度**：`st.progress()` + `st.empty()` 逐文件更新进度条和当前文件名
- **结果汇总**：三列统计卡片（成功/失败/跳过） + 成功率百分比 + 失败详情折叠列表
- 所有 widget key 使用 `batch_*` 前缀，与单张处理页面独立互不冲突

### 🟡 CLI 接口全面对齐（v1.6.0 后续更新）

- **单张模式 Bug 修复**：`process_image()` 补齐 `logo`、`lens_display`、`use_short_lens`、`no_enhance` 参数传递至 `ImageProcessor.process()`（此前 CLI 解析但未使用，参数设置无效）
- **单张模式新增能力**：
  - `--output-format` 输出格式选择（JPEG/PNG），扩展名自动纠正
  - `--skip-existing` 跳过已存在输出文件
  - `--watermark-text` / `--watermark-position` / `--watermark-opacity` / `--watermark-color` 水印装饰
- **批量模式补齐**：
  - `--use-gps-location` 逐张使用 GPS 坐标替换手动拍摄地点
  - `--watermark-*` 水印装饰参数对齐单张模式
- `batch_process_images()` 函数签名扩展至 17 个参数，`process_image()` 扩展至 15 个参数
- CLI 与 GUI 功能覆盖完全对齐：所有 GUI 核心处理参数均已可在 CLI 中使用

### 🟡 GUI 导航调整

- 侧边栏按钮顺序调整：🖼️ 图像处理 → 📦 批量处理 → 📸 相机映射管理 → 🔭 镜头映射管理 → 🎨 样式编辑器
- 批量处理移至图像处理下方，与用户最常用功能相邻

### 已移除

- 旧 `BatchProcessor` 的文件夹扫描模式（`input_folder` + `recursive`）：文件发现职责从 `BatchProcessor` 移至 `discover_files()` 静态方法，由调用方负责
- 批处理页面的手动文件夹路径输入模式：完全由 `file_uploader` 替代
- `main.py` CLI 旧的传参方式（仅传位置参数，如 `args.recursive`）：改为显式关键字参数

## v1.5.2-dev (2026-05-10)

> 本版本修复等效35mm焦距错误换算的严重bug：删除不可靠的裁切系数推算逻辑，改为优先读取EXIF直接提供的 `FocalLengthIn35mmFilm` 字段，无该字段时直接使用物理焦距。

### 🔴 关键修复：等效35mm焦距计算

- `extract_exif_data()` 新增读取 `FocalLengthIn35mmFilm`（Tag `0xA405`），存入 `exif_data['focal_length_35mm']`
- `format_exif_for_display()` 焦距逻辑改为：优先使用 `focal_length_35mm`（相机提供的等效值），否则直接用物理焦距 `focal_length`
- **删除** `_calculate_equivalent_focal()` 方法（原第544-586行）：裁切系数匹配逻辑存在子串匹配缺陷（`'canon'` 误匹配全画幅机型导致 `32mm → 51mm`），不再使用
- GUI 侧边栏 `raw_focal_length` 不受影响，仍显示物理焦距

### 🔴 侧边栏相机信息重复显示

- `image_processing_page.py` 侧边栏相机显示从手动拼接 `raw_camera_make + raw_camera_model` 改为直接使用映射后的 `camera_combined` 字段
- 解决相机 Model 字段已含品牌名时（如 `"Canon EOS 6D"`），Make + Model 拼接导致的品牌重复（如 `"Canon Canon EOS 6D"`）
- 如果 `camera_map.csv` 中正确配置了 `mapped_model`（如 `"EOS 6D"` 不含品牌前缀），侧边栏将显示 `"Canon EOS 6D"`

### 🟩 性能优化：GUI 缓存

- `src/gui/image_processing_page.py` 新增 8 个缓存工厂函数（`@st.cache_resource` × 4 + `@st.cache_data` × 4），跨 rerun 复用 StyleManager / ConfigManager / ExifHelper / LogoSelector 等工具类实例及样式列表、Logo 目录、背景选项等数据加载结果
- 工具类实例化从每次 rerun 创建改为首次创建后永久复用，消除文件系统扫描和 YAML 解析重复开销

### 🔴 修复：EXIF 过长导致 JPEG 保存失败

- `src/core/image_processor.py:_save_image()` 在 `piexif.dump()` 前删除 MakerNote 段（厂商私有数据块，可占用数十 KB），避免 EXIF 总大小超出 JPEG 规范 65535 字节限制
- 增加 dump 后字节数检查（> 65533 时跳过 EXIF 嵌入），兜底其他边缘 case

---

## v1.5.1-dev (2026-05-09)

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

## v1.5.0-dev (2026-05-07)

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

## v1.4.1-dev (2026-05-06)

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

## v1.4.0-dev (2026-05-04)

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

## v1.3.0-dev (2026-04-30)

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

## v1.2.0-dev (2026-04-29)

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

## v1.1.0-dev (2026-04-29)

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

## v1.0.1-dev (2026-04-10)

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

## v1.0.0-dev (早期开发)

- 项目初始化和目录结构搭建
- EXIF 处理模块、图像处理核心、相框样式管理
- GUI 界面、设备映射数据库、配置管理
- 相框渲染引擎、HDR 图像处理
- 装饰元素系统、批量处理
- 响应式设计与扩展画布
- 独立信息字体大小配置
- 背景样式运行时选择
- 错误处理改进
