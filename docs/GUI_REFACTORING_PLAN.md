# MiLecFrame GUI 重构计划

> **版本**: v1.3
> **日期**: 2026-06-09
> **框架**: PySide6 + PySide6-Fluent-Widgets[full]
> **状态**: Streamlit GUI 已封存（gui_legacy），PySide6 为默认入口；批量处理页面已取消；样式编辑器已完成

---

## 目录

1. [项目概述](#1-项目概述)
2. [技术栈与依赖](#2-技术栈与依赖)
3. [原 GUI 功能逻辑总结](#3-原-gui-功能逻辑总结)
4. [重构架构设计](#4-重构架构设计)
5. [图像处理页面详细设计](#5-图像处理页面详细设计)
6. [样式编辑器页面重构方案](#6-样式编辑器页面重构方案样式编辑--实时预览)
7. [QFluentWidgets 组件映射表](#7-qfluentwidgets-组件映射表)
8. [数据模型设计](#8-数据模型设计)
9. [内存与缓存管理](#9-内存与缓存管理)
10. [文件目录结构](#10-文件目录结构)
11. [实施步骤](#11-实施步骤)
12. [开发进度记录](#12-开发进度记录2026-06-04)

---

## 1. 项目概述

### 1.1 重构目标

将 MiLecFrame 的 GUI 从 Streamlit Web 界面迁移到 PySide6 原生桌面应用，全面使用 QFluentWidgets 框架组件，实现 Fluent Design 风格的现代化界面。

### 1.2 核心原则

- **全面使用 QFluentWidgets 组件**：禁止使用任何 Qt 原生界面组件（如 QPushButton、QComboBox 等），所有交互控件必须来自 `qfluentwidgets` 模块
- **保留原有 Streamlit GUI**：Streamlit 模式作为备选保留，双入口并存
- **复用核心处理层**：ImageProcessor、BatchProcessor、StyleManager、ExifHelper、BackgroundFillManager 等核心模块不做任何修改
- **内存安全**：关闭窗口时自动清理所有缓存和临时文件

### 1.3 用户需求摘要

| 序号 | 需求                                            | 状态   |
| ---- | ----------------------------------------------- | ------ |
| 1    | 胶片栏位于页面底部（非顶部）                    | 已确认 |
| 2    | 主入口模式选择使用交互对话框                    | 已确认 |
| 3    | 全面使用 QFluentWidgets 组件，禁用 Qt 原生组件  | 已确认 |
| 4    | 使用 PySide6（非 PyQt6）                        | 已确认 |
| 5    | FluentUI SVG 图标                               | 已确认 |
| 6    | 默认窗口尺寸 1600×900                          | 已确认 |
| 7    | 先完成框架搭建 + 图像处理页面，其余页面后续开发 | 已确认 |

---

## 2. 技术栈与依赖

### 2.1 安装命令

```bash
# 激活虚拟环境
.\venv\Scripts\activate

# 安装 PySide6-Fluent-Widgets 完整版（如网络受限可使用本地代理）
pip install "PySide6-Fluent-Widgets[full]" -i https://pypi.org/simple/

# 备选：使用本地代理
pip install "PySide6-Fluent-Widgets[full]" -i https://pypi.org/simple/ --proxy http://127.0.0.1:7897
```

### 2.2 版本要求

| 依赖                   | 最低版本  | 说明                           |
| ---------------------- | --------- | ------------------------------ |
| PySide6                | ≥ 6.5.0  | Qt6 绑定                       |
| PySide6-Fluent-Widgets | ≥ 1.11.0 | Fluent Design 组件库（完整版） |
| Pillow                 | ≥ 9.0.0  | 图像处理（已有）               |
| piexif                 | ≥ 1.1.3  | EXIF 处理（已有）              |
| numpy                  | ≥ 1.21.0 | 数值计算（已有）               |
| PyYAML                 | ≥ 6.0    | YAML 解析（已有）              |

### 2.3 冲突警告

> **绝对不要同时安装** PyQt-Fluent-Widgets、PyQt6-Fluent-Widgets、PySide2-Fluent-Widgets 和 PySide6-Fluent-Widgets，因为它们的包名都是 `qfluentwidgets`，会互相冲突。

---

## 3. 原 GUI 功能逻辑总结

### 3.1 整体架构

原 GUI 基于 Streamlit 框架，采用 Web 界面模式运行。主入口 `src/gui/app.py` 通过 `st.set_page_config()` 配置页面，使用侧边栏按钮进行 5 个页面的导航切换，通过 `st.session_state` 管理全局状态。

**启动方式**：

- `streamlit run src/gui/app.py`
- `python src/main.py --gui`（subprocess 封装）

### 3.2 页面组成

```
src/gui/
  app.py                      ← 主入口：侧边栏导航 + 页面路由（115行）
  image_processing_page.py    ← 单张图片处理（593行，核心页面）
  batch_processing_page.py    ← 批量处理（719行）
  camera_mapping_page.py      ← 相机映射管理（135行）
  lens_mapping_page.py        ← 镜头映射管理（65行）
  style_creator_page.py       ← 样式编辑器（1257行，最复杂）
```

### 3.3 图像处理页面（image_processing_page.py）详细逻辑

#### 3.3.1 页面布局

- **主布局**：左右两栏 `st.columns([7, 3])`
  - 左侧（70%）：文件上传器 + 原图预览 + 效果预览
  - 右侧（30%）：配置栏（灰色背景 + 圆角）

#### 3.3.2 缓存工厂函数

每个页面独立定义了以下缓存函数（存在代码重复）：

| 函数                           | 缓存类型               | TTL  | 用途                         |
| ------------------------------ | ---------------------- | ---- | ---------------------------- |
| `_get_style_manager()`       | `@st.cache_resource` | -    | 单例 StyleManager            |
| `_get_config_manager()`      | `@st.cache_resource` | -    | 单例 ConfigManager           |
| `_get_exif_helper()`         | 无缓存                 | -    | ExifHelper（需读取最新 CSV） |
| `_get_logo_selector()`       | `@st.cache_resource` | -    | 单例 LogoSelector            |
| `_get_available_styles()`    | `@st.cache_data`     | 60s  | 可用样式列表                 |
| `_get_bg_fill_choices()`     | `@st.cache_data`     | 300s | 背景填充选项                 |
| `_get_cached_style_config()` | `@st.cache_data`     | 60s  | 样式配置                     |
| `_scan_logos()`              | `@st.cache_data`     | 60s  | Logo 文件列表                |

#### 3.3.3 Session State 变量

| Key                   | 类型         | 用途                             |
| --------------------- | ------------ | -------------------------------- |
| `current_page`      | str          | 当前页面标识                     |
| `processing_result` | str          | 处理结果文件路径                 |
| `temp_input_path`   | str          | 临时输入文件路径                 |
| `temp_output_path`  | str          | 临时输出文件路径                 |
| `button_clicked`    | bool         | 按钮点击状态                     |
| `current_config`    | dict         | 当前配置快照（用于变更检测）     |
| `exif_data`         | dict         | 提取的 EXIF 数据                 |
| `display_data`      | dict         | 格式化后的显示数据               |
| `file_info`         | dict         | 文件元数据（格式/色彩空间/尺寸） |
| `file_uploader`     | UploadedFile | 上传的文件对象                   |

#### 3.3.4 处理流程

1. 用户上传图片 → 提取 EXIF 数据 → 侧边栏显示图片信息
2. 用户配置选项（样式/背景/字重/作者/地点/Logo/水印等）
3. 点击"生成相框"按钮 → 收集所有配置参数
4. 创建临时输入文件 → 调用 `ImageProcessor.process()`
5. 成功 → 保存临时输出文件 → 显示效果预览 + 下载按钮
7. 配置变更检测：比较当前配置快照与上次，自动切换按钮为"重新生成"

#### 3.3.5 配置面板内容（从上到下）

1. **按钮区**：生成/重新生成按钮（颜色随状态变化：绿色=生成，红色=重新生成）
2. **⚙️ 配置**：
   - 相框样式（selectbox，默认"底部信息条 Bottom Bars"）
   - 输出格式（selectbox：JPEG/PNG）
   - 背景样式（selectbox，从 BackgroundFillManager.get_choices() 获取）
   - 字重（selectbox：细体/常规/中等）
   - 背景增强（checkbox，仅高斯模糊背景时启用）
3. **🎨 装饰**：
   - 作者姓名（text_input，自动保存到 config.json）
   - 拍摄地点（text_input）+ GPS 替换（checkbox）
   - 镜头显示（selectbox：相机+镜头/只显示相机/只显示镜头）
   - 短版镜头名（checkbox）
4. **✏️ 自定义文本**（仅当样式配置 `custom_text.enabled=true` 时显示）
5. **🏷️ Logo**：
   - 自动匹配/无/手动选择（selectbox）
   - 无样式 Logo 支持时显示提示
7. **💧 水印**（可折叠 expander，默认收起）：
   - 启用水印（checkbox）
   - 内容（text_input）
   - 位置（selectbox：6 种位置）
   - 不透明度（slider：0-100%）
   - 颜色（selectbox：白色/黑色）

#### 3.3.6 预览逻辑

- 横向图片（w > h）：上下排列，缩至 75% 宽度居中
- 竖向/方形图片：左右排列
- 处理完成后生成 1200px 缩略图用于预览

### 3.4 批量处理页面（batch_processing_page.py）详细逻辑

#### 3.4.1 与单张处理的差异

- 多文件上传器（`accept_multiple_files=True`）
- 文件列表显示（HTML 渲染：文件名/尺寸/大小）
- 输出文件夹选择（含 tkinter 原生文件夹对话框）
- 进度条 + 实时状态显示
- 结果统计（成功/失败/跳过数量）

#### 3.4.2 特有 Session State 变量

| Key                     | 类型               | 用途                         |
| ----------------------- | ------------------ | ---------------------------- |
| `batch_output_folder` | str                | 输出文件夹路径               |
| `batch_scanned_files` | List[UploadedFile] | 已扫描的文件列表             |
| `batch_file_infos`    | List[dict]         | 文件信息列表                 |
| `batch_file_ids`      | set                | 文件 ID 集合（用于变更检测） |
| `batch_result`        | BatchResult        | 批量处理结果                 |

#### 3.4.3 处理流程

1. 用户选择多张图片 → 提取文件信息（尺寸/大小）
2. 配置选项（与单张处理几乎相同，key 加 `batch_` 前缀）
3. 选择输出文件夹
4. 点击"开始批量处理" → `_execute_batch_processing()`
5. 逐张调用 `BatchProcessor.batch_process()` + 进度回调
7. 显示结果汇总

### 3.5 相机映射管理页面（camera_mapping_page.py）

- 品牌筛选按钮行（Canon/Nikon/Sony/Fuji/Hasselblad/DJI/OM/Ricoh/Xiaomi/Vivo/Oppo/Huawei + 其它）
- `st.data_editor` 可编辑表格
- 保存到 `data/camera_map.csv`

### 3.6 镜头映射管理页面（lens_mapping_page.py）

- 搜索框 + `st.data_editor` 可编辑表格
- 保存到 `data/lens_map.csv`

### 3.7 样式编辑器页面（style_creator_page.py）

- 可视化 YAML 配置创建器
- 表单区块：基本信息 → 画布扩展 → 安全区域 → 圆角 → 字体 → Logo → 颜色 → 预定义文本 → 自定义文本 → 元素布局
- 加载/新建/保存 YAML 配置文件
- 大量 `st.session_state` 管理表单状态（`sc_` 前缀）

### 3.8 核心依赖模块（不修改）

| 模块                  | 路径                                  | 职责                    |
| --------------------- | ------------------------------------- | ----------------------- |
| ImageProcessor        | `src/core/image_processor.py`       | 单张图像处理主逻辑      |
| BatchProcessor        | `src/core/batch_processor.py`       | 批量处理包装            |
| FrameRenderer         | `src/core/renderer.py`              | 渲染引擎                |
| Decorator             | `src/core/decorator.py`             | 装饰元素（水印）        |
| StyleManager          | `src/frame_styles/style_manager.py` | 样式配置加载 + 变体匹配 |
| ExifHelper            | `src/utils/exif_helper.py`          | EXIF 提取与格式化       |
| DeviceMapper          | `src/utils/device_mapper.py`        | 设备映射数据库          |
| ConfigManager         | `src/utils/config_manager.py`       | 用户偏好持久化          |
| BackgroundFillManager | `src/utils/background_fill.py`      | 背景填充类型注册表      |
| LogoSelector          | `src/utils/logo_selector.py`        | Logo 扫描与自动匹配     |
| RenderContext         | `src/utils/render_context.py`       | 渲染文本数据统一入口    |

---

## 4. 重构架构设计

### 4.1 单入口设计（已更新）

`src/main.py` 为唯一入口，默认启动 PySide6 桌面 GUI。无参数时：

```python
if not args.input and not args.output and not args.batch and not args.recursive:
    launch_pyside_gui()
```

旧版 Streamlit Web GUI 已封存至 `src/gui_legacy/`，不再参与构建和自动导入。

### 4.2 主窗口架构

```
FluentWindow (src/gui_pyside/main_window.py)
├── NavigationInterface
│   ├── NavigationPushButton: 🖼️ 图像处理
│   ├── NavigationPushButton: 📸 相机映射管理
│   ├── NavigationPushButton: 🔭 镜头映射管理
│   └── NavigationPushButton: 🎨 样式编辑器
├── QStackedWidget
│   ├── ImageProcessingPage
│   ├── CameraMappingPage
│   ├── LensMappingPage
│   └── StyleCreatorPage
└── StatusBar
```

### 4.3 模块职责划分

```
src/gui_pyside/
├── app.py                          ← PySide6 应用入口（QApplication 初始化、主题设置）
├── main_window.py                  ← FluentWindow 主窗口 + 导航注册 + closeEvent
│
├── models/                         ← 数据模型层（与 UI 无关）
│   ├── file_item.py                ← 单个图片文件的数据模型
│   └── processing_config.py        ← 处理配置模型
│
├── pages/                          ← 页面容器（布局组装，不含具体 Widget 实现）
│   ├── image_processing_page.py    ← 图像处理页面主容器
│   ├── camera_mapping_page.py      ← 相机映射管理（后续）
│   ├── lens_mapping_page.py        ← 镜头映射管理（后续）
│   └── style_creator_page.py       ← 样式编辑器（后续）
│
├── widgets/                        ← 可复用 Widget 组件
│   ├── filmstrip.py                ← 胶片栏（底部横向缩略图列表）
│   ├── image_preview.py            ← 预览窗口（原图/效果图切换显示）
│   ├── accordion_panel.py          ← 手风琴式配置面板容器
│   ├── output_settings_tab.py      ← Tab 1: 输出设置
│   ├── frame_config_tab.py         ← Tab 2: 相框配置
│   ├── personalization_tab.py      ← Tab 3: 个性化配置
│   ├── shot_info_tab.py            ← Tab 4: 拍摄信息配置
│   ├── watermark_tab.py            ← Tab 5: 文本水印
│   └── exif_info_panel.py          ← EXIF 信息显示面板
│
├── utils/                          ← 工具层
│   └── temp_manager.py             ← 临时文件生命周期管理
│
└── resources/
    └── icons/                      ← FluentUI SVG 图标
```

---

## 5. 图像处理页面详细设计

### 5.1 页面布局

```
┌─────────────────────────────────────────────────────────────────────┐
│  ┌─── 主内容区 ──────────────────────┬─── 配置栏 ───────────────┐  │
│  │                                   │                           │  │
│  │   ┌─── 预览窗口 ──────────────┐   │  ╔══ 输出设置 ══════════╗ │  │
│  │   │                           │   │  ║  输出格式 [JPEG ▼]   ║ │  │
│  │   │   原图 / 效果预览         │   │  ╚══════════════════════╝ │  │
│  │   │   (单图显示，加载时       │   │  ╔══ 相框配置 ══════════╗ │  │
│  │   │    为原图，处理后         │   │  ║  相框样式 [▼]        ║ │  │
│  │   │    切换为效果图)          │   │  ║  背景填充 [▼]        ║ │  │
│  │   │                           │   │  ║  背景增强 [✓]        ║ │  │
│  │   │   缩放到横向 3000px       │   │  ║  字重 [▼]            ║ │  │
│  │   └───────────────────────────┘   │  ╚══════════════════════╝ │  │
│  │                                   │  ╔══ 个性化配置 ════════╗ │  │
│  │   ┌─── EXIF 信息面板 ─────────┐   │  ║  作者姓名 [______]   ║ │  │
│  │   │ 文件: JPEG | sRGB | ...   │   │  ║  拍摄地点 [______]   ║ │  │
│  │   │ 相机: Leica Q3            │   │  ║  GPS替换 [✓]         ║ │  │
│  │   │ 镜头: Summilux 28mm       │   │  ║  自定义文本 [___]    ║ │  │
│  │   │ 焦距: 28mm 光圈: f/1.7    │   │  ╚══════════════════════╝ │  │
│  │   │ 快门: 1/125s ISO: 200     │   │  ╔══ 拍摄信息配置 ══════╗ │  │
│  │   │ 时间: 2025.01.15          │   │  ║  镜头显示 [▼]        ║ │  │
│  │   └───────────────────────────┘   │  ║  短版镜头名 [✓]      ║ │  │
│  │                                   │  ║  LOGO [▼]            ║ │  │
│  │   ┌─── 操作按钮 ─────────────┐   │  ╚══════════════════════╝ │  │
│  │   │ [导出当前图像]           │   │  ╔══ 文本水印 ══════════╗ │  │
│  │   │ [一键导出所有] [清空所有] │   │  ║  启用水印 [✓]        ║ │  │
│  │   └───────────────────────────┘   │  ║  内容 [________]     ║ │  │
│  │                                   │  ║  位置 [▼] 不透明度   ║ │  │
│  └───────────────────────────────────┴──╚══════════════════════╝ ┘  │
│                                                                     │
│  ┌─── 胶片栏 (FilmStrip) ──────────────────────────────────────┐  │
│  │ [img1] [img2] [img3] [img4] [img5] ...     (横向滚动)       │  │
│  │  等比缩略图 | 选中高亮 | 已处理显示效果图缩略图              │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 胶片栏（FilmStrip）设计

**位置**：页面底部，横向排列

**功能**：

- 显示所有已加载图片的等比缩略图（高度固定 100px，宽度等比）
- 支持多文件加载（单文件模式下也可加载多个）
- 点击缩略图切换预览窗口显示对应图片
- 三种状态指示：
  - 未处理：普通灰色边框
  - 已选中：蓝色高亮边框
  - 已处理：绿色边框 + 缩略图替换为效果图
- 支持键盘 Delete 删除选中项
- 支持鼠标滚轮横向滚动

**QFluentWidgets 组件**：

- 容器：`QScrollArea`（Qt 原生，但仅作为滚动容器，不显示任何视觉样式）
- 缩略图项：自定义 `ThumbnailWidget`（继承 `QWidget`，内部使用 `QLabel` 显示图片 + `QLabel` 显示文件名）

> **注意**：QFluentWidgets 没有提供现成的胶片栏/缩略图列表组件，需要基于 `QWidget` + `QHBoxLayout` 自定义实现。这是少数需要自定义绘制的组件之一，但其视觉风格（边框颜色、圆角等）仍遵循 Fluent Design 规范。

### 5.3 预览窗口设计

**功能**：

- 单图显示模式（非分栏）
- 加载图片时显示原图
- 生成相框后自动切换为效果图
- 缩放到横向 3000px 以内以提升性能
- 保持原始宽高比

**QFluentWidgets 组件**：

- 基于 `ImageLabel`（QFluentWidgets 提供）或自定义 `QLabel`
- 外层包裹 `ScrollArea` 支持大图滚动查看

### 5.4 手风琴式配置面板设计

**结构**：5 个折叠区块，使用 QFluentWidgets 的 `ExpandSettingCard` 或 `ExpandGroupSettingCard`

**所有配置选项始终保持可见**，但根据当前样式配置动态控制可编辑状态：

#### Tab 1: 输出设置（OutputSettingsTab）

| 控件     | QFluentWidgets 组件 | 始终可用 |
| -------- | ------------------- | -------- |
| 输出格式 | `ComboBox`        | ✅       |

#### Tab 2: 相框配置（FrameConfigTab）

| 控件         | QFluentWidgets 组件 | 条件                           |
| ------------ | ------------------- | ------------------------------ |
| 相框样式     | `ComboBox`        | ✅ 始终可用                    |
| 背景填充样式 | `ComboBox`        | ✅ 始终可用                    |
| 背景增强     | `CheckBox`        | 仅当背景类型为 gaussian 时启用 |
| 字重         | `ComboBox`        | ✅ 始终可用                    |

#### Tab 3: 个性化配置（PersonalizationTab）

| 控件       | QFluentWidgets 组件 | 条件                                            |
| ---------- | ------------------- | ----------------------------------------------- |
| 作者姓名   | `LineEdit`        | ✅ 始终可用                                     |
| 拍摄地点   | `LineEdit`        | ✅ 始终可用                                     |
| GPS 替换   | `CheckBox`        | 仅当 EXIF 含 GPS 数据时启用                     |
| 自定义文本 | `PlainTextEdit`   | 仅当 `layout.custom_text.enabled=true` 时显示 |

#### Tab 4: 拍摄信息配置（ShotInfoTab）

| 控件       | QFluentWidgets 组件 | 条件                                                  |
| ---------- | ------------------- | ----------------------------------------------------- |
| 镜头显示   | `ComboBox`        | ✅ 始终可用                                           |
| 短版镜头名 | `CheckBox`        | ✅ 始终可用                                           |
| LOGO 选择  | `ComboBox`        | 仅当 `logo.enabled=true` 时显示下拉框               |
| LOGO 提示  | `InfoLabel`       | 当 `logo.enabled=false` 时显示"当前样式未启用 Logo" |

#### Tab 5: 文本水印（WatermarkTab）

| 控件     | QFluentWidgets 组件         | 始终可用         |
| -------- | --------------------------- | ---------------- |
| 启用水印 | `CheckBox`                | ✅               |
| 内容     | `LineEdit`                | 仅当启用时可编辑 |
| 位置     | `ComboBox`                | 仅当启用时可编辑 |
| 不透明度 | `Slider` + `ValueLabel` | 仅当启用时可编辑 |
| 颜色     | `ComboBox`                | 仅当启用时可编辑 |

### 5.5 操作按钮设计

使用 QFluentWidgets 的 `PrimaryPushButton`：

| 按钮         | 功能                     | 条件               |
| ------------ | ------------------------ | ------------------ |
| 导出当前图像 | 处理当前选中的单张图片   | 有图片选中时启用   |
| 一键导出所有 | 批量处理胶片栏中所有图片 | 有未处理图片时启用 |
| 清空所有     | 清空胶片栏中所有图片     | 有图片时启用       |

### 5.6 样式配置选项动态控制逻辑

```python
def _update_config_controls(self, style_name: str):
    """根据当前样式配置更新所有控件的可编辑状态"""
    config = self.style_manager.get_style_config(style_name)
    if not config:
        return

    layout = config.get('layout', {})
    info_position = layout.get('info_position', {})
    logo_config = config.get('logo', {})
    custom_text_config = layout.get('custom_text', {})

    # 自定义文本：仅当样式声明 enabled=true 时显示
    ct_enabled = isinstance(custom_text_config, dict) and custom_text_config.get('enabled', False)
    self.personalization_tab.set_custom_text_visible(ct_enabled)

    # LOGO：仅当样式声明 enabled=true 时显示下拉框
    logo_enabled = isinstance(logo_config, dict) and logo_config.get('enabled', False)
    self.shot_info_tab.set_logo_selector_enabled(logo_enabled)

    # 背景增强：仅当高斯模糊背景时启用
    bg_key = self.frame_config_tab.get_bg_fill_type()
    bg_cfg = BackgroundFillManager.FILL_TYPES.get(bg_key, {})
    is_gaussian = bg_cfg.get('method') == 'gaussian'
    self.frame_config_tab.set_enhance_enabled(is_gaussian)
```

### 5.7 RenderContext 支持的完整 key 列表

用于配置面板中各选项的逻辑判断：

| key                         | 类型           | GUI 控件关联         |
| --------------------------- | -------------- | -------------------- |
| `exif`                    | 格式化曝光参数 | 信息显示             |
| `timestamp`               | 拍摄时间       | 信息显示             |
| `timestamp_author`        | 时间 + 作者    | 信息显示             |
| `camera_lens`             | 相机+镜头组合  | 镜头显示模式控制     |
| `camera`                  | 相机品牌+型号  | 信息显示             |
| `camera_make`             | 映射后品牌     | Logo 自动匹配        |
| `lens`                    | 镜头型号       | 短版镜头名控制       |
| `author`                  | 作者姓名       | 用户输入             |
| `location`                | 拍摄地点       | 用户输入             |
| `gps`                     | GPS 坐标       | GPS 替换控制         |
| `custom_text`             | 自定义文本     | 用户输入（条件显示） |
| `focal_length_formatted`  | 格式化焦距     | 信息显示             |
| `aperture_formatted`      | 格式化光圈     | 信息显示             |
| `shutter_speed_formatted` | 格式化快门     | 信息显示             |
| `iso_formatted`           | 格式化 ISO     | 信息显示             |

---

## 6. 样式编辑器页面重构方案（样式编辑 + 实时预览）

> **版本**: v1.0
> **日期**: 2026-06-06
> **状态**: 规划完成，待实施
> **原版规模**: `src/gui/style_creator_page.py`（1257 行，Streamlit）

### 6.1 概述与目标

将 Streamlit 样式编辑器迁移到 PySide6，并新增**实时样式预览**功能。

| 需求 | 说明 |
|------|------|
| 功能迁移 | 完整迁移原版 10 个配置区块，补齐 Streamlit 遗漏的 `corner_radius` |
| 实时预览 | 右侧预览窗随左侧配置实时刷新，提供横/竖两种样本图切换 |
| 性能 | 1200px 样本图，300ms debounce 防抖，复用 `FrameRenderer.render_frame()` |
| 核心原则 | 不修改 `FrameRenderer` / `BackgroundFillManager` 等核心模块 |

### 6.2 页面布局

```
┌── QSplitter (水平) ───────────────────────────────────────────────────┐
│ ┌── 左侧: 配置面板 ────────────┐  ┌── 右侧: 预览面板 ────────────┐  │
│ │ ┌── Pivot 快速导航 ────────┐  │  │  ┌────────────────────────┐  │  │
│ │ │ [基本][画布][安全][圆角]  │  │  │  │                        │  │  │
│ │ │ [字体][Logo][颜色][预定义]│  │  │  │  样式预览窗口          │  │  │
│ │ │ [自定][元素]              │  │  │  │  (QLabel + QPixmap)    │  │  │
│ │ └──────────────────────────┘  │  │  │                        │  │  │
│ │ ┌── ScrollArea ────────────┐  │  │  │                        │  │  │
│ │ │ ╔══ 基本信息 ═════════╗  │  │  │  │                        │  │  │
│ │ │ ║ 样式名称 [______]    ║  │  │  │  │                        │  │  │
│ │ │ ║ 文件名   [______]    ║  │  │  │  │                        │  │  │
│ │ │ ╚══════════════════════╝  │  │  │  │                        │  │  │
│ │ │ ╔══ 画布扩展 ═════════╗  │  │  │  └────────────────────────┘  │  │
│ │ │ ║ [Switch] 启用        ║  │  │  │  [ 横图预览 ][ 竖图预览 ]  │  │
│ │ │ ║ top [0.03] bot [0.12]║  │  │  │    SegmentedWidget          │  │
│ │ │ ╚══════════════════════╝  │  │  └────────────────────────────┘  │  │
│ │ │ ... 更多 ExpandGroupSettingCard │                                │  │
│ │ └──────────────────────────┘  │                                │  │
│ └───────────────────────────────┘                                │  │
└──────────────────────────────────────────────────────────────────────┘
```

- **快速导航**：配置面板顶部使用 `Pivot`，每个标签对应一个配置区块。点击后 `ScrollArea` 自动滚动到对应的 `ExpandGroupSettingCard`。
- **配置面板**：`ScrollArea` 包裹，10 个配置区块使用 `ExpandGroupSettingCard` 折叠卡片。
- **预览面板**：`SegmentedWidget`（横图/竖图切换）在上，`QLabel`（QPixmap 显示）在下占用剩余空间。
- **顶栏**：样式选择 `ComboBox` + 新建/保存/导出 YAML 按钮。

### 6.3 QFluentWidgets 组件映射表（样式编辑器特有）

| Streamlit 组件 | QFluentWidgets 组件 | 用途 |
|---|---|---|
| `st.text_input` | `LineEdit` | 样式名称、文件名、字体 family、颜色值输入 |
| `st.number_input` (float) | `SpinBox` + `setDecimals(3)` + `setSingleStep(0.005)` | 画布扩展比例、padding、圆角半径、margin、字体 size |
| `st.selectbox` | `ComboBox` | 字重、placement、position、alignment、relative_position 等枚举 |
| `st.checkbox` | `SwitchButton` | 所有布尔开关（启用画布、启用 Logo、系统字体等） |
| `st.radio` (绝对/相对) | `SegmentedWidget`（2 项） | 定位方式切换、横/竖预览切换 |
| `st.expander` | `ExpandGroupSettingCard` | 每个配置章节的折叠卡片（10 个） |
| `st.button` (添加元素) | `PrimaryPushButton` / `PushButton` | 新建、保存、添加元素、导出 YAML |
| `st.code` (YAML 预览) | `Dialog` + `TextEdit`（只读） | YAML 导出预览弹窗 |
| `st.columns` (多列) | `QHBoxLayout` / `QGridLayout` | 多列排列多个 SpinBox / LineEdit |
| 新增 | `Pivot` | 配置面板顶部快速导航标签 |
| 新增 | `ScrollArea` | 配置面板滚动容器 |
| 新增 | `QSplitter` | 左（配置）右（预览）分割 |
| `st.selectbox` (样式选择) | `ComboBox` + 可搜索 | 顶部现有样式文件选择器 |

**颜色输入的"实时色块预览"**：
- 颜色字段使用 `LineEdit`，右侧添加一个 `QWidget` 色块显示解析后的颜色
- 色块通过 `setStyleSheet("background-color: rgb(r,g,b)")` 实时更新
- 输入为 `#RRGGBB` 或 `[r,g,b]` 格式，实时解析

### 6.4 数据模型

#### 12.4.1 StyleConfigFormData

替代 Streamlit 的 ~100 个 `session_state` 键（`sc_` 前缀），用一个 `@dataclass` 集中管理：

```python
@dataclass
class StyleConfigFormData:
    """样式编辑器表单数据模型"""

    # ── 基本信息 ──
    name: str = ""
    filename: str = ""

    # ── 画布扩展 ──
    canvas_enabled: bool = True
    canvas_top: float = 0.03
    canvas_bottom: float = 0.12
    canvas_left: float = 0.02
    canvas_right: float = 0.02

    # ── 安全区域 ──
    pad_top: float = 0.02
    pad_bottom: float = 0.02
    pad_left: float = 0.02
    pad_right: float = 0.02

    # ── 圆角（原 Streamlit 版遗漏，新版补齐） ──
    cr_enabled: bool = False
    cr_tl: float = 0.01
    cr_tr: float = 0.01
    cr_bl: float = 0.01
    cr_br: float = 0.01

    # ── 字体 ──
    font_latin_family: str = ""
    font_latin_weight: str = "medium"
    font_latin_system: bool = False
    font_cjk_family: str = ""
    font_cjk_weight: str = "medium"
    font_cjk_system: bool = False
    font_size_ratio: float = 0.015
    font_line_spacing: float = 0.005
    font_sizes: dict = field(default_factory=dict)     # {key: float}

    # ── Logo ──
    logo_enabled: bool = False
    logo_mode: str = "absolute"                        # "absolute" / "relative"
    logo_placement: str = "outside"
    logo_position: str = "top-right"
    logo_alignment: str = "top-right"
    logo_size_ratio: float = 0.04
    logo_diagonal_limit: float = 2.0
    logo_mt: float = 0.0; logo_mb: float = 0.0
    logo_ml: float = 0.0; logo_mr: float = 0.0
    logo_relative_to: str = ""
    logo_relative_position: str = "below"
    logo_relative_margin: float = 0.01
    logo_offset_x: float = 0.0; logo_offset_y: float = 0.0

    # ── 颜色 ──
    color_light: str = ""
    color_dark: str = ""
    color_per_element: dict = field(default_factory=dict)  # {key: {light: str, dark: str}}

    # ── 元素布局 ──
    elements: list = field(default_factory=list)          # List[ElementConfig]
    defined_texts: list = field(default_factory=list)     # List[DefinedTextConfig]

    # ── 自定义文本 ──
    custom_text_enabled: bool = False
    custom_text_mode: str = "absolute"
    custom_text_placement: str = "outside"
    custom_text_position: str = "bottom-center"
    custom_text_alignment: str = "center"
    custom_text_mt: float = 0.0; custom_text_mb: float = 0.0
    custom_text_ml: float = 0.0; custom_text_mr: float = 0.0
    custom_text_relative_to: str = ""
    custom_text_relative_position: str = "below"
    custom_text_relative_margin: float = 0.01
    custom_text_offset_x: float = 0.0
    custom_text_offset_y: float = 0.0
    custom_text_line_spacing: float = 0.005
```

#### 12.4.2 核心方法

```python
def to_yaml_dict(self) -> dict:
    """将表单数据转换为 YAML 配置字典（复用 Streamlit 版 _collect_config 逻辑）"""

def from_yaml_dict(self, data: dict):
    """从 YAML 字典加载到表单（复用 Streamlit 版 _load_existing_style 逻辑）"""

def save_to_file(self, filepath: str) -> str:
    """序列化为 YAML 字符串并写入文件，返回 YAML 字符串"""

def clone(self) -> 'StyleConfigFormData':
    """深拷贝，用于变更检测"""
```

#### 12.4.3 元素 / 预定义文本子模型

```python
@dataclass
class ElementConfig:
    """单个 info_position 元素的配置"""
    id: int = 0
    key: str = "exif"
    mode: str = "absolute"        # "absolute" / "relative"
    placement: str = "outside"
    position: str = "bottom-left"
    alignment: str = "left"
    margin_top: float = 0.0; margin_bottom: float = 0.02
    margin_left: float = 0.0; margin_right: float = 0.0
    relative_to: str = "exif"
    relative_position: str = "below"
    relative_margin: float = 0.01
    offset_x: float = 0.0; offset_y: float = 0.0
    tree_align: bool = False

@dataclass
class DefinedTextConfig:
    """单个预定义文本条目"""
    id: int = 0
    key: str = ""
    content: str = ""
    mode: str = "absolute"
    tree_align: bool = False
    placement: str = "outside"
    position: str = "bottom-left"
    alignment: str = "left"
    margin_top: float = 0.0; margin_bottom: float = 0.0
    margin_left: float = 0.0; margin_right: float = 0.0
    relative_to: str = "exif"
    relative_position: str = "right-of"
    relative_margin: float = 0.01
    offset_x: float = 0.0; offset_y: float = 0.0
```

### 6.5 预览系统设计

#### 12.5.1 架构总览

```
配置控件变更 → _schedule_preview_update()
                     ↓
              QTimer.singleShot(300ms)
                     ↓
              _update_preview()
              ├── self.form_data.to_yaml_dict() → style_config
              ├── 选择横/竖样本图（1200×800 或 800×1200）
              ├── 计算画布尺寸（LayoutEngine 内部处理）
              ├── 调用 FrameRenderer.render_frame()
              │   ├── 预置 PREVIEW_EXIF_DATA（跳过 ExifHelper 解析）
              │   ├── 预置 PREVIEW_AUTHOR / PREVIEW_LOCATION
              │   ├── 预置 PREVIEW_LOGO（指定文件路径，跳过 LogoSelector）
              │   └── saturation_override=1.0（关闭饱和度增强加速）
              ├── PIL Image → QImage → QPixmap
              └── self.preview_label.setPixmap(scaled_pixmap)
```

#### 12.5.2 预置样本数据

```python
# 预置 EXIF 数据（直接模拟 ExifHelper.get_display_data() 输出格式）
PREVIEW_EXIF_DATA = {
    'camera_make': 'Leica',
    'camera_model': 'Q3 43',
    'lens_model': 'Summilux 28mm f/1.7',
    'short_lens': 'Summilux 28mm',
    'focal_length': 28,
    'focal_length_35mm': 28,
    'aperture': 1.7,
    'shutter_speed': 0.008,
    'iso': 200,
    'datetime_original': '2025.06.15 14:30:00',
    'gps': "31°13'51.1\"N 121°28'19.8\"E",
}

PREVIEW_AUTHOR = "Frank Zhang"
PREVIEW_LOCATION = "Shanghai"
PREVIEW_LOGO = "leica_logo_white.png"
```

#### 12.5.3 性能保证

| 策略 | 说明 |
|------|------|
| **`saturation_override=1.0`** | 跳过饱和度增强步骤，减少 numpy 运算 |
| **300ms debounce** | `QTimer.setSingleShot(True)`，避免每次击键都渲染 |
| **预置数据** | 直接提供模拟 EXIF dict，跳过 ExifHelper 解析和设备映射 |
| **直接指定 Logo** | 跳过 LogoSelector 自动匹配流程 |
| **1200px 样本图** | ~1.2MP 分辨率，gaussian blur < 50ms，整体渲染 < 200ms |
| **不预计算背景缓存** | 1200px 下性能已足够，不需要额外的缓存管理层 |

#### 12.5.4 核心可行性论证

`FrameRenderer.render_frame()`（`src/core/renderer.py:83`）的签名：

```python
def render_frame(
    self,
    image: Image.Image,          # 样本图直接传入
    exif_data: Optional[Dict],   # PREVIEW_EXIF_DATA 预置
    author: Optional[str],       # PREVIEW_AUTHOR 预置
    location: Optional[str],     # PREVIEW_LOCATION 预置
    style_config: Dict,          # form_data.to_yaml_dict() 输出
    bg_fill_type: str,           # 预览用固定背景（可在预览面板切换）
    decorations: Optional[List[Dict]] = None,    # 预览不需要
    logo_filename: Optional[str] = None,         # PREVIEW_LOGO 预置
    lens_display_mode: str = 'combined',         # 固定值
    use_short_lens: bool = False,                # 固定值
    saturation_override: Optional[float] = 1.0,  # 关闭饱和度增强
    custom_text: Optional[str] = None,           # 预览不需要
) -> Image.Image:
```

**不修改核心模块的约束满足情况**：全部满足。`FrameRenderer`、`BackgroundFillManager`、`StyleManager`、`RenderContext` 等核心模块均不做任何修改，仅通过传入预置参数和合理的默认值来适配预览场景。

### 6.6 新增文件目录结构

```
src/gui_pyside/
├── models/
│   └── style_config_form.py          # [NEW] StyleConfigFormData + ElementConfig + DefinedTextConfig
│
├── pages/
│   └── style_creator_page.py         # [NEW] 样式编辑器页面主容器
│
├── widgets/
│   ├── style_preview.py              # [NEW] 预览面板（SegmentedWidget 横竖切换 + QLabel 显示）
│   ├── element_editor.py             # [NEW] 单个元素定位编辑器（绝对/相对定位），供 elements 和 defined_texts 复用
│   │
│   └── style_config_sections/        # [NEW] 10 个配置区块，每区块一个独立文件
│       ├── __init__.py
│       ├── basic_info_section.py     # 基本信息（name + filename）
│       ├── canvas_section.py         # 画布扩展（enable + 四边比例）
│       ├── padding_section.py        # 安全区域（四边比例）
│       ├── corner_radius_section.py  # 原图圆角（enable + 四角半径，原版遗漏，新版补齐）
│       ├── fonts_section.py          # 字体（Latin/CJK family + weight + system + 独立尺寸）
│       ├── logo_section.py           # Logo（enable + 绝对/相对定位 + size + margin）
│       ├── colors_section.py         # 颜色（通用 light/dark + 15 种元素独立覆盖）
│       ├── defined_texts_section.py  # 预定义文本（动态列表，复用 element_editor）
│       ├── custom_text_section.py    # 自定义文本（enable + 定位 + line_spacing）
│       └── elements_section.py       # 元素布局（动态列表，可添加/删除/排序，复用 element_editor）
│
├── data/
│   └── preview_data.py               # [NEW] 预置样本数据（EXIF 字典、作者、地点、Logo 文件名）
│
├── assets/
│   └── preview/                      # [NEW] 预览用样本图
│       └── .gitkeep                  # 横/竖样本图由用户放置，被 gitignore
│
└── main_window.py                    # [MODIFY] 注册 StyleCreatorPage 替换占位页面
```

### 6.7 实施阶段

#### Phase 1：基础设施

| 任务 | 文件 | 说明 |
|------|------|------|
| 1.1 数据模型 | `models/style_config_form.py` | `StyleConfigFormData`、`ElementConfig`、`DefinedTextConfig`，含 `to_yaml_dict()` 和 `from_yaml_dict()` |
| 1.2 预置数据 | `data/preview_data.py` | `PREVIEW_EXIF_DATA`、`PREVIEW_AUTHOR`、`PREVIEW_LOCATION`、`PREVIEW_LOGO` 常量 |

**验证**：`python -m py_compile` 语法校验通过

#### Phase 2：页面骨架 + 预览系统

| 任务 | 文件 | 说明 |
|------|------|------|
| 2.1 预览面板 | `widgets/style_preview.py` | `SegmentedWidget`（横/竖切换） + `QLabel`（QPixmap 显示） |
| 2.2 页面主容器 | `pages/style_creator_page.py` | `QSplitter` 左右布局，左侧 `ScrollArea` + `Pivot` 导航，右侧 `StylePreview` |
| 2.3 预览渲染管线 | `pages/style_creator_page.py` | 300ms debounce timer + `FrameRenderer.render_frame()` 调用 + PIL→QPixmap 转换 |

**验证**：打开页面能看到左右两栏，右侧预览窗能显示样本图，切换横/竖按钮工作

#### Phase 3：10 个配置区块（按依赖/复杂度排序）

| 任务 | 文件 | 复杂度 |
|------|------|--------|
| 3.1 基本信息 | `basic_info_section.py` | 低 |
| 3.2 画布扩展 | `canvas_section.py` | 低 |
| 3.3 安全区域 | `padding_section.py` | 低 |
| 3.4 原图圆角 | `corner_radius_section.py` | 低 |
| 3.5 字体 | `fonts_section.py` | 中 |
| 3.6 Logo | `logo_section.py` | 中 |
| 3.7 颜色 | `colors_section.py` | 中 |
| 3.8 元素定位编辑器 | `element_editor.py` | 高（复用核心） |
| 3.9 预定义文本 | `defined_texts_section.py` | 中（复用 element_editor） |
| 3.10 自定义文本 | `custom_text_section.py` | 中 |
| 3.11 元素布局 | `elements_section.py` | 中（复用 element_editor） |

每个区块是一个 `ExpandGroupSettingCard` 子类，包含：
- `__init__(self, icon, title, parent)` → 创建 `SettingCardGroup` + 内部控件
- `load_from_model(data: StyleConfigFormData)` → 将模型数据填入控件
- `save_to_model(data: StyleConfigFormData)` → 从控件读取数据到模型
- `value_changed` → 信号连接 `_on_config_changed()`

**验证**：每个区块完成后，手动测试界面显示、输入交互、折叠/展开

#### Phase 4：集成与完善

| 任务 | 说明 |
|------|------|
| 4.1 样式选择器 | `ComboBox` 列出已有样式文件，选择后 `from_yaml_dict()` 加载到表单 |
| 4.2 新建/保存 | 新建清空表单 → 设定 filename → `to_yaml_dict()` → 写入文件 |
| 4.3 YAML 导出预览 | `PushButton` 弹出 `Dialog`，内含只读 `TextEdit` 显示 YAML 字符串 |
| 4.4 Pivot 导航联动 | 点击 `Pivot` 标签 → `ScrollArea.verticalScrollBar().setValue(card.y())` |
| 4.5 注册到主窗口 | `main_window.py` 中 `_create_pages()` 添加 `StyleCreatorPage`，`_setup_navigation()` 导航到实际页面 |

**验证**：
- 完整流程：新建样式 → 配置各区块 → 实时预览 → 保存 → 重新加载 → YAML 导出
- 加载已有样式 → 修改 → 保存 → 验证 YAML 内容正确

### 6.8 已确认决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 圆角配置 | **补齐** `corner_radius` 区块 | Streamlit 版遗漏，_STYLE_TEMPLATE.txt 和已有样式均支持 |
| 背景预计算 | **不需要** | 1200px 样本图下模糊 < 50ms，性能足够 |
| 区块折叠 | **使用 `ExpandGroupSettingCard`** | 节省纵向空间，10 个区块可独立折叠 |
| 快速导航 | **使用 `Pivot`** | 点击标签自动滚动到对应区块 |
| 预览渲染器 | **直接复用 `FrameRenderer.render_frame()`** | 接口完全兼容，无需重写 |
| 预览防抖 | **300ms `QTimer` debounce** | 避免每次击键都渲染 |
| 预览背景增强 | **`saturation_override=1.0`** | 关闭饱和度增强加速预览渲染 |
| 样本图片尺寸 | **1200×800（横向）、800×1200（纵向）** | 3:2 比例，~1.2MP，足够预览且性能好 |

### 6.9 样式编辑器已知易错点

以下为样式编辑器开发中特有的注意事项：

1. **切换定位方式时保留另一套配置**：当用户在绝对/相对定位间切换时，之前配置的参数不应丢失。`ElementConfig` 应同时保存两套参数（`placement`/`position`/`margin_*` 和 `relative_to`/`relative_position`/`relative_margin`），切换时隐藏/显示对应控件组而非销毁重建。
2. **`SpinBox` 浮点精度**：`setDecimals(3)` + `setSingleStep(0.005)` + `setRange(0.0, 1.0)` 适用于比例值；`setRange(-1.0, 1.0)` 适用于 offset_x/y。
3. **`ExpandGroupSettingCard` 内容区域布局**：使用 `SettingCardGroup` 包裹内部控件，每个控件作为 `SettingCard` 或自定义 Widget。注意 `setParent(container)` 同步父容器（参考 11.5 第 9 条）。
4. **动态列表的 ID 管理**：`ElementConfig` 和 `DefinedTextConfig` 的 `id` 字段用于键映射，不允许重复。删除时重新分配 ID 或使用递增模式。
5. **颜色输入的实时解析**：`LineEdit.textChanged` 连接解析函数，尝试解析 `#RGB`/`[r,g,b]`，解析成功则更新色块背景色，失败则置为白色。避免在预览 debounce 基础上叠加额外渲染。
7. **Pivot 标签滚动目标计算**：`card.mapTo(scroll_area, QPoint(0, 0)).y()` 获取 card 相对于 ScrollArea 的 Y 坐标。使用 `SmoothScrollBar.scrollValue()` 替代 `setValue()` 实现平滑滚动。
8. **`SegmentedWidget` 与预览切换**：`SegmentedWidget` 的 `currentItemChanged(text)` 信号不再使用 `connect`，而是通过 `currentItemChanged.connect(fn)` 连接。切换后重新触发预览更新。
9. **YAML 导出的流式列表格式**：颜色值如 `[51, 51, 51]` 在 YAML 中需保持 `flow_style=True`，避免展开为多行列表。yaml.Dumper 需注册 `represent_list`。

### 6.10 开发进度记录

| 阶段 | 功能 | 状态 | 文件 |
|------|------|------|------|
| Phase 1 | 数据模型 (`StyleConfigFormData` + YAML 序列化) | ✅ 已完成 | `models/style_config_form.py` |
| Phase 1 | 预置数据 | ✅ 已完成 | `data/preview_data.py` |
| Phase 2 | 预览面板 (`SegmentedWidget` + `QLabel`) | ✅ 已完成 | `widgets/style_preview.py` |
| Phase 2 | 页面主容器 (QSplitter + ScrollArea + Pivot) | ✅ 已完成 | `pages/style_creator_page.py` |
| Phase 2 | 预览渲染管线 (300ms debounce + FrameRenderer) | ✅ 已完成 | `pages/style_creator_page.py` |
| Phase 3 | 元素定位编辑器 (ElementEditor) | ✅ 已完成 | `widgets/element_editor.py` |
| Phase 3 | 10 个配置区块 (BasicInfo/Canvas/Padding/CornerRadius/Fonts/Logo/Colors/DefinedTexts/CustomText/Elements) | ✅ 已完成 | `widgets/style_config_sections/*.py` |
| Phase 4 | 区块注册 + Pivot 导航联动 | ✅ 已完成 | `pages/style_creator_page.py` |
| Phase 4 | 样式加载/保存/导出 YAML | ✅ 已完成 | `pages/style_creator_page.py` |
| Phase 4 | 注册到主窗口替换占位页面 | ✅ 已完成 | `main_window.py` |
| Bugfix | `SegmentedWidget.currentItem()` 返回对象而非字符串 (tree_align 丢失根因) | ✅ 已修复 | `element_editor.py`, `logo_section.py`, `custom_text_section.py` |
| Bugfix | 预览不刷新 (`_on_config_changed` 未回写 UI → form_data) | ✅ 已修复 | `style_creator_page.py` |
| Bugfix | 加载样式后数据被覆盖 (`_save_all_sections` 在加载期间触发) | ✅ 已修复 | `style_creator_page.py` |
| Bugfix | `margin` 统一边距字段未解析 | ✅ 已修复 | `style_config_form.py` |
| Bugfix | ElementEditor 自引用（relative_to 指向自身）导致渲染无限循环 | ✅ 已修复 | `element_editor.py` |
| Bugfix | 动态添加元素后卡片高度不更新（`_adjustViewSize` 未调用） | ✅ 已修复 | `elements_section.py`, `defined_texts_section.py` |
| Bugfix | 配置滚动面板使用了 Qt 原生 `QScrollArea` 而非 QFW `SmoothScrollArea` | ✅ 已修复 | `style_creator_page.py` |

## 7. QFluentWidgets 组件映射表

可以自行联网阅读官方文档和官方组件列表，以获取完整的可用组件名单。

官方文档及组件列表链接：[https://qfluentwidgets.com/zh/pages/componentlist](https://qfluentwidgets.com/zh/pages/componentlist)

官方API文档链接：[https://pyqt-fluent-widgets.readthedocs.io/zh-cn/latest/autoapi/index.html](https://pyqt-fluent-widgets.readthedocs.io/zh-cn/latest/autoapi/index.html)

### 7.1 组件对照（Streamlit → QFluentWidgets）

> **强制规则**：以下映射表中列出的 QFluentWidgets 组件是唯一允许使用的组件。禁止使用对应的 Qt 原生组件。

| Streamlit 组件                    | QFluentWidgets 组件                                | 导入路径                                 |
| --------------------------------- | -------------------------------------------------- | ---------------------------------------- |
| `st.selectbox`                  | `ComboBox`                                       | `qfluentwidgets`                       |
| `st.text_input`                 | `LineEdit`                                       | `qfluentwidgets`                       |
| `st.text_area`                  | `PlainTextEdit`                                  | `qfluentwidgets`                       |
| `st.checkbox`                   | `CheckBox`                                       | `qfluentwidgets`                       |
| `st.slider`                     | `Slider`                                         | `qfluentwidgets`                       |
| `st.button`                     | `PushButton` / `PrimaryPushButton`             | `qfluentwidgets`                       |
| `st.file_uploader`              | 自定义对话框 +`QFileDialog`                      | `qfluentwidgets.components.dialog_box` |
| `st.download_button`            | `PushButton` + 保存对话框                        | `qfluentwidgets`                       |
| `st.image`                      | `ImageLabel` / 自定义 `QLabel`                 | `qfluentwidgets`                       |
| `st.expander`                   | `ExpandSettingCard` / `ExpandGroupSettingCard` | `qfluentwidgets`                       |
| `st.columns`                    | `QHBoxLayout`（Qt 布局，非可视组件）             | `PySide6.QtWidgets`                    |
| `st.spinner`                    | `ProgressBar` / `ProgressRing`                 | `qfluentwidgets`                       |
| `st.info/success/warning/error` | `InfoBar`                                        | `qfluentwidgets`                       |
| `st.metric`                     | 自定义 `CardWidget` + `QLabel`                 | `qfluentwidgets`                       |
| `st.data_editor`                | `TableWidget`（后续页面）                        | `qfluentwidgets`                       |
| `st.sidebar`                    | `NavigationInterface`（导航栏）                  | `qfluentwidgets`                       |
| `st.session_state`              | Python 类属性 / 数据模型                           | -                                        |
| `st.cache_resource`             | 模块级单例 /`__init__` 中初始化                  | -                                        |
| `st.cache_data`                 | `QCache` / LRU 缓存                              | -                                        |
| `st.rerun()`                    | `QApplication.processEvents()` / 信号槽          | -                                        |

### 7.2 禁止使用的 Qt 原生组件

以下组件**绝对不允许**出现在 GUI 代码中：

| 禁止组件                           | 替代方案                                                           |
| ---------------------------------- | ------------------------------------------------------------------ |
| `QPushButton`                    | `PushButton` / `PrimaryPushButton` / `TransparentPushButton` |
| `QComboBox`                      | `ComboBox`                                                       |
| `QCheckBox`                      | `CheckBox`                                                       |
| `QSlider`                        | `Slider`                                                         |
| `QLineEdit`                      | `LineEdit`                                                       |
| `QTextEdit` / `QPlainTextEdit` | `PlainTextEdit`                                                  |
| `QLabel`（用于显示文本）         | `StrongBodyLabel` / `SubtitleLabel` / `CaptionLabel`         |
| `QProgressBar`                   | `ProgressBar`                                                    |
| `QDialog`                        | `Dialog` / `MessageBox`                                        |
| `QMessageBox`                    | `MessageBox`                                                     |
| `QFileDialog`                    | 保留使用（QFluentWidgets 未封装文件对话框）                        |
| `QTabWidget`                     | `SegmentedWidget` / `Pivot`                                    |
| `QScrollBar`                     | `ScrollBar`（QFluentWidgets 自动替换）                           |

### 7.3 布局组件（允许使用 Qt 原生）

以下 Qt 布局类允许使用，因为 QFluentWidgets 不提供布局替代：

- `QVBoxLayout`
- `QHBoxLayout`
- `QGridLayout`
- `QSplitter`（用于可拖拽分割线）
- `QScrollArea`（用于滚动容器）

### 7.4 图标规范

使用 FluentUI SVG 图标，通过 `FluentIcon` 枚举获取：

```python
from qfluentwidgets import FluentIcon as FIF

# 导航图标
FIF.PHOTO          # 图像处理
FIF.CAMERA         # 相机映射
FIF.ZOOM_IN        # 镜头映射（或 FIF.LENS）
FIF.PALETTE        # 样式编辑器

# 操作图标
FIF.SAVE           # 导出
FIF.DELETE         # 清空
FIF.DOWN           # 下载
FIF.ADD            # 添加
FIF.CLOSE          # 关闭
FIF.SETTING        # 设置
```

---

## 8. 数据模型设计

### 8.1 FileItem（单个图片文件）

```python
@dataclass
class FileItem:
    """单个图片文件的数据模型"""
    file_path: str                    # 原始文件路径
    file_name: str                    # 文件名
    file_bytes: bytes = None          # 原始文件字节（内存中保留，避免重复读盘）
    thumbnail: QImage = None          # 缩略图（120px 高度等比）
    result_thumbnail: QImage = None   # 效果图缩略图
    exif_data: dict = None            # EXIF 数据
    display_data: dict = None         # 格式化显示数据
    file_info: dict = None            # 文件元数据
    is_processed: bool = False        # 是否已处理
    result_path: str = None           # 输出文件路径
    config: ProcessingConfig = None   # 该图片的独立配置（每个图片可不同）
```

### 8.2 ProcessingConfig（处理配置）

```python
@dataclass
class ProcessingConfig:
    """处理配置模型"""
    style_name: str = "底部信息条 Bottom Bars"
    output_format: str = "JPEG"
    bg_fill_type: str = "gaussian_black_35"
    font_weight: str = "medium"
    enhance_background: bool = True
    author: str = ""
    location: str = ""
    use_gps_location: bool = False
    lens_display_mode: str = "combined"
    use_short_lens: bool = False
    logo_selection: str = "auto"      # "auto" / "none" / 具体文件名
    custom_text: str = None
    watermark_enabled: bool = False
    watermark_text: str = ""
    watermark_position: str = "bottom-right"
    watermark_opacity: int = 50
    watermark_color: tuple = (255, 255, 255)
```

---

## 9. 内存与缓存管理

### 9.1 TempManager（临时文件管理）

```python
class TempManager:
    """临时文件生命周期管理器"""
  
    def __init__(self):
        self._temp_files: List[str] = []
        self._temp_dirs: List[str] = []
  
    def create_temp_file(self, suffix: str = ".jpg") -> str:
        """创建临时文件并注册到跟踪列表"""
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        self._temp_files.append(path)
        return path
  
    def create_temp_dir(self) -> str:
        """创建临时目录并注册到跟踪列表"""
        path = tempfile.mkdtemp(prefix="mileica_")
        self._temp_dirs.append(path)
        return path
  
    def cleanup(self):
        """清理所有临时文件和目录"""
        for f in self._temp_files:
            try:
                if os.path.exists(f):
                    os.unlink(f)
            except OSError:
                pass
        for d in self._temp_dirs:
            try:
                if os.path.exists(d):
                    shutil.rmtree(d, ignore_errors=True)
            except OSError:
                pass
        self._temp_files.clear()
        self._temp_dirs.clear()
```

### 9.2 主窗口关闭事件

```python
class MainWindow(FluentWindow):
    def closeEvent(self, event):
        """窗口关闭时自动清理所有资源"""
        # 1. 清理临时文件
        self.temp_manager.cleanup()
    
        # 2. 清除图片缓存
        self.image_cache.clear()
    
        # 3. 释放缩略图内存
        for item in self.filmstrip.items():
            item.thumbnail = None
            item.result_thumbnail = None
    
        # 4. 断开所有信号连接
        self信号 disconnect...
    
        # 5. 接受关闭事件
        event.accept()
```

### 9.3 缩略图缓存策略

- 使用 `QCache` 限制最大缓存数量（如 100 张）
- 缩略图尺寸：高度固定 100px，宽度等比
- 预览图尺寸：横向 3000px 以内
- 当缓存满时自动淘汰最久未使用的缩略图

---

## 10. 文件目录结构

```
src/gui_pyside/
├── __init__.py
├── app.py                          # PySide6 应用入口
├── main_window.py                  # FluentWindow 主窗口
│
├── models/
│   ├── __init__.py
│   ├── file_item.py                # FileItem 数据模型
│   └── processing_config.py        # ProcessingConfig 配置模型
│
├── pages/
│   ├── __init__.py
│   ├── image_processing_page.py    # 图像处理页面主容器
│   ├── camera_mapping_page.py      # 相机映射管理（后续）
│   ├── lens_mapping_page.py        # 镜头映射管理（后续）
│   └── style_creator_page.py       # 样式编辑器（后续）
│
├── widgets/
│   ├── __init__.py
│   ├── filmstrip.py                # 胶片栏
│   ├── image_preview.py            # 预览窗口
│   ├── accordion_panel.py          # 手风琴式配置面板容器
│   ├── output_settings_tab.py      # Tab 1: 输出设置
│   ├── frame_config_tab.py         # Tab 2: 相框配置
│   ├── personalization_tab.py      # Tab 3: 个性化配置
│   ├── shot_info_tab.py            # Tab 4: 拍摄信息配置
│   ├── watermark_tab.py            # Tab 5: 文本水印
│   └── exif_info_panel.py          # EXIF 信息显示面板
│
├── utils/
│   ├── __init__.py
│   └── temp_manager.py             # 临时文件管理
│
└── resources/
    └── icons/                      # FluentUI SVG 图标
        ├── photo.svg
        ├── book_stories.svg
        ├── camera.svg
        ├── lens.svg
        ├── palette.svg
        ├── save.svg
        ├── delete.svg
        └── ...
```

---

## 11. 实施步骤

### Phase 1: 基础框架搭建

**目标**：安装依赖、创建目录结构、主入口双模式选择、FluentWindow 主窗口 + 导航

**任务**：

1. 安装 `PySide6-Fluent-Widgets[full]`
2. 创建 `src/gui_pyside/` 目录结构
3. 实现 `app.py`（QApplication 初始化、主题设置）
4. 实现 `main_window.py`（FluentWindow + NavigationInterface + 5 个导航项）
5. 修改 `src/main.py` 增加 `--mode` 参数 + 交互对话框
7. 创建占位页面（每个页面一个简单的 `QLabel`）

**验证**：运行 `python src/main.py --mode pyside` 能看到 FluentWindow + 导航栏，点击导航项可切换页面

### Phase 2: 数据模型

**目标**：定义 FileItem 和 ProcessingConfig 数据模型

**任务**：

1. 实现 `models/file_item.py`
2. 实现 `models/processing_config.py`
3. 实现 `utils/temp_manager.py`

**验证**：单元测试验证数据模型创建和 TempManager 清理

### Phase 3: 图像处理页面骨架

**目标**：搭建页面主容器布局（胶片栏 + 预览 + 配置栏 + 按钮）

**任务**：

1. 实现 `pages/image_processing_page.py`（主容器布局）
2. 实现 `widgets/filmstrip.py`（胶片栏基础版）
3. 实现 `widgets/image_preview.py`（预览窗口基础版）
4. 实现 `widgets/exif_info_panel.py`（EXIF 信息面板）

**验证**：能拖拽/选择图片文件，胶片栏显示缩略图，预览窗口显示原图

### Phase 4: 配置面板

**目标**：实现 5 个手风琴式折叠配置 Tab

**任务**：

1. 实现 `widgets/accordion_panel.py`（容器）
2. 实现 `widgets/output_settings_tab.py`
3. 实现 `widgets/frame_config_tab.py`
4. 实现 `widgets/personalization_tab.py`
5. 实现 `widgets/shot_info_tab.py`
7. 实现 `widgets/watermark_tab.py`

**验证**：所有配置选项正确显示，根据样式配置动态启用/禁用

### Phase 5: 业务逻辑集成

**目标**：连接配置面板与核心处理层

**任务**：

1. 实现图片加载和 EXIF 提取
2. 实现配置参数收集（从 GUI 控件 → ProcessingConfig）
3. 实现 `ImageProcessor.process()` 调用
4. 实现效果图预览切换
5. 实现导出功能（单张 + 批量）
7. 实现清空功能
8. 实现配置变更检测（重新生成按钮）

**验证**：完整流程测试（加载图片 → 配置 → 生成 → 预览 → 导出）

### Phase 6: 完善与测试

**目标**：内存检查、边界情况处理、用户体验优化

**任务**：

1. 内存泄漏检查（临时文件清理、缩略图释放）
2. 大图性能测试
3. 错误处理（文件格式不支持、EXIF 缺失等）
4. 窗口关闭事件测试
5. 快捷键支持（Delete 删除、Ctrl+O 打开等）

---

## 附录 A：QFluentWidgets 组件完整列表（本项目可用）

### 导航类

- `NavigationInterface` - 导航接口
- `NavigationPanel` - 导航面板
- `NavigationPushButton` - 导航按钮
- `NavigationBar` - 导航栏
- `Pivot` - 枢轴导航
- `SegmentedWidget` - 分段导航

### 按钮类

- `PushButton` - 普通按钮
- `PrimaryPushButton` - 主按钮
- `TransparentPushButton` - 透明按钮
- `TransparentToggleToolButton` - 透明切换工具按钮

### 输入类

- `ComboBox` - 下拉框
- `EditableComboBox` - 可编辑下拉框
- `LineEdit` - 单行输入
- `PlainTextEdit` - 多行输入
- `CheckBox` - 复选框
- `SwitchButton` - 开关按钮
- `Slider` - 滑块
- `SpinBox` - 数字框

### 显示类

- `ImageLabel` - 图片标签
- `StrongBodyLabel` - 加粗正文标签
- `SubtitleLabel` - 副标题标签
- `CaptionLabel` - 说明标签
- `ProgressBar` - 进度条
- `ProgressRing` - 进度环
- `InfoBadge` - 信息徽章

### 容器类

- `CardWidget` - 卡片容器
- `ExpandSettingCard` - 展开设置卡片
- `ExpandGroupSettingCard` - 展开分组设置卡片
- `SettingCardGroup` - 设置卡片组
- `ScrollArea` - 滚动区域

### 反馈类

- `InfoBar` - 信息条
- `MessageBox` - 消息对话框
- `Dialog` - 对话框
- `ToolTip` - 工具提示
- `TeachingTip` - 教学提示

### 布局类（Qt 原生，允许使用）

- `QVBoxLayout` - 垂直布局
- `QHBoxLayout` - 水平布局
- `QGridLayout` - 网格布局
- `QSplitter` - 分割器

---

## 附录 B：样式配置参考

### 样式变体匹配逻辑

`StyleManager.get_style_config(name, context)` 的行为：

1. 如果 `name` 对应文件夹样式，根据 `context` 中缺失的字段选择最佳变体
2. 如果 `name` 对应单文件样式，直接加载
3. 变体命名规则：`no_{field}.yaml`（如 `no_location.yaml`）
4. 多字段变体优先级高于单字段变体

### 完整样式配置结构

```yaml
name: "样式名称"
colors:
  text: '#000000'
  custom_text_light_color: [51, 51, 51]
  custom_text_dark_color: [204, 204, 204]
  custom_{key}_light_color: ...
  custom_{key}_dark_color: ...
fonts:
  latin:
    family: Gotham
    weight: medium
    weights: { light: Light, regular: Book, medium: Medium }
  cjk:
    family: GlowSansSC-Normal
    weight: medium
    weights: { light: Light, regular: Regular, medium: Medium }
  size_ratio: 0.02
  sizes:
    {key}: 0.015
  line_spacing_ratio: 0.005
layout:
  expand_canvas:
    enabled: true
    top: 0.0
    bottom: 0.1
    left: 0.0
    right: 0.0
  padding: { top: 0.0, bottom: 0.0, left: 0.04, right: 0.04 }
  corner_radius: { enabled: false, ... }
  info_position:
    {key}:
      placement: outside
      position: "bottom-left"
      alignment: "left"
      margin_top: 0.01
      margin_bottom: 0.028
      margin_left: 0.02
      margin_right: 0.01
  defined_texts:
    defined_text_01: { content: "FL", ... }
  custom_text:
    enabled: true
    placement: outside
    position: "bottom-center"
    alignment: "center"
logo:
  enabled: true
  size_ratio: 0.048
  diagonal_limit_ratio: 2.0
  placement: outside
  position: "bottom-right"
  alignment: "center"
  relative_to: "exif"
  relative_position: "left-of"
  relative_margin: 0.016
```

---

## 12. 开发进度记录（2026-06-04）

### 12.1 已完成的功能

| 阶段    | 功能                                                     | 状态    | 文件                               |
| ------- | -------------------------------------------------------- | ------- | ---------------------------------- |
| Phase 1 | 基础框架搭建（FluentWindow + 5 个导航项）                | ✅ 完成 | `app.py`, `main_window.py`     |
| Phase 1 | 主入口双模式选择（交互对话框）                           | ✅ 完成 | `main.py`                        |
| Phase 1 | 窗口默认尺寸 1280×960，屏幕居中启动                      | ✅ 完成 | `main_window.py`                 |
| Phase 2 | 数据模型（FileItem + ProcessingConfig）                  | ✅ 完成 | `models/`                        |
| Phase 3 | 图像处理页面骨架（预览+配置栏+胶片栏）                   | ✅ 完成 | `pages/image_processing_page.py` |
| Phase 4 | 5 个手风琴式配置 Tab                                     | ✅ 完成 | 同上                               |
| Phase 5 | 生成相框功能（ImageProcessor 集成）                      | ✅ 完成 | 同上                               |
| Phase 5 | 导出功能（文件保存/文件夹选择）                          | ✅ 完成 | 同上                               |
| Phase 5 | ICC 色彩空间转换                                         | ✅ 完成 | 同上                               |
| Phase 5 | 样式配置动态加载（StyleManager + BackgroundFillManager） | ✅ 完成 | 同上                               |
| Phase 5 | LOGO 文件读取 + 自定义文本启用/禁用                      | ✅ 完成 | 同上                               |
| Phase 6 | 胶片栏可调高度（QSplitter）                              | ✅ 完成 | 同上                               |
| Phase 6 | 胶片栏鼠标滚轮横向滚动                                   | ✅ 完成 | 同上                               |
| Phase 6 | 胶片栏选中项蓝色高亮                                     | ✅ 完成 | 同上                               |
| Phase 6 | 胶片栏右键移除图片（RoundMenu）                          | ✅ 完成 | 同上                               |
| Phase 6 | EXIF 信息面板（两行网格布局）                            | ✅ 完成 | 同上                               |
| Phase 6 | StateToolTip 处理状态提示                                | ✅ 完成 | 同上                               |
| Phase 6 | SmoothScrollArea 滚动条美化                              | ✅ 完成 | 同上                               |
| Phase 6 | 其他页面占位（4 个）                                     | ✅ 完成 | `main_window.py`                 |
| Phase 6 | 右侧配置栏宽度可调（水平 QSplitter）+ 最小宽度           | ✅ 完成 | `pages/image_processing_page.py` |
| Phase 6 | CheckBox → SwitchButton（4 处）                         | ✅ 完成 | 同上                               |
| Phase 6 | 删除孤儿 widget（custom_text_label）                     | ✅ 完成 | 同上                               |
| Phase 6 | 背景填充下拉框显示中文标签                               | ✅ 完成 | 同上                               |
| Phase 6 | EXIF 面板字号放大（CaptionLabel → BodyLabel）           | ✅ 完成 | 同上                               |
| Phase 6 | EXIF 面板字段值加粗（HTML `<b>`）                      | ✅ 完成 | 同上                               |
| Phase 6 | 相机映射管理页面（品牌筛选+搜索+可编辑表格+保存）       | ✅ 完成 | `pages/camera_mapping_page.py`  |
| Phase 6 | 镜头映射管理页面（搜索+卡口/品牌筛选+可编辑表格+保存）  | ✅ 完成 | `pages/lens_mapping_page.py`    |
| Phase 6 | lens_map.csv 扩展字段（brand/mount/timestamp）           | ✅ 完成 | `data/lens_map.csv`, `device_mapper.py`, `exif_helper.py` |
| Phase 6 | 配置面板 SmoothScrollArea → ScrollArea                   | ✅ 完成 | `pages/image_processing_page.py` |
| Phase 6 | 配置面板 ExpandLayout + card.setParent 同步父容器       | ✅ 完成 | 同上                               |
| Phase 6 | 自定义文本 PlainTextEdit → LineEdit 修复折叠异常        | ✅ 完成 | 同上                               |
| Phase 6 | 预览图 QPixmap 缓存（FileItem.cached_pixmap）           | ✅ 完成 | `file_item.py`, `image_processing_page.py` |
| Phase 6 | QSplitter setChildrenCollapsible(False) 防止面板消失     | ✅ 完成 | `image_processing_page.py`       |
| Phase 6 | 右侧配置栏 minWidth=450, maxWidth=600                    | ✅ 完成 | 同上                               |
| Phase 6 | 格式规范说明卡片（相机/镜头页面双栏 7:3 布局）          | ✅ 完成 | `camera_mapping_page.py`, `lens_mapping_page.py` |
| Phase 6 | 水平 QSplitter stretchFactor 设置 (1,0)                  | ✅ 完成 | `image_processing_page.py` |
| Phase 6 | 预览图随 QSplitter 手柄拖拽自动缩放（splitterMoved 信号） | ✅ 完成 | `image_processing_page.py` |
| Phase 6 | 胶片栏缩略图随分割器拖拽 / 窗口 resize 自动缩放          | ✅ 完成 | `image_processing_page.py` |
| Phase 6 | 预览图 rescaleEvent + QTimer.singleShot 延迟缩放         | ✅ 完成 | `image_processing_page.py` |
| Phase 6 | QSizePolicy.Ignored — 防止 QLabel pixmap sizeHint 阻塞 splitter | ✅ 完成 | `image_processing_page.py` |
| Phase 6 | 绕过 Qt QImageIOHandler 256MB 上限（QPixmap→PIL 加载） | ✅ 完成 | `image_processing_page.py` |
| Phase 6 | 背景填充默认值选择修复（`bg_choices.values()`→`bg_choices`） | ✅ 完成 | `image_processing_page.py` |
| Phase 6 | 胶片栏 maxHeight=250 防止缩略图过度放大                  | ✅ 完成 | `image_processing_page.py` |
| Phase 6 | 右侧配置栏 minWidth/maxWidth 优化 (350/800)              | ✅ 完成 | `image_processing_page.py` |

### 12.2 未完成 / 待后续开发

| 功能             | 优先级 | 备注                       |
| ---------------- | ------ | -------------------------- |
| 样式编辑器页面   | P2     | ✅ 已完成（2026-06-06）    |
| 数据预置（PREVIEW_EXIF_DATA + custom_text） | P2 | ✅ 已完成（2026-06-07） |
| Logo 自动匹配（LogoSelector） | P2 | ✅ 已完成（2026-06-07） |
| 控件始终可见（全部配置区块） | P2 | ✅ 已完成（2026-06-07） |
| tree_align 数据完整性修复 | P2 | ✅ 已完成（2026-06-07） |
| 字重映射表编辑 | P2 | ✅ 已完成（2026-06-07） |
| margin 统一边距字段解析 | P2 | ✅ 已完成（2026-06-07） |
| 图像拖拽到胶片栏 | P2     | 当前仅支持文件选择器       |

### 12.3 测试中遇到的问题与解决方案

#### 导入问题（反复出现，核心难点）

| 问题                                                   | 根因                                                              | 解决方案                                                                        |
| ------------------------------------------------------ | ----------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `No module named 'src'`                              | `main.py` 运行时 `src/` 在 sys.path，`src` 本身不可导入为包 | `gui_pyside/app.py` 中添加项目根目录到 sys.path                               |
| `attempted relative import beyond top-level package` | `core/__init__.py` 的 `from .._version import __version__`    | 创建最小化 `src` 模块占位（`types.ModuleType`），不触发 `src/__init__.py` |
| `spec_from_file_location` 失败                       | `image_processor.py` 内部 `from src.utils.xxx`                | 项目根目录加入 sys.path 后，正常导入路径生效                                    |

**关键结论**：`core/__init__.py` 中的 `from .._version` 和 `core/*.py` 中的 `from src.xxx` 要求 `src` 必须作为合法包被导入。`src/__init__.py` 又会导入 `gui`（Streamlit），导致 Streamlit 运行时警告。最终方案：手动创建最小化 `src` 包对象放入 `sys.modules`。

#### 其他踩坑点

| 问题                          | 根因                                             | 解决方案                                             |
| ----------------------------- | ------------------------------------------------ | ---------------------------------------------------- |
| 配置选项显示不全              | 硬编码 ComboBox 选项                             | 改为从 StyleManager / BackgroundFillManager 动态加载 |
| 胶片栏图片折行                | `color_space` 含尾部换行符 `\n`              | 使用 `.strip()` 去除                               |
| 胶片栏缩略图裁剪              | `setMaximumHeight(140)` 固定                   | 移除限制，用 QSplitter 实现可调高度                  |
| StateToolTip 动画不转         | `ImageProcessor.process()` 阻塞事件循环        | 接受为已知限制，StateToolTip 提示框本身已足够        |
| 进度条不动画                  | `ProgressBar.setRange(0,0)` 在阻塞期间无法刷新 | 改用 StateToolTip                                    |
| 选择索引错位                  | lambda 闭包捕获创建时的索引                      | 改为 `filmstrip_labels.index(label)` 动态查找      |
| 删除缩略图崩溃                | `layout_index` 公式计算错误                    | 改为 `takeAt(index)` 直接使用                      |
| 日志重复输出                  | `utils.logging_config` 被两个模块路径导入两次  | 统一导入路径为 `from utils.logging_config`         |
| 背景填充选项显示内部 key      | 使用了 `bg_choices.values()` 返回的 key        | 改为 `bg_choices.keys()` 显示中文标签              |
| 缩略图滚动无动画              | `setValue()` 直接设置而非 `scrollValue()`    | 改用 `delegate.hScrollBar.scrollValue(-delta)`     |
| 折叠卡片下方空白 box          | 孤儿 `CaptionLabel` 未被添加到布局             | 删除未使用的 orphan widget                           |
| lambda 闭包索引错位（第二次） | 创建时硬编码索引，删除后索引偏移                 | 改用 `filmstrip_labels.index(label)` 动态查找      |
| CardWidget 布局冲突            | `QVBoxLayout(card)` 后 `FlowLayout(card)` 重复设父 | `FlowLayout()` 不带 parent，用 `addLayout` 加入父布局 |
| TableWidget.setModel 不可用    | QFW TableWidget 将 setModel 声明为私有方法         | 直接用 `setItem(row, col, QTableWidgetItem(...))` API |
| QFW 内置 FlowLayout            | 自定义实现了 FlowLayout，不知 QFW 已提供           | 删除自定义实现，改用 `from qfluentwidgets import FlowLayout` |
| **样式编辑器 tree_align 失效**（2026-06-07） | `SegmentedWidget.currentItem()` 返回 `SegmentedItem` 对象而非字符串，赋值到 `target.mode` 后 `to_yaml_dict` 中的 `== 'absolute'` 比较永远 False，导致所有树级定位参数丢失 | 在 Editor 中维护 `_current_mode` 字符串字段，由 `_on_mode_changed(mode: str)` 更新，save 方法中不再调用 `currentItem()` 而是直接读字符串 |

### 12.5 易错点补充（2026-06-05）

1. **SwitchButton 不需要文字**：`SwitchButton()` 可不传参数，由 group 标题提供说明。其接口与 `CheckBox` 兼容（`isChecked()` / `setChecked()`）。
2. **smoothScrollBar.scrollValue()**：替代直接 `setValue()`，内部使用 `QPropertyAnimation` 实现平滑动画。可通过 `setScrollAnimation(duration, easing)` 配置。
3. **`SmoothScrollArea` 的 delegate**：`self.delegate.hScrollBar` 返回的是 `SmoothScrollBar` 而非原生 `QScrollBar`，有 `scrollValue()` 和 `setScrollAnimation()` 方法。
4. **BodyLabel 支持 HTML**：可通过 `<b>text</b>` 实现部分文本加粗，无需拆分多个 label。
5. **ExpandGroupSettingCard 的孤儿 widget**：创建在 card 上但未 `addGroup` 的 widget 会在折叠时占据空间，产生空白区域。
7. **CardWidget 无预置布局**：`CardWidget` 继承 `QFrame`，没有 `vBoxLayout` 属性，需自行 `QVBoxLayout(card)` 设定布局，不可重复设。
8. **FlowLayout 不传 parent 作为子布局**：`FlowLayout()` 不加 parent 创建，通过父布局的 `addLayout()` 加入，避免 `QWidget::setLayout` 冲突。
9. **QFW TableWidget 使用 QTableWidgetItem API**：`TableWidget.setItem(row, col, QTableWidgetItem(...))` 而非 `setModel()`。
10. **ExpandLayout.addWidget 不设 parent**：`ExpandLayout.addWidget(widget)` 不会自动设置 widget 的父窗口，需手动 `widget.setParent(container)` 使 widget 可见。
11. **PlainTextEdit.sizeHint 不受 setFixedHeight 影响**：`QPlainTextEdit.sizeHint()` 固定返回 192px，无论是否 `setFixedHeight`，导致 `ExpandGroupSettingCard` 折叠异常。解决方案：改用 `LineEdit`。
12. **QWidget 的 max/minSize 与 splitter**：`QSplitter` 配合 `setChildrenCollapsible(False)` 时严格遵循子控件的 `minimumSize` 和 `maximumSize`，`QLabel.setPixmap` 会更新 `minimumSizeHint`，影响 splitter 拖拽范围。可通过 `setMinimumSize` 覆盖。
6. **QSplitter.splitterMoved 信号**：`QSplitter.splitterMoved(pos, index)` 在手柄拖拽后立即触发，此时子 widget 的几何尺寸已更新完毕。连接此信号可响应内部分割器变化，补充 `resizeEvent` 无法覆盖的场景。
13. **QTimer.singleShot(0, fn) 延迟回调**：在 `resizeEvent` 中使用 `QTimer.singleShot(0, fn)` 将操作推迟到当前事件循环后执行，确保所有子 widget 布局更新完毕后再读取几何尺寸。适用场景：QSplitter 调整后代尺寸尚未稳定的 resizeEvent 中。
14. **QSizePolicy.Ignored 与 QSplitter 压缩**：`QSizePolicy.Ignored` 阻止 QSplitter 拖拽时查询 `minimumSizeHint`，仅检查 `minimumSize()`。QLabel 设置 pixmap 后 `minimumSizeHint` 膨胀，设置 Ignored 策略后可正常压缩。
15. **Qt QImageIOHandler 256MB 分配上限**：`QPixmap(file_path)` 底层使用 `QImageReader`，默认最大分配 256MB。高分辨率图（如 10000×8000 RGB=240MB）易超限。替代方案：`PIL.Image.open()` + `QImage` 转换。
16. **ComboBox.setCurrentText 的条件判断陷阱**：`QComboBox.setCurrentText(text)` 在不匹配时静默失败。`bg_choices = {label: key}` 的前提下，`if label in bg_choices`（查 key）正确；`if label in bg_choices.values()`（查 value）永远不匹配。
 
### 12.4 易错点总结

1. **PySide6 相对导入规则**：在包内部使用 `from src.xxx` 导入时，Python 会将其视为相对导入。解决方法是将项目根目录加入 sys.path 并确保 `src` 在 `sys.modules` 中。
2. **`ExpandGroupSettingCard` 需要 icon 参数**：第一个参数是 `FluentIcon`，不是直接传字符串。
3. **`QGridLayout` 的 `addWidget` 签名**：跨列需用 5 参数形式 `addWidget(w, row, col, rowSpan, colSpan)`。
4. **`SmoothScrollDelegate` 事件过滤器优先级**：`installEventFilter` 后装先执行。要覆盖滚轮行为需在 delegate 安装后再安装自己的过滤器。
5. **QFluentWidgets 的 `FluentIcon` 枚举值**：区分大小写，如 `FluentIcon.CHECKBOX`（大写），不能用 `FluentIcon.Document`。
7. **lambda 闭包中的索引捕获**：Python lambda 默认参数是立即求值的，但如果外部变量后续被修改（如列表 pop），旧索引会指向错误位置。解决方案是改为通过对象引用动态查找。

8. **`SegmentedWidget.currentItem()` 返回对象而非字符串**（2026-06-07）：`currentItem()` 返回的是 `SegmentedItem`（QPushButton 子类）对象，而不是添加时的 routeKey 字符串。直接赋值 `target.mode = self.mode_seg.currentItem()` 会使 mode 变成 SegmentedItem 对象，后续 `if mode == 'absolute'` 永远为 False。解决方案：在 `_on_mode_changed(mode: str)` 中接收信号传来的字符串并存入 `self._current_mode`，所有 save 方法从 `self._current_mode` 读取。

9. **`_save_all_sections` 中调用 `blockSignals` 的副作用**（2026-06-07）：`blockSignals(True)` 会阻断 `SegmentedWidget` 内部的状态同步。如果调用 `setCurrentItem` 时信号被阻塞，虽然路由键被设置，但 QFluentWidgets 内部可能不更新返回状态。替代方案：维护独立字符串字段而非依赖 `currentItem()`。

10. **数据模型 round-trip 测试的盲区**（2026-06-07）：`to_yaml_dict() → from_yaml_dict() → to_yaml_dict()` 仅测了纯 Python 模型的序列化路径，测不到 `_save_all_sections()` 中 `save_element()` / `save_defined_text()` 的 UI 值读取。后者使用的 `currentItem()` 返回了 SegmentedItem 对象，绕过了纯模型测试。解决方案：round-trip 测试需要覆盖完整 `save → serialize → load → compare` 路径。

11. **`ExpandSettingCard` 是 QScrollArea 子类**（2026-06-07）：`ExpandSettingCard` 继承自 `QScrollArea`，其 expand/collapse 动画通过操作 `verticalScrollBar().value` 实现。`addGroupWidget()` 直接将 widget 放入 `viewLayout`（垂直布局），`addGroup()` 则包装为 `GroupWidget`（水平布局，widget 在标题右侧）。前者适用于需要自定义复杂布局的场景，后者适用于简单单控件。

12. **SegmentedWidget 的 currentItemChanged 信号返回字符串**：虽然 `currentItem()` 返回对象，但 `currentItemChanged` 信号发出的正是添加时的 routeKey 字符串。所以 `_on_mode_changed(mode: str)` 收到的参数是正确的。应依赖信号参数而非 `currentItem()`。

13. **ElementEditor 切到相对定位时的自引用陷阱**（2026-06-07）：新建样式默认元素 `key='exif'`，`relative_to` 默认也是 `'exif'`。一切到相对定位，`save_element()` 就会写入 `relative_to:'exif'`，形成自引用。渲染引擎拓扑排序对此无限循环导致卡死。解决方案：在 `_on_mode_changed()` 中检测 `relative_to` 是否等于元素自身 key，若是则自动切换到列表中第一个不同 key。

14. **ExpandGroupSettingCard 动态添加元素后卡片高度锁定**（2026-06-07）：`addGroupWidget(container)` 初始化时 `_adjustViewSize()` 计算一次固定高度。之后在 `_container` 布局中动态添加 item 时卡片高度不更新，内容被截断。解决方案：添加/删除后调用 `QTimer.singleShot(0, self._adjustViewSize)`（延迟到 Layout 完成后再更新高度）。

15. **使用 QFW `SmoothScrollArea` 而非 Qt `QScrollArea`**（2026-06-07）：样式编辑器的配置面板滚动区原本使用 Qt 原生 `QScrollArea`，应替换为 QFluentWidgets 的 `SmoothScrollArea`，后者提供平滑滚动动画和 Fluent Design 风格滚动条。

---
