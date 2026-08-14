![Features introduction](docs/v1.0_features_vertical.png)

# MiLecFrame - 照片相框水印工具 ![Version](https://img.shields.io/badge/version-2.4.0--dev-blue)

> ©FrankZhangCC 2026 · 基于 GPLv3 许可证发布 · 由 DeepSeek V4 辅助开发

MiLecFrame 是一款为摄影师设计的照片相框水印工具，参考各品牌水印风格开发。支持 EXIF 信息自动提取与排版、多种预设样式、完全自定义的样式编辑器，以及批量处理。

| 能力 | 说明 |
|------|------|
| EXIF 自动读取 | 品牌、型号、镜头、焦距、光圈、快门、ISO、时间、GPS 坐标 |
| 多格式支持 | JPEG / PNG / TIFF / MPO / HEIF / HEIC / AVIF（HDR 自动转 SDR） |
| 色彩空间转换 | sRGB / AdobeRGB / ProPhotoRGB / Display P3 → 自动转 sRGB |
| 预设样式 | 5 种内置样式，文件夹变体自动匹配（无地点 / 无作者等） |
| 视觉样式编辑器 | GUI 表单式编辑，修改实时预览，一次导出 YAML |
| Logo 支持 | 自动匹配品牌 + 颜色变体自动选择 + 品牌补偿系数 |
| 水印 | 文字、位置、透明度、颜色 四维可调 |
| 批量处理 | GUI 多文件排队 + CLI 文件夹递归 |

> **新用户可直接跳到 [快速上手](#快速上手) 开始使用。**

### 与同类工具的区别

- **相机用户专属**：不同于在线水印工具，MiLecFrame 专为相机工作流设计——自动识别相机品牌/镜头并映射为人类可读的名称（如 ILCE-7M3 → α7 III）
- **全可自定义**：不像大多数工只有水印，你可以用 YAML 控制每一个文字和 Logo 像素的位置
- **原生桌面 GUI**：零网络依赖，图片在本地处理，速度取决于你的电脑性能

---

## 快速上手

### 环境搭建

1. 克隆项目
2. 创建虚拟环境并安装依赖：
   ```bash
   python setup_env.py
   ```
3. 激活虚拟环境：
   ```bash
   .\venv\Scripts\activate
   ```

> 本程序仅已在 Windows 环境下测试，Linux / macOS 可能需要调整路径格式和字体配置。

### 字体安装（可选）

**无自定义字体时自动使用系统预装字体，可直接跳过此步骤。**

如需使用预设样式默认字体（Gotham + GlowSansSC），请放入 `assets/fonts/` 目录：

- Gotham 字体族：`Gotham-Light.otf`、`Gotham-Book.otf`、`Gotham-Medium.otf`
- GlowSansSC 未来荧黑：`GlowSansSC-Normal-Light.otf`、`GlowSansSC-Normal-Regular.otf`、`GlowSansSC-Normal-Medium.otf`

> Gotham 为商业字体，请遵守其授权协议。GlowSansSC 基于 SIL Open Font License 发布。

### 制作第一张照片

```bash
python src/main.py
```

1. **拖入照片**：将 JPEG/PNG 文件拖到窗口
2. **选样式**：在左侧「样式选择」标签页中点击一种样式缩略图
3. **填作者**：展开「个性化配置」标签，输入作者姓名（程序会记住，下次自动填入）
4. **生成相框**：点击底部「生成相框」按钮
5. **导出**：点击「导出当前图像」保存 JPG/PNG

> 拍摄信息（相机型号、镜头、光圈、快门等）会自动从照片的 EXIF 数据中读取并显示。

---

## GUI 功能指南

### 图像处理页面

页面上半部分是预览区（处理前/处理后对比），下半部分是胶片栏（多图排队）。

**右侧配置面板**，从上到下 5 个折叠标签：

| 标签 | 功能 |
|------|------|
| 输出设置 | 选择输出格式（JPEG / PNG） |
| 相框配置 | 切换样式、选择背景填充类型、调整字重 |
| 个性化配置 | 填写作者姓名、拍摄地点、自定义寄语文字 |
| 拍摄信息配置 | 控制镜头显示方式、短版镜头名、时间显示模式、Logo 来源 |
| 文本水印 | 添加文字水印（内容、位置、透明度、颜色） |

**底部胶片栏**：多张照片以缩略图排队显示，蓝色边框 = 当前选中，绿色边框 = 已处理。支持右键移除、Delete 键删除。

**批量导出**：加载多张照片 → 逐一生成 → 点击「一键导出所有」。

### 相机/镜头映射管理

在左侧导航栏选择「相机映射」或「镜头映射」，进入表格编辑界面。

- **相机映射**：将照片 EXIF 中的原始品牌/型号（如 ILCE-7M3）映射为市场名（如 α7 III）
- **镜头映射**：将镜头名（如 NIKKOR Z 85mm f/1.8 S）映射为短版名（如 Z 85mm f/1.8 S）
- 支持品牌筛选、表格内编辑实时保存

> CSV 文件必须使用 **UTF-8 编码**（无 BOM），请用 VS Code / PyCharm 编辑，避免使用 Windows 记事本。

### 样式编辑器

在左侧导航栏选择「样式编辑器」，进入可视化样式创建界面。

- 左侧 10 个折叠卡片覆盖所有样式参数（布局、字体、颜色、Logo 等）
- 修改任意参数后，右侧实时预览自动刷新（约 300ms 防抖）
- 顶部切换横版/竖版样本图预览

支持加载已有样式修改、新建样式从零配置、导出 YAML 预览。详细字段说明请参阅 **[样式配置指南](docs/STYLE_GUIDE.md)**。

### Logo 管理

Logo 文件放在 `assets/logos/` 目录中。在「拍摄信息配置」标签页中三选一：

| 模式 | 行为 |
|------|------|
| 自动匹配 | 根据照片的相机品牌自动查找最匹配的 PNG |
| 手动选择 | 从下拉列表指定文件 |
| 无 | 不显示 Logo |

**颜色自动适配**：深色背景上自动选择白色变体（文件名以 `_white` 结尾），浅色背景上自动选择深色变体。

**品牌补偿系数**：编辑 `data/logo_scale.yaml` 可为特定品牌叠加缩放系数。详见 [数据管理 → Logo 补偿系数](#logo-补偿系数)。

---

## 数据管理

### 设备映射

#### camera_map.csv

相机品牌与型号的映射表，将 EXIF 内部编号转换为人类可读的显示名。

| 列名 | 说明 | 示例 |
|------|------|------|
| `original_brand` | EXIF Make 字段 | SONY |
| `original_model` | EXIF Model 字段 | ILCE-7M3 |
| `mapped_brand` | 显示用品牌名 | SONY |
| `mapped_model` | 显示用型号名 | α7 III |

**品牌名命名建议**：官方全大写品牌（SONY）保持大写；长品牌名（Hasselblad）建议首字母大写。

**型号名命名建议**：跟随品牌官方市场名称，而非 EXIF 内部编号。

#### lens_map.csv

镜头信息映射表，提供完整映射名和短版名两种格式。

| 列名 | 说明 |
|------|------|
| `original_lens` | EXIF LensModel 原始值 |
| `mapped_lens` | 完整显示名 |
| `short_lens` | 短版名（GUI 勾选"使用短版镜头名"时生效） |

**短版名规则**：

| 镜头类型 | 保留内容 | 示例 |
|---------|---------|------|
| 原厂镜头 | 系列名（EF/RF/Z/FE/GF/XF/XCD）+ 定位标识（L/S/GM） | `Z 85mm f/1.8 S`、`FE 85mm F1.4 GM` |
| 副厂镜头 | 仅焦距和光圈 | `100-400mm F5-6.3` |

完整示例对照：

| 原始名 | 完整映射名 | 短版名 |
|--------|-----------|--------|
| RF85mm F1.2 L USM | RF 85mm F1.2 L USM | RF 85mm F1.2 L |
| NIKKOR Z 85mm f/1.8 S | NIKKOR Z 85mm f/1.8 S | Z 85mm f/1.8 S |
| 100-400mm F5-6.3 DG OS HSM\|Contemporary 017 | SIGMA 100-400mm F5-6.3 DG OS HSM Contemporary | 100-400mm F5-6.3 |

### Logo 补偿系数

`data/logo_scale.yaml` 用于校正不同品牌 Logo 在相同 `size_ratio` 下的视觉大小差异：

```yaml
# 细长条 Logo（索尼/佳能/富士）需缩小；紧凑型 Logo（哈苏）需放大
hasselblad_logo: 1.5
sony_logo: 0.7
canon_logo: 0.7
fujifilm_logo: 0.7
```

- **追加新品牌**：新增一行 `品牌关键字: 系数` 即可
- **修改系数**：直接改数值，重启程序生效
- **关键字匹配**：程序检查 Logo 文件名是否包含该关键字（不区分大小写）
- **系数含义**：`1.0` = 不变，`0.7` = 缩到 70%，`1.5` = 放大到 150%
- **文件不存在时**：程序自动创建带默认值的版本

### Logo 文件制作指南

#### 文件格式

- 仅支持 PNG（RGBA 透明背景）
- 图形裁剪至边界，四周不留空白
- 建议横向分辨率 ≥ 2000px

#### 文件命名规范

推荐格式：**`[Brand]_[Shape]_[Color].png`**

| 命名元素 | 说明 | 示例 |
|---------|------|------|
| **Brand** | 英文品牌名；子品牌用下划线分隔 | `sony_alpha`、`nikon_Z`、`canon_EOS` |
| **Shape** | `logo`（原始商标）、`round`（圆形底框）、`vertical`（垂直排列） | `logo`、`round` |
| **Color** | `black`、`white`，或其他颜色名 | `black`、`white`、`red` |

示例：

- `sony_logo_black.png` — Sony 商标，黑色
- `canon_EOS_round_white.png` — Canon EOS 圆形底框，白色

#### 颜色变体自动匹配

- 暗色背景 → 优先 `_white` 后缀（白色在暗背景更醒目）
- 浅色背景 → 优先非 `_white` 后缀（深色在浅背景更醒目）
- 指定变体不存在 → 自动回退该品牌的其他可用文件

---

## 命令行参考

CLI 模式适用于已确认参数的批量自动化，日常使用推荐 GUI。

### 单张处理

```bash
python src/main.py -i input.jpg -o output.jpg -s "底部信息条 Bottom Bars" --author "Frank"
```

### 批量处理

```bash
python src/main.py --batch -i ./photos -o ./output -s "底部信息条 Bottom Bars" --recursive
```

### 完整参数表

| 参数 | 简写 | 说明 |
|------|------|------|
| `--input` | `-i` | 输入图片路径 |
| `--output` | `-o` | 输出图片路径 |
| `--style` | `-s` | 相框样式名称 |
| `--author` | | 作者姓名 |
| `--location` | | 拍摄地点 |
| `--bg-fill` | | 背景填充类型（见下方可选值） |
| `--batch` | | 启用批量处理模式 |
| `--recursive` | | 递归处理子文件夹 |
| `--font-weight` | | 字重：`light` / `regular` / `medium` |
| `--output-format` | | 输出格式：`JPEG` / `PNG` |
| `--logo` | | `auto` / `none` / 文件名 |
| `--lens-display` | | `combined` / `camera_only` / `lens_only` |
| `--timestamp-display` | | `full` / `date_only` / `hide` |
| `--use-short-lens` | | 使用短版镜头名 |
| `--no-enhance` | | 关闭背景增强 |
| `--skip-existing` | | 跳过已存在文件（默认启用） |
| `--use-gps-location` | | 用 GPS 坐标替换拍摄地点 |
| `--watermark-text` | | 水印文字 |
| `--watermark-position` | | 水印位置 |
| `--watermark-opacity` | | 水印不透明度 0-100 |
| `--watermark-color` | | 水印颜色：`white` / `black` |

`--bg-fill` 可选值：`pure_black`、`pure_white`、`gaussian_black_65`、`gaussian_white_80`、`gaussian_black_35`、`gaussian_white_50`

---

## 进阶文档

| 文档 | 内容 | 适合 |
|------|------|------|
| [样式配置指南](docs/STYLE_GUIDE.md) | YAML 配置字段全解、定位系统详解、完整示例 | 想自定义样式的用户 |
| [开发参考](docs/DEVELOPMENT.md) | 架构设计、核心模块实现、渲染管线、开发约定 | 开发者 / 贡献者 |
| [CHANGELOG](CHANGELOG.md) | 开发版完整变更记录 | 查阅详细变更 |
| [CHANGELOG_RELEASE](CHANGELOG_RELEASE.md) | 发行版更新摘要 | 查阅各版本重点功能 |

---

## 贡献与许可

欢迎提交 Issue 和 Pull Request。

本程序基于 GPLv3 许可证发布，详见 [LICENSE](./LICENSE)。
