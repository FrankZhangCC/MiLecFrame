# `position` / `alignment` 语义修复执行方案

> 制定日期：2026-09-22；修订日期：2026-09-23  
> 前置审计：[`POSITION_ALIGNMENT_SEMANTICS_AUDIT_AND_FIX_PLAN.md`](./POSITION_ALIGNMENT_SEMANTICS_AUDIT_AND_FIX_PLAN.md)  
> 文档性质：可直接按阶段执行的工程实施计划；本文件不表示代码已经修改

## 1. 目标与非目标

### 1.1 最终目标

本次修复必须建立并贯彻以下两个互不重叠的语义：

1. `position` 从照片的九个方位点中选出**照片参考点**；
2. `position` 再结合 `margin_*`（以及既有的 `placement` 内外方向）计算唯一的**元素锚点坐标**；
3. `alignment` 决定元素布局盒相对于该元素锚点如何摆放，也就是元素布局盒的哪条边、哪个角或中心点贴到元素锚点；
4. 文字、Logo、矩形和 `tree_align` 组合树使用同一套绝对定位几何；
5. 运行时只保留这一套新语义，不提供旧算法分支、语义版本开关或兼容别名；
6. 旧算法源码仅作为不可执行的离线备份供排查和迁移参考；
7. InfoCard 的左右对齐问题得到真实修复，而不是继续用 margin 补偿文字宽度。

权威数据流如下：

```text
照片边界
   │
   ├─ position ──> 照片九点中的一个参考点 (px, py)
   │
   └─ margin / placement ──> 元素锚点 (ax, ay)
                                  │
元素宽高 (ew, eh) + alignment ────┘
                                  │
                                  └─> 元素布局盒左上角 (x, y)
```

必须始终满足：

- position 阶段不得读取元素宽高；
- alignment 阶段不得读取照片边界、position、placement 或 margin；
- margin 只移动元素锚点，不直接移动元素某条边；
- 对文字而言，“元素”是测量后的文字布局盒；alignment 控制整个文字布局盒相对元素锚点的上下左右关系，不负责多行文本块内部的行对齐。

### 1.2 本次同时解决的问题

- 复合 position 提前返回，导致 alignment 被忽略；
- `both-center` 在 inside 分支补偿方向错误；
- `top` 与 `top-center`、`bottom` 与 `bottom-center` 同名异义；
- `position: center` 错用画布中心；
- `tree_align` 重复解释 position/alignment；
- 多行文字复用 alignment 作为行内对齐；
- 相对定位接受轴向无意义的 alignment 并静默回退；
- PySide6 元素编辑器的相对 alignment 下拉框保存无效；
- StyleManager 未验证定位枚举及组合；
- 内置样式依赖旧隐式语义，算法修改后存在视觉回归风险。

### 1.3 非目标

本次不处理：

- 水印 `Decorator.add_watermark()` 的独立定位系统；
- 字体选择、字偶距或文本内容格式化；
- 新增自动化测试框架；
- 重写相对定位的依赖图和组合盒算法；
- 改变 padding 的“最终安全区域约束”职责；
- 改变画布扩展、照片圆角、矩形效果栈或图层合成顺序；
- 发行版本号、tag 或分支合入，直到全部人工门禁完成。

## 2. 本方案锁定的设计决策

为避免实施过程中再次出现语义分叉，本节的决策在编码前固定。

### 2.1 单一语义与旧算法归档

本次采用一次性破坏性重构，运行时没有 `legacy-v1`、`anchor-v2` 或
`positioning_semantics`：

- `LayoutEngine` 只实现本文定义的新算法；
- 当前全部内置样式、代码内默认配置、模板和 GUI 模型在同一任务中完成迁移；
- 外部旧样式不做自动猜测或静默转换，校验失败时给出字段路径、旧值和迁移建议；
- 旧算法在重写前原样复制到
  `docs/legacy/positioning_v1/layout_engine.py.txt`；
- 归档目录增加 `README.md`，记录来源 commit、归档日期、适用版本和迁移入口；
- `.txt` 归档不得被 import、不得进入任何运行时分支，也不得作为打包资源加入发行包。

这意味着“恢复旧算法”只能通过工程级代码回退或参考归档重新实现，不能由样式配置切换。

### 2.2 position 的九个规范值

`position` 的输入只有照片几何和 margin。它首先选择照片九点中的一个参考点，再根据 margin/placement 得到元素锚点。它不计算元素左上角，也不能因为元素宽度或高度不同而改变元素锚点。

新配置只写以下九个值：

```text
top-left       top-center       top-right
center-left    center           center-right
bottom-left    bottom-center    bottom-right
```

以下旧值不再被运行时接受，仅在迁移文档中提供人工替换关系：

| 旧值 | 迁移目标 |
|---|---|
| `top` / `tc` | `top-center` |
| `bottom` / `bc` | `bottom-center` |
| `left` | `center-left` |
| `right` | `center-right` |
| `tl` | `top-left` |
| `tr` | `top-right` |
| `bl` | `bottom-left` |
| `br` | `bottom-right` |

所有内置样式必须写完整九点值。StyleManager 遇到旧值时直接拒绝加载，错误中显示上表建议；LayoutEngine 仍做防御性异常，不在内部归一化旧别名。

绝对定位节点必须显式提供 `position` 和 `alignment`。缺失字段视为配置错误；默认值只能由“新建样式”模板或 GUI 在生成配置时写入，渲染器不得在读取阶段猜测。

### 2.3 alignment 的九个规范值

`alignment` 的输入只有元素锚点、元素宽度和元素高度。它决定元素布局盒的哪个点与元素锚点重合，由此计算元素左上角。它不能重新选择照片方位点，也不能解释 margin。

例如，同一元素锚点 `(ax, ay)` 下：

```text
alignment: top-left      => 元素左上角 = (ax, ay)
alignment: center        => 元素中心   = (ax, ay)
alignment: bottom-right  => 元素右下角 = (ax, ay)
```

新配置只写以下九个值：

```text
top-left       top-center       top-right
center-left    center           center-right
bottom-left    bottom-center    bottom-right
```

以下旧值不再被运行时接受，仅作为人工迁移提示：

| 旧值 | 可能的迁移目标 |
|---|---|
| `left` | `center-left` |
| `right` | `center-right` |
| `top` | `top-center` |
| `bottom` | `bottom-center` |
| `both-center` | `center` |

其中单轴旧值无法单独决定唯一迁移结果；必须结合元素在旧算法中的实际位置选择完整九点值。例如旧 `left` 可能迁移为 `top-left`、`center-left` 或 `bottom-left`。所有内置样式必须人工完成该判断。

### 2.4 相对定位 cross_alignment

相对定位暂不使用九点 alignment，而是保留“交叉轴对齐”模型：

| relative_position | 合法 cross_alignment | 含义 |
|---|---|---|
| `above` / `below` | `left` / `center` / `right` | 在参考元素宽度内对齐左右边或中心 |
| `left-of` / `right-of` | `top` / `center` / `bottom` | 在参考元素高度内对齐上下边或中心 |

相对节点必须使用独立字段 `cross_alignment`。`alignment` 只属于绝对定位；相对节点继续出现 `alignment` 时直接校验失败，并提示改为 `cross_alignment`。这样 schema 本身即可阻止两类语义再次混用。

相对节点必须显式提供 `relative_to`、`relative_position` 和 `cross_alignment`，并且不得同时出现绝对定位的 `position` / `alignment`。

### 2.5 多行文字行内对齐

新增：

```yaml
line_alignment: left  # left / center / right
```

行为：

- 元素定位只读 `alignment`，多行块内部只读 `line_alignment`；
- 不允许从 `alignment` 推断 `line_alignment`；
- `line_alignment` 缺省为 `left`；
- 单行文字忽略 `line_alignment`。

### 2.6 视觉变化预算

本次采用“除明确缺陷外尽量保持现有画面”的策略：

| 样式 | 决策 |
|---|---|
| InfoCard | 接受预期变化：两列文字改为真正左对齐 |
| FilmClip Frost | 矩形按“完全位于照片内部”解释，改为 `bottom-center` 自对齐；接受矩形向下移动半个矩形高度 |
| SimpleInfo Logo | 改为 `top-center`，保持当前视觉位置，不把旧 `both-center` 字面值强行转成中心跨界 |
| FilmCut Logo | 与 SimpleInfo 相同，保持当前视觉位置 |
| 其余内置样式 | 配置迁移后应保持现有视觉位置 |

如果实现阶段需要改变以上决策，必须先更新本文“视觉变化预算”和样式验收表，不能直接在代码中临时决定。

## 3. 坐标规范

### 3.1 符号

```text
L = original_bounds 左边
T = original_bounds 上边
R = L + original_width
B = T + original_height
CX = (L + R) / 2
CY = (T + B) / 2

ml / mt / mr / mb = 解析为像素后的四方向 margin
ew / eh = 元素布局盒宽高
px / py = position 从照片九点中选出的照片参考点
ax / ay = 照片参考点应用 margin/placement 后得到的元素锚点
dx / dy = alignment 决定的元素布局盒对齐点相对左上角的偏移
x / y = 元素最终左上角
```

### 3.2 position 选择照片九点参考位

position 在本步骤只选择照片上的参考坐标 `(px, py)`：

| position | px | py |
|---|---:|---:|
| `top-left` | `L` | `T` |
| `top-center` | `CX` | `T` |
| `top-right` | `R` | `T` |
| `center-left` | `L` | `CY` |
| `center` | `CX` | `CY` |
| `center-right` | `R` | `CY` |
| `bottom-left` | `L` | `B` |
| `bottom-center` | `CX` | `B` |
| `bottom-right` | `R` | `B` |

这一结果只由 `original_bounds` 和 position 决定，与元素宽高无关。

### 3.3 position 结合 margin 计算元素锚点

为保持现有“顶部/底部条带”和“左右侧条带”的 placement 方向，角点的 outside 只沿所在上/下主轴向外；水平位置仍按照片左右边内侧 margin 定位。

#### 顶部三点

```text
ay = T + mt                    when placement == inside
ay = T - mt                    when placement == outside

top-left:   ax = L + ml
top-center: ax = CX + ml - mr
top-right:  ax = R - mr
```

#### 底部三点

```text
ay = B - mb                    when placement == inside
ay = B + mb                    when placement == outside

bottom-left:   ax = L + ml
bottom-center: ax = CX + ml - mr
bottom-right:  ax = R - mr
```

#### 左右中点

```text
center-left:
    ax = L + ml                when placement == inside
    ax = L - ml                when placement == outside
    ay = CY + mt - mb

center-right:
    ax = R - mr                when placement == inside
    ax = R + mr                when placement == outside
    ay = CY + mt - mb
```

#### 照片中心

```text
center:
    ax = CX + ml - mr
    ay = CY + mt - mb
```

`center` 始终基于原照片，不受非对称 `expand_canvas` 造成的画布中心偏移影响。`placement` 对 center 无意义；若配置 center 时同时设置 placement，仅忽略 placement，不报错。

本步骤输出唯一的元素锚点 `(ax, ay)`。margin 的职责到此结束；后续 alignment 不能再次读取或解释 margin。

### 3.4 alignment 计算元素布局盒相对锚点的位置

alignment 选择元素布局盒上的对齐点。`dx/dy` 是该对齐点相对元素左上角的偏移：

| alignment | dx | dy | 与元素锚点重合的布局盒位置 |
|---|---:|---:|---|
| `top-left` | `0` | `0` | 左上角 |
| `top-center` | `ew // 2` | `0` | 顶边中点 |
| `top-right` | `ew` | `0` | 右上角 |
| `center-left` | `0` | `eh // 2` | 左边中点 |
| `center` | `ew // 2` | `eh // 2` | 中心点 |
| `center-right` | `ew` | `eh // 2` | 右边中点 |
| `bottom-left` | `0` | `eh` | 左下角 |
| `bottom-center` | `ew // 2` | `eh` | 底边中点 |
| `bottom-right` | `ew` | `eh` | 右下角 |

alignment 不选择照片位置，也不移动元素锚点。它只根据元素布局盒尺寸计算 `dx/dy`。

采用整数除法是为了与项目当前像素坐标体系保持一致。奇数尺寸的中心点向左/上取整；几何验证必须固定这一规则，不能在不同函数中混用 `round()` 和 `// 2`。

### 3.5 最终位置

将元素布局盒的 alignment 对齐点放到元素锚点上：

```text
raw_x = ax - dx
raw_y = ay - dy
```

例如 `alignment: bottom-left` 表示：

```text
x = ax
y = ay - eh
```

因此不同宽度的文字只要共享同一个元素锚点，左边缘就一定相同。

以日志中的 `1200×800` InfoCard 相机文字为例：

```text
position: bottom-right
照片参考点 P = (1200, 800)

placement: inside
margin_right = 252 px
margin_bottom = 199 px
元素锚点 A = (1200 - 252, 800 - 199) = (948, 601)

alignment: bottom-left
文字布局盒尺寸 = 104 × 22
alignment 偏移 D = (0, 22)
文字左上角 = A - D = (948, 579)
```

如果同一列的另一段文字宽度变为 185，只要 position 和 `margin_right` 相同，其 x 仍为 948；宽度不会反向参与元素锚点计算。

padding 只作用于 `raw_x/raw_y` 之后：

```text
final_x = clamp(raw_x, pad_left,  pad_right  - ew)
final_y = clamp(raw_y, pad_top,   pad_bottom - eh)
```

当 `defer_padding=True` 时直接返回 raw 坐标；tree_align 在整树完成定位后统一夹持。

## 4. 文件级修改清单

### 4.1 `src/utils/layout_engine.py`

新增模块级常量：

```python
# 绝对定位只接受完整九点枚举，不保留旧别名映射。
ABSOLUTE_POSITIONS = frozenset({...})
ABSOLUTE_ALIGNMENTS = frozenset({...})

# 相对定位按方向使用独立的交叉轴枚举。
HORIZONTAL_CROSS_ALIGNMENTS = frozenset({'left', 'center', 'right'})
VERTICAL_CROSS_ALIGNMENTS = frozenset({'top', 'center', 'bottom'})
```

新增/拆分方法：

| 方法 | 职责 |
|---|---|
| `_validate_position(value)` | 只接受九点规范值；未知值抛出包含字段值的异常 |
| `_validate_alignment(value)` | 只接受九点规范值；未知值抛出包含字段值的异常 |
| `_resolve_photo_reference_point(position)` | 根据 position 从照片九点中选择参考点，不接收元素尺寸 |
| `_resolve_element_anchor(config)` | 在照片参考点上应用 margin/placement，得到元素锚点，不接收元素尺寸 |
| `_resolve_alignment_offset(alignment, ew, eh)` | 只根据 alignment 和元素尺寸计算布局盒对齐点偏移 |
| `_place_element_box(ew, eh, config)` | 将布局盒的 alignment 对齐点放到元素锚点，返回 raw 左上角 |
| `_clamp_box_to_padding(x, y, ew, eh)` | 集中执行 padding 夹持并返回修正量 |
| `_calculate_absolute(...)` | 唯一的绝对定位入口 |
| `_apply_tree_positioning(...)` | 把整树包围盒当作普通盒子定位 |

`calculate_position()` 的分流顺序：

```python
def calculate_position(self, element_width, element_height, config,
                       defer_padding=False):
    # 相对节点必须具有可解析的 relative_to；不得静默退回绝对定位。
    if config.get('relative_to'):
        return self._calculate_relative(
            element_width, element_height, config, defer_padding)

    # 绝对定位只走唯一的新算法。
    return self._calculate_absolute(
        element_width, element_height, config, defer_padding)
```

实施约束：

- 重写前先按 2.1 节归档现有 `layout_engine.py`，然后删除 `_get_anchor()`、`_align_x()`、`_align_y()` 和 `_resolve_tree_ref()` 等旧语义实现；
- 新 helper 不得调用归档代码，也不得保留运行时开关；
- `_resolve_photo_reference_point()` 和 `_resolve_element_anchor()` 的函数签名禁止出现 `element_width` / `element_height`；
- `_resolve_alignment_offset()` 的函数签名禁止出现 original bounds、canvas size、position、placement 或 margin；
- 未知 position/alignment 不再默认 bottom/center；必须由 StyleManager 提前阻止，LayoutEngine 仍做防御性异常；
- 记录 raw 坐标与 clamp delta，但不要在普通 INFO 级别刷屏。

### 4.2 tree_align 改造

唯一算法：

```text
1. 找到无 relative_to 且 tree_align=true 的根；
2. 收集根及全部子孙；
3. 计算当前树包围盒 (tree_left, tree_top, tree_w, tree_h)；
4. 用根配置和 tree_w/tree_h 调用 `_place_element_box()`；
5. shift = target_tree_top_left - current_tree_top_left；
6. 平移根和全部子孙；
7. 计算新包围盒；
8. 对整树执行一次 padding 修正。
```

删除 `_resolve_tree_ref()`，避免树定位继续保留第二套 position/alignment 解释器。

必须验证：

- 同样宽高的普通矩形与 tree 包围盒得到相同目标左上角；
- 根元素在树内部的位置不会被重排，只做整树平移；
- padding 修正保持全部父子相对位置；
- 单成员 tree 也走统一盒定位，或者明确证明跳过后与普通元素完全一致。

### 4.3 相对定位校验

`_calculate_relative()` 的父子组合几何可以沿用，但 schema 与校验一次性修改为：

- 只读取 `cross_alignment`，不得读取 `alignment`；
- `cross_alignment` 未知或与方向轴不匹配时抛出配置错误；
- `relative_to` 缺失、目标不存在或依赖顺序不可解析时失败，不再退回绝对定位；
- 日志记录 `relative_to`、方向、`cross_alignment` 和组合盒平移量。

相对定位 helper 建议命名：

```python
def _validate_cross_alignment(relative_position, cross_alignment):
    # below/above 只允许 left/center/right；
    # left-of/right-of 只允许 top/center/bottom。
    ...
```

### 4.4 `src/core/text_renderer.py`

修改点：

1. 绝对元素继续把完整 config 交给 LayoutEngine；不在 TextRenderer 内自行修正锚点；
2. 多行绘制改为读取专用 `line_alignment`；
3. 未配置时固定使用 `left`，禁止从元素 `alignment` 推断；
4. 定位日志分别输出照片参考点、元素锚点、alignment 偏移、raw box、final box 和 clamp delta；
5. 单行文字布局盒语义仍为 `(x, y, width, height)`，其中 y 表示行盒顶部；
6. 不在本任务中更改字体 metrics 或 Pillow 基线算法。

建议封装：

```python
def _resolve_line_alignment(self, cfg: Dict) -> str:
    # 行内对齐与“布局盒相对元素锚点的 alignment”完全分离，缺省为 left。
    return cfg.get('line_alignment', 'left')
```

### 4.5 `src/frame_styles/style_manager.py`

新增校验函数：

| 函数 | 检查内容 |
|---|---|
| `_validate_absolute_position_config(path, cfg, source)` | position/alignment/placement/margin |
| `_validate_relative_position_config(path, cfg, source)` | relative_to、方向、cross_alignment |
| `_iter_positioned_elements(config)` | 统一遍历 info_position、defined_texts、custom_text、rectangles、logo |

校验范围必须包括：

- `layout.info_position.*`；
- `layout.defined_texts.*`；
- `layout.custom_text`；
- `layout.rectangles.*`；
- 顶层 `logo`。

错误策略：

- 旧别名或未知枚举：ERROR，样式加载失败，并给出迁移建议；
- 相对节点包含旧 `alignment` 字段：ERROR，要求改为 `cross_alignment`；
- 相对轴不匹配：ERROR，样式加载失败；
- 出现 `positioning_semantics`：ERROR，提示该版本开关已删除；
- `tree_align` 放在相对节点：ERROR，禁止加载和保存；
- padding 造成运行期位置修正：只写 DEBUG。

StyleManager 代码内默认配置同步更新：

- 缺省 bottom 外部元素：`position: bottom-center`、`alignment: top-center`；
- 默认 left 外部元素：`position: center-left`、`alignment: center-right`；
- 默认 right 外部元素：`position: center-right`、`alignment: center-left`；
- 新生成的默认样式直接使用唯一新 schema，不写语义版本字段。

### 4.6 `src/gui_pyside/models/style_config_form.py`

文字元素增加：

```python
# 多行文本块内部行对齐，与布局盒相对元素锚点的 alignment 分离。
line_alignment: str = 'left'
```

拆分当前单一 `alignment` 状态：

```python
# 绝对定位时，元素布局盒的九点自对齐。
absolute_alignment: str

# 相对定位时，父元素对应轴上的三值交叉轴对齐。
cross_alignment: str
```

原因：绝对定位使用九点枚举，相对定位使用交叉轴枚举，两者不能继续共享同一个 dataclass 字段。

序列化规则：

- absolute 模式只写 `alignment: absolute_alignment`；
- relative 模式只写 `cross_alignment: cross_alignment`，并移除 `alignment`；
- 文字仅在需要或非默认时写 `line_alignment`；
- 不读写 `positioning_semantics`；如果输入文件含有该字段，加载校验先失败，不能透传到保存结果。

### 4.7 `src/gui_pyside/widgets/element_editor.py`

当前确定存在一个独立保存缺陷：

- UI 有 `abs_alignment` 与 `rel_alignment` 两个 ComboBox；
- `save_element()` / `save_defined_text()` 永远把 `abs_alignment` 写入 `target.alignment`；
- 用户在相对定位区域选择的 alignment 不会保存。

修复方式：

```python
# 根据当前模式只读取当前可见的 alignment 控件，避免隐藏控件覆盖用户选择。
if self._current_mode == 'absolute':
    target.absolute_alignment = self.abs_alignment.currentText()
else:
    target.cross_alignment = self.rel_alignment.currentText()
```

UI 枚举：

- absolute ComboBox：九点 alignment；
- relative ComboBox：根据 relative_position 动态切换合法值；
- below/above 默认 `left`；
- left-of/right-of 默认 `center`；
- 切换 relative_position 时若当前值不合法，重置到 center，并给出简短提示；
- tree_align 只在 absolute 模式显示或启用。

如果新增 `line_alignment` 控件，必须继续使用 `addGroupWidget()` 所属容器内的现有布局，不直接操作 `ExpandGroupSettingCard.viewLayout`。

### 4.8 Logo 与 custom text 编辑器

修改：

- `logo_section.py`：absolute 使用九点 alignment，relative 使用方向相关交叉轴 alignment；
- `custom_text_section.py`：同上，并新增 `line_alignment`；
- 不再让 absolute/relative 两种模式共享同一个 alignment ComboBox；
- 默认 Logo：`top-right + bottom-right`，保持其位于照片上方外侧；
- 默认 custom text：`bottom-center + top-center`，保持其位于照片下方外侧；
- 新建配置直接写唯一新 schema。

### 4.9 文档与模板

同步修改：

- `src/frame_styles/configs/_STYLE_TEMPLATE.txt`
- `docs/STYLE_GUIDE.md`
- `docs/DEVELOPMENT.md`

文档必须明确：

- position 与 alignment 都是九点，但分别属于照片和元素；
- placement 只决定照片边界主轴的内外；
- position 选择照片九点参考位，margin/placement 在该参考位上计算元素锚点；
- padding 可能改变最终盒坐标，但不改变锚点定义；
- 相对定位使用 `cross_alignment` 三值，不是绝对定位的九点 `alignment`；
- 多行内部对齐使用 line_alignment；
- 旧值、旧字段到新 schema 的一次性人工迁移表；
- 旧算法归档只供参考，运行时不会加载。

## 5. 内置样式逐项迁移表

所有 10 份当前样式均直接迁移到唯一新 schema，不增加版本字段。

### 5.1 信息卡片 InfoCard

| 路径 | 当前 | 迁移后 | 视觉结果 |
|---|---|---|---|
| `layout.rectangles.rect_01` | `bottom-right + right` | `bottom-right + bottom-right` | 矩形不变 |
| `layout.info_position.camera` | `bottom-right + left` | `bottom-right + bottom-left` | 左边缘移到列锚点 |
| `layout.info_position.lens` | 同上 | 同上 | 左边缘与 camera 一致 |
| `focal_length_formatted` | 同上 | 同上 | 同列左对齐 |
| `aperture_formatted` | 同上 | 同上 | 同列左对齐 |
| `shutter_speed_formatted` | 同上 | 同上 | 同列左对齐 |
| `iso_formatted` | 同上 | 同上 | 同列左对齐 |
| `defined_text_01` 至 `06` | `bottom-right + left` | `bottom-right + bottom-left` | 标签列左对齐 |

同时更新文件头注释：alignment 表示文字布局盒相对于元素锚点的上下左右关系，不是“文字内部排版对齐”。

### 5.2 测试磨砂矩形 FilmClip Frost

| 路径 | 当前 | 迁移后 | 视觉结果 |
|---|---|---|---|
| `rect_01` | `bottom + both-center` | `bottom-center + bottom-center` | 向下移动半个矩形高度，矩形底边贴到照片底部参考位经 margin 得到的元素锚点 |
| `camera_lens` | `bottom-center + center` | `bottom-center + top-center` | 不变 |
| `defined_text_01` 树根 | `bottom + center` | `bottom-center + top-center` | 整棵树不变 |
| 顶部 custom text | `top + both-center` | `top-center + center` | 不变 |
| 7 个 `right-of + alignment:left` | `alignment: left` | `cross_alignment: center` | 当前等高条件下不变，字段和语义同时修正 |

### 5.3 简洁信息 SimpleInfo

| 元素 | 当前 position/alignment | 迁移后 |
|---|---|---|
| `camera_lens` | `bottom-left + left` | `bottom-left + top-left` |
| `exif` | `bottom-right + right` | `bottom-right + top-right` |
| `timestamp_author` | `top-left + left` | `top-left + bottom-left` |
| `location` | `top-right + right` | `top-right + bottom-right` |
| Logo | `bottom-center + both-center` | `bottom-center + top-center` |

全部保持当前视觉位置。

### 5.4 裁剪胶片 FilmCut

| 元素 | 当前 position/alignment | 迁移后 |
|---|---|---|
| `camera_lens` | `top-left + left` | `top-left + bottom-left` |
| `exif` | `bottom-left + left` | `bottom-left + top-left` |
| `timestamp_author` | `bottom-right + right` | `bottom-right + top-right` |
| `location` | `top-right + right` | `top-right + bottom-right` |
| Logo | `bottom-center + both-center` | `bottom-center + top-center` |

全部保持当前视觉位置。

### 5.5 胶片夹风格 FilmClip/default

| 元素 | 当前 | 迁移后 |
|---|---|---|
| `camera_lens` | `bottom-center + center` | `bottom-center + top-center` |
| `defined_text_01` 树根 | `bottom + center` | `bottom-center + top-center` |
| 顶部 custom text | `top + both-center` | `top-center + center` |
| 7 个 right-of 节点 | `alignment: left` | `cross_alignment: center` |

预期整体视觉不变。

### 5.6 胶片夹风格 FilmClip/no_custom_text

除顶部元素外与 default 相同：

| 元素 | 当前 | 迁移后 |
|---|---|---|
| 顶部 Logo | `top + both-center` | `top-center + center` |

预期整体视觉不变。

### 5.7 宝丽来风格 Polaroid

| 元素 | 当前 | 迁移后 |
|---|---|---|
| `exif` | `bottom-left + left` | `bottom-left + top-left` |
| `camera_lens` | `bottom-right + right` | `bottom-right + top-right` |

两个 below 子元素把现有 `alignment: left/right` 改写为 `cross_alignment: left/right`。预期视觉不变。

### 5.8 底部信息条 Bottom Bars/default

| 元素 | 当前 | 迁移后 |
|---|---|---|
| `camera_lens` | `bottom-left + left` | `bottom-left + top-left` |
| `exif` | `bottom-right + right` | `bottom-right + top-right` |

below 子元素与相对 Logo 将合法值原样迁入 `cross_alignment` 字段。预期视觉不变。

### 5.9 底部信息条 Bottom Bars/no_location

根元素迁移与 default 相同；全部相对节点改用 `cross_alignment`。预期视觉不变。

### 5.10 边框信息条 FrameBar

| 元素 | 当前 | 迁移后 |
|---|---|---|
| `rect_01` | `bottom + top-center` | `bottom-center + top-center` |
| `exif` | `bottom-left + left` | `bottom-left + top-left` |
| `camera_lens` | `bottom-right + right` | `bottom-right + top-right` |

全部相对节点同时把 `alignment` 改名为 `cross_alignment`。预期视觉不变。

## 6. 分阶段执行步骤

### 阶段 0：建立基线与保护工作树

#### 操作

1. 确认处于 `dev` 分支；不在 mainline/release 直接开发；
2. 记录 `git status --short`，区分用户既有改动与本任务改动；
3. 不修改当前 CSV、缩略图、AGENTS.md、release_sync.py 等无关文件；
4. 保存全部 10 个样式的横图基线预览；
5. 对支持竖图的样式保存竖图基线；
6. 保存 InfoCard 当前 debug 坐标，尤其是每列元素的 x、width 和右边缘；
7. 保存 SimpleInfo、FilmCut Logo 当前包围盒；
8. 保存 FilmClip Frost 矩形当前包围盒；
9. 将重写前的 `src/utils/layout_engine.py` 原样复制为
   `docs/legacy/positioning_v1/layout_engine.py.txt`；
10. 创建 `docs/legacy/positioning_v1/README.md`，写明来源 commit、归档日期、
    “仅供参考、禁止 import、禁止打包”和本文迁移文档链接。

#### 退出条件

- 基线图片和关键坐标可供修复后对比；
- 用户既有未提交文件清单已记录；
- 旧算法已有独立、不可执行的文档归档；
- 没有发生 checkout/reset/clean 等破坏性操作。

### 阶段 1：重写唯一的绝对定位几何

#### 操作

1. 删除语义版本分支和旧别名归一化；
2. 删除旧 `_get_anchor()` / `_align_x()` / `_align_y()`；
3. 实现 `_resolve_photo_reference_point()`；
4. 实现 `_resolve_element_anchor()`；
5. 实现 `_resolve_alignment_offset()`；
6. 实现 `_place_element_box()`；
7. 实现集中 padding clamp；
8. 将代码内默认绝对配置同步改为完整九点值；
9. 用临时验证脚本直接调用 helper。

#### 临时几何验证

至少验证：

- 9 position × 9 alignment × 2 placement；
- 元素尺寸 `100×40`、`101×41`；
- 原图 `1200×800`；
- 非对称 canvas expansion；
- 四方向 margin 不相等；
- padding 未触发和触发两种情况。

#### 退出条件

- 照片参考点和元素锚点的结果不随 ew/eh 变化；
- alignment 偏移 helper 不读取照片边界、position 或 margin；
- center 使用 original bounds；
- LayoutEngine 中不存在旧算法调用路径、语义版本开关或旧别名映射；
- 修改的 Python 文件通过 py_compile。

### 阶段 2：接入唯一的单元素绝对定位

#### 操作

1. `calculate_position()` 的绝对分支只调用新 `_calculate_absolute()`；
2. 矩形、Logo、文字仍只调用统一入口；
3. 增加 raw/clamped DEBUG 日志；
4. 创建一个临时规范样式验证九点组合；
5. 创建含旧别名的临时样式，确认其在渲染前被拒绝。

#### 退出条件

- 同一 position/margin 下改变 alignment 会按元素尺寸产生可预测位移；
- `bottom-right + bottom-left` 的不同宽度元素拥有相同左边缘；
- `bottom-right + bottom-right` 的不同宽度元素拥有相同右边缘；
- padding 发生时日志能解释最终坐标变化；
- 旧值不会被静默改写、默认化或落入其他分支。

### 阶段 3：改造 tree_align 与相对定位校验

#### 操作

1. tree_align 改为整树包围盒统一定位；
2. 删除 `_resolve_tree_ref()` 和旧 tree 定位路径；
3. 相对定位只读取 `cross_alignment`；
4. 增加相对方向/`cross_alignment` 合法性校验；
5. 找不到 `relative_to` 时立即报告字段路径和目标名，不再 fallback；
6. 增加组合盒和整树平移日志。

#### 退出条件

- FilmClip 参数链内部间距不变；
- 整树布局盒与同尺寸矩形在相同元素锚点/alignment 下得到一致坐标；
- 相对节点中的旧 `alignment` 字段被拒绝；
- 无效 `right-of + cross_alignment:left` 被拒绝；
- 缺失的 `relative_to` 不会静默退回绝对定位；
- padding 不破坏父子相对坐标。

### 阶段 4：分离多行 line_alignment

#### 操作

1. TextRenderer 新增 `_resolve_line_alignment()`；
2. `layout_multiline_lines()` 只接收行内对齐；
3. 元素 alignment 不再传给行内对齐；
4. 未配置时固定为 left，不从 alignment 推断；
5. 使用宽度不同的三行文字验证 left/center/right。

#### 退出条件

- 改变 line_alignment 只改变块内各行 x，不改变文字布局盒相对元素锚点的位置；
- 改变 alignment 只移动整个文本块，不改变块内各行相对位置；
- 单行文字不受 line_alignment 影响。

### 阶段 5：StyleManager 校验和默认配置

#### 操作

1. 遍历五类定位元素；
2. 增加 absolute/relative 字段和枚举校验；
3. 遇到 `positioning_semantics` 时给出“字段已删除”的迁移错误；
4. 遇到旧 position/alignment 别名时给出候选替换值；
5. 遇到相对节点旧 `alignment` 时提示改用 `cross_alignment`；
6. 更新代码内默认样式；
7. 所有非法组合拒绝加载。

#### 退出条件

- 一份人工构造的新 schema 样式可加载；当前尚未迁移的内置 YAML 按预期被拒绝，并获得可操作的迁移错误；
- 人工构造的旧别名、旧字段和非法组合均得到包含样式源文件、字段路径和迁移建议的错误；
- 没有 `positioning_semantics` 也不会被解释为旧算法；
- 默认样式使用完整九点值和 `cross_alignment`。

### 阶段 6：迁移全部内置样式

#### 操作

1. 按第 5 节逐项修改 10 份 YAML；绝对节点改完整九点，全部相对节点改用 `cross_alignment`；
2. 每修改一个样式立即 YAML 解析；
3. 每个样式渲染横图；
4. 与阶段 0 基线做像素或坐标对比；
5. 只允许视觉变化预算中的差异；
6. InfoCard 验证两列左边缘；
7. Frost 验证矩形底边与 position/margin 计算出的元素锚点重合。

#### 退出条件

- 所有 YAML 成功解析；
- 所有内置样式均不含 `positioning_semantics`；
- 所有 absolute alignment 使用完整九点值；
- 所有相对节点只含 `cross_alignment` 且与方向匹配；
- 非预算样式没有位置回归。

### 阶段 7：更新 PySide6 样式编辑器

#### 操作

1. 模型拆分 absolute `alignment` 与 relative `cross_alignment`；
2. 修复 element_editor 相对 `cross_alignment` 不保存；
3. position 下拉改为规范九点；
4. absolute alignment 下拉改为规范九点；
5. `cross_alignment` 根据方向切换三值；
6. 添加 line_alignment；
7. 新样式直接输出唯一新 schema；
8. 旧样式加载失败时显示可操作的迁移错误，不提供旧模式开关；
9. 验证 YAML 加载→保存→重新加载不丢 rectangles 等透传字段。

#### GUI 操作检查

- 新建绝对元素并切换九个 position；
- 分别保存九个 alignment；
- 新建 below 相对元素，保存 left/center/right；
- 新建 right-of 相对元素，保存 top/center/bottom；
- 确认 `cross_alignment` 不再被隐藏的绝对控件覆盖；
- 展开/收起元素卡片；
- 使用 `layout_debug.dump_expand_card()` 检查新增控件没有破坏高度。

#### 退出条件

- GUI round-trip 后定位字段完全一致；
- `cross_alignment` 保存缺陷修复；
- ExpandGroupSettingCard 收起和展开尺寸正常；
- GUI 预览与 CLI 渲染坐标一致。

### 阶段 8：更新模板与开发文档

#### 操作

1. 更新 `_STYLE_TEMPLATE.txt`；
2. 更新 STYLE_GUIDE；
3. 更新 DEVELOPMENT；
4. 链接本执行方案与审计报告；
5. 清除“复合 position 固定、alignment 不控制”等旧说明；
6. 增加旧值、旧字段到新 schema 的迁移示例；
7. 说明旧算法归档位置和“仅供参考、不可运行”的边界。

#### 退出条件

- 文档示例全部使用唯一新 schema，且不出现语义版本字段；
- position/alignment 表格与代码常量一致；
- 相对定位与多行字段没有复用描述；
- InfoCard 示例能直接说明本次修复的价值。

### 阶段 9：全链路门禁

必须全部通过后才允许提交为完成状态。

#### 语法检查

```powershell
.\venv\Scripts\activate
python -m py_compile `
  D:\Coding\MiLecFrame\src\utils\layout_engine.py `
  D:\Coding\MiLecFrame\src\core\text_renderer.py `
  D:\Coding\MiLecFrame\src\frame_styles\style_manager.py `
  D:\Coding\MiLecFrame\src\gui_pyside\models\style_config_form.py `
  D:\Coding\MiLecFrame\src\gui_pyside\widgets\element_editor.py `
  D:\Coding\MiLecFrame\src\gui_pyside\widgets\style_config_sections\custom_text_section.py `
  D:\Coding\MiLecFrame\src\gui_pyside\widgets\style_config_sections\logo_section.py
```

实际命令应包含本次所有被修改的 `.py` 文件；上表是最低集合。

#### YAML 解析

使用 venv 中的 PyYAML 遍历 `src/frame_styles/configs/**/*.yaml`，确保全部配置可解析，并由 StyleManager 完整加载。

#### CLI 单张

至少选择：

- InfoCard；
- FilmClip Frost；
- FilmClip；
- SimpleInfo；
- Bottom Bars。

验证横图和竖图，检查输出文件可打开。

#### CLI 批量

用包含至少两张不同方向照片的临时输入目录执行批量模式，确认样式变体、输出目录和异常处理正常。

#### GUI

- 启动主窗口；
- 加载并预览上述重点样式；
- 编辑一个 absolute 元素；
- 编辑一个 relative 元素；
- 保存样式、重新加载；
- 验证配置 round-trip；
- 检查卡片布局。

#### 日志

确认 `debug_log.txt`：

- 无新增 ERROR；
- 无 TRACEBACK；
- InfoCard 日志显示同一列拥有统一元素锚点；
- padding 修正有明确 delta；
- 不存在旧算法分支、语义版本或别名归一化日志；
- 非法旧配置在样式加载阶段产生一条包含文件和字段路径的明确错误。

## 7. 坐标级验收矩阵

### 7.1 绝对定位不变量

使用同一元素锚点，元素 A=`100×40`、B=`180×60`：

| alignment | 必须满足 |
|---|---|
| `top-left` | `A.x == B.x` 且 `A.y == B.y` |
| `top-center` | `A.x+A.w//2 == B.x+B.w//2`，顶部相同 |
| `top-right` | 右边缘和顶部相同 |
| `center-left` | 左边缘和垂直中心相同 |
| `center` | 水平、垂直中心均相同 |
| `center-right` | 右边缘和垂直中心相同 |
| `bottom-left` | 左边缘和底边相同 |
| `bottom-center` | 水平中心和底边相同 |
| `bottom-right` | 右边缘和底边相同 |

### 7.2 InfoCard 专项

对值列六项：

```text
x(camera) == x(lens) == x(focal) == x(aperture) == x(shutter) == x(iso)
```

对标签列六项同样成立。

纵向验收：迁移后每项底边应与原版本相同，只有 x 发生预期改变。

### 7.3 tree_align 专项

记录树成员迁移前后的内部差值：

```text
child.x - parent.x
child.y - parent.y
```

整树定位前后，这些内部差值必须保持不变。只允许整树统一增加相同的 shift_x/shift_y。

### 7.4 相对定位专项

- below + left：左右元素左边缘一致；
- below + right：右边缘一致；
- right-of + top：顶边一致；
- right-of + bottom：底边一致；
- 参考元素和当前元素高度不同时，center 仍应按布局盒中心对齐；
- `right-of + cross_alignment:left` 必须校验失败；
- 相对节点使用旧 `alignment` 字段必须在渲染前校验失败。

### 7.5 padding 专项

- raw box 未越界时 clamp delta 为 `(0, 0)`；
- raw box 左越界时只修正 x；
- raw box 上越界时只修正 y；
- tree 越界时全部成员平移相同 delta；
- 矩形 `defer_padding=True` 不被安全区夹持。

## 8. 图像回归判定

### 8.1 应保持不变

迁移后应与基线位置一致：

- Polaroid；
- Bottom Bars 两个变体；
- FrameBar；
- FilmClip 两个变体；
- SimpleInfo（包括 Logo，因为本方案选择 top-center 保持旧画面）；
- FilmCut（同上）。

若存在字体渲染的非确定性，以元素包围盒坐标一致为最终标准；若同一环境下输出可重复，则优先使用像素差为零作为标准。

### 8.2 允许变化

- InfoCard：每个文本横向移动自身宽度，使左边缘贴到 position/margin 计算出的列锚点；纵坐标不变；
- FilmClip Frost：矩形向下移动半个矩形高度，其他元素不变。

任何不在此列表中的视觉变化都视为回归。

## 9. 旧配置拒绝与迁移验证

至少构造以下临时外部样式：

1. 绝对节点使用 `position: top`；
2. 绝对节点使用 `alignment: left`；
3. 相对节点使用旧 `alignment: center`；
4. 相对节点使用轴向错误的 `cross_alignment`；
5. 包含 `positioning_semantics: legacy-v1` 或 `anchor-v2`；
6. 完全符合新 schema 的样式。

验收：

- 1—5 均在渲染前拒绝加载；
- 错误包含样式源文件、元素字段路径、错误值和人工迁移建议；
- 对有歧义的单轴 alignment 不擅自选择九点目标；
- 第 3 项明确提示字段改名为 `cross_alignment`；
- 第 5 项明确提示删除语义版本字段，不启用任何旧路径；
- 第 6 项正常加载并使用九点公式；
- GUI 对 1—5 显示同一校验结果，不自动重写用户文件。

## 10. 日志设计

建议每个绝对元素一条 DEBUG：

```text
[Layout] name=camera position=bottom-right placement=inside
alignment=bottom-left anchor=(948,601) self=(0,22)
raw=(948,579,104,22) final=(948,579,104,22) clamp=(0,0)
```

每棵 tree 一条 DEBUG：

```text
[TreeLayout] root=defined_text_01 members=8
bounds_before=(...) target=(...) shift=(...) clamp=(...)
```

非法旧配置在 StyleManager 中记录一次 ERROR：

```text
[StyleValidation] source=<file> path=<element>.alignment value=left
旧绝对 alignment 已不受支持；请选择 top-left/center-left/bottom-left 之一
```

同一加载失败不要在 StyleManager、LayoutEngine 和 Renderer 重复记录；上层负责呈现一次完整错误。

## 11. 风险与缓解

| 风险 | 后果 | 缓解 |
|---|---|---|
| 一次性替换旧算法 | 外部旧样式无法直接加载 | 启动前严格校验、清晰迁移指南、旧源码离线归档；不做静默猜测 |
| tree_align 只改一半 | 参数链整体错位 | 整树作为普通盒子统一定位 |
| padding 掩盖问题 | 看似 alignment 仍失效 | 同时记录 raw/final/clamp |
| GUI 隐藏控件覆盖 | 保存后配置与界面不一致 | absolute/relative 模型字段拆分 |
| 多行字段继续复用 | 块位置和行内排版联动 | 独立 line_alignment |
| position 别名继续分支 | top 与 top-center 再次分化 | 旧别名直接拒绝，算法只处理九个值 |
| 用户样式被自动猜测迁移 | 无法确认原画面意图 | 不自动改文件；错误给候选值，由用户明确选择 |
| 内置样式迁移遗漏 | 部分样式发布后错位 | 机械审计全部五类定位节点 |
| 字体布局盒与可见字形不同 | 肉眼认为垂直偏移 | 验收以布局盒为准，另行处理字体 metrics |

## 12. 工程回退与数据恢复

### 12.1 不提供配置级回退

- 样式不能通过字段切回旧算法；
- 不保留隐藏环境变量、命令行开关或 fallback；
- `docs/legacy/positioning_v1/` 只用于理解旧输出，不参与程序执行。

### 12.2 代码级回退

若新算法在开发验证中存在系统性问题，应在 `dev` 上通过新的修复提交或针对本任务提交执行可审计的 `git revert`；不得在脏工作树中使用 `git reset --hard`、`git clean` 或批量 checkout 覆盖用户改动。必要时可对照归档源码人工恢复特定公式，但恢复行为必须进入正常代码审查，不能把归档文件直接复制回运行路径形成第二套实现。

### 12.3 数据恢复

本任务不修改 config.json、设备映射 CSV 或用户照片。样式迁移前保存 YAML 基线和渲染基线；已跟踪文件通过对应提交恢复，未跟踪的 InfoCard/Frost 在修改前复制到任务专用备份目录。备份目录不能位于运行时样式扫描路径。

## 13. 建议提交拆分

所有提交仅在 dev：

1. `refactor: split photo anchors from element alignment`
   - 旧源码归档、唯一新 helper、删除语义分流、几何验证；
2. `fix: unify tree and multiline alignment semantics`
   - tree_align、line_alignment、cross_alignment、相对校验、日志；
3. `fix: migrate built-in styles to unified positioning semantics`
   - 10 份 YAML 与 StyleManager 默认配置；
4. `fix: persist relative alignment in style editor`
   - GUI 模型、控件和 round-trip；
5. `docs: document unified positioning semantics`
   - 模板、STYLE_GUIDE、DEVELOPMENT、审计和执行文档。

在全部门禁通过前不执行 `new-version`，不修改版本号，不打 tag。

## 14. 完成定义

仅当以下全部成立，任务才算完成：

- position helper 不接收元素尺寸；
- alignment helper 不读取照片或画布边界；
- 九个 position 和九个 alignment 均有唯一公式；
- 旧 position/alignment 别名在加载阶段被拒绝，不存在运行时归一化；
- 不存在 `positioning_semantics`、旧算法分支或配置级回退；
- 旧算法仅归档为不可执行的 `.txt` 参考文件，且不进入发行包；
- compound position 不再屏蔽 alignment；
- 旧 `both-center` 被拒绝；规范 `center` 在 inside/outside 下使用同一自对齐公式；
- center 使用照片中心；
- tree_align 复用同一盒定位模型；
- line_alignment 与元素 alignment 分离；
- relative `cross_alignment` 与绝对 `alignment` 分离，保存缺陷修复；
- 10 份样式全部完成迁移与预览；
- InfoCard 两列真正左对齐；
- Frost 矩形符合“照片内部底部”定义；
- 除视觉变化预算外没有样式回归；
- 旧用户样式得到明确迁移错误，不被静默猜测或自动改写；
- 所有修改的 Python 文件通过 py_compile；
- CLI 单张、CLI 批量、GUI 预览和配置 round-trip 均通过；
- debug_log.txt 无新增 ERROR / TRACEBACK；
- 任务仍留在 dev，等待按项目合入门禁处理。
