# 竖图方向适配设计与执行方案

> 状态：已实施（Phase 1–5 完成，dev `b6737c4`）；2026-09-21 行为修订：**用户显式选择适配取消竖图限制（所有图片旋转），样式预设仍仅对竖图生效**（`resolve_effective_adaptation` 返回来源标志，`rotate_image_for_render` 按来源区分适用范围）；同日 GUI 菜单更名"竖图方向适配"→"旋转适配"（样式编辑器"默认竖图适配"保留原名，内部标识符与 config 键 `portrait_adaptation` 保持兼容）  
> 设计日期：2026-09-21  
> 基线：`dev` 分支 `90b637a`（工作区已有其他未提交内容，本方案不依赖、不覆盖）  
> 目标：将顺/逆时针适配提升为用户可选处理参数，同时允许样式声明"默认"模式下的建议方向  
> 本文范围：配置契约、优先级、核心管线、GUI、样式编辑器、FilmClip 变体、验证与实施顺序；本轮只修订方案，不修改功能代码  
> 核查结论：方案 §2 全部架构断言与源码吻合（详见 §2.7）；未发现阻断性设计缺陷，可按 §11 细化步骤实施

## 1. 最终产品定义

### 1.1 用户侧四选项

在 PySide6 图片处理页的“相框配置”卡片中增加一个 `ComboBox`，标题为“竖图方向适配”，包含：

1. **默认（跟随样式）**
2. **不旋转**
3. **顺时针适配**
4. **逆时针适配**

内部稳定值分别为：

```text
default
none
clockwise
counterclockwise
```

用户选择是本次处理任务的运行时配置，不再把顺、逆时针两个开关直接写进样式文件。

### 1.2 样式侧只声明默认值

样式配置新增一个可选顶层字段：

```yaml
default_portrait_adaptation: clockwise
```

支持值：

```text
clockwise
counterclockwise
none
```

- 字段缺失等同于 `none`，保持所有现有样式的旧行为。
- FilmClip 的两个实际变体声明 `clockwise`。
- 样式字段只在用户选择 `default` 时生效。
- 用户显式选择 `none`、`clockwise` 或 `counterclockwise` 时，覆盖样式默认值。

使用单一枚举字段后，样式文件中不再存在两个布尔开关同时出现的非法状态；互斥性由字段类型天然保证。

### 1.3 “默认”的明确语义

“默认”不是固定的“不旋转”，而是**跟随当前样式声明**：

| 用户选择 | 样式声明 | 最终行为 |
|---|---|---|
| default | 缺失 / none | 不适配 |
| default | clockwise | 顺时针适配 |
| default | counterclockwise | 逆时针适配 |
| none | 任意值 | 不适配 |
| clockwise | 任意值 | 顺时针适配 |
| counterclockwise | 任意值 | 逆时针适配 |

“不旋转”是明确的用户覆盖值：即使 FilmClip 声明默认顺时针，选择“不旋转”后也不应用
方向适配。“默认（跟随样式）”继续保持动态继承语义，不能与“不旋转”混为一谈。

### 1.4 图像行为

1. 只对 EXIF 方向转正后的严格竖图生效，即 `height > width`。
2. 横图和方形图不旋转。
3. 顺时针适配：渲染前顺时针旋转 90°，完成整帧渲染后逆时针旋转 90°还原。
4. 逆时针适配：渲染前逆时针旋转 90°，完成整帧渲染后顺时针旋转 90°还原。
5. 输入旋转后，背景、画布、矩形、圆角、装饰、水印、文字和 Logo 都按横图尺寸完成处理。
6. 适配方向属于渲染行为参数，不改变源文件、导入缩略图或原图预览。

本功能是新增用户能力，按 SemVer 属于 minor 级功能；遵循项目规则，版本号只在全部门禁
通过并合入 `mainline` 时确定，本方案阶段不修改版本号。

## 2. 当前架构核查

### 2.1 正式处理链路

`ImageProcessor.process()` 当前关键顺序为：

```text
读取图片
  -> ImageOps.exif_transpose() 消解 EXIF Orientation
  -> 提取展示 EXIF / 原始 EXIF
  -> 尺寸限制与 sRGB 转换 / HDR 色调映射
  -> StyleManager 选择并加载最终样式变体
  -> FrameRenderer.render_frame()
  -> ImageProcessor._save_image()
```

因此渲染器收到的图像已经是用户视觉意义上的正确方向。竖图判断必须发生在
`exif_transpose()` 之后，不能依据文件中未经方向标签修正的原始像素尺寸。

### 2.2 单张、批量与 GUI

- CLI 单张最终调用 `ImageProcessor.process()`。
- `BatchProcessor` 对每张图复用一个 `ImageProcessor`，仍逐张调用 `process()`。
- PySide6 图片处理页调用 `ImageProcessor.process()`，输出预览从结果文件重新读取。
- `RenderOptions` 已经承载背景、装饰、Logo、饱和度和缓存等运行时行为参数，是新增用户选择的正确归属。
- `ProcessingConfig` 声明了“相框配置”领域字段，但当前页面生成逻辑仍直接从控件构造
  `RenderOptions`；本次需同步增加字段，避免模型定义继续与实际 GUI 配置漂移。

### 2.3 样式编辑器是特殊调用点

`StyleCreatorPage._render_preview()` 不经过 `ImageProcessor`，而是：

```text
StyleConfigFormData.to_yaml_dict()
  -> 选择横图或竖图样本
  -> FrameRenderer.render_frame()
  -> 显示结果
```

样式编辑器预览没有图片处理页的用户菜单，构造的 `RenderOptions` 使用默认值 `default`，
因此预览会自然展示样式声明的默认适配效果。

若把旋转只放在 `ImageProcessor`，正式输出会生效，但样式编辑器的竖图预览不会生效。
所以仍应在 `FrameRenderer` 外围统一解析最终方向并包裹完整渲染。

### 2.4 配置加载与编辑器往返

- `StyleManager._validate_config()` 是磁盘配置进入正式处理链路的校验入口。
- `StyleConfigFormData` 只显式识别已有顶层字段；目前仅对 `layout` 和 `colors`
  内的未知字段做透传。
- 若只向 FilmClip YAML 添加新的顶层字段，不扩展表单模型，使用样式编辑器加载再保存时会丢失该字段。
- 样式编辑器预览生成的字典不经过 `StyleManager`，因此核心解析函数也必须校验样式默认值。

### 2.5 用户设置持久化

图片处理页关闭时通过 `ConfigManager.save_last_used_settings()` 保存最近使用设置，启动时由
`_load_saved_config()` 恢复。新菜单应保存稳定内部值，而不是中文显示文本，避免未来调整文案
导致已有 `config.json` 无法恢复。

### 2.6 高斯二级缓存

高斯二级缓存键目前包含源图摘要、处理后尺寸、模式、预处理版本、半径和算法版本。
顺时针与逆时针旋转后的尺寸相同，但像素方向不同；若仍使用同一个
`source_cache_key`，切换方向时可能错误复用另一方向的模糊结果。

最终有效适配真实生效时，传给 `RenderBlurCache` 的局部缓存键必须加入方向后缀；不能修改
调用方长期持有的 `RenderOptions.source_cache_key` 本身。

### 2.7 源码逐项核查结论（2026-09-21 审阅补充）

方案 §2.1–§2.6 的断言已逐一对照源码核实成立，另有六项实施相关事实补充如下：

1. **`render_frame()` 内已有就地改写 options 的先例（反面教材）**：
   `renderer.py` 在 Logo 自动匹配分支中直接回写 `options.logo_filename`
   （`render_frame()` 内 `options.logo_filename = ...auto_match_logo(...)`）。
   该图对象由 GUI 页面跨多次渲染复用时存在同类污染风险。本方案的
   "不改写 `options.source_cache_key` / `options.portrait_adaptation`"红线
   由此更有必要：**有效方向与派生缓存键一律放局部变量**（见 §5.1 骨架）。
2. **v2.5.2-dev 的"竖图自动短版镜头名"与本功能互不干扰**：该逻辑在
   `ImageProcessingPage` 图片导入时按转正后 `h >= w` 一次性勾选复选框
   （`image_processing_page.py:774` 附近），判断基准是导入尺寸；本功能旋转
   只发生在渲染管线内部，不改变导入缩略图与宽高信息，该自动勾选不受影响。
   语义上也合理：照片本质仍是竖图，短版镜头名依然适用。**不需要也不应该**
   把该勾选逻辑迁移到旋转后的尺寸上。
3. **GUI 初始化时序安全**：`ImageProcessingPage.__init__` 顺序为
   `_setup_ui()`（创建全部卡片控件）→ `_load_saved_config()`。因此
   `_load_saved_config()` 中 `set_current_style()` 触发
   `_on_style_changed → _update_portrait_adaptation_hint()` 调用链时，
   `combo_portrait_adaptation` 已存在，无空引用风险。
4. **qfluentwidgets 1.11.2 API 已核实**：`ExpandGroupSettingCard.addGroup()`
   返回 `GroupWidget` 且提供 `setContent(content)`；`FluentIcon.ROTATE`
   存在（`common/icon.py`）。§6.2/§6.5 依赖的接口全部真实可用。
5. **FilmClip 变体 YAML 的 `name` 字段是历史遗留**：两个变体顶层
   `name` 均为"扩展宝丽来风格 Polaroid Motto (…)"，与文件夹名
   "胶片夹风格 FilmClip"不一致。不影响本变更（§8 只在 `name` 后插入新行），
   实施时**不要顺手"修复"该不一致**（超出本需求范围，避免无关 diff）。
6. **样式编辑器"拒绝加载"语义可直接落地**：`StyleCreatorPage._on_style_selected()`
   中 `StyleConfigFormData.load_from_file()` 已包裹 try/except，异常经
   `InfoBar.error("加载失败")` 呈现。因此 §7.1 的"非法默认值拒绝加载到表单"
   实现为 `from_yaml_dict()` 抛 `ValueError` 即可，无需新增回退分支。

## 3. 两层配置契约

### 3.1 运行时用户选项

`RenderOptions` 增加：

```python
portrait_adaptation: str = 'default'
```

合法值：

| 值 | 含义 |
|---|---|
| `default` | 跟随 `style_config.default_portrait_adaptation` |
| `none` | 强制不旋转，忽略样式默认值 |
| `clockwise` | 强制使用顺时针适配，忽略样式默认值 |
| `counterclockwise` | 强制使用逆时针适配，忽略样式默认值 |

`ProcessingConfig` 在“相框配置”区域同步增加同名字段和默认值，保持领域模型完整。

CLI 与现有批量 API 本期不新增命令行参数，现有调用点不传字段时自动使用 `default`，即遵循样式。
`RenderOptions` 新字段带默认值，不破坏任何现有构造点。

### 3.2 样式默认值

`default_portrait_adaptation` 是顶层可选字符串字段：

```yaml
name: 我的样式
default_portrait_adaptation: clockwise

layout:
  ...
```

采用顶层字段而不是放入 `layout` 的理由：它描述的是样式对输入方向的默认处理策略，作用于
创建布局引擎之前和完成整帧之后，不是画布内部的布局参数。

合法配置：

```yaml
# 不声明：默认不适配，推荐用于绝大多数现有样式
name: 普通样式
```

```yaml
# 明确默认顺时针
name: 横向排版样式
default_portrait_adaptation: clockwise
```

```yaml
# 显式关闭，语义与缺失相同；规范化保存时建议省略
name: 普通样式
default_portrait_adaptation: none
```

非法配置：

```yaml
default_portrait_adaptation: true
```

```yaml
default_portrait_adaptation: auto
```

字段必须是枚举字符串，不接受布尔值、`null`、大小写变体或未知值，以免静默选择错误方向。

### 3.3 变体规则

当前变体文件是彼此独立的完整配置，不存在从 `default.yaml` 自动继承字段的机制。因此同一
风格的每个可能被选中的变体都必须显式写入相同默认值。遗漏某个变体会导致行为随
`custom_text`、`location` 等运行时上下文变化。

## 4. 有效方向解析

新增 `src/utils/orientation_adaptation.py`，集中保存枚举常量、配置解析、优先级解析、无损旋转和
缓存键派生，避免 `StyleManager`、GUI 和渲染器各写一套规则。

建议常量与接口：

```python
ADAPT_DEFAULT = 'default'
ADAPT_NONE = 'none'
ADAPT_CLOCKWISE = 'clockwise'
ADAPT_COUNTERCLOCKWISE = 'counterclockwise'

STYLE_DEFAULT_KEY = 'default_portrait_adaptation'


def validate_style_default(style_config: dict) -> str:
    """返回样式默认值；字段缺失时返回 'none'，非法值抛出 ValueError。"""


def resolve_effective_adaptation(
    style_config: dict,
    user_choice: str,
) -> str:
    """按用户选择优先、样式默认兜底的规则返回最终方向。"""


def rotate_portrait_for_render(
    image: Image.Image,
    effective_adaptation: str,
) -> tuple[Image.Image, bool]:
    """仅在 height > width 且最终方向非 none 时旋转。"""


def restore_rendered_orientation(
    image: Image.Image,
    effective_adaptation: str,
    applied: bool,
) -> Image.Image:
    """仅在前置旋转真实应用过时执行反向旋转。"""


def build_adapted_source_cache_key(
    source_cache_key: Optional[str],
    effective_adaptation: str,
    applied: bool,
) -> Optional[str]:
    """为真实旋转过的源图附加方向后缀，隔离高斯二级缓存。"""
```

解析伪代码：

```python
style_default = validate_style_default(style_config)

if user_choice == 'default':
    effective = style_default
elif user_choice in {'none', 'clockwise', 'counterclockwise'}:
    effective = user_choice
else:
    raise ValueError(...)
```

即使 GUI 只会产生合法值，渲染器也必须校验 `RenderOptions`，覆盖 CLI、临时代码和未来调用方。

**实现约定（细化补充）**：

- `validate_style_default(style_config)` 接受**整份样式配置 dict**（与
  `resolve_effective_adaptation` 一致），内部读取 `STYLE_DEFAULT_KEY`；
  字段缺失返回 `'none'`；值不是四个合法枚举字符串之一（含布尔、`null`、
  大小写变体）时抛 `ValueError`，消息中点名字段名与合法值列表。
- `rotate_portrait_for_render()` 仅在 `image.height > image.width` 且
  `effective != 'none'` 时执行 `transpose()`；否则**返回原图对象引用本身**
  与 `applied=False`。"未适配路径零复制"是 §10.4"旧输出像素不变"的硬保证。
- `restore_rendered_orientation()` 只认 `applied` 标志做反向旋转，**不重新
  判断宽高**（渲染后的成品图必然回到竖图宽高，重判会误旋转）。
- `build_adapted_source_cache_key()`：`source_cache_key` 为 `None` 或
  `applied=False` 时原样返回输入值（含 `None`）；仅真实旋转时按
  §5.4 的后缀表派生新字符串。
- 本模块**不得引入任何 Qt / GUI 依赖**，保证 CLI 与临时验证脚本可直接
  import 单测（Phase 1 的测试因此无需启动 GUI）。

## 5. 核心渲染设计

### 5.1 在 `FrameRenderer.render_frame()` 包裹整帧渲染

在读取 `layout`、创建 `LayoutEngine` 之前执行：

```text
读取 RenderOptions.portrait_adaptation
  -> 与 style_config.default_portrait_adaptation 合并成最终方向
  -> 判断当前图像是否 height > width
  -> 必要时旋转输入
  -> 以旋转后的 image.size 创建 LayoutEngine / RenderContext
  -> 执行背景、矩形、原图、装饰、水印、文字、Logo 全部现有阶段
  -> 必要时反向旋转最终结果
  -> return
```

必须包裹全部渲染阶段，尤其不能只旋转原始照片层，否则画布、圆角、背景、文字、Logo
和水印仍会按竖向坐标计算，不符合“旋转后再进行处理，处理完成后再还原”的需求。

渲染器当前只有一个正常返回点，可在返回前恢复方向，不需要修改各子渲染器接口。前置旋转
返回新图，不修改调用方持有的原图对象；异常时沿现有异常链抛出，不存在需要回滚的共享状态。

**插入点骨架（细化补充，锚点为 `dev 90b637a` 的 renderer.py 行号）**：

```python
def render_frame(self, image, style_config, metadata=None, options=None):
    metadata = metadata or RenderMetadata()
    options = options or RenderOptions()

    # ── 竖图方向适配·前置（插在 LayoutEngine 创建【现 line 765】之前）──
    # 解析失败（非法样式默认值/非法用户值）→ ValueError 沿现有异常链抛出，
    # 由 ImageProcessor.process / 样式编辑器预览的既有 try/except 兜底
    effective_adaptation = resolve_effective_adaptation(
        style_config, options.portrait_adaptation)
    image, adaptation_applied = rotate_portrait_for_render(
        image, effective_adaptation)
    # 派生局部缓存键：绝不回写 options.source_cache_key
    # （render_frame 内已有就地改写 options.logo_filename 的反面先例，见 §2.7）
    effective_source_cache_key = build_adapted_source_cache_key(
        options.source_cache_key, effective_adaptation, adaptation_applied)
    if adaptation_applied:
        logger.info("竖图方向适配生效: %s（渲染期横图化，输出前还原）",
                    effective_adaptation)

    # ...全部现有阶段原样不动（LayoutEngine/RenderContext 自然按旋转后
    #    image.size 计算；装饰器取的 original_image_size 同为旋转后值）...

    # RenderBlurCache 构造点【现 line 795】改传局部键：
    blur_cache = RenderBlurCache(
        image, prepared_lru=options.prepared_blur_cache,
        source_cache_key=effective_source_cache_key)

    # ...背景/矩形/原图/装饰/文字/Logo 原样不动...

    # ── 竖图方向适配·还原（替换最后的 return）──
    return restore_rendered_orientation(
        image_with_text, effective_adaptation, adaptation_applied)
```

注意 `LayoutEngine(image.size, layout)` 与 `RenderContext(image.size, ...)`
【现 line 765–768】接收的都是**局部变量 `image`**，前置旋转赋值后无需改这两行；
这是把旋转放在函数开头（而非中途）的关键收益。

### 5.2 无损旋转映射

使用 Pillow 离散转置常量，不使用带重采样的任意角度旋转：

| 最终方向 | 渲染前 | 渲染后 |
|---|---|---|
| clockwise | `Image.Transpose.ROTATE_270`（顺时针 90°） | `Image.Transpose.ROTATE_90`（逆时针 90°） |
| counterclockwise | `Image.Transpose.ROTATE_90`（逆时针 90°） | `Image.Transpose.ROTATE_270`（顺时针 90°） |
| none | 不旋转 | 不旋转 |

`transpose()` 是整数像素重排，不引入插值模糊，并会自然交换宽高。

### 5.3 EXIF Orientation 的固定顺序

```text
文件像素 + EXIF Orientation
  -> ImageOps.exif_transpose() 得到视觉正向图
  -> 加载样式并解析用户选择
  -> 以正向宽高判断是否为竖图
  -> 按最终方向做适配旋转
  -> 完整渲染
  -> 反向旋转
  -> 保存视觉正向结果
```

不能在 `_apply_exif_orientation()` 之前判断，否则常见的“横向像素数据 + Orientation=6/8”
竖拍照片会被误判为横图。

最终像素方向与 EXIF 转正后的输入一致，因此现有输出 Orientation 归一化逻辑继续适用，
不为本功能写入 6 或 8，也不需要新增 EXIF 方向标签。

### 5.4 高斯二级缓存隔离

仅当适配真实应用时生成局部键：

```text
原键                         -> none / 横图 / 方形图
原键:portrait-adapt-cw       -> 竖图顺时针适配
原键:portrait-adapt-ccw      -> 竖图逆时针适配
```

创建 `RenderBlurCache` 时使用局部 `effective_source_cache_key`。不要就地改写
`options.source_cache_key`，因为 GUI 和批处理可能跨多次渲染复用同一个 `RenderOptions`。

横图和方形图即使用户或样式选择了适配，也仍使用原缓存键；它们的像素没有发生变化。

### 5.5 配置双层校验

1. `StyleManager._validate_config()` 调用统一函数，非法样式默认值时记录清晰错误并返回 `False`。
2. `FrameRenderer.render_frame()` 再解析样式默认值和用户选择，覆盖样式编辑器预览、临时代码及其他直接传字典的路径。

两层复用同一工具函数，不重复定义枚举或容错规则。

## 6. 图片处理页 GUI 细化方案（QFluentWidgets）

### 6.1 API 基线与组件决策

本地虚拟环境已核实为 `PySide6-Fluent-Widgets 1.11.2`。方案参考：

- [官方 ComboBox 组件说明](https://qfluentwidgets.com/pages/components/combobox/)
- [官方 Setting Card 说明](https://qfluentwidgets.com/pages/components/settingcard/)
- [官方设置系统指南](https://pyqt-fluent-widgets.readthedocs.io/en/latest/settings.html)
- [ExpandGroupSettingCard API](https://pyqt-fluent-widgets.readthedocs.io/en/latest/autoapi/qfluentwidgets/components/settings/expand_setting_card/index.html)

候选组件比较：

| 组件 | 官方定位 | 本项目结论 |
|---|---|---|
| `ComboBox` | 选项较多时使用的下拉选择器，支持 `userData`、`itemData()`、`findData()` 和 `currentIndexChanged` | **采用**；可直接加入现有 `ExpandGroupSettingCard`，不引入第二套配置系统 |
| `ComboBoxSettingCard` | 绑定 `OptionsConfigItem` 的独立设置卡 | 不采用；依赖全局 `qconfig`，而项目已有 `ConfigManager`，嵌入现有展开卡还会形成设置卡套娃 |
| `OptionsSettingCard` | 绑定 `OptionsConfigItem` 的可展开单选按钮组 | 不采用；四个长中文选项占用纵向空间，且同样依赖 `qconfig` |
| `SegmentedWidget` | 紧凑的分段导航/选择控件 | 不采用；四个长标签在右侧窄配置栏容易拥挤，且用户已明确要求“菜单” |

QFluentWidgets 官方文档说明 `ComboBoxSettingCard` / `OptionsSettingCard` 面向
`OptionsConfigItem`，官方设置系统通过 `QConfig` 和 `qconfig.load()` 管理配置。本项目已经使用
`ConfigManager` 读写 `config.json`，本功能不应为了一个菜单并行引入 `QConfig`，否则会产生两个
配置所有者和两套合法值校验。

### 6.2 控件层级与位置

继续复用现有 `ImageProcessingPage._create_frame_config_card()`：

```text
ExpandGroupSettingCard「相框配置」
  ├─ GroupWidget：背景填充样式
  ├─ GroupWidget：背景增强
  ├─ GroupWidget：竖图方向适配    [ ComboBox ▼ ]
  └─ GroupWidget：字重
```

新组放在“背景增强”和“字重”之间。理由：它改变整帧布局方向，属于相框渲染行为；既不是样式
选择本身，也不是拍摄信息或个性化文本。

通过官方 `ExpandGroupSettingCard.addGroup(icon, title, content, widget, stretch)` 接口添加，不直接操作
`viewLayout`：

```python
self.portrait_adaptation_group = card.addGroup(
    FluentIcon.ROTATE,
    '竖图方向适配',
    '仅对竖图生效；默认模式遵循当前样式',
    self.combo_portrait_adaptation,
    2,
)
```

本地 1.11.2 已确认存在 `FluentIcon.ROTATE`。保留 `GroupWidget` 返回值，用其官方
`setContent()` 接口动态展示当前样式默认值。

### 6.3 用 `userData` 绑定稳定值

官方 `ComboBox.addItem(text, icon=None, userData=None)` 支持把显示文本和业务值分离，读取时使用
`currentData()` / `itemData(index)`，恢复时使用 `findData(value)`。因此不再维护“中文文本 → 枚举值”
字典，也不依赖 `currentText()`：

```python
PORTRAIT_ADAPTATION_ITEMS = (
    ('默认（跟随样式）', 'default'),
    ('不旋转', 'none'),
    ('顺时针适配', 'clockwise'),
    ('逆时针适配', 'counterclockwise'),
)

self.combo_portrait_adaptation = ComboBox()
for text, value in PORTRAIT_ADAPTATION_ITEMS:
    self.combo_portrait_adaptation.addItem(text, userData=value)

self.combo_portrait_adaptation.setMinimumWidth(220)
self.combo_portrait_adaptation.setCurrentIndex(
    self.combo_portrait_adaptation.findData('default')
)
self.combo_portrait_adaptation.currentIndexChanged.connect(
    self._on_portrait_adaptation_changed
)
```

`addItems()` 只能批量加入文本，不能同时绑定四个不同的 `userData`，所以这里逐项调用 `addItem()`。

### 6.4 当前值读取与防御

页面增加唯一读取出口，防止生成、保存和提示文字各自实现不同的容错：

```python
_PORTRAIT_ADAPTATION_VALUES = {
    'default', 'none', 'clockwise', 'counterclockwise',
}


def _get_portrait_adaptation(self) -> str:
    """返回 GUI 当前稳定值；异常状态安全回退到 default。"""
    value = self.combo_portrait_adaptation.currentData()
    if value in self._PORTRAIT_ADAPTATION_VALUES:
        return value
    return 'default'
```

生成时直接进入运行时参数：

```python
options = RenderOptions(
    bg_fill_type=bg_key,
    decorations=decorations or None,
    logo_filename=logo_filename,
    saturation_override=(
        None if self.chk_enhance.isChecked() else 1.0
    ),
    source_cache_key=item.cache_key,
    prepared_blur_cache=self._blur_lru,
    portrait_adaptation=self._get_portrait_adaptation(),
)
```

### 6.5 动态辅助文案

四个选项中，“默认”会随样式变化。只显示“默认（跟随样式）”仍要求用户自己猜当前结果，所以
应在 GroupWidget 的内容行显示解析提示：

| 当前用户选择 | 内容行示例 |
|---|---|
| default + FilmClip | `仅对竖图生效；当前样式默认：顺时针适配` |
| default + 普通样式 | `仅对竖图生效；当前样式默认：不旋转` |
| none | `仅对竖图生效；已覆盖样式默认：不旋转` |
| clockwise | `仅对竖图生效；已覆盖样式默认：顺时针适配` |
| counterclockwise | `仅对竖图生效；已覆盖样式默认：逆时针适配` |

实现职责：

```python
def _on_portrait_adaptation_changed(self, _index: int):
    self._update_portrait_adaptation_hint()


def _update_portrait_adaptation_hint(self):
    user_choice = self._get_portrait_adaptation()
    # 当前样式配置仍通过 StyleManager 获取；只读取并格式化默认值。
    # 真实优先级解析继续由核心 orientation_adaptation 工具负责。
    ...
    self.portrait_adaptation_group.setContent(content)
```

`_on_style_changed()` 在现有 `_update_style_dependent_controls()` 之后调用提示刷新，但**不修改菜单当前
选项**。当前是 `default` 时，新样式在渲染时解析自己的默认值；当前是显式 `none` / 顺时针 /
逆时针时，继续覆盖新样式。

不使用 `InfoBar` 提示每次选项变化：该设置没有错误或需要确认，持续弹条会制造噪声；卡片内容行已
能稳定表达当前有效语义。

**提示解析口径（细化补充）**：`_update_portrait_adaptation_hint()` 读取样式默认值时调用
`self.style_manager.get_style_config(style_name)`（无 context）。文件夹样式的变体选择依赖
运行时 context（`custom_text` / `location` 等），提示所用变体可能与实际渲染变体不同
（如 custom_text 缺失时渲染选中 `no_custom_text.yaml`）。约定：

- 提示是**显示性参考**，不参与渲染决策；真实优先级解析只发生在 `render_frame()` 内。
- FilmClip 两个变体声明相同默认值，当前无实际偏差风险。
- `get_style_config` 每次读盘解析；本函数只在用户交互级事件（下拉切换/样式切换）触发，
  频率可接受，**不做缓存**，避免引入第二份样式配置副本。
- 提示刷新应包裹 try/except：样式读取失败时回退为通用文案"仅对竖图生效"，不让
  `_on_style_changed` 因提示异常中断后续逻辑。

### 6.6 持久化

`save_config()` 保存稳定值：

```python
default_config_manager.save_last_used_settings({
    ...,
    'portrait_adaptation': self._get_portrait_adaptation(),
})
```

恢复时用 `findData()`，不使用 `findText()`：

```python
saved_value = saved.get('portrait_adaptation', 'default')
index = self.combo_portrait_adaptation.findData(saved_value)
if index < 0:
    index = self.combo_portrait_adaptation.findData('default')

self.combo_portrait_adaptation.blockSignals(True)
self.combo_portrait_adaptation.setCurrentIndex(index)
self.combo_portrait_adaptation.blockSignals(False)
self._update_portrait_adaptation_hint()
```

只恢复 `default / none / clockwise / counterclockwise`；缺失、旧版本配置或非法值均回退 `default`。
保存内部值而不是中文标签后，即使未来调整显示文案，已有 `config.json` 仍可继续读取。

### 6.7 尺寸与展开卡片

- `ComboBox` 最小宽度设为 220 px，与现有背景/字重控件的 200 px 基线接近，同时完整容纳
  “默认（跟随样式）”。
- 通过 `addGroup()` 添加后会进入 `ExpandGroupSettingCard.widgets`，符合 `_adjustViewSize()` 的计算方式。
- 不设置固定高度，不直接操作 `viewLayout`，不覆盖 `_adjustViewSize()`。
- 实施后必须执行 `layout_debug.dump_expand_card(self.frame_config_card)`，验证：
  - 收起：`card.height() == card.card.height()`；
  - 展开：`spaceWidget.h >= view.h`；
  - 四项菜单展开时不被右侧面板或屏幕底部裁切。

### 6.8 可访问性与键盘行为

- 保持官方 `ComboBox` 默认键盘和焦点行为，不自定义鼠标事件。
- 设置 `setAccessibleName('竖图方向适配')`，便于辅助技术识别。
- 四个显示文本必须能单独表达含义，不仅依赖颜色或图标。
- `FluentIcon.ROTATE` 只作视觉提示；方向含义由菜单文本和内容行共同表达。

### 6.9 主题与视觉一致性

- 必须导入 `qfluentwidgets.ComboBox`，禁止替换成 Qt 原生 `QComboBox`。
- 不为本控件添加独立 QSS、背景色或圆角，让 QFluentWidgets 自动响应明暗主题和主题色。
- 不使用 `EditableComboBox`：四个值是封闭枚举，用户不能输入自定义文本。
- 不设置 `setMaxVisibleItems()`：只有四项，官方默认下拉行为已经足够。
- 不在选项前添加方向字符或 Emoji；旋转方向通过完整中文文本表达，避免不同字体下的基线偏移。

## 7. 样式编辑器设计

### 7.1 表单模型

`StyleConfigFormData` 增加：

```python
default_portrait_adaptation: str = 'none'
```

序列化规则：

- `none` 时省略顶层字段，保证普通旧样式输出简洁。
- `clockwise` / `counterclockwise` 时写出 `default_portrait_adaptation`。
- 其他值抛出 `ValueError`。

反序列化规则：

- 字段缺失时加载为 `none`。
- 字段存在时必须是合法枚举，否则拒绝加载到表单。

**实现位置与细节（细化补充）**：

- `to_yaml_dict()` 写入点在 `data['name']` 赋值之后、`colors` 构建之前，**显式省略**：

  ```python
  # name 之后：
  if self.default_portrait_adaptation != ADAPT_NONE:
      data['default_portrait_adaptation'] = self.default_portrait_adaptation
  ```

  不能依赖 `_clean_dict()` 完成省略——`'none'` 是非空字符串不会被清理，省略必须是
  显式分支（表单字段合法值已由下拉框封闭枚举保证）。
- `from_yaml_dict()` 在 `form.name = ...` 之后新增解析：字段存在且非法时
  `raise ValueError`。`StyleCreatorPage._on_style_selected()` 已有 try/except +
  `InfoBar.error("加载失败")`（见 §2.7 第 6 条），异常自然呈现给样式设计者，
  不需要本模型内做回退。
- 序列化顺序注意：`to_yaml_dict()` 末尾 `_clean_dict(data)` 递归清理不会影响
  本字段（值为非空字符串时保留、省略时不写入）。

### 7.2 样式设计者控件

在 `BasicInfoSection` 中增加“默认竖图适配”下拉框：

1. 不启用
2. 顺时针适配
3. 逆时针适配

这是**样式设计者默认值**，与图片处理页的**用户运行时选项**不是同一个控件：

- 样式编辑器决定 `default_portrait_adaptation`。
- 图片处理页决定 `RenderOptions.portrait_adaptation`。

仍使用 QFluentWidgets `ComboBox`，但只包含样式层的三个实际默认值：

```python
# basic_info_section.py 的 qfluentwidgets import 增加 ComboBox
self.default_portrait_adaptation_combo = ComboBox(container)
self.default_portrait_adaptation_combo.addItem(
    '不启用', userData='none')
self.default_portrait_adaptation_combo.addItem(
    '顺时针适配', userData='clockwise')
self.default_portrait_adaptation_combo.addItem(
    '逆时针适配', userData='counterclockwise')
self.default_portrait_adaptation_combo.setMinimumWidth(200)
self.default_portrait_adaptation_combo.currentIndexChanged.connect(
    self._on_changed)
```

这里不提供“默认（跟随样式）”，因为当前控件本身就在定义样式的默认值，再增加一层 default 会
造成递归语义。

把控件作为现有 `container` 的第三个 `QHBoxLayout` 行加入，整块 `container` 仍只调用一次
`addGroupWidget(container)`：

```text
基本信息
  样式名称        [................]
  文件名          [................]
  默认竖图适配    [不启用        ▼]
```

模型往返同样只使用 `userData`：

```python
def load_from_model(self, data):
    ...
    index = self.default_portrait_adaptation_combo.findData(
        data.default_portrait_adaptation)
    if index < 0:
        index = self.default_portrait_adaptation_combo.findData('none')
    self.default_portrait_adaptation_combo.setCurrentIndex(index)


def save_to_model(self, data):
    ...
    value = self.default_portrait_adaptation_combo.currentData()
    data.default_portrait_adaptation = (
        value if value in {'none', 'clockwise', 'counterclockwise'}
        else 'none'
    )
```

控件继续放在现有 `container` 内，并通过 `addGroupWidget(container)` 加入
`ExpandGroupSettingCard`，禁止直接操作 `viewLayout`。标准 `QVBoxLayout` 的 `sizeHint()` 可反映
新增行高度，无需覆盖 `_adjustViewSize()`，但仍需执行展开卡片布局验证。

### 7.3 预览一致性

样式编辑器构造的 `RenderOptions` 不显式覆盖新增字段，默认值为 `default`，因此：

- 横向样本不旋转。
- 竖向样本展示样式默认值的实际效果。
- 样式设计者切换默认方向后，现有去抖预览机制会重新渲染。

无需在 `StyleCreatorPage._render_preview()` 复制旋转逻辑。

## 8. FilmClip 配置变更

以下两个文件都要在顶层 `name` 后加入：

- `src/frame_styles/configs/胶片夹风格 FilmClip/default.yaml`
- `src/frame_styles/configs/胶片夹风格 FilmClip/no_custom_text.yaml`

目标结构：

```yaml
name: ...
default_portrait_adaptation: clockwise

colors:
  ...
```

不能只修改 `default.yaml`：当 `custom_text` 缺失时，`StyleManager` 会选中
`no_custom_text.yaml`，两个变体是独立加载的，不会继承默认文件字段。

“测试磨砂矩形 FilmClip Frost”是单独的测试样式，不在本需求范围内，不自动加入默认适配。

## 9. 文件级变更清单

| 文件 | 计划变更 |
|---|---|
| `src/utils/orientation_adaptation.py` | 新增枚举常量、样式默认校验、用户/样式优先级解析、前后旋转、缓存键派生 |
| `src/frame_styles/style_manager.py` | 在 `_validate_config()` 校验 `default_portrait_adaptation` |
| `src/core/renderer.py` | `RenderOptions` 增加用户选项；整帧渲染前后应用最终方向；使用方向隔离后的缓存键 |
| `src/gui_pyside/models/processing_config.py` | 相框配置模型增加 `portrait_adaptation='default'` |
| `src/gui_pyside/pages/image_processing_page.py` | 相框配置卡增加四选项菜单；生成时传值；保存/恢复稳定内部值 |
| `src/gui_pyside/models/style_config_form.py` | 增加样式默认值字段及 YAML 序列化/反序列化校验 |
| `src/gui_pyside/widgets/style_config_sections/basic_info_section.py` | 增加样式设计者使用的默认方向下拉框 |
| `src/frame_styles/configs/_STYLE_TEMPLATE.txt` | 增加样式默认值填写项及与用户覆盖关系说明 |
| `src/frame_styles/configs/胶片夹风格 FilmClip/default.yaml` | 加入 `default_portrait_adaptation: clockwise` |
| `src/frame_styles/configs/胶片夹风格 FilmClip/no_custom_text.yaml` | 加入 `default_portrait_adaptation: clockwise` |
| `docs/STYLE_GUIDE.md` | 增加样式默认值、用户优先级、变体重复声明规则与示例 |
| `docs/DEVELOPMENT.md` | 更新端到端管线、RenderOptions 和 EXIF/适配顺序 |

无需修改：

- `src/main.py`：CLI 本期不提供覆盖参数，现有 `RenderOptions()` 自动使用 `default`。
- `src/core/batch_processor.py`：现有批量路径自动跟随样式；新增字段有默认值，不改公开签名。
- `src/gui_pyside/pages/style_creator_page.py`：预览的默认 RenderOptions 会跟随样式声明。
- `src/gui_legacy/`：已封存，不纳入当前 GUI 功能扩展。

## 10. 验证方案

项目没有自动测试框架。实现时使用临时验证脚本和实际 CLI/GUI 操作，临时脚本不入库。

### 10.1 样式配置校验

| 样式字段 | 预期 |
|---|---|
| 缺失 | 合法，解析为 none |
| none | 合法，规范化保存时省略 |
| clockwise | 合法 |
| counterclockwise | 合法 |
| true / false / null / 数字 | 非法，StyleManager 拒绝加载 |
| auto / CW / 其他未知字符串 | 非法，错误日志点明字段与合法值 |

### 10.2 优先级矩阵

对用户四种选择 × 样式三种默认值执行 12 组优先级断言：

| 用户选择 | style none | style clockwise | style counterclockwise |
|---|---|---|---|
| default | none | clockwise | counterclockwise |
| none | none | none | none |
| clockwise | clockwise | clockwise | clockwise |
| counterclockwise | counterclockwise | counterclockwise | counterclockwise |

另测非法用户值，必须抛出清晰异常，不能静默回退。

### 10.3 旋转算法

构造四角颜色和文字均不对称的小型 RGB 图：

1. 顺时针前置旋转后四角位置正确。
2. 逆时针前置旋转后四角位置正确。
3. 前置旋转 + 对应反向恢复后，尺寸和全部像素与原图完全一致。
4. 横图、方形图返回内容不变，`applied=False`。
5. RGBA 图的 alpha 通道也能无损往返。

### 10.4 渲染行为

| 输入 | effective=none | effective=clockwise | effective=counterclockwise |
|---|---|---|---|
| 横图 | 旧输出像素不变 | 与 none 相同 | 与 none 相同 |
| 方形图 | 旧输出像素不变 | 与 none 相同 | 与 none 相同 |
| 竖图 | 当前竖向布局 | 先 CW 渲染、后 CCW 恢复 | 先 CCW 渲染、后 CW 恢复 |
| Orientation=6/8 竖拍图 | 转正后竖向布局 | 转正后再适配 | 转正后再适配 |

用非对称文字、Logo、水印和四边不同扩展量验证“整个结果”被还原，而不是只旋转照片层。

### 10.5 GUI 用户菜单

1. 四个 item 的 `itemData()` 依次为 `default / none / clockwise / counterclockwise`。
2. 初始 `currentData()` 为 `default`，显示“默认（跟随样式）”。
3. 普通样式 + 默认：不适配，内容行显示“当前样式默认：不旋转”。
4. FilmClip + 默认：顺时针适配，内容行显示“当前样式默认：顺时针适配”。
5. FilmClip + 不旋转：用户值覆盖样式，内容行显示“已覆盖样式默认：不旋转”。
6. FilmClip + 逆时针：用户值覆盖样式，执行逆时针适配。
7. 普通样式 + 顺时针：即使样式未声明，也执行顺时针适配。
8. 用户显式选择后切换样式，菜单不被重置，只刷新内容行。
9. 关闭并重新启动应用，四种稳定值均能通过 `findData()` 正确恢复。
10. 手动在 `config.json` 写入未知值，启动时安全回退 default。
11. 键盘 Tab 可聚焦菜单，方向键可切换选项，Enter/Space 可打开或确认，行为沿用官方控件。
12. 明暗主题切换后控件、下拉菜单和 GroupWidget 均无自定义样式残留。

### 10.6 缓存验证

在同一 GUI 会话中，对同一竖图依次渲染：none → clockwise → counterclockwise → clockwise。

- 三种有效状态的 L2 key 必须不同。
- 第二次 clockwise 应命中自己的缓存。
- counterclockwise 不得命中 clockwise 缓存。
- 横图切换菜单仍可复用原键，因为没有发生像素旋转。
- 用户 default + FilmClip clockwise 与用户显式 clockwise 应解析到同一个有效键并可共享缓存。

### 10.7 FilmClip 与样式编辑器

1. 有自定义文本时确认选中 FilmClip `default.yaml`，用户 default 下顺时针生效。
2. 无自定义文本时确认选中 `no_custom_text.yaml`，同样生效。
3. FilmClip 横图输出与改动前基线逐像素一致。
4. 样式编辑器加载 FilmClip 两个变体，默认方向显示为顺时针。
5. 加载、保存、重新加载后字段和值不丢失。
6. 切换样式编辑器的横/竖样本，只有竖向样本应用默认适配。
7. 其他未声明字段的内置样式在用户 default 下输出保持像素级兼容。
8. `BasicInfoSection` 三个选项的 `itemData()` 与模型枚举一致，未知模型值回退 `none`。

### 10.8 项目门禁

1. 激活虚拟环境后，对所有修改过的 `.py` 文件运行 `python -m py_compile`。
2. CLI 单张分别实测普通竖图和带 Orientation 标签的竖拍图；CLI 默认跟随样式。
3. CLI 批量使用至少“横图 + 普通竖图 + Orientation 竖拍图”的混合集合。
4. PySide6 图片处理页实际生成三种菜单状态的输出。
5. 对“相框配置”卡和 `BasicInfoSection` 执行 `layout_debug.dump_expand_card()`。
6. 收起时 `card.height() == card.card.height()`，展开时 `spaceWidget.h >= view.h`。
7. 检查 `debug_log.txt`，不得新增 ERROR / TRACEBACK。

建议语法检查命令：

```powershell
.\venv\Scripts\activate
python -m py_compile `
  src\utils\orientation_adaptation.py `
  src\frame_styles\style_manager.py `
  src\core\renderer.py `
  src\gui_pyside\models\processing_config.py `
  src\gui_pyside\pages\image_processing_page.py `
  src\gui_pyside\models\style_config_form.py `
  src\gui_pyside\widgets\style_config_sections\basic_info_section.py
```

## 11. 实施顺序（细化执行版）

> 锚点行号均相对 `dev 90b637a`；每个 Phase 结束时立即执行对应 `python -m py_compile`，
> 临时验证脚本放项目根、验证后删除、不入库（`tests/` 为空且不引入框架）。

### Phase 1：配置契约与纯算法

**改动文件与插入点**：

1. **新建 `src/utils/orientation_adaptation.py`**（约 100 行）：
   - 常量：`ADAPT_DEFAULT/ADAPT_NONE/ADAPT_CLOCKWISE/ADAPT_COUNTERCLOCKWISE`、
     `STYLE_DEFAULT_KEY`、后缀映射 `{'clockwise': ':portrait-adapt-cw', 'counterclockwise': ':portrait-adapt-ccw'}`。
   - 函数：`validate_style_default` / `resolve_effective_adaptation` /
     `rotate_portrait_for_render` / `restore_rendered_orientation` /
     `build_adapted_source_cache_key`，签名与约定见 §4。
   - 旋转映射按 §5.2：cw 前 `ROTATE_270` 后 `ROTATE_90`；ccw 前后互换。
   - 无 Qt / 无 PIL 之外的第三方依赖；`from PIL import Image` 仅为类型标注。
2. **`src/core/renderer.py`**：`RenderOptions` 在 `prepared_blur_cache` 字段后
   （现 line 91 之后）追加 `portrait_adaptation: str = 'default'`，带注释
   说明合法值与来源（本 Phase 仅加字段，不改渲染逻辑）。
3. **`src/gui_pyside/models/processing_config.py`**：相框配置区
   `enhance_background` 后追加 `portrait_adaptation: str = "default"`。
4. **`src/frame_styles/style_manager.py`**：`_validate_config()` 在 `return True`
   （现 line 307）之前插入：

   ```python
   # 竖图方向适配默认值校验（可选顶层字段；缺失=none，非法值拒绝加载）
   try:
       validate_style_default(config)
   except ValueError as e:
       self.logger.error(f"配置字段非法: {e}")
       return False
   ```

   （`from src.utils.orientation_adaptation import validate_style_default` 置于文件头部。）

**验证（临时脚本 `_tmp_verify_orientation.py`）**：

- §10.1 七行样式字段矩阵 + §10.2 十二组优先级矩阵 + 非法用户值抛异常断言。
- §10.3 无损旋转：四角异色 RGB 图与 RGBA 图的往返逐像素相等（`list(a.getdata()) == list(b.getdata())`）、
  横图/方图返回原对象引用且 `applied=False`。
- `build_adapted_source_cache_key`：None 透传 / 未应用透传 / cw、ccw 后缀正确。

**门禁**：`py_compile` 四个 `.py`；脚本全绿后删除。

建议提交：`feat: 增加竖图方向适配配置模型与解析`

### Phase 2：渲染管线与缓存

**改动文件**：仅 `src/core/renderer.py`，三处插入（完整骨架见 §5.1）：

1. `render_frame()` 开头、`LayoutEngine(image.size, layout)`【现 line 765】之前：
   解析 effective → 前置旋转 → 派生局部缓存键。
2. `RenderBlurCache` 构造点【现 line 795–797】：`source_cache_key=options.source_cache_key`
   改为 `source_cache_key=effective_source_cache_key`。
3. 尾部 `return image_with_text`【现 line 885】改为经 `restore_rendered_orientation()` 返回。

**验证（临时脚本 `_tmp_verify_render_adapt.py`，绕过 ImageProcessor 直调 render_frame）**：

- 构造非对称竖图（四边不同纯色条 + 一角标记）+ 非对称样式（四边不同扩展量 + 底部文字）：
  - `effective=none`：输出与改动前基线逐字节一致（回归保证）。
  - `cw`/`ccw`：输出尺寸 == 输入竖图尺寸；标记角位置验证"整帧还原"而非仅照片层。
  - 横图/方图：三种 effective 输出全一致。
- 缓存隔离：传入同一 `PreparedBlurLRU` 与 `source_cache_key`，依次按 none → cw → ccw → cw
  渲染同一竖图（样式含高斯背景或模糊矩形），断言 `PreparedBlurLRU.stats()` 中
  第 4 次渲染命中前 2 次 cw 条目、ccw 不命中 cw（miss 数符合预期）。
- `RenderOptions` 共享对象断言：渲染前后 `options.source_cache_key` 与
  `options.portrait_adaptation` 值不变（防污染回归断言）。

**门禁**：`py_compile` renderer.py；CLI 单张实测普通竖图与 Orientation=6 竖拍图各一次。

建议提交：`feat: 在整帧渲染管线接入竖图方向适配`

### Phase 3：图片处理页用户菜单

**改动文件**：仅 `src/gui_pyside/pages/image_processing_page.py`：

1. `_create_frame_config_card()`【现 line 532–559】：在"背景增强"组与"字重"组之间
   插入四选项 `ComboBox` 组（代码见 §6.2/§6.3；`addGroup` 返回值存
   `self.portrait_adaptation_group`）。
2. 新增方法：`_get_portrait_adaptation()`（§6.4）、`_on_portrait_adaptation_changed()`、
   `_update_portrait_adaptation_hint()`（§6.5，含 try/except 回退通用文案）。
3. `_on_style_changed()`【现 line 655–657】：`_update_style_dependent_controls()`
   之后追加 `self._update_portrait_adaptation_hint()`。
4. 生成点 `RenderOptions(...)`【现 line 1251–1258】：追加
   `portrait_adaptation=self._get_portrait_adaptation()`。
5. `save_config()`【现 line 1421–1428】：字典追加
   `'portrait_adaptation': self._get_portrait_adaptation()`（稳定内部值；
   **不回改**现有 `bg_fill`/`font_weight` 等旧键的中文文本格式，保持既有
   config.json 兼容）。
6. `_load_saved_config()` 末尾：按 §6.6 的 `findData` + `blockSignals` 模式恢复，
   并调用一次 `self._update_portrait_adaptation_hint()`。

**验证**：§10.5 清单 1–12 逐项实操（重点：切样式不重置菜单、重启恢复、
config.json 手写非法值回退 default）；`layout_debug.dump_expand_card(self.frame_config_card)`
收起/展开断言；`debug_log.txt` 无新增 ERROR。

**门禁**：`py_compile` image_processing_page.py + processing_config.py（若 Phase 1 未含）。

建议提交：`feat: 相框配置增加竖图方向适配菜单`

### Phase 4：样式编辑器与 FilmClip

**改动文件**：

1. `src/gui_pyside/models/style_config_form.py`：
   - `StyleConfigFormData` 在 `filename` 字段后追加
     `default_portrait_adaptation: str = 'none'`。
   - `to_yaml_dict()`：`data['name']` 后按 §7.1 显式省略逻辑写入。
   - `from_yaml_dict()`：`form.name` 后解析；非法值 `raise ValueError`。
   - 文件头部 `from src.utils.orientation_adaptation import ADAPT_NONE, validate_style_default`。
2. `src/gui_pyside/widgets/style_config_sections/basic_info_section.py`：
   - import 增加 `ComboBox`；`_setup_ui()` 在 row2 之后加第三行
     `default_portrait_adaptation_combo`（三选项 + userData，见 §7.2）。
   - `load_from_model()` / `save_to_model()` 增加 §7.2 的往返代码。
3. `src/frame_styles/configs/胶片夹风格 FilmClip/default.yaml` 与
   `no_custom_text.yaml`：顶层 `name:` 行之后各插入
   `default_portrait_adaptation: clockwise`（§8；不动 `name` 的历史遗留值）。

**验证**：§10.7 清单 1–8 逐项（样式编辑器加载 FilmClip 显示"顺时针适配"、
加载→保存→重载字段不丢、横/竖样本预览行为、`BasicInfoSection` itemData 断言）；
`layout_debug.dump_expand_card` 验证基本信息卡。

**门禁**：`py_compile` 两个 `.py`；YAML 用 `yaml.safe_load` 冒烟解析。

建议提交：`feat: 为 FilmClip 默认启用顺时针适配`

### Phase 5：文档与总验收

1. `_STYLE_TEMPLATE.txt`：新增 `default_portrait_adaptation` 填写项（合法值、
   缺省行为、与用户覆盖的关系）。
2. `docs/STYLE_GUIDE.md`：样式默认值语义、优先级表、**变体重复声明规则**
   （同一文件夹每个变体都必须显式声明，遗漏会随运行时上下文漂移）、示例。
3. `docs/DEVELOPMENT.md`：端到端管线图补"竖图方向适配"步骤（EXIF 转正 →
   样式加载 → 方向解析 → 前置旋转 → 整帧渲染 → 反向旋转）；`RenderOptions`
   字段表更新。
4. 总验收：§10.8 全部门禁 + 未声明适配的全部内置样式在用户 default 下输出
   与基线逐像素一致（抽样 3 个样式）+ 全部门禁通过后按 SemVer minor 申请
   `new-version` 合入 mainline（版本号此时才确定）。

建议提交：`docs: 竖图方向适配文档同步`（或并入 Phase 4 提交）

## 12. 风险与边界

| 风险 | 规避措施 |
|---|---|
| “默认”与“不旋转”被混淆 | GUI 明确显示两个独立选项，文档提供优先级表 |
| 切换样式篡改用户显式选择 | 样式变更不改菜单，渲染时动态解析 |
| 用原始像素宽高判断，漏掉 Orientation 竖拍图 | 先 `exif_transpose()`，后在渲染器判断 |
| 只旋转照片，文字/Logo/水印方向不符合需求 | 在 `render_frame()` 最外层包裹全部阶段 |
| 样式编辑器预览与正式输出不一致 | 实现在渲染器，预览使用 user_choice=default |
| FilmClip 变体切换后默认值丢失 | 两个实际 YAML 变体都显式声明 |
| 样式编辑器保存时丢顶层字段 | 表单模型显式支持默认字段 |
| CW/CCW 高斯缓存串用 | 按最终有效方向追加缓存键后缀 |
| 共享 RenderOptions 被污染 | 只构造局部有效方向与局部缓存键，不改写用户选择字段 |
| 方形图方向定义含糊 | 明确只认 `height > width` |
| 旋转引入插值损失 | 使用 `Image.Transpose` 离散 90°转置 |
| 共享 `RenderOptions` 被就地改写 | 有效方向/派生键只用局部变量；Phase 2 加"渲染前后字段值不变"回归断言 |
| 提示文案变体口径与实际渲染变体不一致 | 提示为显示性参考（无 context 解析），渲染决策只在 render_frame 内（§6.5） |
| 样式编辑器提示异常中断 `_on_style_changed` | 提示刷新包裹 try/except，失败回退通用文案 |
| 实施者顺手"修复" FilmClip `name` 历史遗留不一致 | 明确禁止无关 diff（§2.7 第 5 条） |

本期不做：

- 不根据 EXIF 相机品牌、机型或焦段自动选择顺/逆时针。
- 不增加 CLI 覆盖参数；CLI 和现有批量 API 使用 `default`。
- 不改变源文件、导入缩略图或原图预览的视觉方向。
- 不让变体文件继承 `default.yaml`；仍遵守当前独立完整配置规则。
- 不迁移或扩展封存的 Streamlit GUI。

## 13. 完成定义

1. 图片处理页存在“默认（跟随样式）/不旋转/顺时针适配/逆时针适配”四选项菜单。
2. 用户显式不旋转/顺时针/逆时针选择优先于样式默认值，切换样式不重置用户选择。
3. 未声明默认值的样式在用户 default 下保持旧行为。
4. FilmClip 的两个变体都声明 `default_portrait_adaptation: clockwise`。
5. 适配只作用于 EXIF 转正后的严格竖图。
6. 输入旋转、完整渲染、输出反向旋转的顺序可由日志和非对称样片验证。
7. CLI 单张、CLI 批量、PySide6 图片处理页、样式编辑器预览遵循同一解析逻辑。
8. 高斯缓存不会在 none、clockwise 和 counterclockwise 三种最终行为之间错误复用。
9. 用户选项能以稳定内部值保存和恢复；非法持久化值安全回退 default。
10. 未配置适配的现有样式输出保持像素级兼容。
11. 所有修改过的 Python 文件语法检查通过，GUI 操作验证通过，日志无新增错误。
