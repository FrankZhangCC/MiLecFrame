# 样式配置指南 (Style Guide)

> 面向样式创作者：本文档说明如何编写和修改 `.yaml` 样式配置文件，控制相框的布局、文字、颜色、字体和 Logo 效果。

## 目次

1. [快速入门](#1-快速入门)
2. [文件组织规范](#2-文件组织规范)
3. [布局配置](#3-布局配置)
   - [3.5 自定义矩形（rectangles）](#35-自定义矩形-rectangles)
4. [元素定位系统](#4-元素定位系统)
5. [文本内容配置](#5-文本内容配置)
6. [颜色配置](#6-颜色配置)
7. [字体配置](#7-字体配置)
8. [Logo 配置](#8-logo-配置)
9. [水印配置](#9-水印配置)
10. [常见问题 FAQ](#10-常见问题-faq)
11. [附录A：完整 default.yaml 示例](#附录a完整-defaultyaml-示例)
12. [附录B：_STYLE_TEMPLATE.txt 使用指南](#附录b_styletemplatetxt-使用指南)

---

## 1. 快速入门

### 什么是样式配置文件？

一个 YAML 文件控制一张照片添加相框后的**所有视觉效果**——画布大小、文字位置、字体颜色、Logo 大小等。每种样式对应一个文件夹，文件夹内存放一个 `default.yaml`。

### 最简单的样式

```yaml
name: "我的样式"
layout:
  expand_canvas:
    enabled: true
    bottom: 0.12
  info_position:
    camera_lens:
      position: "bottom-left"
      alignment: "left"
      margin_left: 0.03
      margin_bottom: 0.04
    timestamp_author:
      relative_to: "camera_lens"
      relative_position: "below"
      alignment: "left"
      relative_margin: 0.01
fonts:
  size_ratio: 0.015
  sizes:
    camera_lens: 0.022
```

这个 20 行的样式会：在照片底部扩展 12% 的高度 → 在左下角显示相机和镜头信息 → 在它下方显示拍摄时间和作者。

### 创建新样式的三种方式

| 方式 | 适合场景 |
|------|---------|
| **GUI 样式编辑器**（推荐） | 可视化新建/修改样式，修改后实时预览，完成后导出 YAML |
| **复制现有样式** | 以已有样式为基础微调，复制整个文件夹后修改 `default.yaml` |
| **填写模板 + AI 生成** | 在 `_STYLE_TEMPLATE.txt` 中勾选和填写需求，交给 AI 生成 YAML |

### 文件存放位置

```
src/frame_styles/configs/样式名称/
├── default.yaml       # ← 这是你要编写的文件
├── thumbnail.png      # 可选，512×512 预览图
└── no_location.yaml   # 可选，地点缺失时的变体
```

---

## 2. 文件组织规范

### 2.1 基本结构

- **每种样式必须是一个文件夹**（即使只有一个变体）。文件夹名 = GUI 中显示的样式名称。
- **`default.yaml` 必须存在**——程序在无法匹配变体时回退到此文件。
- **传统单文件样式**（将 `样式名.yaml` 直接放在 `configs/` 根目录）已不再推荐。

### 2.2 缩略图

样式选择器以横向缩略图滚动列表展示。每种样式建议放置一张预览图：

| 规范 | 要求 |
|------|------|
| 文件名 | `thumbnail.png`（推荐）或 `thumbnail.jpg` / `thumbnail.jpeg` |
| 尺寸 | 512 × 512 像素（正方形） |
| 存放位置 | 样式文件夹根目录，与 `default.yaml` 同级 |

未放置缩略图时，对应位置以灰色背景 + 样式名称文字占位。

### 2.3 变体系统

当同一个样式需要根据"是否有拍摄地点""是否有作者"等条件**自动切换布局**时，使用变体。

#### 命名规则

| 文件名 | 匹配条件 |
|--------|---------|
| `default.yaml` | 兜底，无匹配变体时使用 |
| `no_{field}.yaml` | 当 `{field}` 的值为空时匹配 |
| `no_{field1}_no_{field2}.yaml` | 多个字段同时为空时匹配，优先级高于单字段变体 |

支持的 `{field}` 名称：`location`、`author`、`custom_text`、`timestamp`。

#### 示例

```
底部信息条 Bottom Bars/
├── default.yaml                  # 所有字段都有数据时使用
├── no_location.yaml              # 没有拍摄地点时使用
├── no_author.yaml                # 没有作者时使用
└── no_location_no_author.yaml    # 两者都没有时使用（优先级最高）
```

#### 匹配算法（通俗解释）

程序会检查你当前处理的照片有没有"地点""作者"等数据。如果"地点"和"作者"都有，用 `default.yaml`；如果只有"地点"没有"作者"，用 `no_author.yaml`；两者都没有，用 `no_location_no_author.yaml`。

#### 精简规范

变体文件中**与缺失字段相关的所有配置项应全部移除**，包括：

- `colors` 中的 `custom_{field}_{light/dark}_color`
- `fonts.sizes` 中的 `{field}` 条目
- `layout.info_position` 中的 `{field}` 条目

只需保留实际生效的配置项，避免无效配置残留。

---

## 3. 布局配置

### 3.1 坐标系概念

理解四个概念后，所有布局参数都能一眼看懂：

```
┌─────────────────────────────────────────┐  ← 画布（canvas）
│  ┌──────────────────────────────────┐   │
│  │         padding 安全区域          │   │
│  │  ┌────────────────────────────┐  │   │
│  │  │                            │  │   │
│  │  │       原始照片区域          │  │   │
│  │  │       (original image)     │  │   │
│  │  │                            │  │   │
│  │  └────────────────────────────┘  │   │
│  │  ← 文字和Logo只能放在这个区域内   │   │
│  └──────────────────────────────────┘   │
│  ← 背景填充覆盖整个画布                  │
└─────────────────────────────────────────┘
```

| 概念 | 定义 | 作用 |
|------|------|------|
| **原图** | 你拍摄的原始照片 | 所有计算的起点 |
| **参照边（short side）** | 原图的短边长度（像素） | 所有浮点比例系数的基准。`size_ratio: 0.015` 表示字号 = 短边 × 1.5% |
| **画布** | 经过 `expand_canvas` 扩展后的总绘图区域 | 背景填充覆盖这里 |
| **安全区域（padding）** | 从画布四边向内收缩得到的矩形 | 文字和 Logo 的活动范围，**高于一切 margin** |

> **为什么所有尺寸都用比例？** 保证同一份样式配置在横版 6000×4000 和竖版 4000×6000 的照片上视觉效果一致。

### 3.2 画布扩展（expand_canvas）

在原始照片四周扩展出额外的画布空间，用于放置文字和 Logo。

```yaml
layout:
  expand_canvas:
    enabled: true        # 开关
    top: 0.02            # 顶部扩展 = 参照边 × 2%
    bottom: 0.12         # 底部扩展 = 参照边 × 12%（文字通常放在下面，多留空间）
    left: 0.0
    right: 0.0
```

- 每边的扩展量独立设置，不用的方向可以写 `0` 或省略
- `enabled: false` 时画布 = 原图，不能放置外部元素

### 3.3 安全区域（padding）

限制文字和 Logo 不能超出画布的指定边界。

```yaml
layout:
  padding:
    top: 0.01            # 从画布顶边向内 1% 为安全上界
    bottom: 0.01         # 从画布底边向内 1% 为安全下界
    left: 0.02           # 从画布左边向内 2% 为安全左界
    right: 0.02          # 从画布右边向内 2% 为安全右界
```

- 不影响原始照片的位置
- **优先级**：padding 对所有元素的最终坐标有截断权，即 `padding > margin`
- 四边默认值均为 `0`（= 画布边界）

### 3.4 原图圆角（corner_radius）

为原始照片的四角添加圆角裁切。

```yaml
layout:
  corner_radius:
    enabled: true
    top_left: 0.01        # 左上角半径 = 参照边 × 1%
    top_right: 0.01
    bottom_left: 0.01
    bottom_right: 0.01
```

- `enabled: false` 或整个字段缺失时，完全跳过（零额外开销）
- 四个角的半径独立控制，设为 `0` 表示该角保持直角
- 与画布扩展和 padding 完全兼容，圆角仅作用于原图，不影响扩出区域

### 3.5 自定义矩形（rectangles）

在背景层之上、原图层之下绘制装饰性矩形色块，可用于添加底部渐变条、背景分隔线等视觉元素。

```yaml
layout:
  rectangles:
    rect_01:
      width_ratio: 0.85          # 宽度 = 参照边 × 比例
      height_ratio: 0.04         # 高度 = 参照边 × 比例
      opacity: 0.8               # 透明度 0.0-1.0
      position: "top"            # 标准锚点
      alignment: "both-center"   # 对齐方式
      margin_top: 0.01           # 边距（可选）
      corner_radius:             # 圆角（可选）
        top_left: 0.005
        top_right: 0.005
        bottom_left: 0
        bottom_right: 0
    rect_02:
      width_ratio: 1.1
      height_ratio: 0.15
      opacity: 0.5
      position: "bottom"
      alignment: "both-center"
      margin_bottom: 0.05
```

#### 命名规则

- key 采用**补零编号**：`rect_01`、`rect_02`、`rect_03`…… 以此类推
- 矩形按键名排序绘制（`rect_01` 最先，位于最底层）
- 颜色在 `colors` 区域中定义（见 [§6 颜色配置](#6-颜色配置)）

#### 矩形专用参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `width_ratio` | `float` | **必填** | 宽度比例，相对于原图参照边（短边） |
| `height_ratio` | `float` | **必填** | 高度比例，相对于原图参照边（短边） |
| `opacity` | `float` | `1.0` | 透明度 0.0-1.0 |
| `corner_radius` | `dict` | — | 四角独立圆角（省略则直角，缩放基准 = 参照边） |

#### 定位参数

矩形复用 [§4.2 绝对定位系统](#42-绝对定位) 的全部锚点和对齐规则，支持 `position`、`alignment`、`margin_*` 等所有参数。**与文字元素不同，矩形不受 `padding` 安全区域约束**，可超出安全区域绘制到画布边界。

#### 图层位置

```
┌────────────────────────┐
│     背景填充层          │
│  ┌──────────────────┐  │
│  │   ★ 矩形层 ★     │  │  ← rectangles 在此
│  └──────────────────┘  │
│  ┌──────────────────┐  │
│  │     原图          │  │
│  └──────────────────┘  │
│      文字 / Logo 层    │
└────────────────────────┘
```

矩形在背景之上、原图之下，文字和 Logo 仍然覆盖在矩形上方。

---

## 4. 元素定位系统

### 4.1 什么是"元素"？

样式中的"元素"是指可以在照片上绘制的内容块：

- **`info_position` 中声明的 text_type**：如 `camera_lens`、`exif`、`timestamp_author` 等（文本来源于 EXIF 数据或用户输入）
- **`defined_texts`**：配置文件中写死的固定文字
- **`custom_text`**：用户在 GUI 中输入的个性文字
- **`rectangles`**：装饰性矩形色块（不受 padding 约束）
- **Logo**：品牌标识图片

所有元素的定位方式分为两种，互斥（`relative_to` 有值时使用相对定位）。

### 4.2 绝对定位

以**原始照片边界**为参考系，通过"挂载点 + 边距"控制元素位置。

#### 三参数

| 参数 | 可选值 | 默认值 | 含义 |
|------|--------|--------|------|
| `placement` | `inside` / `outside` | `outside` | 元素放在原图矩形内部还是外部 |
| `position` | 见下表 14 种锚点 | `bottom` | 元素挂载到原图的哪个位置 |
| `alignment` | `left` / `center` / `right` / `both-center` / 组合格式 | `center` | 元素自身相对于锚点的对齐方式 |

- `inside`：元素在原图内部，margin 从边界向内偏移
- `outside`：元素在原图外部，margin 从边界向外偏移
- `both-center`：元素中心点与锚点完全重合（水平和垂直同时居中），margin 作为该偏移量

#### 14 种 position 锚点

| position | 含义 | alignment 控制 |
|----------|------|---------------|
| `top-left` / `tl` | 原图左上角 | —（固定） |
| `top-center` / `tc` | 原图顶部居中 | —（固定） |
| `top-right` / `tr` | 原图右上角 | —（固定） |
| `top` | 原图顶部 | 水平轴 |
| `bottom-left` / `bl` | 原图左下角 | —（固定） |
| `bottom-center` / `bc` | 原图底部居中 | —（固定） |
| `bottom-right` / `br` | 原图右下角 | —（固定） |
| `bottom` | 原图底部 | 水平轴 |
| `left` | 原图左侧 | 垂直轴 |
| `right` | 原图右侧 | 垂直轴 |
| `center` | 画布中心（不受 margin 影响） | —（固定） |

#### alignment 对齐规则

| alignment 值 | 横向表现 | 纵向表现 |
|---|---|---|
| `left` / `top-left` / `bottom-left` | 元素左边缘对锚点 | — |
| `right` / `top-right` / `bottom-right` | 元素右边缘对锚点 | — |
| `top` / `top-left` / `top-right` | — | 元素顶边对锚点 |
| `bottom` / `bottom-left` / `bottom-right` | — | 元素底边对锚点 |
| `center`（默认） | 元素水平居中于锚点 | 元素垂直居中于锚点 |
| `both-center` | 元素水平居中于锚点 | 元素垂直居中于锚点 |

#### margin 边距体系

margin 是元素相对于原图边界的偏移量，四个方向独立：

| 字段 | 说明 |
|------|------|
| `margin` | 统一边距，设置后覆盖四方向的初始值 |
| `margin_top` / `margin_bottom` / `margin_left` / `margin_right` | 各方向独立边距，覆盖 `margin` 统一值 |

- 浮点数 → 按参照边比例计算（如 `0.02` = 参照边的 2%）
- 整数 → 绝对像素值
- 优先级：`margin_方向` > `margin` > 默认 `0`
- 推荐使用浮点数比例以保持响应式

#### 绝对定位完整示例

```yaml
camera_lens:
  placement: outside
  position: "bottom-left"
  alignment: "left"
  margin_bottom: 0.022
  margin_left: 0.02
```

效果：相机和镜头信息放在原图左下角外侧下方 2.2% 处，左对齐原图左边缘向右 2% 处。

### 4.3 相对定位

以**另一个已存在的元素**为参考，相对于它放置当前元素。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `relative_to` | 文字 | 必填 | 参考元素名称（如 `"camera_lens"`、`"exif"`） |
| `relative_position` | 文字 | `"after"` | 6 种方向：`after`/`below`（下方）、`before`/`above`（上方）、`right-of`（右侧）、`left-of`（左侧） |
| `relative_margin` | 浮点数 | `0.01` | 与参考元素的间距 = 参照边 × 比例 |
| `alignment` | 文字 | `"center"` | 在参考元素范围内的对齐方式 |
| `offset_x_ratio` | 浮点数 | `0` | x 轴微调偏移 |
| `offset_y_ratio` | 浮点数 | `0` | y 轴微调偏移 |

#### alignment 在相对定位中的语义

| relative_position | alignment 控制的轴 | 对齐基准物 |
|---|---|---|
| `after` / `below` | 水平轴（`left` 左对齐 / `right` 右对齐 / 其他居中） | 参考元素的宽度 |
| `before` / `above` | 水平轴（同上） | 参考元素的宽度 |
| `right-of` | 垂直轴（`top` 顶对齐 / `bottom` 底对齐 / 其他居中） | 参考元素的高度 |
| `left-of` | 垂直轴（同上） | 参考元素的高度 |

#### 相对定位示例

```yaml
timestamp_author:
  relative_to: "camera_lens"
  relative_position: "below"
  alignment: "left"
  relative_margin: 0.01
```

效果：拍摄时间+作者放在 `camera_lens` 正下方，间距为参照边的 1%，左对齐 `camera_lens` 的左边缘。

### 4.4 树级组合定位（tree_align）

将一组通过 `relative_to` 串联的元素（如 A → B → C → D）作为一个**整体**进行定位。

**适用场景**：多段文字组成一条水平链，希望整条链在照片上居中。

**启用方式**：在链的根元素（没有 `relative_to` 的元素）上设置 `tree_align: true`：

```yaml
defined_texts:
  defined_text_01:
    content: "FL"
    position: "bottom"
    alignment: "center"
    tree_align: true          # ← 把整条链当作一个整体来定位
    margin_bottom: 0.07
  defined_text_02:
    content: "35mm"
    relative_to: "defined_text_01"
    relative_position: "right-of"
```

- 未声明 `tree_align: true` 的依赖链不受影响
- 单元素（没有子元素）自动跳过，不必刻意移除

### 4.5 定位参数速查表

#### 绝对定位参数（根元素）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `placement` | `"inside"` / `"outside"` | `"outside"` | 元素在原图内侧还是外侧 |
| `position` | 14 种锚点 | `"bottom"` | 参见 [§4.2 锚点表](#14-种-position-锚点) |
| `alignment` | `"left"` / `"center"` / `"right"` / `"both-center"` | `"center"` | 元素自对齐 |
| `margin` | `float` / `int` | `0` | 统一边距 |
| `margin_top` / `_bottom` / `_left` / `_right` | `float` / `int` | `0` | 各方向独立边距 |
| `tree_align` | `bool` | `false` | 启用树级组合定位 |

#### 相对定位参数（`relative_to` 元素）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `relative_to` | 文字 | 必填 | 参考元素名称 |
| `relative_position` | 6 种方向 | `"after"` | 参见 [§4.3](#43-相对定位) |
| `alignment` | `"left"` / `"center"` / `"right"` | `"center"` | 在参考元素范围内的对齐 |
| `relative_margin` | `float` | `0.01` | 间距比例 |
| `offset_x_ratio` / `offset_y_ratio` | `float` | `0` | 微调偏移 |

---

## 5. 文本内容配置

### 5.1 info_position — 显示 EXIF 和拍摄信息

在 `info_position` 中声明哪些信息要显示。**未声明的字段不会渲染**。

| key | 输出示例 | 数据来源 |
|-----|---------|---------|
| `exif` | `35mm, f/2.8, 1/125s, ISO200` | EXIF 格式化曝光参数 |
| `timestamp` | `2025.01.15 14:30:00` | EXIF 拍摄时间 |
| `timestamp_author` | `2025.01.15 14:30:00 by Frank` | 时间 + 作者合并 |
| `camera` | `Leica Q3` | 相机品牌 + 型号 |
| `camera_make` | `Leica` | 仅相机品牌 |
| `lens` | `Summilux 28mm f/1.7` / `28mm` | 镜头型号（受短版开关控制） |
| `camera_lens` | `Leica Q3 \| Summilux 28mm` | 品牌 + 型号 + 镜头（由镜头显示模式控制） |
| `author` | `Frank` | 用户输入 |
| `location` | `Shanghai` | 用户输入 |
| `gps` | `40°26'46.1"N 79°56'56.1"W` | EXIF GPS 坐标 |
| `focal_length_formatted` | `35mm` | 35mm 等效焦距 |
| `aperture_formatted` | `f/2.8` | 光圈值 |
| `shutter_speed_formatted` | `1/125s` | 快门速度（已格式化） |
| `iso_formatted` | `ISO200` | 感光度 |

**镜头显示模式** 和 **使用短版镜头名** 这两个选项在 GUI 中控制，影响 `camera_lens` 和 `lens` 的输出格式。详见 [GUI 功能指南](../README.md#镜头显示控制)。

### 5.2 defined_texts — 固定文字

在配置文件中直接写死的文字，适合放置"FL""Aperture""ISO"等标签。

- key 采用**补零编号**：`defined_text_01`、`defined_text_02`、`defined_text_03`…… 以此类推
- 每个条目包含 `content`（文字内容）和标准的定位参数
- 可跨区域引用：`relative_to: "defined_text_01"` 或 `relative_to: "camera_lens"`

```yaml
defined_texts:
  defined_text_01:
    content: "FL"
    position: "bottom"
    alignment: "center"
    tree_align: true
    margin_bottom: 0.07
  defined_text_02:
    content: "35mm"
    relative_to: "defined_text_01"
    relative_position: "right-of"
    relative_margin: 0.005
```

### 5.3 custom_text — 用户个性文字

在 GUI 文本框中输入的多行文字（如寄语、签名等）。

```yaml
custom_text:
  enabled: true
  position: "bottom-center"
  alignment: "center"
  margin_bottom: 0.03
```

- `enabled: true` 时，GUI 显示文本输入框
- 默认内容：`"Always believe that something wonderful\nis about to happen."`
- 支持多行，用户可用换行分隔

### 5.4 多行文本行间距

```yaml
fonts:
  line_spacing_ratio: 0.005    # 行间距 = 参照边 × 0.5%
```

- 仅对包含换行符 `\n` 的文本生效
- 可在 `defined_texts` 或 `custom_text` 条目中用 `line_spacing_ratio` 覆盖全局值

---

## 6. 颜色配置

颜色由背景类型自动适配，并提供三层自定义覆盖：

### 颜色优先级（从上到下）

```
1. custom_{key}_dark_color / custom_{key}_light_color   ← 按元素类型覆盖（最精细）
2. custom_text_dark_color / custom_text_light_color     ← 通用覆盖
3. 深色背景 = 白色(255,255,255) / 浅色背景 = 黑色(0,0,0)  ← 最终兜底
```

### 自定义背景色（可选）

```yaml
colors:
  custom_bg_color: "#28180B"         # 支持 #RRGGBB 或 [R,G,B]
  custom_bg_text_scheme: "dark"      # 可选：dark / light，不写则自动检测亮度
```

- 指定后，渲染器使用纯色填充扩展画布，GUI 中背景样式下拉框自动禁用
- `custom_bg_text_scheme` 未声明时，自动根据颜色亮度判定明暗

### 通用文字颜色覆盖

```yaml
colors:
  custom_text_light_color: "#333333"     # 浅色背景下的文字颜色
  custom_text_dark_color: "#CCCCCC"      # 深色背景下的文字颜色
```

- 支持十六进制（`"#FF6B6B"`）或 RGB 数组（`[255, 107, 107]`）
- 两个字段可独立声明，无需成对

### 按元素类型独立覆盖

```yaml
colors:
  custom_exif_light_color: [51, 51, 51]
  custom_camera_lens_dark_color: "#FFFFFF"
  custom_timestamp_dark_color: "#CCCCCC"
```

- 支持的元素类型：`exif`、`timestamp`、`timestamp_author`、`camera`、`camera_make`、`lens`、`camera_lens`、`author`、`location`、`gps`

### 矩形颜色

矩形的颜色遵循同样的明暗自适应规则，命名格式为 `custom_{矩形名}_{dark/light}_color`：

```yaml
colors:
  custom_rect_01_dark_color: "#FF6B6B"      # 深色背景时使用
  custom_rect_01_light_color: "#E05555"     # 浅色背景时使用
  custom_rect_02_dark_color: [50, 150, 255]
  custom_rect_02_light_color: [30, 100, 200]
```

- 每个矩形需分别配置 `dark` 和 `light` 颜色
- 若仅配了一种，则无论背景明暗都使用该颜色
- 未配置颜色的矩形会被跳过（warning）

---

## 7. 字体配置

系统支持**拉丁字母**（英文/数字）和 **CJK**（中文/日文/韩文）独立配置字体，并自动回退到系统预装字体。

### 完整 YAML 示例

```yaml
fonts:
  latin:
    family: Gotham              # 从 assets/fonts/ 加载 {family}-{weight}.otf
    weight: medium              # 当前使用的字重
    weights:                    # 字重映射表（抽象值 → 文件后缀）
      light: Light
      regular: Book
      medium: Medium
  cjk:
    family: GlowSansSC-Normal
    weight: medium
    weights:
      light: Light
      regular: Regular
      medium: Medium
  size_ratio: 0.015             # 默认字号 = 参照边 × 1.5%
  sizes:
    camera_lens: 0.022          # 该元素使用独立字号
    exif: 0.016
  line_spacing_ratio: 0.005
```

### 关键说明

- **不配置字体也能用**：系统会自动回退到 Windows Segoe UI / Microsoft JhengHei UI
- **字重映射**：`weight` 用抽象值（`light`/`regular`/`medium`），通过 `weights` 表解析为实际文件名后缀
- **独立字号**：`sizes` 下的 key 对应 `info_position` 中的元素名；未配置则使用 `size_ratio`
- **回退链**：自定义字体文件 → 系统字体 → PIL 默认字体

---

## 8. Logo 配置

Logo 采用独立的渲染管线：文件选择由 GUI 控制，布局、尺寸、定位由 YAML 控制。

### 完整 YAML 示例

```yaml
logo:
  enabled: true
  size_ratio: 0.04              # Logo 短边 = 参照边 × 4%
  max_dim_limit_ratio: 2.5      # 长边上限倍数（防止细长 Logo 失控）
  placement: outside
  position: "bottom-right"
  alignment: "center"
  margin_bottom: 0.01
  margin_right: 0.01
  # 相对定位（与绝对定位互斥）
  # relative_to: "camera_lens"
  # relative_position: "below"
  # relative_margin: 0.01
```

### 尺寸计算

1. Logo 短边 = `参照边 × size_ratio`
2. 长边限制：若缩放后长边 > `参照边 × size_ratio × max_dim_limit_ratio`，按长边上限等比缩小
3. 品牌补偿系数叠加：从 `data/logo_scale.yaml` 读取该 Logo 文件对应的系数，与上述缩放结果相乘

默认值：`size_ratio = 0.04`，`max_dim_limit_ratio = 2.5`。

### Logo 来源

在 GUI 中三选一：

| 模式 | 行为 |
|------|------|
| 自动匹配 | 根据照片的 EXIF 相机品牌，在 `assets/logos/` 目录中自动查找最匹配的 PNG |
| 手动选择 | 在下拉列表中指定一个 Logo 文件 |
| 无 | 不显示 Logo |

### 颜色变体自动选择

- **暗色背景** → 优先选择文件名以 `_white` 结尾的 Logo（白色在暗背景上醒目）
- **浅色背景** → 优先选择非 `_white` 结尾的 Logo（深色在浅背景上醒目）
- 若指定变体不存在，自动回退到该品牌的其他可用文件

### 品牌补偿系数

编辑 `data/logo_scale.yaml` 即可叠加缩放系数。例如：

```yaml
# LOGO 品牌尺寸补偿系数
hasselblad_logo: 1.5    # 哈苏 Logo 紧凑 → 放大 50%
sony_logo: 0.7           # 索尼 Logo 细长 → 缩小到 70%
canon_logo: 0.7
fujifilm_logo: 0.7
```

系数在 `size_ratio` 和长边限制计算之后相乘。默认 `1.0` 表示不做修正。

> Logo 文件制作指南（文件格式、命名规范）请参见 **[Readme → Logo 文件制作指南](../README.md#logo-文件制作指南)**。

---

## 9. 水印配置

水印完全由 GUI 外部参数控制，不在样式 YAML 中定义。在 GUI 模式下，水印由界面控件（文字内容、位置、透明度、颜色）动态组装传入渲染器。

---

## 10. 常见问题 FAQ

### Q: 如何让一整行文字水平居中？

使用 `tree_align: true`，在链的根元素上设置 position 和 alignment，整条链会作为一个整体定位：

```yaml
defined_text_01:
  content: "FL"
  position: "bottom"
  alignment: "center"
  tree_align: true
  margin_bottom: 0.07
```

需要双轴居中时，使用 `alignment: "both-center"`。

### Q: Logo 太大或太小怎么办？

调整 `logo.size_ratio`。例如从 `0.04` 改为 `0.05` 将使 Logo 增大 25%。如果某品牌 Logo 视觉上偏大偏小，在 `data/logo_scale.yaml` 中为该品牌添加补偿系数。

### Q: 如何去掉某个 EXIF 信息（比如不显示 ISO）？

从 `info_position` 中删除该 key 对应的条目即可。**未声明的字段不会渲染**。

### Q: 修改样式 YAML 后 GUI 不更新？

GUI 启动时会加载所有样式配置。修改 YAML 后需重启程序，或使用 GUI 内置的样式编辑器（样式编辑器会实时重载并预览）。

### Q: 为什么 padding 的值不影响原图位置？

padding 仅约束叠加元素（文字、Logo 等），不移动原始照片。原图位置由 `expand_canvas` 控制。

### Q: tree_align: true 对单元素有影响吗？

没有。当根元素没有通过 `relative_to` 引用的子元素时，自动跳过树级定位。

---

## 附录A：完整 default.yaml 示例

```yaml
# ============================================
# MiLecFrame 样式配置文件 — 完整参考示例
# ============================================

# 【基本信息】必需字段
name: "我的自定义样式"

# 【布局配置】
layout:
  # 画布扩展：在原始照片四周扩展画布
  expand_canvas:
    enabled: true
    top: 0.02
    bottom: 0.12
    left: 0.0
    right: 0.0

  # 安全区域：限制叠加元素不能超出此范围
  padding:
    top: 0.01
    bottom: 0.01
    left: 0.02
    right: 0.02

  # 原图圆角（可选）
  corner_radius:
    enabled: true
    top_left: 0.01
    top_right: 0.01
    bottom_left: 0.01
    bottom_right: 0.01

  # 自定义矩形（可选）
  rectangles:
    rect_01:
      width_ratio: 1.1
      height_ratio: 0.15
      opacity: 0.5
      position: "bottom"
      alignment: "both-center"
      margin_bottom: 0.05

  # 信息位置：声明哪些文字显示 + 定位方式
  info_position:
    camera_lens:
      placement: outside
      position: "bottom-left"
      alignment: "left"
      margin_bottom: 0.022
      margin_left: 0.02
    timestamp_author:
      relative_to: "camera_lens"
      relative_position: "below"
      alignment: "left"
      relative_margin: 0.01

  # 预定义文字（可选）
  defined_texts:
    defined_text_01:
      content: "FL"
      position: "bottom"
      alignment: "center"
      tree_align: true
      margin_bottom: 0.07
    defined_text_02:
      content: "35mm"
      relative_to: "defined_text_01"
      relative_position: "right-of"
      relative_margin: 0.005

  # 自定义文本（可选）
  custom_text:
    enabled: false
    position: "bottom-center"
    alignment: "center"
    margin_bottom: 0.03

# 【Logo 配置】（可选）
logo:
  enabled: true
  size_ratio: 0.04
  max_dim_limit_ratio: 2.5
  placement: outside
  position: "bottom-right"
  alignment: "center"
  margin_bottom: 0.01
  margin_right: 0.01

# 【颜色配置】（可选）
colors:
  custom_text_light_color: "#333333"
  custom_text_dark_color: "#CCCCCC"
  custom_rect_01_light_color: [255, 255, 255]
  custom_rect_01_dark_color: [0, 0, 0]

# 【字体配置】（可选，不配置则使用系统字体）
fonts:
  latin:
    family: Gotham
    weight: medium
    weights:
      light: Light
      regular: Book
      medium: Medium
  cjk:
    family: GlowSansSC-Normal
    weight: medium
    weights:
      light: Light
      regular: Regular
      medium: Medium
  size_ratio: 0.015
  sizes:
    camera_lens: 0.022
  line_spacing_ratio: 0.005
```

---

## 附录B：_STYLE_TEMPLATE.txt 使用指南

[`_STYLE_TEMPLATE.txt`](../src/frame_styles/configs/_STYLE_TEMPLATE.txt) 是一份规格化填空模板，覆盖所有配置项。使用流程：

1. **打开模板**：在 `src/frame_styles/configs/` 目录中找到 `_STYLE_TEMPLATE.txt`
2. **填空**：在每个 `[____]` 位置填写你想要的参数值
3. **交给 AI**：将填好的模板内容发给 AI（如 DeepSeek），要求"根据这个模板生成一个完整的样式 YAML 配置文件"
4. **放入文件夹**：将生成的 YAML 保存为 `src/frame_styles/configs/你的样式名/default.yaml`
5. **重启程序**：GUI 中即可看到新样式

这是创建样式的**最快方式**——你只需描述需求，AI 负责生成语法正确的 YAML。
