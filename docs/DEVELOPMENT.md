# 开发参考 (Development Reference)

> 面向开发者：本文档说明 MiLecFrame 的架构设计、核心模块实现、渲染管线、设计模式与开发约定。

## 目次

1. [技术栈](#1-技术栈)
2. [项目结构](#2-项目结构)
3. [整体数据流与处理管线](#3-整体数据流与处理管线)
4. [核心模块详解](#4-核心模块详解)
   - [4.1 LayoutEngine（布局引擎）](#41-layoutengine布局引擎)
   - [4.2 FrameRenderer（渲染器）](#42-framerenderer渲染器)
   - [4.3 TextRenderer（文字排版引擎）](#43-textrenderer文字排版引擎)
   - [4.4 BackgroundFillManager（背景填充管理器）](#44-backgroundfillmanager背景填充管理器)
   - [4.5 RenderContext（渲染文本入口）](#45-rendercontext渲染文本入口)
   - [4.6 LogoSelector（Logo 选择器）](#46-logoselectorlogo-选择器)
   - [4.7 StyleManager（样式管理器）](#47-stylemanager样式管理器)
   - [4.8 DeviceMapper（设备映射）](#48-devicemapper设备映射)
5. [字体引擎](#5-字体引擎)
6. [GUI 架构](#6-gui-架构)
7. [关键设计模式](#7-关键设计模式)
8. [开发约定](#8-开发约定)

---

## 1. 技术栈

| 类别 | 技术 |
|------|------|
| 核心图像处理 | Pillow、NumPy |
| HDR 色调映射 | Reinhard 全局算子（NumPy 实现） |
| EXIF 处理 | piexif |
| GUI 界面 | PySide6 + QFluentWidgets |
| 配置解析 | PyYAML |
| 构建发布 | PyInstaller |

---

## 2. 项目结构

```
MiLecFrame/
├── src/
│   ├── core/                    # 核心处理逻辑
│   │   ├── image_processor.py   # 图像处理主逻辑（验证→HDR→EXIF→样式→渲染→保存）
│   │   ├── renderer.py          # 渲染引擎（图层合成，编排 TextRenderer + Logo + 装饰）
│   │   ├── text_renderer.py     # 文字排版引擎（测量→拓扑排序→定位→绘制）
│   │   ├── hdr_handler.py       # HDR 处理（HEIF/HEIC/AVIF 色调映射至 SDR）
│   │   ├── decorator.py         # 装饰元素（水印）
│   │   └── batch_processor.py   # CLI 批量处理
│   ├── utils/                   # 工具层
│   │   ├── exif_helper.py       # EXIF 数据提取与格式化
│   │   ├── device_mapper.py     # 设备映射数据库管理（CSV 读写）
│   │   ├── config_manager.py    # 用户配置持久化
│   │   ├── font_manager.py      # 字体加载（双字体引擎 + 缓存 + 系统回退）
│   │   ├── layout_engine.py     # 布局引擎（画布计算 + 绝对/相对定位 + 树级定位）
│   │   ├── background_fill.py   # 背景填充管理器（FILL_TYPES 注册表）
│   │   ├── logo_selector.py     # Logo 选择器（扫描 + 校验 + 自动匹配 + 缩放系数）
│   │   ├── gaussian_blur.py     # 高斯模糊（numpy float32 实现）
│   │   ├── render_context.py    # 渲染上下文（统一文本数据入口）
│   │   └── logging_config.py    # 日志配置
│   ├── gui_pyside/              # PySide6 原生桌面 GUI
│   │   ├── app.py               # QApplication 初始化 + Fluent 主题
│   │   ├── main_window.py       # FluentWindow 主容器 + NavigationInterface
│   │   ├── pages/               # 页面（图像处理、相机映射、镜头映射、样式编辑器）
│   │   ├── widgets/             # 可复用组件
│   │   ├── models/              # 数据模型（FileItem、ProcessingConfig、StyleConfigFormData）
│   │   └── utils/               # GUI 工具（临时文件管理、布局调试）
│   ├── gui_legacy/              # Streamlit GUI（已封存，保留可恢复）
│   ├── frame_styles/            # 样式系统
│   │   ├── configs/             # 样式配置文件（每种样式一个文件夹）
│   │   └── style_manager.py     # 样式管理器（加载 + 变体匹配）
│   └── main.py                  # 程序入口（默认启动 PySide6 GUI）
├── assets/
│   ├── logos/                   # Logo PNG 文件
│   └── fonts/                   # 字体文件（被 .gitignore，需自行放置）
├── data/
│   ├── camera_map.csv           # 相机品牌型号映射
│   ├── lens_map.csv             # 镜头映射（原始 → 映射 → 短版）
│   └── logo_scale.yaml          # Logo 品牌尺寸补偿系数
├── docs/
│   ├── STYLE_GUIDE.md           # 样式配置指南
│   └── DEVELOPMENT.md           # 本文件
├── tools/
│   └── release_sync.py          # 版本同步脚本（new-version / cherry / release / check）
├── MiLecFrame.spec              # PyInstaller 打包配置（onedir 便携版）
└── build_release.py             # 一键打包脚本（构建 / --zip 发行包 / 图标生成）
```

---

## 3. 整体数据流与处理管线

### 3.1 端到端处理流程

```
  1. 验证输入文件存在 + 格式支持
  2. HDR 检测 → HDRHandler 加载（保留 ICC profile）
  3. EXIF 提取（piexif + 多编码解码）→ 设备映射 → 记录到 camera_map.csv / lens_map.csv
  4. 尺寸验证 → 超限（>12000px）等比缩小
  5. 色彩空间检测 → 非 sRGB ICC 数学转换至 sRGB
  6. HDR 色调映射 → Reinhard 全局算子压缩动态范围（仅 HEIF/AVIF）
  7. 加载样式配置（StyleManager，含变体上下文匹配）
  8. 渲染相框（FrameRenderer，五阶段管线，见 §3.3）
     8a. 旋转适配前置：解析用户选项 + 样式默认值（预设仅限严格竖图
         整帧顺/逆时针 90° 转置（横图化渲染），见 §4.2.0
  9. 保存输出（JPEG/PNG，quality=95，optimize=True，嵌入原始 EXIF + sRGB ICC profile）
```

### 3.2 EXIF 数据流（四层架构）

数据自上而下流经四层，每层只依赖上一层的输出：

**① 提取层 —— `ExifHelper.extract_exif_data()`**

- piexif 解析原始 EXIF 二进制；`_safe_decode()` 多编码容错（utf-8 / latin-1 / gbk 等）
- 产出 `exif_data` 字典：`camera_make`、`camera_model`、`lens_model`、`focal_length`、`focal_length_35mm`、`aperture`、`shutter_speed`、`iso`、`datetime_original`、`gps` 等字符串字段
- 旁路：`_record_device_info()` 将未见过的设备自动追加到 `camera_map.csv` / `lens_map.csv`（独立 try/except，失败不影响提取结果）

**② 映射层 —— `DeviceMapper`**

- 以 `(original_brand, original_model)`、`original_lens` 为键查询映射库
- 输出 `mapped_brand` / `mapped_model` / `mapped_lens` / `short_lens`；无映射时回退原始值

**③ 组合层 —— `ExifHelper.get_display_data()`（统一数据出口）**

- `camera_combined`：映射后品牌 + 型号
- `camera_lens_combined`：相机 | 镜头 单行组合；`camera_lens_combined_short` 为竖幅/方形用的短版镜头变体
- `exif_formatted`：曝光组合文本（焦距/光圈/快门/ISO，由共享格式化方法组装，见 §7.7）
- `raw_*`：原始值透传，仅供 GUI 设备信息区展示

**④ 路由层 —— `RenderContext.get_text(key)`**

- 按样式 YAML `info_position` 声明的 key 分发最终显示文本，渲染器零改动
- 条件逻辑全部在此闭环：`lens_display_mode`（镜头显示模式）、`use_short_lens`（短版开关）、`timestamp_display_mode`（时间显示模式）、`timestamp_author`（时间+作者拼接）
- 曝光四元素键（`*_formatted`）直接转发 `ExifHelper` 共享格式化方法（同源约定见 [§7.7 渲染文本同源模式](#77-渲染文本同源模式)）

### 3.3 渲染管线（五阶段）

```
Phase 0 ── 旧式矩形绘制（背景层之上，原图层之下） ─────────────────
  仅处理未使用效果字段的 rectangles（legacy 分流见 §4.2.1）
  从 layout.rectangles 读取矩形列表 → 颜色自适应（is_dark_bg）
  → 尺寸计算（reference_side × ratio）
  → 定位（calculate_position + defer_padding，跳过 padding 约束）
  → RGBA 合成（_draw_single_rectangle → alpha_composite）
  效果栈矩形不在此绘制（原图上方，见 §4.2.1 / §4.2.2 / §4.2.3）

Phase 1 ── 测量 ─────────────────────────────────────────────────
  遍历 info_position / defined_texts / custom_text 三种来源的所有元素
  → 获取文本 → 确定字体 → 测量尺寸（font.getbbox + font.getmetrics）
  → 确定颜色（三级优先级） → 存入 draw_items

Phase 2 ── 定位 + 注册 ──────────────────────────────────────────
  拓扑排序（Kahn 算法） → 预注册缺失锚点 → 逐个计算绝对/相对位置
  → 存入 layout_engine.positions 注册表
  → 组合盒约束 + 级联平移（defer_padding 控制是否跳过）

Phase 2.5 ── 树级组合定位（仅 tree_align: true 的根元素执行）───
  收集树成员 → 计算视觉包围盒 → 用根配置的绝对定位公式计算目标位置
  → 级联平移整棵树 → padding 约束

Phase 3 ── 绘制 ─────────────────────────────────────────────────
  按拓扑序从 positions 读取最终坐标 → 单字体/混排/多行各自绘制
```

---

## 4. 核心模块详解

### 4.1 LayoutEngine（布局引擎）

`src/utils/layout_engine.py`

#### 4.1.1 坐标系统

| 概念 | 变量 | 定义 |
|------|------|------|
| 原图尺寸 | `image.size` | 输入图像的 `(w, h)` |
| 参照边 | `reference_side = min(w, h)` | 所有浮点比例系数的除数 |
| 画布 | `canvas_size` | 经 `expand_canvas` 扩展后的总尺寸 |
| 原图边界 | `original_bounds = (ox, oy, ow, oh)` | 原图在画布中的位置 |
| 安全区域 | `padding_bounds` | 从画布四边向内收缩的矩形 |

画布扩展计算：
```python
new_w = original_w + reference_side * (left_exp + right_exp)
new_h = original_h + reference_side * (top_exp + bottom_exp)
ox = int(reference_side * left_exp)
oy = int(reference_side * top_exp)
```

#### 4.1.2 位置注册表（positions）

```python
self.positions = {
    'camera_lens': {'x': 150, 'y': 3337, 'width': 250, 'height': 40},
    'logo':        {'x': 4000, 'y': 3150, 'width': 120, 'height': 60},
}
```

**y 坐标统一语义**：`positions` 中所有元素（文字/Logo/锚点）的 y 统一表示**包围盒顶部（bounding box top）**。这一设计来自 v1.7.0 重构，此前 Phase 2 注册时做 `y -= descent` 将坐标转为基线，导致 `_calculate_relative` 需要大量 ascent 校正。统一后坐标语义清晰：`ty + th = 视觉底部`，无需额外校正。

基线转换仅在 Phase 3 绘制时单点完成：
- 单字体：`draw_y = y - descent`
- 混排：`baseline_y = y + ref_ascent - ref_descent`

#### 4.1.3 依赖图（_dependents）

```python
self._dependents = {
    'camera_lens': ['timestamp_author', 'location'],
}
```

用途：拓扑排序（确定处理顺序）、组合盒扩展、级联平移、树成员收集（BFS）。

#### 4.1.4 方法索引

| 方法 | 类别 | 作用 |
|------|------|------|
| `__init__(size, layout_config)` | 构造 | 计算 canvas_size、original_bounds、padding_bounds |
| `register_element(name, x, y, w, h, relative_to)` | 注册 | 存入 positions + 维护 _dependents |
| `get_element_bounds(name)` | 查询 | 从 positions 读取（支持模糊匹配） |
| `calculate_position(w, h, config, defer_padding)` | 分发 | 根据有无 relative_to 分支到绝对/相对；defer_padding=True 跳过 padding 约束 |
| `_calculate_absolute(w, h, config, defer_padding)` | 绝对定位 | 按 position/alignment/placement/margin 计算；defer_padding=True 时跳过 padding 夹持 |
| `_validate_position(value)` / `_validate_alignment(value)` | 校验 | 只接受九点规范值，未知值（含旧别名）抛 ValueError |
| `_resolve_photo_reference_point(position)` | 绝对定位 | position → 照片九点参考点（不接收元素尺寸） |
| `_resolve_element_anchor(config)` | 绝对定位 | 照片参考点 + margin/placement → 元素锚点（不接收元素尺寸） |
| `_resolve_alignment_offset(alignment, ew, eh)` | 绝对定位 | alignment → 布局盒对齐点偏移（不读取照片/margin） |
| `_place_element_box(ew, eh, config)` | 绝对定位 | 布局盒对齐点贴元素锚点，返回 raw 左上角 |
| `_clamp_box_to_padding(x, y, ew, eh)` | 绝对定位 | 集中 padding 夹持，返回 (final, delta) |
| `get_absolute_layout_info(ew, eh, config)` | 诊断 | 只读返回 photo_ref/anchor/offset/raw，供日志 |
| `_resolve_margins(config)` | 绝对定位 | margin 解析（统一值 → 方向覆盖） |
| `_validate_cross_alignment(rp, ca)` | 相对定位 | cross_alignment 与方向轴匹配校验 |
| `_calculate_relative(w, h, config)` | 相对定位 | 只读 cross_alignment；目标不可解析时抛错不回退 |
| `_shift_dependents(name, sx, sy)` | 级联 | 递归平移所有子孙 |
| `_resolve_element_order(elements, configs)` | 排序 | Kahn 算法拓扑排序 |
| `_collect_tree_members(root, members)` | 树定位 | BFS 遍历收集依赖树成员 |
| `_shift_tree_members(members, sx, sy)` | 树定位 | 整树统一平移 |
| `_compute_visual_bounds(members)` | 树定位 | 计算一组元素的视觉包围盒 |
| `apply_tree_positioning(all_positions)` | 树定位 | 整树包围盒 = 普通盒子走统一盒定位 |

#### 4.1.5 文字基线系统

Pillow 的 `draw.text((x, y), text, font=font)` 将 `(x, y)` 解释为**基线的左上角**：

```
                ───── top_of_glyphs = baseline - ascent
               │       ┌───┬───┬───┐
  baseline ════╪═══════╪═══╧═══╪═══╪══════
               │       └───────┴───┘
               ───── bottom_of_glyphs = baseline + descent
```

| 属性 | 获取方式 | 含义 |
|------|---------|------|
| `ascent` | `font.getmetrics()[0]` | 基线到最高字形顶部（px） |
| `descent` | `font.getmetrics()[1]` | 基线到最低字形底部（px） |

布局引擎返回的是包围盒顶部 y，绘制时需减去 descent 得到基线 y（单字体）或加上 `ref_ascent - ref_descent`（混排）。

#### 4.1.6 绝对定位算法

定位语义分三步，每步输入互不越界（详见执行方案
`docs/plans/POSITION_ALIGNMENT_REPAIR_EXECUTION_PLAN.md` §3）：

1. **`_resolve_photo_reference_point(position)`**：position → 照片九点参考点
   `(px, py)`。输入只有照片几何，禁止读取元素宽高。
2. **`_resolve_element_anchor(config)`**：在参考点上应用 margin/placement
   得到元素锚点 `(ax, ay)`。顶部/底部三点沿上下主轴内外平移；
   `center-left`/`center-right` 沿水平主轴内外平移；`center` 始终基于
   原照片中心（忽略 placement）。margin 的职责到此结束。
3. **`_resolve_alignment_offset(alignment, ew, eh)`** → `_place_element_box()`：
   alignment 只根据元素尺寸计算布局盒对齐点偏移 `(dx, dy)`
   （中心一律 `// 2` 向左/上取整，全模块统一不与 round 混用），
   `raw = anchor - offset`。

```python
raw_x, raw_y = _place_element_box(ew, eh, config)   # 步骤 1-3
if not defer_padding:                                # 步骤 4：集中 padding 夹持
    x, y, dx, dy = _clamp_box_to_padding(raw_x, raw_y, ew, eh)
```

`defer_padding=True` 时跳过步骤 3 的 padding 夹持，用于需要突破安全区域的场景。当前使用方：
- `tree_align` 依赖树内的元素（Phase 2 以 defer 模式定位，Phase 2.5 统一约束）
- **自定义矩形（rectangles）**——矩形不受 padding 安全区域限制，可直接绘制到画布边界

margin 解析两阶段：
1. `config['margin']` → 四边初始值（未设 → 0）。float → `int(reference_side * ratio)`，int → 直接使用。
2. `config['margin_top']` 等方向覆盖。四个方向各自独立，设了几个覆盖几个。

定位 DEBUG 日志（渲染器输出）：`[Layout] name=... position=... placement=...
alignment=... photo_ref=(..) anchor=(..) self=(..) raw=(..) final=(..)
clamp=(..)`；padding 修正发生在 LayoutEngine 内部且仅非零时记一条 clamp DEBUG。

#### 4.1.7 相对定位算法

相对定位只读取 `cross_alignment` 字段（三值交叉轴），不读取绝对定位的
九点 `alignment`；`relative_position` 只接受 `below` / `above` /
`right-of` / `left-of`（旧 `after`/`before` 已删除）。字段缺失、枚举非法、
轴向不匹配、`relative_to` 目标不可解析均直接抛 ValueError，不回退绝对定位。

核心公式（positions 统一存储包围盒顶 y 后，`ty + th` = 参考视觉底部）：

| 方向 | 交叉轴合法值 | x 公式 | y 公式 |
|------|------|--------|--------|
| `below` | left/center/right | 参考宽度内对齐 | `ty + th + margin_px` |
| `above` | left/center/right | 参考宽度内对齐 | `ty - eh - margin_px` |
| `right-of` | top/center/bottom | `tx + tw + margin_px` | 参考高度内对齐 |
| `left-of` | top/center/bottom | `tx - ew - margin_px` | 参考高度内对齐 |

组合盒约束与级联平移（§4.1.8）保持不变，平移发生时输出一条
`[Relative]` DEBUG 日志（含 relative_to/方向/交叉轴/平移量）。

#### 4.1.8 组合盒约束与级联平移

当相对定位放置元素时，将当前元素与参考元素（及其全部从属）合并为组合盒。若组合盒超出 padding，整体平移保持对齐关系不变：

```python
group_top = min(ty, y)           # 所有成员合并包围盒
group_bottom = max(ty + th, y + eh)
if group_top < pad_top:
    shift_y = pad_top - group_top
    _shift_dependents(ref_key, 0, shift_y)  # 级联平移
```

`_shift_dependents(name, sx, sy)` 沿依赖图递归传播平移量。

`tree_align` 链内元素传 `defer_padding=True`，跳过此阶段，改由 Phase 2.5 统一处理。

#### 4.1.9 拓扑排序

Kahn 算法实现：从 `relative_to` 构建有向边 `ref → name`，入度为 0 的元素（无依赖的根）先被处理，BFS 展开。循环依赖兜底按原序追加。

#### 4.1.10 树级组合定位（Phase 2.5）

**唯一算法：整树包围盒 = 普通盒子**（不再有第二套 position/alignment
解释器；旧 `_resolve_tree_ref` 已删除）：

```
1. 识别根元素：无 relative_to + tree_align: true + 未被其他树处理过
2. 收集树成员（含单成员树——与普通元素同公式，保证一致性）
3. 计算树的视觉包围盒（所有成员合并）
4. 用根配置 + tree_w/tree_h 调用 _place_element_box() 得 raw 目标左上角
5. shift = 目标左上角 - 当前树包围盒左上角
6. _shift_tree_members 整树平移（父子相对位置不变）
7. 重算包围盒
8. 对整树执行一次 padding 夹持（全部成员平移相同 delta）
```

每棵树输出一条 DEBUG：`[TreeLayout] root=.. members=..
bounds_before=(..) target=(..) shift=(..) clamp=(..)`。


#### 4.1.11 原图圆角裁切

`_rounded_corner_mask(w, h, r_tl, r_tr, r_bl, r_br)` 使用 **numpy SDF（signed distance field）** 生成抗锯齿蒙版：

```python
mask = np.full((h, w), 255, dtype=np.float32)
iy, ix = np.ogrid[:r_tl, :r_tl]
dist = np.sqrt((ix - r_tl) ** 2 + (iy - r_tl) ** 2)
mask[:r_tl, :r_tl] = np.clip(r_tl - dist + 0.5, 0, 1) * 255
```

`np.clip(r - dist + 0.5, 0, 1)` 在圆弧边界产生 1px 线性过渡（内侧 α=1.0，外侧 α=0.0），消除像素级硬边锯齿。仅处理四角 r×r 区域（如 r=50 时仅 10000 像素），不扫描全图。

合成流程：`image.convert('RGBA')` → `putalpha(mask)` → 以自身 alpha 为遮罩 `paste()` 到背景。

兼容性：与 `expand_canvas`、`padding`、高斯模糊背景、文字/Logo 层均兼容；渲染顺序在原图粘贴阶段。

### 4.2 FrameRenderer（渲染器）

`src/core/renderer.py`

#### 4.2.0 旋转适配（整帧前置旋转 / 输出还原）

规则解析与旋转实现收敛在 `src/utils/orientation_adaptation.py`（渲染器不自带规则）：

```text
用户选项 RenderOptions.portrait_adaptation（default/none/clockwise/counterclockwise）
  × 样式默认值 style_config.default_portrait_adaptation（clockwise/counterclockwise/none，缺失=none）
  → (有效方向, 来源) = 用户显式值优先，default 时取样式默认值
  → 旋转的图片方向适用范围按来源区分：
     用户显式选择 → 所有图片（横图/竖图/方形图）整帧旋转
     样式预设     → 仅转正后 height > width 的竖图旋转
  → 有效方向非 none 且适用范围命中：
     前置 transpose(ROTATE_270 顺时针 / ROTATE_90 逆时针)
     → LayoutEngine/RenderContext/全部渲染阶段按旋转后尺寸执行
     → 唯一返回点 restore_rendered_orientation() 反向转置还原
```

- 旋转是离散转置（无插值损失）；未适配路径零复制（原图引用直通）。
- 判断发生在 `ImageProcessor._apply_exif_orientation()` 转正之后，Orientation=6/8 竖拍图不会误判。
- 高斯二级缓存键按有效方向派生局部后缀（`:portrait-adapt-cw` / `:portrait-adapt-ccw`，见 §4.2.2），不回写共享 `RenderOptions`。
- 样式编辑器预览构造的 `RenderOptions` 不覆盖该字段（默认 `default`），预览自动展示样式声明的默认适配效果。

图层合成顺序（v2.6 起）：

```text
背景填充（可短路为纯色替代，见 §4.2.3）
  → 旧式纯色矩形（未用效果字段的 rectangles，原图下方，兼容旧样式）
  → 原图/原图圆角（base_scene 形成）
  → 效果栈矩形（模糊 → 填充 → 内描边；原图上方，按 key 排序后画覆盖先画）
  → 装饰（水印） → 文字（委托 TextRenderer） → Logo
```

渲染参数经 `RenderMetadata`（拍摄信息）+ `RenderOptions`（行为选项）两个
dataclass 打包传入；`RenderOptions` 是后续新增渲染参数的唯一定居点。

#### 4.2.1 矩形分流（legacy vs 效果栈）

```text
legacy_mode       = fill 字段缺失 and stroke.enabled != true and gaussian_blur.enabled != true
effect_stack_mode = not legacy_mode
```

- legacy 矩形走 `_draw_rectangles()`（原图下方），历史输出像素不变。
- 效果栈矩形走 `_analyze_rectangles()`（需求分析）+ `_draw_rectangle_effect_stack()`（三层合成）。
- `_analyze_rectangles()` 在背景渲染前执行：几何分类（`source_kind`：photo=矩形 ⊆ original_bounds / canvas=跨界或照片外）、画布交集裁切、三层参数独立校验与降级、描边色四级回退链、模糊需求登记。
- 三层合成要点：局部 patch 内混合、仅经 `outer_mask` 一次组裁切（alpha 只写一次，防透明度平方）；填充 opacity 只乘填充层（防"25% 模糊 + 25% 着色"双重着色）；模糊源冻结取自原图卷积缓存，不含已绘制的效果栈矩形（顺序无关）。

#### 4.2.2 两级模糊缓存

```text
gaussian_blur.py（纯算法）     prepare_gaussian_blur / render_prepared_blur / apply_color_overlay
RenderBlurCache（一级，每帧）  帧内 (source_kind, radius) 懒卷积 + 派生缓存 + 命中统计
PreparedBlurLRU（二级，跨帧）  页面级持有；按 nbytes 预算（默认 64 MiB）的 LRU；
                               仅存 photo 源 PreparedBlur（工作分辨率 float32）
```

二级缓存完整键（`build_l2_key()`）：

```text
(source_cache_key, normalized_image_size, normalized_image_mode,
 preprocessing_version, blur_radius, gaussian_algorithm_version)
```

- `source_cache_key`：FileItem 导入时对 `file_bytes` 一次性 sha256 前 16 hex；样式编辑器样本图为 `preview:{orientation}`（横/竖不同键）。禁止临时路径或 PIL 对象身份。方向适配真实生效时，`render_frame()` 内以局部派生键 `原键:portrait-adapt-cw / :portrait-adapt-ccw` 查询/写入（CW/CCW 旋转后尺寸相同，仅靠后缀隔离；不回写调用方持有的 `RenderOptions.source_cache_key`）。
- `preprocessing_version`（常量 "1"）覆盖 EXIF 转正 / ICC / 超尺寸缩放规则，预处理逻辑变更时递增；`gaussian_algorithm_version` 同理。
- 背景类型/叠色/透明度/饱和度/画布尺寸/矩形位置**不进键**（发生在卷积之后，切换应命中并仅重新派生）。
- 接入位置：主处理页（`ImageProcessingPage._blur_lru`，页面级复用 `ImageProcessor`）与样式编辑器页（`StyleCreatorPage._blur_lru`）；页面 `cleanup()` 清空。
- 批量处理（`batch_processor.py`）不传 LRU，仅一级缓存——连续处理不同照片时避免无效内存驻留。
- `source_kind='base_scene'`（精确型/方案 B）为接口预留位，传入 `get_prepared()` 抛 `NotImplementedError`；精确型未来也只允许一级缓存。

#### 4.2.3 全图高斯需求统一短路

`_compute_gaussian_required()` 在渲染前汇总整张输出图的高斯消费者：

```text
gaussian_required = background_blur or 存在有效模糊矩形

background_blur   = 背景类型为 gaussian and 背景可见
背景可见          = original_bounds != 全画布 or 原图圆角(任一半径>0) or image.mode == 'RGBA'（保守）
```

- `gaussian_required == False` 且背景为高斯类型：背景被原图完全覆盖，用与 `text_scheme` 匹配的黑/白纯色替代（输出像素不变），整帧零卷积。顺带修复"高斯背景 + 无画布扩展仍全量模糊"的既有浪费（33MP 样片 2.64s → 0.095s）。
- 矩形模糊需求已在分析阶段过滤：画布外矩形、被 `opacity>=1` 有效填充完全覆盖的模糊层不登记。

#### 4.2.4 性能基准（v2.6.0-dev，Phase 6 总验收记录）

测量环境：开发机（Windows x64），`FrameRenderer.render_frame()` 单帧计时
（`perf_counter`），完整高斯路径 = 高斯背景 + 真实画布扩展；短路路径 =
高斯背景 + 四边零扩展 + 无圆角（`gaussian_required=False`，纯色替代）。
峰值内存为进程工作集峰值增量（`GetProcessMemoryInfo.PeakWorkingSetSize`）。

| 样片档 | 完整高斯路径 | 短路路径 | 峰值内存增量 |
|---|---:|---:|---:|
| 1200×800（预览档） | 0.67 s | 0.011 s | +79 MiB |
| 6000×4000（样片档） | 1.44 s | 0.075 s | +1696 MiB |
| 7008×4672（33MP 基准档） | 1.71 s | 0.100 s | +771 MiB（进程累计峰值 2.6 GiB） |

对照：33MP 高斯背景端到端历史观测值约 **2.64 s**（设计文档 §1，含旧版
全量模糊路径）；当前完整路径 1.71 s，短路路径 0.10 s（约 17-27 倍提升）。

**`blur plan` DEBUG 日志**（单帧计划，`debug_log.txt`）：

```text
blur plan: gaussian_required=True, background_blur=True, photo_radii=[200], scene_radii=[]
blur cache hit: level=L2, source_key=preview:landscape, source=photo, radius=200
blur cache miss: level=L2, source_key=file:9f2a..., source=photo, radius=200 (convolutions=1)
blur cache: prepared hit/miss=2/1 (L2 hit/miss=1/1), derived hit/miss=0/3, convolutions=1
rectangle rect_01: source=photo, box=(x, y, w, h), blur_radius=200, fill=True/0.65, stroke=True/5px/0.60
```

**`_draw_rectangles()` 矩形绘制管线**（legacy 路径）：

1. 从 `layout.rectangles` 读取矩形字典，按键名排序遍历
2. 颜色自适应：根据 `BackgroundFillManager.is_dark_bg()` 从 `colors` 中读取 `custom_{rect_name}_{dark/light}_color`
3. 尺寸计算：`rect_w = reference_side × width_ratio`，`rect_h = reference_side × height_ratio`
4. 定位计算：调用 `layout_engine.calculate_position(w, h, config, defer_padding=True)`，**跳过 padding 约束**
5. 圆角处理：复用 `_rounded_corner_mask()` 生成抗锯齿圆角蒙版，蒙版值乘以 opacity 保留透明度
6. 图层合成：创建 RGBA 矩形层 → `Image.alpha_composite()` 叠加到背景

**`_draw_single_rectangle()` 模块级函数**：创建 RGBA 矩形图像，处理圆角蒙版（通过 `putalpha`），通过 `alpha_composite` 叠加到背景层返回 RGB 图像。透明度由 `opacity` 参数控制（0.0-1.0），圆角蒙版的值也乘以 opacity 因子以保持透明度语义一致。

**矩形定位的特殊处理**：矩形调用 `calculate_position(..., defer_padding=True)` 跳过 padding 约束，因此矩形可以超出 `padding` 安全区域绘制到画布边界。详见 [§4.1.6 绝对定位算法](#416-绝对定位算法)。

注意：`_draw_single_rectangle` 中 `rect_layer.paste(rect_img, position)` **不传 mask 参数**——RGBA 的 alpha 通道本身就作为遮罩，再传自身作 mask 会导致 alpha 被平方（透明度 0.5 → 0.25）。

**`_add_logo()` Logo 尺寸约束链**：

1. 基础缩放：`scale = (reference_side × size_ratio) / logo_short_side`
2. 长边限制：若 `logo_long_side × scale > reference_side × limit_ratio × size_ratio`，重新按长边上限计算 scale
3. 品牌补偿：`scale *= LogoSelector.get_brand_scale_factor(logo_filename)`

调用链：`renderer → LogoSelector(logo_scale.yaml) → get_brand_scale_factor()`

### 4.3 TextRenderer（文字排版引擎）

`src/core/text_renderer.py`

**三源文本收集**：
- `info_position` 的 key → `context.get_text(key)`（EXIF/用户输入）
- `defined_texts` → 配置中写死的 `content`
- `custom_text` → `context.get_text('custom_text')`（GUI 输入）

**三阶段处理**（TextRenderer 参与 Phase 1/2/3，整体管线见 [3.3 渲染管线（五阶段）](#33-渲染管线五阶段)）：

1. Phase 1 测量：逐元素检测混排（CJK 检测正则 `_CJK_CHAR_RE`），单字体用 `font.getbbox`，混排用分段测量合并包围盒
2. Phase 2 拓扑排序 + 定位：Kahn 算法 → 逐个 `calculate_position()` → `register_element()`
3. Phase 3 绘制：从 `positions` 读取最终坐标，根据单字体/混排/多行选择对应绘制路径

**多行文本**：按 `\n` 分割，逐行测量宽度和高度，行间距 = `reference_side × line_spacing_ratio`。Phase 3 中逐行绘制，行内缩进由 alignment 控制。

### 4.4 BackgroundFillManager（背景填充管理器）

`src/utils/background_fill.py`

**FILL_TYPES 注册表**是所有背景填充类型的唯一入口：

```python
FILL_TYPES = {
    'pure_black': {
        'label': '纯黑背景', 'method': 'solid',
        'color': (0, 0, 0), 'text_scheme': 'dark'
    },
    'gaussian_white_80': {
        'label': '模糊背景 (浅色 80%)', 'method': 'gaussian',
        'overlay_color': 'white', 'opacity': 80, 'blur_radius': 200,
        'saturation': 2.0, 'text_scheme': 'light'
    },
}
```

**纯色（solid）方法**：在扩展画布上填充纯色。
**高斯模糊（gaussian）方法**：3-pass Box Blur 近似（O(n)），全分辨率等效半径 200px，大图自动降采样至 1200px 计算。float32 混合 + Floyd-Steinberg 量化消除色彩断层。可选饱和度增强补偿覆盖层颜色淡化。

关键 API：
- `get_choices()` → `{label: key}` 供 GUI 下拉框
- `get_keys()` → key 列表供 CLI argparse
- `is_dark_bg(key)` → 根据 `text_scheme` 判断，供渲染器自动适配文字颜色和矩形颜色
- `register_custom_solid(color, text_scheme)` → 动态注册自定义纯色并返回 key（v2.1.0 预留接口）

新增背景类型只需在 `FILL_TYPES` 中注册，GUI 下拉和 CLI 自动同步。

### 4.5 RenderContext（渲染文本入口）

`src/utils/render_context.py`

`get_text(key)` 根据样式 YAML 中 `info_position` 声明的 key 返回最终显示文本，内部闭环所有条件逻辑：

| key | 内部字段来源 | 条件路由 |
|-----|------------|---------|
| `exif` | `display_data['exif_formatted']`（由共享格式化方法组装） | — |
| `timestamp` | `exif_data['datetime_original']` | `timestamp_display_mode`: `full` → 完整时间，`date_only` → `[:10]` 切片，`hide` → `None` |
| `timestamp_author` | datetime + author | 三段 fallback：时间+作者 / 仅时间 / 仅作者 / None |
| `camera_lens` | `camera_lens_combined` / `camera_lens_combined_short` / `camera_combined` | 由 lens_display_mode + use_short_lens 控制 |
| `camera` | `display_data['camera_combined']` | — |
| `camera_make` | `display_data['camera_make']` | — |
| `lens` | `lens_model` / `short_lens` | use_short_lens 控制 |
| `focal_length_formatted` | `ExifHelper.format_focal_length()`：35mm 等效优先 → 物理焦距取整个位数（`'70.0'`→`'70mm'`） | — |
| `aperture_formatted` | `ExifHelper.format_aperture()` → `f/5.6` | — |
| `shutter_speed_formatted` | `ExifHelper.format_shutter_speed_text()` → `1/800s` | — |
| `iso_formatted` | `ExifHelper.get_iso_value()` → 裸值 `250` | 不含 "ISO" 前缀（前缀由样式标签元素或组合文本承担） |

**新增显示字段指南**：在 `get_text()` 中添加 `elif key == 'xxx':` 分支 → 在 YAML 的 `info_position` 中声明配置。渲染器零改动。曝光类数值（焦距/光圈/快门/ISO）的格式化必须复用 `ExifHelper` 共享方法（见 [§7.7](#77-渲染文本同源模式)），禁止在分支内另行拼接。

### 4.6 LogoSelector（Logo 选择器）

`src/utils/logo_selector.py`

公开 API：

| 方法 | 功能 |
|------|------|
| `scan_logos()` | 遍历 `assets/logos/` 目录下所有 PNG 文件 |
| `validate_logo(path)` | 验证文件为 PNG 格式 |
| `auto_match_logo(brand, is_dark_bg)` | 逐词子串匹配相机品牌 → 选择 PNG 文件 → 根据背景明暗筛选颜色变体 |
| `get_brand_scale_factor(filename)` | 从 `data/logo_scale.yaml` 读取匹配的补偿系数，默认 1.0 |

品牌补偿系数加载：`__init__()` → `_ensure_scale_file_exists()`（YAML 不存在时自动创建默认文件）→ `_load_scale_factors()`（yaml.safe_load + 类型校验 + 错误 fallback 为空字典）。

### 4.7 StyleManager（样式管理器）

`src/frame_styles/style_manager.py`

- `get_available_styles()` → 扫描 `configs/` 下所有文件夹，返回排序列表
- `get_style_config(style_name, context)` → 加载 YAML → `_resolve_style_variant()` 自动匹配最佳变体
- `get_style_thumbnail(style_name)` → 在样式文件夹内查找 `thumbnail.png/jpg`

**变体匹配算法**：从 context 提取缺失字段集合 → 扫描文件夹内变体文件（排除 `default.*`）→ 选择缺失字段集是实际缺失子集且匹配数最多的变体 → 无匹配回退 `default.*`。

### 4.8 DeviceMapper（设备映射）

`src/utils/device_mapper.py`

- `_ensure_dbs_exist()` → 文件不存在时自动创建带表头的 CSV（UTF-8 with BOM）
- `_load_camera_map()` → 读取 `(original_brand, original_model) → {mapped_brand, mapped_model}`
- `_load_lens_map()` → 读取 `original_lens → mapped_lens`
- `_load_short_lens_map()` → 读取 `original_lens → short_lens`（缺省回退 mapped_lens）
- GUI 中通过 `TableView` 可编辑表格，实时保存回 CSV

**CSV 编码约定**：`camera_map.csv` / `lens_map.csv` 统一为 **UTF-8 with BOM（`utf-8-sig`）**，保证中文 Windows 的 Excel 双击打开时按 UTF-8 解码（否则 `α` 等非 ASCII 字符会被 GBK 误解为乱码，如 `α` → `伪`）：

- 读点一律用 `utf-8-sig`（自动剥离 BOM，兼容无 BOM 的历史文件）
- 整文件重写（GUI 保存、新建数据库）用 `utf-8-sig` 写出 BOM
- ⚠️ 追加（`'a'`）模式必须保持 `utf-8`：`utf-8-sig` 编码器在追加时会再次写出 BOM，破坏文件结构（`ExifHelper._record_device_info` 的设备自动记录即此场景）

---

## 5. 字体引擎

`src/utils/font_manager.py`

### 双字体架构

| 组件 | 说明 |
|------|------|
| 字体对 | Latin: `Gotham-{weight}`；CJK: `GlowSansSC-Normal-{weight}` |
| CJK 检测 | 正则 `_CJK_CHAR_RE` 覆盖中日韩码位（U+4E00–U+9FFF、假名 U+3040–U+30FF 等） |
| 拆分函数 | `split_mixed_text(text)` → `[(segment, is_cjk), ...]` |
| 缓存键 | `(font_family, font_weight, font_size, is_cjk)` → `FreeTypeFont` 实例 |
| 字号下限 | `max(12, int(reference_side * size_ratio))` |
| 系统回退 | Windows: Segoe UI (Latin) + Microsoft JhengHei UI (CJK) |

### 混排基线对齐

以 Latin 字体的基线为共享参考，所有片段共用同一基线：

```python
ref_font = drawn_fonts.get('latin') or drawn_fonts.get('cjk')
ref_ascent, ref_descent = ref_font.getmetrics()
shared_baseline = y + ref_ascent   # 布局引擎返回包围盒顶

for seg_text, font, width, ascent, descent in seg_info:
    seg_y = shared_baseline - ascent  # 各片段基线对齐
    draw.text((current_x, seg_y), seg_text, ...)
```

```
               ┌────┐
               │    │
  ─────────────╪────╪──────────────  ← 共享基线（Gotham baseline）
               │    │
               └────┘
  ↑             ↑
  ref_ascent    CJK_ascent（可能更高，字形向上延伸但不影响基线）
```

---

## 6. GUI 架构

`src/gui_pyside/`

### 主框架

- `FluentWindow` 主窗口 + 左侧 `NavigationInterface` 导航栏
- `QStackedWidget` 页面路由：图像处理 / 相机映射 / 镜头映射 / 样式编辑器

### 图像处理页面

布局：`QSplitter` 垂直分割（主内容区 80% + 胶片栏 20%），主内容区再水平分割（预览 55% + 配置栏 45%）。

配置面板 5 个 `ExpandGroupSettingCard` 折叠 Tab：

| Tab | 关键控件 |
|-----|---------|
| 输出设置 | 输出格式 ComboBox |
| 相框配置 | 样式选择器（横向缩略图滚动）、背景填充 ComboBox、背景增强 SwitchButton、字重 ComboBox |
| 个性化配置 | 作者姓名 LineEdit、拍摄地点 LineEdit、GPS 替换 CheckBox、自定义文本 TextEdit |
| 拍摄信息配置 | 镜头显示 ComboBox、短版镜头 CheckBox、时间显示模式 ComboBox、Logo 选择 ComboBox |
| 文本水印 | 水印内容/位置/不透明度/颜色 |

### 样式编辑器

- `QSplitter` 水平分割：左侧 10 个 `ExpandGroupSettingCard` 折叠卡片 + `Pivot` 快速导航 → 右侧实时预览
- 数据模型：`StyleConfigFormData` `@dataclass`，`to_yaml_dict()` / `from_yaml_dict()` / `save_to_file()`
- 实时预览：300ms `QTimer.singleShot` debounce，复用 `FrameRenderer.render_frame()`，预置 `PREVIEW_EXIF_DATA` 跳过 EXIF 解析，1200px 样本图渲染 < 200ms

---

## 7. 关键设计模式

### 7.1 FILL_TYPES 注册表模式

所有背景填充类型在 `BackgroundFillManager.FILL_TYPES` 中集中定义。新增类型只需注册，GUI 下拉和 CLI 自动同步。禁止在 renderer.py 或 GUI 中硬编码背景选项。

### 7.2 RenderContext 解耦模式

渲染器通过 `context.get_text(key)` 获取文本，不直接接触 EXIF 数据。数据准备逻辑（相机合并、镜头切换、时间格式化）全部在 RenderContext 内部闭环。

### 7.3 变体自动匹配模式

`StyleManager._resolve_style_variant()` 根据运行时上下文自动选择最佳变体。`hide` 模式下注入 `context['timestamp'] = None` 使变体系统原生匹配 `no_timestamp.yaml`。

### 7.4 外部数据文件模式

设备映射（`camera_map.csv`、`lens_map.csv`，UTF-8 with BOM，编码约定见 [§4.8](#48-devicemapper设备映射)）和 Logo 补偿系数（`logo_scale.yaml`）均存储为可编辑的外部文件，程序自动创建默认值。用户修改即生效，无需重新编译。

### 7.5 配置持久化

`ConfigManager` 保存/加载 `config.json`（作者名自动记忆 + 最近四项配置）。GUI 关闭时通过 `save_config()` 自动持久化。

### 7.6 ExpandGroupSettingCard 开发铁律

在 `ExpandGroupSettingCard` 内添加自定义内容时必须：

1. 通过 `addGroupWidget()` 或 `addGroup()` 添加子控件，**禁止直接操作 `self.viewLayout.addWidget()`**
2. 子控件的 `sizeHint().height()` 必须能反映真实视觉高度
3. `QScrollArea` / `SmoothScrollArea` 的 `sizeHint()` 不反映 `setFixedHeight()`，需覆盖 `_adjustViewSize()`
4. 动态添加/删除子控件后调用 `QTimer.singleShot(0, self._adjustViewSize)`
5. 开发完成后调用 `layout_debug.dump_expand_card(self)` 验证

### 7.7 渲染文本同源模式

exif 组合文本（`ExifHelper.format_exif_for_display()`）与 RenderContext 的四个
`*_formatted` 单独元素键共用 `ExifHelper` 的共享格式化方法（`format_focal_length`
/ `format_aperture` / `format_shutter_speed_text` / `get_iso_value`），同一数据在
所有渲染元素中的取值与格式完全一致，任何格式调整只需修改对应的一个方法。

组合文本与单独键的唯一差异是 ISO 前缀：单独键返回裸值（前缀由样式标签元素
承担，如 FilmClip 的 `defined_text: "ISO"`），组合文本带 `ISO` 前缀（组合文本
没有样式标签承担该职责）。

新增曝光类显示需求时必须复用共享方法，禁止在 `get_text()` 或组合文本中另行
实现格式化，否则各渲染元素的数值输出会漂移（曾因两处独立拼接导致同一焦距
一处显示 `70mm`、另一处显示 `70.0mm`）。

---

## 8. 开发约定

### 8.1 环境与命令

- 所有开发在 venv 中：`.\venv\Scripts\activate`（Windows PowerShell）
- 校验：`python -m py_compile <文件>` 检查语法
- 调试：DEBUG 级别日志写入 `debug_log.txt`（项目根目录），INFO 及以上输出到 stderr

### 8.2 版本管理

- `src/_version.py` 是版本号**单点入口**
- **版本同源**：mainline 用 `vX.Y.Z-dev`（内部开发版），release 用 `vX.Y.Z`
  （公开发行版，同号去掉 `-dev` 后缀；自 v2.4.0 起对齐，不再有独立 release 编号序列）
- **一个版本 = 一个 commit + 一个 tag**：修复走 patch 号递增（`v2.4.0-dev`→`v2.4.1-dev`），禁止"增补" commit 堆积
- 版本语义遵循 SemVer：新增功能递增 minor（`v2.4.0`→`v2.5.0`），破坏性变更（`feat!`/`BREAKING CHANGE:`）递增 major（`v2.5.0`→`v3.0.0`）
- tag 规范：内部版本 tag（`vX.Y.Z-dev`）为轻量 tag；公开发行 tag（`vX.Y.Z`）为注解 tag（消息 = 发行说明），发行 commit 的父**锚定 mainline 对应版本 commit**
- 版本号变更时同步更新 `README.md` 徽标与 `CHANGELOG.md`；公开发行还需更新 `CHANGELOG_RELEASE.md`（**三个分支都要同步**）
- 全部同步操作由 `tools/release_sync.py` 完成（`new-version` / `cherry` / `release` / `check`），禁止手工 read-tree、禁止移动已推送的 tag

### 8.3 Git 分支规范（三线模型）

| 分支 | 用途 | 推送 |
|------|------|------|
| `dev` | 日常开发（Conventional Commits），不在此分支打 tag | ❌ 仅本地 |
| `mainline` | 版本里程碑线，每 commit = 一版本，带 `vX.Y.Z-dev` tag | ✅ `push origin mainline --follow-tags` |
| `release` | 稳定公开发行，GitHub 默认分支，受保护（禁止 force push） | ✅ `push origin release` |

- 三线共享共同祖先（dev 的 Initial commit）；release 各发行 commit 的父锚定其来源的 mainline 版本
- dev 在每次里程碑快照后 `reset --hard mainline` 自动归档（`new-version` 内置 `merge --squash dev`）
- 单点修复用 `release_sync.py cherry <commit> <目标版本>` 跨线搬运；已发行版本的修复加 `--also-release` 同步 release
- 公开发行完整流程：dev 提交 → `new-version`（squash 合并 + tag + dev 归档 + 推送）→ `release`（锚定签出 + 去 `-dev` + 注解 tag + 推送）→ release 状态下 `build_release.py --zip` 打包
- 轻量 tag 若 `--follow-tags` 未生效，补 `git push origin --tags`

### 8.4 新增功能检查清单

- [ ] 新字段是否需要在 `StyleConfigFormData` 中注册？
- [ ] 新参数是否需要沿透传链传递（CLI → ImageProcessor → FrameRenderer → RenderContext）？
- [ ] 新背景类型是否在 `FILL_TYPES` 注册？（而非在 renderer.py 中硬编码）
- [ ] 新显示字段是否在 `RenderContext.get_text()` 中添加了分支？
- [ ] 曝光类显示格式化是否复用 `ExifHelper` 共享方法？（禁止在消费点另行实现，见 §7.7）
- [ ] 外部数据文件是否在 `.gitignore` 中放了追踪规则？
- [ ] README / STYLE_GUIDE / DEVELOPMENT 是否需要同步更新？
