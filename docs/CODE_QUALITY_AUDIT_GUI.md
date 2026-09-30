# GUI 代码质量审计与重构执行清单（暂不实施）

> **版本：v3（三审修订版），2026-09-30。本文是唯一执行依据，v1 原文中与本版冲突的表述一律以本版为准。**
>
> 审查链：v1 原审（基线 `b3b375c`）→ v2 复审 [`CODE_QUALITY_AUDIT_GUI_REVIEW.md`](./CODE_QUALITY_AUDIT_GUI_REVIEW.md)（基线 `b64388f`，带运行探针）→ v3 本版（对 v1/v2 逐项独立核验源码后合并修订，基线 `8e50ced`）。
> `b64388f..8e50ced` 两个新提交均在 core，`src/gui_pyside/` 零改动；工作区未提交修改也不含 GUI 文件。v2 全部结论适用于当前 HEAD。
> 范围：`src/gui_pyside/`（`src/gui_legacy/` 已封存不计入）；`src/utils/output_metadata.py`、`src/core/renderer.py` 等 GUI 消费方仅在与 GUI 缺陷直接相关处涉及。
> 运行证据：[`review_evidence/gui_report_reaudit.json`](./review_evidence/gui_report_reaudit.json)（探针脚本 `review_evidence/gui_report_reaudit.py`，Qt offscreen 真实控件 + 生产验证器，覆盖 14 个内置样式的三层往返、导出、布局几何、Dumper 副作用、源码指纹）。
> 行号基于 `8e50ced` 工作区，用于定位；实施时以函数名为准。
> **状态：已实施（2026-09-30，随 v2.7.2-dev 里程碑发行）。** T0–T9 全部任务包完成：正确性修复 commit `8cd4a96`（G13）/ `d78901c`（G14+G15+G16）/ `e705b98`（G10），清理与结构重构 `d83922a..b2fb919`。每任务包独立 commit，commit message 内含验收记录，预期行为差异按 §6 逐项标注。另有一项超出本清单的实测发现：LogoSection/CustomTextSection 的相对参数组初始 hide 后切相对模式完全不可见（与 G10 同根因），已随 T3 一并修复。

## 1. 结论与使用方法

v1 曾判断"GUI 行为正确性大体可信、问题不阻断发行"。**经 v2 探针与 v3 核验，该结论撤回**：除结构问题外，存在四个已确认/必现的正确性缺陷（G10、G13、G14、G15），任何一个都应在下次发行前修复：

| 缺陷 | 一句话描述 | 确证方式 |
|---|---|---|
| G10 | 定位编辑器相对参数组**从未加入布局**，切换到相对模式时控件以 100×30 默认几何浮在卡片角落，内容被裁剪 | 探针 `relative_layout_index == -1` + 源码静态确认 |
| G13 | PNG 导出**必然失败**：格式判断取临时文件 `.part` 后缀，期望格式恒为 JPEG，PNG 副本被验证器拒绝 | 源码推演 + 探针实测 `OutputMetadataError` |
| G14 | 样式编辑器保存会**静默改写元素引用**：`relative_to` 下拉缺少 `defined_text_0X` 实例键选项，FilmClip 四个元素的引用被改写为 `exif` | 探针 14 样式往返实测 |
| G15 | 样式经 GUI 读写后**三处数据静默丢失**：相对定位 `line_alignment`、`fonts.sizes.defined_text_0X` 字号、logo 段未知键（如 `max_dim_limit_ratio`），均为 core 真实消费的字段 | 探针实测 + core 消费点源码确认 |

结构问题维持 v1 判断（详见 G1/G2），但在上述缺陷修复前不得开始结构重构。

交接给执行智能体时：

1. 先读 §2 决策记录（已拍板，不得翻案）与 §3 QFluentWidgets 契约面；
2. 按 §7 任务包顺序实施，每个任务包独立 commit、独立验证、可独立回退；**禁止把正确性修复、清理、结构拆分混成一个改动**；
3. 按 §6 行为边界区分"必须保持一致"与"预期修复差异"（允许排版差异的只有 G10/D2；允许行为差异的只有 G13 的扩展名校验、D6 作者名清空、G14/G15 的数据保留修复）；
4. 按 §8 验收矩阵先留存 T0 基线再动手；模型层与控件层用机械对比验收，不依赖目测。

## 2. 决策记录（已拍板；D1/D2 为 v3 修订版，D4–D7 为 v3 新增）

| 编号 | 决策 | 说明 |
|---|---|---|
| D1 | 控件层合并后，非当前模式的定位参数组**采用"禁用（setEnabled）"而非"隐藏（hide）"** | 参数组恒占位，模式切换不改变卡片内容高度。`LogoSection`/`CustomTextSection` 现状即基准；`ElementEditor` 由 hide 改为 disable 是行为变化之一。**v3 修订：仅靠 D1 不能修复 G10——相对组未入布局是独立根因，见 D2** |
| D2 | **G10 修复 = 三步缺一不可**：(a) `rel_widget` 加入编辑器布局；(b) D1 禁用策略落地（`ElementEditor` 由 hide 改 disable）；(c) 模式切换信号路径补防御性 `QTimer.singleShot(0, self._adjustViewSize)` | v1 认为"8 行/6 行网格切换致高度失配"不是根因——相对组根本不在布局内。修复后相对组首次真正占位，**卡片展开高度会增加**，这是"从错到对"的预期差异，是全部改动中唯一允许的排版差异 |
| D3 | **本次交付物为文档，暂不修复** | 本文形成后代码零改动；实施另行启动 |
| D4 | **正确性缺陷（G10/G13/G14/G15/G16）优先于结构重构（G1/G2/G7 等）**，各自独立 commit；G15 必须先于 G1 模型层统一（重构基线应是修复后的无损行为，不能把"丢失"固化进新基线） | 任务包顺序见 §7 |
| D5 | G3 迁移采用**历史文本 → 稳定 key 别名表，长期保留** | 不采用 v1 的"findData 失败回退 findText、一个版本后移除"：该方案只兼容"文案未变"的场景，恰好遗漏 G3 要解决的"文案已变"场景；跳版本用户也会丢配置（v2/R6） |
| D6 | G12 作者名清空改为**显式写空**：`save_config` 在作者名为空时也写回空字符串 | v1 留了"二选一"未决，实施前必须落定（v2 指出）。行为变化列入预期修复差异；实施时验证 `ConfigManager` 对空串的往返 |
| D7 | G16 精度量化采用 **margin/offset 类 spinbox `decimals=3` → `4`** | 消除 `0.1605 → 0.161` 量化窗口；步进 0.005 不变，无副作用 |

## 3. QFluentWidgets 排版契约面（实施约束，违反即排版回归）

QFluentWidgets 组件众多，但牵动排版的隐性契约只有两个集中面。AGENTS.md 的 ExpandGroupSettingCard 六条铁律全部围绕它们。

### 契约 A：折叠卡高度机制（ExpandGroupSettingCard / ExpandSettingCard）

- 子控件必须经 `addGroupWidget()` / `addGroup()` 注册进 `widgets` 列表，禁止直接 `viewLayout.addWidget()`；
- 卡片展开高度 = `sum(w.sizeHint().height() + 3 for w in self.widgets)`（qfluentwidgets `expand_setting_card.py`），**任何改变子控件 `sizeHint` 的改动都必须补 `QTimer.singleShot(0, self._adjustViewSize)`**；
- QScrollArea / SmoothScrollArea / FlowLayout 的 `sizeHint()` 不反映 `setFixedHeight()` 与网格总高度，覆盖 `_adjustViewSize()` 时沿用 `StyleSelectorCard._adjustViewSize()` 的既有模板，不得改写其取高逻辑。
- **v3 补充（G10 教训）**：`dump_expand_card()` 的 `spaceWidget.h >= view.h` 判据**不充分**——G10 故障态下该不等式依然成立（内容 sizeHint 变小、滚动范围反而富余），必须同时检查子控件实际几何（相对组 `geometry()` 落在卡片可视区内、宽高接近其 sizeHint）。

### 契约 B：私有 API 与双主题样式注册

- `SmoothScrollArea.delegate.hScrollBar.scrollValue(...)` 是 qfluentwidgets **内部实现**，两处滚轮过滤器压在它上面（`image_processing_page.py`、`style_selector_card.py`）。重构只搬代码、不改访问方式、不"顺手封装"；
- 双主题样式必须走两步注册：`setCustomStyleSheet(widget, lightQss, darkQss)` + `addStyleSheet(widget, CustomStyleSheet(widget))`（现有封装 `_apply_custom_style()`；`StylePreview` 内联同款两步）。拆出的每个新 widget 都必须保留两步，少一步主题切换即失效；
- `qfluentwidgets.common.style_sheet` 深度导入按现状保留。

### 版本耦合点（升级 qfluentwidgets 时最先失效，实施时不改、只在注释标注版本基线）

| 耦合点 | 位置 |
|---|---|
| `scroll_area.delegate.hScrollBar` 私有访问 | `image_processing_page.py:95`、`style_selector_card.py:37` |
| `qfluentwidgets.common.style_sheet` 深度导入 | `image_processing_page.py:37-40`、`style_preview.py` |
| `ExpandGroupSettingCard._adjustViewSize` 覆盖（依赖内部 `spaceWidget` / `isExpand` / `widgets`） | `style_selector_card.py:133-141`、`layout_debug.py` 全文 |

## 4. 发现总览

优先级：P1 = 正确性缺陷（发行前必修）；P2 = 结构/契约改进（含大量删行机会）与数据精度问题；P3 = 小型清理。"排版契约"列标明实施时是否触碰 §3 契约面。

| 编号 | 优先级 | 发现 | 改动性质 | 排版契约 |
|---|---|---|---|---|
| G1 | P2 | 「定位元素」概念被 4 份模型 + 3 份编辑器重复实现，语义已漂移 | 等价重构（按 v3 修订后的边界） | 控件层触及契约 A |
| G2 | P2 | `image_processing_page.py` 1697 行，六种职责混杂 | 等价拆分 | 触及契约 B |
| G3 | P2 | 控件显示文本被当作稳定 key（5 个内联 map + config.json 文本持久化 + Logo 哨兵文本） | 契约修复 + 别名表迁移（D5） | 否 |
| G4 | P2 | `_on_export_yaml` 临时文件往返是纯浪费；开发环境会把临时文件写进 git 管理的内置目录 | 纯删除 | 否 |
| G5 | P2 | `_build_yaml_config` 污染全局 `yaml.Dumper`（进程级副作用，已探针证实） | 缺陷修复 | 否 |
| G6 | P2 | `ProcessingConfig` 整个模块是死代码 | 纯删除 | 否 |
| G7 | P2 | 相机/镜头映射页约 250 行高度重复（非字节级，存在字段/过滤器差异） | 等价收敛 + 初始化顺序显式设计 | 边缘 |
| G8 | P2 | 样板拷贝 4 组（PIL→QImage ×4、滚轮过滤器 ×2、胶片栏尺寸 ×3、spinbox 工厂 ×6） | 提取 helper | 否 |
| G9 | P2 | `StyleCreatorPage` 自建样式扫描器，绕开 StyleManager 单点入口 | 边界收敛（含加载格式契约） | 否 |
| G10 | **P1** | 定位编辑器相对参数组未加入布局 + 模式切换不刷新卡片高度（D2 三步修复） | **缺陷修复（预期排版差异）** | 触及契约 A |
| G11 | P3 | ~~无意义 hasattr 防御~~ → **v3 重定性：映射页守卫是必要的初始化保护，仅主窗口重复检查可清理** | 保守清理 | 否 |
| G12 | P3 | 未用导入、方法内重复 import、`getattr` 自防御；作者名清空残留按 D6 落定 | 小型清理 | 否 |
| G13 | **P1** | PNG 导出必然失败：`.part` 临时后缀被当作格式判断依据 | **缺陷修复（行为：PNG 可导出；扩展名不符时拒绝）** | 否 |
| G14 | **P1** | `relative_to` 下拉缺实例键选项，保存静默改写元素引用（FilmClip 实测 `defined_text_0X` → `exif`） | **缺陷修复（行为：引用保留）** | 触及契约 A（增删条目已有刷新） |
| G15 | **P1** | 模型层三处数据丢失：相对分支 `line_alignment`、`fonts.sizes` 实例键、logo 段未知键无透传 | **缺陷修复（行为：字段保留）** | 否 |
| G16 | P2 | 控件三位小数量化：ParamCapsule `margin_bottom 0.1605 → 0.161`（D7：decimals=4） | 精度修复 | 否 |

> G13–G16 为 v3 新增编号（源自 v2 复审 R3/R4 与 v3 独立核验）。v1 的 G10/G11 描述已被推翻或重定性，正文按 v3 修订版为准。

## 5. 发现详情

每条按固定结构给出：**根因**（代码定位）→ **影响** → **动作** → **验收**。

### G1（P2）「定位元素」概念被 4 份模型 + 3 份编辑器重复实现

**根因。** 样式系统只有一个概念："一个带定位参数的元素"（placement / position / 九点 alignment / 四向 margin / relative_to / relative_position / cross_alignment / relative_margin / offset_x/y / tree_align / line_alignment）。现状是四份模型、三份编辑器：

| 位置 | 重复形态 |
|---|---|
| `models/style_config_form.py:72-95` `ElementConfig` | 24 字段 |
| `models/style_config_form.py:98-121` `DefinedTextConfig` | 22 字段，与上者仅差 key/content 与个别默认值 |
| `style_config_form.py:244-263`（logo_\*）、`:286-306`（custom_text_\*） | 17 + 16 个扁平字段，同概念第三、四份拷贝 |
| `to_yaml_dict()` / `from_yaml_dict()` | "绝对分支写 alignment / 相对分支写 cross_alignment"各重复 4 遍；`left-of/right-of → cross 默认 center 否则 left` 规则重复 4 次 |
| `widgets/element_editor.py:317-403` | `load_element/save_element/load_defined_text/save_defined_text` = 2 对几乎相同的拷贝 |
| `custom_text_section.py`（约 320 行）、`logo_section.py`（308 行）、`element_editor.py`（422 行） | 各自重建同一套 abs/rel 参数组；`_on_relative_position_changed` + `_sync_cross_options` 三份拷贝 |

三份编辑器语义已经漂移（复制粘贴的必然后果），v3 核验确认的差异清单——**统一时必须逐项显式决策，不得当作"等价删重"**：

| 差异点 | `ElementEditor` | `LogoSection` / `CustomTextSection` |
|---|---|---|
| 非当前模式参数组 | `hide()`（`element_editor.py:247、255-256`） | `setEnabled()` 灰显恒占位 |
| `load_from_model` 加载范围 | 两个分支全字段加载 | 只加载当前模式分支（切换模式后另一分支显示构造默认值） |
| 网格布局 | 单字段每行、两列 | 两个字段并排、四列 |
| 专属字段 | `tree_align` 开关 | Logo：`size_ratio`/`diagonal_limit`；CustomText：`line_spacing`/`line_alignment` 独立控件 |
| cross 无效值重置（切回 above/below 时） | 重置为 `left`（`element_editor.py:279-284`，与序列化默认规则一致） | 重置为 `center`（`logo_section.py:239`、`custom_text_section.py:240`，探针证实） |

**影响。** 每新增一个定位字段要改 4+ 处；漂移已造成行为不一致（上表），后来者抄哪份都不对。

**动作（v3 修订：数据层收敛，控件层共享"绑定"而非共享"布局"）：**

1. **模型层**：定义 `PositionedSpec` dataclass 承载全部定位字段 + `to_entry()/from_entry()` 单点序列化；`ElementConfig = PositionedSpec + key`、`DefinedTextConfig = PositionedSpec + key + content`；logo / custom_text 改为持有 `PositionedSpec` 成员（flat 字段收拢为嵌套成员）。序列化规则必须吸收 G15 修复后的行为（line_alignment 与模式无关、未知键透传）。行数预期（903 → 约 400）仅作参考，以职责与验收为准；
2. **控件层**：抽取共享的**定位参数绑定层**——load/save 全字段映射、cross 合法值同步、`relative_to` 选项管理（复用 G14 的接线）单点实现。**各宿主（ElementEditor / LogoSection / CustomTextSection）保留自己现有的列数、字段集合、顺序与默认值**，不得把 `ElementEditor` 的两列网格强加给 Logo/CustomText（否则违反"除 G10 外排版不变"边界）。专属字段（size_ratio / diagonal_limit / line_spacing / line_alignment / tree_align）留在宿主，不进共享层；
3. **模式切换行为统一为 setEnabled（D1）**：非当前模式组灰显恒占位；`load_from_model` 统一改为**两个分支都加载**（与 `ElementEditor` 现行为对齐，消除"切模式丢模型值"）；
4. **cross 重置规则统一为模型序列化默认**：`left-of/right-of → center`，`above/below → left`（以 `from_yaml_dict` 既有规则为准；Logo/CustomText 的 `center` 重置是历史漂移，统一即行为微调，列入预期修复差异）。

**验收。** ① 模型层：YAML round-trip 机械对比为空（以 T2 修复后的新基线，而非 T0 旧基线——旧基线含 G15 丢失）；② 控件层：14 个内置样式 + 合成样本经"模型 → 真实控件 load/save → 模型"对比，除 G14/G15/G16 修复产生的字段保留外零差异；③ 四张卡 `dump_expand_card()` 合格（含子控件几何检查）；④ 三宿主编排不变（列数、顺序、视觉位置）。

### G2（P2）`image_processing_page.py` 1697 行

**根因。** 六种职责焊在一个 QWidget：拖放（`dragEnterEvent`–`dropEvent`）、胶片栏 CRUD（`_add_filmstrip_item` / `_remove_filmstrip_item` / `_rescale_*`）、预览渲染（`_update_preview` / `_create_thumbnail`）、EXIF 面板（`_update_exif_info`）、导出校验发布（`_file_sha256` 1268-1275、`_export_verified` 1277-1317）、配置持久化（`save_config` / `_load_saved_config`）、6 张配置卡构建（`_create_*_card`）。

其中 `_on_generate_frame`（1359-1500）单方法 140 行，5 个"显示文本→稳定 key"内联字典（`fw_map`/`lens_map`/`ts_map`/`pos_map`/`col_map`，1373-1413）埋在方法体中段（随 G3 一并消灭）。

**关于导出流程归属的定性与 v1 不同**：`_export_verified` docstring 中"GUI 只调用验证器，不自行拼接或修复任何元数据字段"限定的是**元数据拼接**，并不禁止视图层做导出编排；把导出服务拆出是架构改进建议，不是修复"违反既定原则"。**但拆分不得原样搬运——`_export_verified` 内含 G13 确认的故障，必须先修（T1）再拆（T8），否则只是把 bug 搬家。**

**动作。** 胶片栏 → `widgets/filmstrip.py`；导出流程 → `src/utils/output_metadata.py` 或独立导出服务（含 `_file_sha256` / `_export_verified`，搬运的是 G13 修复后版本）；6 张配置卡构建 → `pages/image_processing_config_cards.py`；`_on_generate_frame` 的配置收集 → 纯函数 `collect_render_options(...)`。拆分严格遵守 §3 契约 B（两步注册、`delegate.hScrollBar` 访问、splitter 信号连接原样搬运）。目标每块 ≤ 300 行（参考值）。

**验收。** 生成一张 + 批量导出各一次（冒烟，JPEG/PNG 都过）；light/dark 切换目测拆分后 widget 样式生效；胶片栏滚轮横滚、splitter 拖拽、窗口 resize 行为不变。

### G3（P2）控件显示文本被当作稳定 key

**根因。** `image_processing_page.py:76-81` 的 `PORTRAIT_ADAPTATION_ITEMS` 用 `addItem(text, userData=稳定枚举)` 并把稳定值写入 config.json——这是本文件的规范答案。但其余控件走反路：

- `_on_generate_frame` 用中文 `currentText()` 反查 5 个内联 map（1373-1413）；
- `save_config`（1631-1635）把中文显示文本写入 config.json（`output_format`/`bg_fill`/`font_weight`/`timestamp_display`），`_load_saved_config`（1656-1672）用 `findText` 恢复；
- **v3 补充（v2/R6 与核验确认）**：Logo 下拉的哨兵文本 `"自动匹配"`/`"无"`（678-683 写入选项，1386-1392 用 `currentText()` 判断渲染分支）同样是裸文本协议——哨兵文案一改，Logo 渲染映射静默失效。

**影响。** 任何中文文案调整 = 渲染映射静默失效（回退默认值）+ 用户旧配置恢复失效。同文件两种模式并存，后来者必然抄错。

**动作（含 D5 迁移策略）。**

1. 全部 combo（含 `combo_logo` 的哨兵与动态 logo 名）`addItem(text, userData=key)`；删除 5 个内联 map；`_on_generate_frame` 改读 `currentData()`；`save_config`/`_load_saved_config` 一律读写稳定 key；
2. **迁移用历史文本 → key 别名表**（模块级常量，长期保留）：load 时先 `findData(key)`；失败再查别名表把旧中文文本映射到 key 后 `findData`；仍失败回退默认项。**不采用** v1 的"findText 一次性兼容、一个版本后移除"——findText 只在文案未变时有效，恰好漏掉本条要防的场景；
3. bg_fill 选项来自 `BackgroundFillManager` 注册表，其显示文案也在本保护范围内。

**验收。** ① 旧 config.json（存中文文本）在新代码下正确恢复全部下拉项（含 bg_fill 全部选项）；② **修改任意下拉项显示文案后**（验收时临时改一处文案实测）渲染映射与配置恢复仍正确；③ 新 config.json 只存稳定 key；④ Logo 哨兵文案改动同理验证。

### G4（P2）`_on_export_yaml` 临时文件往返

**根因。** `style_creator_page.py:571-586`：把 YAML 写到临时文件再删除，只为取字符串；except 分支里的 fallback `_build_yaml_config(self.form_data.to_yaml_dict())` **就是正确实现**。

**影响。** 除纯浪费外：临时文件名 `__temp_preview__.yaml` 以 `_` 开头，GUI 自建扫描器（`_get_existing_styles`）会过滤，但 `StyleManager.get_available_styles()` 不过滤 `_` 前缀——写盘后若崩溃残留，渲染页样式列表会出现 `__temp_preview__`。**v3 补充**：开发环境 `CONFIGS_DIR = _RESOURCE_ROOT/src/frame_styles/configs`（`style_creator_page.py:81`），即临时文件直接写进 git 管理的内置样式目录；打包环境才是 exe 同目录 `styles/`。

**动作。** 删除 try 分支的文件 I/O，直接调用 `_build_yaml_config(self.form_data.to_yaml_dict())`。跨模块 import 私有名 `_build_yaml_config`（`style_creator_page.py:31-35`）的命名问题**移出本条**（避免把 API 改名混进纯删除），随 G1 模型层统一时一并处理。

**验收。** 导出预览弹窗内容与修改前字节一致；`git status` 确认内置目录无新文件。

### G5（P2）`_build_yaml_config` 污染全局 `yaml.Dumper`

**根因。** `style_config_form.py:165-177`：`dumper = yaml.Dumper; dumper.add_representer(list, flow_list)` 修改**类级** representer 表，影响进程内之后所有 `yaml.dump()` 调用，且每次调用重复注册。

**影响（探针已证实）。** 调用前后原生 `yaml.dump({'items': [1, 2]})` 从块列表 `items:\n- 1\n- 2` 变为流式 `items: [1, 2]`，`yaml.Dumper.yaml_representers[list]` 确实被改写。**定级说明（v3 采纳 v2/R7）**：证据只证明全局格式副作用，未证明活动 GUI 消费者数据损坏，故从 v1 的 P1 降为 P2；但它不是"零风险纯清理"——隔离 representer 改变进程行为，需独立验收。

**动作。** 模块级一次性 `class _FlowListDumper(yaml.Dumper)`（类体或 `__init__` 中注册 representer），`yaml.dump(data, Dumper=_FlowListDumper, ...)`。

**验收。** ① 同输入样式 YAML 输出与修改前字节一致；② 调用 `_build_yaml_config` 前后，普通 `yaml.dump` 的 representer 表与输出不变。

### G6（P2）`ProcessingConfig` 是死代码

**根因。** `models/processing_config.py` 全模块 44 行 + `image_processing_page.py:43`（import）、`:173`（构造）后再未读写。docstring 声称"每个 FileItem 可以拥有独立的 ProcessingConfig"从未发生。

**动作。** 删除模块与属性。若"多文件各自配置"仍是需求，另行立项，不保留悬空抽象。

**验收。** 删除后 `python -m py_compile` 通过；GUI 启动、图像处理页构造正常。

### G7（P2）相机/镜头映射页约 250 行高度重复

**根因。** `camera_mapping_page.py` 与 `lens_mapping_page.py` 的 `_load_data` / `_create_search_bar` / `_create_action_bar` / `_create_data_table` / `_populate_table` / `_on_table_item_changed` / `_on_add_row` / `_on_delete_row` / `_on_save` / `showEvent` / `cleanup` 高度重复（**v3 修正 v1 表述：非字节级**——CSV 字段、排序键、筛选维度、保存处理存在差异）。相机页把同一段 6 行按钮 QSS 内联写两遍（185-190、197-202），镜头页已抽 `_setup_btn_style()`——跨页不一致。

**动作。** 提取 `CsvMappingPage` 基类，扩展点显式参数化：fieldnames / 排序键 / 筛选卡构建器 / 标题文案 / 保存字段。**基类必须一并显式设计初始化顺序**（现状两页都是 `_load_data()` 先于 `_setup_ui()`，这正是 G11 守卫存在的原因；基类应改为"先 `_setup_ui` 再加载数据"，或把"读 CSV"与"刷新表格"拆成两步，从根上消除对 `hasattr` 守卫的依赖）。按钮 QSS 并入基类单点；**不顺手改现状视觉**（按钮 QSS 未做 dark 适配，保持原样，另行处理）。

**验收。** 两页首次构造、首次显示、再次显示均正常，CSV 正确加载与保存；筛选/搜索/增删行行为不变。

### G8（P2）样板拷贝清单

**根因与位置。**

| 样板 | 拷贝数 | 位置 |
|---|---|---|
| PIL → QImage（RGB888 + sRGB 标记 + copy） | 4 | `image_processing_page.py:973-976`（`_create_thumbnail`）、`1142-1146` 与 `1155-1159`（`_update_preview` 一个方法内两段几乎相同）、`style_preview.py:169-176` |
| 垂直滚轮→水平滚动过滤器 | 2 | `image_processing_page.py:84-98`（`FilmStripWheelFilter`）≡ `style_selector_card.py:26-41`（`HorizontalWheelFilter`） |
| 胶片栏尺寸计算 `max(60, h-40)` / `min(…,120)` / `×1.25` | 3 | `image_processing_page.py:981-983`、`1047-1049`、`1191-1193` |
| 网格 spinbox 工厂 | 6 | `canvas_section.py:56`、`padding_section.py:40`、`corner_radius_section.py:59`、`logo_section.py:191`、`custom_text_section.py:195`、`element_editor.py:60`（`_add_spinbox_row`） |

**动作。** 各抽一个模块级 helper / 共享组件（落 `widgets/` 或 `utils/`）。**helper 必须参数化保留语义**（v3 采纳 v2 补充）：图像转换保留颜色模式、sRGB 标记与 `copy()` 生命周期；spinbox 工厂参数化 range/step/decimals（G16 的 decimals=4 落地后同步）；**不因工厂相似而强制统一不同网格布局**。`_create_thumbnail` 与 `_update_preview` 先在类内合一，再随 G2 拆分归位。

**验收。** 替换点逐一对拍（缩略图/预览像素一致、滚轮行为一致、spinbox 范围步进一致）。

### G9（P2）GUI 自建样式扫描器绕开 StyleManager

**根因。** `style_creator_page.py:393-423`（`_get_existing_styles`）与 `:425-442`（`_resolve_style_filepath`）重新实现"样式在哪、怎么解析"。两份实现语义已分歧：StyleManager 支持 `.json/.yaml/.yml/.toml`（`style_manager.py:124、186、271`）且不过滤 `_` 前缀，GUI 只认 `.yaml` 并过滤 `_`。同类问题：`image_processing_page.py:733-765` 在视图层直读 `config.get('layout', {}).get('custom_text')` 等 YAML 内部形状判断能力开关。

**动作。** 给 `StyleManager` 增加 `list_style_files()` / `resolve_style_file()`（复用其 `extra_dirs` 优先级语义），GUI 只消费 API。**契约必须一并定义（v3 采纳 v2 补充）**：若枚举结果包含 `.json/.yml/.toml`，GUI 的加载（`StyleConfigFormData.load_from_file` 目前只有 `yaml.safe_load`）与保存格式策略要同步——枚举 API 要么带格式过滤参数，要么 GUI 明确"仅加载 YAML、其余格式只读列出"。样式内省（能力开关判断）收敛单一出口，可与 `docs/plans/STYLE_OPTION_CAPABILITIES_PLAN.md` 的能力化方向合并考虑，避免新增第二套能力判断规则。

**验收。** 样式编辑器列表与 StyleManager 枚举一致（含用户目录优先级）；加载/保存一个真实 YAML 样式正常；非 YAML 格式按定义的契约呈现。

### G10（P1）定位编辑器相对参数组未加入布局 + 模式切换不刷新卡片高度（D2）

**根因（v3 重写，v1 的"8 行/6 行网格切换致高度失配约 ±2 行"描述不成立）。** 两重独立问题：

1. **主因：`rel_widget` 从未加入布局。** `element_editor.py` 的 `_setup_ui()` 只在 167 行 `layout.addWidget(self.abs_widget)`；`rel_widget`（170 行创建，内部网格 sizeHint 高约 243）直到 247 行 `hide()` 都没有对应的 `layout.addWidget(...)`。模式切换（255-256 行 `setVisible`）后它**不参与布局管理**，几何停留在 QWidget 默认 100×30，浮在父容器原点附近，内部控件被严重裁剪。探针实测：`editor.layout().indexOf(rel_widget) == -1`，两张卡（ElementsSection/DefinedTextsSection）一致；
2. **次因：模式切换路径没有高度刷新。** `DefinedTextsSection` / `ElementsSection` 的添加/删除条目路径有 `QTimer.singleShot(0, self._adjustViewSize)`（`defined_texts_section.py` / `elements_section.py:102、112`），模式切换路径没有——违反 AGENTS.md 铁律 5。探针实测：切换后内容 sizeHint 482 → 154，卡片高度保持 552 未刷新。

**影响。** 用户把任一 info_position 元素或预定义文本切到"相对定位"时，相对参数组显示为左上角一个被裁剪的小块，大部分字段不可见不可操作。

**动作（D2 三步，缺一不可）。**
① `layout.addWidget(self.rel_widget)`（与 `abs_widget` 并列，两参数组都在布局内）；
② 落地 D1：模式切换改 `setEnabled()`，两组恒占位（高度不再随模式变化，也消除未来的 sizeHint 抖动）；
③ 模式切换信号路径补防御性 `QTimer.singleShot(0, self._adjustViewSize)`（由宿主卡片监听编辑器模式变化触发，或编辑器发信号）。

**验收。** ① 四张卡（ElementsSection / DefinedTextsSection / LogoSection / CustomTextSection）`dump_expand_card()` 合格；② **子控件几何检查**：两组 `layout().indexOf(...) >= 0`，相对模式下每个相对字段控件 `geometry()` 完整落在卡片可视区且宽度正常（不能只看 `spaceWidget.h >= view.h`——G10 故障态下该不等式仍成立）；③ absolute → relative → absolute 往返、初始加载即 relative、多条目场景逐一验证。**修复后卡片展开高度高于现状（相对组首次真正占位），这是唯一允许的排版差异，方向为"从错到对"。**

### G11（P3）hasattr 防御——v3 重定性

**根因（v3 撤回 v1 对映射页的判断）。** v1 称"页面/表格均由初始化无条件创建，防御分支纯噪音"。**对相机/镜头映射页这是错误的**：两页 `__init__` 都是 `_load_data()` 先于 `_setup_ui()`（`camera_mapping_page.py:89-90`），而 `_load_data()` 末尾（106 行）就调用 `_refresh_table()`，此时 `_table` 要到 `_setup_ui() → _create_data_table()`（260-261 行）才创建。守卫（`_refresh_table` 开头 `if not hasattr(self, '_table'): return`）是必要的初始化保护。探针证实：删除守卫后两页构造即 `AttributeError: ... has no attribute '_table'`。

其余点位需逐个判断回调时序，不能用"最终无条件创建"一概而论：

| 位置 | 时序分析 | 处置 |
|---|---|---|
| `main_window.py:160、164` | 同一 `image_page` 属性在 closeEvent 里检查两遍，纯重复 | 合并为一处检查（或直接调用） |
| `main_window.py:167+` camera/lens/style 页守卫 | closeEvent 必然晚于 `__init__` 完成 | 可删，直接调用 |
| `style_creator_page.py:702`（`resizeEvent` 查 `preview`） | resizeEvent 首次触发时序需实测（首帧前后） | 实测确认构造完成前不会触发再删；有疑虑则保留 |
| 两映射页 `_refresh_table` 守卫 | **必须保留**（v1 删除动作撤回） | 保留现状；根治随 G7 基类统一初始化顺序时处理 |

**验收。** 涉及页面首次构造、首次显示、再次显示无异常；主窗口关闭无异常；`debug_log.txt` 无新增 ERROR。

### G12（P3）小型清理

- 未使用导入：`image_processing_page.py` 的 `Optional` / `QSize` / `QWheelEvent` / `InfoBarPosition` / `SettingCardGroup`（仅注解使用的除外），逐个确认后删除；
- 方法内重复 import：`image_processing_page.py:836-837`（`_load_files` 内 `import io, os`，模块顶部已有）、`style_creator_page.py:574`（`QTextEdit`，顶部已有）；
- `style_creator_page.py:643` `getattr(self, '_first_show', True)` 自防御本类属性，改直接 `self._first_show`；
- 作者名清空残留（`image_processing_page.py:1626-1627` 为空不写回，旧值永久残留）：**按 D6 落定为显式写空**，不再保留"二选一"。

### G13（P1，v3 新增）PNG 导出必然失败：格式判断取临时文件后缀

**根因。** `_export_verified`（`image_processing_page.py:1277-1317`）：副本固定命名 `tmp_path = dst_path + '.part'`（1295 行），而格式判断取**临时路径**的后缀——`Path('out.png.part').suffix` 恒为 `.part`，于是 1305-1306 行 `expected_format` 恒为 `'JPEG'`。`verify_output_metadata`（`output_metadata.py:746-760`）打开副本检查实际编码，PNG 副本必被拒绝：`OutputMetadataError: 输出实际格式为 PNG，期望 JPEG`。

**影响（探针实测）。** **PNG 导出 100% 失败**，单张（1338 行）与批量（1518 行）共用同一路径；JPEG 不受影响。另有一个连带契约问题：JPEG 源 + 用户在保存对话框选 `.png` 后缀时，验证按 JPEG 通过，会发布"内容是 JPEG、扩展名是 .png"的文件（保存对话框提供 `*.jpg`/`*.png` 两种过滤器，实际从不转码）。

**动作。**
1. `expected_format` 改从**源文件实际编码**判定（副本是源的字节拷贝，格式必然一致；可用 `Image.open(src_path).format` 或源路径后缀，推荐前者——`read_output_software(src_path)` 本就要打开源文件，可顺带取格式）；
2. **目标扩展名契约（行为变化，列入预期修复差异）**：目标路径扩展名与源实际编码不一致时**拒绝导出并提示**（不发布内容与扩展名不符的文件，也不引入转码——导出的语义是"已验证结果的副本"，转码会破坏哈希一致性校验的前提）。

**验收。** ① JPEG/PNG × 单张/批量导出全部成功且格式正确；② 校验失败路径（可临时注入损坏副本）旧目标保留、`.part` 临时文件被清理；③ 目标扩展名与源不符时被拒绝且提示明确。

### G14（P1，v3 新增）`relative_to` 下拉缺实例键选项，保存静默改写元素引用

**根因。** `ELEMENT_KEYS`（`style_config_form.py:25-31`）只有固定键和泛称 `custom_text` / `defined_text`，**没有 `defined_text_01` 等实例键**。而 `ElementEditor`（`element_editor.py:176`）与 `LogoSection` / `CustomTextSection` 的 `relative_to` 下拉都用它填充选项。加载时 `setCurrentText(elem.relative_to)`（331 行）对不在选项中的值**静默失败**（保持当前默认项 `exif`），保存时（357 行）把当前项写回。已有的 `update_relative_to_options()`（415-421 行）**没有任何调用点**——接口写了，接线忘了。

**影响（探针实测）。** FilmClip 两个变体的四个 `info_position` 元素（`relative_to: defined_text_01..04`，`FilmClip/default.yaml:84-99`）经样式编辑器"加载 → 保存"后引用全部变成 `exif`——相对布局依赖链被静默破坏，渲染结果改变。LogoSection / CustomTextSection 的 `relative_to` 下拉存在同样问题（样式同样可引用实例键）。

**动作。**
1. `ElementsSection` / `DefinedTextsSection` 在**初始加载后与每次条目增删后**，为每个编辑器调用 `update_relative_to_options(可用键列表)`：固定键 + 当前全部 `defined_text_0X` 实例键（各编辑器排除自身 key，防自引用——`_on_mode_changed` 已有自引用保护，选项注入时同样排除）；
2. 加载路径：先注入选项再设值，模型中的引用值必须能被选中；若引用指向**不存在的键**（如被删除的条目），保留原文本进选项并打日志提示，由保存后 StyleManager 校验拒绝，**不得静默改写**；
3. `LogoSection` / `CustomTextSection` 的 `relative_to` 下拉同样接入实例键选项（它们的 `relative_to` 可指向 defined_text 实例）。

**验收。** ① FilmClip 两变体经 GUI 加载 → 不改任何东西 → 保存，`relative_to` 全部保留为 `defined_text_0X`；② 增删 defined_text 条目后各编辑器的 `relative_to` 选项同步增删；③ 引用不存在键时保存的样式被 StyleManager 拒绝且日志有提示。

### G15（P1，v3 新增）模型层三处数据丢失——样式经 GUI 读写后字段静默消失

探针对 14 个内置样式做"源 YAML → 模型（`from_yaml_dict`）→ 输出（`to_yaml_dict`）"与"→ 真实控件 load/save →"对比，区分两类差异：**默认值补齐/省略**（源没写 `margin_top`、输出补 `0.0` 之类，语义等价，可接受）与**字段丢失**（源有值、输出消失）。以下三处是后者，且均为 core 真实消费的字段——不是良性格式化：

**15a. 相对定位分支丢失 `line_alignment`。** `to_yaml_dict()` 只在绝对分支写它（elements 432-434 行、defined_texts 469-470 行；相对分支 435-446 / 473-481 不写）；elements 的相对**读取**分支（702-721）也不读（defined_texts 读取 823-824 行不分模式，读进了也写不出）。`custom_text` 反而正确（506-507 行在分支外，两模式都写）。`STYLE_GUIDE.md` 明确"line_alignment 是文字专用字段，**与绝对/相对定位模式无关**"。探针：相对 defined_text 输入 `line_alignment: right` → 输出消失。内置样式恰好没有"相对 + 非默认行对齐"组合，属未爆雷区。
→ **修复**：相对分支同样读写 `line_alignment`（非默认才写，与绝对分支规则一致）。

**15b. `fonts.sizes` 的实例键被白名单过滤。** `from_yaml_dict`（645-649 行）只按 `COLOR_ELEMENT_KEYS` 收集 `sizes`，`defined_text_01..04` 等实例键被丢弃。core 消费点：`text_renderer.py:286-292` 按 key（含实例键）查逐元素字号。探针实测：ParamCapsule 两变体（0.02 × 4）、FilmClip 两变体（0.027 × 4）的实例字号往返后全部消失，保存后 defined_text 回退默认字号，渲染变化。
→ **修复**：`sizes` 收集不设白名单（或白名单 + `defined_text` 前缀透传），未识别键原样保留。

**15c. logo 段没有未知键透传。** layout 段有 `_passthrough_layout`、colors 段有 `_passthrough_colors`，logo 段没有等价机制：`from_yaml_dict`（754-792 行）只读固定字段，`to_yaml_dict`（518-545 行）只写固定字段。core 消费点：`renderer.py:402-404` **优先**读 `max_dim_limit_ratio`（回退 `diagonal_limit_ratio`）。探针实测：Bottom Bars 两变体的 `logo.max_dim_limit_ratio: 2.5` 往返后消失，且被模型默认 `diagonal_limit_ratio: 2.0` 顶替——Logo 长边限制从 2.5 变 2.0，渲染行为改变。
→ **修复**：logo 段增加未识别键透传容器（参照 `_passthrough_layout` 模式；`enabled` / `size_ratio` 等已识别键正常消费）。

**验收。** ① 14 个内置样式 + **合成样本**（相对 + `line_alignment: right` 的 defined_text、带实例字号的 defined_text、带 `max_dim_limit_ratio` 的 logo）三层往返（源 → 模型 → 控件 → 模型 → 输出）：上述字段零丢失；② 对比报告区分"默认值补齐/省略"与"字段丢失"，仅前者允许；③ 修复后的输出作为 G1 模型层重构（T6）的新基线。

### G16（P2，v3 新增）控件三位小数量化损失

**根因。** `ElementEditor._add_spinbox_row`（`element_editor.py:60-77`）默认 `decimals=3`，第四位小数被舍入。**纯模型层往返无量化**（`from/to_yaml_dict` 是 float 直通），损失发生在控件层 load/save。

**影响（探针实测）。** ParamCapsule 两变体四个元素的 `margin_bottom: 0.1605` 经控件往返变 `0.161`（胶囊中心视觉补偿值被改动）。

**动作（D7）。** margin / offset 类 spinbox `decimals` 提到 4（step 0.005 不变）。随 G8 的共享 spinbox 工厂落地，各调用点核对 range/step/decimals。

**验收。** ParamCapsule 两变体经控件往返 `margin_bottom` 保持 0.1605；四张定位卡 `dump_expand_card()` 仍合格（decimals 不影响布局）。

## 6. 实施前必须保持的行为边界

| 边界 | 要求 |
|---|---|
| 排版不变 | **除 G10（D2）外**，所有改动不得改变任何控件的视觉位置、尺寸、间距；G1 控件层合并保留各宿主现有网格编排 |
| YAML 语义 | 样式配置 round-trip 一致性以 **T2（G14/G15/G16）修复后的输出为新基线**；透传容器（`_passthrough_layout` / `_passthrough_colors` / 新增 logo 透传）、`_clean_dict` 清理规则、flow_style 列表行为不变 |
| 预期行为差异 | 仅允许四处：G10 排版修复；G13 扩展名不符拒绝导出；D6 作者名显式写空；G14/G15 数据保留修复（含 G1 统一 cross 重置默认的微调）。实施 commit message 与验收记录中逐项标注 |
| config.json 兼容 | 旧配置（中文文本 key）经**历史别名表**（D5）恢复；新配置写稳定 key；别名表长期保留 |
| 双主题 | 拆分/合并出的每个 widget 保留 `setCustomStyleSheet` + `addStyleSheet(CustomStyleSheet(...))` 两步注册 |
| 折叠卡铁律 | 触碰契约 A 的改动逐条对照 AGENTS.md 六条铁律；`StyleSelectorCard._adjustViewSize` 覆盖模板不改写；验收不得只凭 `spaceWidget.h >= view.h`（见 §3 契约 A 补充） |
| 私有 API 原样 | `delegate.hScrollBar` 访问、`common.style_sheet` 深度导入只搬运不改写；升级 qfluentwidgets 版本不在本次范围 |
| 视觉现状保留 | 映射页按钮 QSS（未做 dark 适配）、各控件宽度约束（如 `combo_bg_fill` 200–260、标签列等宽逻辑）原样保留，不顺手"改进" |
| 改动纪律 | 正确性修复（T1/T2/T3）、清理（T4）、结构拆分（T6–T9）分 commit；每步可独立回退；**导出服务拆分（T8）搬运的必须是 G13 修复后的实现** |

## 7. 实施顺序（任务包）

v3 重排：正确性优先（D4），结构重构在后；G15 先于 G1（基线先修复后重构）。

| 任务包 | 内容 | 触碰契约 | 风险 |
|---|---|---|---|
| **T0 基线留存** | 源码指纹（HEAD + 未提交改动）；全部内置样式 YAML 原文存档；三层往返输出存档（源 → 模型 → 控件 → 模型，标注差异分类）；四张折叠卡 `dump_expand_card()` + 子控件几何存档；主窗口/样式编辑器 light+dark 截图存档 | 否 | — |
| **T1 正确性·导出** | G13（PNG 导出 + 扩展名契约） | 否 | 低 |
| **T2 正确性·样式数据完整性** | G14（引用保留与选项接线）+ G15（三处丢失）+ G16（decimals=4） | G14 触及契约 A（增删条目路径已有刷新机制） | 中 |
| **T3 正确性·定位编辑器布局** | G10（D2 三步：入布局 + D1 禁用 + 高度刷新） | 契约 A | 中（预期排版修复差异） |
| **T4 清理** | G4、G5、G6、G12；G11 按 v3 重定性处置（映射页守卫**保留**，仅清理 main_window 重复检查与实测确认后的冗余守卫） | 否 | 低（**不再是"零风险"，序列化隔离与删除项各有独立验收**） |
| **T5 稳定 key 化** | G3（含 Logo 哨兵 key 化 + D5 别名表迁移） | 否 | 低 |
| **T6 模型层统一** | G1 数据层（`PositionedSpec` + 单点序列化，吸收 G15 修复行为；`_build_yaml_config` 命名归位） | 否 | 中（机械对比验收，基线 = T2 后输出） |
| **T7 控件层合并** | G1 控件层（共享定位绑定层 + 各宿主保留自身网格）+ cross 重置规则统一 | 契约 A | 中 |
| **T8 页面拆分** | G2 + G7（含映射页初始化顺序统一） | 契约 B | 中 |
| **T9 收编与去样板** | G9（含加载格式契约）+ G8 | 否 | 低 |

依赖关系：T1 独立可先行；**T2 → T6 → T7 严格串行**（同一概念、同一批文件）；T3 独立但建议在 T7 前完成（T7 改动同一批控件，避免两次排版验收）；T4/T5 独立；T8 建议 T7 之后（拆分目标文件更小）；T9 随时可做（G8 的 spinbox 工厂建议在 T2 的 G16 之后，一次到位 decimals=4）。

## 8. 验收矩阵

| 验收项 | 适用任务包 | 通过标准 |
|---|---|---|
| `python -m py_compile` 全部改动文件 | 全部 | 零报错 |
| YAML 模型 round-trip 机械对比 | T2、T6 | 与基线 diff 为空（T2 基线 = T0 存档 + 预期修复差异清单；T6 基线 = T2 后输出）；差异逐项归因为"默认值补齐/省略"或"预期修复" |
| 真实控件 load/save 往返（14 内置样式 + 合成样本） | T2、T6、T7 | 引用（`defined_text_0X`）、`line_alignment`、实例字号、logo 未知键、0.1605 精度全部保留 |
| JPEG/PNG × 单张/批量导出 | T1、T8 | 正确格式发布；校验失败时旧目标保留、`.part` 清理；扩展名与源不符被拒绝 |
| 相机/镜头页首次构造、首次显示、再次显示 | T4、T8 | 无 `_table` 初始化异常，CSV 正确加载 |
| 两张列表卡 absolute→relative→absolute、初始加载 relative、多条目 | T3 | 两组均在布局内（`indexOf >= 0`）、相对字段完整可见可操作、无裁剪；卡片高度与 D1 策略一致 |
| `layout_debug.dump_expand_card()` + 子控件几何 | T3、T7 | 收起无底部间隙；展开滚动范围充足；**并检查子控件实际边界**（不能仅凭 space/view 不等式判通过——G10 故障态下该不等式仍成立） |
| 旧 config.json 恢复（含改文案场景） | T5 | 旧中文文本经别名表恢复正确 key；临时修改一处显示文案后恢复仍正确；新配置只存稳定 key |
| 序列化隔离 | T4 | 专用 Dumper 输出与基线字节一致；调用前后普通 `yaml.dump` representer 与输出不变 |
| 双主题切换 | T7、T8 | light/dark 各切一次，拆分/合并的 widget 样式均生效 |
| 布局交互 | T7、T8 | splitter 拖拽、窗口 resize、胶片栏滚轮横滚、缩略图动态缩放行为不变 |
| 功能冒烟 | T8 | 单张生成 + 单张导出（JPEG/PNG）+ 批量导出各一次；样式编辑器加载/编辑/保存一个真实样式 |
| 界面验证 | T3、T7、T8 | 按 AGENTS.md 合入门禁第 3 条实际启动 GUI 操作验证；`debug_log.txt` 无新增 ERROR |

## 附录 A：重复代码定位速查

实施时按此表逐项替换，防止漏项：

| # | 拷贝点 | 归并目标 |
|---|---|---|
| 1 | `ElementConfig` / `DefinedTextConfig` / `logo_*` / `custom_text_*` | `PositionedSpec`（G1/T6） |
| 2 | `to_yaml_dict` 绝对/相对分支 ×4、`from_yaml_dict` cross 默认规则 ×4 | `PositionedSpec.to_entry/from_entry`（含 G15 修复后的 line_alignment 与透传规则） |
| 3 | `ElementEditor.load_element/load_defined_text`、`save_element/save_defined_text` | 单对 `load_from/save_to` |
| 4 | `_on_relative_position_changed` ×3、`_sync_cross_options` ×3 | 共享函数（重置默认按 D 决策统一为序列化默认规则） |
| 5 | `fw_map`/`lens_map`/`ts_map`/`pos_map`/`col_map` + Logo 哨兵文本判断 | `addItem(userData=...)` + `currentData()`（G3/T5） |
| 6 | PIL→QImage ×4 | `utils` 图像转换 helper（G8） |
| 7 | `FilmStripWheelFilter` / `HorizontalWheelFilter` | 单一滚轮过滤器组件（G8） |
| 8 | 胶片栏尺寸计算 ×3 | FilmStrip 内部单一方法（G2/G8） |
| 9 | `_make_spinbox` ×5、`_add_spinbox_row` ×1 | 共享控件工厂（decimals=4，G8/G16） |
| 10 | 相机/镜头映射页 CRUD ×2 | `CsvMappingPage` 基类（含初始化顺序统一，G7/T8） |
| 11 | `_get_existing_styles` / `_resolve_style_filepath` | `StyleManager.list_style_files/resolve_style_file`（含格式契约，G9） |
| 12 | `_file_sha256` / `_export_verified` | 导出服务（**搬运 G13 修复后版本**，G2/T8） |

## 附录 B：审查链、核验记录与证据索引

**审查链。** v1 原审（本文档前一版）基于 `b3b375c` 静态审查；v2 复审基于 `b64388f`，以 Qt offscreen 探针验证 v1 关键论断并发现 R1–R7；v3（本版）对 v1/v2 逐项独立核验后合并修订。v2 的 R1–R7 经 v3 独立源码比对**全部确认属实**；v3 另有两点超出 v2 文本的增量：

1. v2 将 `fonts.sizes.defined_text_*` 与 `logo.max_dim_limit_ratio` 的往返消失笼统归入"语义字典变化（不全是缺陷）"；v3 核验证据 JSON 与 core 消费点（`text_renderer.py:286-292`、`renderer.py:402-404`）后确认这两类是**源有值、往返后消失的确定数据丢失**，已单列为 G15b/G15c；
2. v1 G10 的根因描述（hide 切换高度失配）被 v2 探针推翻、v3 源码复核确认（`element_editor.py` 的 `_setup_ui` 中 `rel_widget` 无 `layout.addWidget` 调用），D2 已按新根因重写。

**v3 独立核验方式。** 未运行 GUI，全部为源码逐点比对（行号均为 `8e50ced` 实测）+ 复算 v2 探针证据 JSON。核验要点：映射页初始化顺序（`camera_mapping_page.py:89-90/106/260-261/367-369`）、`rel_widget` 未入布局（`element_editor.py:167/170/247/255-256`）、`.part` 后缀误判（`image_processing_page.py:1295/1305-1306` 与 `output_metadata.py:746-760`）、`ELEMENT_KEYS` 无实例键与 `update_relative_to_options` 无调用点、`line_alignment` 相对分支读写双漏（`style_config_form.py:435-446/473-481/702-721/823-824`，对照 `STYLE_GUIDE.md`）、`sizes` 白名单（645-649）、logo 段无透传（754-792）、三编辑器布局与 cross 重置差异、`CONFIGS_DIR` 开发环境指向内置目录（`style_creator_page.py:78-82`）、StyleManager 四格式支持（`style_manager.py:124/186/271`）、`b64388f..HEAD` 的 GUI 零改动。

**证据文件。**

- 探针脚本：[`review_evidence/gui_report_reaudit.py`](./review_evidence/gui_report_reaudit.py)（Qt offscreen 真实控件 + 生产验证器；不使用 pytest/unittest 框架）；
- 运行证据：[`review_evidence/gui_report_reaudit.json`](./review_evidence/gui_report_reaudit.json)——含导出结果（JPEG 成功 / PNG 报错）、映射页守卫删除实验、四卡布局几何（`relative_layout_index=-1`）、Dumper 副作用前后对照、14 个内置样式三层往返逐字段差异、34 个源码 SHA-256 指纹（探针运行期间源码未变）；
- v2 复审文档：[`CODE_QUALITY_AUDIT_GUI_REVIEW.md`](./CODE_QUALITY_AUDIT_GUI_REVIEW.md)。

**尚未覆盖（留给实施任务的首个验证动作）。** 双主题截图比对、CLI 单张/批量渲染冒烟、打包验证在 v2/v3 均未执行，对应 §8 相关验收项在 T0 与各任务包中补做。
