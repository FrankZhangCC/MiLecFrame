# 照片元数据 MiLecFrame 标识方案：审阅报告

> 审阅对象：[PHOTO_METADATA_BRANDING_EXECUTION_PLAN.md](./PHOTO_METADATA_BRANDING_EXECUTION_PLAN.md)
> 审阅日期：2026-09-26
> 核查基线：dev `a107994`（与方案声明的基线一致）
> 实测环境：项目 venv（piexif 1.1.3、Pillow 12.2.0、Windows 10 / PowerShell 5.1）
> 审阅方法：源码逐条核对方案论断 + 技术假设实测探针（临时脚本，不落盘项目目录）
> 结论摘要：**方案质量高，可实施；技术路线经实测成立。发现 3 项 P0 必须修订、2 项 P1 必须明确、3 项 P2 建议修订，另有 1 项待用户决策。**

---

## ⚠️ 勘误（2026-09-26 第二轮复审推翻，务必先读）

方案已由 [审阅复核与修订记录](PHOTO_METADATA_BRANDING_REVIEW_RESPONSE.md) 修订为 v2；
第二轮复审（见文末「第二轮复审记录」）**独立实测确认对方纠正成立**，
本报告第一轮的以下 4 处结论/建议**已被推翻，不得再作为实施依据**：

| 第一轮出处 | 被推翻的结论 | 实际事实 |
| --- | --- | --- |
| §3.3（P0-1 根因） | "piexif.dump 不自动补 NUL，写回时应手动补 NUL" | **piexif.dump 无条件补一个 NUL**（`piexif/_dump.py:222/225` 的 `+ b"\x00"`）；手动补 NUL 反而产生双 NUL。v2 契约"入参不带 NUL、序列化器补、读回去尾 NUL"正确 |
| §3.5 | "APP1 TIFF 数据上限是 65527，现有 65533 略宽松" | **65533 就是正确阈值**：piexif.dump 输出已含 6 字节 `Exif\0\0` 前缀（`_dump.py:23`），其总长即 APP1 载荷；Pillow `JpegImagePlugin.py:761/803` 按 65533 校验，实测 65533 过、65534 抛 ValueError |
| §3.1 | "PNG 三处读回均不触发像素解码" | **`.text` 首次访问会触发 `load()`**（`PngImagePlugin.py:831`），`info`/`getexif` 不触发；且 tEXt 位于 IDAT 之后时 `Image.open()` 阶段不可见。v2 "验证禁用 `.text`、只用 info/getexif"正确且必要 |
| §4.4（P2-1） | "建议 `\` → `\\` 转义" | **加倍法不幂等**（`Camera\Tool` 逐次翻倍），与 §5.1 幂等性要求矛盾。v2 "反斜杠保持原样、转义不反解码"正确 |

第一轮其余结论（现状核对 §2、P0-2/P0-3 缺口、P1-1/P1-2/P2-2/P2-3、设计亮点、
规范符合性）经复审**仍然成立**。以 v2 与本文件文末复审记录为准。

---

## 1. 总体结论

方案的需求边界清晰、调用链核实准确、接口契约完整、降级与事务设计合理、验收矩阵覆盖全面，
是一份可执行的任务书。本审阅对照 dev `a107994` 源码逐条核实方案论断，并在项目 venv 中
实测了方案依赖的 7 项关键技术假设。

- **方案对现状的描述全部准确**（§1.1 调用链表格逐条核实通过）。
- **方案的技术路线成立**：PNG 双写、读回验证、"验证后发布"事务在实测环境中均可行，
  且读回验证不需要解码像素，方案的性能约束可以满足。
- **必须在实施前修订文档**：发现 4 处文档缺口会在实施时必然踩坑（NUL 终止符约定缺失、
  验证比较语义未定义、异常捕获范围偏窄、HEIC/AVIF 原软件名无来源），
  另有若干边界与转义规则需澄清。
- 修订建议均不改变方案的总体设计，只补细节约定与边界决策；**无需推翻任何章节结构**。

---

## 2. 对方案现状描述的核对（§1.1 逐条）

| 方案论断 | 核对结果 | 证据位置 |
| --- | --- | --- |
| `process()` 提取 raw EXIF、方向转正后渲染，调用 `_save_image()` | ✅ 准确 | `src/core/image_processor.py:122`（提取）、`:190`（保存） |
| raw EXIF 非空才写入；失败或过大即跳过 EXIF | ✅ 准确 | `:383` `if raw_exif:`；`:419` 超限跳过；`:426` 异常仅 warning，仍出图 |
| 同一保存函数直接删除传入 EXIF 中的 MakerNote/坏标签 | ✅ 准确 | `:387` `del raw_exif["Exif"][MakerNote]`；`:413` `del exif_dict[ifd][tag]`，均为入参 |
| JPEG 长度限制也用于 PNG | ✅ 准确 | `:419` `len(exif_bytes) > 65533` 不区分格式 |
| `extract_raw_exif()` 直接调用 piexif，异常返回 None | ✅ 准确 | `src/utils/exif_helper.py:137` `piexif.load(image_source)` |
| 批量复用 ImageProcessor，按布尔结果计数 | ✅ 准确 | `src/core/batch_processor.py:229-247` |
| GUI 生成结果为临时文件，导出用 `shutil.copy2()` | ✅ 准确 | `image_processing_page.py:1356`（temp）、`:1281`/`:1440`（copy2） |

### 2.1 方案未提的现状补充事实（建议写入 M-T0 基线记录）

1. **现有 `_try_dump_exif` 并非无限循环**（`image_processor.py:390-417`）：
   `while True` 每轮删除一个标签、字典有限递减，数学上有界，只是无显式上限。
   方案 §2.5 "默认最多清理 32 个字段"是显式化改进而非修 bug，优先级可按普通改进对待。
   另注意现状只捕获 `(ValueError, TypeError)`——实测该范围不够（见 §3.4）。
2. **PNG/HEIC 输入现在每张都刷一条 warning**：`extract_raw_exif` 对这两种文件路径必然
   抛异常（piexif 不支持），日志出现 `"EXIF原始提取失败"`（`exif_helper.py:138-140`）。
   实施 PNG 兼容路径后顺带消除，批量 PNG 场景日志会明显干净。
3. **GUI 失败语义现状已与方案 §6.4 一致**：生成失败不改 `is_processed`/`result_path`
   （`image_processing_page.py:1396-1412`），旧结果保留、tooltip 显示失败。
   实施时仅需补文案（见 P2-3）。

---

## 3. 技术假设实测发现

以下均在项目 venv 实测（piexif 1.1.3 / Pillow 12.2.0），结论可直接写入
M-T0 基线记录，省去实施阶段重复探针。

### 3.1 ✅ PNG 双写技术路线成立（方案 §2.1/§2.4）

`image.save(path, format='PNG', exif=exif_bytes, pnginfo=pnginfo)` 实测同时写出
eXIf chunk 与 tEXt 文本；读回三处全部可用：

| 读取方式 | 结果 |
| --- | --- |
| `Image.open(p).info['Software']` | `'MiLecFrame'`（tEXt） |
| `Image.open(p).text.get('Software')` | `'MiLecFrame'` |
| `Image.open(p).getexif()[305]` | 软件值（eXIf） |
| `Image.open(p).info['exif']` | eXIf chunk 原始 bytes 存在 |

且全部为**懒加载元数据，不触发像素解码**——方案 §6.2 "验证不主动完整解码"可满足。
Pillow 12 的 PNG 文本块在 `Image.open()` 时即解析进 `info`/`text`，
方案 §5.2 第 4 条"部分 PNG 文本可能在加载后才可用"的担心在本版本不成立（保守写法无害）。

### 3.2 ✅ 简化建议：PNG 的 EXIF 补读直接用 `info['exif']`，勿用 `getexif().tobytes()`（方案 §5.2 第 3 条）

实测 `piexif.load(Image.open(p).info['exif'])` 对 eXIf chunk **完全保真**：

- `0th` IFD 键：`[274, 305, 34665, 34853]`（Orientation、Software、ExifIFD 指针、GPS 指针）；
- Orientation=6 原样保留；`Exif` IFD 的 FocalLength=(50,1)、`GPS` IFD 均正确展开。

即 `info['exif']` 是 chunk 原始 bytes，piexif 可直接解析，**不存在**方案担心的
"Orientation 与嵌套 IFD 丢失"。该风险仅存在于 `getexif().tobytes()` 路径
（Pillow 的 Exif 对象重组 IFD 时可能发生），建议文档把 `info['exif']`
改为首选路径，`getexif().tobytes()` 仅作兜底并注明需保真性验证。

### 3.3 ⚠️ NUL 终止符行为（P0-1 根因）

- `piexif.dump()` **不自动补 NUL**：`b'MiLecFrame'` 与 `b'MiLecFrame\x00'` 产出不同字节
  （dump 结果相差 1 字节，count 字段不同）。
- 读回差异实测：

| 写入值 | Pillow `getexif()` | `piexif.load()` |
| --- | --- | --- |
| `b'MiLecFrame'`（无 NUL） | `'MiLecFrame'` | `b'MiLecFrame'` |
| `b'MiLecFrame\x00'`（带 NUL） | `'MiLecFrame\x00'`（**保留 NUL，不 strip**） | `b'MiLecFrame\x00'` |

- 方案 §2.2 要求输入"去除尾部 NUL"，但 **未规定写回时是否补 NUL**；
  §4.2 的 `verify_output_metadata` 也未规定比较前是否归一化。
  两端约定不闭合，实施时必然出现两类问题之一：
  - 写入带 NUL、验证比 `'MiLecFrame'` → 假阴性（把好文件判失败）；
  - 写入不带 NUL → 违反 EXIF ASCII 类型应 NUL 终止的规范，严格解析器/Windows 属性处理器行为不可控。
- **建议约定**（二选一，推荐前者）：
  1. 写入值 = `normalized_text.encode('ascii') + b'\x00'`（规范）；**所有读回比较前统一
     `rstrip('\x00')`**（verify、去重判断、M 系列断言全部适用）；
  2. 明确"不补 NUL"并把"验证读回值 `rstrip('\x00')` 后比较"写进契约
     （读回仍可能带 NUL，比较端归一化不可省）。

### 3.4 ⚠️ piexif.dump "坏标签可定位"只部分成立（P0-3 根因）

实测两类坏值的错误形态完全不同：

| 坏值形态 | piexif 1.1.3 行为 | 可否定位标签 |
| --- | --- | --- |
| `Software=12345`（int）、`Software={...}`（dict）、`Make=[1,2]`（list） | `ValueError: "dump" got wrong type of exif value.\n305 in 0th IFD. Got as <class 'int'>.` | ✅ 可定位，现有正则 `(\d+) in (\w+) IFD` 能匹配 |
| `XResolution='abc'`（str）、GPS float 元组 | **`UnboundLocalError: cannot access local variable 'new_value'`**（piexif 自身 bug） | ❌ 消息不含标签 ID，且异常类型不是 ValueError/TypeError |

结论：

1. 方案 §2.5 的"无法定位→直接最小兜底"分支**被证实必要**，不要试图解析 UnboundLocalError
   的消息来猜标签。
2. 实施时**序列化捕获范围必须放宽**：不能沿用现状的 `except (ValueError, TypeError)`，
   需覆盖 UnboundLocalError 等广义序列化异常；"每轮必须减少一个字段"的进展保证
   在 UnboundLocalError 场景无法定向删标签，直接转最小结构是正确决策。
3. §8.2 故障注入中"无法定位的异常"用例务必保留，它对应的是**真实存在的** piexif bug，
   不是虚构场景。

### 3.5 ✅ JPEG 超限行为：Pillow 抛 ValueError（方案 §2.5/§5.3 第 7 条）

实测 70033 字节 EXIF 保存 JPEG 时 Pillow 12.2.0 **抛 `ValueError: EXIF data is too long`**，
不会静默写出损坏文件。由此：

- 最小兜底的触发应以**捕获该 ValueError** 为主，自判长度仅作提前分流；
- APP1 中 TIFF 数据的精确上限为 **65527**（65535 − 2 长度域 − 6 `"Exif\0\0"`），
  现有代码 `65533`（`image_processor.py:419`）略宽松；65533 附近的精确边界
  按方案要求在 M-T3 于安装版本实测后固化；
- 另实测 60033 字节（未超限）可正常写入读回，说明"超限"判定必须用真实边界而非估算。

### 3.6 ✅ `piexif.load()` 对 PNG 文件路径抛异常（方案 §2.3 判断正确）

实测抛 `InvalidImageDataError: Given file is neither JPEG nor TIFF.`，
证实 PNG 输入必须走 Pillow 补读路径（`info['exif']` → `piexif.load`）。
该异常现状被 `extract_raw_exif` 吞掉并 warning（见 §2.1 第 2 条）。

### 3.7 ℹ️ 非 ASCII 原值：方案策略可接受（权衡说明）

实测把 UTF-8 bytes（如"光影魔术手"）直接写入 EXIF ASCII 字段，piexif/Pillow 均可读回
（数据不丢），但违反 EXIF ASCII 规范，跨平台显示不可控。方案 §5.1 选择"确定性反斜杠转义"
保守安全，能保证 PNG 两处值一致、跨平台可读，与 §2.2 "不承诺逐字节保真"的声明自洽，
**不判为缺陷**。若将来追求原值保真，可另立任务讨论"保留 UTF-8 bytes + ASCII 转义写 PNG 文本"
的混合方案，本期不做。

---

## 4. 需修订缺口清单

### 4.1 汇总表

| # | 缺口 | 级别 | 落点章节 | 建议 |
| --- | --- | --- | --- | --- |
| P0-1 | NUL 终止符写回与读回归一化未定义 | 必须 | §2.2 / §5.3 | 明确"写入补 NUL + 比较前 rstrip"两端约定（见 §3.3） |
| P0-2 | verify 比较语义："expected_software 相同"未定义是否归一化 | 必须 | §4.2 / §6.1 第 6 条 | 定义为"token 归一化后相等"（复用 normalize 的拆分逻辑），不比原始字节 |
| P0-3 | piexif 序列化异常捕获范围偏窄 | 必须 | §2.5 / §5.3 第 5-6 条 | 覆盖 UnboundLocalError 等非 ValueError/TypeError 异常；无法定位即转最小结构（见 §3.4） |
| P1-1 | HEIC/AVIF 输入的原 Software 保留无来源 | 必须明确 | §2.3 / §3 M14 | **待用户决策**，见 §5 |
| P1-2 | `_save_image` else 分支（非 .jpg/.png 扩展名）行为未定义 | 应明确 | §5.4 | 明确告警+沿用现有行为或断言不可达（见 §4.3） |
| P2-1 | 反斜杠转义映射不封闭，幂等性可证性存疑 | 建议 | §5.1 第 4 条 | 明确 `\`→`\\`、非 ASCII 字节→`\xNN`（见 §4.4） |
| P2-2 | 4096 限制单位混用"字符或字节" | 建议 | §5.1 第 3 条 | 固定"str 按字符、bytes 按字节"并写入验证记录 |
| P2-3 | GUI 失败保留旧结果的界面文案 | 建议 | §6.4 | 失败提示补"本次生成失败，已保留上次结果" |

### 4.2 P0 详细说明

- **P0-1（NUL）**：见 §3.3。这是本次审阅发现的最高风险项——两端约定不闭合时，
  M01-M09 的读回断言会出现假阴性或假阳性，整个验收矩阵的可信度受损。
- **P0-2（比较语义）**：与 P0-1 连带。EXIF 读回值可能带 NUL、Pillow 返回 str 而 piexif
  返回 bytes，"相同"必须定义为**归一化后 token 序列相等**（strip NUL → decode →
  按 §5.1 第 6 条拆 token → 大小写不敏感比对品牌 token），
  而不是原始字符串全等。建议 `verify_output_metadata` 内部复用 `normalize_software`
  的 token 拆分逻辑，保证"构建端与验证端用同一套语义"。
- **P0-3（异常范围）**：见 §3.4。注意现有 `_try_dump_exif` 的 `except (ValueError, TypeError)`
  会漏掉 UnboundLocalError，导致直接跳到外层"嵌入EXIF信息失败"warning——
  新方案中该路径必须落入"无法定位→最小兜底"分支而非静默无标识出图。

### 4.3 P1-2：else 分支（原格式兜底）行为

- 现状 `_save_image` 的 else 分支（`image_processor.py:376`）用 `original_format`
  （可能是 TIFF/MPO）保存，不写品牌标识。
- 实测**当前不可达**：CLI 按 `--output-format` 强制改扩展名为 .jpg/.png
  （`main.py:252-257`）、批量 `output_ext` 同规则（`batch_processor.py:150`）、
  GUI 下拉仅 JPEG/PNG（`image_processing_page.py:1355`）。
- 方案 §5.4 第 2 条"只有实际编码仍为 JPEG/PNG 才套用本方案"与第 4 条
  "不能无提示成功输出无标识文件"对 TIFF 输出的要求存在张力。
  **建议明确**：else 分支到达时记录 WARNING（"该输出格式未写入品牌标识"）并沿用现有能力，
  或在 M-T0 检索调用点后断言不可达并在代码注释说明。二者选一，不沉默。

### 4.4 P2-1：转义映射与幂等性

§5.1 第 4 条"非 ASCII 字节使用确定性反斜杠转义"未定义原值含反斜杠时的处理。
若不转义 `\` 自身，转义产物 `\\xNN` 与原生反斜杠文本不可区分；
而 §5.1 要求幂等性 `normalize(normalize(x)).text == normalize(x).text`，
要求转义映射是封闭的。**建议明确**：`\`→`\\`、非 ASCII 字节→`\xNN`、
控制字符→`\xNN`，并把幂等性测试列为 M-T1 的断言（方案已有，落实用例即可）。

---

## 5. 待用户决策：P1-1 HEIC/AVIF 输入的原软件名

**问题**：`piexif.load()` 不支持 HEIC/AVIF 文件，`extract_raw_exif` 对这些输入必然返回 None。
方案 §2.3 的软件字段来源只有"EXIF Software / PNG 文本 Software"两级，
导致 HEIC 原图 `Software='Adobe Lightroom'` 处理后输出 `MiLecFrame` 而非
`Adobe Lightroom; MiLecFrame`——与 §2.2 对 JPEG 输入的追加规则精神不一致。

**两个选项**：

| 选项 | 做法 | 代价 |
| --- | --- | --- |
| A. 保留（推荐） | 从已打开图像对象的 `image.info['exif']` 补读（pillow_heif 通常把 EXIF 放入其中），走与 PNG 相同的零额外解码路径；M14 扩展为"HEIC 原 Software 追加保留" | 需 HEIC 样本验证 pillow_heif 的 EXIF 暴露行为；无样本则该项如实标未验证 |
| B. 明确放弃 | 在 §2.3 写明"HEIC/AVIF 输入不保留原软件名，只写品牌标识"，验收与 CHANGELOG 同步此边界 | 零额外工作；但 JPEG/PNG 与 HEIC 输入的保留行为不一致，需在文档中显式声明 |

**状态：待用户决策后再修订方案文档。** 本审阅不代做决定。

---

## 6. 设计亮点（建议保持，勿改）

1. **"验证后发布"事务模型**（§2.6/§6.1）：同目录唯一名临时文件 → 独立读回 → `os.replace`；
   "finally 只清理本次临时文件"。Windows 上 `mkstemp` 句柄须先关闭的提醒与
   `temp_manager.py:55` 的现状吻合，是真实教训的正确吸收。
2. **分级降级** `preserved → cleaned → minimal → fail` 且"重试必须保证有进展"：
   比现状"EXIF 失败即无 EXIF 出图"严谨，同时用最小兜底保住鲁棒性
   （minimal 只含 Software，几乎不会失败，不会把好照片拖成处理失败）。
3. **"失败只重试元数据，不反复重做图片"**（§6.3）与"不靠删验证绕问题"：
   正确区分元数据错误与磁盘/权限错误。
4. **验收以结构化读回为准**（§3）："不把'文件内任意位置有同名字符串'视为成功"，
   避免了最常见的一类假验收。
5. **隐私克制**：日志只记格式/level/原因码/标签 ID，不打 EXIF 全文（§9.4）；
   不主动复制源图全部文本块到 PNG（§6.1 第 4 条）。
6. **诚实的边界声明**（§10）：不把元数据说成防篡改水印；历史补标、其他格式不扩围。
7. **M17 防御性测试**（输入 EXIF 对象不被清理逻辑修改）：现状每次 `process` 重新提取、
   无真实复用场景，属函数契约改进；测试保留，优先级可低。

---

## 7. 项目规范符合性

| 检查项 | 结果 |
| --- | --- |
| 新模块落 `src/utils/output_metadata.py`，与 utils 分层一致 | ✅ |
| 不引入新第三方依赖（Pillow/piexif/stdlib） | ✅ |
| 日志 `[output-metadata]` 前缀、不打隐私数据 | ✅ |
| 夹具进 gitignore 的 `test_images/metadata_branding_validation/` | ✅ |
| 门禁含 `python -m py_compile`、无虚构 pytest 套件 | ✅ |
| 不自行升版本、不发行；提交主题 `feat:` 符合 Conventional Commits | ✅ |
| 不动 RenderContext / 样式 YAML / Decorator / GUI 布局 | ✅ |

---

## 8. 对实施的建议

1. **先修订方案文档**再动工：P0-1/P0-2/P0-3 写入 §2.2/§4.2/§5.3，
   P1-2 写入 §5.4，P2 系列顺手补齐；P1-1 等用户决策。
2. **本报告 §3 的实测结论直接抄进 M-T0 基线记录**（NUL 行为、`info['exif']` 路径、
   UnboundLocalError、`ValueError: EXIF data is too long`、65527 边界），
   可省去实施阶段一轮探针。
3. M-T1 的幂等性断言、M-T3 的故障注入用例按 §3.4/§4.4 落实，
   特别是"无法定位的异常"用例（真实 piexif bug，非虚构）。
4. M-T3 实测 65533/65527 边界后，把最终阈值写进验证记录并在代码注释中说明推导。

---

## 附录 A：探针复现要点

> ⚠️ 本附录为第一轮原始探针，其中 A1 注释"dump 不补 NUL"、A2 注释"均不需解码像素"
> 已被文首勘误推翻（dump 会补 NUL；`.text` 触发 load）。代码本身如实反映第一轮观察，
> 正确结论以文首勘误块与第二轮 R1 为准。

审阅使用一次性临时脚本（存于系统临时目录，未落盘项目，未改动任何项目文件）。
关键用例与预期结论如下，实施者可按此复核：

```python
# 环境: 项目 venv (piexif 1.1.3, Pillow 12.2.0)
import piexif
from PIL import Image, PngImagePlugin

img = Image.new("RGB", (32, 32), (120, 30, 30))

# A1. NUL 终止符：dump 不补 NUL，两者字节不同
d = {"0th": {piexif.ImageIFD.Software: b"MiLecFrame"}, "1st": {}, "Exif": {},
     "GPS": {}, "Interop": {}, "thumbnail": None}
assert piexif.dump(d) != piexif.dump({**d, "0th": {piexif.ImageIFD.Software: b"MiLecFrame\x00"}})

# A2. PNG 双写 + 三处读回（均不需解码像素）
pi = PngImagePlugin.PngInfo(); pi.add_text("Software", "MiLecFrame")
img.save("t.png", format="PNG", optimize=True, exif=piexif.dump(d), pnginfo=pi)
im = Image.open("t.png")
assert im.info["Software"] == "MiLecFrame" and im.text["Software"] == "MiLecFrame"
assert im.getexif()[piexif.ImageIFD.Software] == "MiLecFrame"
raw = piexif.load(im.info["exif"])          # eXIf chunk 直接可解析（保真，含嵌套 IFD 指针）

# A3. piexif.load 不吃 PNG 文件路径
try:
    piexif.load("t.png")                    # 抛 InvalidImageDataError
except Exception as e:
    print(type(e).__name__, e)

# A4. 坏值两类错误形态
try:
    piexif.dump({"0th": {piexif.ImageIFD.Software: 12345}, "1st": {}, "Exif": {},
                 "GPS": {}, "Interop": {}, "thumbnail": None})
except ValueError as e:                     # 可定位: "305 in 0th IFD"
    print(e)
try:
    piexif.dump({"0th": {piexif.ImageIFD.XResolution: "abc"}, "1st": {}, "Exif": {},
                 "GPS": {}, "Interop": {}, "thumbnail": None})
except Exception as e:                      # UnboundLocalError，不可定位
    print(type(e).__name__, e)

# A5. JPEG 超限：Pillow 抛 ValueError("EXIF data is too long")
big = {"0th": {piexif.ImageIFD.Software: b"X" * 70000}, "1st": {}, "Exif": {},
       "GPS": {}, "Interop": {}, "thumbnail": None}
try:
    img.save("big.jpg", format="JPEG", exif=piexif.dump(big))
except ValueError as e:
    print(e)
```

## 附录 B：审阅范围声明

- 本轮仅产出本审阅文档，**未修改**方案原文、任何 `.py` 文件或照片文件。
- 探针脚本为一次性临时文件，存放于系统临时目录，不进项目、不进 git。
- 未验证项：真实 HEIC/AVIF 样本下的 pillow_heif EXIF 暴露行为（属实施阶段 M-T5 夹具）；
  Windows 资源管理器属性页显示（方案已声明不作为验收依据）。

---
---

# 第二轮复审记录（2026-09-26，对方案 v2）

> 复审对象：[执行方案 v2](PHOTO_METADATA_BRANDING_EXECUTION_PLAN.md)（经
> [审阅复核与修订记录](PHOTO_METADATA_BRANDING_REVIEW_RESPONSE.md) 修订）
> 复审方法：逐条核对第一轮 8 条意见的落实 + **独立实测复核对方的三项纠正**
> （venv：piexif 1.1.3、Pillow 12.2.0）+ v2 新契约端到端验证
> 结论摘要：**v2 修订全部落实且多处比第一轮建议更正确；对方三项纠正经独立实测全部成立；
> v2 可进入实施。第一轮 4 处技术错误已勘误（见文首）。**

## R1. 对方纠正的独立验证：全部成立

第一轮审阅有 3 处技术错误 + 1 处设计建议错误，对方在复核记录中指出。本轮**不采信对方
声明、按原始实验独立复核**，结果如下（全部证实对方正确）：

| # | 对方声明 | 独立实测结果 | 判定 |
| --- | --- | --- | --- |
| R1-1 | piexif.dump 自动补 NUL（`_dump.py:220`） | 源码 `TYPES.Ascii` 分支 `_dump.py:222/225` 对 str/bytes 均执行 `+ b"\x00"`，无条件追加；解剖 TIFF 存储载荷：入参 `b'MiLecFrame'` → count=11、存储 `b'MiLecFrame\x00'`；入参 `b'MiLecFrame\x00'` → count=12、双 NUL | ✅ 对方正确，第一轮错误 |
| R1-2 | 65533 是 JPEG 正确阈值（`JpegImagePlugin.py:761`） | 常量存在于该行（函数内局部常量，故模块属性访问不到——第一轮探针的访问方式有误，非对方引证错误）；`piexif.dump` 输出以 `Exif\0\0` 开头（`_dump.py:23`），其总长即 APP1 载荷；实测 dump 总长 65527/65533 保存读回 OK，65534 抛 `ValueError: EXIF data is too long` | ✅ 对方正确，第一轮 65527 说法错误 |
| R1-3 | `.text` 触发 load，info/getexif 不触发；IDAT 后文本 open 阶段不可见 | 计数实测：`info` 0 次、`getexif` 0 次、`.text` 1 次 load 调用；手工构造 tEXt 位于 IDAT 后的 PNG：`open()` 后 `info.get('Software')` 为 None，`load()` 后才可读 | ✅ 对方正确，第一轮"均不触发"不完整 |
| R1-4 | 反斜杠加倍不幂等 | `Camera\Tool` 经加倍映射逐次翻倍（`Camera\\Tool` → `Camera\\\\Tool` → …）；v2 映射（反斜杠原样、非 ASCII/控制字符转义不反解码）对全部用例幂等成立 | ✅ 对方正确，第一轮 P2-1 建议错误 |

第一轮错误成因记录（供后续审阅借鉴）：R1-1 只比较两个 dump 结果是否相同、未解剖存储
载荷与 count 字段；R1-2 把 piexif.dump 输出误当纯 TIFF 数据、未检查其头部；R1-3 观察
样本的 tEXt 恰在文件头部，未测 IDAT 后文本，把个例推广为通则。

## R2. 第一轮 8 条意见的落实核对：全部处理

| 第一轮意见 | v2 落实 | 复审判定 |
| --- | --- | --- |
| P0-1 NUL 契约 | §2.2/§5.3 第 3 条/§6.1 第 6 条：写入 `encode('ascii')` 不手动加 NUL、序列化器补一个；读回严格 ASCII 解码 + 去尾部 NUL；输入清理/存储终止符/只读验证三阶段分离；新增 M19 | ✅ 契约闭合，且纠正了第一轮的错误根因 |
| P0-2 比较语义 | §6.2 第 2-3 条 + 新接口 `decode_stored_software()`：解码去尾 NUL 后与 expected_software **精确相等**，并按分号查恰一个品牌 token；明确禁止验证端调用 `normalize_software()` | ✅ 采纳且**优于第一轮建议**（用 normalize 比较会把缺品牌/重复品牌"修复"成通过，掩盖构建缺陷） |
| P0-3 异常范围 | §5.3 第 5 条：dump 捕获范围覆盖 `UnboundLocalError`；MemoryError 直接失败；KeyboardInterrupt/SystemExit 等 BaseException 不捕获 | ✅ 与实测事实吻合，层次正确 |
| P1-1 HEIC/AVIF 原软件名 | 用户已确认**保留**；§2.3/§5.2 从已加载对象 `info['exif']` 补读（不走不支持 HEIC 的 piexif.load 文件路径）；M14 扩展"原软件名可读时追加一次"；新增 synthetic.heic/avif 合成夹具 | ✅ 决策已闭合；合成夹具不依赖用户照片，思路好 |
| P1-2 else 分支 | §5.4：CLI/GUI 已规范扩展名（该分支实测不可达）；直接调用其他格式时保留旧能力 + WARNING，不宣称品牌保证 | ✅ 与第一轮建议一致 |
| P2-1 转义映射 | §5.1 第 4-5 条：可打印 ASCII（含反斜杠）原样；bytes 其他值 `\xNN`，str 码点按宽度 `\xNN`/`\uNNNN`/`\UNNNNNNNN`；转义不再反解码；示例表含 `Camera\Tool`、`0xFF→\xff`；M20 覆盖 | ✅ 采纳明确映射、正确否决加倍法；幂等性实测成立 |
| P2-2 长度单位 | §5.1 第 3/9 条 + M20：str 按字符、bytes 按字节；最终 ASCII 按字节、不含序列化器补的 NUL | ✅ |
| P2-3 GUI 提示 | §6.4：失败且存在旧结果时提示"本次生成失败，已保留上次结果" | ✅ |
| 附议：PNG EXIF 用 `info['exif']` | §5.2 第 3 条：原始字节优先，不默认 `getexif().tobytes()` | ✅ |
| 附议：65533 边界实测 | §5.3 第 7 条 + M21：65533 含前缀可保存、65534 拒绝；注明非纯 TIFF 上限 | ✅（数值与第一轮建议相反，v2 正确） |

## R3. v2 新契约端到端验证：通过

按 v2 契约（写入不加 NUL → piexif 补一个 → 读回严格解码去尾 NUL → 精确比较）实测：

| 路径 | 写入文本 | EXIF 读回 | 去尾 NUL 后 | PNG 文本读回 | 精确相等 |
| --- | --- | --- | --- | --- | --- |
| PNG | `MiLecFrame` | `'MiLecFrame'` | `MiLecFrame` | `'MiLecFrame'` | ✅ |
| PNG | `Adobe Lightroom; MiLecFrame` | `'Adobe Lightroom; MiLecFrame'` | 同左 | 同左 | ✅ |
| JPEG | `MiLecFrame` | `'MiLecFrame'` | `MiLecFrame` | —（JPEG 无文本字段） | ✅ |

即 v2 的"两处值一致 + 与构建期 expected 精确相等"在两种格式下均可严格成立，
M03/M19 的断言可执行。

## R4. v2 新增内容质量

- **M19-M22 设计合理**：分别封住 NUL 契约、转义/长度边界、JPEG 容量边界、
  PNG 读取通道四个本轮实测出的坑，与教训一一对应。
- **故障注入改用真实构造**（§8.2：`XResolution='abc'` 触发真实 UnboundLocalError、
  用小文件实测验证器而非模拟）比第一轮的模拟法更可靠。
- **save 抛 ValueError 降级为兜底路径**（§6.3：只对 `image.save` 阶段的 ValueError
  兜底、长度预检提前分流）比第一轮"以捕获为主"更精确。
- **M01-M18 无回归**：抽查 M04/M09/M10/M14/M18 与新契约不冲突。

## R5. 遗留观察（非阻塞，实施时留意）

1. **str 与 bytes 的转义产物不同**：`'中'` → `\u4e2d`，而 UTF-8 bytes `b'\xe4\xb8\xad'`
   → `\xe4\xb8\xad`。§5.1 已明确按类型分列，语义成立；M20 用例应同时覆盖两种输入类型，
   并在验证记录中写明该差异是设计而非缺陷。
2. **NUL 行为绑定 piexif 1.1.3**（§2.2"当前 piexif 1.1.3"）：依赖 `_dump.py` 的补
   NUL 行为。建议实施时在 `output_metadata.py` 注释中固化该版本假设；
   M19 已有读回验证兜底，升级 piexif 时会暴露。
3. **PNG 文本补读时机分两段**：EXIF 字节在打开阶段捕获（§5.2 第 1 条），而 IDAT 后
   文本须待渲染 `load()` 后才可见（R1-3）。§5.2 第 4 条已覆盖语义（复用已有加载、
   禁止二次打开），实施时注意两个捕获点先后即可。
4. **合成 HEIF/AVIF 夹具的 Orientation 观察**（复核记录 §3.5：HEIF 归一化为 1、
   AVIF 保留 6）是合成矩形 + 当前库版本的行为，不能外推到真实相机文件；
   真实样本回归仍按 M-T5/M14 执行（对方已如实声明）。

## R6. 复审结论

- 第一轮 8 条意见**全部落实**，其中 P0-2、P2-1 的 v2 处理**优于**第一轮建议，
  应以 v2 为准。
- 对方三项纠正（R1-1/R1-2/R1-3）与对 P2-1 的否决（R1-4）**全部经独立实测成立**，
  第一轮相应结论已勘误。
- v2 内部自洽、契约闭合、验收矩阵 M01-M22 覆盖完整，**同意进入实施（M-T0 → M-T7）**。
- 本文档第一轮 §6-§8 的实施建议（实测结论抄入 M-T0、幂等性断言、故障注入用真实
  bug）仍然有效，数值类结论以勘误块与 R1 为准。

## 附录 C：第二轮复审探针要点

复核脚本存于系统临时目录（`probe_recheck*.py`），未落盘项目。关键断言：

```python
import io, struct, piexif
from PIL import Image, PngImagePlugin

def dump_software(v):
    return piexif.dump({"0th": {305: v}, "Exif": {}, "GPS": {},
                        "Interop": {}, "1st": {}, "thumbnail": None})

# R1-1 存储载荷解剖：dump 无条件补一个 NUL
def stored_ascii(raw):
    tiff = raw[6:]                      # dump 输出含 6 字节 Exif\0\0 头
    off = struct.unpack(">I", tiff[4:8])[0]
    tag, kind, count, addr = struct.unpack(">HHII", tiff[off+2:off+14])
    return tiff[addr:addr+count] if count > 4 else None

assert stored_ascii(dump_software(b"MiLecFrame")) == b"MiLecFrame\x00"
assert stored_ascii(dump_software(b"MiLecFrame\x00")) == b"MiLecFrame\x00\x00"

# R1-2 JPEG 边界：65533 过、65534 拒
image = Image.new("RGB", (8, 8))
overhead = len(dump_software(b"X" * 100)) - 100
for length in (65533, 65534):
    raw = dump_software(b"X" * (length - overhead))
    assert len(raw) == length
    try:
        buf = io.BytesIO(); image.save(buf, format="JPEG", exif=raw)
        assert length == 65533
    except ValueError as e:
        assert length == 65534 and str(e) == "EXIF data is too long"

# R1-3 .text 触发 load、info/getexif 不触发（计数 load 调用）
info = PngImagePlugin.PngInfo(); info.add_text("Software", "MiLecFrame")
buf = io.BytesIO(); image.save(buf, format="PNG",
                               exif=dump_software(b"MiLecFrame"), pnginfo=info)
for field in ("info", "getexif", "text"):
    with Image.open(io.BytesIO(buf.getvalue())) as r:
        calls = []; orig = r.load
        r.load = lambda *a, **k: (calls.append(1), orig(*a, **k))
        {"info": lambda: r.info["Software"], "getexif": lambda: r.getexif()[305],
         "text": lambda: r.text["Software"]}[field]()
        assert len(calls) == (1 if field == "text" else 0)

# R3 v2 契约端到端：写入不加 NUL，读回精确比较
text = "Adobe Lightroom; MiLecFrame"
buf = io.BytesIO(); pi = PngImagePlugin.PngInfo(); pi.add_text("Software", text)
image.save(buf, format="PNG", exif=dump_software(text.encode("ascii")), pnginfo=pi)
with Image.open(io.BytesIO(buf.getvalue())) as r:
    decoded = r.getexif()[305].encode("latin-1").rstrip(b"\x00").decode("ascii")
    assert decoded == text and r.info["Software"] == text
```
