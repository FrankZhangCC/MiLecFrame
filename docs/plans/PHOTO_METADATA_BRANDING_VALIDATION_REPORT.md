# 照片元数据 MiLecFrame 标识：实施与验收报告

> 日期：2026-09-26
> 依据：[执行方案 v2](PHOTO_METADATA_BRANDING_EXECUTION_PLAN.md)
> 基线：dev `a107994`（实施前已复核）；依赖实测 Python 3.14.2 / Pillow 12.2.0 / piexif 1.1.3 / pillow-heif 1.3.0
> 状态：M-T0–M-T7 全部执行完毕；M01–M22 逐项结果见 §3；未验证项见 §8。
> 提交状态：**未创建提交**（按方案 §9，提交以实施任务授权为准）；工作区中其他任务的未提交改动（FONT_BASELINE 文档移动、`data/*.csv`、其他计划文档）均未触碰。

## 1. 实际改动文件

| 文件 | 改动 |
| --- | --- |
| `src/utils/output_metadata.py`（新增） | 规范化、只读解码、EXIF 构建/清理/降级、PNG 文本、输出验证、导出读回 |
| `src/utils/exif_helper.py` | 新增 `extract_raw_exif_from_bytes()`（容器 EXIF 字节解析）、`extract_software_hint()`（单字段补读）；`extract_raw_exif()` 原签名与行为不变 |
| `src/core/image_processor.py` | 加载后立即捕获源元数据（`_capture_source_metadata`）；按已知容器选择 EXIF 来源；`_save_image` 改为"临时写入 → 读回验证 → 发布"事务，新增仅关键字 `software_hint`；非 JPEG/PNG 走 `_save_legacy` 兼容路径并告警 |
| `src/gui_pyside/pages/image_processing_page.py` | 生成失败/异常的用户提示（区分首次失败与保留上次结果）；导出增加"复制 → 哈希一致 → 标识读回 → 发布"的 `_export_verified()`（单张与一键共用） |
| `README.md` | 功能表新增"输出元数据标识"一行 |
| `CHANGELOG.md` | `v2.7.0-dev` 条目新增 feat 小节（含"可被编辑器删除，非不可移除水印"的边界说明） |

未改动：`RenderContext`、相框 YAML、`Decorator`、可见水印、GUI 布局、`batch_processor.py`、`main.py`（二者按方案 §4.1 只验证、不改公开参数）、任何第三方依赖（未新增）。

## 2. 验证方式与夹具

- 夹具根目录：`test_images/metadata_branding_validation/run20260926-164303/`（项目 gitignore 目录），含 `input/`（合成夹具）与 `v1/`–`v6/`、`cli/`（各轮输出与报告产物）。
- 夹具类型：`plain.jpg/png`（无 EXIF）、`full.jpg`（相机/曝光/作者/版权/GPS/ICC/Software/MakerNote）、`rotated.jpg`（Orientation=6 + 可辨方向图案）、`software_text.png` / `software_exif.png` / `software_conflict.png`（三种 Software 来源与冲突）、`synthetic.heic` / `synthetic.avif`（已安装编码器合成）、`large.jpg`（4000×3000，性能用）、`broken.jpg`（批量失败注入）、`oversized/malformed EXIF`（内存构造，非文件）。
- 临时验证代码（直接调用生产模块，未写入仓库）：`m0_probe`（依赖探针）、`m1_test`（规范化）、`m2_probe`/`m2b`（容器来源与 PNG 读取代价）、`v1_test`（构建/保存矩阵）、`v2_test`（完整 `process()`）、`v3_inject_test`（故障注入）、`v4_cli_test`（CLI 子进程）、`v5_gui_test`（GUI offscreen 驱动）、`v6_final_test`（M15/M18/性能）、`v7_otherfmt_test`（非 JPEG/PNG 兼容分支）。
- 全部被修改的 `.py` 已通过 `python -m py_compile`。

## 3. 验收矩阵结果（M01–M22）

| 编号 | 场景 | 结果 | 证据 |
| --- | --- | --- | --- |
| M01 | 有合法 EXIF 的 JPEG | **通过** | V1：`Adobe Lightroom; MiLecFrame`；Make/Model/Artist/Copyright/曝光/GPS 逐项与输入一致；MakerNote 移除；ICC 保留；输入字典快照未变 |
| M02 | 无 EXIF 的 JPEG | **通过** | V1：新建合法 EXIF，`Software=MiLecFrame` 可读回，verify 通过 |
| M03 | PNG 输出 | **通过** | V1：EXIF 与文本均 `MiLecFrame`、两处一致、文本无 NUL |
| M04 | 原 Software 有其他软件名 | **通过** | V1：`Adobe Lightroom` / `Adobe Lightroom; milecframe; MiLecFrame` / 已规范值 → 追加一次且结果正确 |
| M05 | 输出重新导入（含 PNG） | **通过** | V1：JPEG 与 PNG 二次处理前后值完全相同，不重复追加 |
| M06 | 含 MiLecFrame 子串非完整 token | **通过** | V1：`MiLecFramePlugin` → `MiLecFramePlugin; MiLecFrame`；`MILECFRAME` → `MiLecFrame` |
| M07 | 字段类型异常、MakerNote 过大 | **通过** | V1：`XResolution='abc'`（UnboundLocalError）→ `minimal` + 原因码；MakerNote 8KB → `cleaned` + `Exif.MakerNote(37500)`；`Software=12345` → 文件读回 `MiLecFrame` |
| M08 | 超 JPEG 容量 EXIF | **通过** | V1：构建后 65534 字节的 JPEG 走最小兜底（`jpeg_exif_oversize`）；同样的数据走 PNG 完整保留并读回 65534 字节 |
| M09 | 异常编码 / NUL / 巨大文本 | **通过** | V1：非 ASCII、内部 NUL、5000 字符输入均输出有效标识且幂等 |
| M10 | Orientation 转正 | **通过** | V2：80×40 + Orientation=6 → 输出竖向 (40,80)、标记重置为 1；二次处理尺寸稳定 |
| M11 | ICC/作者/版权/GPS 正常样本 | **通过** | V2：完整 `process()` 后相机、曝光、拍摄时间、GPS（4 键）、ICC 全部保留，MakerNote 按既有规则移除 |
| M12 | CLI 单张与批量（两种格式） | **通过** | V4：单张 JPEG/PNG 退出码 0 且标识有效；批量 JPEG/PNG 各 4 成功输出全部含标识（PNG 双字段一致） |
| M13 | GUI 单张与一键导出 | **通过** | V5：生成结果含标识；单张导出与一键导出的副本哈希与源一致、标识可读回、无 `.part` 残留 |
| M14 | HEIC/AVIF 输入转 JPEG/PNG | **通过（合成样本）** | V2：`synthetic.heic`→JPEG/PNG、`synthetic.avif`→PNG 均保留 `Adobe Lightroom` 并追加；PNG 冲突样本以 EXIF 为准；捕获点位于方向/色彩/HDR 转换之前（代码位置 + HEIC 探针验证） |
| M15 | 目标目录不可写、写入失败、读回失败 | **通过** | V6：父路径为文件 → 处理失败且无输出、阻塞文件未破坏；V3 注入4（`image.save` OSError）→ 旧输出哈希不变、无伪成功；注入6（`os.replace` 失败）→ 原文件字节不变、临时文件清除；V6/V3 注入5 → 验证失败即不发布 |
| M16 | 批量混合成功/失败/跳过 | **通过** | V4：5 文件（含 1 损坏）→ 4 成功 / 1 失败 / 0 跳过，`success+fail+skip==total`，失败详情列出 `broken.jpg`，退出码 1；二次运行 0 成功 / 1 失败 / 4 跳过且已有输出字节不变 |
| M17 | 同一 EXIF 对象复用 | **通过** | V1 M17 + V3 注入8：两次保存后输入字典与快照逐 IFD 一致，第二次输出仍含相机字段，两次 Software 相同 |
| M18 | 仅开启本功能前后的对照导出 | **通过** | V6：同一渲染对象、相同编码参数，仅元数据不同 → JPEG/PNG 解码像素逐点一致（76800 px，differ=0）、尺寸与 ICC 一致；元数据差异符合预期（A 无 EXIF / B 有标识） |
| M19 | 终止符与验证反例 | **通过** | V1：TIFF Software 条目恰含一个 NUL（`b'...MiLecFrame\x00'`）、读回容忍尾部 NUL；缺品牌、重复品牌、含控制字符、值不符的**真实坏文件**均被 `verify_output_metadata` 拒绝；`read_output_software` 对无 EXIF 文件拒绝 |
| M20 | 转义与长度边界 | **通过** | M-T1：24 组样例（含 §5.1 全部示例）+ 每组幂等断言 + 4096 输入上限 + 1024 输出字节上下界（恰好 1024 保留、1025+ 降级）+ 字面反斜杠/非 ASCII/控制字符重复处理幂等 |
| M21 | JPEG 实际容量边界 | **通过** | V1：构建后 65533 完整字节可写可读回（与输入构造长度差 12 字节的品牌追加量已计入）；65534 → 最小兜底；65527（纯 TIFF）概念已核对 |
| M22 | PNG 读取是否解码像素 | **通过** | V1：本程序输出 PNG 的 `info`/`getexif` 各 0 次 `load`、`.text` 1 次 `load`（故验证器禁用 `.text`）；性能侧 `verify=0.9ms << save=191.4ms` |

补充证据：JPEG 用 Pillow 与 piexif 双通道交叉读取一致；M20/M05 幂等性在生产路径与内部函数两侧均成立。

## 4. 任务执行记录（M-T0–M-T7）

| 任务 | 结果 | 要点 |
| --- | --- | --- |
| M-T0 基线 | 完成 | piexif 1.1.3 自动补一个 NUL（解析 TIFF count/载荷实证）；JPEG `MAX_BYTES_IN_MARKER=65533` 且 65533 可写 / 65534 拒绝；PNG `info`/`getexif` 不触发 `load` 而 `.text` 触发；分支 `dev` @ `a107994` |
| M-T1 字段规范化 | 完成 | `normalize_software` + `decode_stored_software`；幂等、验证不补值 |
| M-T2 容器输入兼容 | 完成 | 各容器 `info['exif']` 均为带 `Exif\0\0` 头的完整 EXIF 且可被 `piexif.load` 解析；PNG 文本位于 IDAT 后时在"完全无线索"分支复用一次 `load` 补读；HEIC/AVIF 在 `convert_hdr_to_sdr` 之前捕获 |
| M-T3 EXIF 构建 | 完成 | 深拷贝 + 结构校验 + MakerNote 清理 + 有界定向清理（32 轮上限、重复错误即停）+ JPEG 容量预检 + 最小兜底；入参对象不变 |
| M-T4 保存事务 | 完成 | 同目录 `mkstemp`（先关句柄）→ `save` → 只读验证 → `os.replace` → `finally` 清理；失败不重试为"无元数据保存" |
| M-T5 调用链实测 | 完成 | CLI 单张/批量（JPEG/PNG）、GUI 生成/重复生成/失败提示/单张与一键导出 |
| M-T6 回归与性能 | 完成 | 像素/ICC/Orientation 对照通过；阶段耗时与峰值内存记录（§6） |
| M-T7 收尾 | 完成 | 全量 `py_compile`；日志检查；README/CHANGELOG 更新；便携包冒烟（§7）；本报告 |

## 5. 故障注入记录（预期失败，非缺陷）

注入均为临时 `mock.patch`，运行结束自动恢复，生产代码未留下任何测试开关或强制失败分支。

| 注入点 | 预期 | 实际 |
| --- | --- | --- |
| 可定位序列化错误（伪造带标签 ID 的 ValueError） | 只删该标签并重试，Software 保留 | 通过：`Make(271)` 被定向删除，`Adobe Lightroom; MiLecFrame` 保留，无临时残留 |
| 不可定位序列化错误（真实 `XResolution='abc'` + 受控注入） | 直接最小兜底、不猜标签 | 通过：`level=minimal`，原字段丢弃，标识仍在 |
| 最小兜底也失败（序列化器全失效） | `process=False`、不发布 | 通过：返回 False，最终文件不存在，无临时残留 |
| 保存写入失败（OSError） | 不降级为无元数据保存，旧输出不变 | 通过：返回 False，旧输出哈希不变，标识完好 |
| 验证拒绝坏文件 | 缺字段/缺品牌/重复品牌/控制字符/PNG 两处冲突/格式不符 全部拒绝 | 通过（V3 注入5 + V1 M19） |
| 最终替换失败（`os.replace` OSError） | 原文件不变、临时文件清除 | 通过 |
| 临时文件清理失败（`os.unlink` OSError） | 主异常仍可见 + 单独清理告警 | 通过：`[output-metadata] 临时文件清理失败` WARNING 与原始 `No space left` ERROR 并存 |
| EXIF 对象复用 | 输入对象不变、无渐进删字段 | 通过 |
| 批量损坏输入（`broken.jpg`） | 计入失败、退出码 1、无伪成功输出 | 通过 |

## 6. 性能记录（M-T6）

代表性大图 `large.jpg`（4000×3000）完整 `process()` ×3（`tracemalloc` 开启）：

- 总耗时 18.56 s（单张约 6.2 s，含渲染/编码；与元数据功能无关部分占绝大多数）
- Python 峰值内存 699.1 MiB（`tracemalloc` 计数本身会放大分配开销，仅作同口径相对参考）
- 阶段平均耗时：`prepare=1.0 ms`、`save=191.4 ms`、`verify=0.9 ms`、`publish=0.5 ms`（n=3）
- `verify` 相对 `save` 低两个数量级 → 生产验证读取未引入完整像素解码；构建阶段为纯内存操作
- 每张输出仅打印一条 `[output-metadata]` INFO 汇总（格式/级别/原因码/移除标签/阶段耗时），不输出 EXIF 全文

## 7. 日志检查与便携包冒烟

- `debug_log.txt` 当前（1000 行轮转窗口内）无 TRACEBACK；仅 3 条 ERROR，全部来自 M16 故意损坏的 `cli/batch_input/broken.jpg`（预期失败，已列于 §5）。
- 生产日志统一使用 `[output-metadata]` 前缀，仅含格式、`level`、`reasons`、移除标签 ID 与阶段耗时。
- **便携包冒烟（通过）**：
  - `python build_release.py` 构建成功（PyInstaller 6.22.0，onedir → `dist/MiLecFrame/`）；`output_metadata` 已进入分析产物（xref 命中 15 处），`warn-MiLecFrame.txt` 中无项目自身模块缺失（仅 `collections.abc` 等常规无害告警）。
  - dist exe CLI 冒烟：`MiLecFrame.exe -i full.jpg -o dist_single.jpg` → 退出码 0，日志含 `[output-metadata] format=JPEG level=cleaned ... verify=0.3ms`；用 venv 读回 `Adobe Lightroom; MiLecFrame` 并通过生产验证器。
  - dist exe GUI 冒烟：双击等效启动后存活 12 s，日志"PySide6 GUI 启动完成"，exe 同目录 `debug_log.txt` 无 ERROR/TRACEBACK，首启自动生成 `config.json`。
  - `_internal/assets/app_icon.ico` 为真实文件（Attributes=Archive，非目录）、`_internal/src/frame_styles/configs` 为目录。

### 7.1 非 JPEG/PNG 兼容分支（方案 §5.4）

V7 直接调用 `ImageProcessor._save_image(..., "WEBP")`（标准入口不会产生该格式）：

- 保存能力保留（`other.webp` 正常产出）；输出 WARNING：`[output-metadata] 输出格式 WEBP 未启用品牌元数据保证（保证范围为 JPEG/PNG），走既有兼容路径`；
- 不进入新构建/验证器（日志无品牌事务行）；既有"可序列化 EXIF 才写入、坏标签丢弃后仍出图"的旧逻辑保持不变。

## 8. 未验证项（如实列出，不作通过声明）

1. **真实拍摄的 HEIC/AVIF 样本**：仅用 pillow-heif / Pillow 编码器合成样本验证了对象来源字段读取与追加；未使用真实相机 HEIC/AVIF 文件，不能声称真实拍摄兼容性已验收。
2. **人工 GUI 操作**：GUI 验证以 `QT_QPA_PLATFORM=offscreen` 自动驱动真实页面控件完成（生成、重复生成、失败提示、单张/一键导出），未做人工点击式窗口验收。
3. **真实用户照片**：全部夹具为合成数据，未使用用户原图；历史输出文件未扫描、未补标。
4. **多进程/断电持久化**：并发覆盖语义与断电后的持久化事务不在本期范围，未测试。
5. Windows 资源管理器"属性 → 详细信息"是否显示该字段未纳入判定（按方案以文件内实际字段为准）。
