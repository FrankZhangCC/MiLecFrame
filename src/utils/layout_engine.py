# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
布局引擎模块

定位语义（运行时唯一一套算法；无旧算法分支、无语义版本开关、无旧别名归一化）：

    照片边界
       │
       ├─ position ──> 照片九点之一作为参考点 (px, py)
       │
       └─ margin / placement ──> 在参考点上得到元素锚点 (ax, ay)
                                      │
    元素宽高 (ew, eh) + alignment ────┘
                                      │
                                      └─> 元素布局盒左上角 (x, y)

职责边界（见 docs/plans/POSITION_ALIGNMENT_REPAIR_EXECUTION_PLAN.md §1.1）：

- position 只选择照片九点参考位，输入只有照片几何和 margin，
  全程不读取元素宽高；
- alignment 只决定元素布局盒的哪个点贴到元素锚点，输入只有元素锚点
  和元素宽高，全程不读取照片边界、position、placement 或 margin；
- margin 只移动元素锚点，不直接移动元素某条边；
- padding 是最终安全区域约束，可能修正最终盒坐标，但不改变锚点定义；
- 相对定位（relative_to）使用独立的 cross_alignment 三值交叉轴对齐，
  与绝对定位的九点 alignment 互不混用；
- tree_align 组合树把整树包围盒当作普通盒子走同一套绝对定位几何。

历史旧算法（复合 position/alignment 语义、both-center、单轴别名）已
原样离线归档于 docs/legacy/positioning_v1/layout_engine.py.txt，
仅供排查与迁移参考：不得 import、不得进入运行时分支、不得打包发行。
"""
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

# ── 绝对定位九点枚举 ────────────────────────────────────────────
# position 与 alignment 共享同一九点值集合（审计 Q9）：两个名字保留
# 语义别名，校验函数各自的报错文案与迁移提示不变。
# 只接受完整九点规范值，不保留旧别名映射。旧值（top / bottom / left /
# right / tc / bc / tl / tr / bl / br / both-center 等）由 StyleManager
# 在样式加载阶段直接拒绝并给出迁移建议；本引擎仍做防御性异常兜底。
_NINE_POINT_VALUES = frozenset({
    'top-left', 'top-center', 'top-right',
    'center-left', 'center', 'center-right',
    'bottom-left', 'bottom-center', 'bottom-right',
})
ABSOLUTE_POSITIONS = _NINE_POINT_VALUES
ABSOLUTE_ALIGNMENTS = _NINE_POINT_VALUES

# ── 相对定位交叉轴枚举 ──────────────────────────────────────────
# above/below 在参考元素宽度内水平对齐（左缘/中心/右缘）；
# left-of/right-of 在参考元素高度内垂直对齐（顶缘/中心/底缘）。
HORIZONTAL_CROSS_ALIGNMENTS = frozenset({'left', 'center', 'right'})
VERTICAL_CROSS_ALIGNMENTS = frozenset({'top', 'center', 'bottom'})

# 相对定位方向只接受这四个值（旧 after/before 已随旧语义一并删除）。
RELATIVE_POSITIONS = frozenset({'above', 'below', 'left-of', 'right-of'})


def resolve_relative_chain(
    configs: Dict[str, Dict], start: str
) -> Tuple[List[str], Dict, Optional[List[str]]]:
    """沿 relative_to 链自 start 向上找根（审计 Q4）。

    依赖树的根查找与环检测复用同一实现：text_renderer 判断链根的
    tree_align、StyleManager 校验环均调用本函数，不再各自维护一份
    向上遍历逻辑。

    Args:
        configs: 裸名 → 定位配置 dict（与渲染端 all_positions 的合并
            键空间一致）
        start: 起始元素名

    Returns:
        (chain, terminal_cfg, cycle)
        chain — 节点名链，从 start 开始，按向上遍历顺序
        terminal_cfg — 链终点配置：终点不在 configs 中时为 {}，
                       在时为其配置 dict（用于读取 tree_align）
        cycle — 环节点名链（末尾重复闭环首节点）；无环为 None
    """
    chain = [start]
    walk = start
    while True:
        cfg = configs.get(walk) or {}
        ref = cfg.get('relative_to')
        if not ref:
            # 链终点：绝对定位根，或目标不在配置集合内
            return chain, cfg, None
        if ref in chain:
            return chain, cfg, chain[chain.index(ref):] + [ref]
        chain.append(ref)
        walk = ref


class LayoutEngine:
    """统一布局引擎，支持文字和非文字元素的定位，以及位置注册表"""

    def __init__(self, original_image_size: Tuple[int, int], layout_config: Dict):
        self.original_image_size = original_image_size
        self.original_width, self.original_height = original_image_size
        self.reference_side = min(self.original_width, self.original_height)

        self.layout_config = layout_config
        self.canvas_size = self._calculate_canvas_size()
        self.canvas_width, self.canvas_height = self.canvas_size
        self.original_bounds = self._calculate_original_bounds()
        self.padding_bounds = self._calculate_padding_bounds()

        # 照片几何派生只求值一次（审计 Q10）：九点参考点表与边界坐标
        # 供定位与诊断（get_absolute_layout_info）共享，不再各自解包
        # original_bounds 重复计算
        _l, _t, _ow, _oh = self.original_bounds
        self._photo_edges = (
            _l, _t, _l + _ow, _t + _oh, _l + _ow // 2, _t + _oh // 2)
        _l, _t, _r, _b, _cx, _cy = self._photo_edges
        self._photo_ref_points = {
            'top-left': (_l, _t),
            'top-center': (_cx, _t),
            'top-right': (_r, _t),
            'center-left': (_l, _cy),
            'center': (_cx, _cy),
            'center-right': (_r, _cy),
            'bottom-left': (_l, _b),
            'bottom-center': (_cx, _b),
            'bottom-right': (_r, _b),
        }

        self.positions: Dict[str, dict] = {}
        self._dependents: Dict[str, list] = {}

    # ── 画布 / 照片 / padding 几何 ──────────────────────────

    def _calculate_canvas_size(self) -> Tuple[int, int]:
        expand_config = self.layout_config.get('expand_canvas', {})
        if not expand_config.get('enabled', False):
            return self.original_image_size

        top_exp = expand_config.get('top', 0)
        bottom_exp = expand_config.get('bottom', 0)
        left_exp = expand_config.get('left', 0)
        right_exp = expand_config.get('right', 0)

        new_width = self.original_width + int(self.reference_side * (left_exp + right_exp))
        new_height = self.original_height + int(self.reference_side * (top_exp + bottom_exp))

        return new_width, new_height

    def _calculate_original_bounds(self) -> Tuple[int, int, int, int]:
        expand_config = self.layout_config.get('expand_canvas', {})
        if not expand_config.get('enabled', False):
            x = (self.canvas_width - self.original_width) // 2
            y = (self.canvas_height - self.original_height) // 2
        else:
            top_exp = expand_config.get('top', 0)
            left_exp = expand_config.get('left', 0)
            x = int(self.reference_side * left_exp)
            y = int(self.reference_side * top_exp)

        return x, y, self.original_width, self.original_height

    def _calculate_padding_bounds(self) -> Tuple[int, int, int, int]:
        """
        计算叠加元素的安全区域（padding），从画布四边向内收缩。
        返回 (left_bound, top_bound, right_bound, bottom_bound)
        padding 值以 reference_side 比例为基准，默认为 0（即画布边界）
        """
        padding_config = self.layout_config.get('padding', {})
        if not padding_config:
            return 0, 0, self.canvas_width, self.canvas_height

        def ratio_to_px(value):
            # padding 的数值一律按参照边比例换算（STYLE_GUIDE §padding）。
            # 注意与 margin 的单位语义不同（审计 Q13）：margin 整数是
            # 像素、浮点才是比例，两套换算保持可区分的命名，不得合并。
            if isinstance(value, (int, float)):
                return int(self.reference_side * float(value))
            return 0

        pad_left = ratio_to_px(padding_config.get('left', 0))
        pad_top = ratio_to_px(padding_config.get('top', 0))
        pad_right = ratio_to_px(padding_config.get('right', 0))
        pad_bottom = ratio_to_px(padding_config.get('bottom', 0))

        return (
            pad_left,
            pad_top,
            self.canvas_width - pad_right,
            self.canvas_height - pad_bottom
        )

    # ── 元素位置注册表 ──────────────────────────────────────

    def register_element(self, name: str, x: int, y: int, width: int, height: int, relative_to: str = None, ascent: int = None):
        self.positions[name] = {'x': x, 'y': y, 'width': width, 'height': height, 'ascent': ascent}
        if relative_to:
            if relative_to not in self._dependents:
                self._dependents[relative_to] = []
            if name not in self._dependents[relative_to]:
                self._dependents[relative_to].append(name)

    def _lookup_position(self, name: str) -> Optional[Tuple[str, Tuple[int, int, int, int]]]:
        """元素查找唯一入口（审计 Q11）。

        先精确命中，再按双向 endswith 模糊匹配（保持既有 dict 插入序
        遍历与兼容行为）。返回 (真实注册表 key, (x, y, w, h))，未命中
        返回 None。get_element_bounds 与相对定位共享本入口，模糊查找
        逻辑不再存在第二份实现。
        """
        if name in self.positions:
            pos = self.positions[name]
            return name, (pos['x'], pos['y'], pos['width'], pos['height'])
        for key, pos in self.positions.items():
            if key == name or key.endswith(name) or name.endswith(key):
                return key, (pos['x'], pos['y'], pos['width'], pos['height'])
        return None

    def get_element_bounds(self, name: str) -> Optional[Tuple[int, int, int, int]]:
        found = self._lookup_position(name)
        return found[1] if found else None

    # ── 枚举校验（防御性兜底；样式加载阶段的正式校验在 StyleManager） ──

    def _validate_position(self, value) -> str:
        """只接受九点规范 position 值；未知值（含旧别名）抛出包含字段值的异常"""
        if value not in ABSOLUTE_POSITIONS:
            raise ValueError(
                f"position 值非法: {value!r}；"
                f"九个规范值为 {sorted(ABSOLUTE_POSITIONS)}"
                f"（旧单轴值如 top/bottom/left/right 已删除，请改用完整九点值）")
        return value

    def _validate_alignment(self, value) -> str:
        """只接受九点规范 alignment 值；未知值（含 both-center 旧值）抛出异常"""
        if value not in ABSOLUTE_ALIGNMENTS:
            raise ValueError(
                f"alignment 值非法: {value!r}；"
                f"九个规范值为 {sorted(ABSOLUTE_ALIGNMENTS)}"
                f"（旧值 both-center 请改为 center，单轴值请结合实际位置选择完整九点值）")
        return value

    # ── 统一入口 ────────────────────────────────────────────

    def calculate_position(
        self,
        element_width: int,
        element_height: int,
        config: Dict,
        padding_mode: str = 'clamp',
    ) -> Tuple[int, int]:
        """
        计算元素的绘制坐标（统一处理文字和非文字元素）

        config 支持的键：
        - placement: 'inside' 或 'outside'（默认 'outside'），
            只决定元素位于照片边界主轴的内侧或外侧
        - relative_to: 参考元素名（有此键则使用相对定位）
        - relative_position: 'above' / 'below' / 'left-of' / 'right-of'
        - cross_alignment: 相对定位交叉轴对齐
            （above/below → left/center/right；left-of/right-of → top/center/bottom）
        - relative_margin: 间距比例
        - offset_x_ratio / offset_y_ratio: 微调偏移比例（相对定位）
        - position: 照片九点参考位（top-left ... bottom-right）
        - alignment: 元素布局盒九点自对齐（元素布局盒的哪个点贴到元素锚点）
        - margin / margin_top / margin_bottom / margin_left / margin_right: 边距

        padding_mode: 安全区域夹持策略（审计 Q4——此前单个布尔参数混用
            "延迟"与"永久豁免"两种语义，现拆分为显式三态）：
            'clamp'  — 立即夹持到 padding 安全区（普通文字、Logo 等默认）
            'defer'  — 暂缓夹持并跳过组合盒溢出平移，由
                       apply_tree_positioning() 在整树定位完成后统一处理
                       （tree_align 依赖树内的子孙元素）
            'exempt' — 永久豁免：不夹持、后续也不补做。矩形按设计可越出
                       安全区绘制（STYLE_GUIDE §padding 的既定豁免）

        Raises:
            ValueError: position/alignment/relative_position/cross_alignment
            值非法或组合非法，或相对定位目标不可解析时抛出。
        """
        # 相对节点必须具有可解析的 relative_to；不得静默退回绝对定位。
        if config.get('relative_to'):
            return self._calculate_relative(
                element_width, element_height, config, padding_mode)

        # 绝对定位只走唯一的新算法。
        return self._calculate_absolute(
            element_width, element_height, config, padding_mode)

    # ── 绝对定位：photo ref → element anchor → element box ──

    def _resolve_photo_reference_point(self, position: str) -> Tuple[int, int]:
        """
        position 的第一步：从照片九点中选择参考点 (px, py)。

        输入只有照片几何（original_bounds）和 position，禁止接收元素宽高。
        参考点来自 __init__ 的一次性派生表（审计 Q10），诊断日志与实际
        定位取同一值。center 始终基于原照片边界（original_bounds），不受
        非对称 expand_canvas 造成的画布中心偏移影响。
        """
        return self._photo_ref_points[position]

    def _resolve_element_anchor(self, config: Dict) -> Tuple[int, int]:
        """
        position 的第二步：在照片参考点上应用 margin/placement，得到元素锚点。

        输入只有照片几何、position、placement 和 margin，禁止接收元素宽高——
        元素锚点不得因元素宽高不同而改变。margin 的职责到此结束；
        后续 alignment 不能再次读取或解释 margin。
        照片边界坐标取自共享派生（审计 Q10），不重新解包 original_bounds。

        placement 只决定照片边界主轴的内外方向：
        - 顶部/底部三点沿上/下主轴内外平移；
        - center-left / center-right 沿水平主轴内外平移；
        - center 无内外之分，placement 对其无意义（若同时设置则仅忽略，不报错）。
        """
        position = self._validate_position(config.get('position'))
        placement = config.get('placement', 'outside')
        margins = self._resolve_margins(config)
        mt = margins['top']
        mb = margins['bottom']
        ml = margins['left']
        mr = margins['right']

        L, T, R, B, CX, CY = self._photo_edges

        inside = (placement == 'inside')

        # 垂直主轴：顶部三点向下（inside）/向上（outside）；
        # 底部三点向上（inside）/向下（outside）；
        # 左右中点与 center 垂直居中于照片，只受上下 margin 差影响。
        if position.startswith('top-'):
            ay = T + mt if inside else T - mt
        elif position.startswith('bottom-'):
            ay = B - mb if inside else B + mb
        else:
            # center-left / center-right / center
            ay = CY + mt - mb

        # 水平位置：角点与左右中点贴所在边内侧 margin；中点类按左右 margin 差偏移。
        if position.endswith('-left'):
            ax = L + ml
            # center-left 的 outside 沿水平主轴向外
            if position == 'center-left' and not inside:
                ax = L - ml
        elif position.endswith('-right'):
            ax = R - mr
            # center-right 的 outside 沿水平主轴向外
            if position == 'center-right' and not inside:
                ax = R + mr
        else:
            # *-center 与 center：按左右 margin 差偏移
            ax = CX + ml - mr

        return ax, ay

    def _resolve_alignment_offset(
        self, alignment: str, element_width: int, element_height: int
    ) -> Tuple[int, int]:
        """
        alignment 的唯一职责：根据元素布局盒尺寸计算对齐点相对左上角的偏移。

        输入只有 alignment 和元素宽高，禁止读取照片边界、position、
        placement 或 margin。中心点一律使用整数除法 // 2（奇数尺寸向左/
        上取整），几何体系全模块统一，不与 round() 混用。
        """
        self._validate_alignment(alignment)

        ew, eh = element_width, element_height
        if alignment == 'top-left':
            dx, dy = 0, 0
        elif alignment == 'top-center':
            dx, dy = ew // 2, 0
        elif alignment == 'top-right':
            dx, dy = ew, 0
        elif alignment == 'center-left':
            dx, dy = 0, eh // 2
        elif alignment == 'center':
            dx, dy = ew // 2, eh // 2
        elif alignment == 'center-right':
            dx, dy = ew, eh // 2
        elif alignment == 'bottom-left':
            dx, dy = 0, eh
        elif alignment == 'bottom-center':
            dx, dy = ew // 2, eh
        else:  # 'bottom-right'
            dx, dy = ew, eh

        return dx, dy

    def _place_element_box(
        self, element_width: int, element_height: int, config: Dict
    ) -> Tuple[int, int]:
        """
        绝对定位第三步：将元素布局盒的 alignment 对齐点放到元素锚点上，
        返回布局盒 raw 左上角坐标（尚未做 padding 夹持）。
        """
        ax, ay = self._resolve_element_anchor(config)
        dx, dy = self._resolve_alignment_offset(
            config.get('alignment'), element_width, element_height)
        return ax - dx, ay - dy

    def _clamp_box_to_padding(
        self, x: int, y: int, element_width: int, element_height: int
    ) -> Tuple[int, int, int, int]:
        """
        集中执行 padding 安全区域夹持。

        返回 (final_x, final_y, delta_x, delta_y)，delta 为实际修正量
        （0 表示未修正）。padding 只作用于 raw 坐标之后，不改变锚点定义。
        """
        pad_left, pad_top, pad_right, pad_bottom = self.padding_bounds
        final_x = max(pad_left, min(x, pad_right - element_width))
        final_y = max(pad_top, min(y, pad_bottom - element_height))
        return final_x, final_y, final_x - x, final_y - y

    def get_absolute_layout_info(
        self, element_width: int, element_height: int, config: Dict
    ) -> Dict:
        """
        绝对定位几何诊断信息（只读，不改变任何状态）。

        供渲染器输出定位日志使用：照片参考点、元素锚点、alignment 偏移、
        raw box。final box 与 clamp delta 由调用方对比 raw box 得到。
        """
        position = self._validate_position(config.get('position'))
        photo_ref = self._resolve_photo_reference_point(position)
        anchor = self._resolve_element_anchor(config)
        offset = self._resolve_alignment_offset(
            config.get('alignment'), element_width, element_height)
        raw_x, raw_y = anchor[0] - offset[0], anchor[1] - offset[1]
        return {
            'position': position,
            'placement': config.get('placement', 'outside'),
            'alignment': config.get('alignment'),
            'photo_ref': photo_ref,
            'anchor': anchor,
            'offset': offset,
            'raw': (raw_x, raw_y),
        }

    def _calculate_absolute(
        self,
        element_width: int,
        element_height: int,
        config: Dict,
        padding_mode: str = 'clamp',
    ) -> Tuple[int, int]:
        """唯一的绝对定位入口：统一盒定位 → 集中 padding 夹持"""
        raw_x, raw_y = self._place_element_box(
            element_width, element_height, config)

        x, y = raw_x, raw_y
        delta_x = delta_y = 0
        if padding_mode == 'clamp':
            x, y, delta_x, delta_y = self._clamp_box_to_padding(
                raw_x, raw_y, element_width, element_height)
            if delta_x != 0 or delta_y != 0:
                # padding 造成位置修正时记录 DEBUG（只在修正发生时输出，
                # 避免每个元素刷屏；详细几何见渲染器的 [Layout] 日志）
                logger.debug(
                    f"[Layout] padding clamp: raw=({raw_x},{raw_y}) "
                    f"final=({x},{y}) delta=({delta_x},{delta_y}) "
                    f"box={element_width}x{element_height}")

        return x, y

    # ── margin 解析（position 阶段的输入之一） ───────────────

    def _resolve_margins(self, config: Dict) -> Dict[str, int]:
        reference_side = self.reference_side

        def margin_value_to_px(value):
            # margin 的单位语义与 padding 不同（审计 Q13）：
            # 浮点 = 参照边比例，整数 = 绝对像素（STYLE_GUIDE §定位）。
            # 两套换算保持可区分的命名，不得合并为同一 ratio_to_px。
            # 调用方已排除 None，不再保留 None 分支。
            if isinstance(value, float):
                return int(reference_side * value)
            return int(value)

        # 统一 margin 作为初始值（向后兼容），未设置时默认为 0
        unified = config.get('margin', None)
        if unified is not None:
            base = margin_value_to_px(unified)
        else:
            base = 0

        result = {'top': base, 'bottom': base, 'left': base, 'right': base}

        # 逐方向覆盖：显式定义的独立 margin 值覆盖对应方向
        for key in ('top', 'bottom', 'left', 'right'):
            val = config.get(f'margin_{key}', None)
            if val is not None:
                result[key] = margin_value_to_px(val)

        return result

    # ── 相对定位 ────────────────────────────────────────────

    def _validate_cross_alignment(
        self, relative_position: str, cross_alignment: str
    ) -> str:
        """
        校验 cross_alignment 与 relative_position 的轴向匹配：
        above/below 只允许 left/center/right；
        left-of/right-of 只允许 top/center/bottom。
        """
        if relative_position in ('above', 'below'):
            legal = HORIZONTAL_CROSS_ALIGNMENTS
        else:  # left-of / right-of（relative_position 本身已先行校验）
            legal = VERTICAL_CROSS_ALIGNMENTS
        if cross_alignment not in legal:
            raise ValueError(
                f"cross_alignment 值非法: {cross_alignment!r} 与 "
                f"relative_position={relative_position!r} 轴向不匹配；"
                f"合法值为 {sorted(legal)}")
        return cross_alignment

    def _shift_dependents(self, name: str, shift_x: int, shift_y: int,
                          _chain=None):
        # _chain 记录递归路径：依赖图成环时受控报错而非无限递归
        # （审计 Q14-12；外部调用方不传 _chain，行为不变）
        if _chain is None:
            _chain = []
        if name in _chain:
            cycle = _chain[_chain.index(name):] + [name]
            raise ValueError(
                f"依赖图存在环: {' → '.join(cycle)}；组合盒平移中止")
        _chain.append(name)
        if name not in self._dependents:
            return
        for dep_name in self._dependents[name]:
            if dep_name in self.positions:
                self.positions[dep_name]['x'] += shift_x
                self.positions[dep_name]['y'] += shift_y
                self._shift_dependents(dep_name, shift_x, shift_y, _chain)

    def _calculate_relative(
        self,
        element_width: int,
        element_height: int,
        config: Dict,
        padding_mode: str = 'clamp',
    ) -> Tuple[int, int]:
        """
        相对定位：以参考元素布局盒为基准，沿 relative_position 方向排列，
        cross_alignment 决定交叉轴对齐。

        只读取 cross_alignment 字段，绝不读取绝对定位的九点 alignment；
        缺失字段、未知枚举、轴向不匹配、参考目标不可解析均直接抛出
        配置错误，不再退回绝对定位。
        """
        relative_to = config.get('relative_to')
        relative_position = config.get('relative_position')
        cross_alignment = config.get('cross_alignment')
        relative_margin = config.get('relative_margin', 0.01)
        offset_x_ratio = config.get('offset_x_ratio', 0.0)
        offset_y_ratio = config.get('offset_y_ratio', 0.0)

        # 显式字段校验：缺失即配置错误（正式校验在 StyleManager，这里兜底）
        if not relative_position:
            raise ValueError(
                f"相对定位节点缺少 relative_position 字段；"
                f"合法值为 {sorted(RELATIVE_POSITIONS)}")
        if relative_position not in RELATIVE_POSITIONS:
            raise ValueError(
                f"relative_position 值非法: {relative_position!r}；"
                f"合法值为 {sorted(RELATIVE_POSITIONS)}"
                f"（旧值 after/before 已删除，请改用 below/above）")
        if not cross_alignment:
            raise ValueError(
                f"相对定位节点缺少 cross_alignment 字段"
                f"（relative_position={relative_position!r}）"
                f"——相对定位不再读取绝对定位的 alignment 字段")
        self._validate_cross_alignment(relative_position, cross_alignment)

        relative_margin_px = int(self.reference_side * relative_margin)

        # 查找唯一入口（审计 Q11）：同时确定真实注册表 key，
        # 组合盒平移不再重复实现一遍模糊查找
        found = self._lookup_position(relative_to)
        if found is None:
            raise ValueError(
                f"relative_to 目标不可解析: {relative_to!r}"
                f"（目标不存在或尚未完成定位，请检查元素依赖顺序）")
        resolved_key, (tx, ty, tw, th) = found

        # 注册到 positions 的 y = 包围盒顶（文字和非文字统一）
        # 因此 ty = 参考包围盒顶，ty + th = 参考包围盒底 = 参考视觉底部
        if relative_position in ('below', 'above'):
            # 垂直排列：交叉轴为水平，在参考元素宽度内对齐左缘/中心/右缘
            if relative_position == 'below':
                # 当前包围盒顶 y 在参考包围盒底 + margin 处
                y = ty + th + relative_margin_px
            else:
                y = ty - element_height - relative_margin_px
            if cross_alignment == 'left':
                x = tx
            elif cross_alignment == 'right':
                x = tx + tw - element_width
            else:  # 'center'
                x = tx + (tw - element_width) // 2
        else:  # left-of / right-of
            # 水平排列：交叉轴为垂直，在参考元素高度内对齐顶缘/中心/底缘
            if cross_alignment == 'top':
                y = ty
            elif cross_alignment == 'bottom':
                y = ty + th - element_height
            else:  # 'center'
                y = ty + (th - element_height) // 2
            if relative_position == 'right-of':
                x = tx + tw + relative_margin_px
            else:  # 'left-of'
                x = tx - element_width - relative_margin_px

        offset_x = int(self.reference_side * offset_x_ratio)
        offset_y = int(self.reference_side * offset_y_ratio)
        x += offset_x
        y += offset_y

        # 组合盒约束：将参考元素、当前元素、以及所有已注册的从属元素当作整体，
        # 整体平移确保不超出 padding 安全区域
        pad_left, pad_top, pad_right, pad_bottom = self.padding_bounds

        group_left = min(tx, x)
        group_top = min(ty, y)
        group_right = max(tx + tw, x + element_width)
        group_bottom = max(ty + th, y + element_height)

        # 扩展组合盒以包含所有已注册的从属元素
        for dep_name in self._dependents.get(relative_to, []):
            dep_bounds = self.get_element_bounds(dep_name)
            if dep_bounds:
                dx, dy, dw, dh = dep_bounds
                group_left = min(group_left, dx)
                group_top = min(group_top, dy)
                group_right = max(group_right, dx + dw)
                group_bottom = max(group_bottom, dy + dh)

        shift_x = 0
        shift_y = 0
        if padding_mode == 'clamp':
            if group_left < pad_left:
                shift_x = pad_left - group_left
            elif group_right > pad_right:
                shift_x = pad_right - group_right
            if group_top < pad_top:
                shift_y = pad_top - group_top
            elif group_bottom > pad_bottom:
                shift_y = pad_bottom - group_bottom

        if shift_x != 0 or shift_y != 0:
            # 真实 key 已由查找入口确定（审计 Q11）
            ref_key = resolved_key
            if ref_key in self.positions:
                logger.debug(
                    f"[Relative] relative_to={relative_to!r} "
                    f"direction={relative_position} cross={cross_alignment} "
                    f"组合盒溢出平移 shift=({shift_x},{shift_y})")
                self.positions[ref_key]['x'] += shift_x
                self.positions[ref_key]['y'] += shift_y
                self._shift_dependents(ref_key, shift_x, shift_y)
            x += shift_x
            y += shift_y

        if padding_mode == 'clamp':
            # 与普通盒共用同一夹持公式（审计 Q12：相同的策略不再各写一份；
            # 超大盒树的左/右优先级差异属未定契约，此处不涉及）
            x, y, _, _ = self._clamp_box_to_padding(
                x, y, element_width, element_height)

        return x, y

    # ── tree_align 组合树定位 ────────────────────────────────

    def _collect_tree_members(self, root_name: str, members: set, _chain=None):
        """
        递归收集以 root_name 为根的依赖树中所有元素名称

        _chain 记录递归路径：依赖图成环时受控报错而非无限递归
        （审计 Q14-12；外部调用方不传 _chain，行为不变）。
        """
        if _chain is None:
            _chain = []
        if root_name in _chain:
            cycle = _chain[_chain.index(root_name):] + [root_name]
            raise ValueError(
                f"依赖图存在环: {' → '.join(cycle)}；树成员收集中止")
        _chain.append(root_name)
        members.add(root_name)
        for dep_name in self._dependents.get(root_name, []):
            self._collect_tree_members(dep_name, members, _chain)

    def _compute_visual_bounds(self, member_names):
        """
        根据 positions 注册表计算一组元素的包围盒
        所有元素统一使用 (x, y, width, height) 中的 y=包围盒顶、y+h=包围盒底
        """
        tree_left = float('inf')
        tree_top = float('inf')
        tree_right = float('-inf')
        tree_bottom = float('-inf')

        for member_name in member_names:
            mpos = self.positions.get(member_name)
            if not mpos:
                continue
            mx, my = mpos['x'], mpos['y']
            mw, mh = mpos['width'], mpos['height']

            tree_left = min(tree_left, mx)
            tree_top = min(tree_top, my)
            tree_right = max(tree_right, mx + mw)
            tree_bottom = max(tree_bottom, my + mh)

        if tree_left == float('inf'):
            return None
        return tree_left, tree_top, tree_right, tree_bottom

    def _shift_tree_members(self, tree_members: set, shift_x: int, shift_y: int):
        """整树统一平移：保持全部父子相对位置不变"""
        for member_name in tree_members:
            mpos = self.positions.get(member_name)
            if mpos:
                mpos['x'] += shift_x
                mpos['y'] += shift_y

    def apply_tree_positioning(self, all_positions: dict):
        """
        tree_align 组合树定位（唯一算法：整树包围盒 = 普通盒子）

        将每棵依赖树（根 + 其 relative_to 子孙）的视觉包围盒当作一个
        普通元素盒，用根节点的 position / alignment / margin_* 走与单元素
        完全相同的 _place_element_box() 统一盒定位，再整树平移并做一次
        padding 修正。树内部成员的相对位置只做整树平移，不重排。

        调用时机：Phase 2 所有元素完成独立注册之后，Phase 3 绘制之前。
        """
        processed = set()

        for name in list(self.positions.keys()):
            cfg = all_positions.get(name, {})
            if cfg.get('relative_to'):
                continue
            if name in processed:
                continue
            # 仅处理显式声明 tree_align 的根元素，未声明的链不受影响
            if not cfg.get('tree_align'):
                continue

            # 1. 收集整棵树的所有成员（单成员树也走统一盒定位，
            #    保证与普通元素在相同配置下得到完全一致的坐标）
            tree_members = set()
            self._collect_tree_members(name, tree_members)
            processed.update(tree_members)

            # 2. 计算当前树的视觉包围盒
            bounds = self._compute_visual_bounds(tree_members)
            if bounds is None:
                continue

            tree_left, tree_top, tree_right, tree_bottom = bounds
            tree_w = tree_right - tree_left
            tree_h = tree_bottom - tree_top

            # 3. 整树包围盒作为普通盒子，用根配置走统一盒定位（raw 目标）
            target_x, target_y = self._place_element_box(tree_w, tree_h, cfg)

            # 4. 整树平移：shift = target_tree_top_left - current_tree_top_left
            shift_x = target_x - tree_left
            shift_y = target_y - tree_top
            if shift_x != 0 or shift_y != 0:
                self._shift_tree_members(tree_members, shift_x, shift_y)

            # 5. padding 约束：对整树执行一次夹持，全部成员平移相同 delta
            new_bounds = self._compute_visual_bounds(tree_members)
            if new_bounds is None:
                continue
            nl, nt, nr, nb = new_bounds

            pad_left, pad_top, pad_right, pad_bottom = self.padding_bounds
            clip_x = 0
            clip_y = 0
            if nl < pad_left:
                clip_x = pad_left - nl
            elif nr > pad_right:
                clip_x = pad_right - nr
            if nt < pad_top:
                clip_y = pad_top - nt
            elif nb > pad_bottom:
                clip_y = pad_bottom - nb

            if clip_x != 0 or clip_y != 0:
                self._shift_tree_members(tree_members, clip_x, clip_y)

            logger.debug(
                f"[TreeLayout] root={name} members={len(tree_members)} "
                f"bounds_before=({tree_left},{tree_top},{tree_w},{tree_h}) "
                f"target=({target_x},{target_y}) shift=({shift_x},{shift_y}) "
                f"clamp=({clip_x},{clip_y})")

    # ── 多行文本行内对齐 ────────────────────────────────────

    def layout_multiline_lines(
        self,
        block_x: int,
        block_y: int,
        block_w: int,
        block_h: int,
        lines: list,
        line_spacing: int,
        line_alignment: str = 'left',
    ) -> list:
        """
        计算多行文本块内每行的绘制位置。

        行内对齐只由 line_alignment（left / center / right）决定，
        与元素布局盒相对元素锚点的 alignment 完全分离：
        - 改变 line_alignment 只改变块内各行 x，不改变文本块整体位置；
        - 改变 alignment 只移动整个文本块，不改变块内各行相对位置。

        Args:
            block_x, block_y: 文本块包围盒左上角（来自 calculate_position）
            block_w: 块宽度（用于行内对齐偏移）
            block_h: 块高度（保留参数，行位置由行高与行间距递推）
            lines: 每行信息，每项含 height / width / baseline_offset
            line_spacing: 行间距（像素）
            line_alignment: 行内水平对齐 left / center / right（缺省 left）

        Returns:
            [(line_x, baseline_y), ...] 每行的绘制起始坐标
        """
        if line_alignment not in ('left', 'center', 'right'):
            raise ValueError(
                f"line_alignment 值非法: {line_alignment!r}；"
                f"合法值为 ['center', 'left', 'right']")

        # 空列表是合法的空块；调用方仍负责保留显式空行对应的行槽字典。
        if not lines:
            return []

        result = []
        line_top = block_y

        for ln in lines:
            if 'baseline_offset' not in ln:
                raise ValueError(
                    "多行定位契约错误：每个行槽都必须提供 baseline_offset")
            if line_alignment == 'right':
                line_x = block_x + (block_w - ln['width'])
            elif line_alignment == 'center':
                line_x = block_x + (block_w - ln['width']) // 2
            else:  # 'left'
                line_x = block_x
            # y 是布局盒顶；唯一基线来源是该行 Latin 参考度量产生的 offset。
            result.append((line_x, line_top + ln['baseline_offset']))
            line_top += ln['height'] + line_spacing

        return result
