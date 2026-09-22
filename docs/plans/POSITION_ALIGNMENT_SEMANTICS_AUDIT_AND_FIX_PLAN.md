# `position` / `alignment` 语义冲突全面审计与修复方案

> 审计日期：2026-09-22；方案修订日期：2026-09-23  
> 审计范围：布局引擎、文字渲染、矩形、Logo、相对定位、`tree_align`、样式编辑器、样式文档，以及仓库内全部样式 YAML  
> 本文只定义问题与总体方案，不代表算法已经修改  
> 详细执行步骤：[`POSITION_ALIGNMENT_REPAIR_EXECUTION_PLAN.md`](./POSITION_ALIGNMENT_REPAIR_EXECUTION_PLAN.md)

## 1. 结论摘要

当前布局系统没有真正分离 `position` 与 `alignment`：

- `position` 名义上表示照片上的锚点，实际上在多数分支中还直接决定了元素哪条边贴到照片边界；
- `alignment` 只有在 `position: top / bottom / left / right` 等少数分支中局部生效；
- `top-left / top-center / top-right / bottom-left / bottom-center / bottom-right / center` 会提前返回，完全忽略 `alignment`；
- 单行文字没有第二次对齐处理，因此上述忽略会直接反映到最终坐标；
- 多行文字又把同一个 `alignment` 用作“文本块相对锚点的对齐”和“文本块内部各行的对齐”，存在字段复用；
- `tree_align` 用另一套 `position + alignment` 映射重复了旧语义，无法只修改 `_get_anchor()`；
- `both-center` 在 `inside + top/bottom/left/right` 下的补偿方向错误，在部分分支会多偏移一个完整元素宽度或高度；
- `position: center` 使用画布中心而不是原照片中心，不符合“position 相对照片”的定义。

因此，这不是 InfoCard 单一样式配置错误，而是布局引擎从早期版本延续至今的模型级问题。InfoCard 只是第一次使用了 `position: bottom-right` 与 `alignment: left` 这种不相同的组合，从而把问题稳定暴露出来。

最终决策是以一次性破坏性重构建立唯一定位语义：

1. `position + placement + margin_*` 只计算照片锚点；
2. `alignment` 只选择元素自身的对齐点；
3. 最终左上角 = 照片锚点 - 元素自身对齐点偏移；
4. 多行内部对齐改用独立字段 `line_alignment`；
5. `tree_align` 把整棵树的包围盒视作普通元素，复用同一套锚点函数；
6. 相对定位改用独立字段 `cross_alignment`；
7. 不保留 `legacy-v1` / `anchor-v2` 运行时分支、兼容别名或自动迁移；
8. 旧算法只归档为不可执行的 `.txt` 参考文件，全部内置样式一次性迁移。

## 2. 用户期望的语义

### 2.1 `position`

`position` 只回答一个问题：**元素要挂到照片的哪个方位点？**

逻辑上应当只有九个照片方位点：

| 水平 / 垂直 | top | center | bottom |
|---|---|---|---|
| left | `top-left` | `center-left` | `bottom-left` |
| center | `top-center` | `center` | `bottom-center` |
| right | `top-right` | `center-right` | `bottom-right` |

只有表中九个值合法。现有 `top`、`bottom`、`left`、`right` 和缩写不再作为别名读取；StyleManager 应在渲染前拒绝并给出迁移建议。

### 2.2 `alignment`

`alignment` 只回答另一个问题：**元素自身的哪个点要与照片锚点重合？**

为避免单轴值的歧义，`alignment` 只支持完整九点：

| 值 | 元素自身与锚点重合的位置 |
|---|---|
| `top-left` | 左上角 |
| `top-center` | 顶边中点 |
| `top-right` | 右上角 |
| `center-left` | 左边中点 |
| `center` | 中心点 |
| `center-right` | 右边中点 |
| `bottom-left` | 左下角 |
| `bottom-center` | 底边中点 |
| `bottom-right` | 右下角 |

下列旧值只能出现在迁移说明中，不能被运行时接受：

- `left` → `center-left`
- `right` → `center-right`
- `top` → `top-center`
- `bottom` → `bottom-center`
- `both-center` → `center`

其中 `left/right/top/bottom` 不能仅凭字符串无歧义地迁移，因为它们无法表达另一轴。例如旧 `left` 必须结合 position 和旧画面人工选择 `top-left`、`center-left` 或 `bottom-left`。

绝对节点必须显式提供 `position` 和 `alignment`；缺失值由 StyleManager 拒绝。默认值只应由 GUI 或模板在新建配置时写入，渲染器不能在读取阶段补猜测值。

### 2.3 `placement` 与 margin

为了保持现有样式的布局方向，保留当前 `placement` 的“主轴”含义：

- `top-*` / `bottom-*`：`placement` 决定锚点位于照片上边/下边的内部还是外部；
- `left` / `right`：`placement` 决定锚点位于照片左边/右边的内部还是外部；
- 另一轴始终在照片边界范围内按 `margin_left` / `margin_right` / `margin_top` / `margin_bottom` 定位；
- `center` 相对于**原照片中心**，不能使用画布中心；四方向 margin 可作为中心点的平移量，或者在第一版中明确禁止并给出校验警告。

这样可以修正语义，同时避免把 `bottom-left + outside` 突然解释成照片左下角的对角线外侧。

## 3. 当前调用链与问题位置

### 3.1 统一入口

所有下列元素最终都会进入 `LayoutEngine.calculate_position()`：

- `info_position` 文字；
- `defined_texts`；
- `custom_text`；
- `layout.rectangles`；
- 顶层 `logo`。

水印 `Decorator.add_watermark()` 使用独立定位逻辑，不属于本次布局引擎修复范围。

### 3.2 绝对定位提前返回

`LayoutEngine._get_anchor()` 在下列分支直接返回最终左上角：

- `top-left / tl`
- `top-center / tc`
- `top-right / tr`
- `bottom-left / bl`
- `bottom-center / bc`
- `bottom-right / br`
- `center`

这些分支没有读取 `alignment`。例如 `bottom-right` 的横坐标为：

```python
# 当前代码直接减去元素宽度，因此无论 alignment 是什么，元素右边缘都会贴锚点。
x = ox + ow - ew - margin_right
```

这意味着 `bottom-right + left`、`bottom-right + center`、`bottom-right + right` 得到完全相同的坐标。

### 3.3 `top / bottom / left / right` 只在单轴上使用 alignment

- `top / bottom` 只把 `alignment` 传给 `_align_x()`；
- `left / right` 只把 `alignment` 传给 `_align_y()`；
- 这套行为使 `position` 既表示锚点，又隐含元素在法向轴上的贴边方式。

当前 GUI 一共暴露 11 个 position 字符串，而不是九个逻辑锚点。`top` 与 `top-center`、`bottom` 与 `bottom-center` 看似同义，实际却因为是否读取 alignment 而行为不同。

### 3.4 `both-center` 的 inside 修正方向错误

以 `position: bottom`、`placement: inside` 为例：

```text
照片锚点 ay = 照片底边 - margin_bottom
基础 y       = ay - element_height
当前补偿     = 基础 y - element_height / 2
当前结果     = ay - 1.5 × element_height
正确居中结果 = ay - 0.5 × element_height
```

当前结果比正确结果向上多偏移一个完整元素高度。

同类错误包括：

| position | placement | 当前相对正确中心的位置 |
|---|---|---|
| `top` | `inside` | 向下多偏移一个元素高度 |
| `bottom` | `inside` | 向上多偏移一个元素高度 |
| `left` | `inside` | 向右多偏移一个元素宽度 |
| `right` | `inside` | 向左多偏移一个元素宽度 |

对应的 `outside` 分支因为基础坐标在另一侧，当前补偿恰好得到正确中心，造成 inside/outside 行为不对称。

### 3.5 复合 position 完全屏蔽 `both-center`

`top-center / bottom-center / top-left / ...` 在 `both-center` 判断之前已经返回。

例如：

```yaml
position: bottom-center
alignment: both-center
```

当前并不是“元素中心与照片底部中心重合”，而是“元素顶边中点与照片底部中心重合”。这会影响 SimpleInfo 和 FilmCut 的 Logo。

### 3.6 `center` 参考了错误的矩形

当前 `position: center` 使用：

```python
x = (canvas_width - element_width) // 2
y = (canvas_height - element_height) // 2
```

当 `expand_canvas` 非对称时，画布中心不等于原照片中心。按照目标语义，应基于 `original_bounds` 计算照片中心锚点。

仓库内当前没有样式使用 `position: center`，因此这是确定存在但尚未由内置样式触发的缺陷。

### 3.7 单行与多行文字的行为不同

单行文字：

- `TextRenderer` 把元素尺寸和完整配置传给 `calculate_position()`；
- 绘制阶段直接使用布局引擎返回的 `x`；
- 因此 alignment 一旦在布局引擎中被忽略，就没有后续补救。

多行文字：

- 文本块坐标仍由 `calculate_position()` 计算；
- 随后 `layout_multiline_lines()` 又使用同一个 `alignment` 决定各行在块内的左/中/右对齐；
- 一个字段同时承担“块对锚点”和“行对块”两种职责。

应新增 `line_alignment: left | center | right`。未配置时固定为 `left`，不得从旧 `alignment` 推断；元素 alignment 与行内对齐从 schema 到实现都必须彻底分离。

### 3.8 相对定位中的无效 alignment 会静默回退

当前相对定位规则是：

- `below / above`：alignment 控制水平轴，合法语义为 left/center/right；
- `left-of / right-of`：alignment 控制垂直轴，合法语义为 top/center/bottom。

但是 FilmClip 系列大量使用：

```yaml
relative_position: right-of
alignment: left
```

`left` 对垂直轴没有意义，当前 `_align_y()` 只是将未知值静默当作 center。由于这些元素大多字体尺寸相同，目前通常看不出偏差；一旦两侧元素高度不同，结果会与配置文字产生明显冲突。

相对定位保留现有的交叉轴几何模型，但字段改名为 `cross_alignment` 并执行方向相关校验：

| relative_position | 允许的 cross_alignment |
|---|---|
| `below / above` | `left / center / right` |
| `left-of / right-of` | `top / center / bottom` |

相对节点继续出现 `alignment` 时应直接校验失败，提示改为 `cross_alignment`；不保留读取兼容层。

### 3.9 `tree_align` 重复实现旧语义

`apply_tree_positioning()` 当前流程为：

1. 先用 `_calculate_absolute(tree_w, tree_h, root_config)` 得到一个左上角；
2. 再用 `_resolve_tree_ref(position, alignment)` 猜测该左上角对应树包围盒的哪个参考点；
3. 计算二次平移。

这套二次解释与 `_get_anchor()` 强耦合，而且已经出现不一致：`_resolve_tree_ref()` 将任意 `both-center` 解释为中心，但 `_get_anchor()` 对复合 position 会忽略它。

修复后应删除这种“先算左上角、再反推参考点”的流程。整棵树的视觉包围盒就是一个普通矩形，直接调用与单元素相同的 `_place_box_on_anchor()` 即可。

### 3.10 padding 可能掩盖正确的 alignment

绝对定位完成后，当前代码会把坐标夹持到 padding：

```python
# 即使原始锚点计算正确，只要元素越过安全区，最终坐标也会被重新夹回边界。
x = max(pad_left, min(raw_x, pad_right - element_width))
y = max(pad_top, min(raw_y, pad_bottom - element_height))
```

因此，某些靠近边界的不同 alignment 仍可能得到相同最终坐标。这不是锚点算法错误，但会让用户误以为 alignment 再次失效。

建议日志同时输出：

- `anchor=(ax, ay)`；
- `raw_box=(x, y, w, h)`；
- `clamped_box=(x, y, w, h)`；
- 是否发生 padding 修正及修正量。

## 4. InfoCard 的直接证据

InfoCard 的值列六项和标签列六项均配置为：

```yaml
placement: inside
position: bottom-right
alignment: left
```

运行日志示例：

```text
camera: x=844, width=104  -> 右边缘=948
lens:   x=763, width=185  -> 右边缘=948
```

两项右边缘完全相同，证明 `alignment: left` 没有生效；元素宽度越大，左边缘越向左移动。

在唯一的新语义中，这些文本应使用完整自对齐点：

```yaml
# bottom-right 计算照片内的行锚点；bottom-left 让文字左下角贴到该锚点。
position: bottom-right
alignment: bottom-left
```

这样相同列中的所有元素拥有相同 x，且现有纵向位置保持不变。与当前渲染相比，每个元素将向右移动自身宽度，这是预期修正。

InfoCard 的矩形应从 `alignment: right` 改为 `alignment: bottom-right`，从而在新语义下保持当前位置不变。

## 5. 全部样式配置审计

审计开始时，`src/frame_styles/configs` 下共有 10 份 YAML：

- 已纳入 Git：8 份；
- 审计开始时未跟踪：InfoCard、FilmClip Frost 共 2 份；
- 工作区 `styles/` 中没有额外用户 YAML。

审计过程中工作树曾被外部操作更新，InfoCard 与 FilmClip Frost 一度消失；截至 2026-09-23，两份配置已重新出现在工作区，10 份 YAML 均已再次核对。两份目录当前仍未纳入 Git，实施时必须先保护其内容，不能依赖 Git 恢复。

审计开始时的 10 份配置共包含 72 个带定位信息的节点：42 个绝对定位、30 个相对定位。其中：

- 34 个绝对定位节点使用会提前返回并忽略 alignment 的复合 position；
- 21 个水平相对定位节点使用了与垂直交叉轴不匹配的 `alignment: left`；
- 2 个 `bottom-center + both-center` 明确被复合 position 屏蔽；
- 另有 1 个 `inside + bottom + both-center` 进入错误方向的中心补偿。

### 5.1 风险分类

| 级别 | 含义 |
|---|---|
| A | 当前已经产生明确错误画面，算法修复后应有意改变渲染 |
| B | 当前配置表达与实际行为不一致；修复后是否改变画面需要确认设计意图 |
| C | 当前画面通常正确，但依赖旧的隐式行为；必须迁移配置以避免算法修复后改变画面 |
| D | 相对定位值在当前轴上无意义，现阶段因尺寸相同或默认回退而不明显 |

### 5.2 逐文件结论

| 样式配置 | 级别 | 发现 | 推荐迁移 | 最终是否应改变画面 |
|---|---:|---|---|---|
| 信息卡片 InfoCard / `default.yaml` | A/C | 12 个文本元素均为 `bottom-right + left`，实际全部右对齐；矩形为 `bottom-right + right` | 12 个文本改 `bottom-left`；矩形改 `bottom-right` | **是**。文本横向改为真正左对齐；矩形不变 |
| 测试磨砂矩形 FilmClip Frost / `default.yaml` | B/C/D | `rect_01` 为 `inside + bottom + both-center`，触发 inside 补偿方向错误；1 个绝对文本与 1 棵树依赖旧默认；7 个 `right-of + left` 静默回退 center | 见下文专项说明；相对项改用 `cross_alignment` | **是或否取决于矩形意图**；其余可保持不变 |
| 简洁信息 SimpleInfo / `default.yaml` | B/C | 四角文字依赖 position 隐含纵向自对齐；Logo 的 `bottom-center + both-center` 当前忽略 both-center | 四角文字改完整 alignment；Logo 需在 `center` 与 `top-center` 中确认 | Logo 可能改变；文字可保持不变 |
| 裁剪胶片 FilmCut / `default.yaml` | B/C | 与 SimpleInfo 相同 | 与 SimpleInfo 相同 | Logo 可能改变；文字可保持不变 |
| 胶片夹风格 FilmClip / `default.yaml` | C/D | `camera_lens: bottom-center + center` 与树根 `bottom + center` 实际均为顶边贴锚点；7 个 `right-of + left` 实际居中 | 两个绝对根改 `top-center`；7 个相对项改为 `cross_alignment: center`；顶部自定义文字的 `both-center` 改为 `center` | 可保持不变 |
| 胶片夹风格 FilmClip / `no_custom_text.yaml` | C/D | 与 default 相同；顶部 Logo 使用 `top + both-center`，当前恰好真正居中 | 根元素迁移同上；相对项改用 `cross_alignment: center`；Logo 改为 `center` | 可保持不变 |
| 宝丽来风格 Polaroid / `default.yaml` | C | 底部左右两个绝对根依赖 position 隐含“outside 时顶边贴锚点” | `bottom-left + top-left`、`bottom-right + top-right` | 可保持不变 |
| 底部信息条 Bottom Bars / `default.yaml` | C | 两个绝对根同上；相对 Logo 的 center 有效 | 根改 `top-left` / `top-right`；相对项保持 | 可保持不变 |
| 底部信息条 Bottom Bars / `no_location.yaml` | C | 与 default 相同 | 同上 | 可保持不变 |
| 边框信息条 FrameBar / `default.yaml` | C | 两个绝对文字根依赖旧行为；矩形 `bottom + top-center` 已经表达完整 | 文字根改 `top-left` / `top-right`；矩形不变 | 可保持不变 |

### 5.3 InfoCard 迁移明细

需要有意修正的 12 个元素：

- `layout.info_position.camera`
- `layout.info_position.lens`
- `layout.info_position.focal_length_formatted`
- `layout.info_position.aperture_formatted`
- `layout.info_position.shutter_speed_formatted`
- `layout.info_position.iso_formatted`
- `layout.defined_texts.defined_text_01` 至 `defined_text_06`

全部从：

```yaml
alignment: left
```

迁移为：

```yaml
alignment: bottom-left
```

`layout.rectangles.rect_01` 从 `right` 迁移为 `bottom-right`，用于保持矩形右下角位置不变。

### 5.4 FilmClip Frost 矩形的设计选择

该矩形配置为：

```yaml
placement: inside
position: bottom
alignment: both-center
```

配置注释称其为“照片内部底部一条磨砂玻璃色块”。这里有两个可能意图：

1. **严格服从 both-center**：矩形中心与照片内底部锚点重合。修复后矩形相对当前向下移动一个完整矩形高度；由于 margin 小于半高，矩形会有一部分越过照片底边。
2. **保证矩形完全位于照片内部**：应迁移为 `alignment: bottom-center`。修复后矩形相对当前向下移动半个矩形高度，矩形底边贴到锚点。

根据现有注释，推荐第 2 种，即使用 `bottom-center`。该样式本身标注为临时测试样式，因此应在算法实现阶段通过实际预览确认。

其余 FilmClip Frost 配置按 FilmClip 迁移：

- `camera_lens`：`center` → `top-center`；
- `defined_text_01` 树根：`center` → `top-center`；
- 7 个 `right-of + left`：改为 `cross_alignment: center`，删除相对节点的 `alignment`；
- 顶部 custom text：`both-center` 规范化为 `center`，画面不变。

### 5.5 SimpleInfo / FilmCut Logo 的设计选择

两者 Logo 均为：

```yaml
placement: outside
position: bottom-center
alignment: both-center
```

当前 `bottom-center` 提前返回，Logo 实际完全位于底部锚点下方，等价于 `alignment: top-center`。

修复时有两个选择：

1. **保持当前画面**：迁移为 `alignment: top-center`；
2. **尊重现有 both-center 字面意图**：迁移为 `alignment: center`，Logo 向上移动半个 Logo 高度，中心落在锚点上。

本执行方案最终选择第 1 种：迁移为 `top-center`，保持当前发布画面。第 2 种只能在未来有明确视觉需求并单独评审时采用，不能借本次语义修复静默改变。

### 5.6 其余样式的无损迁移规则

为了让新算法修复后仍保持当前画面：

| 当前组合 | placement | 当前实际自对齐点 | 新配置 |
|---|---|---|---|
| `top-left + left` | outside | 元素左下角 | `bottom-left` |
| `top-right + right` | outside | 元素右下角 | `bottom-right` |
| `bottom-left + left` | outside | 元素左上角 | `top-left` |
| `bottom-right + right` | outside | 元素右上角 | `top-right` |
| `bottom-center + center` | outside | 元素顶边中点 | `top-center` |
| `bottom + center` | outside | 元素顶边中点 | `top-center` |
| `top + both-center` | outside | 元素中心 | `center` |
| `bottom + top-center` | outside | 元素顶边中点 | `top-center` |

如果未来出现 inside 配置，应按实际几何迁移，不能机械套用上表的 outside 规则。

## 6. 推荐的新算法

### 6.1 数据结构

建议引入两个小型内部结果对象；它们可以使用 tuple，也可以使用带注释的 dataclass：

```python
# PhotoAnchor 只描述照片参考点，不包含任何元素尺寸信息。
PhotoAnchor = Tuple[float, float]

# SelfAnchorOffset 描述元素自身对齐点相对左上角的偏移。
SelfAnchorOffset = Tuple[float, float]
```

核心不变量：**照片锚点计算函数不得接收 `element_width` 或 `element_height`。** 这样可以从接口层阻止 position 再次吸收 alignment 的职责。

### 6.2 绝对定位流程

```python
def _calculate_absolute(element_width, element_height, config, defer_padding=False):
    # 第一步只根据照片边界、position、placement 和 margin 计算照片锚点。
    anchor_x, anchor_y = _resolve_photo_anchor(config)

    # 第二步只根据 alignment 和元素尺寸计算元素自身锚点偏移。
    self_x, self_y = _resolve_self_anchor_offset(
        config['alignment'],
        element_width,
        element_height,
    )

    # 元素自身锚点与照片锚点重合，得到元素左上角。
    raw_x = anchor_x - self_x
    raw_y = anchor_y - self_y

    # padding 是最终安全约束，不参与锚点语义。
    if defer_padding:
        return round(raw_x), round(raw_y)
    return _clamp_to_padding(raw_x, raw_y, element_width, element_height)
```

### 6.3 元素自身锚点偏移

```python
def _resolve_self_anchor_offset(alignment, width, height):
    # alignment 必须已经通过完整九点枚举校验；不做旧值归一化。
    horizontal_name, vertical_name = _split_canonical_alignment(alignment)

    horizontal = {
        'left': 0,
        'center': width / 2,
        'right': width,
    }
    vertical = {
        'top': 0,
        'center': height / 2,
        'bottom': height,
    }
    return horizontal[horizontal_name], vertical[vertical_name]
```

坐标取整必须集中在最终一步，避免多次 `// 2` 在奇数尺寸下积累 1 px 偏差。

### 6.4 tree_align

树定位应简化为：

1. 计算树当前视觉包围盒；
2. 使用根配置计算照片锚点；
3. 根据根 alignment 计算树包围盒自身锚点；
4. 将整树平移到目标；
5. 对整树执行一次 padding 修正。

这样可以删除 `_resolve_tree_ref()`，消除与绝对定位的第二套映射表。

### 6.5 相对定位

相对定位的父子组合几何可以保留，但 schema 和失败策略必须同步重构：

- 相对节点只读取 `cross_alignment`；
- 相对节点必须显式提供 `relative_to`、`relative_position` 和 `cross_alignment`，且不能混入绝对 `position` / `alignment`；
- 对 `relative_position` 与 `cross_alignment` 的合法组合进行校验；
- 将 FilmClip 系列的无效 `right-of + alignment:left` 显式迁移为 `right-of + cross_alignment:center`；
- 目标不存在、字段缺失或轴向错误时立即失败，不再静默 fallback；
- 保持组合盒 padding 与级联平移行为不变。

后续如需把相对定位也拆成“目标元素锚点 + 当前元素锚点”，应作为独立重构；本次先固定交叉轴字段边界和严格校验。

## 7. 破坏性迁移与旧算法归档

项目支持 exe 同目录下的用户自建 `styles/`，因此一次性重构会使旧外部样式无法直接加载。这是本方案明确接受的破坏性变化：宁可给出可操作的迁移错误，也不在运行时维持两套含义。

### 7.1 单一运行时语义

- 不增加 `positioning_semantics`；
- 不保留 `legacy-v1`、`anchor-v2` 或任何同类版本开关；
- 不接受旧 position/alignment 别名；
- 不从旧字段自动推断新字段；
- StyleManager 在渲染前完成严格校验，并指出源文件、元素路径、错误值和候选迁移方式。

### 7.2 为什么不自动猜测

`alignment: left` 在旧配置中可能表示：

- 顶边在照片外时的左下角；
- 底边在照片外时的左上角；
- 仅水平左对齐，纵轴依赖 position；
- 相对定位 right-of 中实际被当作垂直居中。

仅凭字符串无法无歧义迁移。内置样式按本文审计结果人工迁移；外部样式由用户根据旧画面选择明确九点值。程序可以提供候选值和迁移文档，但不得静默改写文件。

### 7.3 旧算法归档

在修改 `src/utils/layout_engine.py` 前，将原文件逐字复制到：

```text
docs/legacy/positioning_v1/layout_engine.py.txt
```

同目录 `README.md` 记录来源 commit、归档日期、适用版本、已知缺陷以及本迁移方案链接。归档文件必须使用 `.txt`，不得 import、不得进入运行时 fallback、不得加入 PyInstaller 数据资源。

### 7.4 样式编辑器

当前 PySide6 编辑器应同步修改：

- position 下拉只显示九个逻辑锚点；
- alignment 下拉显示完整九点；
- 相对定位使用独立 `cross_alignment` 控件和字段；
- 多行文字增加 `line_alignment`；
- 新建样式直接写唯一新 schema；
- 加载旧样式时显示严格校验错误和迁移入口，不提供“保持旧语义”选项；
- GUI 不自动保存或覆盖加载失败的旧文件。

`gui_legacy` 已封存，不新增交互功能；若其中仍有可能被导入的定位常量或导出逻辑，应删除运行时引用或明确隔离，避免旧值重新进入新配置。

## 8. 配置校验与诊断日志

StyleManager 当前只验证 `name`、`layout` 及少量容器类型，没有校验 position/alignment 组合。建议新增：

- position 是否属于唯一九点规范集合；
- 绝对 alignment 是否属于唯一九点规范集合；
- 旧别名与 `positioning_semantics` 字段直接报迁移错误；
- 相对节点是否只使用 `cross_alignment`；
- relative_position 与 cross_alignment 是否轴向匹配；
- `position: center` 使用 margin 时给出明确规则；
- `tree_align` 只能出现在绝对定位根节点；
- 未知字段给 warning，不应默默按 center 或 bottom 处理；
- padding 导致锚点结果被修正时输出 debug 日志。

建议的定位日志格式：

```text
[Layout] name=camera position=bottom-right placement=inside
alignment=bottom-left
photo_anchor=(948, 601) self_anchor=(0, 22)
raw_box=(948, 579, 104, 22) clamp_delta=(0, 0)
```

## 9. 实施文件清单

### 9.1 核心代码

- `src/utils/layout_engine.py`
  - 旧源码先归档为 `docs/legacy/positioning_v1/layout_engine.py.txt`；
  - 删除旧别名、旧算法和语义版本分流；
  - 分离照片锚点与元素自身锚点；
  - 只保留唯一 `_calculate_absolute()`；
  - tree_align 改为复用同一盒定位；
  - 相对定位只读 `cross_alignment`；
  - 保持相对定位组合盒与 padding 行为。
- `src/core/text_renderer.py`
  - `alignment` 只用于文本块定位；
  - 多行块内部改读 `line_alignment`；
  - 增强 raw/clamped 调试日志。
- `src/frame_styles/style_manager.py`
  - 严格拒绝旧别名、旧字段和 `positioning_semantics`；
  - 增加新 schema 合法值与组合校验；
  - 修正默认样式配置。

### 9.2 GUI 与模型

- `src/gui_pyside/models/style_config_form.py`
  - position 规范值；
  - alignment 完整九点；
  - 相对定位 `cross_alignment` 字段；
  - 多行 `line_alignment` 字段；
  - 更新默认值。
- `src/gui_pyside/widgets/element_editor.py`
- `src/gui_pyside/widgets/style_config_sections/custom_text_section.py`
- `src/gui_pyside/widgets/style_config_sections/logo_section.py`
  - 更新选项、提示和迁移警告。

### 9.3 配置与文档

- 全部内置 YAML 一次性迁移，不写语义版本字段；
- 全部相对节点把旧 `alignment` 改为 `cross_alignment`；
- 增加 `docs/legacy/positioning_v1/README.md` 与不可执行的旧源码归档；
- `src/frame_styles/configs/_STYLE_TEMPLATE.txt` 更新九点语义；
- `docs/STYLE_GUIDE.md` 删除“复合 position 固定、alignment 不控制”的旧规则；
- `docs/DEVELOPMENT.md` 更新算法、tree_align 与调试日志；
- InfoCard 注释中“alignment 只负责文字内部排版对齐”应改为“alignment 决定文字布局盒自身哪个点贴到照片锚点”。

### 9.4 StyleManager 内置默认值

代码内还有两组非 YAML 默认配置，也必须迁移：

- 缺少 `info_position` 时注入的 `bottom + center` 默认值；
- `create_default_style()` 中的 bottom、left、right 三个元素。

按保持当前画面的原则，outside 默认值应分别使用：

- bottom → `top-center`
- left → `center-right`
- right → `center-left`

## 10. 验证方案

项目没有自动化测试框架，因此实现阶段应使用临时验证脚本、实际 CLI 渲染和 GUI 预览完成门禁。

### 10.1 几何矩阵

至少覆盖：

- 9 个 position；
- 9 个 alignment；
- inside / outside；
- 横图、竖图；
- 对称与非对称 expand_canvas；
- 奇数与偶数元素宽高；
- 零 margin 与四方向非零 margin；
- padding 未触发、单轴触发、双轴触发。

关键不变量：

1. 修改元素宽高不能改变照片锚点；
2. 修改 alignment 不能改变照片锚点；
3. `*-left` 对齐时，不同宽度元素的左边缘相同；
4. `*-right` 对齐时，不同宽度元素的右边缘相同；
5. `top-*` / `bottom-*` 对高度满足同类不变量；
6. `center` 必须使用原照片中心，而不是画布中心；
7. tree 包围盒与同尺寸普通矩形得到相同目标坐标；
8. padding 只能改变最终盒坐标，不能回写或改变锚点定义。

### 10.2 回归样式

每个样式至少渲染：

- 3:2 横图；
- 2:3 竖图；
- 短/长相机与镜头名称；
- 有/无 location；
- 有/无自定义文本；
- Logo 开启样式。

重点对比：

- InfoCard：同一列所有文字左边缘一致；
- FilmClip Frost：矩形是否符合“完全在照片内部”的设计；
- SimpleInfo / FilmCut：Logo 选择保持旧画面还是尊重 both-center；
- FilmClip 三份配置：树级参数行整体位置不变；
- Polaroid、Bottom Bars、FrameBar：迁移前后像素位置不变。

### 10.3 执行门禁

实现完成后必须执行：

1. `python -m py_compile` 校验所有修改的 `.py` 文件；
2. 单张 CLI 渲染；
3. 批量 CLI 渲染；
4. GUI 样式编辑器加载、保存、重新加载；
5. GUI 预览上述重点样式；
6. 检查 `debug_log.txt` 无新增 ERROR / TRACEBACK；
7. 对比 raw anchor、raw box、clamped box 日志。

## 11. 推荐实施顺序

1. 保存渲染基线，并把旧 `layout_engine.py` 归档为不可执行 `.txt`；
2. 实现纯几何 helper 与临时坐标矩阵验证；
3. 删除旧绝对定位、别名归一化和 tree 二次解释，只接入唯一新算法；
4. 相对定位字段改为 `cross_alignment`，缺失目标或轴向错误立即失败；
5. 分离 `line_alignment`；
6. 增加严格配置校验和日志；
7. 一次性迁移全部当前内置 YAML 与代码内默认配置；
8. 按审计快照重点迁移并预览 InfoCard 与 FilmClip Frost；
9. 更新 PySide6 样式编辑器、模板与迁移文档；
10. 验证旧配置拒绝路径，再完成横图/竖图、单张/批量、GUI 回归。

## 12. 验收标准

满足以下条件才视为修复完成：

- `position` 的照片锚点计算完全不依赖元素宽高；
- `alignment` 的元素自身锚点计算完全不依赖照片边界；
- InfoCard 使用同一锚点和 `bottom-left` 后，长短文本左边缘严格一致；
- 九个 position 与九个 alignment 的组合均有确定、可解释的坐标；
- compound position 不再忽略 alignment；
- 旧 `both-center` 被拒绝；规范 `center` 在 inside/outside 下行为对称且公式正确；
- `position: center` 使用原照片中心；
- tree_align 与普通元素共用同一几何函数；
- 多行内部对齐不再复用元素 alignment；
- 相对定位只使用 `cross_alignment`，不再复用绝对 `alignment`；
- 运行时不存在旧算法分支、语义版本开关或旧别名归一化；
- 旧算法仅作为不可执行参考文件归档，且不进入发行包；
- 旧用户样式会得到包含文件、字段路径与迁移建议的明确错误，不会被自动猜测或覆盖；
- 除明确批准的 InfoCard、FilmClip Frost、SimpleInfo/FilmCut Logo 变化外，内置样式迁移前后视觉位置不变。
