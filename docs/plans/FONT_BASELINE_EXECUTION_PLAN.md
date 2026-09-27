# Gotham / GlowSans 中西文混排基线修复：执行方案

状态：**待实施**。本方案供其他实施者直接执行。现象、根因、原始测量与 AC-1～AC-6 的定义见[分析报告](FONT_BASELINE_DIAGNOSIS.md)；[重测报告](FONT_BASELINE_REMEASURE_REPORT.md)和[文字盒审计](TEXT_BOX_ALGORITHM_AUDIT.md)是补充证据。诊断基于 dev 的 `b6c1c43707693caf39097d42c9fde1e081d3784b`；实施前须重新采集当前环境的旧行为。

## 1. 目标与实施边界

FilmClip/default、3000×2000 原图、54px Gotham Medium / GlowSans Medium、居中对齐时，纯西文 `AaBbCc` 的基线为 287；加入 `永和九年` 后，共同西文段变为 280，上移 7px。目标是**保留纯西文修复前的最终位置**，让混排和纯中文都按配置西文字体建立布局盒及基线。修复后该样本三种文本的基线均应为 287。中文字形仍可比西文更高、底部更低；不做光学补偿。

改动范围是[TextRenderer.render()](../src/core/text_renderer.py) 的测量与绘制、[LayoutEngine.layout_multiline_lines()](../src/utils/layout_engine.py) 的逐行定位，以及必要的诊断日志和验证脚本。保持现有样式配置、字体文件、12px 下限、margin/padding 与中心 `//2` 取整规则。保留横向 bbox 宽度推进和现有分段规则；advance/bearing、Unicode 扩展、超大盒策略、`custom_text` 多行入口另行评审。由字体缺失造成的实际字体变化需如实记录，不能承诺跨字体像素兼容。

| 阶段 | 工作 | 退出条件 |
|---|---|---|
| A | 在旧代码上采集真实 before，并验证断言确实能发现偏移 | 54px 旧值复现，旧实现的混排检查失败 |
| B | 按第 2 节契约修改单行、多行、空行和最终绘制 | AC-1～AC-5 通过，纯西文旧位置不变 |
| C | 完成诊断、CLI/GUI 回归与交付 | AC-6 通过，日志和产物可追溯 |

按 A → B → C 顺序实施。当前文件是设计文档，生产修复尚未执行。日常提交遵守仓库 `dev` 工作流和 `AGENTS.md` 合入门禁。

## 2. 唯一的定位数据契约

每个文字元素先按现有字号规则加载一次**西文定位参考字体**，不根据该元素是否含中文切换参考。设返回的 Pillow 正值度量为 `A_L, D_L = latin_font.getmetrics()`：

| 字段 | 定义 | 使用处 |
|---|---|---|
| `H_L` | `A_L + D_L` | 每个单行或多行行槽的逻辑高度 |
| `baseline_offset` | `A_L - D_L` | 行顶到最终绘制基线的距离 |
| `seg_info` | 现有 `(文本, 实际字体, bbox宽, 段ascent, 段descent)` 序列 | 保留字形字体、横向推进和逐段绘制 |
| `line_info` | `seg_info, width, height=H_L, baseline_offset` | 单行与多行使用同一行模型 |
| `draw_items` | 单行 item 保存该行的 `seg_info/width/height/baseline_offset`；多行 item 保存 `lines/width/height/line_spacing` | Phase 2 注册与 Phase 3 绘制共用同一测量结果 |
| 元素尺寸 | 单行高度 `H_L`；N 行高度 `N*H_L+(N-1)*S`，`S` 为现有整数行距 | `calculate_position()` 和 `register_element()` |

对**每个已进入渲染队列的非空文本**统一执行 `raw_lines = text.split('\n')`：无换行时得到一个行槽，有换行时保留首尾和连续空项。`custom_text` 的现有换行转空格处理发生在此步骤之前，暂不改变。空槽的 `seg_info=[]`、`width=0`，有正常 `H_L` 和 `baseline_offset`，不绘制字形。元素宽度取所有行宽的最大值；全空行块宽度为 0。完全空字符串继续遵守现有入口过滤规则。

**坐标只在最终布局完成后确定。** 对单行最终盒顶 `y`，基线 `B=y+baseline_offset`；每段仍用 Pillow 默认 `la` 锚点，在 `draw_y=B-seg_ascent` 绘制。多行第 i 个槽的行顶为 `y+i*(H_L+S)`，基线为该行顶加本行 `baseline_offset`。纯西文的 `draw_y=y+(A_L-D_L)-A_L=y-D_L`，与旧单段公式相同；真实兼容性仍以 A 阶段捕获的坐标和 mask 判定。

`seg_ascent/seg_descent` 只描述实际字形字体，不能改变逻辑高度。旧 `line_info.ref_ascent/ref_descent` 和单行 item 中同名字段在 B 阶段移除；`A_L/D_L` 如需记录，只放在元素级诊断信息中。`LayoutEngine` 只读取每行的 `baseline_offset`，避免出现两个可用的基线来源。

仅用于 DEBUG 的字体度量安全范围，相对逻辑盒顶为 `safety_top = baseline_offset - max(已加载配置字体的 ascent)`、`safety_bottom = baseline_offset + max(已加载配置字体的 descent)`；需要完整 Latin/CJK 组合时在诊断路径加载实际配置字体。这个估计值不一定覆盖特殊字形，精确墨迹仍由 mask 测量。`safety_bounds`、估计字形边界及像素墨迹边界都不能参与定位。不要把 `register_element(..., ascent=...)` 的遗留字段当作新基线来源。

## 3. 阶段 A：冻结旧行为

**A1｜锁定输入。** 在修改 `src/` 前记录 HEAD、工作区状态，以及 `text_renderer.py`、`layout_engine.py`、`font_manager.py`、FilmClip/default YAML 的 SHA-256。记录 Python、Pillow、FreeType 版本，实际选中变体、原图/画布尺寸，Gotham 与 GlowSans 返回字体的真实路径、字号和 `getmetrics()`；可访问字体文件时记录 SHA-256，否则记录对象类型。固定其他 EXIF、作者、地点和依赖元素内容，使配对案例只有待测文本不同。FilmClip YAML 内部 `name` 与目录名不同，必须记录 StyleManager 解析的文件路径。源码或字体与历史诊断不同，以本次实际 before 为准；已有未提交改动先保存差异，不清理用户工作区。

**A2｜先建独立测量器。** 按第 6 节接口，在未修复的真实 `TextRenderer.render()` 上捕获每次 `draw.text()` 的文本、坐标、字体和段基线 `draw_y+seg_ascent`；临时 hook 必须在结束时恢复。非空待测元素使用唯一文本，结合调用顺序、分段及 LayoutEngine 最终注册盒确认归属；纯空行案例按已配置的元素键和注册盒确认，并断言它没有 draw 调用。无法唯一归属的案例直接失败。每个 run 用原始 draw 方法按真实画布坐标生成独立灰度 mask，裁剪后连同裁剪原点保存；关键 54px 样本另存整画布 mask 交叉核对。捕获真实坐标，不用待验证的排版公式反推“实测值”。异常案例单独记录堆栈并继续采集。

**A3｜建立可复现样本。** 固定 3000×2000 原图、FilmClip/default、`custom_text` 54px，分别以内存配置测试 top-center、center、bottom-center 和三种文本。旧代码的实际基线应为：

| alignment | `AaBbCc` | `AaBbCc永和九年` 的西文段 | `永和九年` | 修复目标 |
|---|---:|---:|---:|---:|
| top-center | 319 | 319 | 327 | 均为 319 |
| center | 287 | 280 | 288 | 均为 287 |
| bottom-center | 254 | 240 | 248 | 均为 254 |

再仅通过内存配置把 `fonts.sizes.custom_text` 设为 `0.006/0.0135/0.0215/0.027/0.0405/0.05/0.054`，覆盖 12/27/43/54/81/100/108px；另设低于 0.006 的比例验证 12px 下限。每个字号 × 三种对齐 × 三种文本，对 `fonts.weight=light/regular/medium` 重复采集。用实际返回字号及字体路径命名和核对案例，避免把目标字号或配置家族当成实测。另采集中文在前、中文前后 ASCII 空格、`gypq`、一组多行反向顺序、首尾/连续空行、仅含 `\n` 或 `\n\n` 的 `defined_texts`，以及 relative＋tree 组合；`custom_text` 目前会把换行转为空格。

**A4｜旧实现反例。** `capture` 保存 before，不要求旧代码通过 AC-2/AC-3；随即在同一旧代码上运行 `compare`。它必须报告 center 混排西文相对纯西文 **-7px**、bottom-center **-14px**、center 纯中文 **+1px**，以非零退出码和案例 ID、expected、actual、delta 证明断言有效。top-center 混排原本不移动，不能单凭它验证工具。旧代码对仅含换行的案例可能抛 `IndexError`，作为已知失败保存，不计通过。封存非空不可覆盖的 `before/` 与失败对照输出后，才开始 B；字体或源码改变时另建基准目录。

## 4. 阶段 B：按契约修改实现

实现上建议提取三个私有职责：`_resolve_latin_reference()` 返回参考西文字体度量；`_measure_text_line()` 复用现有分段、字体选择和宽度计算，返回第 2 节的行数据；`_draw_line_runs()` 按给定基线绘制并推进 x。字体配置在元素循环前用 B1 的小函数统一规范化一次。名称可随现有代码调整，关键是单行与多行共用测量和绘制逻辑，LayoutEngine 只计算行位置。继续使用现有字典和 `seg_info` 元组，不引入新排版框架；实际改动按 B1～B4 顺序分步验证。

**B1｜固定参考字体（`TextRenderer.render()` Phase 1）。** 沿用 `fonts.get('sizes', {})`、`fonts.get('size_ratio', 0.02)` 和当前 `original_image_size` 取得每元素字号比例；行距继续用 `int(reference_side * line_spacing_ratio)`。在单行/多行、中文/西文分支之前调用一次 `load_font(fonts_cfg, original_image_size, text_specific_size_ratio, force_chinese=False)`，生成第 2 节的 `A_L/D_L/H_L/baseline_offset`，供该元素所有行复用。

当前 `FontManager.load_font()` 对缺失的 `latin/cjk` 能回退；显式 `latin: null` 或 `cjk: null` 在加载对应类别字体时会因 `None.get(...)` 抛 `AttributeError`。在传给加载器的**局部配置副本**中对两者使用同一规则：只有键缺失或值为 `None` 才置为 `{}`；映射类型（包括已有 `{}`）保留；字符串、列表等类型即使为空也报出对应的 `fonts.latin` 或 `fonts.cjk` 错误。不要用 `value or {}` 吞掉非法的空值类型，也不要改写 YAML。西文定位参考、B2 的字形字体和 DEBUG 诊断都从同一副本加载。

空配置经 `family=''` 进入对应的系统字体链：西文用 `_SYSTEM_LATIN_FILES`，中文用 `_SYSTEM_CJK_FILES`；依次尝试当前 weight、Regular、Medium、Light、Bold 中的可用映射，全失败后调用 `ImageFont.load_default()`。自定义字体文件缺失也沿对应链回退。记录真实返回字体与 metrics；无法获得可信 `getmetrics()` 就报错。现有全局 weight、weights 映射、字体缓存和 12px 下限继续由 [FontManager.load_font()](../src/utils/font_manager.py) 处理。CJK 配置规范化只保证字形加载可用，定位参考始终是 Latin；不要再从 `drawn_fonts.get('latin') or drawn_fonts.get('cjk')` 选择参考。

局部规范化可按下述写法实现，且只在 TextRenderer 内传递这个副本：

```python
from collections.abc import Mapping

def normalize_font_entry(fonts, key):
    # 同时处理 Latin/CJK；只有键缺失或 YAML null 才表示采用默认配置。
    value = fonts.get(key)
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f'fonts.{key} 必须是映射或 null')
    return value

# 在元素循环前构造一次局部副本，保留其他字段且不改写原配置。
fonts_cfg = {
    **fonts,
    'latin': normalize_font_entry(fonts, 'latin'),
    'cjk': normalize_font_entry(fonts, 'cjk'),
}
```

**B2｜统一测量（Phase 1）。** 保留 `FontManager.split_mixed_text()` 的段顺序和 `getbbox()` 的 `right-left` 宽度。对 `len(segments)<=1` 的非空行，仍按整串文本加载字形字体，生成一个 `seg_info` run；纯中文由 GlowSans 绘制，纯西文由 Gotham 绘制。多段仍按 `force_chinese=is_cjk` 为每段选字体，宽度为原段宽之和。所有非空行统一注册 `height=H_L` 和 `baseline_offset`，不再用段字体的最大 ascent/descent 定高度。

所有文本都按第 2 节先执行一次 `text.split('\n')`，逐项调用同一个测量方法；只有布局与绘制位置需要按一个行槽或多个行槽分流。空项生成无 run 的正常高度槽。元素宽度为 `max(line.width)`，高度为 `N*H_L+(N-1)*S`。`"AaBbCc\n\nAaBbCc"` 和 `"\n\n"` 都有 3 个槽，后者高 `3H_L+2S` 且不画字形。移除旧“空行只加间距”与“每个非空行先加间距、最后减一次”的分叉计算。旧 item 的 `mixed`、`text/font/descent/ref_ascent/ref_descent` 不再作为新定位数据保留；需要的字体度量写入元素级 DEBUG 日志。

**B3｜从最终盒绘制（Phase 2/2.5/3）。** 保留 `_resolve_element_order() → calculate_position() → register_element() → apply_tree_positioning()` 的调用顺序，以及 relative、tree、padding、中心取整与水平推进规则。Phase 3 才调用 `get_element_bounds(name)`；不得缓存 Phase 1/2 的绝对基线。单行统一使用 `B=y+baseline_offset`，每个 run 用 `draw.text((run_x, B-seg_ascent), ...)` 绘制，随后 `run_x += seg_width`；纯段旧 `y-item['descent']` 路径应退出纵向定位。纯西文仍只调用一次 draw。

**B4｜逐行定位（`LayoutEngine.layout_multiline_lines()`）。** 保留函数签名、返回顺序、line_alignment 合法性检查和 left/center/right 的原 x 公式。合法性检查后，空 `lines` 返回空列表；正常非空多行必须有 N 个行槽。以 `line_top=block_y` 开始，每行返回 `(line_x, line_top+line['baseline_offset'])`，再令 `line_top += line['height']+line_spacing`。删除首行 `ref_ascent/ref_descent` 初始化路径，并把函数的 `lines` 字段说明改为 `height/width/baseline_offset`；缺少 `baseline_offset` 应报契约错误。Phase 3 对每槽取得对应位置，先检查位置数等于行槽数；空槽不调用 draw，非空 run 仍绘于 `baseline_y-seg_ascent`。更新“视觉底部”等误导性注释为“布局盒底”，不改变树或夹持几何。

**B5｜按关口检验。**

| 完成后 | 立即验证 | 失败时先检查 |
|---|---|---|
| B1～B2 | 三种文本注册同一 `H_L`；实际字形字体和原横向宽度不变 | 内容相关参考选择、单段旧高度 |
| B3 | 54px 三种对齐分别达到第 3 节修复目标；纯西文 before 坐标和 mask 相同 | 最终盒顶、旧纯段 y 分支、字号和字体 |
| B4 | N 行槽、N−1 行距；纯换行不崩溃；无空行纯西文多行兼容 | 空行过滤、首行偏移、总高度 |
| 布局传播 | relative/tree/padding 后基线来自最终盒；墨迹越界只记录 | 提前缓存基线、把墨迹盒用于夹持 |

B 结束时第 6 节的 `compare` 应通过 AC-1～AC-5。不能用样式 margin、固定像素 delta 或中文专用补偿替代失败断言的修复。

## 5. 阶段 C：日志与实际回归

DEBUG 日志按元素记录实际参考字体路径/字号、`A_L/D_L/H_L`、行槽数、最终布局盒及基线；必要时逐 run 记录字体、ascent 和 draw_y。字体度量安全范围与逐段 `getbbox()` 合成的边界要注明坐标系，并命名为估计边界；精确非零像素墨迹盒和重心留在诊断脚本测量。空槽用“无墨迹”状态，不伪造零坐标。昂贵计算置于 DEBUG 开关后；诊断边界不反写布局高度或最终 y。实际字体无文件路径时记录对象类型和 metrics。

用 FilmClip/default 及另一种可输入作者或地点的样式，完成横图、竖图、CLI 单张、批量、GUI 输入切换和导出检查。记录 StyleManager 实际命中变体。旋转图先在文字坐标系判定基线，再核对旋转后的落点；GUI 缩放截图只作体感检查，像素断言使用源尺寸或无损 mask。按本次运行时间检查 `debug_log.txt` 新增 ERROR/TRACEBACK。若实施涉及资源、依赖或打包路径，再执行仓库规定的打包冒烟。

## 6. 验证器与产物格式

必须新增独立验收器 `docs/diagnostics/font_baseline/verify_latin_baseline_contract.py`；当前不存在。它复用真实渲染管线，独立捕获 draw 调用与 mask，并执行实际断言。提供 `--mode capture|compare|measure`、`--output`、以及 compare 的 `--baseline`：

| 模式 | 行为 |
|---|---|
| capture | 逐案例保存旧实现的事实；已知旧缺陷不使整个采集停止；非空输出目录拒绝覆盖 |
| compare | 重新真实渲染，执行 AC-1～AC-5 数值断言；失败或缺少基准、run、案例时返回非零 |
| measure | 输出墨迹盒/重心等诊断统计；整段不同内容的墨迹边界差不作为通过条件 |

`before/manifest.json` 至少含 commit、源/样式 SHA-256、实际字体路径及可访问文件的 SHA-256（无路径时记对象类型）、Python/Pillow/FreeType、实际变体、原图和画布尺寸。逐案例 JSON 含稳定案例 ID、文本来源/原文、对齐、字号、最终逻辑盒、行槽/行距、每 run 的文本/实际字体/xy/ascent/descent/基线，以及 mask 的半开边界和裁剪原点；异常保存类型与堆栈。裁剪 mask 比较前必须按原点还原到画布坐标；关键 54px 样本用整画布 mask 交叉核对。hook 中调用保存的原 draw 方法，退出恢复。纯西文旧快照是 AC-1 的 expected；跨语言 expected 来自配对的旧纯西文实测基线，不能由新生产 helper 自行计算。失败明细输出 AC 编号、案例 ID、expected、actual、delta，不能只把两值写进 JSON。共同西文 run 的像素 y 范围要求精确相等；先归一 x 原点以排除文本变宽的正常水平移动。字体或栅格化环境变化标为“环境不一致”，不放宽 1px 阈值。

实施脚本后，在激活 venv 的 PowerShell 中按顺序执行；每个输出路径必须是新的空目录：

```powershell
./venv/Scripts/activate
$env:PYTHONPATH = 'D:/Coding/MiLecFrame'
$tool = 'D:/Coding/MiLecFrame/docs/diagnostics/font_baseline/verify_latin_baseline_contract.py'
$run = 'D:/Coding/MiLecFrame/docs/diagnostics/font_baseline/implementation_run_01'
python $tool --mode capture --output "$run/before"
python $tool --mode compare --baseline "$run/before" --output "$run/control"
# 完成阶段 B 后再运行：
python $tool --mode compare --baseline "$run/before" --output "$run/after"
```

旧实现的 control 比较预期以非零退出，并保存第 3 节列出的位移；after 必须全通过。不要覆盖原始诊断数据。现有重测脚本中 `claim_A_baseline_restore.latin_glyph_shift=0` 是直接赋值，`claim_C_small_sizes.ink_top_shift` 是同基线残差，`claim_B_clean_contrast` 的 1px 观察不能推广为全部字形的上限；它们的输出不能替代新验收器的断言。可以复用其测量片段，但要按[分析报告第 10.2～10.3 节](FONT_BASELINE_DIAGNOSIS.md)区分字段口径。新脚本的资源路径遵守 `app_paths.py`，显式 `--output` 只作为本次诊断目录。

所有实际修改的 Python 文件均须在 venv 中运行 `python -m py_compile`；至少覆盖 `text_renderer.py`、`layout_engine.py` 和新验证脚本。仓库无现成测试框架，验证以本节脚本和实际渲染为准。

## 7. 验收矩阵

下表展开[分析报告第 7 节](FONT_BASELINE_DIAGNOSIS.md)的 AC-1～AC-6。对旧版含空行的错误布局，不要求像素兼容；修复后按行槽公式和空 mask 判定。缺失基准、环境不一致或未执行案例一律标为未完成。

| AC | 样本 | 必须满足 |
|---|---|---|
| 1～3 | 12/27/43/54/81/100/108px、light/regular/medium、三种对齐；纯西文/混排/纯中文 | 纯西文与 before 相同；混排共同西文 run 的基线及归一 x 后的像素 y 不变；纯中文使用该西文基线 |
| 2～3 | 中文在前、中文前后空格、`gypq`、标点 | 不因内容顺序或空格切换定位参考；正常下行部保留 |
| 5 | 正反顺序多行、首尾/连续空行、`\n`、`\n\n`；三种 line_alignment | N 槽、N−1 间距；全空槽不绘制且不崩溃 |
| 4 | 四种 relative_position、合法 cross_alignment、tree_align 开关、至少三层依赖、padding 触边 | 语言切换不引入额外纵向移动；最终盒决定绘制基线 |
| 1～4 | info_position 的作者/地点、defined_texts、custom_text；Latin/CJK 各自缺省、`{}`、`null`、两者同时 `null`、文件缺失、weight 覆盖；另测空字符串/空列表等非法类型 | 三入口共用行契约；混排/纯中文的 `cjk: null` 不崩溃；非法类型报对应字段；记录实际回退字体，定位始终使用 Latin |
| 6 | 横图/竖图、FilmClip/default 与另一内置样式、CLI 单张/批量、GUI 预览/导出 | 命中变体和字体可追溯，预览体感与源图数值一致，日志无新增错误 |

旧版因 `null` 崩溃的案例保存异常，不要求其不存在的像素快照满足 AC-1；另采集同环境下将对应键显式设为 `{}` 的可运行基准，修复后按这个等价配置核对实际字体和定位。旧版可正常绘制的纯西文案例仍须满足 AC-1。

完整画布墨迹顶部/底部/重心、中文越出逻辑盒以及大于可用区的已知场景只作诊断；不能以不同内容整行墨迹边界相等作为验收目标。若实际字体已回退，先核对环境指纹再解释坐标差异。

## 8. 交付与回退

交付时列出修改文件及原因、AC-1～AC-6 的逐项结果、54px FilmClip before/after 坐标与 mask、字体/环境指纹、CLI 单张/批量和 GUI 实际选中变体、日志检查结果，以及仍存在的关联问题。只有核心验证和实际回归完成后才更新方案及分析报告状态。所有新增代码须详细注释兼容公式，保留仍有效的原注释；生产改动、后续横向问题分别提交到 dev，版本及 mainline 合入按仓库门禁处理。

若纯西文位置变化，先核对字体，再检查 `H_L`、中心取整、旧 `-descent` 等价式与最终盒顶；若混排仍跳动，查残留的 max A/D 高度或中文基线来源。回退只撤销本次实施的明确改动或修复提交，重新运行旧行为复现；不要清理整座工作区或覆盖用户其他改动。
