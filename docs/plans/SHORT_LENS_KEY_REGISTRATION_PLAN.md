# short_lens 键注册与镜头名三态改造方案

> **状态**：待执行
> **基线**：`dev` 分支当前工作区（2026-10-04）
> **一句话目标**：让样式配置可以直接调用 `short_lens`（短版镜头名）；同时把 GUI 的"短版镜头名"勾选框升级为三态下拉（默认 / 完整镜头名 / 短版镜头名），并让 InfoCard、竖版胶囊两个样式的镜头行改用 `short_lens`。
> **性质**：功能增强 + 样式配置调整。**不触碰渲染算法**，所有布局数值、字号、颜色一律不变。

---

## 0. 如何使用本文档

- **人类读者**：按顺序读 §1（背景）→ §2（语义，含具体例子）即可理解全部改动意图；§3 起是执行细节，可跳读。
- **执行智能体**：严格按 §3 的 Step 顺序执行，每个 Step 是一个独立可验收的单元；改动前先读 §4"不做的事"防止过度改动；每完成一步执行该步的"完成标志"；全部完成后跑 §6 验收清单。
- **执行纪律**：
  1. 每个 Step（或按 §5 的提交拆分）单独提交，禁止混提交；
  2. 保留既有注释，新增代码写详细中文注释；
  3. 行号会漂移，**以每处给出的"定位锚点"（上下文文本）为准**，行号仅供参考；
  4. **若锚点与实际代码对不上（找不到原文或出现多处歧义匹配），停止并报告差异，勿凭猜测改**；
  5. 全部命令在虚拟环境内执行：先 `.\venv\Scripts\activate`（PowerShell 5.1，不支持 `&&`，用 `;` 分隔）。

---

## 1. 背景与需求

### 1.1 现状（存在什么问题）

系统里有两套镜头名，来自 `data/lens_map.csv` 的两列：

| 名称 | 来源 | 例子 |
|---|---|---|
| **完整镜头名**（内部叫 `lens_model`） | `mapped_lens` 列 | `Summilux 28mm f/1.7 ASPH` |
| **短版镜头名**（内部叫 `short_lens`） | `short_lens` 列（缺列时回退完整名） | `Summilux 28mm` |

当前行为：

1. 短版镜头名**没有注册为渲染键**。样式配置文件（YAML 的 `info_position` 段）里写 `short_lens:` 会被静默忽略——取不到文本、不渲染、无报错。样式作者无法直接使用它。
2. 它只能"暗中"替代完整名：GUI 勾选"使用短版镜头名"后，`lens`、`camera_lens` 两个渲染键的输出会切换成短版名。所以它只是 `lens_model` 的"可选替代"，不是一等公民。
3. GUI 只有勾选/不勾选两态，无法表达"强制完整名"与"强制短版名"的区别。

### 1.2 目标（改完后是什么样）

1. `short_lens` 注册进 `RenderContext.get_text()`，样式配置可直接写 `info_position.short_lens:` 使用它。
2. GUI 的勾选框改为**三态下拉**："默认 / 完整镜头名 / 短版镜头名"。
3. InfoCard、竖版胶囊两个样式的镜头行从 `lens` 键改为 `short_lens` 键。
4. `lens` 键的替代能力完整保留——三态下拉继续控制它，GUI 选项照常生效。

### 1.3 已确认的决策（2026-10-04 与用户逐条确认）

| 问题 | 结论 |
|---|---|
| "默认"选项的语义？ | **各键归位、互不替代**：`lens` 出完整名，`short_lens` 出短版名 |
| "完整镜头名"选项的语义？ | `short_lens` 键的输出被完整名**替代**（"允许用 lens 代替 short_lens"） |
| "短版镜头名"选项的语义？ | `lens` / `camera_lens` 的输出被短版名**替代**（对称行为） |
| CLI 开关怎么办？ | 同步改为三态 `--lens-name {default,full,short}`，**删除** `--use-short-lens`，不留兼容 |
| 竖图自动设置逻辑怎么办？ | 保留：导入新图时首图竖幅/方形 → 自动选"短版镜头名"，横幅 → 自动选"默认"；仅导入时设置一次，之后尊重用户手动选择 |

---

## 2. 核心语义（执行前必读）

### 2.1 术语表

| 术语 | 含义 |
|---|---|
| **渲染键（key）** | 样式 YAML `info_position:` 段里的字段名（如 `lens`、`short_lens`、`camera`）。渲染器遍历这些键，逐个向 `RenderContext.get_text(key)` 要文本；返回 `None` 则该行不渲染 |
| **替代** | 某个模式下，A 键的输出改用 B 的数据。比如"完整镜头名"模式下 `short_lens` 键输出完整名——这就是"用 lens 代替 short_lens" |
| **键归位** | 默认模式下每个键输出自己语义对应的数据，谁也不替代谁 |
| **三态模式** | 本次新增的镜头名显示策略，内部值 `default` / `full` / `short`，见下表 |
| **`lens_display_mode`** | 既有的"镜头显示"下拉（combined / camera_only / lens_only），决定**显示哪些设备**；本次不动它，它与三态模式**正交**（管不同维度） |

### 2.2 三态下拉定义

| GUI 文案 | 内部值 | 一句话语义 |
|---|---|---|
| 默认 | `default` | 键归位：`lens` 出完整名，`short_lens` 出短版名 |
| 完整镜头名 | `full` | 全部强制完整名：`short_lens` 的输出被 `lens_model` 替代 |
| 短版镜头名 | `short` | 全部强制短版名：`lens` / `camera_lens` 的输出被短版名替代 |

### 2.3 贯穿示例（三态下各键实际渲染什么）

设定一张照片的 EXIF：相机 `Leica Q3`，镜头映射后完整名 `Summilux 28mm f/1.7 ASPH`，短版名 `Summilux 28mm`（来自 `lens_map.csv` 的 `short_lens` 列）。

| 渲染键 | `default`（默认） | `full`（完整镜头名） | `short`（短版镜头名） |
|---|---|---|---|
| `lens` | `Summilux 28mm f/1.7 ASPH` | `Summilux 28mm f/1.7 ASPH` | **`Summilux 28mm`** ← 替代 |
| `short_lens` | `Summilux 28mm` | **`Summilux 28mm f/1.7 ASPH`** ← 替代 | `Summilux 28mm` |
| `camera_lens`（combined） | `Leica Q3  \|  Summilux 28mm f/1.7 ASPH` | `Leica Q3  \|  Summilux 28mm f/1.7 ASPH` | **`Leica Q3  \|  Summilux 28mm`** ← 替代 |
| `camera_lens`（lens_only） | `Summilux 28mm f/1.7 ASPH` | `Summilux 28mm f/1.7 ASPH` | **`Summilux 28mm`** ← 替代 |
| `camera_lens`（camera_only） | `Leica Q3` | `Leica Q3` | `Leica Q3`（不受影响） |

（组合名的实际分隔符是**两个空格** `"  |  "`，见 `exif_helper.py` 的 `camera_lens_combined` 拼接格式，上表以此为准。）

要点：

- `default` 与 `full` 的差异**只在 `short_lens` 键上**；`full` 的价值就是"样式里写了 `short_lens`，但我这次想要完整名"。
- 对既有键而言，`short` 就是现状 `use_short_lens=True` 的行为，`default` 就是现状 `use_short_lens=False` 的行为——**老用户的行为完全可预期**；`short_lens` 键本身是新增能力。
- 任一键无数据时返回 `None`（该行不渲染），不输出占位符。短版名数据层已有回退链（短版名 → 映射名 → 原名），一般不会为空。

### 2.4 参数数据流（改造后）

```
CLI --lens-name {default,full,short}          GUI 下拉 combo_lens_name
        │                                       （ComboBox，userData 绑定内部值）
        ▼                                              │
main.process_image / batch_process_images                     │
(lens_name_mode=...)                    collect_render_options(page, item)
        │                                              │
        └──────────────► RenderMetadata.lens_name_mode: str = 'default'
                                     │
                                     ▼
                 RenderContext(..., lens_name_mode=...)
                                     │
                                     ▼
              get_text('short_lens' | 'lens' | 'camera_lens')
```

---

## 3. 执行步骤

### Step 1 渲染核心：`src/utils/render_context.py`

**目标**：注册 `short_lens` 键，实现 §2.3 输出矩阵。

**1a. 构造函数参数改三态**（定位锚点：`def __init__` 签名）。参数位置不变（仍第 6 位），`renderer.py` 的位置传参不受影响：

```python
# ── 改动前 ──
lens_display_mode: str = 'combined', use_short_lens: bool = False,

# ── 改动后 ──
lens_display_mode: str = 'combined', lens_name_mode: str = 'default',
```

同步：`self.use_short_lens = use_short_lens` → `self.lens_name_mode = lens_name_mode`（注释写明三态取值与语义）。

**1b. `get_text()` 新增 `short_lens` 分支并改造 `lens` 分支**（定位锚点：`elif key == 'camera_make':` 分支之后、`elif key == 'author':` 分支之前——即**原 `elif key == 'lens':` 分支处**，整体替换为以下两个分支）：

```python
        elif key == 'short_lens':
            # 短版镜头名（键归位：默认输出短版名）。
            # 三态"完整镜头名"（'full'）下被完整镜头名替代——
            # 即用户强制统一为完整名时，样式里的 short_lens 行也显示完整名。
            if self.lens_name_mode == 'full':
                return self._display_data.get('lens_model') or None
            return self._display_data.get('short_lens') or None
        elif key == 'lens':
            # 镜头型号（键归位：默认输出完整镜头名）。
            # 三态"短版镜头名"（'short'）下被短版名替代——
            # 保留 short_lens 作为 lens 替代的能力，GUI 下拉照常生效。
            if self.lens_name_mode == 'short':
                return self._display_data.get('short_lens') or None
            return self._display_data.get('lens_model') or None
```

**1c. `camera_lens` 分支只改判断条件**（定位锚点：`elif key == 'camera_lens':`）。两处 `if self.use_short_lens:` → `if self.lens_name_mode == 'short':`，其余逻辑原样保留。

**1d. docstring 更新**：`get_text` 的"支持的 key"列表补 `short_lens`，并在类注释处补一句：`lens_name_mode`（default/full/short）控制镜头长短名的替代关系。

**完成标志**：`python -m py_compile src/utils/render_context.py` 通过；§6.1 的临时验证脚本三态矩阵断言全绿。

---

### Step 2 链路改造：`renderer.py` / `main.py` / `batch_processor.py`

**目标**：`use_short_lens: bool` 全链路替换为 `lens_name_mode: str`。共 10 处，逐一按下表改。

| # | 文件 : 定位锚点 | 改动前 | 改动后 |
|---|---|---|---|
| 1 | `src/core/renderer.py` : `class RenderMetadata` 内字段 | `use_short_lens: bool = False                # 是否使用短版镜头名` | `lens_name_mode: str = 'default'             # 镜头名模式：default(键归位)/full(强制完整名)/short(强制短版名)` |
| 2 | `src/core/renderer.py` : `context = RenderContext(` 一行 | `metadata.lens_display_mode, metadata.use_short_lens,` | `metadata.lens_display_mode, metadata.lens_name_mode,` |
| 3 | `src/main.py` : argparse 的 `--use-short-lens` | `parser.add_argument("--use-short-lens", action="store_true", help="使用短版镜头名")` | `parser.add_argument("--lens-name", choices=['default', 'full', 'short'], default='default', help="镜头名模式：default=键归位 / full=强制完整镜头名 / short=强制短版镜头名")` |
| 4 | `src/main.py` : 批量分支 `use_short_lens=args.use_short_lens,` | 同左 | `lens_name_mode=args.lens_name,` |
| 5 | `src/main.py` : 单张分支 `use_short_lens=args.use_short_lens,` | 同左 | `lens_name_mode=args.lens_name,` |
| 6 | `src/main.py` : `def process_image(` 签名 | `use_short_lens=False,` | `lens_name_mode='default',` |
| 7 | `src/main.py` : `process_image` docstring | `use_short_lens: 是否使用短版镜头名` | `lens_name_mode: 镜头名模式 default/full/short（见 docs/STYLE_GUIDE.md）` |
| 8 | `src/main.py` : `process_image` 内 `metadata = RenderMetadata(` 一行（约 261） | `lens_display_mode=lens_display, use_short_lens=use_short_lens,` | `lens_display_mode=lens_display, lens_name_mode=lens_name_mode,` |
| 9 | `src/main.py` : **`def batch_process_images(`** 签名（约 290）+ docstring（约 316）+ 函数内 `processor.batch_process(...)` 透传（约 375） | 三处 `use_short_lens` | 参数 `use_short_lens=False,` → `lens_name_mode='default',`；docstring 同步；透传行 `use_short_lens=use_short_lens,` → `lens_name_mode=lens_name_mode,`。注意：**该函数不直接构造 RenderMetadata**，只把参数透传给 `BatchProcessor.batch_process()` |
| 10 | `src/core/batch_processor.py` : `batch_process()` 参数（约 101）+ docstring（约 127）+ 函数内 `metadata = RenderMetadata(...)` 构造（约 160） | 三处 `use_short_lens` | 同 #6/#7/#8 的改法 |

**注意**：一次性硬切换，**不留** `use_short_lens` 兼容参数（与 `RENDER_PARAMS_REFACTOR_PLAN.md` §0.4"不加兼容层"的先例一致）。改完后全库 grep `use_short_lens` 应只命中 `gui_legacy/` 与历史文档/CHANGELOG。

**完成标志**：`python -m py_compile` 通过 3 个文件；`python src/main.py --help` 显示 `--lens-name` 且不再有 `--use-short-lens`。

---

### Step 3 GUI 改造

**目标**：勾选框 → 三态下拉；自动设置逻辑映射三态。

**3a. `src/gui_pyside/pages/image_processing_config_cards.py`**

1. 常量区（定位锚点：`LENS_DISPLAY_ITEMS` 定义附近）新增选项表（本文件使用；3b 的自动设置逻辑只用字符串字面量 + `findData`，无需导入此常量）：

```python
# 镜头名模式三态选项（GUI 文案 → 稳定内部值，与 CLI --lens-name 对齐）。
# 默认 = 键归位（lens 出完整名、short_lens 出短版名）；
# 完整镜头名 = short_lens 的输出被 lens_model 替代；
# 短版镜头名 = lens / camera_lens 的输出被短版名替代。
LENS_NAME_ITEMS = [
    ('默认', 'default'),
    ('完整镜头名', 'full'),
    ('短版镜头名', 'short'),
]
```

2. `create_shot_info_card()` 内（定位锚点：`page.chk_short_lens = SwitchButton()`）：

```python
# ── 改动前 ──
    page.chk_short_lens = SwitchButton()
    card.addGroup(FluentIcon.CHECKBOX, "短版镜头名", "使用简洁的镜头名称", page.chk_short_lens)

# ── 改动后（仿同函数内 combo_lens_display 的构造模式）──
    page.combo_lens_name = ComboBox()
    for _text, _key in LENS_NAME_ITEMS:
        page.combo_lens_name.addItem(_text, userData=_key)
    page.combo_lens_name.setCurrentIndex(0)
    card.addGroup(FluentIcon.CAMERA, "镜头名", "默认按样式键取值；可强制完整名或短版名", page.combo_lens_name, 1)
```

3. `collect_render_options()` 内（定位锚点：`use_short_lens=page.chk_short_lens.isChecked(),`）：
   → `lens_name_mode=page.combo_lens_name.currentData() or 'default',`
4. **保留 `SwitchButton` 的 import，禁止清理**——本文件 `chk_enhance`（背景增强）、`chk_use_gps`（GPS 替换）、`chk_watermark`（文本水印）等控件仍在使用它。

**3b. `src/gui_pyside/pages/image_processing_page.py`**（竖图自动设置，定位锚点：注释"竖图自动启用"所在段）

```python
# ── 改动前 ──
                auto_short_lens = first_item.height >= first_item.width
                self.chk_short_lens.setChecked(auto_short_lens)

# ── 改动后（保留"仅导入新图时设置一次"的既有语义；三态映射：
#    竖幅/方形 → "短版镜头名"，横幅 → "默认"）──
                auto_name_mode = 'short' if first_item.height >= first_item.width else 'default'
                self.combo_lens_name.setCurrentIndex(self.combo_lens_name.findData(auto_name_mode))
```

原注释块**保留**，在其后补一行三态映射说明。紧随其后的 `logger.info` 日志中 `-> {auto_short_lens}` 改为 `-> {auto_name_mode}`（文案"自动设置短版镜头名"可顺带改为"自动设置镜头名模式"）。

**3c.（可选，低优先级）死代码区同步**：本文件 `_create_shot_info_card()`（约 709 行起）里还有一份 `self.chk_short_lens = SwitchButton()`。该批 `_create_*_card()` 方法经 grep 确认**无调用点**（实际卡片由 `image_processing_config_cards.py` 构造，见本文件 `self.shot_info_card = create_shot_info_card(self)`）。不改不影响运行；若追求一致性可同步改名，禁止删除。

**完成标志**：GUI 实际启动，下拉显示三项；导入竖图自动跳"短版镜头名"、横图自动跳"默认"；切换三项预览实时变化。

---

### Step 4 样式配置文件（提交类型 `style:`）

**目标**：InfoCard 与竖版胶囊的镜头行改用 `short_lens` 键。**只改键名，数值一律不动。**

**4a. `src/frame_styles/configs/信息卡片 InfoCard/`**——4 个变体各改 1 处（统一定位锚点：`info_position:` 段内、**`camera:` 元素块之后的 `lens:` 元素块**；注意各变体的 `margin_bottom` 数值不同，仅作核对参考，**一律不动**）：

| 文件 | 参考行号 | 该块 `margin_bottom`（核对用） | 改动 |
|---|---|---|---|
| `default.yaml` | 122 | `0.151` | `lens:` → `short_lens:` |
| `no_author.yaml` | 117 | `0.131` | `lens:` → `short_lens:` |
| `no_location.yaml` | 117 | `0.131` | `lens:` → `short_lens:` |
| `no_author_no_location.yaml` | 104 | `0.111` | `lens:` → `short_lens:` |

键下定位参数（`placement` / `position` / `alignment` / `margin_right` / `margin_bottom`）原样保留。文件内注释描述的"lens 行"指视觉行（标签文案仍是 `"Lens"`），**保留不动**；仅在涉及数据键语义处补一句：该行取 `short_lens`（短版镜头名），受 GUI 镜头名下拉控制。InfoCard 没有 lens 专属颜色/字号键，无连带改动。

**4b. `src/frame_styles/configs/竖版胶囊 Vertical Capsule/default.yaml`**——3 处：

| 位置（参考行号） | 改动前 | 改动后 |
|---|---|---|
| `colors:` 段（57-58） | `custom_lens_dark_color: [255, 255, 255]` / `custom_lens_light_color: [0, 0, 0]` | `custom_short_lens_dark_color: [255, 255, 255]` / `custom_short_lens_light_color: [0, 0, 0]`（颜色键名 = `custom_{元素键}_{明暗}`，随键名自动派生，**数值不变**） |
| `fonts.sizes:` 段（121） | `lens: 0.0192` | `short_lens: 0.0192` |
| `info_position:` 段（249） | `lens:` | `short_lens:`（定位参数原样保留） |

**4c. 自查（防漏改）**：

```powershell
Select-String -Path "src\frame_styles\configs\信息卡片 InfoCard\*.yaml","src\frame_styles\configs\竖版胶囊 Vertical Capsule\*.yaml" -Pattern "^\s+lens:" 
# 期望：无输出（info_position / font sizes 里已无裸 lens 键）
```

**完成标志**：两条残留检查命令均无输出（4c + §6.3 的 `custom_lens_` 检查）；两个样式渲染样张正常（见 §6.3）。

---

### Step 5 样式编辑器白名单：`src/gui_pyside/models/style_config_form.py`

**目标**：GUI 样式编辑器能选择/保存 `short_lens`。两个常量各补一项（放 `'lens'` 后面）：

| 常量（定位锚点） | 作用 | 改动 |
|---|---|---|
| `ELEMENT_KEYS`（约 25 行） | 元素键下拉、`relative_to` 引用池 | 列表中 `'lens',` 后补 `'short_lens',` |
| `COLOR_ELEMENT_KEYS`（约 60 行） | 颜色表 / 字号表的行白名单 | 列表中 `'lens',` 后补 `'short_lens',` |

两处被 `element_editor.py`、`elements_section.py`、`colors_section.py`、`fonts_section.py`、`custom_text_section.py`、`logo_section.py` 共用，补一行全量生效。

**完成标志**：样式编辑器中元素键下拉出现 `short_lens`；颜色/字号表格出现 `short_lens` 行；保存→重载往返无字段丢失。

---

### Step 6 文档同步（提交类型 `docs:`）

| 文件 | 改动点 |
|---|---|
| `src/frame_styles/configs/_STYLE_TEMPLATE.txt` | ① 元素模板（`lens: [________]` / `camera_lens: [________]` 处）补一行 `short_lens: [________]`；② "系统支持的 key" 列表补 `short_lens`；③ 颜色模板（`custom_lens_light_color` 行附近）补 `custom_short_lens_light_color / dark` 行 |
| `docs/STYLE_GUIDE.md` | ① 文本输出表：补 `short_lens` 行（输出示例 `Summilux 28mm`，注明受三态控制），同时把 `lens` 行的"受短版开关控制"改为"受镜头名三态控制"；② "镜头显示模式 和 使用短版镜头名 这两个选项在 GUI 中控制"一句改为"镜头显示模式"（显示哪些设备）+"镜头名"三态下拉（长短名）的表述；③ "支持的 info_position 元素类型"列表补 `short_lens` |
| `docs/DEVELOPMENT.md` | ① RenderContext 条件逻辑说明（`use_short_lens` → `lens_name_mode`）；② key 映射表补 `short_lens` 行（`短版名 / lens_model（full 替代）`） |
| `README.md` | ① 第 87 行 GUI 功能表"短版镜头名"改为"镜头名三态（默认/完整/短版）"；② 第 157 行字段表 `short_lens` 行的"GUI 勾选"表述改三态下拉；③ 第 256 行 CLI 参数表 `--use-short-lens` → `--lens-name`（含三态说明） |
| `CHANGELOG.md` | 随提交补条目：代码 `feat:`、样式 `style:`、文档 `docs:` 分列 |

**完成标志**：文档中不再有把短版镜头名描述为"勾选"的现行行为表述（历史 CHANGELOG 条目除外）。

---

## 4. 不做的事（防止过度改动）

1. **不拆分 `camera_lens` 短版独立键**——组合名长短仍由三态 + `lens_display_mode` 决定。
2. **不动 `gui_legacy/`**——已封存、零 import 链，签名变更不影响运行。
3. **不动数据层**——`ExifHelper` / `DeviceMapper` 的 `short_lens` 产出与回退链已就绪，零改动。
4. **不动样式变体系统**——`_resolve_style_variant()` 的 `no_{field}` 机制不引入 `short_lens` 变体。
5. **不持久化下拉状态**——`config.json` 不新增字段（与现状一致）。
6. **不改 `defined_texts` 的 `"Lens"` 标签文案**——那是固定文案，不是数据键。
7. **不删任何旧注释、不顺手重构无关代码**（含 3c 的死代码区——只可同步，不可删）。

## 5. 提交拆分（Conventional Commits，本项目语义）

| 顺序 | 提交信息 | 覆盖内容 |
|---|---|---|
| 1 | `feat: 注册 short_lens 渲染键并新增镜头名三态模式` | Step 1/2/3/5（全部代码） |
| 2 | `style: InfoCard 与竖版胶囊镜头行改用 short_lens 键` | Step 4（样式 YAML；本项目 `style` 专指相框样式改动，**不得记作 feat**） |
| 3 | `docs: 同步 short_lens 键与镜头名三态文档` | Step 6 |

## 6. 验收清单（命令级，逐条勾选）

### 6.1 语法与三态矩阵（功能验证脚本）

- [ ] `.\venv\Scripts\activate` 后逐个 `python -m py_compile` 覆盖：`src/utils/render_context.py`、`src/core/renderer.py`、`src/main.py`、`src/core/batch_processor.py`、`src/gui_pyside/pages/image_processing_config_cards.py`、`src/gui_pyside/pages/image_processing_page.py`、`src/gui_pyside/models/style_config_form.py`。
- [ ] 项目根新建临时脚本 `_verify_lens_name_mode.py`（下划线开头、**不提交**，验证后删除）并运行，断言 §2.3 矩阵。脚本要点：

```python
# 临时验证脚本：三态输出矩阵断言（验证后删除，不入库）
from unittest.mock import patch
from src.utils.render_context import RenderContext

FAKE = {'lens_model': 'Summilux 28mm f/1.7 ASPH', 'short_lens': 'Summilux 28mm',
        'camera_combined': 'Leica Q3',
        'camera_lens_combined': 'Leica Q3  |  Summilux 28mm f/1.7 ASPH',
        'camera_lens_combined_short': 'Leica Q3  |  Summilux 28mm'}

def ctx(mode, display='combined'):
    with patch('src.utils.render_context.ExifHelper') as M:
        M.return_value.get_display_data.return_value = FAKE
        return RenderContext((100, 100), {'x': 1}, lens_display_mode=display, lens_name_mode=mode)

d, f, s = ctx('default'), ctx('full'), ctx('short')
assert d.get_text('lens') == FAKE['lens_model']            # 默认：键归位
assert d.get_text('short_lens') == FAKE['short_lens']
assert f.get_text('short_lens') == FAKE['lens_model']       # full：short_lens 被替代
assert s.get_text('lens') == FAKE['short_lens']             # short：lens 被替代
assert s.get_text('camera_lens') == FAKE['camera_lens_combined_short']
# camera_only 模式不受三态影响（三种模式均输出相机名）
for _m in ('default', 'full', 'short'):
    assert ctx(_m, 'camera_only').get_text('camera_lens') == FAKE['camera_combined']
print('三态矩阵断言全部通过')
```

### 6.2 CLI

- [ ] `python src/main.py --help` 显示 `--lens-name {default,full,short}`，且无 `--use-short-lens`。
- [ ] `--lens-name` 三值各渲染一张照片，输出镜头行符合 §2.3 矩阵；传 `--use-short-lens` 报 `unrecognized arguments`。

### 6.3 样式渲染

- [ ] InfoCard 4 个变体 + 竖版胶囊各渲染样张，镜头行随三态变化符合矩阵。
- [ ] 竖版胶囊的镜头行颜色/字号与改前**视觉一致**（仅键名变化）。
- [ ] 残留检查无输出：`Select-String -Path "src\frame_styles\configs\竖版胶囊 Vertical Capsule\*.yaml" -Pattern "custom_lens_"`。

### 6.4 GUI（实际启动验证）

- [ ] "拍摄信息配置"卡出现"镜头名"下拉，三项文案为"默认/完整镜头名/短版镜头名"。
- [ ] 导入竖图自动跳"短版镜头名"、横图自动跳"默认"；手动切换后导入新图仍会被自动值覆盖一次（保持现状语义），切换选中胶片栏图片不重置。
- [ ] 样式编辑器：元素键下拉、颜色表、字号表均出现 `short_lens`；保存→重载往返无丢失。

### 6.5 收尾

- [ ] `debug_log.txt` 无新增 ERROR / TRACEBACK。
- [ ] 残留检查仅命中封存区（**注意：`Select-String` 没有 `-Recurse` 参数，须用 `Get-ChildItem` 管道**）：
  ```powershell
  Get-ChildItem -Path src -Recurse -Filter *.py | Select-String -Pattern "use_short_lens"
  ```
  期望仅命中 `src/gui_legacy/` 下的调用点——**属预期失效，勿修**（封存代码零 import 链不可达，见 §4 第 2 条）。
- [ ] 临时脚本 `_verify_lens_name_mode.py` 已删除。
