# 渲染参数重构执行方案（render_frame 参数打包）

> 状态：待执行（细化到文件级、逐调用点级）
> 基线：`dev` 分支 `c17f639` + 工作区（含已完成的两处修复，见 §0.2）
> 目标：`render_frame` 签名从 13 参数收敛为 4 参数，`ImageProcessor.process()`
> 从 15 参数收敛为 6 参数；**零行为变化、输出像素不变**；为高斯矩形设计
> （[`RECTANGLE_GAUSSIAN_BLUR_DESIGN.md`](./RECTANGLE_GAUSSIAN_BLUR_DESIGN.md)，
> 下称"设计文档"）的第 8 步缓存接入预留扩展点。
> 定位：设计文档第 10 节实施顺序的**前置第 0 步**，独立 commit，可单独回退。

## 0. 范围与已定决策

### 0.1 关联评审决策记录（2026-09-20）

| 评审项 | 决策 |
|---|---|
| 盲区 A：照片内矩形压原图圆角的取样近似 | **接受**。模糊本身可掩盖；未来切换方案 B（base_scene 二次模糊）可彻底解决 |
| 盲区 B：磨砂信息条 | **零配置升级**。FrameBar 升级只需在 `rect_01` 追加 `fill:`/`gaussian_blur:`/`stroke:` 三块进入效果栈，`info_position` 不动，图层顺序天然保证文字叠在磨砂条上 |
| 盲区 C：卷积内核性能优化 | **本期搁置**，不纳入 |
| 盲区 D：参数膨胀 | 本方案（第 0 步前置重构） |

### 0.2 已完成修复（工作区待提交，随本方案一并入库）

1. `src/core/renderer.py:21` 补齐 `List` 导入（修复 Python 3.14 下
   `inspect.signature()` 触发的 `NameError`）。
2. `AGENTS.md` 更新已删除的 `project_master_spec.json` 引用说明
   （该文件于 v2.0.0-dev `fb7f132` 开源准备时移除，不再恢复）。

### 0.3 与讨论稿的一处微调

讨论稿中 `RenderOptions` 预留了 `source_cache_key` / `prepared_blur_cache`
两个字段。本方案**推迟到高斯设计第 8 步**再添加：届时
`PreparedBlurLRU` 类型已存在，且 dataclass 追加带默认值字段对全部现有
构造点零影响——"加字段"而非"改签名"。本期避免注解指向尚不存在的类型。

### 0.4 明确不做的事

- **不改 `BatchProcessor.batch_process()` 签名**（17 参数，属批量任务
  配置描述，本期仅内部适配；未来若需再引入 BatchTaskConfig，超出本期范围）。
- **不迁移 `gui_legacy/`**：已验证 `main.py` 与 `gui_pyside` 均不引用
  （零 import 链），封存代码签名变更不影响运行。
- **不加 `**kwargs` 兼容层**：调用点全在仓库内（本方案逐一列出），
  兼容层会掩盖拼写错误，违背项目高可读性要求。一次性硬切换。

## 1. 变更文件总览

| 文件 | 变更 | 说明 |
|---|---|---|
| `src/core/renderer.py` | 核心 | 新增 2 个 dataclass；`render_frame` 新签名 |
| `src/core/image_processor.py` | 核心 | `process()` 新签名，对象透传 |
| `src/gui_pyside/pages/style_creator_page.py` | 调用点 | `_render_preview()` 直调迁移 |
| `src/gui_pyside/pages/image_processing_page.py` | 调用点 | 生成按钮路径迁移（高斯 LRU 未来接入点） |
| `src/main.py` | 调用点 | CLI 单张路径迁移 |
| `src/core/batch_processor.py` | 调用点 | 循环外构造对象、循环内就地更新 |
| `src/gui_legacy/**` | **不动** | 见 §0.4 |

## 2. Step 0：基线留存（重构前执行）

重构承诺"输出像素不变"，先留存对照基准。任选一张带 EXIF 的真实照片
（建议横拍、竖拍各一张，竖拍覆盖 EXIF 转正路径），在**重构前**执行：

```powershell
.\venv\Scripts\activate
python src/main.py -i test_images\<样片>.jpg -o output_test_baseline.jpg `
    -s "边框信息条 FrameBar" --author "Verify" --bg-fill gaussian_black_35
```

> `output_test*.jpg` 已被 gitignore，不会污染仓库。基准文件保留到 Step 4
> 像素对比完成后才可删除。

## 3. Step 1：`src/core/renderer.py`

### 3.1 import 变更

```python
# 顶部新增（dataclass 定义用）
from dataclasses import dataclass
# typing 行保持上一修复后的样子，List 已在：
from typing import Tuple, Optional, Dict, List
```

### 3.2 新增两个 dataclass（放在 `_rounded_corner_mask` 之前、模块工具函数区）

```python
@dataclass
class RenderMetadata:
    """渲染元数据：拍摄相关信息，render_frame 内部整体转喂 RenderContext。

    生命周期：随每张图 / 每次生成新建，不跨请求持有。
    注意：走 ImageProcessor.process() 路径时 exif_data 由处理器从文件
    提取并覆盖（见 process() 内说明），调用方无需也无法从外部传入。
    """
    exif_data: Optional[Dict] = None            # EXIF 数据（预览直调路径使用）
    author: Optional[str] = None                # 作者名
    location: Optional[str] = None              # 拍摄地点
    custom_text: Optional[str] = None           # 自定义文本（样式 custom_text.enabled 时生效）
    lens_display_mode: str = 'combined'         # 镜头显示模式 combined/camera_only/lens_only
    use_short_lens: bool = False                # 是否使用短版镜头名
    timestamp_display_mode: str = 'full'        # 拍摄时间显示模式 full/date_only/hide


@dataclass
class RenderOptions:
    """渲染行为选项：背景 / 装饰 / Logo 等跨图层渲染开关。

    生命周期：可由 GUI 页面长期持有、随用户操作就地更新字段
    （高斯矩形设计第 8 步将在此追加 source_cache_key / prepared_blur_cache
    两个带默认值字段，届时所有现有构造点零改动）。
    """
    # 默认值取注册表常量：历史默认 "white" 是非法键（image_processor.py
    # 注释已记录该坑），凡未显式指定背景的调用一律落到 DEFAULT_FILL
    bg_fill_type: str = BackgroundFillManager.DEFAULT_FILL
    decorations: Optional[List[Dict]] = None    # 装饰元素列表 [{'type': ..., 'params': ...}]
    logo_filename: Optional[str] = None         # None=按相机品牌自动匹配；""=禁用 Logo；其他=指定文件
    saturation_override: Optional[float] = None # None=FILL_TYPES 默认；1.0=不做增强
```

### 3.3 `render_frame()` 签名与函数体替换清单

新签名（替换现有 222-237 行整个签名）：

```python
def render_frame(
    self,
    image: Image.Image,
    style_config: Dict,
    metadata: Optional[RenderMetadata] = None,
    options: Optional[RenderOptions] = None,
) -> Image.Image:
```

函数体开头插入哨兵解包（避免可变默认值陷阱，也兼容 `None` 直传）：

```python
    metadata = metadata or RenderMetadata()
    options = options or RenderOptions()
```

函数体逐处替换（**逻辑零改动，仅改参数来源前缀**）：

| 原代码 | 替换为 | 位置（原行号） |
|---|---|---|
| `effective_bg_type = bg_fill_type`（两处：解析失败回退分支、else 分支） | `effective_bg_type = options.bg_fill_type` | 281、283 |
| `RenderContext(image.size, exif_data, author, location, lens_display_mode, use_short_lens, custom_text=..., timestamp_display_mode=...)` | 七个实参全部加 `metadata.` 前缀 | 288 |
| `saturation=saturation_override` | `saturation=options.saturation_override` | 292 |
| `if decorations:` 与 `apply_decorations(positioned_image, decorations, ...)` | `options.decorations`（两处） | 324、327 |
| `if logo_filename is None:` / `if logo_filename:` / `self._add_logo(image_with_text, logo_filename, ...)` | `options.logo_filename`（三处） | 342、351、352 |

同时重写 docstring：Args 段改为 `image / style_config / metadata / options`
四项，其余描述段落原样保留。

## 4. Step 2：`src/core/image_processor.py`

### 4.1 import 变更

```python
from src.core.renderer import FrameRenderer, RenderMetadata, RenderOptions
```

### 4.2 `process()` 新签名（替换 53-67 行）

```python
def process(self, input_path: str, output_path: str,
            style_name: Optional[str] = None,
            metadata: Optional[RenderMetadata] = None,
            options: Optional[RenderOptions] = None,
            font_weight: Optional[str] = None) -> bool:
```

- `font_weight` 保持平铺：它在函数内改写 `style_config['fonts']['weight']`
  （188-189 行），是样式改写而非渲染选项，**不进** `RenderOptions`。
- 原参数级注释"背景填充默认值必须取注册表常量"迁移到
  `RenderOptions.bg_fill_type` 字段注释（§3.2 已含）。

### 4.3 函数体改动（两处）

开头哨兵解包 + EXIF 覆盖（语义与现状一致：现状调用方本就无法传
exif_data，EXIF 一律由处理器从文件提取）：

```python
    metadata = metadata or RenderMetadata()
    options = options or RenderOptions()
```

在原 126 行 `exif_data = self.exif_helper.extract_exif_data(input_path)`
之后补一行：

```python
    # EXIF 由处理器从输入文件提取，覆盖 metadata 中可能存在的值
    # （与旧签名行为一致：调用方原本没有传入 EXIF 的途径）
    metadata.exif_data = exif_data
```

原 192-206 行 `render_frame(...)` 调用改为对象透传：

```python
    rendered_image = self.renderer.render_frame(
        image=image,
        style_config=style_config,
        metadata=metadata,
        options=options,
    )
```

## 5. Step 3：调用点迁移（4 处，逐个 before/after）

### 5.1 `style_creator_page.py` — `_render_preview()`（652-664 行）

保持本页延迟导入 renderer 的现有风格，在渲染调用前 import：

```python
            # 渲染（dataclass 随 FrameRenderer 一并延迟导入，保持本页启动轻量）
            from src.core.renderer import RenderMetadata, RenderOptions
            metadata = RenderMetadata(
                exif_data=PREVIEW_EXIF_DATA,
                author=PREVIEW_AUTHOR,
                location=PREVIEW_LOCATION,
                custom_text=PREVIEW_CUSTOM_TEXT)
            options = RenderOptions(
                bg_fill_type=bg_fill_type,
                saturation_override=1.0)
            result = renderer.render_frame(
                sample_img, style_config, metadata, options)
```

可选优化（非必须，本期不做）：预览参数恒定，可将两对象提为页面成员，
切换背景时仅更新 `options.bg_fill_type`。

### 5.2 `image_processing_page.py` — 生成路径（1230-1245 行）

```python
            metadata = RenderMetadata(
                author=self.edit_author.text() or None,
                location=location or None,
                custom_text=self.edit_custom_text.text() or None,
                lens_display_mode=lens_key,
                use_short_lens=self.chk_short_lens.isChecked(),
                timestamp_display_mode=ts_mode,
            )
            options = RenderOptions(
                bg_fill_type=bg_key,
                decorations=decorations or None,
                logo_filename=logo_filename,
                saturation_override=None if self.chk_enhance.isChecked() else 1.0,
            )
            processor = ImageProcessor()
            success = processor.process(
                input_path=input_path,
                output_path=output_path,
                style_name=self.style_selector_card.current_style or "底部信息条 Bottom Bars",
                metadata=metadata,
                options=options,
                font_weight=fw_key,
            )
```

（`RenderMetadata` / `RenderOptions` 在文件顶部与 `ImageProcessor`
同一 import 区补充。本调用点是高斯设计第 8 步 `prepared_blur_cache`
的接入位置，届时只加一个字段赋值。）

### 5.3 `main.py` — CLI 单张（259-269 行）

```python
    metadata = RenderMetadata(
        author=author, location=location, custom_text=custom_text,
        lens_display_mode=lens_display, use_short_lens=use_short_lens,
        timestamp_display_mode=timestamp_display)
    options = RenderOptions(
        bg_fill_type=bg_fill, decorations=decorations,
        logo_filename=logo_filename,
        saturation_override=saturation_override)
    processor = ImageProcessor(style_config=style)
    success = processor.process(input_path, actual_output_path,
                                style_name=style,
                                metadata=metadata, options=options,
                                font_weight=font_weight)
```

（`from src.core.renderer import RenderMetadata, RenderOptions` 补到
main.py 现有项目 import 区。）

### 5.4 `batch_processor.py` — `batch_process()` 内部（循环外构造，循环内更新）

在 153 行 `processor = ImageProcessor()` 之后构造一次：

```python
        # 循环外构造渲染参数对象：整批不变的参数一次性确定，
        # 循环内只有逐张变化的字段（location / logo）就地更新
        metadata = RenderMetadata(
            author=author, location=location,
            custom_text=custom_text,
            lens_display_mode=lens_display_mode,
            use_short_lens=use_short_lens,
            timestamp_display_mode=timestamp_display_mode)
        options = RenderOptions(
            bg_fill_type=bg_fill_type,
            decorations=decorations,
            saturation_override=saturation_override)
```

循环内（原 209-224 行调用处）改为：

```python
                # 逐张变化的字段就地更新（引用同一对象，无重建开销）
                metadata.location = current_location
                # 注意：current_logo 可能为 ""（空串=禁用 Logo 自动匹配的哨兵），
                # 必须原样赋值，禁止做 `or None` 之类的转换——
                # None 会触发 render_frame 内的品牌自动匹配，改变行为！
                options.logo_filename = current_logo
                success = processor.process(
                    input_path=str(input_path),
                    output_path=str(output_path),
                    style_name=style_name,
                    metadata=metadata, options=options,
                    font_weight=font_weight,
                )
```

## 6. Step 4：验证

### 6.1 静态检查

```powershell
# 语法检查（全部改动文件）
python -m py_compile src/core/renderer.py src/core/image_processor.py `
    src/core/batch_processor.py src/main.py `
    src/gui_pyside/pages/style_creator_page.py `
    src/gui_pyside/pages/image_processing_page.py

# 旧 kwarg 残留检查：以下三条的输出应只剩 RenderMetadata/RenderOptions
# 构造处的字段赋值、字段定义与 None 判断，不再出现对
# render_frame/process 的旧式关键字传参（gui_legacy 除外）
grep -rn "lens_display_mode=" src/ --include="*.py" | findstr /V gui_legacy
grep -rn "saturation_override=" src/ --include="*.py" | findstr /V gui_legacy
grep -rn "timestamp_display_mode=" src/ --include="*.py" | findstr /V gui_legacy
```

### 6.2 行为等价性（像素级对比）

用与 Step 0 **完全相同**的命令生成重构后输出（仅改文件名）：

```powershell
python src/main.py -i test_images\<样片>.jpg -o output_test_refactor.jpg `
    -s "边框信息条 FrameBar" --author "Verify" --bg-fill gaussian_black_35

python -c "from PIL import Image, ImageChops; a=Image.open('output_test_baseline.jpg'); b=Image.open('output_test_refactor.jpg'); d=ImageChops.difference(a,b); print('像素一致' if d.getbbox() is None else f'存在差异区域: {d.getbbox()}')"
```

预期输出 `像素一致`（渲染管线全确定性：无随机源，同输入必同输出）。
竖拍样片重复一次，覆盖 EXIF 转正路径。

### 6.3 GUI 冒烟

```powershell
python src/main.py    # 启动 PySide6 GUI
```

检查清单：
1. 样式编辑器页：默认样式预览正常渲染、切换预览背景立即重绘；
2. 主处理页：导入一张照片 → 生成相框 → 输出正常；
3. 控制台 / `debug_log.txt` 无新增异常堆栈。

## 7. 提交切分（dev 分支，Conventional Commits）

| 顺序 | commit | 内容 |
|---|---|---|
| 1 | `docs: 新增渲染参数重构执行方案` | 本文件 |
| 2 | `fix: 补齐 renderer.py 缺失的 List 导入（修复注解内省 NameError）` | §0.2-1，工作区已完成 |
| 3 | `docs: AGENTS.md 更新已删除的 project_master_spec.json 引用说明` | §0.2-2，工作区已完成 |
| 4 | `refactor: render_frame/process 参数打包为 RenderMetadata/RenderOptions` | Step 1-3 全部文件，**必须原子提交**（签名与调用点分批提交会产生不可运行的中间态） |

> ⚠️ 工作区尚有与本方案无关的既有改动（`data/camera_map.csv`、
> `data/lens_map.csv`、未跟踪的 `RECTANGLE_GAUSSIAN_BLUR_DESIGN.md`），
> 提交时按文件精确 `git add <file>`，**禁止 `git add -A`** 混入。
> 设计文档本身建议单独提交：`docs: 矩形描边/填充/高斯模糊设计方案（评审稿）`。

不发独立版本 tag：纯 refactor 随高斯矩形功能（minor，预计 v2.6.0-dev）
一起经 `new-version` squash 入 mainline。

## 8. 风险与回退

| 风险 | 评估 | 兜底 |
|---|---|---|
| 调用点遗漏 | 调用点已逐一核实（§5 四处 + image_processor 内部透传），全仓库无其他 | §6.1 grep 残留检查 |
| `bg_fill_type` 默认值变化（`"white"` → `DEFAULT_FILL`） | 所有现有调用点均显式传背景值，无调用方依赖非法默认键；且新默认是**合法**键，只会更安全 | 无需额外处理 |
| `metadata.exif_data` 覆盖语义 | 与现状一致（调用方原本无传入途径） | §6.2 像素对比 |
| 批量 Logo 空串哨兵被误转换 | 已在 §5.4 代码注释中显式警告 | 代码评审 + 批量冒烟 |
| gui_legacy 因签名变更损坏 | 已验证零 import 链引用，不在任何运行路径 | 如未来复活 Streamlit GUI，需同步迁移其调用点 |
| 回退 | 单 commit（第 4 个）revert 即整体还原 | `git revert <commit>` |

## 9. 与高斯矩形设计的衔接

1. 本方案合并后，按设计文档第 10 节步骤 1-10 顺序执行高斯功能。
2. 设计文档第 8 步（二级缓存接入）时：`RenderOptions` 追加
   `source_cache_key: Optional[str] = None` 与
   `prepared_blur_cache: Optional["PreparedBlurLRU"] = None`
   两个带默认值字段（dataclass 加默认字段不破坏任何现有构造点），
   `render_frame` 内部开始消费；接入点为 §5.2 的主处理页与
   §5.1 的样式编辑器页。
3. 设计文档第 7 节"需要修改的文件"清单中 `renderer.py` / `image_processor.py`
   的职责描述，在高斯实施提交时按本方案的新签名同步更新。
4. 决策记录（§0.1）中盲区 B 的"零配置升级"结论，应作为高斯实施时
   `docs/STYLE_GUIDE.md` 更新的首要示例（FrameBar 磨砂信息条）写入。
