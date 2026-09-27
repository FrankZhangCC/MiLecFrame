# 照片元数据 MiLecFrame 标识：独立实施方案

> 日期：2026-09-26  
> 状态：待实施；本文的接口和任务为执行设计，不表示已有代码或验证通过。  
> 核查基线：dev `a107994`；实施前重新核查分支、源码和工作区。  
> 来源：由原合并方案拆分，细化为可独立实施和验收的任务书。
> 修订：v2，2026-09-26；已逐项复核外部审阅，补充序列化、验证与 HEIC/AVIF 来源契约。实测证据及采纳情况见 [审阅复核记录](PHOTO_METADATA_BRANDING_REVIEW_RESPONSE.md)。

## 1. 已确认需求与交付范围

用户已确认：在处理后的照片文件元数据中加入 `MiLecFrame`，不改变照片画面。

用户进一步确认：**HEIC/AVIF 输入也应保留已有软件名称，再追加 MiLecFrame**；从已加载图像对象补读，不能因 piexif 不支持该容器路径就直接放弃原值。

- 覆盖新生成的 JPEG/PNG，包括 GUI 单张生成与导出、GUI 一键导出、CLI 单张和批量。
- HEIC/AVIF 等输入在现有管线解码成功并输出 JPEG/PNG 时，同样写入标识。
- 默认始终写入，不增加参数或设置开关；固定产品名，不附加版本号。
- 标识保证覆盖 JPEG/PNG；直接调用底层接口产生的其他格式保留既有能力并明确告警，详见 §5.4，不计入本期标识支持格式。
- 不扫描历史输出；被现有规则跳过的输出不回写。历史补标需要单独任务。
- 不向画面、作者、版权、相机型号等位置写品牌字样。
- 桌面快捷方式是另一项独立功能，不是本方案的前置依赖。

“新生成输出”是本期执行边界；Software 字段、双格式兼容和验证后发布是本方案制定的技术规则。

### 1.1 已核实的调用链与缺口

| 位置 | 现状 | 实施动作 |
| --- | --- | --- |
| `src/core/image_processor.py::process()` | 提取 raw EXIF、方向转正后渲染，调用 `_save_image()` | 在转换前捕获 PNG/HEIC/AVIF 源 EXIF 和软件信息，维持方向处理顺序 |
| `ImageProcessor._save_image()` | raw EXIF 非空才写入；失败或过大即跳过 EXIF | 始终构建品牌标识，采用分级降级与验证后发布 |
| 同一保存函数 | 直接删除传入 EXIF 中的 MakerNote/坏标签；JPEG 长度限制也用于 PNG | 仅改副本，按真实格式限制容量 |
| `ExifHelper.extract_raw_exif()` | 直接调用 piexif，异常返回 None | 按已知容器选择来源，补读 PNG/HEIC/AVIF 已打开图像的 EXIF 字节 |
| `src/core/batch_processor.py` | 复用 ImageProcessor，按布尔结果计数 | 验证失败传播，不另写标识逻辑 |
| `src/gui_pyside/pages/image_processing_page.py` | 生成结果为临时文件，导出用 `shutil.copy2()` | 验证最终副本以及重复生成失败时的状态语义 |

## 2. 元数据规则

### 2.1 字段选择与格式

| 输出格式 | 必须写入 | 示例 |
| --- | --- | --- |
| JPEG | EXIF 0th IFD 的 `Software`，即 `piexif.ImageIFD.Software` | `MiLecFrame` |
| PNG | 同一 EXIF `Software`，以及 PNG 文本字段 `Software` | 两处文本保持一致 |

`Software` 表示处理软件，符合本需求语义。不得把品牌标识写入 `Artist`、`Copyright`、相机型号、镜头型号或拍摄时间。无需同时写入 `UserComment`、XMP 或 IPTC，避免出现多套不一致字段。

是否在 Windows“属性 → 详细信息”中显示，取决于该格式的系统属性处理器。验收以文件内实际字段为准，不能只凭资源管理器界面是否显示判断成功。

### 2.2 原有软件信息与去重

| 输入软件字段 | 输出规则 |
| --- | --- |
| 缺失、空值或仅空白 | `MiLecFrame` |
| `Adobe Lightroom` | `Adobe Lightroom; MiLecFrame` |
| `Adobe Lightroom; MiLecFrame` | 保持，不再追加 |
| 存在大小写不同的同名产品 token | 规范为 `MiLecFrame`，仅保留一份 |
| `MiLecFramePlugin` 等不同名称 | 保留原名称，再追加独立的 `MiLecFrame` token |
| 字节类型或含尾部 NUL | 安全解码、去除终止 NUL，再应用上述规则 |

去重按分隔后的完整软件名称判断，不能仅做字符串子串搜索。新拼接使用 `; ` 分隔，不重排原软件名称，也不引入版本号。

`software_text` 和 PNG 文本不含 NUL。传给当前 piexif 1.1.3 的 Software 值为 `software_text.encode('ascii')`，**不手动追加 NUL**：该版本会自动在 TIFF ASCII 存储值末尾补一个 NUL。读回 EXIF 时统一严格 ASCII 解码并去除尾部 NUL 后比较；输入清理、存储终止符和只读验证是三个不同阶段，不能混用会自动补品牌名的规范化函数。

EXIF `Software` 属于 ASCII 字段。有效 ASCII 原值应保留；无法无损表达的非法或非 ASCII 原值，不得未经处理直接交给序列化器。建议在日志中记录字段降级原因，使用确定性的 ASCII 安全表达保留可表示部分；完全不可用或异常巨大时退回 `MiLecFrame`。这是异常输入兼容策略，不承诺对任意损坏软件字段逐字节保真。

### 2.3 输入元数据读取兼容

现有原始 EXIF 提取直接使用 piexif。JPEG/TIFF 可沿用原路径；PNG/HEIC/AVIF 则优先从现有加载器返回的源图像 `info['exif']` 捕获原始字节，再交给 piexif 解析，避免对已知不支持的容器反复调用路径解析并记录预期失败。捕获应发生在方向转正、色彩转换、HDR 转换和渲染之前；加载器已经规范化过的方向以返回图像为准，不能再次强行还原文件旧值。

优先级如下：

1. 可解析且非空的 EXIF `Software`，包括从 PNG/HEIC/AVIF 图像对象补读到的原始 EXIF。
2. 原始 EXIF 字节不可用或整体解析失败时，尝试源图像已有 `getexif()` 中可用的 Software，作为单字段补充；不为此重新构造整份 EXIF。
3. 原图为 PNG 时，其有效文本 `Software`。
4. 都不可用时，直接新建 `MiLecFrame` 标识。原字段确实不可读取时记录原因，不能宣称已保留。

EXIF 与 PNG 文本冲突时，以 EXIF 为准，输出统一两处内容，不无限合并重复历史。不得为补读软件字段额外完整解码一遍大图；复用已打开图像对象。HEIC/AVIF 的原软件名保留是本期明确要求，不再是待选项；合成夹具和真实样本验证分开记录。

本次只补齐标识与相关原值保留，不扩大为任意格式全部 EXIF/XMP/IPTC 的完整迁移工程。

### 2.4 统一写入流程

在 `ImageProcessor._save_image()` 中接入统一元数据构建函数，所有调用方复用。

1. 明确实际输出编码为 JPEG 或 PNG。
2. 对原始 EXIF 深拷贝；没有原始 EXIF 时建立可序列化的空 IFD 结构。
3. 从可用来源取得原软件字段并规范化，写入包含 `MiLecFrame` 的 `Software`。
4. 在副本上沿用已有 MakerNote 清理与不兼容标签容错，避免污染调用方对象。
5. 序列化 EXIF，并根据实际输出格式处理容量限制。
6. PNG 同时构建文本 `Software`；文本值必须与最终 EXIF 软件值一致。
7. 沿用现有 JPEG 质量、PNG 优化、色彩与 ICC 设置保存。
8. 读回必要的元数据，验证标识后才将文件发布为成功结果。

照片的方向修正和现有色彩处理保持原流程。不能因写入标识而把已经纠正的 Orientation 恢复成输入旧值。

### 2.5 异常兜底与成功条件

当前“EXIF 失败就不带 EXIF 保存”的行为需要调整为分级降级：

1. **优先完整保留**：在现有兼容范围内保留原 EXIF，加入标识。
2. **清理后重试**：仅清理确认无法序列化的字段及现有流程会移除的厂商数据。重试必须保证有进展，避免无限循环。
3. **最小标识兜底**：原 EXIF 无法序列化，或 JPEG EXIF 超过可用容量时，重新构造仅含必要软件标识的合法 EXIF；记录原字段发生丢弃。
4. **最终失败**：最小标识保存或读回验证仍失败，则报告该照片处理失败，进入现有单张/批量错误处理。

JPEG 的 EXIF 容量检查按其实际 APP1 载荷限制处理；不能继续把 JPEG 的阈值套用到 PNG。最小兜底时可以将软件字段收缩为 `MiLecFrame`，避免异常原软件文本导致兜底仍超限。

正常图片应保留现有流程支持的拍摄参数、作者、版权、GPS 等数据；异常兜底会损失部分或全部原 EXIF，必须在日志中如实记录，不能宣称完全保留。ICC 独立于 EXIF 管理，不因 EXIF 降级而被顺带删除。

### 2.6 输出文件与失败回滚

建议在目标目录中创建唯一临时文件，明确传入实际编码格式；保存并读回元数据验证成功后，再替换最终输出路径。

- 读回 JPEG EXIF 和 PNG EXIF/文本，不要求为此完整解码图像像素。
- 验证 `Software` 包含独立的 `MiLecFrame` 标识，PNG 两处值一致。
- 对已有最终输出，仅在调用方允许覆盖且新结果通过验证后替换；保持原有跳过语义。
- 保存、标识验证或最终替换失败时，清理本次临时文件，保留原有最终输出，不留下被误判为成功的新文件。
- GUI 返回失败时不设置 `is_processed=True`；批量失败计数沿用现有机制。
- 日志只记录格式、标识写入结果和必要异常，不输出整份 EXIF 或照片隐私数据。

## 3. 基础验收矩阵

| 编号 | 场景 | 通过标准 |
| --- | --- | --- |
| M01 | 有合法 EXIF 的 JPEG | 保留现有支持字段，Software 含 MiLecFrame |
| M02 | 无 EXIF 的 JPEG | 新建合法 EXIF，标识可读回 |
| M03 | PNG 输出 | EXIF 与文本 Software 一致且均包含标识 |
| M04 | 原 Software 有其他软件名 | 合法原值保留并追加一次 |
| M05 | 输出重新导入处理，包括 PNG | 不重复追加，原软件信息按规则保留 |
| M06 | 软件名含 MiLecFrame 子串但不是完整 token | 仍追加独立 MiLecFrame 标识 |
| M07 | EXIF 字段类型异常、MakerNote 过大 | 按策略降级，标识不丢失，日志说明原因 |
| M08 | 超出 JPEG 容量的 EXIF | JPEG 最小兜底成功；PNG 不误用 JPEG 阈值 |
| M09 | 输入 Software 为异常编码、NUL 或巨大文本 | 有界处理，不挂起，输出标识有效 |
| M10 | 原图经过 Orientation 转正 | 输出不会因元数据恢复旧方向而二次旋转 |
| M11 | 带 ICC、作者、版权和 GPS 的正常样本 | 新逻辑不额外破坏现有保留行为 |
| M12 | CLI 单张与批量，覆盖两种输出格式 | 每个实际成功输出都有标识，计数正确 |
| M13 | GUI 单张与一键导出 | 最终导出文件保留标识，不能只验证中间预览文件 |
| M14 | HEIC/AVIF 输入转 JPEG/PNG | 原软件名可读时保留并追加一次；无 EXIF 仍有标识；验证捕获不晚于转换 |
| M15 | 目标目录不可写、磁盘写入失败、标识读回失败 | 处理失败；既有最终文件不被损坏；无伪成功结果 |
| M16 | 批量中混合成功、失败和跳过 | 状态、计数及文件与各自语义一致 |
| M17 | 同一原始 EXIF 对象被复用 | 处理前后输入对象未被清理逻辑修改 |
| M18 | 仅开启本功能前后的对照导出 | PNG 解码像素一致；JPEG 使用相同编码参数时解码像素一致，ICC 等原设置一致 |
| M19 | ASCII 终止符与验证反例 | TIFF 存储含一个 NUL；EXIF 读回容忍尾部 NUL；缺品牌、重复品牌、非法值不能被验证器修复成通过 |
| M20 | 软件名转义与长度边界 | 4096 字符/字节和 1024 输出字节界限明确；字面反斜杠、非 ASCII、控制字符重复处理幂等 |
| M21 | JPEG 实际容量边界 | 完整 EXIF 字节 65533 可写读回、65534 走最小兜底；与不含头的 TIFF 长度区分 |
| M22 | PNG 读取是否解码像素 | 本程序输出用 info/getexif 验证不调用 load；输入 IDAT 后文本仍可在既有加载中取得 |

读回验证至少使用 Pillow；JPEG 可增加 piexif 交叉读取。PNG 文本和 EXIF 分别读取，不能只检查文件字节中是否出现 `MiLecFrame`。不得把“文件内任意位置有同名字符串”视为字段写入成功。

## 4. 确定的代码边界与接口契约

本功能只依赖已有 Pillow、piexif 和 Python 标准库。新增 `src/utils/output_metadata.py`，将元数据构建与文件 IO 分开；GUI 不调用该模块自行拼接字段，批量处理也不重复实现。

### 4.1 文件改动清单

| 文件 | 具体动作 | 验证重点 |
| --- | --- | --- |
| `src/utils/output_metadata.py`（新增） | 原软件名规范化、标识去重、深拷贝、EXIF 清理/降级、PNG 参数、输出字段验证 | 纯函数不改变输入；最小兜底始终包含标识 |
| `src/utils/exif_helper.py` | 保留 `extract_raw_exif()` 现有调用兼容；补 PNG/HEIC/AVIF 源 EXIF 和软件字段读取 | JPEG 行为不回退；容器补读不丢原软件名称 |
| `src/core/image_processor.py` | 捕获源软件信息；传入保存函数；临时写入、验证和发布 | 原方向/色彩流程保留；结果只在发布成功后为真 |
| `src/gui_pyside/pages/image_processing_page.py` | 首先验证现有失败与复制行为；仅有缺口时补充局部处理 | 本次失败不冒充成功；最终导出保留原文件元数据 |
| `src/core/batch_processor.py` / `src/main.py` | 优先只验证，不为标识改公开参数；确有失败传播缺口再局部修改 | 成功/失败/跳过状态和 CLI 退出码 |
| `README.md` / `CHANGELOG.md` | 功能完成后说明 Software 标识、格式与历史文件边界 | 不把可删除元数据描述成防篡改水印 |

本方案不修改 RenderContext、相框 YAML、Decorator、可见水印或 GUI 布局。新增资源路径一律走 `app_paths.py`，本功能原则上没有新增资源文件。

### 4.2 模型与函数

以下是建议签名与职责，最终名称可按项目风格调整；输入输出语义不可被省略。

| 接口 | 输入 | 返回/异常契约 |
| --- | --- | --- |
| `normalize_software(value)` | None、str 或 bytes | `SoftwareValue(text, reasons)`；text 是 ASCII 安全文本，恰有一个独立 MiLecFrame token |
| `prepare_output_metadata(raw_exif, output_format, software_hint=None)` | piexif 字典或 None；JPEG/PNG；源图像软件补充值 | `PreparedMetadata`，不得修改 raw_exif，不执行磁盘写入 |
| `PreparedMetadata` | 构建结果 | 至少含 `exif_bytes, software_text, pnginfo, level, reasons, removed_tags` |
| `decode_stored_software(value)` | 从 EXIF 读取的 str 或 bytes | 严格 ASCII 解码，去尾部 NUL；非法类型/编码即失败，不补值、不修复 |
| `verify_output_metadata(path, expected_format, expected_software)` | 本次临时输出路径和规范的期望值 | 按 §6.2 只读比较；字段缺失/值不符/编码不符抛 `OutputMetadataError` |
| `ImageProcessor._save_image(...)` | 原有参数，加仅关键字 `software_hint=None` | 成功仍返回 None；保存、验证、发布失败抛异常，供 process 转换为 False |

`level` 仅取 `preserved`、`cleaned`、`minimal`。`reasons` 使用短原因码，日志层再格式化；不要在原因码中嵌入原始 EXIF 全文。

常见原因码：`software_missing`、`software_invalid_type`、`software_escaped`、`software_too_long`、`tag_removed`、`jpeg_exif_oversize`、`exif_unserializable`。最小兜底失败使用 `OutputMetadataError`，不要返回一个没有 exif_bytes 的“成功对象”。

元数据构建完成后 `PreparedMetadata` 视为只读。不能在验证中重新推导另一个软件值，否则会掩盖构建和保存之间的不一致。

## 5. 数据处理算法

### 5.1 Software 规范化的固定顺序

以下限制是本方案为异常输入制定的默认执行值，实施如调整须在验证记录中写明原因。

1. 缺失、None 或空白直接生成 `MiLecFrame`。
2. 仅接受 str/bytes；其他类型记录 `software_invalid_type`，使用品牌名。不得把字典等内容整体转成字符串写入。
3. 对 str 按 Python `len()` 字符数、对 bytes 按字节数计算；超过 4096 直接降级。这是转义前输入限制，不是存储字节限制。
4. 先去除原值尾部 NUL，再逐单元映射为可打印 ASCII：保留 0x20–0x7E（包含原有反斜杠）；bytes 的其他值输出 `\xNN`；str 的非打印/非 ASCII 码点按宽度输出 `\xNN`、`\uNNNN` 或 `\UNNNNNNNN`，十六进制固定小写。此处不猜测相机私有编码。
5. 内部控制字符同样转义，不能原样写入；**原有反斜杠既不加倍，也不反解码**。因此已经转义成 ASCII 的文本再次输入保持不变。转义文本与原本字面文本可能同形，接受这种有损显示，不承诺可逆；无条件把反斜杠加倍会破坏幂等性。
6. 只按半角分号拆分，去除每段首尾空白和空 token。其他标点视作软件名的一部分，不随意破坏原名称。
7. 对完整 token 做不区分大小写比较，所有 `MiLecFrame` token 收敛成规范大小写的一份，保留首个所在位置；若不存在，在末尾追加。
8. 其他软件 token 保持次序，不主动去重或重排。用 `; ` 连接。
9. 最终文本的 ASCII 编码超过 1024 字节时，降级为 `MiLecFrame` 并记录原因；此限制不含序列化器最后添加的一个 NUL。不能截断品牌名或输出半个转义序列。

必须满足幂等性：`normalize(normalize(x).text).text == normalize(x).text`。

| 输入样例 | 期望输出 |
| --- | --- |
| None | `MiLecFrame` |
| `Adobe Lightroom` | `Adobe Lightroom; MiLecFrame` |
| `Adobe Lightroom; milecframe; MiLecFrame` | `Adobe Lightroom; MiLecFrame` |
| `MiLecFrame; Adobe Lightroom` | `MiLecFrame; Adobe Lightroom` |
| `MiLecFramePlugin` | `MiLecFramePlugin; MiLecFrame` |
| `; ; Camera Tool ;` | `Camera Tool; MiLecFrame` |
| 字面文本 `Camera\Tool` | `Camera\Tool; MiLecFrame`，再次处理不增加反斜杠 |
| 单个输入字节 0xFF | `\xff; MiLecFrame`，再次处理保持一致 |
| 非法类型、超长值 | `MiLecFrame`，同时返回对应原因码 |

### 5.2 PNG/HEIC/AVIF 源软件字段如何进入保存函数

1. 在输入加载器返回后、`_apply_exif_orientation()` 之前，捕获源图像 `info.get('exif')` 的不可变字节和能读取的软件值；不能保留会随对象转换失效的 info 引用，也不能在 `rendered_image.info` 上找原值。
2. JPEG 等原来可被 piexif 处理的输入继续走原有解析路径。
3. PNG/HEIC/AVIF 使用 `piexif.load(source_exif_bytes)`；HEIC/AVIF 来自现有 `HDRHandler.load_image()` 返回的图像对象，必须在后续 `convert_hdr_to_sdr()` 创建新图像前捕获。默认不使用 `getexif().tobytes()` 重组整份 EXIF；字节不可解析时只补读可用 Software。
4. PNG EXIF 没有有效 Software 时，优先读取源 `info['Software']`。输入 PNG 文本可能位于 IDAT 后，届时复用源图像本来就需要的一次加载再捕获其文本值；不能因为 Pillow 12 支持 PNG 就假定所有元数据都在 `Image.open()` 时可见，也不为补读重新打开解码第二遍。
5. `software_hint` 单独传入 `_save_image()`，只在 EXIF 软件值不可用时参与选择；不混入用于画面渲染的 `RenderMetadata`。
6. 源 EXIF 的 Orientation 仍按现有 `orientation_transposed` 逻辑修正，然后再传给输出构建函数。输入对象加载、关闭的责任要明确，不能提前关闭渲染仍需使用的图像。

“仅读元数据”不能笼统等同于所有 Pillow PNG 操作都不会加载像素。输入补读应复用已有加载；输出验证则针对本程序写在标准位置的字段，并通过运行时探针确认读取代价。

### 5.3 构建、清理和最小 EXIF

1. 深拷贝 raw_exif。顶层结构不合法或无法复制时记录原因，直接建立最小结构。
2. 确保 0th/Exif/GPS/Interop/1st IFD 以及 thumbnail 的结构符合 piexif 的输入要求。不要凭空发明拍摄时间、设备、GPS 或作者。
3. 写入规范化 Software 的 ASCII 字节，不手动加 NUL；piexif 1.1.3 在存储层补一个终止符。最小结构采用同样规则，PNG 文本始终无 NUL。
4. 在副本中沿用已有 MakerNote 移除行为；只记录标签名称/ID，不打印内容。
5. 仅围绕 `piexif.dump()` 捕获序列化 `Exception`，包括真实存在的 `UnboundLocalError`；不要只捕获 ValueError/TypeError。MemoryError 直接上抛；KeyboardInterrupt/SystemExit 等 BaseException 不捕获。报错能可靠定位现存坏标签时，删除后重试，每轮减少一个字段，默认最多清理 32 个字段。
6. 无法定位、重复报同一问题、达到重试上限，或 Software 本身异常时转最小结构；不能猜标签。现有循环已通过删除标签保证有限递减，新增 32 次限制属于显式预算，不把旧实现误称为必然无限循环。
7. JPEG 使用**完整序列化 EXIF 字节** `len(exif_bytes) <= 65533`，其中已含 6 字节 `Exif\0\0` 前缀；不含前缀的 TIFF 部分上限才是 65527。当前 Pillow 12.2.0 已实测完整长度 65533 可保存读回、65534 拒绝；PNG 不套用此门槛。依赖版本变更后重验。
8. 最小结构保留 Software=`MiLecFrame`，其余 IFD 为空、thumbnail=None；像素已转正时省略 Orientation 等价于不再要求旋转，不写回旧值。
9. 最小结构再次 dump，仍失败则转换为 OutputMetadataError 并保留异常链；不再嵌套兜底。PNG 文本值取最终 software_text，若降级时收缩成品牌名，两处同步收缩。以上捕获范围不包住磁盘写入、读取或最终发布。

原图 MakerNote、无效字段及容量兜底带来的丢失沿用或明确记录；不要把“保留 EXIF”扩写为所有原始字节不变。正常样本的相机、镜头、曝光、作者、版权、GPS 等字段需要逐项对比。

### 5.4 实际格式判定

- `.jpg` / `.jpeg` 对应 JPEG，`.png` 对应 PNG，保持现有显式输出路径规则。
- 如进入原格式兜底分支，只有实际编码仍为 JPEG/PNG 才套用本方案；按实际编码而不是陌生后缀判断元数据能力。
- 已核实当前 CLI 会把输出后缀规范为 JPEG/PNG，GUI 和批量同样只生成这两种后缀；标准入口不会请求其他输出格式。但 `ImageProcessor.process()` 可被代码直接调用，不能据此断言保存函数 else 分支绝对不可达。
- 对直接调用产生的其他实际格式，**保留原有保存能力与旧有元数据路径，输出明确 WARNING：该格式未启用品牌元数据保证**；不调用只支持 JPEG/PNG 的新构建/验证器，不宣称通过本方案的标识验收。标准入口的 JPEG/PNG 禁止使用该兼容分支逃避品牌写入。
- 因此成功标识保证严格覆盖本期 JPEG/PNG，其他格式是明确告警的既有兼容路径。实施前仍要重检调用点，不新增格式、不把已有能力静默改成报错。

## 6. 保存事务与调用方状态

### 6.1 保存时序

1. 先准备并验证内存中的元数据，再开始生成最终文件的磁盘产物。
2. 在目标所在目录用唯一名字创建临时文件。Windows 下先关闭 `mkstemp` 返回的句柄，再由 Pillow 写入，避免文件占用；不要在仍打开的 NamedTemporaryFile 上重复打开。
3. JPEG 保持当前 `quality=95, optimize=True`，PNG 保持 `optimize=True`；继续显式传入 ICC 与实际 `format`。
4. 写 EXIF；PNG 同时传入只包含本次明确需要字段的 `PngInfo`。不要自动把源图所有文本复制过去，扩大现有隐私或格式行为。
5. 保存结束后关闭写入句柄，用独立读取句柄验证实际图像格式及软件字段；验证句柄也必须在发布前关闭。
6. 按 §6.2 对 EXIF 做只读解码与尾部 NUL 去除后，必须与构建阶段 expected_software 精确相同；PNG 文本也必须精确相同且不含 NUL。原始读回值先验证再比较，不调用会补品牌或去重的构建函数。
7. `os.replace()` 把同目录临时文件替换为最终输出；该操作失败则本次保存失败，不先删除原文件。
8. 无论在哪一步失败，finally 只清理本次创建的临时文件；清理失败另记 WARNING，不掩盖原始异常。

这保证正常异常处理中的“验证后发布”，不承诺断电后的持久化事务。已有输出在验证/替换失败时必须保持原字节；目标不存在时，不得留下一个被报告成功的最终文件。

### 6.2 输出验证的读取策略

JPEG 通过 Pillow 的 getexif 读取 Software，验收时用 piexif 交叉核对。当前 Pillow 12.2.0 的 PNG 输出可通过 `getexif()[305]` 和 `info['Software']` 读取本程序写出的字段，无需解码像素。**验证器禁止用 `.text` 属性代替 `info`**：本轮实测首次访问 `.text` 调用了 load，并非纯元数据读取。

验证必须按下列顺序执行：

1. 字段缺失、值为 None 或非法类型直接失败，不能替换成默认品牌名。
2. EXIF bytes 使用严格 ASCII 解码；str 先确认全部为 ASCII。只允许去掉尾部 NUL，不做去重、补品牌、反斜杠转义或大小写修复；内部 NUL/控制字符直接失败。
3. decoded_text 必须精确等于不带 NUL 的 expected_software。另对原读回的去终止符文本按分号检查恰有一个完整 MiLecFrame token，不接受重复品牌。
4. PNG 文本字段必须是无 NUL、无非法控制字符的 ASCII str，精确等于 expected_software 及去终止符后的 EXIF 文本；PNG 文本不是 EXIF ASCII 存储字段，不能擅自追加终止符。
5. 构建函数可以修复输入，验证函数只能证明输出已正确。不能复用 `normalize_software()` 验证：它会给缺品牌值补品牌、把重复品牌收敛成一份，造成坏文件假通过。

原始字节类型差异和 EXIF 终止符通过只读解码解决，不需要把比较放宽为任意 token 修复后的相等。有效输入的规范化和输出严格验证使用不同函数，是有意的边界。

生产验证不主动调用完整图像解码来比较像素。若安装版本必须加载像素才能获取输出字段，先测量额外成本并调整只读元数据的读取实现，不能在大图批量路径中静默增加一次完整解码。像素一致性只在验收阶段做。

### 6.3 失败只重试元数据，不反复重做图片

EXIF 清理与最小兜底尽量在 `image.save()` 前完成。遇到磁盘写入失败、无权限、目标文件被占用时直接失败，不再套用“最小 EXIF”重试，因为这些不是元数据错误。

容量预检是正常路径的首要判断，不能只依赖捕获 image.save 的 ValueError：无关 ValueError 也可能来自图像编码。已通过 65533 完整字节预检却被当前编码器拒绝，应作为边界或依赖回归报告失败并保留旧输出，不能随意吞掉后另存无标识图片。

不得通过“第一次保存失败后去掉所有 EXIF 再保存”来提高成功率。若读回发现缺失品牌字段，应报告失败并保存诊断原因；不能直接删除验证步骤绕过问题。

### 6.4 GUI、批量和跳过规则

- `process()` 只有在验证和最终发布都成功之后才返回 True，沿用原先的异常日志入口。
- 批量成功/失败计数由这一结果驱动；`success + fail + skip == total`。局部失败不妨碍其余图片继续处理。
- GUI 首次生成失败，不设置新的 result_path，不设置本次成功状态。
- GUI 现状已在失败时保留上一份 is_processed/result_path，不重构此状态模型。有上次有效结果时，普通失败及异常分支统一提示“本次生成失败，已保留上次结果”；首次失败提示“生成失败”。不把本次临时路径替换进去，不将旧结果算成本次成功。
- 一键导出继续复制已成功生成的结果文件，验证复制后的文件哈希与源结果一致并读回标识，不经 QPixmap 二次编码。
- 跳过已有文件的检查仍在原有调用层，不在本期改变覆盖参数。既有“检查后另一个进程创建文件”的并发覆盖语义不在本期扩展，临时输出发布不能被宣传为多进程输出锁。

## 7. 按顺序执行的任务清单

| 任务 | 前置条件 | 执行动作 | 本步完成证据 |
| --- | --- | --- | --- |
| M-T0 基线 | 无 | 激活 venv；记录 git 状态、依赖版本、调用点、日志起点；对照本次复核记录 | 确认序列化终止符、完整 EXIF 长度、PNG API 与版本相符；不照抄审阅中的冲突结论 |
| M-T1 字段规范化 | M-T0 | 实现 normalize_software、只读解码器、原因码和边界限制 | §5.1 示例及 M20 通过；构建幂等，验证不补值 |
| M-T2 容器输入兼容 | M-T1 | 捕获 PNG/HEIC/AVIF 源 EXIF 和 software_hint，避开转换后的元数据丢失 | 原软件可读取时保留；PNG 冲突与二次输入符合规则；合成与真实样本分开记录 |
| M-T3 EXIF 构建 | M-T2 | 实现副本、清理、有界重试、格式容量检查和最小兜底 | M01–M11、M17、M21 及 M19 存储终止符验证通过；原字典不变 |
| M-T4 保存事务 | M-T3 | 接入同目录临时写入、只读严格比较、最终替换和清理 | M19 验证反例及 M22 读取探针通过；JPEG/PNG 无无标识成功输出 |
| M-T5 调用链实测 | M-T4 | CLI 单张/批量；GUI 生成/重复生成/单张和一键导出 | M12–M16 通过，错误计数与提示正确 |
| M-T6 回归与性能 | M-T5 | 对照像素、ICC、Orientation；记录保存/验证耗时与峰值内存 | M18 通过；无新增完整图像解码或图像副本造成异常增长 |
| M-T7 收尾 | M-T6 | 全修改文件 py_compile；日志检查；必要的便携包验证；文档与报告 | 有可核验记录；剩余未验证项明确列出 |

可先完成 M-T1 至 M-T4 的内部临时验证，再运行完整渲染，不必为每个坏标签都重新启动 GUI。但这些内部检查不能替代 CLI 单张、批量及 GUI 导出实测。

## 8. 夹具、故障注入与执行命令

### 8.1 最小夹具集

在项目忽略目录 `test_images/metadata_branding_validation/<run-id>/` 中保存输入、输出与报告，不把用户原图改成测试文件。

| 夹具 | 内容 | 用途 |
| --- | --- | --- |
| plain.jpg / plain.png | 无 EXIF 的小型合成图 | M02、M03 基线 |
| full.jpg | 合法设备、曝光、作者、版权、GPS、Software 和 ICC | 正常字段保留与软件追加 |
| rotated.jpg | Orientation=6 且具有可辨别方向的像素图案 | 验证不会二次旋转 |
| software_text.png | 只有文本 Software，无 EXIF Software | PNG 软件名补读 |
| software_exif.png | 有 EXIF Software，无文本 Software | PNG EXIF 保留与双字段输出 |
| software_conflict.png | 两处 Software 值不同 | 验证以 EXIF 为准 |
| malformed/oversized 数据对象 | 构造异常 piexif 字典传入内部函数 | 不能依赖正常编码器生成损坏 EXIF 文件 |
| synthetic.heic / synthetic.avif | 用已安装编码器生成、含原 Software 和嵌套 EXIF 的小图 | 验证对象源字段读取与追加；不冒充真实拍摄兼容性验收 |
| real.heic / real.avif | 本地可合法使用、原 Software 已知、现有管线能打开的样本 | 原软件名追加保留与输入兼容；缺样本如实标记未验证 |
| large.jpg | 具有代表性分辨率的照片 | 内存和额外保存验证成本 |

对每份正常元数据样本保存关键字段期望值；日志只保存断言结论，不把全部 GPS、作者或 EXIF 内容写入仓库。

### 8.2 必须执行的故障注入

| 注入点 | 方式 | 预期结果 |
| --- | --- | --- |
| 序列化异常 | 临时替换序列化器，使其先报可定位坏标签 | 仅删除目标字段并有界重试，Software 保留 |
| 无法定位的异常 | 真实坏值 XResolution='abc' 触发 piexif UnboundLocalError，再做受控异常注入 | 直接走最小兜底，不猜标签，不静默无 EXIF 出图 |
| 最小兜底也失败 | 控制序列化器所有调用失败 | process=False，最终文件不被发布 |
| 保存写入失败 | 临时替换保存调用抛 OSError，或使用隔离不可写目录 | 不重试成无元数据保存；旧输出哈希不变 |
| 验证字段丢失 | 给实际验证器传入字段缺失、仅有其他软件名、重复 MiLecFrame、PNG 两处冲突的真实小文件 | 验证器本身拒绝坏输出；不能只用假验证器抛异常替代这一检查 |
| 最终替换失败 | 临时替换 os.replace 或独占目标文件 | 原文件不变；本次临时文件清除 |
| 清理失败 | 模拟临时文件 unlink 失败 | 主异常仍可见，额外记录清理告警 |
| 相同 EXIF 对象复用 | 深拷贝快照对比并连续处理两次 | 原输入对象完全不变，无渐进删字段 |

故障注入仅用于临时验证，结束后恢复替换对象；不得把测试开关或强制失败分支留在生产代码中。

### 8.3 语法及 CLI 实测

以下命令为实现完成后的示例，当前文档任务不执行。先创建夹具并按实际文件名替换输入路径，输出目录应为空以避免默认 skip-existing 掩盖测试。

```powershell
.\venv\Scripts\activate
python -m py_compile D:\Coding\MiLecFrame\src\utils\output_metadata.py D:\Coding\MiLecFrame\src\utils\exif_helper.py D:\Coding\MiLecFrame\src\core\image_processor.py
python D:\Coding\MiLecFrame\src\main.py -i D:\Coding\MiLecFrame\test_images\metadata_branding_validation\input\plain.jpg -o D:\Coding\MiLecFrame\test_images\metadata_branding_validation\single\plain.jpg
python D:\Coding\MiLecFrame\src\main.py --batch -i D:\Coding\MiLecFrame\test_images\metadata_branding_validation\input -o D:\Coding\MiLecFrame\test_images\metadata_branding_validation\batch_jpeg --output-format JPEG
python D:\Coding\MiLecFrame\src\main.py --batch -i D:\Coding\MiLecFrame\test_images\metadata_branding_validation\input -o D:\Coding\MiLecFrame\test_images\metadata_branding_validation\batch_png --output-format PNG
```

实际使用时在上述验证根目录中加入本轮 run-id；修改了其他 Python 文件就一起 py_compile。命令退出后还需运行读回断言，不能仅靠控制台“成功”文字判定。

不运行不存在的 pytest/unittest 套件。临时验证代码应直接调用实际模块，记录断言、输出格式、实际 Software 值、兜底级别及文件是否存在。

### 8.4 对照与性能

- 对照编码使用同一个已经渲染好的图像对象、相同编码参数，仅改变元数据写入；避免两次完整渲染的动态时间、缓存或用户设置影响像素比较。
- PNG 比较解码像素及尺寸；JPEG 在同一编码器、同参数下比较解码像素。整个文件哈希会因元数据改变而变化，不应要求文件完全相同。
- ICC、Orientation、关键拍摄字段单独对比；不把“像素一致”代替元数据保留检查。
- 分开记录 metadata_prepare、image_save、metadata_verify、publish 的耗时，代表性大图至少运行一轮完整批量。
- 本方案不预设未经测量的毫秒指标；验收要求无额外完整图像解码、无保存每张照片后累计持有大对象。若安装版本无法满足，应先优化读取方式并如实记录剩余成本。

## 9. 独立完成门禁与交付

建议提交主题：`feat: 为输出照片写入 MiLecFrame 软件标识`。是否创建提交以实施任务授权为准；不为本任务自行升版本或发行。

1. M-T0 至 M-T7 都有执行结果；M01–M22 逐项标注通过、失败或未验证，不能只打一个总勾。
2. JPEG/PNG、无 EXIF、二次处理、兜底和写入失败均为必过场景；CLI 单张与批量、GUI 实际导出必须实测。
3. 正常路径无新增 ERROR/TRACEBACK。故障注入的预期失败单独列出，不能当作未解释的正常错误。
4. 生产日志使用 `[output-metadata]` 前缀，记录格式、level、reason、移除标签 ID 与阶段耗时；不打印原始元数据全文。
5. 所有新增及修改 Python 文件语法检查通过。涉及新增模块打包或依赖/资源改动时，完成项目要求的便携包冒烟；本期不引入新第三方依赖。
6. 报告包含实际改动文件、验证命令、夹具类型、字段读回结果、失败回滚证据、性能记录和未验证项。
7. 保留其他任务的 CSV、文档和未提交改动。不得为完成此功能重置工作区或改写 release 历史。

如果缺少真实 HEIC/AVIF 样本、GUI 操作环境或便携包验证条件，应把对应项列为未验证，继续完成不受影响的检查，不能宣称全部门禁已通过。

本轮修订仅修改文档，并执行内存中的依赖行为探针，没有执行 M-T0 至 M-T7 的生产实现，没有改写照片或 Python 文件。探针只能证明记录中的具体依赖行为，不能代替后续调用链与功能验收。

## 10. 参考与限制

- [项目 AGENTS.md](../../AGENTS.md)：venv、注释、语法校验、实际运行验证与发行流程。
- [Pillow 图像格式文档](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html)：EXIF、PNG 文本以及格式保存参数。
- [独立的桌面快捷方式方案](DESKTOP_SHORTCUT_EXECUTION_PLAN.md)：另一项功能，不是本功能实施或验收依赖。

元数据可被后续编辑器删除，不是不可移除的画面水印、版权证明或数字签名。Windows 属性页是否显示字段不影响结构化读回的结果。历史照片补标、其他输出格式的全面支持和任意元数据无损迁移均不属于本期。
