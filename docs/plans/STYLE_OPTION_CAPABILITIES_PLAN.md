# GUI 选项随样式支持能力联动：评估与智能体执行方案

> 日期：2026-09-25  
> 状态：方案待实施；修订为可交接给其他智能体的执行任务书，本轮只修改文档。  
> 修订：v3，2026-09-25。已根据评审复核补齐加载器默认值、空样式持久化、单变体覆盖及 T5 独立门禁。§9–§15 为执行契约。  
> 核查基线：dev `c220897`；ParamCapsule 已随 `da87145` 提交。当前既有数据修改为相机/镜头 CSV，执行前仍须重新核查，不以旧行号定位。  
> 目标：右侧配置项随所选样式的全部变体调整可编辑性；保留用户输入，并说明不可用或暂不生效的原因。

评审参考：[STYLE_OPTION_CAPABILITIES_REVIEW.md](STYLE_OPTION_CAPABILITIES_REVIEW.md)。执行以本版契约为准；默认值注入造成的漏判方向、非法恢复名称的实际处理、未知条件的兜底行为均已按源码澄清。评审中的实现与 GUI 验证建议已转换为下文的具体任务和断言，不视为功能已验收。

## 1. 结论与复杂度

**需求可行，建议实施，完整方案复杂度为中等。** 当前架构已经提供样式选择事件、统一样式加载器、集中渲染文本入口，以及部分控件禁用逻辑，无需重构 GUI 或改写渲染算法。QFluentWidgets 具备所需接口，无需更换组件库或升级依赖。

主要难点不是调用 `setEnabled()`，而是准确识别所有变体支持的参数，处理组合字段，保持界面状态与生成参数一致，以及避免变体切换造成输入框无法再次启用。

| 工作包 | 复杂度 | 主要风险 |
| --- | --- | --- |
| 变体来源、匹配与能力分析 | 中 | 同名来源优先级、复合字段、损坏配置与能力漏判 |
| GUI 状态、刷新与参数收集 | 中 | 变体自锁、旧值丢失、信号循环、状态与渲染不一致 |
| 背景、字重及完整回归 | 中 | 颜色解析偏差、旧渲染行为回归、布局与焦点问题 |

本文面向执行智能体，不以人日作为执行预算。预计新增 3 个、修改 7 个生产代码文件，以及指南和验证记录；具体清单见 §10。按任务包逐项验收，不以“已改成灰色”作为完成标准。

固定交付范围：个性化四项、拍摄信息四项、背景填充、背景增强、字重全部纳入；输出格式、旋转适配、水印保持其独立语义。背景/字重不再是执行时自行决定的可选阶段。右栏布局重做、每样式独立偏好、能力 YAML 新字段、自动渲染与发行不在本次范围内。

## 2. 已核实的现状

| 位置 | 当前行为与影响 |
| --- | --- |
| `src/gui_pyside/pages/image_processing_page.py::_update_style_dependent_controls()` | 无上下文调用 `get_style_config()`，通常只拿到 default；只实际调整自定义文本和背景相关控件。计算了 `logo_enabled`，但没有调用 LOGO 控件的 `setEnabled()`。 |
| 同文件 `_create_personalization_card()` / `_create_shot_info_card()` | 控件均由 QFluentWidgets 构建，使用 `ExpandGroupSettingCard.addGroup()`；多数分组返回值未保存，补保存引用即可更新说明文案。 |
| 同文件 `_on_generate_frame()` | 直接读取文本、下拉值和开关状态构造 `RenderMetadata` / `RenderOptions`；控件禁用不会阻止其残留值进入渲染。 |
| 同文件 `_on_generate_frame()` / `save_config()` | 两处都存在 `current_style or "底部信息条 Bottom Bars"` 兜底；本次分别改成禁止无选择生成、保存真实名称或 null。 |
| 同文件 `_create_style_selection_card()` | 样式列表为空时会自动调用 create_sample_styles；本次移除 GUI 的自动创建调用，以保证无样式→保存→重启仍能真实表达空状态。 |
| 同文件初始化、配置恢复与 `refresh_style_list()` | UI 构建末尾已有一次状态刷新；恢复配置可能再触发。列表刷新本身没有统一重算能力，同名样式修改后可能保留旧状态。 |
| `src/gui_pyside/widgets/style_selector_card.py::refresh_styles()` | 恢复或自动选择样式不会发射 `style_selected`；列表为空时还可能保留旧的 `_current_style`。不能仅依赖用户点击事件刷新。 |
| `src/frame_styles/style_manager.py` | 支持 YAML/YML/JSON/TOML、单文件和目录变体；每个变体都是完整配置，不继承 default。尚无“全变体能力”接口。 |
| 同文件 `_validate_config()` | 会修改传入配置：缺少或非字典的 info_position 注入 exif/author/location；空字典不注入。能力必须基于校验后的结果。 |
| `src/core/image_processor.py::process()` | 按作者、地点、自定义文本、时间隐藏状态构建变体上下文，然后选择配置。 |
| `src/utils/render_context.py::get_text()` | `timestamp_author` 同时消费作者与时间；`camera_lens` 消费镜头显示模式；独立 `lens` 也消费短版镜头名。 |
| `src/core/text_renderer.py::render()` | `info_position` 按字段消费文本；`defined_texts` 是固定文字；专用 `layout.custom_text` 需要 `enabled: true`。 |

`ProcessingConfig` 虽然声明了相关字段，但当前生成路径直接读取控件并构造渲染参数。因此只修改此 dataclass 不会完成联动或过滤。

仓库指引中的 GUI 重构文档现实际位于 `docs/docs_legacy/GUI_REFACTORING_PLAN.md`。继续遵守其 QFluentWidgets 组件约定；其中“核心层完全不修改”属于旧重构范围，本方案需要在现有 StyleManager 上增加查询能力，不改变渲染结果规则。

### 2.1 真实样式对照

以下覆盖本次基线的全部 8 个内置样式，结果基于 StyleManager 加载并校验后的配置。“支持”表示全变体并集，不表示每个变体都显示。

| 样式 | 作者 / 地点 | 自定义文本 | 时间 | 镜头模式 / 短名 | LOGO | 关键差异 |
| --- | --- | --- | --- | --- | --- | --- |
| 信息卡片 InfoCard | 支持 / 支持 | 不支持 | 不支持 | 不支持 / 支持 | 不支持 | 使用独立 `camera`、`lens`；不能把“存在镜头文字”等同于支持镜头显示模式。 |
| 胶片夹风格 FilmClip | 不支持 / 不支持 | 支持 | 不支持 | 支持 / 支持 | 支持 | default 启用自定义文本、关闭 LOGO；`no_custom_text` 关闭自定义文本、启用 LOGO。 |
| 参数胶囊 ParamCapsule | 不支持 / 不支持 | 支持 | 不支持 | 支持 / 支持 | 不支持 | `camera_lens` 只在 `no_custom_text` 中出现；只读 default 会漏判镜头选项。 |
| 底部信息条 Bottom Bars | 支持 / 支持 | 不支持 | 支持 | 支持 / 支持 | 支持 | 作者通过 `timestamp_author` 表达，不能仅查 `author` key。 |
| 宝丽来风格 Polaroid | 支持 / 支持 | 不支持 | 支持 | 支持 / 支持 | 不支持 | 同样依赖 `timestamp_author`。 |
| 裁剪胶片 FilmCut | 支持 / 支持 | 不支持 | 支持 | 支持 / 支持 | 支持 | 配置了固定背景色，背景选项需保留现有约束。 |
| 简洁信息 SimpleInfo | 支持 / 支持 | 不支持 | 支持 | 支持 / 支持 | 支持 | 仅 default；作者来自 timestamp_author，设备信息来自 camera_lens。 |
| 边框信息条 FrameBar | 支持 / 支持 | 不支持 | 支持 | 支持 / 支持 | 不支持 | 仅 default；作者来自 timestamp_author，设备信息来自 camera_lens。 |

SimpleInfo、FrameBar、Polaroid、FilmCut 均为仅含 default 的目录样式。它们的家族能力与该变体能力相同，不应出现 other_variant_only；背景锁定、短名依赖等局部禁用仍可出现。

## 3. 交互规则

### 3.1 样式能力与当前生效状态分开

**默认以整个样式的全部有效变体的能力并集决定能否编辑，以当前命中变体决定提示是否生效。**

- 全变体均不支持：控件保持可见，禁用编辑或选择，说明“当前样式不支持”。
- 至少一个变体支持且当前变体也支持：正常可用。
- 至少一个变体支持，但当前变体不支持：仍可编辑，说明“部分布局支持”；可在完整提示中写“当前布局未使用此项”。
- 缺少照片、EXIF 或品牌数据：不等于样式不支持，优先说明数据条件，不把所有预设入口锁死。
- 输入框变灰时保留原值；切回支持的样式后恢复编辑。不自动清空作者、地点、文本或取消用户开关。
- 保留卡片展开按钮和说明文字可用，不禁用整个 `ExpandGroupSettingCard`。

例如 FilmClip 初始自定义文本为空会命中 `no_custom_text`。若按当前变体禁用输入框，用户永远无法输入文本切回 default。因此不能使用“当前变体不画此字段 → 禁用输入框”的单层规则。LOGO 即使当前未显示，也可保留选择，提示其在部分布局生效。

本方案不新增“每个样式记忆一套用户值”；沿用当前共享输入与已有配置持久化行为，避免扩大范围。

### 3.2 参数支持规则

下表中的“存在字段”指有效配置中的实际 `layout.info_position` 消费项；不能通过搜索 YAML 文本、字体/颜色 key 或固定文字内容判断支持。

| GUI 选项 | 单个变体支持条件 | 额外说明 |
| --- | --- | --- |
| 作者姓名 | 存在 `author` 或 `timestamp_author` | 时间设为隐藏后，`timestamp_author` 仍可单独显示作者。 |
| 拍摄地点 | 存在 `location` | `gps` 是 EXIF 坐标的独立字段，不能据此认定手工地点有效。 |
| GPS 替换 | 支持 `location` 输入 | 此开关把 GPS 送入 location，不能控制直接显示的 `gps` 字段。 |
| 自定义文本 | `layout.custom_text.enabled` 为真 | 兼容现有运行时可消费的 `info_position.custom_text`，但它不是当前指南主推配置方式，应附兼容诊断，避免静默误判。 |
| 拍摄时间 | 存在 `timestamp` 或 `timestamp_author` | 没有 EXIF 时间只影响显示，不影响用户选择隐藏模式。 |
| 镜头显示模式 | 存在 `camera_lens` | 只有独立 `camera` / `lens` 时，此三选项无效。 |
| 短版镜头名 | 存在 `lens` 或 `camera_lens` | 若全变体只有 `camera_lens`，且用户选择只显示相机，可暂时禁用；存在独立 `lens` 时仍可用。 |
| LOGO | `logo.enabled` 为真 | 不能从 assets 中存在 LOGO 或相机品牌字段推断支持。 |
| 背景填充 | 当前变体没有可成功解析的固定背景色 | 与渲染器使用相同解析器，不能只看字段非空。 |
| 背景增强 | 当前实际背景类型使用高斯背景 | 通过 BackgroundFillManager 注册表查询，不硬编码背景名称；不要把矩形自身磨砂效果误认为此开关控制。 |
| 字重 | 至少一个变体消费受全局字重影响的文字 | 包括固定文字；不能仅以作者/地点缺失禁用。字体是否有某个文件不是样式能力。 |
| 输出格式、旋转适配、水印 | 独立于样式文本能力 | 不因缺少 `custom_text` 或 LOGO 禁用；水印是独立装饰功能。 |

`info_position` 当前没有统一的 `enabled` 消费逻辑，不应自行假定 `info_position.author.enabled: false` 会停止渲染。分析器需遵守真实渲染语义；专用 custom_text 与 logo 的 enabled 才有既定含义。

### 3.3 GPS 与字段依赖

- 无 `location` 显示或变体控制能力时，禁用地点及 GPS 替换，并在生成时不应用 GPS 替换。
- 支持地点时，即使当前照片无 GPS，仍可预设开关；提示“无 GPS 时使用手工地点”，保留现有回退逻辑。
- 当 GPS 已启用且当前照片有坐标时，保留手工地点可编辑，说明“当前使用 GPS，手工地点作备用”。这是备用输入，不是无效输入。
- 切换照片后刷新 GPS 提示，不把上一张照片的坐标或能力结论带入下一张。

### 3.4 只影响变体选择的参数

现有命名规则允许 `no_author` 等条件，即使该字段未被任何文本节点显示，它也可能影响布局选择。此情况应区分 `display_support` 与 `variant_control_support`：

- GUI 的变体控制条件限于当前处理器提供的四项：author、location、custom_text、timestamp；通用匹配器仍保留现有任意上下文字段匹配语义。
- 某参数只用于选择变体时，保持可编辑，提示“用于切换布局”；不能因为不直接绘制就过滤掉。
- 条件来源单独记录，不能把任意文件名或未知 `no_xxx` 都算成显示支持。
- 非规范名称、同等匹配优先级、缺少 default 等情况记录诊断；沿用当前解析顺序，不在本任务中静默改变变体排序。

未知条件如 no_iso 不会通过当前 ImageProcessor 的四字段上下文匹配；但无匹配且无 default 时，它仍可能作为第一个文件被兜底选中。不能删去未知候选，也不能把它描述为“永远不会使用”。若通用调用者显式传入 iso=None，既有匹配器仍应允许条件命中。

这项防护兼容用户自建样式，避免参数过滤改变原本有效的布局切换。

## 4. 实现结构

```text
StyleManager：确定样式来源，枚举并加载变体，复用变体选择规则
    ↓
能力分析：逐变体消费字段 + 条件字段 → 样式能力并集及来源
    ↓
页面：共享输入 + 当前照片 → 有效元数据 → 当前变体 → 控件状态/提示
    ↓
同一份有效元数据 → RenderMetadata / RenderOptions → 现有处理器
```

### 4.1 样式加载层

在 StyleManager 增加公开的变体快照查询接口，纯计算放在新增的 `src/frame_styles/style_capabilities.py`。本节接口描述为架构概览，最终命名和签名统一以 §9 为准：

| 接口或结构 | 职责 |
| --- | --- |
| `StyleManager.get_style_snapshot(style_name)` | 返回完整候选、实际来源、能力并集和加载诊断，兼容单文件。 |
| `analyze_style_capabilities(candidates, source_kind)` | 返回不可变能力结果：支持选项、条件输入及诊断；不接触 Qt。 |
| `evaluate_style_options(snapshot, raw, gps_text, background_method)` | 根据快照和当前输入一次性计算控件状态、有效参数与当前变体。 |
| `build_style_variant_context(...)` | 从渲染元数据构造上下文，供 GUI 提示与 ImageProcessor 共用。 |

必须与现有 `get_style_config()` 使用相同的样式来源选择。当前实现是“目录样式优先，再查单文件；各自用户目录优先”，并不完全等同于跨类型无条件用户覆盖。特别是“用户单文件与内置同名目录”这一组合，能力查询必须与真正加载结果一致。可提取共用来源定位助手；修正覆盖优先级是另一项兼容行为变更，不应顺带实施。

只聚合实际选中来源中的变体，禁止把用户目录样式与已被遮蔽的内置同名样式混为一体。扩展名、校验和异常处理复用现有加载器。新增路径继续遵守 `app_paths.py`，GUI 不自行拼资源目录。

所有配置都无效、样式不存在或没有选择时，返回明确的不可用状态并清除旧能力。部分变体失效时只从有效配置聚合显示能力；条件输入仍保留实际候选文件名提供的合法条件，以便用户切换离开损坏变体。若实际选择命中无效变体，只阻止本次生成，保留已知可编辑入口，不静默换成别的变体。具体状态优先级见 §11。

#### 4.1.1 校验后的配置才是能力依据

固定数据流为“解析文件 → 既有 `_validate_config()` 注入/校验 → 提取 VariantFacts”，渲染加载和能力加载都经 `_load_config_file()`。不得直接读取原始 YAML 推断能力，也不得在提取 facts 前另设严格校验，拒绝既有加载器会归一化的字段。

| 原配置 layout.info_position | 既有校验后的实际字段 | 作者/地点能力 |
| --- | --- | --- |
| 字段缺失 | exif、author、location | 均支持 |
| null 或其他非字典值 | exif、author、location | 均支持 |
| 显式空字典 `{}` | 空字典，不注入 | 若无其他消费或条件控制则不支持 |
| 有效字典 | 保留现有条目，不补齐其他字段 | 按实际条目分析 |

忽略此规则会把真实支持作者/地点的缺省配置误判为“不支持”。colors/fonts 的默认注入也必须先于 facts 提取；仅在既有加载器处理完毕后仍有无法分析的结构异常，才按 §9.4 标记候选不可用。C06/C07/C08 等“没有动态文本”的测试夹具必须显式写 `info_position: {}`，不能用省略字段代替。

### 4.2 能力与选择结果不要共用可变配置缓存

在样式切换、进入页面、编辑后刷新时重建小型能力快照，不增加后台线程或持久缓存。当前工作区最大样式只有 4 个配置文件；实际响应耗时应在实施阶段测量并记录。

文本输入时只使用页面当前持有的快照计算能力和状态，避免每个字符重新加载全部文件。本次不添加管理器级缓存；每次规定的重载事件都替换快照，不按样式名称长期复用旧结果。

ImageProcessor 会修改加载到的 `fonts.weight`。能力快照应不可变，或与渲染配置独立复制，不能把一份可变字典同时交给 UI 和渲染器。变体名称解析和匹配逻辑保持单一来源，避免 GUI 复制出第二套匹配算法。

### 4.3 界面状态集中更新

保留 `_update_style_dependent_controls()` 作为统一入口，内部按“能力 → 依赖 → 控件与文案”顺序计算。保存作者、地点、自定义文本、时间、镜头与 LOGO 的 GroupWidget 引用，统一设置简短说明和完整 tooltip。

需要覆盖的刷新时机：

1. 所有控件创建完成、所有已保存配置恢复完成后，统一重算一次。
2. 用户切换样式。
3. 同名样式重新保存、返回图片处理页、列表刷新、当前样式被删除或列表变空。
4. 作者、地点、自定义文本、时间模式变化：重算当前变体提示；可用 QTimer 合并连续输入事件，不触发图像渲染。
5. GPS、镜头模式、背景类型变化，以及当前照片切换或删除：刷新相应依赖。
6. 点击生成前重新核查样式状态，防止外部修改后仍使用旧能力。

配置恢复期间允许用恢复标记抑制中间刷新，最后显式刷新。状态刷新不调用 `setText('')`、不重置下拉选项、不保存 config、不自动生成图片。若确需程序性改值，使用信号阻断并确保恢复原信号状态。

### 4.4 控件值、有效参数与变体选择

**禁用只限制交互，并不会清空值。** 使用统一的 `_read_raw_option_values()` → `evaluate_style_options()` 出口，由生成流程和当前变体提示共用：

1. 读取并保留全部用户原值。
2. 依据“全变体显示支持或变体控制支持”过滤：完全无关的 author/location/custom_text 传 `None`，GPS 替换仅在地点输入受支持时应用。
3. 对完全无关的时间、镜头模式、短名使用现有默认语义；不要把“禁用时间”自动转换成 hide，以免误触发 `no_timestamp`。
4. 用有效元数据构造变体上下文，解析当前变体。当前实现中，时间条件只在用户选择 hide 时标记缺失，不因为照片没有 EXIF 时间就自动标记；共享助手必须保持此行为。
5. 对仅在其他变体支持的参数保留用户选择，不再按当前变体过滤第二次，避免反馈循环。渲染器继续按实际配置消费。
6. 全样式无 LOGO 支持时跳过 GUI 自动匹配并传“无 LOGO”的既有值；支持时保留选择，并由实际变体的 enabled 决定是否绘制。
7. 保存用户偏好时保存原始输入，不把为本次生成过滤后的空值写回控件或配置文件。

提取 ImageProcessor 的上下文构造助手供 GUI 复用，不把 GUI 禁用策略强加给 CLI；CLI 仍按既有参数与样式规则运行。提取助手后需要单张和批量 CLI 回归。

## 5. QFluentWidgets 适配与官方 API 核查

本机实际版本：**PySide6-Fluent-Widgets 1.11.2 / PySide6 6.11.1**。官方在线文档的部分类签名基于 PyQt5，因此同时核对了本地 PySide6 包实现，并运行了一次离屏 API 探针。

| 需求 | 使用方式 | 约束 |
| --- | --- | --- |
| 禁用编辑或选择 | 对 Fluent `LineEdit` / `ComboBox` / `SwitchButton` 调用继承的 `setEnabled(False)` | 保留值；禁用对象是交互控件，行与卡片保持启用。Qt 官方说明禁用父控件会影响子控件。[Qt QWidget](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html#PySide6.QtWidgets.QWidget.setEnabled) |
| 显示原因 | 保存 `addGroup()` 返回的 GroupWidget，并调用 `setContent()` | 官方接口已支持；完整说明放 tooltip，短文案避免撑宽右栏。[分组设置卡 API](https://pyqt-fluent-widgets.readthedocs.io/zh-cn/latest/autoapi/qfluentwidgets/components/settings/expand_setting_card/index.html) |
| 单独禁用下拉选项 | `ComboBox.setItemEnabled(index, bool)` | 初版以整个选项控件为粒度即可；未来细化时使用 Fluent 接口，不套用原生 QComboBox 的 model/item 操作。[ComboBox API](https://pyqt-fluent-widgets.readthedocs.io/zh-cn/latest/autoapi/qfluentwidgets/components/widgets/combo_box/index.html) |
| 输入框行为 | 使用现有 Fluent LineEdit | 推荐 disabled 表达不支持；若将来要求能复制但不能编辑，再单独设计只读交互。[LineEdit API](https://pyqt-fluent-widgets.readthedocs.io/zh-cn/latest/autoapi/qfluentwidgets/components/widgets/line_edit/index.html) |
| 开关依赖 | SwitchButton 的 `checkedChanged` 与 `setEnabled()` | 禁用不等于取消勾选，参数收集时仍须判定能力。[SwitchButton API](https://pyqt-fluent-widgets.readthedocs.io/zh-cn/latest/autoapi/qfluentwidgets/components/widgets/switch_button/index.html) |
| 避免信号递归 | Qt `QSignalBlocker` | 属于信号管理工具，不是替换 Fluent 界面组件。[QSignalBlocker](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QSignalBlocker.html) |

组件清单亦已参照：[QFluentWidgets 官方组件列表](https://qfluentwidgets.com/zh/pages/componentlist/)。该页面本次网页工具未提取到正文，具体接口结论以官方 API 页和本地包为准。

离屏探针已通过：禁用输入保留文字且不触发 textChanged；禁用开关保留勾选；GroupWidget 描述可更新；行与展开按钮仍启用；单项禁用接口存在且有效；QSignalBlocker 能抑制程序性选项切换信号。**这不是完整 GUI 视觉验收**，浅色/深色主题、键盘焦点与禁用后菜单行为仍需实际窗口操作确认。

布局沿用 addGroup/addGroupWidget，禁止直接向 viewLayout 塞控件。仅改变 enabled 不需要重建布局或新增高度覆盖；若动态改变内容高度、增加行，再调用延迟 `_adjustViewSize()`。保留简短非空说明，避免频繁显隐引发布局抖动。实施完成仍须按项目规定调用 `layout_debug.dump_expand_card()` 检查展开/收起尺寸。

不依赖禁用控件能否触发 tooltip 来解释原因：GroupWidget 本身保持启用，并显示说明。避免每次输入或切换样式弹出 InfoBar。

## 6. 实施拆分与修改文件

| 阶段 | 修改位置 | 完成标准 |
| --- | --- | --- |
| A：能力层 | `style_manager.py`；新增 `style_capabilities.py` | 单文件/目录/多格式/实际来源一致；全变体并集与条件输入正确；无效配置有诊断。 |
| B：共享上下文与参数出口 | `image_processor.py`；能力模块或单独纯函数模块；`image_processing_page.py` | GUI 提示与生成使用同一份有效元数据，保持现有变体上下文语义。 |
| C：GUI 联动 | `image_processing_page.py`；必要时 `style_selector_card.py` | 个性化、拍摄信息与 LOGO 联动，保值、提示、初始化/刷新/删除/空列表均正确。 |
| D：背景/字重精细化 | 页面、能力层、背景颜色解析工具 | 复用既有颜色解析结果再锁定背景；增强依赖实际背景；不误伤固定文字与独立装饰。本次必须完成。 |
| E：验证与说明 | `docs/STYLE_GUIDE.md`、本文实施记录 | 指南解释全变体能力，不让样式作者重复手填一套 GUI 开关。通过下节验收后才合入版本。 |

不推荐新增必须填写的 YAML `capabilities` 清单：已有布局声明足够推导，重复声明容易与真实渲染脱节。今后若引入不能自动推导的新消费方式，再讨论可选覆盖字段和校验规则。

执行顺序与逐文件验收以 §10 为准，A–E 全部在本次交付范围内。用户要求的作者、地点、自定义文本，以及同类的时间、镜头、LOGO 一并覆盖；背景和字重按限定规则实现，不延伸到像素级可见性分析。

## 7. 验收清单与风险控制

项目没有测试框架，不运行 pytest 或 unittest。实现阶段可使用临时断言脚本、CLI 实测和实际 GUI 操作，不引入新框架。

| 场景 | 预期结果 |
| --- | --- |
| 只有非 default 变体支持某参数 | 并集检测为支持；输入入口仍可用。使用 ParamCapsule 镜头字段与 FilmClip LOGO 验证。 |
| FilmClip 自定义文本从空 → 有 → 空 | 始终能输入；变体与提示切换正常；无自锁，无反复切换。 |
| InfoCard 作者/地点四种空值组合 | 按现有解析器切换四个布局；不能因当前布局移除了字段而锁死输入。 |
| Bottom Bars 的 timestamp_author | 作者可编辑；隐藏时间后作者仍可出现；没有作者时日期仍可显示。 |
| InfoCard 独立 camera/lens | 镜头模式禁用，短名可用；“只显示相机”的旧残留值不影响独立 lens。 |
| GPS 有/无、切换照片、直接 gps 字段 | 地点替换与备用值准确；只有 gps 字段的样式不会错误启用手工地点替换。 |
| 支持样式 A → 不支持 B → A | 作者、地点、文本、下拉值与开关原值保留；B 不消费无关残留值。 |
| 仅作 no_author 等变体条件 | 字段可控制布局且不会被过滤，说明与直接显示支持有所区分。 |
| 首次启动、配置恢复、同名保存后返回 | 所有控件状态及时重算，恢复不触发渲染或覆盖用户值。 |
| 当前样式删除、全部样式为空 | 不保留上一个样式的能力/选中名；生成入口给出明确不可用状态。 |
| JSON/YML/TOML、用户与内置同名 | 能力与处理器加载同一来源，不误合并被覆盖配置；单文件视为一个变体。 |
| 非法或部分损坏变体、未知字段 | 明确诊断；不延用旧状态、不崩溃、不静默绕过当前配置错误。 |
| 背景固定色与无效色 | 解析成功的固定色禁用背景设置；解析失败不能误判为有效锁定。另测纯色/高斯切换与增强。颜色解析兼容边界见 §10。 |
| 键盘与鼠标 | 禁用项不能输入/点击/切换；Tab 焦点合理，打开下拉菜单时切换状态无残留交互。 |
| 浅色/深色、窄右栏、卡片展开/收起 | 禁用外观清晰、提示可读；无新增横向溢出，dump_expand_card 符合项目约定。 |
| CLI 单张 + 批量 | 若提取共享上下文，结果与变体选择保持一致；GUI 策略不改变 CLI 原有规则。 |

实施完成后，对所有新增/修改 `.py` 在激活 venv 后执行 `python -m py_compile <各文件绝对路径>`；检查本次运行新增的 debug_log ERROR/TRACEBACK。日志记录样式、变体、能力集合及状态原因，不额外记录作者姓名、地点、自定义文本内容。异常配置用例允许产生预期诊断，应与正常路径错误分开检查。

只有涉及打包路径、资源或依赖变动时才执行打包冒烟；普通状态联动无需扩大到全量发行工作。开发和验证均留在 dev；所有门禁通过后再按 release_sync 流程合入 mainline、赋版本，不在本方案阶段改版本或 tag。

## 8. 本轮评估的验证边界

已完成源代码追踪、现有样式全变体配置加载校验、官方 API 查阅、本机依赖版本确认及离屏控件 API 断言验证。未实施能力分析器、未启动完整应用做人工 GUI 验收、未实测新方案的渲染输出或性能。

本轮仅新增/修订 Markdown 文档，无新增或修改 `.py` 文件，因此没有适用的 py_compile 目标。以下接口与行为是供执行智能体实现的契约，尚未成为功能代码，也不代表已通过合入门禁。

## 9. 执行契约：数据结构、公共接口与依赖方向

本节名称固定，执行者不要在 GUI 再写一套样式解析器。可以调整私有函数拆分，但不得改变以下输入输出含义。以下是接口规格，不是要求原样粘贴的实现代码；新增代码须按 AGENTS.md 保留中文说明和边界注释。

### 9.1 模块依赖

```text
utils/color_utils.py                    utils/render_context.py
          ↓                                      ↓
frame_styles/style_capabilities.py ← 字段到用户选项的依赖常量
          ↑
frame_styles/style_manager.py ← 文件来源与加载
          ↓
gui_pyside/models/style_option_state.py ← 纯数据与状态计算，无 Qt import
          ↓
gui_pyside/pages/image_processing_page.py ← 控件、信号、参数对象构造

core/image_processor.py → 复用 build_style_variant_context()
core/renderer.py → 复用 color_utils.parse_hex_or_rgb()
```

能力模块不得 import GUI、ImageProcessor 或 FrameRenderer；GUI 纯状态模块不得实例化 QWidget、写配置、读文件或发起渲染。

### 9.2 固定选项标识

使用稳定字符串，不使用中文显示名作判断：

`author`、`location`、`use_gps_location`、`custom_text`、`timestamp_display_mode`、`lens_display_mode`、`use_short_lens`、`logo_selection`、`bg_fill_type`、`enhance_background`、`font_weight`。

变体条件名与选项名分开映射：`timestamp` → `timestamp_display_mode`；`author/location/custom_text` → 同名选项。GPS 是 location 输入来源，不是第五种变体条件。

### 9.3 能力层数据对象

在 `style_capabilities.py` 定义以下对象，优先使用 frozen dataclass、tuple、frozenset。frozen dataclass 并不会冻结内部 dict，不能借此宣称嵌套字典不可变。

| 对象 | 必须包含的字段 | 契约 |
| --- | --- | --- |
| `VariantFacts` | `info_keys`、`display_options`、`custom_text_enabled`、`logo_enabled`、`has_weighted_text`、`fixed_background_rgb`、`diagnostics` | 从单份有效配置提取；不保存可被渲染器改写的完整配置字典。`fixed_background_rgb` 为 RGB tuple 或 None。 |
| `VariantCandidate` | `path`、`filename`、`required_missing`、`is_default`、`facts`、`diagnostics` | path 为实际来源中的绝对路径；加载失败时 facts=None，候选仍保留，以免改变匹配结果。 |
| `StyleCapabilities` | `display_options`、`control_options`、`has_weighted_text`、`has_independent_lens`、`diagnostics` | 前两项各自为 frozenset；显示能力只聚合 facts 有效的候选；来源说明从候选列表追溯。 |
| `StyleSnapshot` | `style_name`、`source_path`、`source_kind`、`candidates`、`capabilities`、`status`、`diagnostics` | source_kind 为 directory/single_file/none；candidates 保留原枚举顺序；status 为 ready/partial/invalid/missing/empty。 |

状态定义：所有候选有效为 ready；有效/无效混合为 partial；有候选但无有效配置为 invalid；名称无对应来源为 missing；目录无候选或未选择为 empty。诊断使用 code/path/detail；detail 描述配置问题，不带用户输入内容。

`info_keys` 仅含 RenderContext 认识、且节点结构可供渲染的字段。未知字段记录诊断，不视为任何个性化选项的支持，也不据此启用字重。输入已经通过既有加载器归一化；只有归一化后仍存在的非字典容器等异常才标记候选不可用，GUI 不继续生成该候选。不得拒绝会被加载器正常注入默认值的原始 info_position/colors/fonts，也不要将这些防护改成全仓库 schema 重写。

### 9.4 公共接口签名与副作用

| 位置与接口 | 输入 → 输出 | 约束 |
| --- | --- | --- |
| `style_capabilities.parse_variant_missing_fields(filename)` | str → frozenset[str] | 从现有内嵌 parse_missing_set 原样提取；保留 custom_text 复合字段、no 分隔、大小写规则。通用解析不做四字段白名单过滤。 |
| `style_capabilities.select_variant_candidate(candidates, context)` | 顺序候选 + dict/None → 候选/None | 缺失条件子集匹配、更多字段优先、同分保留先遇到者；其次第一个 default；最后第一个候选。无文件 I/O。无效候选也参与选中，之后再报告失败。 |
| `style_capabilities.build_style_variant_context(*, author, location, custom_text, timestamp_display_mode)` | 四个标量 → dict | 总含 author/location；custom_text 假值时加入 None，非空时不加入；时间 hide 时加入 timestamp=None，其余不加入。不要 strip 用户文本，也不要根据 EXIF 推导时间缺失。 |
| `style_capabilities.analyze_variant_config(config)` | 已加载配置 → VariantFacts | 纯计算；复用字段依赖常量与公共颜色解析。不可分析的结构异常抛带字段路径的 ValueError，由 manager 转换为候选诊断和 facts=None；未知字段等非阻断信息放 facts.diagnostics。 |
| `style_capabilities.analyze_style_capabilities(candidates, source_kind)` | 候选 → StyleCapabilities | 单文件名不解释为 no_x 条件；目录中合法条件可形成 control_options。 |
| `StyleManager.get_style_snapshot(style_name)` | str/None → StyleSnapshot | 同步扫描一次当前来源，逐候选校验；无缓存、无配置写入。 |
| `style_option_state.evaluate_style_options(snapshot, raw, gps_text, background_method)` | 快照 + 原值 + 当前 GPS + 所选背景类型的方法 → OptionEvaluation | 不访问控件；无文件读取；一次性得到有效值、当前变体、所有控件状态、是否可生成。 |

`background_method` 是通过 BackgroundFillManager 查询所得的选中背景方法，纯状态函数再根据当前变体固定色覆盖判定；不要让模型直接修改 FILL_TYPES 或调用注册自定义背景的方法。

StyleManager 增加私有来源枚举助手，供 `get_style_config()`、`_resolve_style_variant()` 和 `get_style_snapshot()` 共用；具体拆分可按现有结构调整。**get_style_config 仍只加载选中的一个配置，不得为了新 UI 能力变成每张照片加载全部变体。** 快照是页面专用查询，渲染不复用它的配置对象。

匹配只调用同一个 select_variant_candidate；生成当前变体诊断时复用候选 path，不能凭文件名重新猜测。保留 `_resolve_style_variant(style_dir, context)` 现有入口作为适配层，避免顺带破坏内部调用或已有脚本。

### 9.5 字段依赖常量

在 `render_context.py` 的模块层新增 `TEXT_OPTION_DEPENDENCIES`，给每个已支持的 get_text key 注册它消费的选项。它是能力判定的声明来源，本次不改 get_text 分支行为。

| get_text 字段 | 消费选项 |
| --- | --- |
| author | author |
| location | location |
| custom_text | custom_text |
| timestamp | timestamp_display_mode |
| timestamp_author | author、timestamp_display_mode |
| camera_lens | lens_display_mode、use_short_lens |
| lens | use_short_lens |
| exif、camera、camera_make、gps、focal_length_formatted、aperture_formatted、shutter_speed_formatted、iso_formatted | 空集合，仍为可绘制且受字重影响的文字 |

注册表值用 frozenset。说明新增 get_text 字段时同步登记依赖；用临时断言覆盖组合字段映射，防止后续遗漏。字体颜色、fonts.sizes、defined_texts 中的 key 都不是用户输入依赖来源。

### 9.6 GUI 纯状态模型

在 `src/gui_pyside/models/style_option_state.py` 定义：

- `RawOptionValues`：保存 §9.2 的 11 项原始选择；作者/地点/文本为空时可用空字符串，枚举使用内部稳定值。
- `EffectiveOptionValues`：同样的选项，但不支持的值按 §11.2 归一化；额外保存实际 location。不得回写 RawOptionValues。
- `OptionState`：`enabled`、`reason_code`、`content`、`tooltip`。控件启用状态不能反过来作为业务能力来源。
- `OptionEvaluation`：`effective_values`、`active_variant_path`、`active_variant_valid`、`states`、`can_render_style`、`diagnostics`。每次必须覆盖全部 11 项，不能只返回有变化的部分。

初始化、照片为空和异常分支都要生成完整结果。can_render_style 只判断样式可生成；页面再与“当前选中照片有效”合并，不能混淆两种状态。

## 10. 逐文件执行任务

### T0：记录基线与保护工作区

1. 在 venv 中执行 git status，记录分支与 HEAD，阅读当时有效的 AGENTS.md。
2. 核对本文列出的函数、依赖版本和样式是否仍存在；按函数名定位，不按本文评估时行号改文件。
3. 本次基线中既有用户修改为 data/camera_map.csv、data/lens_map.csv；ParamCapsule、AGENTS.md、缩略图及 FilmClip Frost 删除已入库。方案与评审文档目前为未跟踪文件。执行者仍以启动时 git status 为准，保护届时所有既有修改，不恢复、不清理、不自动纳入提交。
4. 记录 debug_log 起始文件大小或时间；准备独立临时目录存放验证输出。严禁用 reset --hard、清理用户未跟踪文件或覆盖 config.json 来制造干净环境。
5. 在修改生产代码之前，按 §13.3 保存固定输入的 CLI 基线输出、关键参数、选中变体和颜色解析结果。不要到实现结束后才发现无法做前后比较。

完成证据：验证记录写明 HEAD、工作区基线与依赖版本。若执行时基线已变，先适配真实代码；只有产品规则与新实现冲突时才向用户提问。

### T1：共享颜色解析与背景类型查询

文件：新增 `src/utils/color_utils.py`；修改 `src/core/renderer.py`、`src/utils/background_fill.py`。

1. 将 renderer._parse_hex_or_rgb 的函数体原样迁入公共 `parse_hex_or_rgb(value)`；原私有函数保留为带说明的薄包装，以保持内部/外部引用兼容。
2. 能力分析调用公共函数，渲染器仍通过包装调用同一函数。本任务不收紧颜色语法，不增加范围截断，不修改 RGB 转换行为。
3. 在 BackgroundFillManager 增加只读 `get_fill_method(fill_type) -> Optional[str]`，返回注册项的 method；未知键返回 None，由 GUI 原值收集回退 DEFAULT_FILL 后再查询。

特别注意：现有颜色解析器对长度、尾部字符、通道范围的校验较宽松。本文“颜色有效”仅指与现有解析器的成功/失败结果一致，不代表此次补全颜色验证。为修正这一历史问题改变颜色语义需另立任务，避免 GUI 功能夹带渲染变化。

完成证据：迁移前后对 None、空字符串、标准 HEX、解析失败字符串、三元列表/元组、非三元列表，以及现有宽松边界输入的结果一致；对每个现有背景注册项查询结果正确。这里只需临时断言，不改渲染样式文件。

### T2：能力数据与字段映射

文件：新增 `src/frame_styles/style_capabilities.py`；修改 `src/utils/render_context.py`。

1. 实现 §9 的数据结构、纯解析/选择/上下文函数与字段映射。
2. 按 §3.2 推导 display_options；GPS 能力由 location 显示或条件支持派生，不由直接 gps 字段派生。
3. 字重支持为：至少一个已知 info_position 字段，或非空固定文字，或启用的专用 custom_text。custom_text 当前为空不影响能力；只有字体配置而无文字消费节点不算支持。
4. `has_independent_lens` 判断所有有效候选的 info_keys 是否含 lens；不能只看当前候选。
5. control_options 从目录候选的非空 required_missing 推导；仅当整组条件均属于 author/location/custom_text/timestamp 时纳入 GUI 控制。未知条件只诊断，通用解析器仍照旧处理。
6. 显示支持只统计有效候选；条件支持包含可解析名称的损坏候选，以保留逃离错误变体的入口。全部候选损坏时则进入整体 invalid 状态，能力入口禁用。

完成证据：最小配置字典断言覆盖组合字段、专用 custom_text、兼容 info_position.custom_text、独立 gps、固定文字、未知字段、条件专用输入、损坏候选。更复杂结构不能直接调用 `.get()` 假设类型正确。

### T3：StyleManager 接入与变体匹配保持兼容

文件：修改 `src/frame_styles/style_manager.py`。

1. 抽出实际来源与候选路径枚举；保留目录优先、用户目录优先以及单文件扩展名 json/yaml/yml/toml 顺序。
2. 目录候选保留 os.listdir 原有顺序；能力报告可以另行排序展示，但匹配输入不得排序。
3. `_resolve_style_variant()` 改为调用共享解析/选择；保留 default、同分和无 default 的旧行为。
4. `get_style_snapshot()` 对当前来源全部候选调用既有 `_load_config_file()`，再从其返回的校验后配置提取 facts。缺失/非字典 info_position 注入默认字段与显式空字典不注入的区别必须保留；colors/fonts 同理。错误候选保留 path/条件/诊断，不进入显示并集。
5. `get_style_config()` 保持“选路径 → 只加载此路径”，不因选中配置损坏而改选其他候选。
6. 同名目录空、候选全损坏时不能回退到内置同名来源；这与当前优先级一致。禁止从缩略图查找结果推导配置来源。

完成证据：四种格式、单文件与目录、默认与组合变体、同分顺序、无 default、目录/文件交叉同名、空目录和损坏命中全部通过断言。另必须通过 C19 默认值注入、C20 单变体目录、C21 未知条件兜底中的加载/能力部分；涉及 GUI 纯状态的断言在 T4 完成。每种用例同时比较 get_style_config 的实际返回配置和快照选中候选的事实数据；路径可用临时探针记录，不只测新 API 自身。

### T4：GUI 纯状态与有效参数

文件：新增 `src/gui_pyside/models/style_option_state.py`。

按 §11 精确实现求值次序、所有值的回退及原因优先级。模块仅接收数据，避免把 enable 判断散落在生成函数、样式切换和信号回调中。不得使用控件的 isEnabled() 过滤参数，因为禁用父容器、窗口忙碌等 UI 状态与样式能力不是同一件事。

完成证据：同一个 snapshot/raw/gps 输入求值两次相等；raw 不变；求值无文件 I/O；FilmClip 空→有→空可逆；固定色与镜头模式依赖不影响其他选项；当前候选损坏时保留已知输入可编辑。

### T5：GUI 控件绑定与刷新

文件：修改 `src/gui_pyside/pages/image_processing_page.py`、`src/gui_pyside/widgets/style_selector_card.py`。

1. 保存 §12.1 列出的全部 GroupWidget 返回值，建立内部选项到控件/行的绑定表。
2. 构造函数在 `_setup_ui()` 前设置 `_restoring_config=True`、`_style_snapshot=None`、`_option_evaluation=None`、`_updating_option_states=False`；创建归属于页面的 singleShot QTimer。
3. 移除 `_setup_ui()` 末尾那次过早刷新，改为 UI 和保存配置恢复完成、信号连接完成之后统一首次刷新。用 try/finally 复原恢复标记，处理 `_load_saved_config()` 中无配置提前 return。
4. `_reload_style_snapshot()` 只负责当前名称的一次加载；无选择也要替换旧快照。`_update_style_dependent_controls()` 只求值与应用，不重新遍历目录。
5. `_read_raw_option_values()` 集中完成中文选项到内部值的映射；复用现有字重/时间/镜头映射，不趁机改 config.json 存储格式。
6. `_apply_option_states()` 只 setEnabled、setContent、setToolTip/AccessibleDescription；不改值、不发起渲染、不保存配置、不重建卡片。仅值确实变化时调用 UI setter。
7. 样式列表 refresh 后始终显式重载当前快照并刷新状态。selector.refresh_styles([]) 必须设置 `_current_style=None`；不新增依赖字符串空值的伪 style_selected 事件。
8. `_update_button_states()` 的生成按钮条件改为“合法选中索引且 can_render_style”；导出按钮仍只依赖已有结果，不因当前样式错误而禁用旧结果导出。
9. 保留独立旋转适配提示的现有机制；本任务不借机重做其默认值展示。删除/清空照片时清除 GPS 提示，保留用户参数和样式预设能力。
10. 移除 `_create_style_selection_card()` 中“无样式则调用 create_sample_styles”的 GUI 启动逻辑；保留 StyleManager.create_sample_styles 方法本身供显式调用。无样式时展示空选择器和说明，不自动创建配置、不借重启修复空列表。这是空状态产品规则的必要配套，不改变 CLI 的默认行为。
11. 实现下方 T5-P 的保存/恢复契约，不能等到 T6 才处理 save_config。让空列表、持久化和重启作为 T5 的独立闭环验收。

完成证据：§12 的非生成事件逐项触发；所有选项未被意外重置；初始化无 AttributeError、无重复信号连接；同名编辑生效；G06 保存/重启闭环、G07 快速输入/切样式必过。T5 验收独立于 T6 的生成参数验收，具体分工见 §14.1。

#### T5-P：样式选择的保存与恢复契约

save_config、_load_saved_config 与 selector 使用同一规则，其他用户参数仍按原格式保存。无需修改 ConfigManager 或 config.json schema；其现有 JSON 保存支持 null。

| 情况 | 保存 style_name | 下次启动/刷新 |
| --- | --- | --- |
| 有真实选中项，名称仍在当前选择器列表中 | 该名称字符串 | 名称仍在新列表则恢复；允许配置暂时损坏的真实条目保留选择，生成另行校验。 |
| 列表为空或没有真实选中项 | null，覆盖旧值 | 列表仍空时 current_style=None，不创建示例、不注入 Bottom Bars。 |
| 保存值为 null、缺失、空字符串或非字符串 | 由本次实际选择决定后续保存 | 不调用 set_current_style 恢复该值；沿用刷新后自动选择的第一项，若列表空则 None。 |
| 保存名称已删除或不存在 | 不恢复不存在的名称 | 沿用刷新后的第一项，若无条目则 None；下次保存实际选择或 null。 |

具体实施：

1. 删除 save_config 中 `current_style or "底部信息条 Bottom Bars"`。样式名只从当前选择器的真实状态取值；null 必须显式写入，不能省略字段后让旧值残留。
2. 恢复时只对非空字符串尝试 set_current_style；该方法已有列表成员检查，保留“未知名称不改变选择、不发信号”的行为。不存在的名称原本就不会被恢复成本地非法选中态，本次不要绕开检查。
3. 保存和恢复不修改其他输入，不触发生成；恢复完成后统一加载快照并求值。
4. 空→重启仍空、空→加入样式→重启、旧名称删除→其他样式仍存在，这三条链路都要测。使用临时配置文件与临时样式目录，不删除或重命名真实内置样式来测试。

### T6：生成参数与处理器共享上下文

文件：修改 `image_processing_page.py`、`src/core/image_processor.py`。

1. 把 ImageProcessor.process 中原有 context 拼装替换为 build_style_variant_context 调用。保留传入原 metadata、加载 EXIF、font_weight 覆盖、失败处理和函数公开签名。
2. 在 GUI `_on_generate_frame()` 开头，合法图片检查之后、创建进度提示和临时文件之前：停止待处理的状态计时器，重新加载快照、读取原值、求值一次。
3. 若当前候选不可用，展示一次现有 Fluent InfoBar 警告并 return；不创建处理器、不写临时文件、不调用默认样式兜底。删除 process 调用处 `current_style or "底部信息条 Bottom Bars"`，仅传此次重载和求值所对应的真实样式名；与 T5-P 的保存规则一致。
4. 用此次 evaluation 的 effective_values 构造 RenderMetadata、选项和 font_weight。删除生成路径中重复的 GPS 替换/时间/镜头映射和直接读取三个文本框的逻辑。
5. LOGO 全样式不支持时传空字符串并跳过自动匹配；支持时保持现有 auto/none/文件名语义。本任务不改变自动匹配算法。
6. 字重不支持时向 process 传 None；支持时传用户映射值。背景填充始终传用户原选择的合法 key，固定色由渲染器覆盖；不得把自定义背景动态 key 写回控件。
7. 饱和度覆盖仅在 enhance_background 状态可用时采用用户开关：勾选→None，未勾选→1.0；不可用→None。水印、方向适配、LRU 与图像输出路径保留现有流程。
8. save_config 对用户选项保持原值持久化：读取原控件，不读取 effective_values。style_name 单独遵守 T5-P 的真实名称/null 契约。对于目前未保存的地点、文本等，不新增持久化行为。

生成前重载可防止一般外部文件编辑造成陈旧状态，不承诺快照与处理器重新读盘之间的原子一致性；本次不新增配置锁、文件监控或向渲染器注入快照的 API。极短时间并发修改仍由既有处理器报错处理，并在验证记录注明此边界。

既有 LOGO 边界：GUI 自动预匹配使用用户所选 bg_key 的明暗，而固定背景色样式可能使用另一明暗方案；若 GUI 已得到具体 logo_filename，渲染器不会再次自动匹配，只有该值为 None 时才走其内部分支。本次保留算法并在验证记录标明，不把现有明暗版差异归为能力联动失败，也不借本任务修改匹配算法。

完成证据：拦截/记录 process 调用参数验证原值与有效值分离，再实际渲染验证。不能只检查界面变灰就声称残留值不会进入生成。

### T7：文档与验证交付

文件：修改 `docs/STYLE_GUIDE.md` 中自定义文本可用性说明；更新本文末尾的实施记录；新增 `docs/plans/STYLE_OPTION_CAPABILITIES_VALIDATION.md` 保存验证证据。

指南解释“全部变体能力并集、保留输入、当前变体可能不使用某项”，同步说明组合字段、GPS 替换与直接 gps 的差异，以及整个 info_position 缺省会注入默认字段、显式空字典才表示无信息字段。不新增样式 YAML 能力开关，不改现有样式以迎合能力分析器。

完成证据：§13、§14 全部执行或明确记录未执行原因。功能缺口、GUI 无法验证等不得写成通过。仅按用户实际授权提交；若要求提交，只提交本任务文件至 dev，不合并、不推送、不升级版本。

## 11. 状态求值：确定顺序和所有回退值

### 11.1 一次求值的固定顺序

1. 从快照读 family display/control 并集；生成 author/location/custom_text/time 等选项的支持谓词。
2. 不参考当前变体，按全家族支持计算有效参数。location 先判支持，再按 GPS 开关与当前 gps_text 决定实际值。
3. 用有效参数构造上下文，并从完整候选列表选择当前变体；不要剔除损坏候选后再匹配。
4. 计算当前变体是否消费各选项，只用于文案。**不得把当前变体结果再回灌第 2 步重新过滤。**
5. 计算局部依赖：短镜头名与镜头显示模式、背景固定色与背景方法、字重。不得因当前文本为空而取消样式声明能力。
6. 生成所有 OptionState 和 can_render_style；一次应用，更新生成按钮。若状态正在应用，用 guard 防重入；恢复标记只延迟刷新，不能遗失最终刷新。

背景是明确例外：固定背景色由当前变体决定是否允许修改。背景选择不参与变体匹配，因此此例外不会造成作者/文本输入的自锁。

### 11.2 参数值回退表

| 项 | 支持时的有效值 | 不支持或依赖关闭时的有效值 | 原控件值 |
| --- | --- | --- | --- |
| author | 原值或 None | None | 保留 |
| location | GPS 开且有 GPS→GPS；否则手工原值或 None | None，忽略 GPS 开关 | 保留 |
| custom_text | 原值或 None | None | 保留 |
| timestamp_display_mode | full/date_only/hide 原选择 | full | 保留 |
| lens_display_mode | combined/camera_only/lens_only 原选择 | combined | 保留 |
| use_short_lens | 原开关 | False | 保留 |
| logo_selection | 原 auto/none/文件名，经现有逻辑转换 | none，对应 logo_filename="" | 保留 |
| bg_fill_type | 原合法 key；未知 key 回退 DEFAULT_FILL | 固定色时仍传原合法 key，由渲染覆盖 | 保留 |
| enhance_background | 原开关决定 saturation_override | saturation_override=None | 保留 |
| font_weight | 原 light/regular/medium | 传给 process 的 font_weight=None | 保留 |

author/location/custom_text 仍使用现有 `value or None` 规则，不 trim；空格字符串与空字符串语义保持不同。RawOptionValues 内部已规范为合法枚举，异常恢复值用既有默认项回退，不能把空背景 key 传到 BackgroundFillManager。

短名启用公式：`family_has_independent_lens OR (family_supports_camera_lens AND effective_lens_mode != camera_only)`。再与全家族 use_short_lens 支持及快照整体可用性相交。只在其他变体有独立 lens 时也应保持可用，并说明当前布局未使用。

### 11.3 reason_code 与文案优先级

从上到下选择首个适用主原因，其他信息放 tooltip；不要同时显示互相矛盾的原因。

| 优先级 / code | enabled | 简短说明 | 适用条件 |
| --- | --- | --- | --- |
| 1 no_style / invalid_style | False | 未选择样式 / 样式配置不可用 | empty/missing/invalid，作用于本次 11 项；输出、旋转和水印不受此规则限制。 |
| 2 unsupported | False | 当前样式不支持 | 全家族既无显示消费也无相关条件控制。 |
| 3 current_variant_invalid | 按全家族支持保留 | 当前布局配置有误 | partial 且选中候选损坏；保留能切换布局的已知输入。背景和增强因当前配置未知暂禁用；can_render_style=False。 |
| 4 fixed_background | False | 背景由样式指定 | 背景相关控件；仅当当前变体解析固定色成功。 |
| 5 dependency_inactive | False | 仅显示相机时无效 / 仅模糊背景有效 | 短名或增强的局部依赖未满足。 |
| 6 variant_control_only | True | 用于切换布局 | 参数仅有控制支持，无显示支持。 |
| 7 other_variant_only | True | 部分布局支持 | 家族支持，当前候选不消费该项。 |
| 8 gps_override / gps_fallback | True | 当前使用 GPS / 无 GPS，使用手工地点 | 地点/GPS 的状态说明；缺照片时说明可预设 GPS。 |
| 9 supported | True | 使用该行原有说明 | 其余正常支持状态。 |

背景、增强没有普通 display_options 时不能套用 unsupported；它们使用专门规则。字重依据 has_weighted_text。GPS 的 control_only/other_variant_only 由 location 能力及当前用途派生。生成的“supported”只表示样式有消费入口，不保证照片 EXIF 齐全或画面每一项都可见。

对 unsupported 与 other_variant_only 的 tooltip 说明原值已保留；后者可附支持变体文件名和当前文件名。GUI 不暴露本地绝对资源路径，完整路径仅用于 debug 日志与配置错误诊断。

## 12. GUI 绑定表、事件表与框架操作边界

### 12.1 控件与 GroupWidget 引用

| option_id | 现有控件 | 保存的行引用 |
| --- | --- | --- |
| author | edit_author | author_group |
| location | edit_location | location_group |
| use_gps_location | chk_use_gps | gps_group |
| custom_text | edit_custom_text | custom_text_group |
| timestamp_display_mode | combo_timestamp | timestamp_group |
| lens_display_mode | combo_lens_display | lens_display_group |
| use_short_lens | chk_short_lens | short_lens_group |
| logo_selection | combo_logo | logo_group |
| bg_fill_type | combo_bg_fill | bg_fill_group |
| enhance_background | chk_enhance | enhance_group |
| font_weight | combo_font_weight | font_weight_group |

现有 bg_group/fw_group 的局部引用改为对应成员后，保持三列宽度对齐逻辑引用正确。每行保留原基础说明作为恢复文案；不能首次设为“不支持”后失去正常说明。

### 12.2 事件与刷新动作

| 事件 | 重载快照 | 重算 evaluation | 触发渲染 |
| --- | --- | --- | --- |
| 初始化完成、恢复完成 | 是，一次 | 是，同步 | 否 |
| style_selected | 是 | 是，同步 | 否 |
| refresh_style_list / showEvent 返回页面 | 是，即使名称未变 | 是，同步 | 否 |
| 三个 LineEdit.textChanged | 否 | 150ms singleShot 合并 | 否 |
| 时间、镜头模式、背景 ComboBox.currentIndexChanged | 否 | 是，同步 | 否 |
| GPS、短名、增强 SwitchButton.checkedChanged | 否 | 是，同步 | 否 |
| LOGO、字重 ComboBox.currentIndexChanged | 否 | 是，同步 | 否 |
| _select_item / _remove_filmstrip_item / _on_clear_all | 否 | 是，读取最新 current_index | 否 |
| 生成按钮 | 是，同步 | 是，取消待执行 timer 后重算 | 通过样式与照片检查后执行一次 |

信号连接统一放在所有控件构造后，连接一次。回调接收并忽略 Qt 传入的 index/bool/text，统一调度求值；不要把 bool 信号误绑定到 reload 参数。刷新不能递归调用 refresh_style_list。

`showEvent()` 目前会重建样式列表，本次不优化为文件监控；不在 textChanged 中调用它。无照片仍应允许编辑受支持的预设，只有生成按钮不可用。

### 12.3 QFluentWidgets 的实施要求

- 使用实际 `LineEdit`、`ComboBox`、`SwitchButton`；不替换成 Qt 原生交互控件。
- 只禁用绑定表中的控件，不调用 card.setEnabled(False) 或 group.setEnabled(False)。
- 使用 GroupWidget.setContent 保留可读原因；短说明不主动换行，不新增固定高度。不用颜色 CSS 代替实际禁用。
- 这次按控件粒度禁用，不改动下拉选项列表；setItemEnabled 仅作为已有能力参考，本任务无需引入单项禁用状态机。
- 默认不需改值，因此不必为每次 setEnabled 包裹 QSignalBlocker；只有配置恢复的程序性改值使用 blocker，并在结束统一刷新。
- 若实测打开的 ComboBox 菜单不会随控件禁用关闭，只在集中应用器中收拢该菜单；核对本地 dropMenu 的实际类型及公开关闭接口后实现，避免散落私有方法调用。
- 需要验证浅色/深色主题中灰态和文字对比度；不要为本任务全局覆盖 Fluent QSS。

## 13. 可复现验证用例与精确断言

验证临时脚本放在项目现有忽略的 `test_images/style_option_capabilities/` 下，使用 Python assert，不加入测试框架，不提交生成图片。临时 `.py` 同样执行 py_compile。验证配置用临时目录和 StyleManager(config_dir=...)，不覆盖真实内置样式、字体、CSV 或 config.json。

### 13.1 能力、匹配与纯状态验证

夹具约定：除专测默认值注入的 C19 外，最小配置显式包含 `name`、`layout.info_position: {}`；需要动态字段的用例在此字典中加入节点。固定文字节点及已知信息节点须使用现有合法定位字段（例如 position=bottom-center、alignment=top-center、placement=outside）。所有磁盘集成用例先经 `_load_config_file()`，再分析返回结果；纯函数用例使用等价的校验后配置。不得通过绕开加载器制造与实际渲染不同的预期。

| 编号 | 输入构造 | 必须断言 |
| --- | --- | --- |
| C01 | default 无 custom_text，no_location 有启用 custom_text | 家族支持 custom_text；default 下输入仍 enabled；当前提示 other_variant_only。 |
| C02 | 只有 timestamp_author | author 和 timestamp_display_mode 均启用；hide 不取消作者能力。 |
| C03 | 只有 camera、lens | lens_display_mode disabled，短名 enabled；残留 camera_only 被归一为 combined。 |
| C04 | 只有 camera_lens | camera_only 下短名 disabled，原勾选保留；回 combined 后 enabled 并恢复有效勾选。 |
| C05 | 只有 gps | location/GPS 替换 disabled；EXIF gps 字段本身的显示不受开关影响。 |
| C06 | 显式 info_position={}，只有非空 defined_texts，无条件变体 | 字重 enabled；作者/地点/custom_text disabled。固定文本 key 叫 author 也不能启用作者输入。 |
| C07 | 两个独立夹具：info_position={} + fonts.sizes.author；info_position 只含合法定位的未知 key | 两者均不启用作者或字重；后者含未知字段诊断。不能省略 info_position 导致默认条目注入。 |
| C08 | default 与 no_author 均显式 info_position={}；no_author 使用不同背景 | author 为 variant_control_only；空/非空选择相应布局，参数不被过滤。 |
| C09 | 候选 no_custom_text 与 no_author_no_custom_text | custom_text 是一个字段；后者条件数 2，不拆成 custom/text。 |
| C10 | 固定顺序的同分候选；再测试无 default | 同分取第一个；无匹配无 default 时仍取第一个；不依赖真实系统目录排序作断言。 |
| C11 | 用户目录同名样式 + 内置目录；用户单文件 + 内置目录 | 与当前 get_style_config 优先级相同；不把两个来源能力做并集。 |
| C12 | 当前命中损坏 no_author，default 有效 | 不回退 default；can_render_style=False；作者入口仍能编辑使其离开损坏变体。 |
| C13 | 所有候选损坏、空目录、未知样式、无选择 | 输出完整 11 项 disabled 状态，无上一个样式残留；生成不可用。 |
| C14 | 单文件名 no_author.yaml | 作为单文件样式不产生作者条件控制能力。 |
| C15 | 同一最小合法配置分别保存为 yaml/yml/json/toml | 四种格式能力相同；变体识别与单文件兼容。 |
| C16 | 传入作者/地点/文本为空、空格、普通文字；时间 full/date_only/hide | 上下文键集合与旧 ImageProcessor 逻辑逐项相等，不能因为 trim 或 EXIF 缺失改变匹配。 |
| C17 | 合法固定色、明确解析失败颜色、无固定色；所选 pure/gaussian | 解析成功锁定背景+增强；解析失败按用户背景；纯色仅增强禁用；高斯增强可用。 |
| C18 | 多次求值、A→B→A、克隆后的渲染配置改 font weight | raw 不变、结果稳定；快照能力不被渲染配置修改污染。 |
| C19 | info_position 分别缺失、null、列表、空字典及只含合法 timestamp 节点；另将 colors/fonts 设为缺失或非字典值 | 前三种经加载后为 exif/author/location，作者/地点/字重支持；空字典不注入且无其他文字时三者不支持；timestamp 字典不补作者/地点。colors/fonts 先按既有校验归一化，不能被能力分析预先拒绝；事实数据与 get_style_config 返回配置一致。 |
| C20 | 仅 default 的目录夹具，并核对 SimpleInfo、FrameBar、Polaroid、FilmCut | 只有一个候选，家族显示能力等于该候选能力；不同用户输入不产生 other_variant_only。短名依赖/固定背景等局部禁用仍按规则；四个内置样式均记录结果。 |
| C21 | 候选 no_iso：有 default、无 default 且列首两组；再由通用调用者传 iso=None | GUI 四字段上下文不按 iso 条件命中：有 default 选 default，无 default 可按首文件兜底选 no_iso；不得删候选或虚构 GUI iso 选项。通用上下文显式给 iso=None 时仍可按条件命中。 |

使用通用选择函数的受控候选序列验证顺序，再验证 StyleManager 把真实枚举结果原序传入；不要通过给新旧结果都排序来掩盖变化。

### 13.2 GUI 与生成参数验证

GUI 探针必须使用临时 ConfigManager 或在探针内临时替换页面引用，保持生产默认行为不变，避免关闭窗口时覆盖用户 config。无窗口的纯函数验证不能代替下面的真实窗口验证。

| 编号 | 实际操作 | 通过条件 |
| --- | --- | --- |
| G01 | 启动应用、无照片依次切换 §2.1 的全部 8 个样式 | 选项与能力表一致、允许预设，生成按钮禁用；标题和说明可读；四个单变体目录不出现 other_variant_only。 |
| G02 | FilmClip 输入空→文字→空并生成样张 | 输入从不被锁死；LOGO 为家族可选；default/无文本变体提示与实际渲染相符。 |
| G03 | InfoCard 作者/地点四种空值组合 | 四变体均能达到；输入不被清空；组合文件匹配正确。 |
| G04 | A 输入作者等→B 不支持→A | 文本/开关/下拉选择均恢复原值，B 的 process 元数据已过滤。 |
| G05 | 有 GPS 图片↔无 GPS 图片↔删当前图片 | GPS 提示和 effective location 更新，无上一张坐标残留；手工地点可作备用。 |
| G06 | 临时样式目录和临时配置中依次完成：同名保存返回、删除当前项、清空列表并保存重启、加入新样式再重启、旧名称不存在但另有样式 | 同名能力重载；空列表 current_style=None 且保存 style_name=null；重启仍空、不创建示例文件；新列表非空时选第一项，有效已存名称优先恢复；未知/空/null/非字符串保存值不会形成非法选中态。 |
| G07 | a：恢复配置、快速输入、连续切样式并等待 pending timer；b：有 pending timer 时立即生成 | a 在 T5 必测：无重复连接/自动渲染/控件不存在，最终 evaluation 属于最后样式和输入；b 在 T6 必测：取消或吸收 pending timer，生成恰一次并使用最后一次完整求值。 |
| G08 | 给 process 加临时捕获包装，分别生成支持/不支持样式 | author/location/custom_text、时间、镜头、logo_filename、font_weight、saturation_override 与 §11.2 完全一致；原控件值不变。 |
| G09 | 当前损坏变体，已有可导出结果 | 生成不可用且说明明确；已有结果仍可导出；填写条件参数可恢复其他有效变体。 |
| G10 | 浅/深主题，窄右栏，Tab 键，已打开下拉菜单后禁用 | 不支持项不能被修改；说明可读，无横向溢出；没有可操作的残留菜单。 |
| G11 | 相关卡片先展开再收起，待动画结束后 dump_expand_card | 收起总高度等于标题高度；展开 spaceWidget.h≥view.h；两种状态都有日志证据。 |

G08 的捕获包装仅限临时脚本；验完移除，不把拦截或测试按钮留在生产 GUI。不要仅通过 disabled 属性断言替代键鼠与图像样张验证。

G06 必须用真实的临时 ConfigManager 文件完成保存→销毁页面→创建新页面→恢复，不以手工赋值模拟重启。在临时样式根目录记录前后文件列表，证明空列表重启没有隐式创建示例。探针既覆盖生产的 save_config/_load_saved_config，也隔离用户真实配置；可在构造页面前替换依赖引用，禁止为测试跳过本次要验证的恢复函数。

### 13.3 CLI 与渲染回归

由于本方案提取了变体上下文、选择逻辑和颜色解析，本次单张与批量实测均为必做。执行前对受控测试输入保存基线输出；实施后用相同输入和参数生成新输出，比较解码后的尺寸、像素及选中变体。输出路径必须分开，避免 skip-existing 跳过处理。

最小命令模板（尖括号先替换为独立验证目录中的实际绝对路径，不得原样执行）：

```powershell
.\venv\Scripts\activate
python D:\Coding\MiLecFrame\src\main.py -i "<测试输入绝对路径>" -o "<新单张输出绝对路径>" -s "底部信息条 Bottom Bars" --author "Probe" --location "Probe" --logo none
python D:\Coding\MiLecFrame\src\main.py --batch -i "<仅含测试图的绝对目录>" -o "<独立批量输出绝对目录>" -s "底部信息条 Bottom Bars" --author "Probe" --logo none
```

再用 FilmClip 的 custom_text 空/非空各生成一张，覆盖 no_custom_text 与 default；用 FilmCut 覆盖固定背景色。批量目录至少两张不同尺寸图片。返回码之外，还要检查输出存在且能解码、数量和日志；CLI 当前异常捕获方式可能使返回码不足以说明成功。

输出像素应保持一致的范围是“共享函数提取前后、相同显式 CLI 参数”。GUI 对无关残留参数过滤属于预期行为变化，应比较有效参数与预期图像，不把其差异误报为 CLI 回归。

## 14. 任务顺序、完成门禁与证据格式

执行顺序固定为 **T0 → T1 → T2 → T3 → T4 → T5 → T6 → T7**。同一智能体可以顺序完成全部工作；本文件不要求创建额外智能体或 Codex 任务。若用户另行安排多人协作，按文件归属交接，避免两个执行者同时编辑 image_processing_page.py。

### 14.1 逐阶段门禁

| 门禁 | 必须提供的证据 | 未通过时 |
| --- | --- | --- |
| T1/T2/T3 结束 | 相关新增/修改 py_compile；C01–C21 中适用的加载/能力断言，特别是 C19–C21；颜色兼容对照 | 留在当前任务包修复，不能以 GUI 灰态掩盖解析错误。 |
| T4 结束 | C01–C21 全部逻辑断言，含无 I/O、原值保留、损坏变体可退出、注入后能力一致 | 不开始宣称生成参数一致。 |
| T5 独立门禁 | §12.2 全部非生成事件逐行记录；G01/G03/G05/G06/G07a/G10/G11，加 G04 的保值和 G09 的状态部分；GUI 文件 py_compile | G06 持久化闭环或 G07a 时序冒烟失败则 T5 未通过。实际 GUI 无法验证时记录待验，不与 T6 合并宣称通过。 |
| T6 独立门禁 | G02/G07b/G08，G04 的有效参数及 G09 的导出行为；CLI 单张+批量、FilmClip 与固定色样张；受本阶段修改影响的 T5 用例重验 | 参数、实际渲染或 CLI 回归失败则 T6 未通过，不能用 T5 灰态证明代替。 |
| T7 结束 | 全部修改文件清单、最终语法检查、增量日志检查、指南与结果记录 | 任何必做项未通过都不得合入 mainline。 |

检查命令在 venv 内执行，Python 脚本使用绝对路径。最终 py_compile 列表依据实际改动收集，包含新增未跟踪 `.py` 与临时验证脚本，不能只靠 git diff 找到已跟踪文件。无需添加 pytest、lint 或类型检查工具。

仅在新增资源/依赖/打包路径改变时触发 build_release 打包门禁。本方案预期只新增可被正常 import 的 Python 模块、不新增资源；执行者仍需确认没有动态导入导致 PyInstaller 漏包，不能仅因新增了 `.py` 就宣称已完成打包验证。

### 14.2 验证记录模板

`STYLE_OPTION_CAPABILITIES_VALIDATION.md` 至少记录：

1. 执行日期、基线 HEAD、实际依赖版本、任务相关文件列表。
2. T0–T7 状态：完成 / 未完成 / 阻塞；每项附实际证据，不写笼统“全部测试通过”。
3. C01–C21、G01–G11 的通过/失败/未执行及原因；G07a/b、G04/G09 的阶段子项分开记录；临时脚本路径和关键断言输出。
4. CLI 输入与输出路径、处理数量、选中变体、尺寸与像素比较结果。
5. GUI 截图或可复现操作记录，以及两种卡片状态的布局日志。
6. py_compile 的实际文件列表与结果；新增 ERROR/TRACEBACK 的数量；负面用例的预期诊断单列。
7. 对用户工作区既有修改的保护情况；剩余限制和未解决事项。
8. T5 与 T6 的独立门禁结果；G06 临时配置中的 style_name 实际保存值、重启后的选中项及目录无新增文件证据；固定背景色下 LOGO 预匹配的既有明暗边界单列。

日志只记录样式名、变体名、选项 enabled/reason_code，以及必要的资源定位错误。连续相同状态不重复打印，切换/失效/错误时输出 DEBUG 摘要。不要为了调试把用户作者名、地点、文字内容写入新日志。

### 14.3 最终完成定义

必须同时满足：所有 11 项按约定联动；能力以校验后配置为准且并集不漏非 default 能力；当前变体不会锁死输入；原值不丢失；有效参数与提示一致；同名更新与空列表无残留，空状态保存/重启不伪造样式或创建示例；QFluentWidgets 外观及布局可用；T5/T6 各自通过；共享逻辑 CLI 无回归；文档与证据齐全。

不把“代码已写完”“离屏 API 能调用”或“语法检查通过”等同于功能完成。无法完成实际 GUI 验证时，交付状态写“实现完成，GUI 验收待完成”，留在 dev，不擅自升级版本或合入。

## 15. 可直接交给执行智能体的任务提示词

> 请在 D:\Coding\MiLecFrame 的 dev 工作区实施 GUI 选项随样式能力联动功能。先阅读 AGENTS.md 和 docs/plans/STYLE_OPTION_CAPABILITIES_PLAN.md，按其中 v3 执行契约完成 T0–T7。实现范围包含作者、地点、GPS 替换、自定义文本、拍摄时间、镜头模式、短镜头名、LOGO、背景填充、背景增强和字重。以校验后配置的全部变体显示/控制能力决定可编辑性，以当前变体决定生效提示；保留用户原值，统一构造有效渲染参数，避免输入自锁。特别遵守 info_position 缺省注入与显式空字典的区别，以及 T5-P 的真实样式名称/null 保存恢复规则，移除 GUI 无样式时自动创建示例的调用。遵循文档指定的模块边界、公共接口、来源优先级和 QFluentWidgets 约束，完成 C01–C21、G01–G11，分别通过 T5/T6 门禁，并完成语法检查、CLI 单张/批量与日志检查，将实际证据写入 docs/plans/STYLE_OPTION_CAPABILITIES_VALIDATION.md。保护工作区已有改动，不修改版本、tag、发行分支或推送。只执行功能实现与验证，未获提交指令时不自动提交。若执行环境无法进行实际 GUI 验收，明确记录未完成项，不冒称全部通过。遇到基线差异先核查并适配，遇到真正的产品规则冲突再提出具体问题。

### 实施记录（由执行者填写）

- [ ] T0 基线记录
- [ ] T1 颜色解析与背景查询
- [ ] T2 字段映射与能力纯函数
- [ ] T3 样式快照及兼容匹配
- [ ] T4 选项求值和有效参数
- [ ] T5 GUI 控件、信号和刷新
- [ ] T6 生成链路与共享上下文
- [ ] T7 文档与完整验证证据

当前以上任务均未执行；本轮交付物为方案文档。
