# 矩形描边/填充/高斯模糊 整体执行方案

> 状态：待执行
> 上游文档：
> - 设计方案：[`RECTANGLE_GAUSSIAN_BLUR_DESIGN.md`](../RECTANGLE_GAUSSIAN_BLUR_DESIGN.md)（下称"设计文档"，技术细节以它为准，本方案不重复其论证，只引用章节）
> - 参数重构子方案：[`RENDER_PARAMS_REFACTOR_PLAN.md`](./RENDER_PARAMS_REFACTOR_PLAN.md)（下称"参数方案"，作为本方案 Phase 0.2 全文引用）
> 基线：`dev` 分支 `c17f639` + 工作区（含两处已完成修复）
> 版本目标：**v2.6.0-dev**（新功能 minor），全部完成后一次 `new-version` 入 mainline
> 交付形态：照片内/跨界/照片外矩形可独立开启"高斯模糊 → 纯色填充 → 内描边"三层效果栈

## 0. 总览

### 0.1 阶段地图与依赖

```text
Phase 0 前置准备 ──> Phase 1 算法层拆分 ──> Phase 2 一级缓存+统一短路
                                                        │
                                                        v
Phase 5 文档模板 <── Phase 4 二级缓存+GUI接入 <── Phase 3 矩形效果栈(核心)
                                                        │
                                                        v
                                        Phase 6 总验收与发版 v2.6.0-dev
```

- Phase 0-2 之间严格串行（每步是下一步的地基）。
- Phase 3 依赖 Phase 2（消费缓存与短路判定），是工作量最大的阶段。
- Phase 4 依赖 Phase 3（矩形也是缓存消费者）。
- Phase 5 文档可穿插在 Phase 3/4 期间编写，但定稿必须在 Phase 6 之前。

### 0.2 已定决策基线（执行中不再摇摆）

| # | 决策 | 来源 |
|---|---|---|
| D1 | 照片内矩形压原图圆角的取样近似**接受**（模糊可掩盖；未来方案 B 彻底解决） | 评审盲区 A |
| D2 | FrameBar 类样式**零配置升级**：rect 加 `fill:`/`gaussian_blur:`/`stroke:` 即进效果栈，`info_position` 不动，文字自动叠在磨砂条上 | 评审盲区 B |
| D3 | 卷积内核性能优化（`np.apply_along_axis` 替换）**本期不做** | 评审盲区 C |
| D4 | 参数重构为前置 Phase 0.2，独立 commit | 评审盲区 D |
| D5 | 首期固定**方案 A（复用型）**；`source_kind=base_scene` 接口预留不实现 | 设计文档 §4.3 |
| D6 | 效果栈固定层级"模糊 → 填充 → 内描边"，内描边不改外部尺寸 | 设计文档 §3 |
| D7 | 样式编辑器"字段保留"（最小兼容方案）为本需求**前置依赖**（Phase 0.3），完整 GUI 编辑 UI 本期不做 | 评审 §四 |
| D8 | 半径默认 `200`（与背景一致利于共享），样片评审后可调 | 设计文档 §11 |

## 1. Phase 0：前置准备（4 个子项，全部独立可提交）

### 0.1 既有修复提交（工作区已完成，只差 commit）

- commit `fix: 补齐 renderer.py 缺失的 List 导入（修复注解内省 NameError）`
- commit `docs: AGENTS.md 更新已删除的 project_master_spec.json 引用说明`

### 0.2 参数重构

**按参数方案全文执行**（dataclass 定义、签名、4 个调用点迁移、验证、原子 commit
`refactor: render_frame/process 参数打包为 RenderMetadata/RenderOptions`）。
本阶段完成后 `RenderOptions` 即为后续所有新参数的唯一定居点。

### 0.3 样式编辑器字段保留（最小兼容方案）

**改动文件**：`src/gui_pyside/models/style_config_form.py`

`StyleConfigFormData` 增加两个透传容器（不加任何 UI）：

```python
# from_yaml_dict() 时保留未识别的 layout 键（如 rectangles），
# to_yaml_dict() 原样回写。本期不支持 GUI 编辑，仅保证"加载→保存"不丢配置。
self._passthrough_layout: Dict = {}    # layout 下未识别的子字典
self._passthrough_colors: Dict = {}   # colors 下不在 COLOR_ELEMENT_KEYS 白名单的键
```

- `from_yaml_dict()`：读取时把 `layout['rectangles']` 等未消费键存入
  `_passthrough_layout`；`colors` 中 `custom_rect_*` 等白名单外键存入
  `_passthrough_colors`。
- `to_yaml_dict()`：写出的 dict 合并回这两个容器。
- 现状缺口（评审已核实）：不改则加载 FrameBar 再保存会丢 `rectangles`
  与 `custom_rect_01_*` 颜色。

**验证关卡**：
```powershell
# 单元性质脚本（临时，不入库）：加载 FrameBar default.yaml → to_yaml_dict()
# 断言 layout.rectangles 与 custom_rect_01_light/dark_color 均存在且值一致
```
commit：`fix: 样式编辑器保留未识别的 layout/colors 字段（加载再保存不丢矩形配置）`

### 0.4 验收基线留存

固定三张样片（横拍带 EXIF、竖拍带 EXIF、无 EXIF 各一，放 `test_images/`），
对**全部内置样式 × 代表性背景**（pure_black / gaussian_black_35 /
gaussian_white_80 / custom_bg_color 样式）生成基线输出目录
`test_images/baseline_v2.5/`（gitignore 内）。Phase 1-4 每阶段结束重跑同一
矩阵做像素 diff，旧路径必须恒为 `像素一致`。

## 2. Phase 1：算法层拆分（设计文档 §4.1"共享阶段"）

### 改动：`src/utils/gaussian_blur.py`

保持纯算法层定位，新增三个公开接口 + 一个载体类，原函数改为组合实现：

```python
class PreparedBlur:
    """着色前、目标尺寸缩放前的工作分辨率卷积结果。

    内部保留 float32 数组（而非 uint8）：原算法在 float32 域连续完成
    box blur → 饱和度增强，中途量化会引入不可逆差异，拆分后必须接力
    float32 才能保证背景输出逐像素不变（Phase 1 验收硬标准）。
    """
    def __init__(self, work_arr: np.ndarray, scale_factor: float): ...
    @property
    def nbytes(self) -> int: ...   # 二级缓存预算计量（work_arr.nbytes）

def prepare_gaussian_blur(image: Image.Image, radius: int) -> PreparedBlur:
    """共享阶段：原图 → 工作尺寸（≤1200 长边，短边≥512）→ 三遍 Box Blur（float32）"""

def render_prepared_blur(prepared: PreparedBlur, target_size, saturation=1.0) -> Image.Image:
    """派生阶段：float32 饱和度增强 → uint8 → 缩放到目标尺寸（原图尺寸或画布尺寸）"""

def apply_color_overlay(image: Image.Image, color, opacity_percent: int) -> Image.Image:
    """着色阶段：现有黑/白叠色推广为任意 RGB（矩形分支复用）"""
```

`apply_gaussian_blur_overlay_expansion()` 重写为三函数组合（顺序与原实现
严格一致：卷积→饱和度→缩放→叠色），`background_fill.py` **本阶段零改动**。

### 验证关卡（gate G1）

- 基线矩阵（Phase 0.4）全量重跑：四种高斯背景 × 全部样式，diff 恒为 0。
- 纯色背景路径未触碰，抽样式 diff 为 0。

commit：`refactor: gaussian_blur 拆分为 prepare/render_prepared/color_overlay 三阶段`

## 3. Phase 2：一级缓存与全图统一短路（设计文档 §5.2 一级 / §5.4）

### 新增文件：`src/core/blur_cache.py`

```python
class RenderBlurCache:
    """一级缓存：单次 render_frame() 生命周期内懒计算、按需派生。

    - 帧内源图唯一，缓存键简化为 (source_kind, radius)；
      source_kind 本期仅 'photo'，预留 'base_scene'（方案 B 接口位）。
    - prepared_lru：可选二级缓存（Phase 4 接入，本阶段恒为 None）。
    """
    def __init__(self, source_image, prepared_lru=None): ...
    def get_prepared(self, source_kind: str, radius: int) -> PreparedBlur: ...
    def get_photo_size_blur(self, radius: int, saturation=1.0) -> Image.Image: ...
    def get_canvas_size_blur(self, radius: int, saturation=1.0, canvas_size=None) -> Image.Image: ...
    # 命中/未命中计数，供 §8 日志与 Phase 6 验收断言
```

### 改动：`src/utils/background_fill.py`

`render()` 增加可选参数 `blur_cache: Optional[RenderBlurCache] = None`：
高斯路径优先从缓存取（同 `blur_radius` 键），无缓存回退直算（CLI/批量
兼容）。注册表结构不动。

### 改动：`src/core/renderer.py`

- 新增私有方法 `_compute_gaussian_required(...)`（设计文档 §5.4 公式），
  入参含 `rect_consumers: List`（**本阶段恒为空列表**，Phase 3 填充）。
- `render_frame()` 开头判定：
  - `gaussian_required == False` → 不建缓存；背景为高斯类型时用
    **按 `text_scheme` 选黑/白的纯色**替代（背景不可见，但 `is_dark_bg`
    仍驱动文字/Logo/矩形配色，替代色必须匹配明暗方案，输出像素不变）；
  - `True` → 创建 `RenderBlurCache` 传入背景渲染。
- "背景可见"几何判定：`original_bounds != (0,0,cw,ch)` 或原图圆角启用或
  `image.mode == 'RGBA'`（保守）。
- DEBUG 日志 `blur plan: gaussian_required=..., background_blur=..., photo_radii=[...]`（设计文档 §8 格式）。

### 验证关卡（gate G2）

- 基线矩阵 diff 恒 0（含"高斯背景+无扩展"这类被短路场景：背景虽被
  纯色替代，但被原图全覆盖，最终像素不变）。
- 短路矩阵（设计文档 §6 表格前 3 行 + 后 2 行）：用日志断言
  `gaussian_required` 与卷积次数符合预期。
- 高斯背景 + 无扩展 + 无圆角的样片渲染耗时显著下降（原 33MP 约 2.64s
  路径被短路）。

commit：`feat: 全图高斯需求统一判定与每帧一级模糊缓存（背景短路修复）`
> 注：此 commit 顺带修复了"高斯背景+无画布扩展仍全量模糊"的既有浪费，
> CHANGELOG 中作为可感知改进单列。

## 4. Phase 3：矩形效果栈（核心，设计文档 §3 / §5.1 / §5.5 / §6）

### 改动：`src/core/renderer.py`（主体）

**(a) RectangleSpec 内部模型**（模块级 dataclass，解析产物，不含渲染逻辑）：

```python
@dataclass
class RectangleSpec:
    """单矩形效果解析结果（设计文档 §5.1 需求分析阶段的产物）"""
    name: str
    mode: str                       # 'legacy' | 'effect_stack'（§3.1 分流规则）
    box: Tuple[int, int, int, int]  # 未裁切矩形盒 (x, y, w, h)（画布坐标）
    canvas_clip: Tuple[int, int, int, int]  # 与画布交集（§5.5 同步裁切基准）
    source_kind: str                # 'photo'（矩形⊆original_bounds）| 'canvas'
    fill_enabled: bool;  fill_color: Optional[Tuple];  fill_opacity: float
    stroke_enabled: bool; stroke_color: Optional[Tuple]
    stroke_px: int;      stroke_opacity: float
    blur_enabled: bool;  blur_radius: Optional[int]
    corner_radius: Optional[Dict]
```

**(b) `_analyze_rectangles()`**：分流、几何分类（§4.1 包含关系判定）、
颜色解析（填充：现有 dark/light 回退；描边：§3 四级回退链
当前方案描边色→另一方案描边色→当前填充色→另一方案填充色）、
各层参数校验与独立降级（§6 三个短路表 + 半径/厚度上限 warning）。

**(c) `skip_keys` 扩展**：`{'width_ratio','height_ratio','opacity','corner_radius','name'}`
**加上** `{'fill','stroke','gaussian_blur'}`（设计文档 §3 规则 11）。

**(d) `_draw_rectangle_effect_stack()`**（新函数，不动 `_draw_single_rectangle`）：
局部 patch 内三层合成 + 单次组裁切（§5.5）：

```text
clip = box ∩ canvas（负坐标/越界矩形先裁，五层同坐标：stroke_coverage/
outer_mask/模糊源 patch/underlay patch/效果 patch）
1. 内容底图 = 模糊 patch（photo 源按 box-orig 偏移从照片尺寸模糊层 crop；
   canvas 源从画布尺寸模糊层 crop）或 underlay patch（模糊关闭）
2. 填充层按 fill_opacity 混合（只乘填充，不乘模糊层——§5.5 防双重着色）
3. 描边层按 stroke_coverage × stroke_opacity 混合（inner_box 内缩 +
   inner_corner = max(outer - stroke_px, 0)，复用 _rounded_corner_mask 两次）
4. output.paste(效果 patch, clip[:2], outer_mask)   ← alpha 只写一次，
   禁止再传 patch 自身 alpha（透明度平方防护）
```

- `stroke_px = max(1, round(ref * radius_ratio))`，上限
  `(min(rect_w, rect_h) - 1) // 2`（保底 1px 内容区，超限 warning 并截断）。
- 效果栈整体绘制点：`render_frame()` 中原图 paste 之后、decorator 之前；
  按 key 排序，后画覆盖先画；**模糊源一律取自冻结的原图卷积缓存**
  （RenderBlurCache），不含任何已绘制效果栈矩形（顺序无关，设计文档 §2.2）。
- 矩形模糊需求登记：`_compute_gaussian_required()` 的 `rect_consumers`
  由分析阶段填充（含 §6 短路规则：`opacity>=1` 的有效填充覆盖模糊层、
  画布外矩形、空内容区等不登记）。

### 验证关卡（gate G3）

- **回归红线**：全部内置样式（无新字段）基线 diff 恒 0；FrameBar 旧式
  矩形仍在原图下方。
- 八种开关组合矩阵（设计文档 §3.2 表）：临时 YAML 测试样式（放
  `test_images/`，不入 `configs/`），逐组合生成样片并人工核对层级。
- §9.2 功能矩阵其余项：三种位置、直角/四角圆角、opacity 0/0.25/1.0、
  描边回退色与最小 1px、厚度上限 warning、负坐标/越界。
- D2 验证：FrameBar 的 rect_01 加 `gaussian_blur:{enabled:true,radius:200}`
  后，`info_position` 零改动，文字叠在磨砂条上（样片人工确认）。

commit（可拆 2-3 个，均在 dev，最后随版本 squash）：
1. `feat: 矩形效果栈解析与 legacy/effect_stack 分流`
2. `feat: 矩形三层效果合成（模糊→填充→内描边）与独立降级`

## 5. Phase 4：二级缓存与 GUI 生命周期接入（设计文档 §5.2 二级 / §5.3）

### 改动清单

| 文件 | 改动 |
|---|---|
| `src/core/blur_cache.py` | 新增 `PreparedBlurLRU`：按 `nbytes` 计量的 LRU，默认预算 64 MiB（可配置），仅收 `source_kind='photo'` 的 `PreparedBlur`；`base_scene` 一律不进 LRU |
| `src/core/renderer.py` | `RenderOptions` 追加 `source_cache_key: Optional[str] = None`、`prepared_blur_cache: Optional["PreparedBlurLRU"] = None`（dataclass 加默认字段，全部现有构造点零改动——参数方案 §9 已定）；`render_frame` 将 LRU 注入 `RenderBlurCache` |
| `src/gui_pyside/models/file_item.py` | 导入时对内存中的 `file_bytes` 做一次性摘要（如 sha256 前 16 hex）存为 `cache_key` 字段 |
| `src/gui_pyside/pages/image_processing_page.py` | 页面级持有 `ImageProcessor` + `PreparedBlurLRU`（替代每次点击新建）；生成时 `RenderOptions(source_cache_key=item.cache_key, prepared_blur_cache=self._blur_lru)` |
| `src/gui_pyside/pages/style_creator_page.py` | 页面级 LRU；样本图稳定键 `(preview_asset, orientation)`（横/竖不同键） |

缓存键结构（设计文档 §5.3 完整定义）：
`(source_cache_key, normalized_image_size, normalized_image_mode, preprocessing_version, blur_radius, gaussian_algorithm_version)`；
`preprocessing_version` 覆盖 EXIF 转正 / ICC / 超尺寸缩放规则，首期取常量
`"1"`，任一预处理逻辑变更时递增。批量处理（`batch_processor.py`）**不传
LRU**，仅一级缓存。

### 验证关卡（gate G4）

设计文档 §9.3 缓存矩阵，用 DEBUG 日志的 hit/miss 计数断言：

- 同图切换背景颜色/透明度/饱和度 → L2 命中，卷积计数不增；
- 高斯↔纯色↔高斯往返 → 命中（LRU 未淘汰时）；
- 横竖样本互切 → 未命中；切回 → 命中；
- 不同 `FileItem` 同尺寸文件 → 未命中（摘要键不同）；
- 修改半径 / source key / preprocessing_version → 未命中；
- 批量不同照片连续处理 → 无 L2 驻留增长（内存平稳）。

commit：`feat: PreparedBlurLRU 二级缓存与页面级源键接入`

## 6. Phase 5：文档与模板（设计文档 §7 文件表后四行）

| 文件 | 内容 |
|---|---|
| `src/frame_styles/configs/_STYLE_TEMPLATE.txt` | 【10. 自定义矩形】追加三个效果块（`fill/gaussian_blur/stroke`）填空项 + 效果栈层级说明 + "显式 `fill:` 字段会把矩形迁移到原图上方"的显要提示（设计文档 §11 风险项） |
| `docs/STYLE_GUIDE.md` | 矩形效果完整章节；**首要示例 = FrameBar 磨砂信息条（D2 决策）**：rect_01 加三块字段、`info_position` 零改动的对照 YAML；跨界矩形"拉伸原图模糊"语义的显式声明（设计文档 §4.1 局限） |
| `docs/DEVELOPMENT.md` | 渲染管线图（新图层顺序）、缓存键与两级缓存生命周期、短路条件、`blur plan` 日志说明 |
| `docs/RECTANGLE_GAUSSIAN_BLUR_DESIGN.md` | 状态行更新为"已实施（v2.6.0）"，附决策记录 D1-D8 |

可选（独立小 commit，视觉决策留待样片评审）：内置 FrameBar 样式本身
是否启用磨砂条。默认**不启用**，保持发行样式稳定。

commit：`docs: 矩形效果栈配置模板、样式指南与开发文档`

## 7. Phase 6：总验收与发版

1. **全量回归**：Phase 0.4 基线矩阵最后一次全量 diff（旧路径零变化）。
2. **设计文档 §9 验收清单逐项执行**：§9.1 兼容性、§9.2 功能矩阵、
   §9.3 性能与缓存矩阵、§9.4 必需检查（`py_compile` 全部改动 `.py`；
   打包冒烟——本功能无新资源依赖，确认 spec 无需改动即可）。
3. **性能基准记录**：1200×800 预览图、6000×4000、7008×4672 三档的
   耗时与峰值内存，写入 `docs/DEVELOPMENT.md` 基准表（与 2.64s 历史值对照）。
4. **版本发布**（AGENTS.md 流程）：
   ```powershell
   # dev：升版本 src/_version.py → 2.6.0-dev；README 徽标；CHANGELOG.md 条目
   # mainline：squash + tag + 推送
   python tools/release_sync.py new-version 2.6.0-dev --msg "矩形描边/填充/高斯模糊效果栈" --push
   python tools/release_sync.py check   # 三线体检
   ```

## 8. 新增 / 修改文件总表

| 文件 | 类型 | 阶段 |
|---|---|---|
| `src/utils/gaussian_blur.py` | 拆分 | P1 |
| `src/core/blur_cache.py` | **新增** | P2/P4 |
| `src/utils/background_fill.py` | 接缓存 | P2 |
| `src/core/renderer.py` | 签名/短路/效果栈 | P0.2/P2/P3/P4 |
| `src/core/image_processor.py` | 签名 | P0.2 |
| `src/main.py` / `src/core/batch_processor.py` | 调用点/复用 | P0.2 |
| `src/gui_pyside/pages/style_creator_page.py` | 调用点/LRU | P0.2/P4 |
| `src/gui_pyside/pages/image_processing_page.py` | 调用点/处理器复用 | P0.2/P4 |
| `src/gui_pyside/models/style_config_form.py` | 字段保留 | P0.3 |
| `src/gui_pyside/models/file_item.py` | 源键摘要 | P4 |
| `_STYLE_TEMPLATE.txt` / `docs/STYLE_GUIDE.md` / `docs/DEVELOPMENT.md` / 设计文档 | 文档 | P5 |

## 9. 关键设计红线（实现与评审 checklist）

1. `PreparedBlur` 全程 float32 接力，任何阶段不得中途转 uint8 再转回。
2. 填充 `opacity` 只乘填充层；描边透明度独立；模糊层永不被这两者乘。
3. 效果 patch 的 alpha 只经 `outer_mask` 写入一次，`paste()` 不得再传 patch 自身。
4. 模糊源冻结：矩形模糊只取原图卷积缓存，绝不含已绘制的效果栈矩形。
5. 无新字段的样式必须像素级不变（每阶段 gate 都跑基线矩阵）。
6. 短路时背景替代色的明暗方案必须与原背景类型一致（`text_scheme` 驱动）。
7. 批量 Logo 空串哨兵 `""` 原样传递，禁止 `or None`（参数方案 §5.4）。
8. 二级缓存只存 `PreparedBlur`（工作分辨率 float32），绝不存全画布派生图。
9. 效果栈矩形与画布的所有裁切（蒙版/模糊源/underlay/patch）使用同一交集坐标。

## 10. 风险跟踪

| 风险 | 阶段 | 缓解 |
|---|---|---|
| 算法拆分引入量化差异 | P1 | 红线 1 + gate G1 像素 diff |
| 短路判定漏判（背景可见性） | P2 | RGBA 保守判定 + gate G2 短路矩阵 + 基线矩阵兜底 |
| 效果栈边缘暗边/透明度平方 | P3 | 红线 3 + 八组合样片放大目检（400% 边缘） |
| 缓存错误复用（跨图/跨预处理） | P4 | 键结构含摘要+尺寸+模式+版本；gate G4 未命中用例 |
| LRU 内存超预算 | P4 | nbytes 计量 + 预算可配 + 批量内存平稳用例 |
| 旧样式意外迁移效果栈 | P3 | 分流规则只在显式字段时迁移；全部内置样式 gate G3 回归 |
| 短周期内改动面大 | 全局 | 阶段化 commit + 每阶段独立可回退 |

## 11. 回退策略

每个 Phase 独立 commit（dev 上线性历史），任一阶段验收不过：
`git revert` 该阶段 commit 即可回到上一 gate，不影响已合入的更早阶段。
发版前全部阶段必须通过各自 gate；发版后修复走 `cherry` + patch 递增流程。
