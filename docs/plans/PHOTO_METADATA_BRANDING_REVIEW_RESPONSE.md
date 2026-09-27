# 照片元数据方案：审阅复核与修订记录

> 日期：2026-09-26  
> 对照材料：[外部审阅报告](PHOTO_METADATA_BRANDING_EXECUTION_PLAN_REVIEW.md)  
> 修订成果：[执行方案 v2](PHOTO_METADATA_BRANDING_EXECUTION_PLAN.md)  
> 实测环境：本项目 venv，Pillow 12.2.0、piexif 1.1.3、pillow-heif 1.3.0。  
> 范围：复核并修订规划文档；未修改生产 Python、真实照片或外部审阅原文。

## 1. 复核结论

审阅指出的验证契约不够明确、异常捕获需要细化、HEIC/AVIF 原软件名缺少来源、其他格式兼容行为不够具体等问题成立，已修订。

但报告中的部分技术结论不能直接作为实施基线：**piexif 自动补 NUL、完整 EXIF 容量单位、PNG `.text` 是否加载像素**均与本项目实际依赖源码和本轮探针结果不符。转义反斜杠和输出验证的建议也需要调整，否则会引入幂等性或假通过问题。

本轮保留报告作为原始审阅材料，不修改其结论；由本记录说明证据差异。方案的“待实施”状态不因探针通过而改变。

## 2. 逐项处理结果

| 审阅条目 | 处理 | v2 采用的规则 |
| --- | --- | --- |
| P0-1 NUL 契约 | 采纳补全契约，纠正根因及手动补 NUL 建议 | piexif 入参不带 NUL，由序列化器补一个；EXIF 只读解码后去尾部 NUL 比较 |
| P0-2 验证比较 | 采纳严格定义比较，不采用修复后比较 | 验证不调用 normalize_software；不补品牌、不去重、不修大小写，解码后与期望精确相等 |
| P0-3 序列化异常 | 采纳 | dump 的异常边界覆盖 UnboundLocalError；不能定位就最小兜底；不吞内存耗尽或进程退出信号 |
| P1-1 HEIC/AVIF 原软件名 | 用户已确认保留 | 从加载器返回图像捕获 EXIF 字节和软件字段，在后续转换前补读并追加品牌 |
| P1-2 原格式兜底 | 采纳明确行为的建议 | 标准入口仍为 JPEG/PNG；直接调用的其他格式保留旧能力并告警，不宣称品牌保证 |
| P2-1 反斜杠映射 | 采纳明确映射，不采用无条件加倍 | 原有 ASCII 反斜杠保持不变，新转义不再反解码，接受非可逆显示以保持幂等 |
| P2-2 长度单位 | 采纳 | str 输入按字符、bytes 输入按字节；最终 ASCII 文本按字节，不含存储 NUL |
| P2-3 GUI 提示 | 采纳 | 保留现有旧结果状态；本次失败且有旧结果时提示“本次生成失败，已保留上次结果” |
| PNG EXIF 来源 | 采纳 | 优先 `info['exif']` 原始字节，不默认通过 getexif().tobytes() 重组 IFD |
| PNG 所有文本均懒加载可见 | 不采纳该概括 | info/getexif 能读取本程序输出字段；`.text` 会 load；尾部文本可能加载后才出现 |
| JPEG 65533 判定略宽松 | 不采纳 | 65533 是包含 Exif 头的总长度，65527 是 TIFF 部分；两个数不能直接替换 |
| 超限主要靠捕获 save 的 ValueError | 不采纳作为主路径 | 序列化完整长度预检先分流；磁盘错误及其他编码错误不误当元数据问题 |

## 3. 本轮复测证据

所有图像探针使用 `BytesIO` 和小型合成图，不写真实图片文件，不调用应用生产处理或启动 GUI。源码行号以本项目安装版本为准，升级后须重新核对。

### 3.1 piexif 会自动补 NUL

安装源码 `venv/Lib/site-packages/piexif/_dump.py:220` 的 ASCII 分支对 str 和 bytes 都追加 `b'\x00'`，然后计算 TIFF count。

本轮不只比较两个 dump 是否相同，而是解析其 TIFF IFD 的字段类型、count、偏移和实际载荷：

| piexif 的 Software 入参 | TIFF count | 存储载荷 | piexif/Pillow 读回值 |
| --- | --- | --- | --- |
| `b'MiLecFrame'` | 11 | `b'MiLecFrame\x00'` | 不带 NUL 的文本 |
| `b'MiLecFrame\x00'` | 12 | `b'MiLecFrame\x00\x00'` | 带一个尾部 NUL 的文本 |

因此，外部报告“两个 dump 结果不相同”这一观察成立，但不能推导出“dump 不自动补 NUL”。差异实际上来自第二个入参被再次补 NUL。

v2 不手动追加终止符，并区分三层：构建文本不含 NUL；存储包含一个 NUL；读回兼容尾部 NUL。PNG 文本不带终止符。

### 3.2 JPEG 容量的两个数指向不同对象

安装源码 `venv/Lib/site-packages/PIL/JpegImagePlugin.py:761` 定义 `MAX_BYTES_IN_MARKER = 65533`，`:803` 直接与 `len(exif)` 比较。

使用真实 piexif.dump 字节构造精确总长度，并在保存后重新打开文件核对 EXIF 长度：

| 完整 exif_bytes 长度 | 结果 |
| --- | --- |
| 65527 | 保存并读回成功 |
| 65528 | 保存并读回成功 |
| 65532 | 保存并读回成功 |
| 65533 | 保存并读回成功 |
| 65534 | ValueError: EXIF data is too long |

APP1 的长度字段包括自身 2 字节，留给 EXIF 载荷的是 65535−2=65533；载荷中 6 字节的 `Exif\0\0` 头由 piexif.dump 已经包含，所以纯 TIFF 内容才是 65527。

原项目对完整 dump 使用 65533 并不宽松。原实现真正需要修正的是把 JPEG 限制也用于 PNG，以及超过限制直接放弃标识的行为。

### 3.3 PNG `.text` 会触发加载

本轮为每种访问方式重新打开同一个合成 PNG，包装该实例的 `load()` 计数，避免前一个读取行为污染后一个观察：

| 访问方式 | load 调用次数 | 读取后待解码 tile 数量 |
| --- | --- | --- |
| `im.info['Software']` | 0 | 1 |
| `im.getexif()[305]` | 0 | 1 |
| `im.text['Software']` | 1 | 0 |

安装源码 `venv/Lib/site-packages/PIL/PngImagePlugin.py:831` 的 text 属性在 `_text is None` 时调用 load，以包含文件尾部的文本块。

另构造合法 tEXt 位于 IDAT 后、IEND 前的 PNG：刚 Image.open 时 `info.get('Software')` 为 None，调用已有图像的 load 后才为 `Adobe Lightroom`。这证明不能把本程序默认写出的头部文本推广为所有输入 PNG 的普遍情况。

v2 生产输出验证使用 info/getexif，不访问 `.text`。输入补读沿用源图像本来需要的一次加载，禁止另开一次大图完整解码。

### 3.4 异常捕获缺口确实存在

本轮复现：

- `Software=12345` 导致包含标签 ID 的 ValueError，可定向处理。
- `XResolution='abc'` 导致不含标签 ID 的 UnboundLocalError，不能沿用只捕获 ValueError/TypeError 的分支。

v2 在 dump 调用周围设置明确异常边界，无法定位时转最小 EXIF；最小 EXIF 仍失败则上抛。MemoryError 和 BaseException 类退出信号不被当作普通坏元数据吞掉，磁盘 IO 也不纳入该兜底。

现有 while 循环每次删除一个实际标签，本身已有限递减。32 次限制是新增明确预算，而不是修复一个已证实的无限循环。

### 3.5 HEIC/AVIF 可通过已加载对象暴露 EXIF

用户已选择保留原软件名称。本轮合成夹具分别使用 pillow-heif 的 HEIF 编码/加载，以及 Pillow 的 AVIF 编码/加载，确认其图像对象 `info['exif']` 可交给 piexif.load。

| 合成容器 | Software | 嵌套 Exif.FocalLength | 返回的 Orientation |
| --- | --- | --- | --- |
| HEIF | Adobe Lightroom | (50, 1) | 1 |
| AVIF | Adobe Lightroom | (50, 1) | 6 |

输入夹具原本指定 Orientation=6，HEIF 路径已返回规范化后的 1。这提示执行者应尊重加载器返回的像素与元数据关系，不能在后续重新套用文件旧方向。

该探针仅证明当前编码器合成样本存在可用来源，**不等于通过现有 HDRHandler 整条管线，也不等于真实相机 HEIC/AVIF/HDR 样本均兼容**。真实样本与 GUI/CLI 验收仍留在 M14、M-T5。

### 3.6 反斜杠加倍不具有幂等性

对字面输入 `Camera\Tool` 无条件执行 `replace('\\', '\\\\')`，第一次和第二次结果不同；每轮都会继续增加反斜杠。

v2 明确保留已有可打印 ASCII，包括反斜杠，仅对非打印字符和非 ASCII 单元产生 ASCII 转义。不反解码这些转义，接受显示层非可逆性，从而保证下一轮输入仍是稳定的可打印 ASCII。

### 3.7 验证器不能修复输出

这项是函数契约分析，不是已实现验证器的测试结果。若复用会自动补品牌、去重的 normalize_software：

- 缺品牌的 `Adobe Lightroom` 会被补成期望值，可能假通过。
- 重复的 `MiLecFrame; MiLecFrame` 会被收敛成一个，可能假通过。

因此 v2 仅共享不会改变语义的只读解码/字段拆分步骤，不共享构建修复。EXIF 严格解码并去掉尾部 NUL 后精确比较，PNG 文本无 NUL 且精确比较。实际坏文件必须传给真实验证器，不能只让一个假验证器抛异常来代替拒绝能力检查。

## 4. 最小复现片段

以下代码可在激活 venv 后通过 PowerShell here-string 输入 Python，无需保存 `.py` 文件。所有输出在内存中；片段用于确认关键依赖行为，不是生产实现。

```python
import io
import struct
import piexif
from PIL import Image, PngImagePlugin

def dump_software(value):
    # 保持夹具结构简单，使 Software 是 0th IFD 的唯一条目。
    return piexif.dump({"0th": {305: value}, "Exif": {}, "GPS": {},
                        "Interop": {}, "1st": {}, "thumbnail": None})

def stored_ascii(raw):
    # 验证实际 TIFF 存储载荷，而不是由两个 dump 不同推测 NUL 行为。
    tiff = raw[6:]
    endian = ">" if tiff[:2] == b"MM" else "<"
    offset = struct.unpack(endian + "I", tiff[4:8])[0]
    entry = tiff[offset + 2:offset + 14]
    tag, kind, count, address = struct.unpack(endian + "HHII", entry)
    assert (tag, kind) == (305, 2)
    return tiff[address:address + count] if count > 4 else entry[8:8 + count]

assert stored_ascii(dump_software(b"MiLecFrame")) == b"MiLecFrame\x00"
assert stored_ascii(dump_software(b"MiLecFrame\x00")) == b"MiLecFrame\x00\x00"

# 使用真实 dump 长度检查完整 EXIF 的边界，避免混淆纯 TIFF 部分。
image = Image.new("RGB", (8, 8))
overhead = len(dump_software(b"X" * 100)) - 100
for length in (65533, 65534):
    raw = dump_software(b"X" * (length - overhead))
    assert len(raw) == length
    buffer = io.BytesIO()
    try:
        image.save(buffer, format="JPEG", exif=raw)
    except ValueError as error:
        assert length == 65534 and str(error) == "EXIF data is too long"
    else:
        assert length == 65533
        with Image.open(io.BytesIO(buffer.getvalue())) as result:
            assert len(result.info["exif"]) == length

# 使用新实例分别探测字段读取，记录 load 调用而非仅检查返回值。
info = PngImagePlugin.PngInfo()
info.add_text("Software", "MiLecFrame")
buffer = io.BytesIO()
image.save(buffer, format="PNG", exif=dump_software(b"MiLecFrame"), pnginfo=info)
for field in ("info", "getexif", "text"):
    with Image.open(io.BytesIO(buffer.getvalue())) as result:
        calls = []
        original_load = result.load
        def counted_load(*args, **kwargs):
            # 只包装本实例，不修改库文件或后续实例。
            calls.append(1)
            return original_load(*args, **kwargs)
        result.load = counted_load
        if field == "info":
            assert result.info["Software"] == "MiLecFrame"
        elif field == "getexif":
            assert result.getexif()[305] == "MiLecFrame"
        else:
            assert result.text["Software"] == "MiLecFrame"
        assert len(calls) == (1 if field == "text" else 0)
```

## 5. 交付与未完成事项

已完成：执行方案 v2、此复核记录、当前依赖的内存探针，新增 M19–M22 验收项。原外部审阅文件保持不变，快捷方式方案不受本轮影响。

未完成且不作成功声明：生产函数实现、22 项完整功能验收、真实照片回归、GUI 操作、CLI 单张/批量和便携包冒烟。没有修改 `.py` 文件，因此本轮没有需要执行 py_compile 的生产文件。

后续执行以 v2 契约及证据为准，不能将外部审阅的冲突断言直接抄为已验证事实。
