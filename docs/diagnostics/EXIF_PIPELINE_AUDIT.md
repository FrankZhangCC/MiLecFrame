# EXIF 处理流审查报告

> 日期：2026-09-26
> 范围：输入读取（EXIF 提取/容器补读）→ 方向修正 → 渲染数据 → 输出构建/保存/验证 → GUI 导出
> 基线：实施 [PHOTO_METADATA_BRANDING_EXECUTION_PLAN.md](../plans/PHOTO_METADATA_BRANDING_EXECUTION_PLAN.md) 之后的 dev 工作区
> 方法：代码走查 + 定向实测（`audit_exif.py` / `audit_exif2.py`，内存与临时文件，不改生产代码）

## 1. 数据流全景

```
输入文件 ─┬─ extract_exif_data(path|bytes) ─→ RenderMetadata.exif_data ─→ RenderContext ─→ 相框文字
          │        （显示：相机/镜头/曝光/GPS；附带 _record_device_info 写 CSV）
          ├─ extract_raw_exif(path) ─┐
          ├─ extract_raw_exif_from_bytes(info['exif']) ─┴→ raw_exif ─┬→ Orientation 重置=1
          ├─ extract_software_hint(image) ─→ software_hint            └→ prepare_output_metadata
          └─ _capture_source_metadata（转正/转换前捕获）                    ├ 深拷贝/清理/分级降级
                                                                            └ PreparedMetadata
_save_image ─ 同目录临时写入 → verify_output_metadata → os.replace 发布
GUI 导出 ── shutil.copy2(.part) → 哈希一致 + read_output_software + verify_output_metadata → 发布
```

## 2. 发现的问题

### P1 — 功能缺陷（违背本期"保留原软件名/展示 EXIF"需求）

**P1-1 EXIF `Software` 为空值或非法类型时，不回落 `software_hint`**

- 位置：`src/utils/output_metadata.py::_resolve_software`
- 现象：`raw_value is not None` 即锁定 EXIF 值，即便它规范化后是 `software_missing` / `software_invalid_type`。
- 实测：
  - `EXIF Software=b'' + PNG 文本='Adobe Lightroom'` → 输出 `MiLecFrame`（期望 `Adobe Lightroom; MiLecFrame`）
  - `EXIF Software=12345 + hint='Adobe Lightroom'` → 输出 `MiLecFrame`
- 违反方案 §2.3 优先级 1："**可解析且非空**的 EXIF Software"。

**P1-2 GUI/批量的 EXIF 提取对 PNG/HEIC/AVIF 完全失效**

- 位置：`ExifHelper.extract_exif_data(完整文件字节)` / `(文件路径)`，经 `piexif.load` 不支持该容器即返回 None
- 实测：GUI 视角（`item.file_bytes`）→ `None`；process 视角（`info['exif']`）→ `{camera_make: 'Canon', camera_model: 'EOS R5', iso: '200'}`
- 后果：GUI EXIF 面板空白、导出/批量的 **logo 自动匹配失效、GPS 替换失效**，而输出 EXIF 中这些数据都在；预览面板与渲染结果（相框文字）不一致。

### P2 — 一致性/边界

**P2-3 PNG 文本关键字大小写敏感**：只认精确 `Software`；写入 `software` / `SOFTWARE` 的源文件读不到原软件名（实测三种键的结果）。

**P2-4 方向转正后 EXIF 缩略图仍是旧方向**（既有行为）：主图转正 (40,80) 竖向、缩略图仍 (20,10) 横向，且 `Orientation` 已重置为 1 → 查看器主图正确、缩略图方向错误。

**P2-5 `level` 与 `reasons` 不一致**：未知顶层键被丢弃时 reasons 记 `tag_removed`、level 却是 `preserved`（实测 `level=preserved reasons=('tag_removed',) removed=()`），日志自相矛盾。

### P3 — 性能/诊断（本次不修，记录在案）

| # | 问题 |
| --- | --- |
| P3-6 | 同一输入被 `piexif.load` 最多 3 次（process 的 exif_data + raw_exif，加 batch 逐张提取），可合并为一次解析派生两份数据 |
| P3-7 | `_check_image_format()` 的 `Image.open(path).format` 未显式 close（依赖 GC），大批量时句柄回收滞后 |
| P3-8 | 损坏 thumbnail 导致最小兜底时原因码只有 `exif_unserializable`，看不出根因是 thumbnail |
| P3-9 | `extract_software_hint` 的空值判断 `value != ""` 对 `b''` 不生效（bytes/str 不等）；当前 Pillow 返回 str 规避，边界不严谨 |

### 审查确认无问题

- 坏 EXIF 时 `path` 与 `info['exif']` 两条路解析结果一致（同一字节），不存在"显示有/输出无"的不一致。
- 损坏 thumbnail → 无法定位 → 不猜标签 → 最小兜底，标识保留（符合方案 §5.3.6）。
- `level` 在序列化清理后统一计算；M17 输入对象不被修改；验证器严格不修复；非 JPEG/PNG 分支保留能力并告警。
- 批量计数、GUI 失败状态、导出事务语义此前已通过 M12–M16 验收。

## 3. 修复记录（2026-09-26）

用户选择修复 P1 + P2（P3 记录不修）：

| 问题 | 修复 |
| --- | --- |
| P1-1 | `_resolve_software()` 仅把"可解析且非空"的 EXIF 值作为首选来源；missing/invalid_type 时回落 `software_hint`；原因码如实记录"EXIF 值不可用" |
| P1-2 | `extract_exif_data()` / `extract_raw_exif()` 增加 Pillow 容器回落：piexif 不支持的来源改用 Pillow 读取已解析的 `info['exif']` 再解析（只读头部，不解码像素），GUI/批量自动受益 |
| P2-3 | `extract_software_hint()` 对 PNG 文本按不区分大小写匹配 `software` 键 |
| P2-4 | 方向转正时丢弃旧方向的 EXIF 缩略图（`thumbnail=None`）并记日志，与 Orientation 重置保持一致 |
| P2-5 | 未知顶层键丢弃改记入 `removed_tags`，`level` 随之为 `cleaned`，与原因码一致 |

修复后重跑 M-T1 / V1 / V2 / V5 无回归，并新增定向用例验证上述五项（见 §3.1）。

### 3.1 修复验证（实测结果）

新增定向用例 V8（23/23 通过）：

- P1-1：`EXIF=b'' + hint='Adobe Lightroom'` → `Adobe Lightroom; MiLecFrame`（原因码 `software_missing` 如实记录）；`EXIF=12345 + hint` → 同（`software_invalid_type`）；`EXIF=b' ' + hint=None` → `MiLecFrame`；EXIF 有效值仍优先（冲突样本不回归）。
- P1-2：PNG 文件路径 / 完整文件字节 / HEIC 路径经 `extract_exif_data` 均取回相机、曝光、拍摄时间与 GPS；`extract_raw_exif` 对容器同样回落；**GUI 视角与输出侧字段完全一致**（9 个字段同名同值）。
- P2-3：`Software` / `software` / `SOFTWARE` 三种写法均可读取。
- P2-4：转正输出 `thumbnail=None` 且 `Orientation` 保持 1；未转正输入（Orientation=1）仍保留缩略图、不改 Orientation（不扩大改动）。
- P2-5：未知键丢弃 → `level=cleaned`、`removed=('top-level.UnknownKey',)`；干净输入仍 `preserved`。

回归（全部保持通过）：M-T1 24 组样例 + 边界 + 严格解码；V1 71/71（构建/保存矩阵）；V2 24/24（完整 `process()`，M10/M11/M14）；V4 18/18（CLI 单张/批量）；V5 27/27（GUI 语义）。全量 `python -m py_compile` 通过。

**P3 未修**（P3-6 重复解析、P3-7 句柄、P3-8 原因码粒度、P3-9 hint 空值边界），如需处理另起任务。
