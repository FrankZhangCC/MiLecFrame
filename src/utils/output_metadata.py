# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
输出照片元数据模块：MiLecFrame 软件标识的构建、清理、降级与读回验证

设计边界（对应 docs/plans/PHOTO_METADATA_BRANDING_EXECUTION_PLAN.md）：
  - 本模块只负责"内存中构建元数据"与"只读验证落盘结果"两件事，
    磁盘写入、临时文件发布由 ImageProcessor._save_image() 负责。
  - 构建函数（normalize_software / prepare_output_metadata）可以修复输入，
    验证函数（verify_output_metadata / decode_stored_software）只能证明输出正确，
    绝不补品牌、不去重、不修大小写——两套函数故意不共用修复逻辑，
    否则坏文件会被"修复后比较"假通过。
  - 所有日志带 [output-metadata] 前缀，只记录格式、级别、原因码与标签 ID，
    不输出整份 EXIF 或照片隐私数据。
"""

import copy
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

import piexif
from PIL import Image
from PIL.PngImagePlugin import PngInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量：品牌名、字段与边界
# ---------------------------------------------------------------------------

# 固定产品标识：不附加版本号，不写入 Artist/Copyright/相机型号等其他字段
BRAND_NAME = "MiLecFrame"

# EXIF 0th IFD 的 Software 标签 ID（处理软件字段，语义上正好承载产品名）
SOFTWARE_TAG = piexif.ImageIFD.Software  # 305

# 转义前的输入长度上限：str 按字符数、bytes 按字节数（§5.1 第 3 步）
MAX_INPUT_UNITS = 4096

# 最终软件文本的 ASCII 字节上限，不含序列化器追加的一个存储 NUL（§5.1 第 9 步）
MAX_SOFTWARE_BYTES = 1024

# JPEG APP1 载荷上限：完整 exif_bytes（含 6 字节 "Exif\\0\\0" 头）≤ 65533；
# 不含头的纯 TIFF 部分上限才是 65527。Pillow 12.2.0 实测 65533 可写、65534 拒绝。
# PNG 的 eXIf chunk 不适用该阈值，不能混用。
JPEG_EXIF_MAX_BYTES = 65533

# 序列化失败后的定向清理预算：每轮只删除一个可定位的坏标签（保证递减），
# 达到上限仍未成功则转最小兜底（§5.3 第 5、6 步）
MAX_CLEAN_RETRIES = 32

# piexif 要求的顶层结构键（thumbnail 允许为 None）
_IFD_KEYS = ("0th", "Exif", "GPS", "Interop", "1st")

# 输出支持的品牌保证格式；其他格式走旧兼容路径（由调用方告警）
BRANDED_FORMATS = ("JPEG", "PNG")

# 常见原因码（日志用短码，不嵌入原始 EXIF 全文）
#   software_missing            原软件字段缺失/空白
#   software_invalid_type       原值不是 str/bytes
#   software_escaped            原值含非打印或非 ASCII 字符，已确定性转义
#   software_too_long           超出输入或输出长度上限，降级为品牌名
#   tag_removed                 有标签被移除（MakerNote 或序列化定向清理）
#   jpeg_exif_oversize          JPEG 完整 EXIF 超过 65533 字节，转最小兜底
#   exif_unserializable         EXIF 结构异常或无法序列化，转最小兜底
REASON_MISSING = "software_missing"
REASON_INVALID_TYPE = "software_invalid_type"
REASON_ESCAPED = "software_escaped"
REASON_TOO_LONG = "software_too_long"
REASON_TAG_REMOVED = "tag_removed"
REASON_JPEG_OVERSIZE = "jpeg_exif_oversize"
REASON_UNSERIALIZABLE = "exif_unserializable"


class OutputMetadataError(Exception):
    """元数据构建或读回验证失败时抛出（最终失败，交给调用方按处理失败处理）"""


class _DumpFailed(Exception):
    """内部信号：piexif.dump 无法定位坏标签 / 清理无进展 / 预算耗尽，转最小兜底"""


@dataclass(frozen=True)
class SoftwareValue:
    """规范化后的软件字段文本及其原因码

    Attributes:
        text: ASCII 安全文本，恰含一个独立的 MiLecFrame token
        reasons: 短原因码列表（正常路径可能为空）
    """
    text: str
    reasons: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PreparedMetadata:
    """构建完成的输出元数据（视为只读，验证阶段不得重新推导软件值）

    Attributes:
        exif_bytes: 可直接交给 Pillow 的完整 EXIF 字节（含 "Exif\\0\\0" 头）
        software_text: 最终写入 EXIF 与 PNG 文本的统一软件值（无 NUL）
        pnginfo: PNG 文本块（仅 PNG 输出；值与 software_text 一致），JPEG 为 None
        level: 降级级别 'preserved' / 'cleaned' / 'minimal'
        reasons: 构建阶段收集的短原因码
        removed_tags: 被移除标签的 "IFD.名称(ID)" 或 "IFD.ID" 列表
        build_ms: 构建耗时（毫秒，日志用）
    """
    exif_bytes: bytes
    software_text: str
    pnginfo: Optional[PngInfo]
    level: str
    reasons: Tuple[str, ...] = ()
    removed_tags: Tuple[str, ...] = ()
    build_ms: float = 0.0


# ---------------------------------------------------------------------------
# 只读解码：验证阶段专用（严格、不修复）
# ---------------------------------------------------------------------------

def decode_stored_software(value: Union[str, bytes]) -> str:
    """严格 ASCII 解码从文件读回的 Software 字段（只读，禁止补值）

    只做两件事：严格 ASCII 解码、去掉存储终止 NUL。不做去重、不补品牌、
    不做反斜杠转义或大小写修复——这些属于构建阶段的能力，混入验证会让
    坏文件假通过。

    Args:
        value: Pillow 读回的 str 或 bytes

    Returns:
        去掉尾部 NUL 后的文本

    Raises:
        OutputMetadataError: 类型非法、非 ASCII 编码、含内部 NUL 或控制字符
    """
    if isinstance(value, bytes):
        try:
            text = value.decode("ascii")
        except UnicodeDecodeError as e:
            raise OutputMetadataError(f"Software 字段非 ASCII 字节: {e}") from e
    elif isinstance(value, str):
        if not value.isascii():
            raise OutputMetadataError("Software 字段含非 ASCII 字符")
        text = value
    else:
        raise OutputMetadataError(
            f"Software 字段类型非法: {type(value).__name__}"
        )

    # 只允许去掉尾部的存储终止符；内部 NUL/控制字符一律判失败
    stripped = text.rstrip("\x00")
    for ch in stripped:
        cp = ord(ch)
        if cp < 0x20 or cp == 0x7F:
            raise OutputMetadataError("Software 字段含内部控制字符")
    return stripped


def count_brand_tokens(text: str) -> int:
    """按分号统计完整品牌 token 的数量（不区分大小写，不做子串匹配）

    Args:
        text: 已解码的软件文本

    Returns:
        与 MiLecFrame 完全相等的 token 个数
    """
    if not isinstance(text, str):
        return 0
    target = BRAND_NAME.casefold()
    return sum(1 for tok in text.split(";") if tok.strip().casefold() == target)


# ---------------------------------------------------------------------------
# 构建阶段：Software 规范化（§5.1 固定顺序）
# ---------------------------------------------------------------------------

def _escape_to_ascii(value: Union[str, bytes]) -> Tuple[str, bool]:
    """把原始软件值逐单元映射为可打印 ASCII（§5.1 第 4、5 步）

    规则：
      - 保留 0x20–0x7E（含原有反斜杠），原有反斜杠既不加倍也不反解码，
        从而保证"已转义文本再次输入保持不变"的幂等性；
      - bytes 的其他值输出 \\xNN（小写十六进制）；
      - str 的非打印/非 ASCII 码点按宽度输出 \\xNN / \\uNNNN / \\UNNNNNNNN。

    Args:
        value: 已通过类型检查的 str 或 bytes

    Returns:
        (转义后的文本, 是否发生过转义)
    """
    parts: List[str] = []
    changed = False

    if isinstance(value, bytes):
        # 先去除尾部存储 NUL，中间的 NUL 会被转义成可见序列
        for byte in value.rstrip(b"\x00"):
            if 0x20 <= byte <= 0x7E:
                parts.append(chr(byte))
            else:
                parts.append(f"\\x{byte:02x}")
                changed = True
    else:
        for ch in value.rstrip("\x00"):
            cp = ord(ch)
            if 0x20 <= cp <= 0x7E:
                parts.append(ch)
            elif cp <= 0xFF:
                parts.append(f"\\x{cp:02x}")
                changed = True
            elif cp <= 0xFFFF:
                parts.append(f"\\u{cp:04x}")
                changed = True
            else:
                parts.append(f"\\U{cp:08x}")
                changed = True

    return "".join(parts), changed


def normalize_software(value: Any) -> SoftwareValue:
    """把任意来源的软件字段规范化为"含唯一 MiLecFrame 标识"的 ASCII 文本

    固定顺序（§5.1，顺序不可调整，否则幂等性与示例表会失配）：
      1. None / 空白 → 直接生成品牌名；
      2. 仅接受 str/bytes，其他类型记 software_invalid_type 并降级；
      3. 转义前长度上限 4096（str 按字符、bytes 按字节）；
      4. 去尾部 NUL 后逐单元转义为可打印 ASCII；
      5. 原有反斜杠保持不变（保证幂等）；
      6. 只按半角分号拆分并去空 token；
      7. 不区分大小写收敛 MiLecFrame token 为规范大小写的一份，保留首个位置；
      8. 其余 token 保持次序，用 "; " 连接；无品牌则末尾追加；
      9. 最终 ASCII 字节数 > 1024 时降级为品牌名。

    幂等性保证：normalize(normalize(x).text).text == normalize(x).text

    Args:
        value: None、str、bytes 或其他异常类型

    Returns:
        SoftwareValue：text 为 ASCII 安全文本且恰含一个品牌 token
    """
    # 1. 缺失 / 空白
    if value is None:
        return SoftwareValue(BRAND_NAME, (REASON_MISSING,))
    if not isinstance(value, (str, bytes)):
        # 2. 类型非法：绝不把字典等内容整体 str() 后写入
        return SoftwareValue(BRAND_NAME, (REASON_INVALID_TYPE,))
    if isinstance(value, str):
        if not value.strip():
            return SoftwareValue(BRAND_NAME, (REASON_MISSING,))
    else:
        if not value.strip(b" \t\n\r\x0b\f\x00"):
            return SoftwareValue(BRAND_NAME, (REASON_MISSING,))

    reasons: List[str] = []

    # 3. 转义前输入长度限制（不是存储字节限制）
    if len(value) > MAX_INPUT_UNITS:
        return SoftwareValue(BRAND_NAME, (REASON_TOO_LONG,))

    # 4/5. 确定性 ASCII 转义（不加倍反斜杠 → 幂等）
    escaped, changed = _escape_to_ascii(value)
    if changed:
        reasons.append(REASON_ESCAPED)

    # 6. 只按半角分号拆分；其他标点视作软件名的一部分
    tokens = [tok.strip() for tok in escaped.split(";")]
    tokens = [tok for tok in tokens if tok]

    # 7/8. 品牌 token 收敛为规范大小写的一份，保留首个位置；其余保持次序
    merged: List[str] = []
    brand_seen = False
    for tok in tokens:
        if tok.casefold() == BRAND_NAME.casefold():
            if not brand_seen:
                merged.append(BRAND_NAME)
                brand_seen = True
            # 重复出现的品牌 token 直接丢弃（已知重复不无限合并）
        else:
            merged.append(tok)
    if not brand_seen:
        merged.append(BRAND_NAME)

    text = "; ".join(merged)

    # 9. 输出长度上限（按 ASCII 字节计，不含序列化器追加的存储 NUL）
    try:
        encoded = text.encode("ascii")
    except UnicodeEncodeError:
        # 理论不可达：上游已保证全为可打印 ASCII；防御性降级
        return SoftwareValue(BRAND_NAME, tuple(reasons + ["software_not_ascii"]))
    if len(encoded) > MAX_SOFTWARE_BYTES:
        return SoftwareValue(BRAND_NAME, tuple(reasons + [REASON_TOO_LONG]))

    return SoftwareValue(text, tuple(reasons))


# ---------------------------------------------------------------------------
# EXIF 结构准备、清理与序列化
# ---------------------------------------------------------------------------

def _empty_exif_dict() -> Dict[str, Any]:
    """构造 piexif 可序列化的空 IFD 结构（不发明任何拍摄时间/设备/GPS/作者）"""
    return {
        "0th": {},
        "Exif": {},
        "GPS": {},
        "Interop": {},
        "1st": {},
        "thumbnail": None,
    }


def _sanitize_structure(raw_exif: Any, reasons: List[str],
                        removed: List[str]) -> Dict[str, Any]:
    """深拷贝原始 EXIF 并校验顶层结构符合 piexif 输入要求（§5.3 第 1、2 步）

    Args:
        raw_exif: piexif 字典或 None
        reasons: 原地追加失败原因码
        removed: 原地追加被移除的顶层键（保证 level/reasons 语义一致）

    Returns:
        可安全修改的副本；输入为 None 或结构异常时返回空结构
    """
    if raw_exif is None:
        return _empty_exif_dict()

    try:
        copied = copy.deepcopy(raw_exif)
    except Exception as e:
        logger.debug("[output-metadata] EXIF 深拷贝失败，转最小结构: %s", e)
        reasons.append(REASON_UNSERIALIZABLE)
        return _empty_exif_dict()

    if not isinstance(copied, dict):
        reasons.append(REASON_UNSERIALIZABLE)
        return _empty_exif_dict()

    clean: Dict[str, Any] = {}
    for key in _IFD_KEYS:
        value = copied.get(key)
        if value is None:
            clean[key] = {}
        elif isinstance(value, dict):
            clean[key] = value
        else:
            # IFD 不是字典（类型异常）：替换为空结构，避免 dump 阶段崩溃
            clean[key] = {}
            reasons.append(REASON_UNSERIALIZABLE)

    thumbnail = copied.get("thumbnail")
    if thumbnail is None or isinstance(thumbnail, bytes):
        clean["thumbnail"] = thumbnail
    else:
        clean["thumbnail"] = None
        reasons.append(REASON_UNSERIALIZABLE)

    # 未知顶层键：piexif 只读上述键，直接丢弃并记录（不静默吞掉）。
    # 记入 removed 而非只记原因码，使 level=cleaned 与 removed 语义一致
    unknown = [k for k in copied.keys() if k not in _IFD_KEYS and k != "thumbnail"]
    if unknown:
        for k in unknown:
            removed.append(f"top-level.{k}")
            reasons.append(REASON_TAG_REMOVED)
            logger.debug("[output-metadata] 丢弃未知 EXIF 顶层键: %r", k)

    return clean


def _tag_label(ifd_name: str, tag_id: int) -> str:
    """生成只含标签名/ID 的日志标签（不打印标签内容）

    Args:
        ifd_name: IFD 名称（0th/Exif/GPS/Interop/1st）
        tag_id: 标签数值 ID

    Returns:
        形如 "Exif.MakerNote(37500)" 或 "0th.305" 的标签
    """
    modules = {
        "0th": piexif.ImageIFD,
        "Exif": piexif.ExifIFD,
        "GPS": piexif.GPSIFD,
        "Interop": piexif.InteropIFD,
        "1st": piexif.ImageIFD,
    }
    module = modules.get(ifd_name)
    if module is not None:
        for attr in dir(module):
            if attr.startswith("_"):
                continue
            try:
                candidate = getattr(module, attr)
            except Exception:  # pragma: no cover - piexif 常量模块不会抛
                continue
            if isinstance(candidate, int) and not isinstance(candidate, bool) \
                    and candidate == tag_id:
                return f"{ifd_name}.{attr}({tag_id})"
    return f"{ifd_name}.{tag_id}"


def _remove_makernote(exif_dict: Dict[str, Any], removed: List[str],
                      reasons: List[str]) -> None:
    """在副本中沿用既有的 MakerNote 移除行为（厂商私有数据，易超限且不可移植）

    Args:
        exif_dict: 待修改的 EXIF 副本
        removed: 原地追加被移除标签
        reasons: 原地追加 tag_removed
    """
    exif_ifd = exif_dict.get("Exif")
    if isinstance(exif_ifd, dict) and piexif.ExifIFD.MakerNote in exif_ifd:
        del exif_ifd[piexif.ExifIFD.MakerNote]
        removed.append(_tag_label("Exif", piexif.ExifIFD.MakerNote))
        reasons.append(REASON_TAG_REMOVED)


def _serialize_with_cleanup(exif_dict: Dict[str, Any],
                            removed: List[str],
                            reasons: List[str]) -> bytes:
    """序列化 EXIF，遇到可定位的坏标签定向删除后有界重试（§5.3 第 5、6 步）

    异常边界：只捕获普通 Exception（含 piexif 实际存在的 UnboundLocalError），
    不捕 MemoryError、KeyboardInterrupt/SystemExit 等；磁盘 IO 不在本函数内。

    Args:
        exif_dict: 已写入 Software 的 EXIF 字典（本函数会就地删除坏标签）
        removed: 原地追加被删除的标签
        reasons: 原地追加原因码

    Returns:
        piexif.dump 结果字节

    Raises:
        _DumpFailed: 无法定位坏标签、重复同一问题或达到重试预算
    """
    seen: set = set()

    for _attempt in range(MAX_CLEAN_RETRIES + 1):
        try:
            return piexif.dump(exif_dict)
        except MemoryError:
            # 内存耗尽不是"坏元数据"，必须上抛
            raise
        except Exception as e:  # noqa: BLE001 - 有意覆盖 UnboundLocalError 等
            msg = str(e)
            # piexif 的定向错误形如:
            #   "dump" got wrong type of exif value. 41729 in Exif IFD. Got as ...
            match = re.search(r"(\d+) in (\w+) IFD", msg)
            if not match:
                reasons.append(REASON_UNSERIALIZABLE)
                raise _DumpFailed(msg) from e

            tag_id = int(match.group(1))
            ifd_name = match.group(2)
            key = (ifd_name, tag_id, msg)
            if key in seen:
                # 同一问题重复出现：删除并未产生进展，停止猜测
                reasons.append(REASON_UNSERIALIZABLE)
                raise _DumpFailed(f"重复序列化错误: {msg}") from e

            target = exif_dict.get(ifd_name)
            if not (isinstance(target, dict) and tag_id in target):
                # 报错无法可靠定位到现存标签：不猜，转最小兜底
                reasons.append(REASON_UNSERIALIZABLE)
                raise _DumpFailed(msg) from e

            seen.add(key)
            del target[tag_id]
            removed.append(_tag_label(ifd_name, tag_id))
            reasons.append(REASON_TAG_REMOVED)
            logger.debug("[output-metadata] 序列化失败，已定向移除标签 %s: %s",
                         _tag_label(ifd_name, tag_id), msg)

    # 重试预算耗尽（每轮都删掉一个标签，理论上罕见）
    reasons.append(REASON_UNSERIALIZABLE)
    raise _DumpFailed("EXIF 序列化清理达到重试上限")


def _resolve_software(exif_dict: Dict[str, Any],
                      software_hint: Any,
                      reasons: List[str]) -> str:
    """按优先级选择原软件字段并规范化（§2.3 优先级）

    优先级（"可用"= 可解析且非空）：
      1. EXIF 0th Software 中**可用**的值（含从 PNG/HEIC/AVIF 源字节补读到的
         原始 EXIF）；
      2. EXIF 值缺失/空值/非法类型时，回落 software_hint（源图像 getexif()
         单字段 / PNG 文本 Software）；
      3. 都不可用 → 直接生成品牌名。

    注意：这里把原始值交给 normalize_software（宽容转义，保留可表示部分），
    而不是 decode_stored_software（严格验证，会直接拒绝），两者用途不同。
    EXIF 值不可用的事实会如实记入 reasons，不掩盖"原值已丢失"。

    Args:
        exif_dict: EXIF 副本
        software_hint: 源图像软件字段补充值
        reasons: 原地追加原因码

    Returns:
        规范化后的软件文本（必含品牌标识）
    """
    zeroth = exif_dict.get("0th")
    raw_value = zeroth.get(SOFTWARE_TAG) if isinstance(zeroth, dict) else None
    if raw_value is not None:
        value = normalize_software(raw_value)
        # 只有"可解析且非空"的 EXIF 值才作为首选来源；missing（空值）与
        # invalid_type（非法类型）视为不可用，继续尝试补充来源（§2.3 优先级 1）
        unusable = set(value.reasons) & {REASON_MISSING, REASON_INVALID_TYPE}
        reasons.extend(value.reasons)
        if not unusable:
            return value.text

    if software_hint is not None:
        value = normalize_software(software_hint)
        reasons.extend(value.reasons)
        return value.text

    # EXIF 不可用且没有补充来源：若上面尚未记录过不可用原因，补记缺失
    if not (set(reasons) & {REASON_MISSING, REASON_INVALID_TYPE}):
        reasons.append(REASON_MISSING)
    return BRAND_NAME


def _build_minimal(software_text: str, fmt: str,
                   reasons: List[str], removed: List[str],
                   started: float) -> PreparedMetadata:
    """最小标识兜底：重建仅含 Software 的合法 EXIF（§2.5 第 3 步）

    Args:
        software_text: 规范化后的软件文本
        fmt: 'JPEG' / 'PNG'
        reasons: 已收集的原因码（本函数可能追加）
        removed: 已移除标签列表
        started: 构建起始时间戳（perf_counter，用于记录耗时）

    Returns:
        level='minimal' 的 PreparedMetadata

    Raises:
        OutputMetadataError: 最小结构序列化仍失败（保留异常链）
    """
    def _dump(text: str) -> bytes:
        minimal = _empty_exif_dict()
        minimal["0th"][SOFTWARE_TAG] = text.encode("ascii")
        return piexif.dump(minimal)

    try:
        exif_bytes = _dump(software_text)
    except Exception as first_error:  # noqa: BLE001 - 收缩品牌名后再试一次
        try:
            exif_bytes = _dump(BRAND_NAME)
            software_text = BRAND_NAME
            logger.debug("[output-metadata] 最小兜底收缩为品牌名后序列化成功")
        except Exception as second_error:  # noqa: BLE001
            raise OutputMetadataError(
                "最小标识 EXIF 序列化失败"
            ) from second_error
        # 记录首次失败原因，避免把丢失包装成完全保留
        logger.debug("[output-metadata] 最小兜底初次序列化失败: %s", first_error)

    if fmt == "JPEG" and len(exif_bytes) > JPEG_EXIF_MAX_BYTES:
        raise OutputMetadataError("最小标识 EXIF 仍超出 JPEG 容量")

    pnginfo = _build_pnginfo(fmt, software_text)
    return PreparedMetadata(
        exif_bytes=exif_bytes,
        software_text=software_text,
        pnginfo=pnginfo,
        level="minimal",
        reasons=tuple(dict.fromkeys(reasons)),  # 去重且保持顺序
        removed_tags=tuple(dict.fromkeys(removed)),
        build_ms=(time.perf_counter() - started) * 1000.0,
    )


def _build_pnginfo(fmt: str, software_text: str) -> Optional[PngInfo]:
    """构建 PNG 文本块（只写本功能需要的 Software 字段）

    PNG 文本不是 EXIF ASCII 存储字段，绝不追加终止 NUL，
    也不自动复制源图的其他文本，避免扩大隐私与格式行为。

    Args:
        fmt: 输出格式
        software_text: 最终软件文本

    Returns:
        PNG 输出返回 PngInfo；其他格式返回 None
    """
    if fmt != "PNG":
        return None
    pnginfo = PngInfo()
    pnginfo.add_text("Software", software_text)
    return pnginfo


def prepare_output_metadata(raw_exif: Optional[Dict],
                            output_format: str,
                            software_hint: Any = None) -> PreparedMetadata:
    """在内存中构建带 MiLecFrame 标识的输出元数据（不写磁盘、不改入参）

    Args:
        raw_exif: piexif 字典或 None（调用方负责来源与 Orientation 修正）
        output_format: 实际输出编码，'JPEG' 或 'PNG'
        software_hint: 源图像软件字段补充值（仅当 EXIF Software 不可用时参与）

    Returns:
        PreparedMetadata（只读契约）

    Raises:
        OutputMetadataError: 输出格式不受支持，或最小兜底仍无法序列化
    """
    started = time.perf_counter()
    fmt = (output_format or "").upper()
    if fmt not in BRANDED_FORMATS:
        # §5.4：其他格式由调用方走旧兼容路径并告警，不进本构建器
        raise OutputMetadataError(f"品牌元数据仅支持 JPEG/PNG，收到: {output_format!r}")

    reasons: List[str] = []
    removed: List[str] = []

    # 1/2. 深拷贝 + 结构校验（绝不修改调用方传入的对象）
    exif_dict = _sanitize_structure(raw_exif, reasons, removed)

    # 3. 取原软件字段并规范化（含品牌去重）
    software_text = _resolve_software(exif_dict, software_hint, reasons)

    # 4. 在副本上沿用既有清理逻辑（MakerNote）
    _remove_makernote(exif_dict, removed, reasons)

    # 写入规范化 Software：只 encode、不手动补 NUL，
    # piexif 1.1.3 会在 TIFF ASCII 存储值末尾自动补一个终止符
    exif_dict["0th"][SOFTWARE_TAG] = software_text.encode("ascii")

    # 5. 序列化（有界定向清理；序列化阶段可能继续追加 removed）
    try:
        exif_bytes = _serialize_with_cleanup(exif_dict, removed, reasons)
    except _DumpFailed as e:
        logger.debug("[output-metadata] 完整 EXIF 序列化失败，转最小兜底: %s", e)
        return _build_minimal(software_text, fmt, reasons, removed, started)

    # 5a. JPEG 容量预检（PNG 不套用 JPEG 阈值）
    if fmt == "JPEG" and len(exif_bytes) > JPEG_EXIF_MAX_BYTES:
        logger.debug(
            "[output-metadata] JPEG EXIF 超限 (%d > %d)，转最小兜底",
            len(exif_bytes), JPEG_EXIF_MAX_BYTES,
        )
        reasons.append(REASON_JPEG_OVERSIZE)
        return _build_minimal(software_text, fmt, reasons, removed, started)

    # 6. PNG 同时构建文本 Software，值与 EXIF 软件值保持一致
    pnginfo = _build_pnginfo(fmt, software_text)

    # 有任何标签被移除即视为 cleaned，完全原样保留才是 preserved
    level = "cleaned" if removed else "preserved"
    return PreparedMetadata(
        exif_bytes=exif_bytes,
        software_text=software_text,
        pnginfo=pnginfo,
        level=level,
        reasons=tuple(dict.fromkeys(reasons)),
        removed_tags=tuple(dict.fromkeys(removed)),
        build_ms=(time.perf_counter() - started) * 1000.0,
    )


# ---------------------------------------------------------------------------
# 输出验证（只读、严格比较；禁止复用 normalize_software）
# ---------------------------------------------------------------------------

def _fail(message: str) -> None:
    """统一抛出验证失败（字段缺失/值不符/编码不符都必须失败，不能补默认值）"""
    raise OutputMetadataError(message)


def _verify_png_text(text_value: Any, expected: str) -> str:
    """校验 PNG 文本 Software（无 NUL、纯 ASCII、精确等于期望值）"""
    if text_value is None:
        _fail("输出缺少 PNG 文本 Software 字段")
    if not isinstance(text_value, str):
        _fail(f"PNG 文本 Software 类型非法: {type(text_value).__name__}")
    if not text_value.isascii():
        _fail("PNG 文本 Software 含非 ASCII 字符")
    if "\x00" in text_value:
        _fail("PNG 文本 Software 含 NUL（PNG 文本不应有终止符）")
    for ch in text_value:
        cp = ord(ch)
        if cp < 0x20 or cp == 0x7F:
            _fail("PNG 文本 Software 含控制字符")
    if text_value != expected:
        _fail("PNG 文本 Software 与期望值不一致")
    return text_value


def read_output_software(path: str) -> str:
    """只读读取文件中的 EXIF Software（用于导出副本与源文件的同源比较）

    与 verify_output_metadata 一样是严格只读：不补值、不修复，缺失即抛错。

    Args:
        path: 已存在的图像文件路径

    Returns:
        严格解码并去掉存储 NUL 后的软件文本

    Raises:
        OutputMetadataError: 字段缺失、类型非法或编码不符
    """
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            raw_value = exif.get(SOFTWARE_TAG) if exif is not None else None
    except OutputMetadataError:
        raise
    except Exception as e:  # noqa: BLE001
        raise OutputMetadataError(f"读取 Software 失败: {e}") from e
    if raw_value is None:
        raise OutputMetadataError("文件缺少 EXIF Software 字段")
    return decode_stored_software(raw_value)


def verify_output_metadata(path: str, expected_format: str,
                           expected_software: str) -> None:
    """读回临时输出文件，严格验证标识写入结果（验证通过才允许发布）

    只读策略：Pillow 的 getexif() 与 info[] 读取本程序写在标准位置的字段，
    不触发像素解码；禁止访问 .text 属性（Pillow 12 中会触发 load）。

    Args:
        path: 本次临时输出路径
        expected_format: 期望的实际编码，'JPEG' / 'PNG'
        expected_software: 构建阶段的 expected_software（精确比较基准）

    Raises:
        OutputMetadataError: 格式不符、字段缺失、值不符或编码不符
    """
    fmt = (expected_format or "").upper()
    if fmt not in BRANDED_FORMATS:
        raise OutputMetadataError(f"验证仅支持 JPEG/PNG，收到: {expected_format!r}")

    # 期望值本身必须是干净的规范文本，否则比较基准不可信
    if not isinstance(expected_software, str) or not expected_software:
        raise OutputMetadataError("期望软件值为空或类型非法")
    if not expected_software.isascii() or "\x00" in expected_software:
        raise OutputMetadataError("期望软件值含非 ASCII 或 NUL")

    try:
        with Image.open(path) as img:
            actual_format = (img.format or "").upper()
            if actual_format != fmt:
                _fail(f"输出实际格式为 {actual_format}，期望 {fmt}")

            exif = img.getexif()
            raw_value = exif.get(SOFTWARE_TAG) if exif is not None else None
            if raw_value is None:
                _fail("输出缺少 EXIF Software 字段")

            # 严格解码 + 去存储 NUL，然后精确比较（不修复、不去重）
            decoded = decode_stored_software(raw_value)
            if decoded != expected_software:
                _fail("EXIF Software 与期望值不一致")
            if count_brand_tokens(decoded) != 1:
                _fail("EXIF Software 中品牌标识不是恰好一个")

            if fmt == "PNG":
                # 用 info 读取，禁止 .text（会触发完整图像加载）
                text_value = img.info.get("Software")
                png_text = _verify_png_text(text_value, expected_software)
                if png_text != decoded:
                    _fail("PNG 文本与 EXIF Software 不一致")
    except OutputMetadataError:
        raise
    except Exception as e:  # noqa: BLE001 - 读取失败同样判定为验证失败
        raise OutputMetadataError(f"读回验证失败: {e}") from e
