# 布局引擎与渲染器算法文档

> 对应模块：`src/utils/layout_engine.py`（LayoutEngine）和 `src/core/renderer.py`（FrameRenderer）
>
> 版本：v1.12.0-dev，2026-05-25

---

## 目次

1. [架构总览](#1-架构总览)
2. [LayoutEngine 核心数据结构](#2-layoutengine-核心数据结构)
3. [文字基线系统——理解坐标约定的关键](#3-文字基线系统理解坐标约定的关键)
4. [绝对定位系统](#4-绝对定位系统)
5. [相对定位系统](#5-相对定位系统)
6. [组合盒约束与级联平移](#6-组合盒约束与级联平移)
7. [拓扑排序（Phase 2 顺序控制）](#7-拓扑排序phase-2-顺序控制)
8. [树级组合定位（Phase 2.5）](#8-树级组合定位phase-25)
9. [三阶段渲染管线详解](#9-三阶段渲染管线详解)
10. [字体引擎与混排渲染](#10-字体引擎与混排渲染)
11. [多行文本处理](#11-多行文本处理)
12. [RenderContext 渲染上下文](#12-rendercontext-渲染上下文)
13. [Logo 渲染](#13-logo-渲染)
14. [关键参数速查](#14-关键参数速查)
15. [常见问题](#15-常见问题)
16. [原图圆角裁切](#16-原图圆角裁切)

---

## 1. 架构总览

整个渲染管线按照数据流顺序分为四个阶段。每个阶段都有明确的输入和输出，阶段之间通过 `draw_items` 字典和 `positions` 注册表传递数据。

```
Phase 1  ── 测量 ──────────────────────────────────────────────────
输入: layouts(info_position/defined_texts/custom_text),
      context(RenderContext),
      colors, fonts, bg_fill_type
输出: draw_items（key → {text, font, color, width, height, ascent, descent, mixed?}）

行为：
  遍历所有三种文本来源的每个元素，分别进行：
  ├─ 获取文本内容：
  │   ├─ info_position 的 key  →  context.get_text(key)
  │   ├─ defined_texts 的 key  →  配置中的 content 字段
  │   └─ custom_text           →  context.get_text('custom_text')
  ├─ 确定字体：根据混排检测结果加载拉丁/Gotham 或 CJK/GlowSansSC 字体
  ├─ 测量尺寸：font.getbbox(text) 获取宽度；font.getmetrics() 获取 ascent + descent
  ├─ 确定颜色：按「元素专属 custom_{key}_{dark/light}_color > 通用兜底 custom_text_{dark/light}_color > 黑白默认」三级优先级
  └─ 存入 draw_items（此时不触碰 layout_engine）
  │
  ▼
Phase 2  ── 定位 + 注册 ───────────────────────────────────────────
输入: draw_items, all_positions（每个元素的定位配置）,
      text_elements（按三种来源合并的元素列表）
输出: layout_engine.positions（元素坐标注册表）
      layout_engine._dependents（依赖关系图）

行为：
  ├─ 拓扑排序：_resolve_element_order() → 确定处理顺序（根先于子孙）
  ├─ 预注册缺失锚点：当 relative_to 指向的元素被跳过时，用 0x0 注册其绝对位置
  ├─ 逐个定位：calculate_position(w, h, cfg, defer_padding) → (x, y)，y = 包围盒顶
  │   tree_align 树内的元素传 defer_padding=True，跳过组合盒平移 + padding 夹持，
  │
  ▼
Phase 2.5  ── 树级组合定位（v1.7.0，仅在根元素设 tree_align: true 时执行）──
输入: all_positions, layout_engine.positions
输出: 对选定树的平移（直接修改 positions 中的坐标）

行为：
  └─ apply_tree_positioning(all_positions)
      ├─ 遍历所有根元素，仅处理 tree_align: true 的
      ├─ 收集 tree_members → 计算视觉包围盒
      ├─ 用 _calculate_absolute 计算目标位置
      ├─ 计算平移量并级联平移
      └─ padding 约束
  │
  ▼
Phase 3  ── 绘制 ──────────────────────────────────────────────────
输入: positions, draw_items
输出: 最终图像

行为：
  └─ 按拓扑序从 positions 读取最终坐标：
      ├─ 单字体行  →  draw.text(x, y - descent, text)
      ├─ 混排文本  →  baseline_y = y + ref_ascent - ref_descent，逐片段
      └─ 多行文本  →  首行 baseline = y - descent，逐行 + 行间距
```

---

## 2. LayoutEngine 核心数据结构

### 2.1 坐标系与参照系

| 概念 | 命名 | 定义 | 用途 |
|------|------|------|------|
| 原图尺寸 | `image.size` | 输入图像的 `(width, height)` | 所有计算的起点 |
| 参照边 | `reference_side = min(w, h)` | 原图的短边长度（像素） | 所有浮点比例系数的基准除数。`size_ratio=0.02` 意味着字号 = `int(reference_side * 0.02)` |
| 画布 | `canvas_size = (w, h)` | 经 `expand_canvas` 扩展后的总绘图区域 | 所有元素的最终边界 |
| 原图边界 | `original_bounds = (ox, oy, ow, oh)` | 原始图像在画布中的位置 | 绝对定位的参考矩形 |
| 安全区域 | `padding_bounds = (left, top, right, bottom)` | 从画布四边向内收缩后得到的矩形边界 | 叠加元素的活动范围，高于一切 margin |

expand_canvas 的计算：
```python
new_width  = original_width  + reference_side * (left_exp + right_exp)
new_height = original_height + reference_side * (top_exp + bottom_exp)
ox = int(reference_side * left_exp)           # 原图左边缘在画布中的 x
oy = int(reference_side * top_exp)            # 原图顶边缘在画布中的 y
```

padding 的计算：
```python
pad_left   = int(reference_side * padding_left)
pad_top    = int(reference_side * padding_top)
pad_right  = canvas_width  - int(reference_side * padding_right)
pad_bottom = canvas_height - int(reference_side * padding_bottom)
```

### 2.2 位置注册表（positions）

```python
self.positions = {
    'exif': {
        'x': 150,            # 元素包围盒左上角 x
        'y': 3337,           # 元素包围盒左上角 y（文字和非文字统一）
        'width': 250,        # 元素宽度
        'height': 40,        # 文字：ascent + descent；Logo：像素高度
    },
    'logo': {
        'x': 4000,
        'y': 3150,           # Logo 的包围盒左上角 y
        'width': 120,
        'height': 60,
    },
}
```

**y 坐标的语义约定——这是理解整个定位系统的核心**：

`positions` 中所有元素的 y 统一表示**包围盒顶部（bounding box top）**的 y 坐标。文字元素和非文字元素（Logo、占位锚点）遵循完全相同的规则。过去 v1.7.0 早期版本曾在此处存储基线 y，导致 `_calculate_relative` 需要 ascent 校正才能推测真实视觉边界。此重构已彻底消除这一歧义。

包围盒顶 y 意味着：
- 元素的视觉顶部 = y（文字视觉顶 = baseline - ascent = (y+ascent) - ascent = y）
- 元素的视觉底部 = y + height（文字视觉底 = baseline + descent = (y+ascent) + descent = y + height）
- 包围盒底部 = y + height = 视觉底部（两者相等）
- `_calculate_relative` 可以放心使用 `ty + th` 作为参考底部、`ty` 作为参考顶部

基线仅在 Phase 3 绘制时通过 `y - descent`（单字体）或 `y + (ref_ascent - ref_descent)`（混排）从包围盒顶转换得到。详见[第 3 章](#3-文字基线系统)。

| 元素类型 | 注册 y 含义 | 注册 height 含义 |
|---------|------------|-----------------|
| 单字体文字 | 包围盒顶 | `ascent + descent` |
| 混排文字 | 包围盒顶 | `max_ascent + max_descent` |
| 多行文字 | 包围盒顶（块整体） | 块总视觉高度 |
| Logo | 包围盒顶 | Logo 像素高度 |
| 占位锚点 | 包围盒顶 | 0 |

### 2.3 依赖图（_dependents）

`self._dependents` 维护一张有向无环图（DAG），自动由 `register_element(name, ..., relative_to='parent')` 构建：

```python
self._dependents = {
    'exif':        ['timestamp_author', 'location'],   # exif 有两个子节点
    'camera_lens': ['location'],                        # camera_lens 有一个子节点
}
```

**四个用途**：

| 用途 | 调用方 | 动作 |
|------|--------|------|
| 拓扑排序 | `_resolve_element_order()` | 从 `relative_to` 构建入度，确定处理顺序 |
| 组合盒扩展 | `_calculate_relative()` | 在计算组盒时加入所有已注册从属 |
| 级联平移 | `_shift_dependents()` | 沿依赖树递归传播 shift_x, shift_y |
| 树成员收集 | `_collect_tree_members()` | BFS 遍历获取整棵树的所有元素 |

### 2.4 方法索引（完整列表）

| 方法 | 类别 | 作用 |
|------|------|------|
| `__init__(size, layout_config)` | 构造 | 计算 canvas_size、original_bounds、padding_bounds |
| `register_element(name, x, y, w, h, relative_to)` | 注册 | 存入 positions + 维护 _dependents |
| `get_element_bounds(name)` | 查询 | 从 positions 读取（支持模糊匹配） |
| `calculate_position(w, h, config, defer_padding)` | 分发 | 根据有无 relative_to 分支到绝对/相对。`defer_padding` 控制是否在此阶段跳过 padding 约束，用于 tree_align 链内元素 |
| `_calculate_absolute(w, h, config)` | 绝对定位 | 按 position/alignment/placement/margin 计算 |
| `_get_anchor(...)` | 绝对定位 | 14 种 position 的具体数学公式实现 |
| `_align_x(alignment, ox, ow, ew, m)` | 对齐辅助 | 水平对齐函数 |
| `_align_y(alignment, oy, oh, eh, m)` | 对齐辅助 | 垂直对齐函数 |
| `_resolve_margins(config)` | 绝对定位 | 统一 margin + 方向覆盖的解析 |
| `_calculate_relative(w, h, config)` | 相对定位 | 按 relative_to + relative_position 计算 |
| `_shift_dependents(name, sx, sy)` | 级联 | 递归平移所有子孙元素 |
| `_resolve_element_order(elements, configs)` | 排序 | Kahn 算法拓扑排序 |
| `_collect_tree_members(root, members)` | 树定位 | BFS 遍历收集依赖树所有成员 |
| `_resolve_tree_ref(position, alignment)` | 树定位 | position+alignment → (h_ref, v_ref) |
| `_compute_visual_bounds(members)` | 树定位 | 计算一组元素的视觉包围盒 |
| `apply_tree_positioning(all_positions)` | 树定位 | 树级组合定位入口 |

---

## 3. 文字基线系统——理解坐标约定的关键

### 3.1 字体的五大度量值

每个 Pillow `FreeTypeFont` 对象包含几组固定的属性值，它们决定了文字渲染时的精确位置：

| 属性 | 获取方式 | 含义 | 示例值（Gotham Medium 40px） |
|------|---------|------|------|
| `ascent` | `font.getmetrics()[0]` | 从基线到最高字形顶部的距离（正值，单位 px） | 32 |
| `descent` | `font.getmetrics()[1]` | 从基线到最低字形底部的距离（正值，单位 px） | 8 |
| `height` | `ascent + descent` | 字体总高度 | 40 |
| `bbox` | `font.getbbox(text)` | `(x0, y0, x1, y1)` 四元组。y0 通常在基线之上（负值），y1 在基线之下（正值） | 因文本而异 |

字体的视觉范围示意（以基线为参考线）：

```
                ───── top_of_glyphs = baseline - ascent
               │
               │   ┌───┬───┬───┐
               │   │   │   │   │
  baseline  ═══╪═══╪═══╧═══╪═══╪═══════════════════
              │    │       │   │
              │    └───────┴───┘
              │──── bottom_of_glyphs = baseline + descent
```

### 3.2 `draw.text()` 的基线语义

Pillow 的 `ImageDraw.text(x, y, text, font=font)` 将 `(x, y)` 解释为**基线的左上角起点**

```python
draw = ImageDraw.Draw(image)
draw.text((100, 200), "Hello", font=font_40px)
# 基线在 (100, 200)，文字向右上方和右下方伸展
```

这意味着：
- 文字的视觉顶部在 `y - ascent = 200 - 32 = 168`
- 文字的视觉底部在 `y + descent = 200 + 8 = 208`
- 文字向右延伸到 x=100 加每个字形的宽度之和

### 3.3 布局引擎返回的 y 是什么？

布局引擎的 `_calculate_absolute()` 在计算位置时，使用参数 `eh = ascent + descent`（即文字的总高度）。所有公式中出现的 `eh` 都是一个矩形方框的高度。返回的 `y` 就是这个矩形方框的**顶部边缘**坐标。

```
  y  = ( 单元素时布局引擎返回的值）
       │
       │  ┌──────────────────┐  ← 包围盒顶部（y_calc）
       │  │                  │
       │  │  (ascent = 32)   │
       │  │                  │
  ═════╪══╪══════════════════╪════  ← 基线（应放置 draw.text 的位置）
       │  │                  │
       │  │  (descent = 8)   │
       │  │                  │
       │  └──────────────────┘  ← 包围盒底部（y_calc + eh）
       │
       └─────────────────────── y + eh
```

**核心约束**：`draw.text()` 要的是基线 y，而布局引擎的 `_calculate_absolute()` 返回的是包围盒顶部 y。两者之间差一个 `descent`。

### 3.4 从"注册时转"到"绘制时转"

v1.7.0 最终版采用的设计是：**`positions` 统一存储包围盒顶 y，基线转换仅发生在 Phase 3 绘制时单点完成**。此前尝试过在 Phase 2 注册时做 `y -= descent` 转为基线，但由此导致的坐标歧义需要大量 `ascent` 校正代码来补救。最终回归到最简洁的方式。

绘制时的转换规则：

```python
# Phase 3 中，从 positions 读取的 y = 包围盒顶

# 单字体：基线 = 包围盒顶 - descent
draw_y = y - item['descent']
draw.text((x, draw_y), item['text'], fill=item['color'], font=item['font'])

# 混排：基线 = 包围盒顶 + ref_ascent - ref_descent
baseline_y = y + item['ref_ascent'] - item['ref_descent']
for seg_text, font, seg_width, seg_ascent, seg_descent in item['seg_info']:
    seg_y = baseline_y - seg_ascent
    draw.text((seg_current_x, seg_y), seg_text, fill=item['color'], font=font)
    seg_current_x += seg_width
```

为什么减 `descent` 或加 `(ref_ascent - ref_descent)` 能得到正确基线？

```
单字体：
  positions y = 包围盒顶
  我们想让 baseline 在旧版 Phase 2 的 y_reg 处。
  旧版 y_reg = 包围盒顶 - descent
  所以 draw_y = y - descent

混排：
  旧版 y_reg = 包围盒顶 - ref_descent
  旧版 Phase 3: baseline_y = y_reg + ref_ascent = 包围盒顶 - ref_descent + ref_ascent
  新版 y = 包围盒顶
  新版 baseline_y = y + (ref_ascent - ref_descent) = 包围盒顶 + ref_ascent - ref_descent
```

两种方式计算出的基线在画布上的绝对位置完全一致。

### 3.5 统一坐标的数学优势

当 `positions` 存储包围盒顶 y 时，`_calculate_relative` 和所有定位公式中读取的 `(tx, ty, tw, th)` 具有以下天然关系：

```
ty          = 参考元素的包围盒顶部    = 参考视觉顶部
ty + th     = 参考元素的包围盒底部    = 参考视觉底部
```

文字元素的视觉边界与包围盒边界重合，因为：
```
文字视觉顶 = baseline - ascent = (ty + ascent) - ascent = ty = 包围盒顶
文字视觉底 = baseline + descent = (ty + ascent) + descent = ty + (ascent + descent) = ty + th = 包围盒底
```

因此 `ty + th` 可以直接作为参考底部使用，不需要任何 `ascent`/`descent` 校正。`_align_y("bottom", ty, th, eh)` 的语义是"让当前元素的包围盒底（= 视觉底）与参考元素的包围盒底（= 视觉底）对齐"——完全正确，没有歧义。

这是本重构的核心收益：**删掉了一整层"基线→包围盒"的转换和反向校正，把问题化简到了它的本质——坐标就是坐标，不因元素类型而改变语义**。

---

## 4. 绝对定位系统

### 4.1 `_calculate_absolute(w, h, config)` 完整流程

```python
def _calculate_absolute(self, ew, eh, config):
    margins  = self._resolve_margins(config)        # 步骤 1：解析 margin
    placement = config.get('placement', 'outside')  # 步骤 2：三参数
    position  = config.get('position', 'bottom')
    alignment = config.get('alignment', 'center')

    x, y = self._get_anchor(placement, position, alignment,   # 步骤 3：锚点
                            ox, oy, ow, oh, ew, eh, margins)

    x = max(pad_left, min(x, pad_right - ew))       # 步骤 4：padding 约束
    y = max(pad_top,  min(y, pad_bottom - eh))

    return x, y
```

### 4.2 三个正交参数

| 参数 | 可选值 | 默认值 | 作用轴 |
|------|--------|--------|--------|
| `placement` | `inside` / `outside` | `outside` | 元素在原图矩形内侧还是外侧 |
| `position` | 14 种锚点 | `bottom` | 绑定到原图的哪条边或哪个角 |
| `alignment` | `left` / `center` / `both-center` / `right` | `center` | 元素自身相对于锚点的对齐方式；`both-center` 使元素中心与锚点重合 |

### 4.3 14 种 position 的完整行为矩阵

下表显示了每种 position 值从原图边界的何处计算元素的位置。`alignment` 列说明该 position 下 alignment 控制哪根轴（`-` 表示不控制，固定组合）。

| position | 水平参考 | 垂直参考 | alignment 控制的轴 |
|----------|---------|---------|-------------------|
| `top-left` / `tl` | 左边缘 | 顶部 | —（固定） |
| `top-right` / `tr` | 右边缘 | 顶部 | —（固定） |
| `top-center` / `tc` | 水平居中 | 顶部 | —（固定） |
| `top` | 取决于 alignment | 顶部 | 水平轴 |
| `bottom-left` / `bl` | 左边缘 | 底部 | —（固定） |
| `bottom-right` / `br` | 右边缘 | 底部 | —（固定） |
| `bottom-center` / `bc` | 水平居中 | 底部 | —（固定） |
| `bottom` | 取决于 alignment | 底部 | 水平轴 |
| `left` | 左边缘 | 取决于 alignment | 垂直轴 |
| `right` | 右边缘 | 取决于 alignment | 垂直轴 |
| `center` | 画布居中 | 画布居中 | —（固定，不受 placement 和 margins 影响） |

### 4.4 `_get_anchor` 的逐公式展开

#### `_align_x`——水平对齐函数

```python
def _align_x(alignment, ox, ow, ew, m):
    # alignment 包含 'left' 语义：元素左边缘在原图左边缘 + margin_left
    if alignment in ('left', 'top-left', 'bottom-left'):
        return ox + m['left']
    
    # alignment 包含 'right' 语义：元素右边缘在原图右边缘 - margin_right
    if alignment in ('right', 'top-right', 'bottom-right'):
        return ox + ow - ew - m['right']
    
    # 其他（包括 'center'、'both-center'、默认）：元素水平居中于原图
    return ox + (ow - ew) // 2
```

#### `_align_y`——垂直对齐函数

```python
def _align_y(alignment, oy, oh, eh, m):
    # alignment 包含 'top' 语义：元素顶边 = 原图顶边 + margin_top
    if alignment in ('top', 'top-left', 'top-right'):
        return oy + m['top']
    
    # alignment 包含 'bottom' 语义：元素底边 = 原图底边 - margin_bottom
    if alignment in ('bottom', 'bottom-left', 'bottom-right'):
        return oy + oh - eh - m['bottom']
    
    # 其他（包括 'center'、'both-center'、默认）：元素垂直居中于原图
    return oy + (oh - eh) // 2
```

#### 所有 14 种 position 的数学公式

下表中 `oy + oh` 是原图底边，`ox + ow` 是原图右边。

**垂直位置（placement='outside'，默认）：**

| position | y 公式 | 说明 |
|----------|--------|------|
| `top-*`（全部） | `y = oy - eh - m['top']` | 元素包围盒在图片外部上方 |
| `bottom-*`（全部） | `y = oy + oh + m['bottom']` | 元素包围盒在图片外部下方 |
| `left` | `y = _align_y(alignment, ...)` | 由 alignment 决定垂直位置 |
| `right` | `y = _align_y(alignment, ...)` | 由 alignment 决定垂直位置 |
| `center` | `y = (canvas_h - eh) // 2` | 画布居中，不受 margins 影响 |

**垂直位置（placement='inside'）：**

| position | y 公式 | 说明 |
|----------|--------|------|
| `top-*`（全部） | `y = oy + m['top']` | 元素包围盒在图片内部顶部，margin 向内 |
| `bottom-*`（全部） | `y = oy + oh - eh - m['bottom']` | 元素包围盒在图片内部底部 |
| `left` / `right` | `y = _align_y(alignment, ...)` | 同 outside |
| `center` | `y = (canvas_h - eh) // 2` | 同 outside |

**水平位置（所有 position）：**

| position | x 公式 | 说明 |
|----------|--------|------|
| `*-left` / `left` | `inside:  ox + m['left']`；`outside left:  ox - ew - m['right']` | 元素左边缘对齐原图左边缘 |
| `*-right` / `right` | `inside: ox + ow - ew - m['right']`；`outside right: ox + ow + m['left']` | 元素右边缘对齐原图右边缘 |
| `*-center` | `ox + (ow - ew) // 2` | 元素水平居中于原图 |
| `top` / `bottom` | `_align_x(alignment, ...)` | 由 alignment 决定 |
| `center` | `(canvas_w - ew) // 2` | 画布居中 |

### 4.5 margin 解析层级

`_resolve_margins(config)` 的解析分两步，优先级清晰：

```
第一步：统一值。config['margin'] → 四边初始值（未设 → 0）。
        值类型：float → int(reference_side * ratio)；int → 直接使用。

第二步：方向覆盖。config['margin_top'] → 覆盖 top（如有）
         config['margin_bottom'] → 覆盖 bottom（如有）
         config['margin_left'] → 覆盖 left（如有）
         config['margin_right'] → 覆盖 right（如有）
         每个方向各自独立，设了几个覆盖几个，不存在互斥激活条件。

最终结果：{'top': px, 'bottom': px, 'left': px, 'right': px}
```

举例：`margin_bottom: 0.035` + `reference_side = 3000` → `m['bottom'] = int(3000 * 0.035) = 105` 像素。

### 4.6 padding 约束

padding 是所有定位计算的最后一道约束，优先级高于所有 margin：

```python
x = max(pad_left, min(x, pad_right - element_width))
y = max(pad_top,  min(y, pad_bottom - element_height))
```

- 元素超出 padding 左边界 → 推到 pad_left
- 元素超出 padding 右边界 → 拉到 `pad_right - element_width`
- 元素超出 padding 上边界 → 推到 pad_top
- 元素超出 padding 下边界 → 拉到 `pad_bottom - element_height`
- 当 element_width 大于 `pad_right - pad_left` 时：左对齐到 pad_left，右侧必然溢出（仅单方向约束）

---

## 5. 相对定位系统

### 5.1 `_calculate_relative(w, h, config)` 参数表

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `relative_to` | `str` | 必填 | 参考元素的名称 |
| `relative_position` | `str` | `'after'` | 6 种方向 |
| `relative_margin` | `float` | `0.01` | 间距比例，像素 = `int(reference_side * ratio)` |
| `alignment` | `str` | `'center'` | 在参考元素范围内的对齐方式 |
| `offset_x_ratio` | `float` | `0.0` | x 轴微调比例 |
| `offset_y_ratio` | `float` | `0.0` | y 轴微调比例 |

### 5.2 六种方向和 alignment 语义

| relative_position | 元素放置方向 | alignment 控制哪根轴 | 对齐基准物 |
|------------------|-------------|---------------------|-----------|
| `after` / `below` | 参考元素的下方 | 水平轴（left/center/right） | 参考元素的宽度 |
| `before` / `above` | 参考元素的上方 | 水平轴（left/center/right） | 参考元素的宽度 |
| `right-of` | 参考元素的右侧 | 垂直轴（top/center/bottom） | 参考元素的高度 |
| `left-of` | 参考元素的左侧 | 垂直轴（top/center/bottom） | 参考元素的高度 |

### 5.3 完整定位公式

`positions` 统一存储包围盒顶 y 后，`(tx, ty, tw, th)` 具有直观的语义：

| 符号 | 含义 |
|------|------|
| `tx, ty` | 参考元素的包围盒左上角 x, y |
| `tw, th` | 参考元素的宽度和高度（文字：`ascent + descent`） |
| `ty` | = 参考视觉顶部（文字视觉顶 = baseline - ascent = (ty+ascent) - ascent = ty） |
| `ty + th` | = 参考视觉底部（文字视觉底 = baseline + descent = (ty+ascent) + descent = ty + th） |
| `eh` | 当前元素的包围盒高度（`ascent + descent`） |
| `margin_px` | `int(reference_side * relative_margin)` |

由于视觉边界与包围盒边界重合，所有公式可以直接使用注册的 `(tx, ty, tw, th)`，不需要额外校正。

#### `after` / `below`——当前元素在参考元素下方

```
y = ty + th + margin_px
x = _align_x(alignment, tx, tw, ew, {'left': 0, 'right': 0})
```

**推导**：当前包围盒顶部 y 在参考包围盒底部 + margin 处。当前视觉顶部 = y（包围盒顶 = 视觉顶），参考视觉底部 = ty + th。间距 = y - (ty + th) = margin_px。✓

#### `before` / `above`——当前元素在参考元素上方

```
y = ty - eh - margin_px
x = _align_x(alignment, tx, tw, ew, {'left': 0, 'right': 0})
```

**推导**：当前包围盒底部 = y + eh 在参考包围盒顶部 - margin 处。参考视觉顶部 = ty。间距 = ty - (y + eh) = ty - (ty - margin) = margin_px。✓

#### `right-of`——当前元素在参考元素右侧

```
x = tx + tw + margin_px
y 使用原始 _align_y 公式：

  alignment = 'bottom' / 'bottom-left' / 'bottom-right':
    y = ty + th - eh
    → 当前包围盒底(y+eh) = ty + th = 参考包围盒底 ✓

  alignment = 'top' / 'top-left' / 'top-right':
    y = ty
    → 当前包围盒顶(y) = ty = 参考包围盒顶 ✓

  alignment = 'center' / 其他:
    y = ty + (th - eh) // 2
    → 当前包围盒中心(y + eh//2) = ty + th//2 = 参考包围盒中心 ✓
```

#### `left-of`——当前元素在参考元素左侧

```
x = tx - element_width - margin_px
y 的公式：与 right-of 完全一致（三个 alignment 分支）
```

### 5.4 微调偏移

所有六种方向计算完毕后，额外叠加 offset 微调：

```python
offset_x = int(reference_side * offset_x_ratio)
offset_y = int(reference_side * offset_y_ratio)
x += offset_x
y += offset_y
```

这两个 offset 在组合盒约束之前应用，因此仍然受 padding 约束保护。

---

## 6. 组合盒约束与级联平移

### 6.1 组合盒的计算

当相对定位放置一个元素时，系统将它和参考元素（以及所有已注册的从属元素）视为一个整体——称为**组合盒**。如果这个组合盒超出 padding 安全区域，系统通过整体平移来保持组内相对位置不变。

由于 `positions` 统一使用包围盒顶 y，`ty` = 参考视觉顶部、`ty + th` = 参考视觉底部，因此直接使用注册坐标即可，不需要任何 ascent 校正：

```python
# 组合盒边界（所有元素统一使用注册的 (x, y, w, h)）
group_left   = min(tx, x)
group_top    = min(ty, y)
group_right  = max(tx + tw, x + element_width)
group_bottom = max(ty + th, y + element_height)

# 扩展组合盒以包含所有已注册的从属元素
for dep_name in self._dependents.get(relative_to, []):
    dep_bounds = self.get_element_bounds(dep_name)
    if dep_bounds:
        dx, dy, dw, dh = dep_bounds
        group_left   = min(group_left, dx)
        group_top    = min(group_top, dy)
        group_right  = max(group_right, dx + dw)
        group_bottom = max(group_bottom, dy + dh)
```

### 6.2 平移量的计算

```python
shift_x = 0
shift_y = 0

# 检查四个方向的溢出
if group_left < pad_left:
    shift_x = pad_left - group_left          # 左溢出：向右推
elif group_right > pad_right:
    shift_x = pad_right - group_right        # 右溢出：向左拉

if group_top < pad_top:
    shift_y = pad_top - group_top            # 上溢出：向下推
elif group_bottom > pad_bottom:
    shift_y = pad_bottom - group_bottom      # 下溢出：向上拉
```

### 6.3 平移的应用——`_shift_dependents()`

```python
def _shift_dependents(self, name, shift_x, shift_y):
    # 沿依赖树向下传播
    for dep_name in self._dependents.get(name, []):
        if dep_name in self.positions:
            self.positions[dep_name]['x'] += shift_x
            self.positions[dep_name]['y'] += shift_y
            self._shift_dependents(dep_name, shift_x, shift_y)
```

调用方式（在 `_calculate_relative` 中）：

```python
if shift_x != 0 or shift_y != 0:
    ref_key = relative_to
    # 先平移参考元素本身
    self.positions[ref_key]['x'] += shift_x
    self.positions[ref_key]['y'] += shift_y
    # 再级联平移所有子孙
    self._shift_dependents(ref_key, shift_x, shift_y)
    # 当前元素的位置也同步更新（因为当前元素尚未注册）
    x += shift_x
    y += shift_y
```

### 6.4 最终 padding 夹持

无论是平移前还是平移后，当前元素的位置最终都会受 padding 保护：

```python
x = max(pad_left, min(x, pad_right - element_width))
y = max(pad_top,  min(y, pad_bottom - element_height))
```

### 6.5 tree_align 的 padding 延迟

当元素属于 `tree_align: true` 的依赖树时，组合盒约束和最终 padding 夹持都会通过 `defer_padding=True` 参数跳过。原因是：

1. 链条可能很长，以根元素的初始绝对位置（如原图中心）为起点时右缘可能超出画布
2. 如果 Phase 2 中逐个裁剪或平移，链条内部的相对关系会被破坏
3. `apply_tree_positioning` 在第 8 步会统一重新计算树的包围盒并对齐到目标位置，再做最终 padding 约束

非 tree_align 的元素不受影响，始终 `defer_padding=False`。

---

## 7. 拓扑排序（Phase 2 顺序控制）

### 7.1 Kahn 算法实现

`_resolve_element_order(text_elements, all_positions)` 对元素列表按依赖关系拓扑排序：

```python
def _resolve_element_order(self, text_elements, all_positions):
    # 构建依赖图（有向，从参考元素指向依赖者）
    names_in_list = [t[0] for t in text_elements]
    names_set = set(names_in_list)

    in_degree = {name: 0 for name in names_in_list}
    dependents = {name: [] for name in names_in_list}

    for name in names_in_list:
        cfg = all_positions.get(name, {})
        ref = cfg.get('relative_to')
        if ref and ref in names_set:
            dependents[ref].append(name)   # ref → name 的有向边
            in_degree[name] += 1           # name 的入度 +1

    # 入度为 0 的元素（无依赖，即绝对定位的根）
    queue = [name for name in names_in_list if in_degree[name] == 0]
    ordered = []

    # BFS 拓扑展开
    while queue:
        name = queue.pop(0)
        ordered.append(name)
        for dep in dependents[name]:
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)

    # 兜底：未被覆盖的元素（循环依赖等）按原序追加
    for name in names_in_list:
        if name not in ordered:
            ordered.append(name)

    return ordered
```

**保证**：绝对定位的根元素始终先于相对定位的子元素处理。

### 7.2 缺失参考元素保护

当配置中有 `relative_to` 指向某个元素，但该元素因为无文本数据被 `draw_items` 跳过时，系统会检查这个"缺失的参考元素"是否仍在 `all_positions` 中配置了定位参数，如果是，则以 0×0 尺寸预注册其绝对位置锚点：

```python
for name in draw_items:
    cfg = all_positions.get(name, {})
    ref = cfg.get('relative_to')
    if ref and ref not in draw_items and ref in all_positions:
        ref_cfg = all_positions[ref]
        if not ref_cfg.get('relative_to'):
            rx, ry = layout_engine.calculate_position(0, 0, ref_cfg)
            layout_engine.register_element(ref, rx, ry, 0, 0, ascent=0)
```

确保依赖元素不会因为参考元素被跳过而降级为默认绝对定位导致位置偏移。

---

## 8. 树级组合定位（Phase 2.5）

### 8.1 动机

现有相对定位只能实现「A 在 B 右侧」这种单一元素级别的控制。当多个元素通过 `relative_to` 链组成 `A → B → C → D` 时，只有根 A 使用绝对定位，整条链必然从 A 的位置开始向右延伸，无法实现整条链的居中/右对齐等整体定位效果。

树级组合定位要解决的问题：将整条依赖树**当作一个整体**，用根元素的 `position / alignment / margin_*` 参数对整棵树做一次完整的绝对定位。

### 8.2 启用方式

`tree_align: true` 声明在根元素（即没有 `relative_to` 的元素）的定位配置中：

```yaml
defined_texts:
  defined_text_01:
    content: "FL"
    position: "bottom"
    alignment: "center"
    tree_align: true       # ← 启用树级组合定位
    margin_bottom: 0.07
```

未声明 `tree_align: true` 的依赖树（包括现有的所有样式配置）不受影响，行为与 v1.7.0 之前完全一致。

### 8.3 算法步骤

`apply_tree_positioning(all_positions)` 遍历 `positions` 中所有元素：

```
第一步：识别根元素
  只有同时满足以下条件的元素才会进入树定位流程：
  ├─ 无 relative_to（不是其他元素的子元素）
  ├─ 尚未被其他树处理过
  └─ 配置中有 tree_align: true

第二步：收集树成员
  _collect_tree_members(root, members)
  使用 BFS 遍历 _dependents，收集根节点及其所有子孙。

  如果 len(tree_members) == 1（即根节点没有子元素）→ 跳过。

第三步：计算树的包围盒
  _compute_visual_bounds(members)

  所有元素统一使用注册的包围盒坐标：
    visual_top    = y
    visual_bottom = y + height

  合并所有成员的包围盒范围：
    tree_left   = min(x)
    tree_top    = min(y)
    tree_right  = max(x + width)
    tree_bottom = max(y + height)

  tree_w = tree_right - tree_left
  tree_h = tree_bottom - tree_top

  注意：此处不涉及 ascent 校正。因为 positions 统一存储包围盒顶 y，ty = 视觉顶，ty + th = 视觉底。

第四步：用根配置计算目标位置
  target_x, target_y = _calculate_absolute(tree_w, tree_h, root_cfg)

  这里完全复用现有的绝对定位方法，把整棵树当作一个宽度 tree_w、高度 tree_h
  的虚拟元素来计算目标位置。

第五步：解析水平和垂直参考方向
  (h_ref, v_ref) = _resolve_tree_ref(position, alignment)

  见 8.4 节的完整映射表。

第六步：计算平移量
  目标参考坐标：
    if h_ref == 'left':   target_ref_x = target_x
    if h_ref == 'right':  target_ref_x = target_x + tree_w
    if h_ref == 'center': target_ref_x = target_x + tree_w // 2

    if v_ref == 'top':    target_ref_y = target_y - tree_h
    if v_ref == 'bottom': target_ref_y = target_y
    if v_ref == 'center': target_ref_y = target_y - tree_h // 2

  当前参考坐标（从树当前包围盒获取）：
    if h_ref == 'left':   cur_ref_x = tree_left
    if h_ref == 'right':  cur_ref_x = tree_right
    if h_ref == 'center': cur_ref_x = (tree_left + tree_right) // 2

    if v_ref == 'top':    cur_ref_y = tree_top
    if v_ref == 'bottom': cur_ref_y = tree_bottom
    if v_ref == 'center': cur_ref_y = (tree_top + tree_bottom) // 2

  shift_x = target_ref_x - cur_ref_x
  shift_y = target_ref_y - cur_ref_y

第七步：平移整棵树
  if shift_x != 0 or shift_y != 0:
      _shift_dependents(root, shift_x, shift_y)
      根元素自身 + shift_x, + shift_y

第八步：padding 约束
  平移后重新计算树的视觉包围盒。
  如果溢出 padding 边界，计算 clip_x/clip_y 并再次整体平移回来。
```

### 8.4 `_resolve_tree_ref` 的完整映射

`_resolve_tree_ref(position, alignment)` 将根元素的 `position` + `alignment` 参数解析为 `(h_ref, v_ref)`，完全对齐 `_get_anchor` 的 14 种组合：

| position | alignment | h_ref | v_ref |
|----------|-----------|-------|-------|
| `top-left` / `tl` | 任意 | `left` | `top` |
| `top-right` / `tr` | 任意 | `right` | `top` |
| `top-center` / `tc` / `top` | 任意 | `center` | `top` |
| `bottom-left` / `bl` | 任意 | `left` | `bottom` |
| `bottom-right` / `br` | 任意 | `right` | `bottom` |
| `bottom-center` / `bc` / `bottom` | 任意 | `center` | `bottom` |
| `left` | `top` / `top-*` | `left` | `top` |
| `left` | `bottom` / `bottom-*` | `left` | `bottom` |
| `left` | 其他 | `left` | `center` |
| `right` | `top` / `top-*` | `right` | `top` |
| `right` | `bottom` / `bottom-*` | `right` | `bottom` |
| `right` | 其他 | `right` | `center` |
| `center` | 任意 | `center` | `center` |
| 任意 | **`both-center`** | `center` | `center` |

> **v1.12.0 新增**：`alignment='both-center'` 时 `_resolve_tree_ref` 直接返 `('center', 'center')`，整棵树以中心为参考点进行树级定位。

当 `position` 为 `top` 或 `bottom` 时，它本身不指定水平方向，此时：
- `alignment` 为 `left` / `top-left` / `bottom-left` → `h_ref = 'left'`
- `alignment` 为 `right` / `top-right` / `bottom-right` → `h_ref = 'right'`
- 其他（含 `both-center`）→ `h_ref = 'center'`

当 `position` 为 `left` 或 `right` 时，垂直方向由 `alignment` 决定（见上表，`both-center` 落入"其他"类）。

### 8.5 目标参考 y 的校正

`_calculate_absolute(tree_w, tree_h, root_cfg)` 返回的 `(target_x, target_y)` 是虚拟元素包围盒的**左上角**。在 `positions` 统一存储包围盒顶 y 的系统中，视觉底部 = `y + height`，因此目标参考点的计算方法为：

```
v_ref = 'bottom' → target_ref_y = target_y + tree_h  （树视觉底部 = 目标包围盒底）
v_ref = 'top'    → target_ref_y = target_y             （树视觉顶部 = 目标包围盒顶）
v_ref = 'center' → target_ref_y = target_y + tree_h // 2
```

```python
cur_ref_y = tree_bottom（或 tree_top、tree_center）
shift_y = target_ref_y - cur_ref_y
```

---

## 9. 三阶段渲染管线详解

`_add_text_and_icons_flexible()` 是渲染器中的主方法，控制整条文字渲染管线。以下按阶段逐一展开。

### 9.1 Phase 1：统一文本收集 + 尺寸测量

**收集三种来源的文本：**

```python
# --- 来源 1: info_position（EXIF / 相机信息）---
for key in info_positions:
    text = context.get_text(key)    # get_text 返回格式化文本，无数据返回 None
    if text:
        all_positions[key] = cfg
        text_elements.append((key, text))

# --- 来源 2: defined_texts（预定义文本）---
for key, entry in defined_texts_cfg.items():
    content = entry.get('content', '')
    if content:
        layout_cfg = {k: v for k, v in entry.items() if k != 'content'}
        all_positions[key] = layout_cfg
        text_elements.append((key, content))

# --- 来源 3: custom_text（用户输入）---
if custom_text_cfg.get('enabled', False):
    custom_text_content = context.get_text('custom_text')
    if custom_text_content:
        all_positions['custom_text'] = layout_cfg
        text_elements.append(('custom_text', custom_text_content))
```

**逐元素测量尺寸：**

对于 `text_elements` 中的每个 `(text_type, text)`：

```python
text_config = all_positions[text_type]
size_ratio = font_size_config.get(text_type, fonts.get('size_ratio', 0.02))
text_color = _determine_text_color(bg_fill_type, colors, text_type)

segments = FontManager.split_mixed_text(text)

if len(segments) <= 1:
    # === 单字体路径 ===
    font = load_font(fonts, original_image_size, size_ratio, text)
    bbox = font.getbbox(text)
    ascent, descent = font.getmetrics()
    draw_items[text_type] = {
        'text': text, 'font': font, 'color': text_color,
        'width': bbox[2] - bbox[0],      # 文本宽度
        'height': ascent + descent,       # 元素高度
        'descent': descent,
        'ascent': ascent,
        'mixed': False
    }
else:
    # === 混排路径（详见 10.2） ===
    drawn_fonts = {}
    seg_info = []
    total_width = 0
    for seg_text, is_cjk in segments:
        font = _get_segment_font(is_cjk)
        bbox = font.getbbox(seg_text)
        ascent, descent = font.getmetrics()
        seg_info.append((seg_text, font, bbox[2]-bbox[0], ascent, descent))
        total_width += bbox[2] - bbox[0]

    ref_font = drawn_fonts.get('latin') or drawn_fonts.get('cjk')
    ref_ascent, ref_descent = ref_font.getmetrics()
    max_ascent = max(s[3] for s in seg_info)
    max_descent = max(s[4] for s in seg_info)

    draw_items[text_type] = {
        'seg_info': seg_info,
        'ref_ascent': ref_ascent,
        'ref_descent': ref_descent,
        'color': text_color,
        'width': total_width,
        'height': max_ascent + max_descent,
        'ascent': ref_ascent,
        'mixed': True
    }
```

### 9.2 Phase 2：定位 + 注册

```python
# 预注册缺失参考元素锚点
for name in draw_items:
    cfg = all_positions[name]
    ref = cfg.get('relative_to')
    if ref and ref not in draw_items and ref in all_positions:
        ref_cfg = all_positions[ref]
        if not ref_cfg.get('relative_to'):
            rx, ry = layout_engine.calculate_position(0, 0, ref_cfg)
            layout_engine.register_element(ref, rx, ry, 0, 0, ascent=0)

# 拓扑排序
ordered_names = _resolve_element_order(text_elements, all_positions)

# 逐个定位 → 注册
for name in ordered_names:
    item = draw_items[name]
    cfg = all_positions[name]

    x, y = layout_engine.calculate_position(item['width'], item['height'], cfg)

    # descent 偏移：从包围盒顶转基线
    if item.get('type') == 'multiline':
        first_line = item['lines'][0]
        y -= first_line.get('ref_descent', first_line.get('descent', 0))
    elif item['mixed']:
        y -= item['ref_descent']
    else:
        y -= item['descent']

    # 确定 ascent 值用于注册
    if item.get('type') == 'multiline':
        first_line = item['lines'][0]
        element_ascent = (first_line.get('ref_ascent', 0)
                         if first_line.get('mixed')
                         else first_line.get('ascent', 0))
    else:
        element_ascent = item.get('ascent', 0)

    layout_engine.register_element(
        name, x, y,
        item['width'], item['height'],
        cfg.get('relative_to'),
        ascent=element_ascent
    )
```

### 9.3 Phase 2.5：树级组合定位

```python
layout_engine.apply_tree_positioning(all_positions)
```

参见第 8 章。

### 9.4 Phase 3：绘制

```python
for name in ordered_names:
    bounds = layout_engine.get_element_bounds(name)
    if bounds is None:
        continue
    x, y, w, h = bounds
    item = draw_items[name]
    cfg = all_positions[name]

    if item.get('type') == 'multiline':
        # === 多行文本绘制（详见第 11 章）===
        draw_multiline(x, y, w, item, cfg, draw)

    elif not item['mixed']:
        # === 单字体绘制 ===
        draw.text((x, y), item['text'], fill=item['color'], font=item['font'])

    else:
        # === 混排绘制（详见 10.2）===
        baseline_y = y + item['ref_ascent']
        current_x = x
        for seg_text, font, seg_width, ascent, descent in item['seg_info']:
            seg_y = baseline_y - ascent
            draw.text((current_x, seg_y), seg_text, fill=item['color'], font=font)
            current_x += seg_width
```

---

## 10. 字体引擎与混排渲染

### 10.1 FontManager

| 组件 | 详细说明 |
|------|---------|
| 字体对 | 拉丁：`Gotham-{weight}`（Gotham-Light / Gotham-Book / Gotham-Medium）；CJK：`GlowSansSC-Normal-{weight}` |
| CJK 检测 | 正则 `_CJK_CHAR_RE` 覆盖中日韩码位（U+4E00–U+9FFF、U+3400–U+4DBF、U+F900–U+FAFF、日文仮名 U+3040–U+30FF 等） |
| `split_mixed_text(text)` | 返回 `[(segment, is_cjk), ...]` 片段列表，例如 `"Leica M10-P 拍摄于东京"` → `[("Leica M10-P ", False), ("拍摄于", True), ("东京", True)]` |
| 缓存键 | `(font_family, font_weight, font_size, is_cjk)` → `FreeTypeFont` 实例 |
| 字号 | `max(12, int(reference_side * size_ratio))`，最小 12px |

### 10.2 混排渲染的基线对齐

混排渲染的难点在于中文字体（GlowSansSC）和拉丁字体（Gotham）的 ascent 值通常不同。如果简单以各自基线渲染，中文和拉丁文字会在视觉上错位。

**对齐方法**：以拉丁字体的基线为共享参考，所有片段共用同一个基线 y，CJK 片段的 ascent 如果大于拉丁 ascent，字形向上延伸但基线仍在同一水平线上：

```python
ref_font = drawn_fonts.get('latin')  # 以 Gotham 为参考
ref_ascent, ref_descent = ref_font.getmetrics()

shared_baseline = y + ref_ascent   # 共享基线在 bound box 中的位置

for seg_text, font, seg_width, ascent, descent in seg_info:
    seg_y = shared_baseline - ascent  # 当前片段的绘制 y（基线对齐）
    draw.text((current_x, seg_y), seg_text, fill=color, font=font)
    current_x += seg_width
```

```
               ┌────┐
               │    │
 ──────────────╪────╪──────────────  ← 共享基线
               │    │
               └────┘
 ↑              ↑
 ref_ascent    CJK_ascent（可能更高，字形上伸更多但不影响基线位置）
```

---

## 11. 多行文本处理

### 11.1 测量

```python
lines = text.split('\n')
line_infos = []
total_width = 0
total_height = 0

for line_text in lines:
    if not line_text:
        total_height += line_spacing_px    # 空行：只记行间距
        continue
    # 对每行运行单行测量（同 Phase 1）
    line_info = measure_single_line(line_text, fonts, ...)
    line_infos.append(line_info)
    total_width = max(total_width, line_info.width)
    total_height += line_info.height

# 末尾减去多余的 line_spacing（最后一行之后不追加间距）
total_height -= line_spacing_px
```

行间距计算：
```python
default_line_spacing_ratio = fonts.get('line_spacing_ratio', 0.005)
ratio = element_config.get('line_spacing_ratio', default_line_spacing_ratio)
line_spacing_px = int(reference_side * ratio)
```

### 11.2 绘图

```python
current_y = y  # 块的第一行基线 y
for line_info in lines:
    # 行内缩进：由 alignment 决定
    if alignment in ('right', 'bottom-right', 'top-right'):
        line_x = x + (block_width - line_width)
    elif alignment in ('center', 'bottom-center', 'top-center'):
        line_x = x + (block_width - line_width) // 2
    else:
        line_x = x

    if single_font:
        draw.text((line_x, current_y), text, fill=color, font=font)
    else:
        # 混排行：走混排绘制路径
        baseline_y = current_y + ref_ascent
        ...

    current_y += line_info.height + line_spacing_px
```

---

## 12. RenderContext 渲染上下文

所有显示文本的统一入口。`get_text(key)` 返回对应 key 的格式化文本，无数据时返回 `None`。

| Key | 输出格式 | 数据来源 | 说明 |
|-----|---------|---------|------|
| `exif` | `"35mm, f/2.8, 1/125s, ISO200"` | `display_data['exif_formatted']` | 组合字符串 |
| `timestamp` | `"2025.01.15 14:30:00"` | `exif_data['datetime_original']` | 原始拍摄时间 |
| `timestamp_author` | `"2025.01.15 14:30:00 by Frank"` | datetime + author | 作者为空时仅显示时间 |
| `camera_lens` | `"Leica Q3"` 或 `"Leica Q3 \| Summilux 28mm"` | `camera_combined` / `camera_lens_combined` | 由 lens_display_mode 和 use_short_lens 控制 |
| `camera` | `"Leica Q3"` | `display_data['camera_combined']` | 品牌 + 型号 |
| `camera_make` | `"Leica"` | `display_data['camera_make']` | 映射后品牌 |
| `lens` | `"Summilux 28mm"` / `"28mm"` | `lens_model` / `short_lens` | 受 use_short_lens 控制 |
| `author` | `"Frank"` | 用户输入 | 用户输入 |
| `location` | `"Shanghai"` | 用户输入 | 用户输入 |
| `gps` | `"40°26'N 79°56'W"` | `exif_data['gps']` | GPS 度分秒格式 |
| **`custom_text`** (v1.7.0) | 用户输入文本 | GUI `st.text_area` 或 CLI `--custom-text` | 多行文本 |
| **`focal_length_formatted`** (v1.7.0) | `"35mm"` | `raw_focal_length_35mm` → 回退 `raw_focal_length` | 优先 35mm 等效焦距 |
| **`aperture_formatted`** (v1.7.0) | `"f/2.8"` | `raw_aperture` | — |
| **`shutter_speed_formatted`** (v1.7.0) | `"1/125s"` | `raw_shutter_speed`（已格式化）+ "s" | 分数/小数自动 |
| **`iso_formatted`** (v1.7.0) | `"200"`（纯数字） | `raw_iso` | 不含"ISO"前缀 |

---

## 13. Logo 渲染

| 处理步骤 | 详细说明 |
|---------|---------|
| 加载 | `Image.open(logo_path)` → 转换为 RGBA 模式 |
| 缩放基准 | Logo 短边 = `int(reference_side * size_ratio)` |
| 对角线保护 | 若缩放后对角线 > `2 × size_ratio × reference_side`，以对角线为上限等比缩小 |
| 定位 | `layout_engine.calculate_position(new_w, new_h, logo_config)` —— 支持绝对和相对定位 |
| 粘贴 | `result.paste(logo, (x, y), logo)` —— 使用 alpha 通道混合 |
| 注册 | `layout_engine.register_element('logo', x, y, new_w, new_h, ascent=0)` |
| 颜色自适应 | 暗背景优先 `_white` 后缀 Logo；亮背景优先非 `_white` 后缀 |
| 渲染顺序 | Phase 3 之后（文字层之后），可 `relative_to` 引用文字元素 |

---

## 14. 关键参数速查

### `layout.` 顶层字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `expand_canvas` | `dict{enabled, top, bottom, left, right}` | 画布扩展比例 |
| `padding` | `dict{top, bottom, left, right}` | 安全区域比例 |
| `corner_radius` | `dict{enabled, top_left, top_right, bottom_left, bottom_right}` | 原图四角圆角系数（v1.8.0） |
| `info_position` | `dict{key: positioning_config}` | EXIF/相机信息的定位配置 |
| `defined_texts` | `dict{key: {content, positioning_config}}` | 预定义文本，key 采用补零编号 |
| `custom_text` | `dict{enabled, positioning_config}` | 自定义文本 |

### `positioning_config` 定位配置参数

**默认值**：`placement='outside'`, `position='bottom'`, `alignment='center'`

**绝对定位参数**（根元素）：
| 参数 | 类型 | 说明 |
|------|------|------|
| `placement` | `'inside'` / `'outside'` | 元素在原图内侧还是外侧 |
| `position` | 14 种锚点 | 绑定到原图的哪条边/角 |
| `alignment` | `'left'` / `'center'` / `'both-center'` / `'right'` | 元素自身对齐方式；`both-center` 使元素中心与锚点重合 |
| `margin` | `float` / `int` | 统一边距 |
| `margin_top` / `_bottom` / `_left` / `_right` | `float` / `int` | 各方向独立边距 |
| `tree_align` | `boolean` | v1.7.0：启用树级组合定位 |

**相对定位参数**（`relative_to` 元素）：
| 参数 | 类型 | 说明 |
|------|------|------|
| `relative_to` | `string` | 参考元素名称 |
| `relative_position` | `'after'` / `'below'` / `'before'` / `'above'` / `'right-of'` / `'left-of'` | 相对位置 |
| `alignment` | `'left'` / `'center'` / `'both-center'` / `'right'` | 相对于参考元素的对齐方向；`both-center` 等价于 `center` |
| `relative_margin` | `float` | 间距比例（默认 0.01） |
| `offset_x_ratio` / `offset_y_ratio` | `float` | 微调偏移（默认 0） |

### `fonts.` 下字段

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `family` | `"Gotham"` | 字体族名 |
| `weight` | `"medium"` | `'light'` / `'regular'` / `'medium'` |
| `size_ratio` | `0.02` | 默认字号 = `int(reference_side * ratio)` |
| `line_spacing_ratio` | `0.005` | 多行行间距比（v1.7.0） |
| `sizes` | `{}` | 各元素独立字号：`{key: ratio}` |

### `colors.` 下字段

三层优先级，从上到下：
```
1. custom_{key}_dark_color / custom_{key}_light_color      # 按元素类型覆盖
2. custom_text_dark_color / custom_text_light_color         # 通用兜底
3. 深色背景 = (255, 255, 255) / 浅色背景 = (0, 0, 0)        # 最终默认
```

---

## 15. 常见问题

### Q: `right-of` + `alignment: "bottom"` 为什么不对齐？

v1.7.0 之前这是已知 bug（旧版在 Phase 2 注册时做了 `y -= descent` 将包围盒顶转为基线，导致 `positions` 存储的 ty 成为基线而非包围盒顶，`_align_y("bottom", ty, th, eh)` 计算出错）。v1.7.0 最终版采用统一坐标注册——`positions` 存储包围盒顶 y —彻底消除了这一歧义，`_align_y` 的原始公式直接工作。

### Q: `apply_tree_positioning` 为什么把我原来的垂直链（如 exif → timestamp_author）推走了？

这是因为早期版本对所有依赖树自动应用了树级定位。v1.7.0 已改为 `tree_align` opt-in 模式：只有根元素声言 `tree_align: true` 的依赖树才会进入树级定位流程。原有的垂直链不受影响。

### Q: 如何让一整行水平居中？

```yaml
defined_texts:
  root_item:
    content: "xxx"
    position: "bottom"        # 控制垂直位置（底部）
    alignment: "center"       # 水平居中，作用于整棵树
    tree_align: true           # ← 启用树级定位
    margin_bottom: 0.03
  child:
    content: "..."
    relative_to: "xxx"
    relative_position: "right-of"  # 水平链
```

根元素的 `position: "bottom"` + `alignment: "center"` + `tree_align: true` 会将整棵依赖树居中。若需双轴居中（元素中心与锚点重合），使用 `alignment: "both-center"`。

### Q: `tree_align: true` 对单元素有影响吗？

没有。单元素树（没有 `relative_to` 子元素的根元素，或本身是其他元素子元素的元素）在 `apply_tree_positioning` 中通过 `len(tree_members) <= 1` 判断后自动跳过。

### Q: 水平链过长，超出画布怎么办？

`apply_tree_positioning` 在最后一步做 padding 约束——如果平移后的整棵树超出安全区域，会触发第二次整体平移回到 padding 边界内。如果树宽超过 `pad_right - pad_left` 则必定溢出，需要减小字号或缩短文本内容。

---

## 16. 原图圆角裁切

> v1.8.0 新增

### 16.1 功能概述

在渲染管线的原图粘贴步骤前，允许对原始照片的四角进行独立圆角裁切。通过样式配置中的 `corner_radius` 段控制开关与半径。

### 16.2 配置格式

```yaml
layout:
  corner_radius:
    enabled: true
    top_left: 0.01        # 半径系数，相对于 reference_side（原图短边）
    top_right: 0.01
    bottom_left: 0.01
    bottom_right: 0.01
```

- `enabled`: 布尔值，缺省 `false`
- `top_left` / `top_right` / `bottom_left` / `bottom_right`: 四角独立系数，乘以 `reference_side` 得像素半径。值为 `0` 时该角保持直角
- 整个 `corner_radius` 字段缺失、`enabled != true`、或所有半径系数同时为 0 时，完全跳过此步骤

### 16.3 实现位置

`src/core/renderer.py` → `_rounded_corner_mask()` + `render_frame()` 第 127-150 行

### 16.4 蒙版生成算法

函数 `_rounded_corner_mask(w, h, r_tl, r_tr, r_bl, r_br)` 返回灰度蒙版（255=保留，0=切除）。

从几何上看，四角独立圆角的蒙版可以理解为：在每个角的 r×r 方形区域内，方形减去一个 1/4 圆即为需要切除的部分。如果忽略抗锯齿，用 PIL 的 `rectangle + pieslice` 即可实现：

```python
# 几何示意：在每个角先填黑方形，再画白色 1/4 扇形恢复圆弧内部
draw.rectangle([0, 0, r_tl, r_tl], fill=0)
draw.pieslice([0, 0, r_tl * 2, r_tl * 2], start=180, end=270, fill=255)
```

但实际实现改用 **numpy SDF（signed distance field）** 来获得抗锯齿效果：在四个 r×r 角区域内，用 `np.ogrid` 生成网格坐标，计算每个像素到圆心的欧几里得距离，通过 `np.clip(r - dist + 0.5, 0, 1)` 在圆弧边界处产生 **1px 线性过渡**（内侧 α=1.0，外侧 α=0.0），实现相同的几何切除效果的同时消除像素级硬边产生的锯齿：

```python
mask = np.full((h, w), 255, dtype=np.float32)

iy, ix = np.ogrid[:r_tl, :r_tl]
dist = np.sqrt((ix - r_tl) ** 2 + (iy - r_tl) ** 2)
mask[:r_tl, :r_tl] = np.clip(r_tl - dist + 0.5, 0, 1) * 255
```

**性能**：只对四个 r×r 小方块做运算，不扫描全图。例如 r=50 时仅 `4×50×50 = 10000` 像素。

### 16.5 合成流程

1. `render_frame()` 检测 `corner_cfg.get('enabled') == True`
2. 读取四角系数并乘以 `reference_side` 得像素半径
3. 若任一方向半径 > 0，创建蒙版
4. 将原图 `convert('RGBA')` 并用 `putalpha(mask)` 写入 Alpha 通道
5. 以自身 RGBA 为遮罩粘贴到背景画布上

```python
img_rgba = image.convert('RGBA')
mask = _rounded_corner_mask(orig_w, orig_h, r_tl, r_tr, r_bl, r_br)
img_rgba.putalpha(mask)
positioned_image.paste(img_rgba, (orig_x, orig_y), img_rgba)
```

### 16.6 兼容性

- 与 `expand_canvas` 完全兼容：圆角在原图边界内裁切，不影响扩出的画布区域
- 与 `padding` 完全兼容：文字/Logo 层在圆角之上绘制，不受影响
- 与高斯模糊背景、装饰层等完全兼容：圆角在原图图层上处理，不影响上层
