# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
高斯模糊工具模块

纯算法层定位：只做工作尺寸计算、卷积、饱和度增强、缩放与颜色叠加，
不感知画布扩展、矩形位置或启用判定（这些属渲染器职责）。

v2.6 起算法拆分为三个可组合阶段（设计文档 §4.1 "共享阶段"）：
    共享阶段  prepare_gaussian_blur()   原图 → 工作尺寸 → 三遍 Box Blur
    派生阶段  render_prepared_blur()    float32 饱和度增强 → uint8 → 缩放
    着色阶段  apply_color_overlay()     任意 RGB 叠色（矩形分支复用）
原入口 apply_gaussian_blur_overlay_expansion() 保持签名与像素行为不变，
内部改为三函数组合。
"""
from PIL import Image
import numpy as np

COLOR_OPTIONS = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
}

_BLUR_WORK_MAX = 1200
_BLUR_WORK_MIN = 512
_BOX_BLUR_PASSES = 3


def _box_blur_numpy(arr: np.ndarray, radius: float) -> np.ndarray:
    r = int(radius)
    if r <= 0:
        return arr
    kernel = np.ones(2 * r + 1, dtype=np.float32) / (2 * r + 1)

    def _blur_1d(x):
        return np.convolve(np.pad(x, r, mode='edge'), kernel, mode='valid')

    for _ in range(_BOX_BLUR_PASSES):
        arr = np.apply_along_axis(_blur_1d, 1, arr)
        arr = np.apply_along_axis(_blur_1d, 0, arr)
    return arr


def _compute_scale_factor(image_long_edge: int) -> float:
    if image_long_edge <= _BLUR_WORK_MAX:
        return 1.0
    return _BLUR_WORK_MAX / image_long_edge


def _enhance_saturation_numpy(arr: np.ndarray, factor: float) -> np.ndarray:
    if factor <= 1.0:
        return arr
    L = (0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2])
    result = np.stack([
        L + (arr[:, :, 0] - L) * factor,
        L + (arr[:, :, 1] - L) * factor,
        L + (arr[:, :, 2] - L) * factor,
    ], axis=-1)
    return np.clip(result, 0, 255)


class PreparedBlur:
    """着色前、目标尺寸缩放前的工作分辨率卷积结果。

    内部保留 float32 数组（而非 uint8）：原算法在 float32 域连续完成
    box blur → 饱和度增强，中途量化会引入不可逆差异，拆分后必须接力
    float32 才能保证背景输出逐像素不变（Phase 1 验收硬标准）。

    生命周期：由 prepare_gaussian_blur() 创建，可同时派生任意数量的
    目标尺寸结果；作为整体参与缓存（二级缓存的计量与存储单位）。
    """

    def __init__(self, work_arr: np.ndarray, scale_factor: float):
        # 工作分辨率 float32 RGB 数组，形状 (h, w, 3)，值域 [0, 255]
        self._work_arr = work_arr
        # 工作分辨率相对原图的缩放系数（<=1.0；1.0 表示未降采样）。
        # 当前派生阶段不直接消费它，保留以备精确型/调试用途
        self._scale_factor = scale_factor

    @property
    def work_arr(self) -> np.ndarray:
        """工作分辨率 float32 数组（只读视图约定：调用方不得原地修改）"""
        return self._work_arr

    @property
    def scale_factor(self) -> float:
        return self._scale_factor

    @property
    def nbytes(self) -> int:
        """数组字节数，供二级缓存（PreparedBlurLRU）预算计量"""
        return self._work_arr.nbytes


def prepare_gaussian_blur(image: Image.Image, radius: int) -> PreparedBlur:
    """共享阶段：原图 → 工作尺寸（≤1200 长边，短边≥512）→ 三遍 Box Blur（float32）

    这是模糊计算中最昂贵的部分，产物可被同源同半径的多个消费者
    （背景、多个矩形）共享；不同目标尺寸只产生廉价的缩放派生。

    Args:
        image: 原始图像（任意模式，内部转 RGB）
        radius: 全分辨率等效模糊半径

    Returns:
        PreparedBlur：着色前、目标尺寸缩放前的卷积结果
    """
    orig_w, orig_h = image.size
    image_long = max(orig_w, orig_h)

    scale_factor = _compute_scale_factor(image_long)

    blur_img = image.copy().convert('RGB')

    if scale_factor < 1.0:
        scaled_w = max(int(orig_w * scale_factor), _BLUR_WORK_MIN)
        scaled_h = max(int(orig_h * scale_factor), _BLUR_WORK_MIN)
        blur_img = blur_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

    effective_radius = radius * scale_factor

    # float32 域卷积：与原实现一致，量化推迟到派生阶段饱和度增强之后
    arr = np.array(blur_img, dtype=np.float32)
    arr = _box_blur_numpy(arr, effective_radius)

    return PreparedBlur(arr, scale_factor)


def render_prepared_blur(
    prepared: PreparedBlur,
    target_size,
    saturation: float = 1.0,
) -> Image.Image:
    """派生阶段：float32 饱和度增强 → uint8 → 缩放到目标尺寸

    Args:
        prepared: prepare_gaussian_blur() 的产物
        target_size: (width, height)——原图尺寸（矩形 photo 分支）
                     或画布尺寸（背景分支）
        saturation: 饱和度增强系数（1.0 = 不变，>1.0 增强）

    Returns:
        RGB 模式的目标尺寸模糊图像（未叠色）
    """
    # 与原实现顺序严格一致：先在 float32 域做饱和度增强，
    # 再一次性量化 uint8，最后缩放到目标尺寸
    arr = _enhance_saturation_numpy(prepared.work_arr, saturation)
    blur_img = Image.fromarray(arr.astype(np.uint8), mode='RGB')
    return blur_img.resize(tuple(target_size), Image.Resampling.LANCZOS)


def apply_color_overlay(
    image: Image.Image,
    color,
    opacity_percent: int,
) -> Image.Image:
    """着色阶段：按不透明度百分比向图像叠加纯色

    color 支持两种形式：
      - 颜色名（'black' / 'white' / 'gray'，见 COLOR_OPTIONS）——背景分支沿用
      - 任意 (r, g, b) RGB 元组——矩形效果栈分支使用

    Args:
        image: RGB 模式图像
        color: 颜色名或 RGB 元组
        opacity_percent: 不透明度百分比 (0-100)

    Returns:
        叠色后的 RGB 图像（新对象）
    """
    # 颜色名先查表，查不到则按 RGB 元组使用
    overlay_rgb = COLOR_OPTIONS.get(color, color)
    img_arr = np.array(image, dtype=np.float32)
    alpha = opacity_percent / 100.0
    overlay_arr = np.full_like(img_arr, fill_value=np.array(overlay_rgb, dtype=np.float32))
    blended = img_arr * (1.0 - alpha) + overlay_arr * alpha
    blended = np.clip(blended, 0, 255).astype(np.uint8)
    return Image.fromarray(blended, mode='RGB')


def apply_gaussian_blur_overlay_expansion(
    image: Image.Image,
    canvas_width: int,
    canvas_height: int,
    overlay_color: str,
    opacity: int,
    blur_radius: int = 200,
    saturation: float = 1.0,
) -> Image.Image:
    """
    应用高斯模糊叠加效果（适用于扩展画布）

    自 v2.6 起为三阶段组合实现：卷积 → 饱和度 → 缩放 → 叠色，
    顺序与拆分前严格一致，输出像素不变（gate G1 基线矩阵验证）。

    Args:
        image: 原始图像
        canvas_width: 画布宽度
        canvas_height: 画布高度
        overlay_color: 叠加颜色
        opacity: 透明度百分比 (0-100)
        blur_radius: 全分辨率下的模糊半径 (默认200)
        saturation: 饱和度增强系数（1.0 = 不变，>1.0 增强，用于补偿覆盖层颜色淡化）

    Returns:
        应用效果后的背景图像
    """
    # 共享阶段：工作分辨率卷积（可缓存/可共享的部分）
    prepared = prepare_gaussian_blur(image, blur_radius)
    # 派生阶段：饱和度增强 + 缩放到画布尺寸
    blur_img = render_prepared_blur(prepared, (canvas_width, canvas_height), saturation)
    # 着色阶段：黑/白叠色
    return apply_color_overlay(blur_img, overlay_color, opacity)
