# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
一级/二级渲染模糊缓存

RenderBlurCache（一级）的生命周期只覆盖一次 render_frame()：
帧内源图唯一，缓存键简化为 (source_kind, radius)；职责是
  - 同一帧内的背景和多个矩形共享原图卷积（懒计算，按需派生）；
  - 多个同半径矩形只计算一次昂贵卷积；
  - 缓存由 PreparedBlur 派生的原图尺寸/画布尺寸结果；
  - 渲染结束后随帧释放，避免长期占用大图内存。

PreparedBlurLRU（二级）跨多次 render_frame() 保存 source_kind='photo'
的 PreparedBlur（工作分辨率 float32 卷积结果），按 nbytes 预算 LRU 淘汰；
由交互页面（样式编辑器/图片处理页）持有，不由算法模块全局持有。
批量处理不接二级缓存，避免连续处理不同照片产生无效内存驻留。

缓存状态不放入纯算法模块，也不使用无容量限制的进程级全局缓存。
"""
import hashlib
import logging
from collections import OrderedDict
from typing import Optional, Tuple

from PIL import Image

from src.utils.gaussian_blur import (
    PreparedBlur,
    prepare_gaussian_blur,
    render_prepared_blur,
)

logger = logging.getLogger(__name__)

# source_kind 常量：'photo' = 原图卷积（矩形 ⊆ original_bounds 时按照片
# 局部坐标取样）；'base_scene' 为精确型（方案 B）预留接口位，本期不实现
SOURCE_PHOTO = 'photo'
SOURCE_BASE_SCENE = 'base_scene'

# 预处理版本号：覆盖 EXIF 转正 / ICC 转换 / 超尺寸缩放规则。
# 任一预处理逻辑变更时必须递增，否则跨版本缓存会错误复用旧预处理结果
PREPROCESSING_VERSION = "1"

# 高斯算法版本号：卷积/饱和度/缩放实现变更时递增
GAUSSIAN_ALGORITHM_VERSION = "1"

# 二级缓存键位置下标（可读性辅助）
_L2_IDX_SOURCE_KEY = 0
_L2_IDX_SIZE = 1
_L2_IDX_MODE = 2
_L2_IDX_PREPROC = 3
_L2_IDX_RADIUS = 4
_L2_IDX_ALGO = 5


def compute_source_cache_key(file_bytes: bytes) -> str:
    """对已在内存中的文件字节做一次性内容摘要（sha256 前 16 hex）

    供 FileItem 导入时调用一次并保存，后续生成直接复用，
    避免每次渲染都对全图 tobytes() 重新哈希。
    """
    return hashlib.sha256(file_bytes).hexdigest()[:16]


def build_l2_key(source_cache_key: str, normalized_size: Tuple[int, int],
                 normalized_mode: str, blur_radius: int) -> tuple:
    """组装二级缓存完整键（设计文档 §5.3）

    (source_cache_key, normalized_image_size, normalized_image_mode,
     preprocessing_version, blur_radius, gaussian_algorithm_version)

    背景类型/叠色/透明度/饱和度/目标画布尺寸/矩形位置不进键——
    这些都发生在原始卷积之后，切换它们时应命中缓存并只重新派生。
    """
    return (str(source_cache_key), tuple(normalized_size), str(normalized_mode),
            PREPROCESSING_VERSION, int(blur_radius), GAUSSIAN_ALGORITHM_VERSION)


class PreparedBlurLRU:
    """二级缓存：按 nbytes 计量、有预算上限的 LRU

    只应保存 source_kind='photo' 的 PreparedBlur；base_scene 依赖
    背景/画布/圆角/旧式矩形等完整场景指纹，一律不进 LRU（见设计文档
    §5.3"精确型切换背景后重新卷积属于正确失效"）。

    默认预算 64 MiB：工作长边上限 1200 时一张方形 float32 RGB 工作
    图理论上限约 16.5 MiB，该预算可容纳少量图片/半径组合而不无界增长。
    """

    def __init__(self, budget_bytes: int = 64 * 1024 * 1024):
        self._budget = max(1, int(budget_bytes))
        self._items = OrderedDict()  # l2_key -> PreparedBlur（尾部=最近使用）
        self._current_bytes = 0

        # 命中/未命中/淘汰计数（DEBUG 日志与 gate G4 验收断言用）
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get(self, key: tuple) -> Optional[PreparedBlur]:
        """取缓存项并移动到最近使用位；未命中返回 None"""
        prepared = self._items.get(key)
        if prepared is not None:
            self._items.move_to_end(key)
            self.hits += 1
        else:
            self.misses += 1
        return prepared

    def put(self, key: tuple, prepared: PreparedBlur) -> None:
        """存入缓存项，超预算时从最久未使用项开始释放"""
        if key in self._items:
            # 重复写入：先移除旧条目再插入，保证计量准确
            self._current_bytes -= self._items[key].nbytes
            del self._items[key]
        self._items[key] = prepared
        self._current_bytes += prepared.nbytes
        while self._current_bytes > self._budget and len(self._items) > 1:
            _, evicted = self._items.popitem(last=False)
            self._current_bytes -= evicted.nbytes
            self.evictions += 1
            logger.debug("blur L2 cache: evicted entry, budget=%s, current=%s",
                         self._budget, self._current_bytes)

    def clear(self) -> None:
        """清空全部缓存（页面关闭时调用）"""
        self._items.clear()
        self._current_bytes = 0

    @property
    def current_bytes(self) -> int:
        return self._current_bytes

    def stats(self) -> str:
        """命中统计摘要（DEBUG 日志 / gate G4 断言用）"""
        return (f"L2 hit/miss={self.hits}/{self.misses}, "
                f"evictions={self.evictions}, "
                f"entries={len(self._items)}, bytes={self._current_bytes}")


class RenderBlurCache:
    """单次渲染内的高斯模糊懒缓存（一级缓存）

    - 源图唯一：构造时传入，get_prepared 键只需 (source_kind, radius)；
    - 卷积懒计算：首次请求某半径时才调用 prepare_gaussian_blur()；
    - 派生结果帧内缓存：同 (radius, saturation, target_size) 的缩放/着色前
      结果只生成一次；
    - 命中/未命中计数：供 blur plan 日志与验收断言（设计文档 §8）。
    """

    def __init__(self, source_image: Image.Image,
                 prepared_lru: Optional[PreparedBlurLRU] = None,
                 source_cache_key: Optional[str] = None):
        # 帧内源图（只持引用，不复制；生命周期由调用方 render_frame 决定）
        self._source_image = source_image
        # 可选二级缓存（页面级 PreparedBlurLRU）
        self._prepared_lru = prepared_lru
        # 源图稳定键：与 prepared_lru 同时提供时才启用二级查询/写入
        # （键不完整的跨帧复用有错误命中风险，宁可不缓存）
        self._source_cache_key = source_cache_key
        # 帧内 PreparedBlur 缓存：键 (source_kind, radius)
        self._prepared = {}
        # 帧内派生结果缓存：键 (source_kind, radius, saturation, size)
        self._derived = {}

        # ── 命中/未命中统计（日志与验收断言用） ──
        self.prepared_hits = 0
        self.prepared_misses = 0
        # 二级缓存命中/未命中（计入 prepared_hits/misses 的子集）
        self.l2_hits = 0
        self.l2_misses = 0
        self.derived_hits = 0
        self.derived_misses = 0
        # 实际执行的卷积次数（= prepare_gaussian_blur 调用次数）
        self.convolution_count = 0

    # ── 卷积层 ──────────────────────────────────────────

    def get_prepared(self, source_kind: str, radius: int) -> PreparedBlur:
        """取（或懒计算）指定源与半径的工作分辨率卷积结果

        source_kind 本期仅支持 'photo'；'base_scene' 为方案 B 预留，
        传入即抛 NotImplementedError（接口位，防止误用）。
        """
        if source_kind != SOURCE_PHOTO:
            # 方案 B（base_scene 二次模糊）接口位：Phase 3 首期不实现
            raise NotImplementedError(
                f"source_kind={source_kind!r} 尚未实现（方案 B 预留）")

        key = (source_kind, int(radius))
        if key in self._prepared:
            self.prepared_hits += 1
            return self._prepared[key]

        # 二级查询：键含源摘要+尺寸+模式+预处理版本+半径+算法版本，
        # 跨图/跨预处理/跨半径/跨算法版本一律未命中（防错误复用）
        lru_key = None
        if self._prepared_lru is not None and self._source_cache_key is not None:
            lru_key = build_l2_key(
                self._source_cache_key, self._source_image.size,
                self._source_image.mode, int(radius))
            prepared = self._prepared_lru.get(lru_key)
            if prepared is not None:
                self.l2_hits += 1
                self.prepared_hits += 1
                self._prepared[key] = prepared
                logger.debug(
                    "blur cache hit: level=L2, source_key=%s, source=photo, "
                    "radius=%s", self._source_cache_key, int(radius))
                return prepared
            self.l2_misses += 1

        self.prepared_misses += 1
        prepared = prepare_gaussian_blur(self._source_image, int(radius))
        self.convolution_count += 1
        self._prepared[key] = prepared
        # 二级写入：只存 photo 源的 PreparedBlur（工作分辨率 float32），
        # 绝不存全画布派生图（设计红线 8）
        if lru_key is not None:
            self._prepared_lru.put(lru_key, prepared)
        logger.debug(
            "blur cache miss: level=%s, source_key=%s, source=photo, radius=%s "
            "(convolutions=%s)",
            "L2" if lru_key is not None else "L1",
            self._source_cache_key, int(radius), self.convolution_count)
        return prepared

    # ── 派生层 ──────────────────────────────────────────

    def get_photo_size_blur(self, radius: int, saturation: float = 1.0) -> Image.Image:
        """原图尺寸派生：矩形 ⊆ original_bounds 时按照片局部坐标取样"""
        return self._get_derived(
            SOURCE_PHOTO, radius, saturation, tuple(self._source_image.size))

    def get_canvas_size_blur(self, radius: int, saturation: float = 1.0,
                             canvas_size: Optional[Tuple[int, int]] = None) -> Image.Image:
        """画布尺寸派生：跨界/照片外矩形按画布坐标取样（延续背景拉伸语义）"""
        if canvas_size is None:
            raise ValueError("canvas_size 必须显式传入（画布宽高二元组）")
        return self._get_derived(
            SOURCE_PHOTO, radius, saturation, tuple(canvas_size))

    def _get_derived(self, source_kind: str, radius: int,
                     saturation: float, size: Tuple[int, int]) -> Image.Image:
        """帧内派生缓存：同键只缩放/增强一次（饱和度→uint8→resize）"""
        key = (source_kind, int(radius), float(saturation), size)
        if key in self._derived:
            self.derived_hits += 1
            return self._derived[key]

        self.derived_misses += 1
        prepared = self.get_prepared(source_kind, radius)
        derived = render_prepared_blur(prepared, size, saturation)
        self._derived[key] = derived
        return derived

    # ── 统计输出 ────────────────────────────────────────

    def summary(self) -> str:
        """命中统计摘要（DEBUG 日志 / Phase 6 验收断言用）"""
        return (f"prepared hit/miss={self.prepared_hits}/{self.prepared_misses} "
                f"(L2 hit/miss={self.l2_hits}/{self.l2_misses}), "
                f"derived hit/miss={self.derived_hits}/{self.derived_misses}, "
                f"convolutions={self.convolution_count}")
