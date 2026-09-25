# 文字盒计算算法补充审计

日期：2026-09-23。本文保留补充审计时的记录，当时审计对象包含“固定西文参考行盒”的试验实现。

**状态更新：该实现未经用户授权，现已全部撤销，生产代码恢复至原始版本。** 与基线、文字盒及小字号直接相关的结论已合并并校正于[问题诊断与证据](FONT_BASELINE_DIAGNOSIS.md)第 5.6～5.10 节；实施步骤以[独立执行方案](FONT_BASELINE_EXECUTION_PLAN.md)为准。下文第 3 节的纯中文数据属于试验模型，不能直接作为恢复后原算法的纯中文数据。

## 1. 总结

试验当时消除了语言切换的纵向跳动，但文字几何仍只有一个 `(x, y, width, height)`，同时承担排版推进、九点对齐、padding、相对定位和所谓“视觉边界”。这些概念本来不是同一个盒，因此当时记录了以下缺陷；撤销后基线跳动仍存在。

| 优先级 | 缺陷 | 当前内置样式是否可触发 | 主要影响 |
|---|---|---|---|
| P1 | 逻辑行盒不包含实际墨迹 | 是 | padding、树边界和 top alignment 不能保证文字不越界 |
| P1 | 横向把 bbox 宽度当 advance | 是；斜体更明显 | 混排段间距、居中/右对齐、相对定位宽度不准确 |
| P1 | 超长文字大于安全区时仍静默放置 | 是 | 右侧/底部越界或被画布裁切 |
| P1 | relative_to 使用后缀模糊匹配 | 内置配置未触发 | 拼写错误可能静默引用错误元素 |
| P2 | 样式校验不检查依赖存在、环和跨来源重名 | 内置配置未触发 | 运行时异常、重复绘制或配置被覆盖 |
| P2 | 中西文分类范围不完整 | 特殊字符可触发 | 韩文、扩展汉字、变体选择符走错字体与度量 |
| P2 | 小字号存在多层整数化 | 是 | 1px 误差在小字号中占比更大，缩放呈台阶状 |
| P3 | custom_text 主动删除换行 | 是 | CLI 声称支持多行，但不会进入多行盒算法 |

本次只补充诊断、证据和改造建议，没有继续修改生产代码。

## 2. 审计方法与范围

- 实测 Gotham Light/Book/Medium 与 GlowSansSC-Normal Light/Regular/Medium。
- 字号覆盖 12、27、54、81、100px。
- 比较 `getbbox()`、`getlength()`、逐段实际绘制墨迹和注册逻辑盒。
- 检查 FilmClip 示例、斜体放大样本、padding 超大盒、元素引用解析、全部内置 YAML 的引用图。
- 结构化结果见 [text_box_audit.json](diagnostics/font_baseline/text_box_audit.json)，复现代码见 [audit_text_box.py](diagnostics/font_baseline/audit_text_box.py)。

审计中的“墨迹盒”是实际非零像素范围；“advance”是下一段排版原点应前进的距离；“逻辑盒”是当前注册进 LayoutEngine 的矩形。

## 3. P1：逻辑行盒不包含实际墨迹

已撤销试验的固定参考行为（非当前生产代码）：

```text
H = A_latin + D_latin
baseline = y + A_latin - D_latin
```

这个公式保留了修复前纯西文位置，但它并不是标准字体度量盒。若逻辑盒顶部为 `y`，同一字体度量盒的基线通常应在 `y + A`，而不是 `y + A - D`。当前基线相对盒顶被上移了一个 descent，造成墨迹可能越过逻辑盒顶部。

FilmClip 54px Medium 实测：

| 文本 | 逻辑盒 y 范围 | 基线 | 实际墨迹 y 范围 | 顶部越界 |
|---|---|---:|---|---:|
| AaBbCc | [0,65] | 39 | [-2,40) | 2px |
| gypq | [0,65] | 39 | [9,48) | 0px |
| 永和九年 | [0,65] | 39 | [-7,43) | 7px |
| ，。 | [0,65] | 39 | [25,46) | 0px |

100px 时 `永和九年` 顶部越界达到 13px。三组测试字重、五个字号中，共 60 组垂直样本有 30 组越过逻辑盒顶部。

直接后果：

1. 元素被夹到 `padding_top` 时，实际中文仍可能进入 padding 外侧。
2. `LayoutEngine._compute_visual_bounds()` 合并的是注册逻辑盒，并不读取实际墨迹；函数名和 tree_align 文档中的“视觉包围盒”不准确。
3. 相对布局不会发生盒重叠，但可见文字仍可能重叠。
4. 不能通过继续增大或缩小某个动态文本盒解决，否则会重新引入“加入中文后位置变化”。

推荐保持“基线不随内容变化”的目标，同时拆出两套垂直范围：

- `layout_box`：保持稳定、参与九点 alignment，不随本次文字语言改变。
- `safety_bounds`：相对于稳定基线，根据配置中的西文和 CJK 字体共同计算固定最大 ascent/descent；即使本次只有西文，也使用同一安全范围。
- `ink_bounds`：按实际 runs 合并，只用于调试、碰撞诊断和精确裁切信息，不直接反推元素位置。

这样 padding 和 tree 可以使用内容无关的 `safety_bounds`，仍不会因为用户加入中文而移动。如果必须逐像素保持旧版纯西文位置，可以保留当前 baseline 作为兼容锚点，只把固定 safety 上下外延纳入边界与夹持。

## 4. P1：横向测量把 bbox 宽度误作 advance

代码对纯文本和混排段均使用：

```text
width = bbox.right - bbox.left
next_x = current_x + width
```

字体排版应使用 `font.getlength(text)` 作为下一段原点。bbox 用于墨迹外接范围，两者受左 bearing、右侧 overhang 和 kerning 影响，不可互换。

当前常规字体的误差较小但真实存在：审计的 300 个 run 样本中有 58 个存在非零 bearing 或 bbox/advance 差。Gotham Medium 54px 的 `j`：

```text
bbox x = [-1, 15]
当前 width = 16
advance = 15
```

`j永` 因此把中文原点放在 16px，而正确推进应为 15px；注册宽 70px，advance 总和 69px，实际墨迹还向注册盒左侧越过 1px。

算法允许用户选择任意字体文件/weight，斜体会放大问题。Gotham-MediumItalic 100px：

| 文本 | bbox x | 当前 width | advance | 差值 |
|---|---|---:|---:|---:|
| A | [-6,76] | 82 | 76 | 6px |
| j | [-13,34] | 47 | 29 | 18px |
| f | [0,49] | 49 | 40 | 9px |
| AV | [-6,158] | 164 | 147.875 | 16.125px |

推荐每个 run 同时记录：

```text
origin_x       排版原点
advance        getlength()，用于推进下一 run
ink_bbox       getbbox(anchor='ls')，相对基线原点
```

元素的 `advance_width` 用于普通行内排列；所有 run 的 `origin + ink_bbox` 合并成 `ink_bounds`。计算期间保留 1/64px 精度，只在最终需要离散像素时统一取整，避免每段独立取整累积误差。

## 5. P1：超长文字没有明确溢出策略

`_clamp_box_to_padding()` 假设元素能放进安全区。当元素宽高超过可用范围时，公式只能将左上角贴到 padding 左上角，无法同时满足右/下边界，也不会告警。

100×100 画布、四边 10px padding、100×100 元素的实测结果是 `(10,10,100,100)`，右侧和底部各越过安全区 20px。长作者名、地点或 custom_text 可以触发同一问题；custom_text 又被强制为单行，因此风险更高。

需要显式定义并校验 overflow 策略，例如：

- `allow`：允许越界，但记录 WARNING；
- `ellipsis`：按 advance 截断并加省略号；
- `shrink`：二分字号直到放入最小字号限制；
- `wrap`：按最大宽度换行；
- `error`：拒绝该次渲染并指出元素名和超出像素。

在没有产品级配置前，最低限度应检测 `element_width > available_width` 或 `element_height > available_height`，日志不能继续宣称已经完成安全区夹持。tree_align 的整树夹持也需要同样的 oversized 分支。

## 6. P1/P2：元素引用解析和依赖校验不严谨

`get_element_bounds()` 在精确 key 不存在时使用：

```text
key.endswith(name) or name.endswith(key)
```

实测注册表只有 `custom_text` 时，请求不存在的 `text` 会得到 `custom_text` 的盒。这会将配置拼写错误变成静默错误引用，布局结果看似成功但位置不可信。相对定位中寻找待平移根节点还有一份相同后缀逻辑。

应该只允许精确、唯一的元素 ID。若确实需要历史别名，应在样式加载阶段做显式别名表迁移，而不是运行时猜测。

StyleManager 当前只验证定位枚举和字段组合，没有验证：

- `relative_to` 是否存在；
- 引用图是否有环；
- info_position、defined_texts、custom_text 是否使用了同一个名称；
- 一个节点是否能从合法绝对根到达。

全部内置 YAML 本次静态检查结果为干净：没有缺失引用、环或跨来源重名。但用户自建样式仍可能触发。建议加载阶段建立统一命名空间和有向图，错误时拒绝样式，并删除运行时拓扑排序末尾“把未排序节点补回”的容错行为。

## 7. P2：脚本分类不完整，会选错字体和盒度量

`_CJK_CHAR_RE` 覆盖常用汉字、扩展 A、兼容汉字、日文和部分全角字符，但未覆盖 Hangul、CJK 扩展 B 及更高平面、变体选择符。实测：

```text
中文한글  -> 中文=CJK，한글=Latin
中文𠀀    -> 中文=CJK，𠀀=Latin
永︀       -> 永=CJK，变体选择符=Latin
中文🙂    -> 中文=CJK，emoji=Latin
```

这不仅可能产生缺字方框，还会让错误字体的 ascent、advance 和 bbox 进入文字盒计算。应按 Unicode Script/Block 和 grapheme cluster 分段；Common/Inherited 字符应继承相邻文字的字体，不能独立切成西文 run。字体实际 cmap 覆盖与回退结果也应进入日志。

## 8. P2：小字号的整数化会放大比例误差

当前至少有四个离散化点：

1. 字号 `int(reference_side * size_ratio)`，并强制最小 12px；
2. margin、relative_margin、offset 和 line spacing 使用 `int()` 截断；
3. 中心对齐使用 `// 2`；
4. bbox 宽度是整数，而 getlength 可保留 1/64px。

所以此前看到的小字号“比例更大”不来自固定中文上移量，但 1px bearing、截断或栅格化误差在 12px 字号中可占 8.3%，在 100px 中只占 1%。所有计算都向零/向下取整，还会形成方向一致的偏差。

建议：

- 几何和 advance 全程保留 float；中心使用 `/ 2`；
- 比例转像素在最终阶段统一采用明确的舍入规则；
- 重新评估 12px 下限，至少在文档和 GUI 中显示最终实际字号；
- 若确实需要低于 12px 的稳定字形，可高分辨率渲染后缩小，而不是叠加人工位移。

## 9. P3：多行入口与实现不一致

试验曾调整多行行槽和空行递推，这些改动也已撤销。custom_text 在进入测量前执行 `replace('\n', ' ')`，CLI 参数帮助却写“支持多行”，所以该入口不会进入多行盒分支。defined_texts 可以进入该分支。

需要在产品语义上二选一：保留换行并支持多行 custom_text，或者把 CLI/GUI 文案明确改成单行。当前状态属于功能契约不一致，不是基线算法问题。

## 10. 历史改造建议（已由独立执行方案取代）

以下为审计时记录的方向，不是当前实施顺序。尤其第 3 项“让 safety bounds 参与 padding/tree 定位”会改变现有纯西文位置，与用户已确定的目标冲突；当前方案只记录越界，不自动移动基线或整树。实际改动与验收按[执行方案](FONT_BASELINE_EXECUTION_PLAN.md)。

1. 引入统一 `TextRunMetrics` / `TextBlockMetrics`，分离 baseline、advance、layout_box、safety_bounds、ink_bounds。
2. 用 getlength 推进 runs，以合并 bbox 记录实际墨迹；保持浮点坐标到最终绘制。
3. 为配置中的 Latin+CJK 字体建立内容无关的垂直 safety bounds，修复 padding 和 tree 的真实边界，同时保持混排基线稳定。
4. 明确 oversized overflow 策略，并覆盖单元素、相对组和 tree。
5. relative_to 改为精确 ID；StyleManager 验证唯一命名空间、引用存在和 DAG。
6. 改为 grapheme/script 感知的字体分段，再决定 custom_text 的多行契约。

每一步都应继续保留现有关键断言：加入中文前后，同一西文 run 的 baseline 和墨迹 y 范围必须完全一致。新增断言还应覆盖：墨迹/安全盒不得越过 padding、混排 run 原点等于前段 advance、超大盒按声明策略处理、非法引用在样式加载时失败。

## 11. 验证状态

- 审计脚本通过 `python -m py_compile`。
- 全部内置 YAML 引用图检查通过。
- 证据脚本没有修改生产配置、字体或应用日志。
- 审计时未继续改动 `src/`；随后按用户要求，之前的生产代码改动已撤销，所有修复建议均未实施。
- 仓库原有 `data/camera_map.csv`、`data/lens_map.csv` 修改未触碰。
