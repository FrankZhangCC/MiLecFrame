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
└── build_pyside.py              # PyInstaller 编译脚本
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
  8. 渲染相框（FrameRenderer，三阶段管线）
  9. 保存输出（JPEG/PNG，quality=95，optimize=True，嵌入原始 EXIF + sRGB ICC profile）
```

### 3.2 EXIF 数据流（四层架构）

```
EXIF Helper              Device Mapper             display_data           RenderContext
│                        │                         │                      │
├─ 解析原始二进制        │                         │                      │
├─ _safe_decode()        │                         │                      │
│  多编码容错            │                         │                      │
│                        ├─ 品牌/机型/镜头名映射   │                      │
│                        │                        ├─ 字段拼接组合        │
│                        │                        ├─ camera_combined     │
│                        │                        ├─ camera_lens_combined│
│                        │                        ├─ short_lens          │
│                        │                        ├─ raw_* 原始值        │
│                        │                        │                      ├─ 条件路由
│                        │                        │                      ├─ 镜头显示模式
│                        │                        │                      ├─ 短版开关
│                        │                        │                      ├─ 时间隐藏模式
│                        │                        │                      ├─ 时间+作者拼接
│                        │                        │                      ├─ 竖向自适应
│                        │                        │                      │
▼                        ▼                        ▼                      ▼
raw EXIF bytes          映射后字段               组合显示字段            最终文本
```

统一数据出口为 `exif_helper.get_display_data()`。`raw_*` 字段供 GUI 设备信息区展示，映射后字段供渲染使用。

### 3.3 渲染管线（四阶段）

```
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
| `calculate_position(w, h, config, defer_padding)` | 分发 | 根据有无 relative_to 分支到绝对/相对 |
| `_calculate_absolute(w, h, config)` | 绝对定位 | 按 position/alignment/placement/margin 计算 |
| `_get_anchor(...)` | 绝对定位 | 14 种 position 的具体公式实现 |
| `_align_x(alignment, ox, ow, ew, m)` | 辅助 | 水平对齐函数 |
| `_align_y(alignment, oy, oh, eh, m)` | 辅助 | 垂直对齐函数 |
| `_resolve_margins(config)` | 绝对定位 | margin 解析（统一值 → 方向覆盖） |
| `_calculate_relative(w, h, config)` | 相对定位 | 按 relative_to + relative_position 计算 |
| `_shift_dependents(name, sx, sy)` | 级联 | 递归平移所有子孙 |
| `_resolve_element_order(elements, configs)` | 排序 | Kahn 算法拓扑排序 |
| `_collect_tree_members(root, members)` | 树定位 | BFS 遍历收集依赖树成员 |
| `_resolve_tree_ref(position, alignment)` | 树定位 | position+alignment → (h_ref, v_ref) |
| `_compute_visual_bounds(members)` | 树定位 | 计算一组元素的视觉包围盒 |
| `apply_tree_positioning(all_positions)` | 树定位 | 树级组合定位入口 |

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

`_calculate_absolute(ew, eh, config)` 流程：
```python
margins = _resolve_margins(config)           # 步骤 1：解析 margin
placement = config.get('placement', 'outside')
position  = config.get('position', 'bottom')
alignment = config.get('alignment', 'center')
x, y = _get_anchor(placement, position, alignment,  # 步骤 2：计算锚点
                   ox, oy, ow, oh, ew, eh, margins)
x = clamp(x, pad_left, pad_right - ew)      # 步骤 3：padding 约束
y = clamp(y, pad_top, pad_bottom - eh)
```

_align_x / _align_y 的核心逻辑：
```python
def _align_x(alignment, ox, ow, ew, m):
    if 'left' in alignment:   return ox + m['left']
    if 'right' in alignment:  return ox + ow - ew - m['right']
    return ox + (ow - ew) // 2    # center / both-center / 默认

def _align_y(alignment, oy, oh, eh, m):
    if 'top' in alignment:    return oy + m['top']
    if 'bottom' in alignment: return oy + oh - eh - m['bottom']
    return oy + (oh - eh) // 2    # center / both-center / 默认
```

margin 解析两阶段：
1. `config['margin']` → 四边初始值（未设 → 0）。float → `int(reference_side * ratio)`，int → 直接使用。
2. `config['margin_top']` 等方向覆盖。四个方向各自独立，设了几个覆盖几个。

#### 4.1.7 相对定位算法

6 种方向的核心公式（positions 统一存储包围盒顶 y 后，`ty + th` = 参考视觉底部）：

| 方向 | x 公式 | y 公式 |
|------|--------|--------|
| `after` / `below` | `_align_x(alignment, tx, tw, ew)` | `ty + th + margin_px` |
| `before` / `above` | `_align_x(alignment, tx, tw, ew)` | `ty - eh - margin_px` |
| `right-of` | `tx + tw + margin_px` | `_align_y(alignment, ty, th, eh)` |
| `left-of` | `tx - ew - margin_px` | `_align_y(alignment, ty, th, eh)` |

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

**算法 8 步**：

```
1. 识别根元素：无 relative_to + tree_align: true + 未被其他树处理过
2. 收集树成员（BFS）
3. 计算树的视觉包围盒（所有成员合并）
4. 用根配置的 _calculate_absolute 计算目标位置
5. _resolve_tree_ref 解析参考方向
6. 计算平移量（目标 - 当前）
7. _shift_dependents 平移整棵树
8. padding 约束（若溢出则整体平移回边界）
```

`_resolve_tree_ref(position, alignment)` 映射表（完全对齐 `_get_anchor` 的 14 种组合）：

| position | alignment | h_ref | v_ref |
|----------|-----------|-------|-------|
| `top-left` / `tl` | 任意 | `left` | `top` |
| `top-right` / `tr` | 任意 | `right` | `top` |
| `top-center` / `tc` / `top` | 任意 | `center` | `top` |
| `bottom-left` / `bl` | 任意 | `left` | `bottom` |
| `bottom-right` / `br` | 任意 | `right` | `bottom` |
| `bottom-center` / `bc` / `bottom` | 任意 | `center` | `bottom` |
| `left` / `right` | `*-top` | 对应 | `top` |
| `left` / `right` | `*-bottom` | 对应 | `bottom` |
| `left` / `right` | 其他 | 对应 | `center` |
| `center` | 任意 | `center` | `center` |
| 任意 | `both-center` | `center` | `center` |

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

图层合成顺序：背景填充 → 原图圆角裁切 → 装饰（水印） → 文字（委托 TextRenderer） → Logo。

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

**三阶段处理**（详情见 [3.3 渲染管线](#33-渲染管线四阶段)）：

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
- `is_dark_bg(key)` → 根据 `text_scheme` 判断，供渲染器自动适配文字颜色
- `register_custom_solid(color, text_scheme)` → 动态注册自定义纯色并返回 key（v2.1.0 预留接口）

新增背景类型只需在 `FILL_TYPES` 中注册，GUI 下拉和 CLI 自动同步。

### 4.5 RenderContext（渲染文本入口）

`src/utils/render_context.py`

`get_text(key)` 根据样式 YAML 中 `info_position` 声明的 key 返回最终显示文本，内部闭环所有条件逻辑：

| key | 内部字段来源 | 条件路由 |
|-----|------------|---------|
| `exif` | `display_data['exif_formatted']` | — |
| `timestamp` | `exif_data['datetime_original']` | `timestamp_display_mode`: `full` → 完整时间，`date_only` → `[:10]` 切片，`hide` → `None` |
| `timestamp_author` | datetime + author | 三段 fallback：时间+作者 / 仅时间 / 仅作者 / None |
| `camera_lens` | `camera_lens_combined` / `camera_lens_combined_short` / `camera_combined` | 由 lens_display_mode + use_short_lens 控制 |
| `camera` | `display_data['camera_combined']` | — |
| `camera_make` | `display_data['camera_make']` | — |
| `lens` | `lens_model` / `short_lens` | use_short_lens 控制 |
| `focal_length_formatted` | `raw_focal_length_35mm` → 回退 `raw_focal_length` | — |
| `aperture_formatted` | `raw_aperture` | — |
| `shutter_speed_formatted` | `raw_shutter_speed` + "s" | — |
| `iso_formatted` | `raw_iso` | 不含 "ISO" 前缀 |

**新增显示字段指南**：在 `get_text()` 中添加 `elif key == 'xxx':` 分支 → 在 YAML 的 `info_position` 中声明配置。渲染器零改动。

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

- `_ensure_dbs_exist()` → 文件不存在时自动创建带表头的 CSV
- `_load_camera_map()` → 读取 `(original_brand, original_model) → {mapped_brand, mapped_model}`
- `_load_lens_map()` → 读取 `original_lens → {mapped_lens, short_lens, brand, mount}`
- GUI 中通过 `TableView` 可编辑表格，实时保存回 CSV

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

设备映射（`camera_map.csv`、`lens_map.csv`）和 Logo 补偿系数（`logo_scale.yaml`）均存储为可编辑的外部文件，程序自动创建默认值。用户修改即生效，无需重新编译。

### 7.5 配置持久化

`ConfigManager` 保存/加载 `config.json`（作者名自动记忆 + 最近四项配置）。GUI 关闭时通过 `save_config()` 自动持久化。

### 7.6 ExpandGroupSettingCard 开发铁律

在 `ExpandGroupSettingCard` 内添加自定义内容时必须：

1. 通过 `addGroupWidget()` 或 `addGroup()` 添加子控件，**禁止直接操作 `self.viewLayout.addWidget()`**
2. 子控件的 `sizeHint().height()` 必须能反映真实视觉高度
3. `QScrollArea` / `SmoothScrollArea` 的 `sizeHint()` 不反映 `setFixedHeight()`，需覆盖 `_adjustViewSize()`
4. 动态添加/删除子控件后调用 `QTimer.singleShot(0, self._adjustViewSize)`
5. 开发完成后调用 `layout_debug.dump_expand_card(self)` 验证

---

## 8. 开发约定

### 8.1 环境与命令

- 所有开发在 venv 中：`.\venv\Scripts\activate`（Windows PowerShell）
- 校验：`python -m py_compile <文件>` 检查语法
- 调试：DEBUG 级别日志写入 `debug_log.txt`（项目根目录），INFO 及以上输出到 stderr

### 8.2 版本管理

- `src/_version.py` 是版本号**单点入口**
- 公开 Release 版：`v0.x.x` / `v1.x.x`
- 内部开发版：`v2.x.x-dev`
- 版本号变更时，同步更新 `README.md` 徽标和 `CHANGELOG.md`

### 8.3 Git 分支规范

| 分支 | 用途 | 推送 |
|------|------|------|
| `dev` | 日常开发 | ❌ 不推送 |
| `release` | 公开发布快照 | ✅ `origin/release` |

- 仅推送 `release` 标签，**绝不推送** `v*-dev` 标签
- release 分支仅含纯净快照 commit，无开发中间历史

### 8.4 新增功能检查清单

- [ ] 新字段是否需要在 `StyleConfigFormData` 中注册？
- [ ] 新参数是否需要沿透传链传递（CLI → ImageProcessor → FrameRenderer → RenderContext）？
- [ ] 新背景类型是否在 `FILL_TYPES` 注册？（而非在 renderer.py 中硬编码）
- [ ] 新显示字段是否在 `RenderContext.get_text()` 中添加了分支？
- [ ] 外部数据文件是否在 `.gitignore` 中放了追踪规则？
- [ ] README / STYLE_GUIDE / DEVELOPMENT 是否需要同步更新？
