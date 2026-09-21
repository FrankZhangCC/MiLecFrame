# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
旋转适配工具模块（样式预设仅对竖图生效）

集中保存方向适配的枚举常量、样式默认值校验、用户/样式优先级解析、
无损 90° 离散转置与高斯二级缓存键方向派生。
设计文档：docs/plans/PORTRAIT_ORIENTATION_ADAPTATION_PLAN.md（§3/§4/§5）。

两层配置契约：
  - 用户运行时选项 RenderOptions.portrait_adaptation
    （default / none / clockwise / counterclockwise）
  - 样式默认值 style_config['default_portrait_adaptation']
    （clockwise / counterclockwise / none）
  优先级：用户显式选择 > 样式默认值；样式默认值只在用户选择
  'default' 时生效（见 resolve_effective_adaptation 的优先级矩阵）。

图片方向适用范围（按旋转来源区分，见 rotate_image_for_render）：
  - 用户显式选择顺/逆时针 → 所有图片（横图/竖图/方形图）都旋转
  - 样式预设（用户选择 default 时）→ 仅竖图旋转（预设是样式
    对竖拍构图的建议，横图/方形图保持原方向）

调用链位置：
  - StyleManager._validate_config() → validate_style_default（磁盘配置入口校验）
  - FrameRenderer.render_frame()    → resolve + rotate + restore + 缓存键派生
  - 图片处理页 GUI                   → USER_ADAPTATION_VALUES 读取防御
  - 样式编辑器表单                   → validate_style_default（反序列化校验）

本模块不得引入任何 Qt / GUI 依赖，保证 CLI 与临时验证脚本可直接 import 单测。
"""
import logging
from typing import Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

# ── 枚举常量 ────────────────────────────────────────────────
# 'default' 仅作为用户选项合法值（语义=跟随样式声明）；样式字段本身
# 缺失时语义为 'none'（不适配），不存在"样式的默认值还是 default"的递归语义
ADAPT_DEFAULT = 'default'
ADAPT_NONE = 'none'
ADAPT_CLOCKWISE = 'clockwise'
ADAPT_COUNTERCLOCKWISE = 'counterclockwise'

# 用户选项全集（GUI 下拉框稳定内部值，方案 §1.1/§6.3）
USER_ADAPTATION_VALUES = frozenset({
    ADAPT_DEFAULT, ADAPT_NONE, ADAPT_CLOCKWISE, ADAPT_COUNTERCLOCKWISE,
})

# 样式默认值合法值全集（无 'default'，方案 §3.2）
STYLE_ADAPTATION_VALUES = frozenset({
    ADAPT_NONE, ADAPT_CLOCKWISE, ADAPT_COUNTERCLOCKWISE,
})

# 样式配置顶层字段名（方案 §3.2）
STYLE_DEFAULT_KEY = 'default_portrait_adaptation'

# 高斯二级缓存键方向后缀（仅真实旋转过的源图使用，方案 §5.4）：
# cw/ccw 旋转后尺寸相同但像素方向不同，仅靠 (尺寸, 模式, 半径) 无法区分，
# 必须在源键上附加方向后缀防止串用
ADAPT_KEY_SUFFIX = {
    ADAPT_CLOCKWISE: ':portrait-adapt-cw',
    ADAPT_COUNTERCLOCKWISE: ':portrait-adapt-ccw',
}


def validate_style_default(style_config: dict) -> str:
    """校验样式配置中的竖图方向适配默认值，返回解析结果

    规则（方案 §3.2）：
      - 配置非字典或字段缺失 → 'none'（保持所有现有样式的旧行为）
      - 值必须是 none / clockwise / counterclockwise 之一
      - 布尔、null、数字、大小写变体、未知字符串 → ValueError
        （不静默回退，避免静默选择错误方向）

    Args:
        style_config: 整份样式配置字典（顶层读取 STYLE_DEFAULT_KEY）

    Returns:
        合法样式默认值字符串

    Raises:
        ValueError: 字段存在但值非法，消息点名字段与合法值
    """
    if not isinstance(style_config, dict) or STYLE_DEFAULT_KEY not in style_config:
        return ADAPT_NONE
    value = style_config[STYLE_DEFAULT_KEY]
    if value in STYLE_ADAPTATION_VALUES:
        return value
    raise ValueError(
        f"{STYLE_DEFAULT_KEY} 值非法: {value!r}，"
        f"合法值为 {'/'.join(sorted(STYLE_ADAPTATION_VALUES))}"
        f"（字段缺失等同于 {ADAPT_NONE}）"
    )


def resolve_effective_adaptation(
    style_config: dict,
    user_choice: str,
) -> Tuple[str, bool]:
    """按"用户选择优先、样式默认兜底"规则解析最终方向（方案 §1.3/§4）

    优先级矩阵（用户选择 × 样式默认值 = 最终方向）：
      user=default            → 样式默认值（字段缺失按 none）
      user=none/cw/ccw        → 直接采用（显式覆盖样式）
      user 非法               → ValueError

    即使 GUI 只会产生合法值，渲染器也必须经本校验，覆盖 CLI、
    临时代码和未来调用方（方案 §4）。

    Args:
        style_config: 整份样式配置字典
        user_choice: RenderOptions.portrait_adaptation 用户选项

    Returns:
        (最终方向, 是否来自用户显式选择) 二元组。
        第二个元素决定旋转的图片方向适用范围（见
        rotate_image_for_render）：用户显式选择对所有图片生效，
        样式预设仅对竖图生效。

    Raises:
        ValueError: 用户选择非法，或样式默认值非法
    """
    if user_choice not in USER_ADAPTATION_VALUES:
        raise ValueError(
            f"portrait_adaptation 用户选项非法: {user_choice!r}，"
            f"合法值为 {'/'.join(sorted(USER_ADAPTATION_VALUES))}"
        )
    if user_choice == ADAPT_DEFAULT:
        return validate_style_default(style_config), False
    return user_choice, True


def rotate_image_for_render(
    image: Image.Image,
    effective_adaptation: str,
    from_user: bool,
) -> Tuple[Image.Image, bool]:
    """前置旋转：按最终方向做 90° 离散转置（方案 §1.4/§5.2）

    图片方向适用范围按旋转来源区分：
      - from_user=True（用户显式选择顺/逆时针）：所有图片都旋转，
        横图/方形图同样适配
      - from_user=False（样式预设生效）：仅 height > width 的竖图
        旋转——预设是样式对竖拍构图的建议，横图/方形图保持原方向
      - effective_adaptation 为 none：任何图片都不旋转

    - clockwise:        ROTATE_270（= 顺时针 90°）
    - counterclockwise: ROTATE_90 （= 逆时针 90°）
    - transpose() 是整数像素重排，无插值损失，自然交换宽高
    - 未旋转路径零复制：直接返回传入的原图对象引用，保证"旧输出
      像素不变"的回归基线（方案 §10.4）

    Args:
        image: EXIF 转正后的正向图（方向判断以此为基准，方案 §5.3）
        effective_adaptation: resolve_effective_adaptation 的返回值[0]
        from_user: resolve_effective_adaptation 的返回值[1]

    Returns:
        (旋转后的图像, 是否真实旋转) 二元组

    Raises:
        ValueError: effective_adaptation 非法（解析函数已保证不会发生，
                    此处为绕过解析直传的防御）
    """
    width, height = image.size
    if effective_adaptation == ADAPT_NONE:
        return image, False
    if not from_user and height <= width:
        # 样式预设只对竖图起作用：横图与方形图保持原方向
        return image, False
    if effective_adaptation == ADAPT_CLOCKWISE:
        transposed = image.transpose(Image.Transpose.ROTATE_270)
    elif effective_adaptation == ADAPT_COUNTERCLOCKWISE:
        transposed = image.transpose(Image.Transpose.ROTATE_90)
    else:
        raise ValueError(
            f"effective_adaptation 非法: {effective_adaptation!r}"
            f"（应先经 resolve_effective_adaptation 解析）"
        )
    logger.debug(
        "方向适配前置旋转: %s（来源=%s）(%dx%d -> %dx%d)",
        effective_adaptation, "用户显式" if from_user else "样式预设",
        width, height, transposed.size[0], transposed.size[1])
    return transposed, True


def restore_rendered_orientation(
    image: Image.Image,
    effective_adaptation: str,
    applied: bool,
) -> Image.Image:
    """反向旋转：仅在前置旋转真实应用过时执行对应反向转置（方案 §4）

    只认 applied 标志，不重新判断宽高——渲染后的成品画布必然保持
    竖图宽高比（前置旋转交换过一次宽高），此时重判宽高没有意义，
    applied 是"是否需要还原"的唯一事实来源。

    Args:
        image: 整帧渲染完成的输出图
        effective_adaptation: resolve_effective_adaptation 的返回值
        applied: rotate_image_for_render 返回的旋转标志

    Returns:
        还原后的图像（applied=False 时原样返回输入引用）

    Raises:
        ValueError: applied=True 且 effective_adaptation 非法
    """
    if not applied:
        return image
    if effective_adaptation == ADAPT_CLOCKWISE:
        # 前置顺时针 90° → 渲染后逆时针 90° 还原
        return image.transpose(Image.Transpose.ROTATE_90)
    if effective_adaptation == ADAPT_COUNTERCLOCKWISE:
        # 前置逆时针 90° → 渲染后顺时针 90° 还原
        return image.transpose(Image.Transpose.ROTATE_270)
    raise ValueError(
        f"effective_adaptation 非法: {effective_adaptation!r}")


def build_adapted_source_cache_key(
    source_cache_key: Optional[str],
    effective_adaptation: str,
    applied: bool,
) -> Optional[str]:
    """为真实旋转过的源图派生方向隔离的高斯二级缓存键（方案 §5.4）

    键规则：
      原键 / None                → none、横图、方形图（像素未变）
      原键:portrait-adapt-cw     → 竖图顺时针适配
      原键:portrait-adapt-ccw    → 竖图逆时针适配

    只派生新字符串返回，绝不修改调用方持有的
    RenderOptions.source_cache_key——GUI 和批处理可能跨多次渲染
    复用同一个 RenderOptions 对象（方案 §12 污染风险红线）。

    Args:
        source_cache_key: 调用方持有的源图稳定键（None=未启用二级缓存）
        effective_adaptation: resolve_effective_adaptation 的返回值
        applied: rotate_image_for_render 返回的旋转标志

    Returns:
        派生后的局部缓存键（可能就是输入值本身）
    """
    if source_cache_key is None or not applied:
        return source_cache_key
    suffix = ADAPT_KEY_SUFFIX.get(effective_adaptation)
    if suffix is None:
        # applied=True 时 effective 必为 cw/ccw（rotate 阶段已校验），
        # 未知值属防御分支：不派生后缀，维持原键
        return source_cache_key
    return f"{source_cache_key}{suffix}"
