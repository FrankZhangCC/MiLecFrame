# 布局引擎与渲染器算法文档

> 对应模块：`src/utils/layout_engine.py`（LayoutEngine）和 `src/core/renderer.py`（FrameRenderer）
>
> 版本：v1.7.0，2026-05-18

---

## 1. 架构总览

```
Phase 1 ── 测量所有元素的字体/尺寸/颜色
  │
  ├── info_position 的元素 → context.get_text(key)        （EXIF/相机信息）
  ├── defined_texts  的元素 → entry['content']             （预定义文本）
  └── custom_text    元素   → context.get_text('custom_text') （自定义文本）
  │
  ▼
Phase 2 ── 按拓扑排序计算位置 + 注册到 register
  │
  ├── _resolve_element_order()    ← Kahn 算法拓扑排序
  ├── calculate_position()        ← 绝对/相对定位
  └── register_element()          ← 存入 positions 注册表
  │
  ▼
Phase 2.5 ── 依赖树组合定位（v1.7.0 新增）
  │
  └── apply_tree_positioning()    ← 整棵树按根配置重新定位
  │
  ▼
Phase 3 ── 从注册表读取最终坐标 + 绘制
  │
  ├── 单字体行：draw.text(x, y, text)
  ├── 混排：逐片段 + 基线对齐
  └── 多行：逐行 + 行间距
```

---

## 2. LayoutEngine 类

### 2.1 坐标系与参照系

- **参照边（reference_side）**：`min(original_width, original_height)` — 所有比例系数（size_ratio、margin、padding 等）的基准值
- **画布（canvas）**：经过 `expand_canvas` 扩展后的完整绘图区域
- **原图边界（original_bounds）**：`(ox, oy, ow, oh)` — 原始图像在画布中的位置
- **安全区域（padding_bounds）**：`(left, top, right, bottom)` — 所有叠加元素的最终活动范围，画布四边向内收缩

### 2.2 位置注册表（positions）

```
self.positions: Dict[str, dict] = {
  ex: {'x': 100, 'y': 200, 'width': 300, 'height': 40, 'ascent': 32}
}
```

所有已定位元素的坐标、尺寸和基线 ascent 值。**关键约定**：

- 对于文字元素，`y` 是 **基线（baseline）y 坐标**（不是包围盒顶部）
- 对于非文字元素（Logo、占位锚点），`y` 是包围盒顶部 y 坐标
- `height` = `ascent + descent`（文字元素）或视觉高度（非文字元素）
- `ascent`：文字元素用 `font.getmetrics()[0]`；混排用 `ref_ascent`；非文字用 0/None

基线偏移约定的成因：
```
register_element 前做了 y -= descent → y 从"包围盒顶"变成"基线"
draw.text(x, y, text) 的语义就是"在 y 处放基线"
视觉底部 = y_registered + descent = y_calc（布局引擎返回的包围盒顶）
视觉顶部 = y_registered - ascent = y_calc - (ascent + descent)
```

### 2.3 依赖图（_dependents）

```
self._dependents: Dict[str, list] = {
  'exif': ['timestamp_author', 'location'],  # exif 的子节点
  'camera_lens': ['location'],                # camera_lens 的子节点
}
```

由 `register_element(name, ..., relative_to='parent')` 自动维护。用于：
- 拓扑排序时确定处理顺序
- 组合盒约束时收集从属元素
- 树定位时递归遍历整棵依赖树
- `_shift_dependents()` 级联平移

---

## 3. 绝对定位系统

### 3.1 `calculate_position(w, h, config)`

分发逻辑：
- 有 `relative_to` → 调用 `_calculate_relative()`
- 无 `relative_to` → 调用 `_calculate_absolute()`

### 3.2 `_calculate_absolute(w, h, config)`

参数：
- `placement`: `'inside' | 'outside'`（默认 `'outside'`）
- `position`: 14 种锚点，见下方
- `alignment`: `'left' | 'center' | 'right'`
- `margin` / `margin_top` / `margin_bottom` / `margin_left` / `margin_right`

锚点锚定到**原图边界**（非画布边界），带 padding 约束。

**拆分为 placement + position + alignment 三个正交参数**（v1.4.0 重构）：

| position 值 | 水平参考 | 垂直参考 | 说明 |
|------------|---------|---------|------|
| `top-left` / `tl` | 左边缘 | 顶部 | 固定组合 |
| `top-right` / `tr` | 右边缘 | 顶部 | 固定组合 |
| `top-center` / `tc` | 水平居中 | 顶部 | 固定组合 |
| `top` | 由 alignment 决定 | 顶部 | alignment 控制水平 |
| `bottom-left` / `bl` | 左边缘 | 底部 | 固定组合 |
| `bottom-right` / `br` | 右边缘 | 底部 | 固定组合 |
| `bottom-center` / `bc` | 水平居中 | 底部 | 固定组合 |
| `bottom` | 由 alignment 决定 | 底部 | alignment 控制水平 |
| `left` | 左边缘 | 由 alignment 决定 | alignment 控制垂直 |
| `right` | 右边缘 | 由 alignment 决定 | alignment 控制垂直 |
| `center` | 画布居中 | 画布居中 | 不受 placement/margin 影响 |

**placement 语义**：
- `inside`：元素在原图矩形内部，margin 从边界向内偏移
- `outside`：元素在原图矩形外部，margin 从边界向外偏移

**margin 层级**（`_resolve_margins`）：
```
1. 统一 margin → 四边初始值（未设 = 0）
2. margin_top / margin_bottom / margin_left / margin_right → 各自覆盖对应方向
3. float = reference_side * ratio, int = 绝对像素
```

**padding 约束**（最后应用）：
```
x = max(pad_left, min(x, pad_right - w))
y = max(pad_top, min(y, pad_bottom - h))
```
padding 优先级高于 margin。

### 3.3 `_get_anchor(placement, position, alignment, ox, oy, ow, oh, ew, eh, m)`

绝对定位的核心算法，根据 placement + position + alignment 三参数计算 `(x, y)`。

**对齐函数**：

`_align_x(alignment, ox, ow, ew, m)`：
- `'left' / 'top-left' / 'bottom-left'` → `ox + m['left']`
- `'right' / 'top-right' / 'bottom-right'` → `ox + ow - ew - m['right']`
- 其他 → `ox + (ow - ew) // 2`（居中）

`_align_y(alignment, oy, oh, eh, m)`：
- `'top' / 'top-left' / 'top-right'` → `oy + m['top']`
- `'bottom' / 'bottom-left' / 'bottom-right'` → `oy + oh - eh - m['bottom']`
- 其他 → `oy + (oh - eh) // 2`（居中）

---

## 4. 相对定位系统

### 4.1 `_calculate_relative(w, h, config)`

参数：
- `relative_to`: 参考元素名称
- `relative_position`: `'after' / 'below' / 'before' / 'above' / 'right-of' / 'left-of'`
- `relative_margin`: 间距比（默认 0.01）
- `alignment`: 相对于参考元素的对齐方式
- `offset_x_ratio / offset_y_ratio`: 微调偏移（默认 0）

### 4.2 基线偏移校正（v1.7.0 修复）

问题：参考元素注册时的 `y` 已做 `-= descent` 偏移（从包围盒顶变为基线），但 `_calculate_relative` 将 `(tx, ty, tw, th)` 中的 `ty` 当作包围盒顶部处理，导致所有 y 轴对齐计算出错。

修复：每个 `positions` 条目新增 `ascent`，计算时校正视觉边界：

```python
# 给定位移前的视觉校正：
ref_ascent = self.positions[relative_to].get('ascent')
if ref_ascent is not None and ref_ascent > 0:
    ref_visual_top = ty - ref_ascent
    ref_visual_bottom = ty + (th - ref_ascent)  # = ty + descent
else:
    ref_visual_top = ty
    ref_visual_bottom = ty + th
```

### 4.3 相对位置定位公式

参考元素的视觉包围盒 `(ref_visual_top, ref_visual_bottom)` 确定后：

**水平参考方向**（`right-of` / `left-of`）：

| alignment | `right-of` | `left-of` |
|-----------|-----------|-----------|
| `bottom` (含组合) | `y = ref_visual_bottom` | `y = ref_visual_bottom` |
| `top` (含组合) | `y = ref_visual_top + element_height` | `y = ref_visual_top + element_height` |
| `center` / 其他 | `y = (ref_visual_top + ref_visual_bottom + element_height) // 2` | 同上 |

其中 `element_height = ascent + descent`（或 `max_ascent + max_descent`）。

**垂直参考方向**（`after` / `below` / `before` / `above`）：

| relative_position | y 公式 | 说明 |
|-------------------|--------|------|
| `after` / `below` | `y = ref_visual_bottom + element_height + margin_px` | 元素位于参考下方，descent 调整后视觉顶距参考视觉底恰为 margin |
| `before` / `above` | `y = ref_visual_top - element_height - margin_px` | 元素位于参考上方 |

所有位置的 `x` 或 `y` 推导均遵循同一个原则：**`y`（布局引擎返回值）是包围盒顶部，descent 调整后视觉底部 = `y`**。

### 4.4 组合盒约束与级联平移

当相对定位元素放置时，它与参考元素（及所有已注册从属）构成**组合盒**。如果组合盒超出 padding 安全区域，整个组合盒整体平移：

```python
group_left   = min(tx, x)
group_top    = min(ref_visual_top, y)
group_right  = max(tx + tw, x + element_width)
group_bottom = max(ref_visual_bottom, y + element_height)

if group_left < pad_left:
    shift_x = pad_left - group_left
elif group_right > pad_right:
    shift_x = pad_right - group_right
```

平移通过 `_shift_dependents()` 沿依赖树级联传播：

```python
def _shift_dependents(self, name, shift_x, shift_y):
    for dep_name in self._dependents.get(name, []):
        self.positions[dep_name]['x'] += shift_x
        self.positions[dep_name]['y'] += shift_y
        self._shift_dependents(dep_name, shift_x, shift_y)
```

---

## 5. 拓扑排序（Phase 2 顺序控制）

```python
_resolve_element_order(text_elements, all_positions) → List[str]
```

使用 Kahn 算法（BFS 入度计数）：
1. 建立依赖图：对有 `relative_to` 的元素添加边
2. 入度为 0 的元素（无依赖）入队
3. 每次出队 → 加入有序列表 → 依赖者入度 -1 → 入度 0 时入队
4. 兜底：未被覆盖的元素（循环依赖等）按原序追加

保证绝对定位元素（根）先于相对定位元素（子孙）处理。

**缺失参考元素保护**：当 `relative_to` 指向的元素因无文本被跳过但仍存在于配置中时，以 0×0 尺寸预先注册其绝对位置锚点，避免依赖元素降级为默认绝对定位导致位置偏移。

---

## 6. 树级组合定位（Phase 2.5）

### 6.1 动机

现有相对定位只能实现「A 在 B 右侧」这种单一元素级别的控制。当多个元素通过 `relative_to` 链组成「A → B → C → D」时，只有根 A 有绝对定位控制权，整条链必然偏向 A 所在的一侧。用户需要将**整条链**当作一个整体，按 `position / alignment / margin` 做一次**整体绝对定位**。

### 6.2 启用方式

在根元素的 positioning config 中添加 `tree_align: true` 显式开启：

```yaml
defined_texts:
  defined_text_01:
    content: "FL"
    position: "bottom"
    alignment: "center"
    tree_align: true       # ← 开启树级组合定位
    margin_bottom: 0.07
```

未声明 `tree_align` 的依赖树（原版所有样式配置）不受影响，行为与 v1.7.0 之前完全一致。

### 6.2 算法（`apply_tree_positioning`）

```
for each root in positions (元素无 relative_to):
    1. _collect_tree_members(root, members)
       → 递归 _dependents, 得 {root, child1, child2, ...}

    2. _compute_visual_bounds(members)
       → (tree_left, tree_top, tree_right, tree_bottom)

    3. target_x, target_y = _calculate_absolute(tree_w, tree_h, root_cfg)
       → 树应有的包围盒左上角

    4. _resolve_tree_ref(position, alignment) → (h_ref, v_ref)

    5. target_ref = (target_x [± w/2 ± w], target_y [± h ∓ h/2])
       cur_ref     = (tree_xxx, tree_yyy)
       shift = target_ref - cur_ref

    6. _shift_dependents(root, shift_x, shift_y)
       平移根节点自身

    7. padding 约束：重新计算包围盒，若溢出则再次整体平移
```

**核心洞察**：`_calculate_absolute(tree_w, tree_h, cfg)` 返回的是**包围盒顶部**坐标。在 descent 调整语义下，视觉底部 = `y_calc`。因此垂直参考点的 target_ref 使用 `y_calc`（底部）或 `y_calc - tree_h`（顶部），而非 `y_calc + tree_h`。

### 6.3 `_resolve_tree_ref` 的14种position映射

依赖树定位的水平和/垂直参考方向完全对齐 `_get_anchor` 的 14 种 position 组合：

```python
position='bottom' + alignment='center' → (h='center', v='bottom')
position='left'   + alignment='bottom' → (h='left',   v='bottom')
position='center'                      → (h='center', v='center')
# ...（全部 14 种组合）
```

### 6.4 响应式行为

`tree_w / tree_h` 随时间变化（依赖实际的文本内容长度）。平移量自动适应：
- 文本变长 → tree_w 变大 → 居中时 shift_x 自动调整
- 字体比例变大 → tree_h 变大 → 底部对齐时 shift_y 自动调整

不需要任何手动协调，因为 shift 是相对量（target - current）。

---

## 7. RenderContext（渲染上下文）

所有显示文本的统一入口。`get_text(key)` 返回对应 key 的格式化文本，无数据时返回 `None`：

| Key | 格式 | 数据来源 |
|-----|------|---------|
| `exif` | `"35mm, f/2.8, 1/125s, ISO200"` | `display_data['exif_formatted']` |
| `timestamp` | `"2025.01.15 14:30:00"` | `exif_data['datetime_original']` |
| `timestamp_author` | `"2025.01.15 14:30:00 by Frank"` | datetime + author |
| `camera_lens` | `"Leica Q3 \| Summilux 28mm"` | 由 lens_display_mode + use_short_lens 控制 |
| `camera` | `"Leica Q3"` | `camera_combined` |
| `camera_make` | `"Leica"` | 映射后品牌 |
| `lens` | `"Summilux 28mm"` | 受 short_lens 开关控制 |
| `author` | `"Frank"` | 用户输入 |
| `location` | `"Shanghai"` | 用户输入 |
| `gps` | `"40°26'N 79°56'W"` | EXIF GPS 度分秒 |
| **`custom_text`** (v1.7.0) | 用户输入文本 | GUI 或 CLI 传入 |
| **`focal_length_formatted`** (v1.7.0) | `"35mm"` | 优先 35mm 等效 |
| **`aperture_formatted`** (v1.7.0) | `"f/2.8"` | raw_aperture |
| **`shutter_speed_formatted`** (v1.7.0) | `"1/125s"` | raw_shutter_speed |
| **`iso_formatted`** (v1.7.0) | `"ISO200"` | raw_iso |

---

## 8. 字体引擎

### 8.1 FontManager

- 双字体引擎：Gotham（拉丁）+ GlowSansSC（CJK/日文）
- 中英文检测：`_CJK_CHAR_RE` 正则覆盖中日韩码位
- `split_mixed_text(text)` → `[(segment, is_cjk), ...]` 将混排字符串拆分为片段
- 缓存键：`(font_family, font_weight, font_size, is_cjk)` → 字体实例
- 字号 = `max(12, reference_side * size_ratio)` 像素

### 8.2 混排渲染

以拉丁字体的基线为共享参照，CJK 片段上移适配：

```
ref_ascent_latin = Gotham.getmetrics()[0]
shared_baseline = y + ref_ascent_latin
segment_y = shared_baseline - segment_ascent
```

---

## 9. 多行文本（v1.7.0）

### 9.1 测量

按 `\n` 拆行，逐行复用单行测量逻辑：

```
block_width  = max(all_line_widths)
block_height = sum(line_heights) + (num_lines - 1) * line_spacing_px
line_spacing_px = int(reference_side * line_spacing_ratio)
```

### 9.2 定位

整个文本块当作一个整体元素，`calculate_position(block_w, block_h, cfg)` 正常计算。

### 9.3 绘制

逐行绘制，行内按 alignment 缩进：
```
current_y = registered_y
for each line:
    if alignment == 'right': line_x = x + (block_w - line_w)
    elif alignment == 'center': line_x = x + (block_w - line_w) // 2
    else: line_x = x
    draw.text(line_x, current_y, line_text, ...)
    current_y += line_height + line_spacing_px
```

---

## 10. Logo 渲染（`_add_logo`）

- 缩放基准：Logo 短边 = `reference_side * size_ratio`
- 对角线上限保护：`logo_diagonal ≤ 2 * reference_side * size_ratio`
- 支持绝对定位和相对定位（`relative_to` 可引用文字元素坐标）
- 背景明暗自适应：暗背景 → `_white` 后缀 Logo，亮背景 → 非 `_white`
- 渲染顺序：文字层之后，可引用文字注册的坐标

---

## 11. 关键参数速查

### `layout.` 下字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `expand_canvas` | dict | `{enabled, top, bottom, left, right}` |
| `padding` | dict | `{top, bottom, left, right}` 安全区域 |
| `info_position` | dict | `{key: positioning_config}` EXIF/相机信息 |
| `defined_texts` | dict | `{key: {content, ...}}` 预定义文本 |
| `custom_text` | dict | `{enabled, ...}` 自定义文本 |

### `positioning_config` 定位参数

默认值：placement=`outside`, position=`bottom`, alignment=`center`

**绝对定位**：placement / position / alignment / margin / margin_*

**相对定位**：relative_to / relative_position / alignment / relative_margin / offset_x_ratio / offset_y_ratio

### `fonts.` 下字段

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `family` | `"Gotham"` | 字体族 |
| `weight` | `"medium"` | 字重 (light/regular/medium) |
| `size_ratio` | `0.02` | 默认字号比例 |
| `line_spacing_ratio` | `0.005` | 多行行间距比（v1.7.0） |
| `sizes` | `{}` | 各元素独立字号：`{key: ratio}` |

### `colors.` 下字段

两层优先级：
1. `custom_{key}_dark_color` / `custom_{key}_light_color`（按元素类型覆盖）
2. `custom_text_dark_color` / `custom_text_light_color`（通用兜底）
3. 最终兜底：深色背景 = 白色 `(255,255,255)`，浅色背景 = 黑色 `(0,0,0)`

---

## 12. 常见问题

### Q: `right-of` + `alignment: "bottom"` 为什么不对齐？

v1.7.0 之前这是已知 bug（基线偏移）。确认 `layout_engine.py` 版本 ≥ 1.7.0，且 `register_element` 调用了 `ascent` 参数。相关 fix 详见 `_calculate_relative` 中的 `ref_visual_top` / `ref_visual_bottom` 计算逻辑。

### Q: 树定位后元素跑到了 padding 外面？

`apply_tree_positioning` 内部已做 padding 约束——如果树定位后整体溢出，会触发第二次整体平移回到安全区域。如果仍然溢出，检查树的 bounding box 是否已经超出 `padding_bounds` 能容纳的范围。

### Q: 如何让一整行水平居中？

```yaml
defined_texts:
  root_item:
    content: "xxx"
    position: "bottom"       # 控制垂直位置
    alignment: "center"      # 控制水平居中（作用于整棵树）
    margin_bottom: 0.03
  child_1:
    content: "..."
    relative_to: "xxx"
    relative_position: "right-of"
```

`root_item` 的 `position: "bottom"` + `alignment: "center"` 会将整棵依赖树居中。

### Q: 树定位对单元素有影响吗？

无。单元素树（无 `relative_to` 引用的元素，或无子元素的元素）在 `apply_tree_positioning` 中自动跳过。
