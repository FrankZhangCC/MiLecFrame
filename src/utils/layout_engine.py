"""
布局引擎模块
负责画布尺寸计算、原图边界定位、元素（文字与非文字）的绝对/相对位置计算
"""
from typing import Dict, Tuple, Optional


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

        self.positions: Dict[str, dict] = {}
        self._dependents: Dict[str, list] = {}

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

        def to_px(value):
            if isinstance(value, (int, float)):
                return int(self.reference_side * float(value))
            return 0

        pad_left = to_px(padding_config.get('left', 0))
        pad_top = to_px(padding_config.get('top', 0))
        pad_right = to_px(padding_config.get('right', 0))
        pad_bottom = to_px(padding_config.get('bottom', 0))

        return (
            pad_left,
            pad_top,
            self.canvas_width - pad_right,
            self.canvas_height - pad_bottom
        )

    def register_element(self, name: str, x: int, y: int, width: int, height: int, relative_to: str = None, ascent: int = None):
        self.positions[name] = {'x': x, 'y': y, 'width': width, 'height': height, 'ascent': ascent}
        if relative_to:
            if relative_to not in self._dependents:
                self._dependents[relative_to] = []
            if name not in self._dependents[relative_to]:
                self._dependents[relative_to].append(name)

    def get_element_bounds(self, name: str) -> Optional[Tuple[int, int, int, int]]:
        if name in self.positions:
            pos = self.positions[name]
            return pos['x'], pos['y'], pos['width'], pos['height']
        for key, pos in self.positions.items():
            if key == name or key.endswith(name) or name.endswith(key):
                return pos['x'], pos['y'], pos['width'], pos['height']
        return None

    def calculate_position(
        self,
        element_width: int,
        element_height: int,
        config: Dict
    ) -> Tuple[int, int]:
        """
        计算元素的绘制坐标（统一处理文字和非文字元素）

        config 支持的键：
        - placement: 'inside' 或 'outside'（默认 'outside'），元素位于原图内部或外部
        - relative_to: 参考元素名（有此键则使用相对定位）
        - relative_position: 'after', 'before', 'below', 'above', 'right-of', 'left-of'
        - relative_margin: 间距比例
        - offset_x_ratio / offset_y_ratio: 偏移比例
        - position: 锚点位置 (如 'top-left', 'bottom-right', 'top', 'bottom', 'left', 'right', 'center' 等)
        - alignment: 元素对齐方式 (如 'left', 'center', 'right')
        - margin / margin_top / margin_bottom / margin_left / margin_right: 边距
        """
        if config.get('relative_to'):
            return self._calculate_relative(element_width, element_height, config)
        return self._calculate_absolute(element_width, element_height, config)

    def _calculate_absolute(
        self,
        element_width: int,
        element_height: int,
        config: Dict
    ) -> Tuple[int, int]:
        orig_x, orig_y, orig_w, orig_h = self.original_bounds

        margins = self._resolve_margins(config)
        placement = config.get('placement', 'outside')
        position = config.get('position', 'bottom')
        alignment = config.get('alignment', 'center')

        x, y = self._get_anchor(
            placement, position, alignment,
            orig_x, orig_y, orig_w, orig_h,
            element_width, element_height,
            margins
        )

        # padding 约束：确保最终坐标不超出安全区域（优先级高于 margin）
        pad_left, pad_top, pad_right, pad_bottom = self.padding_bounds
        x = max(pad_left, min(x, pad_right - element_width))
        y = max(pad_top, min(y, pad_bottom - element_height))

        return x, y

    def _get_anchor(
        self,
        placement: str,
        position: str,
        alignment: str,
        ox: int, oy: int, ow: int, oh: int,
        ew: int, eh: int,
        m: Dict[str, int]
    ) -> Tuple[int, int]:
        """
        根据 placement + position + alignment 计算元素坐标。

        placement: 'inside'（原图内部） | 'outside'（原图外部）
        position:  原图边界上的锚点位置（top-left / top / top-right / left / right /
                   bottom-left / bottom / bottom-right / top-center / bottom-center / center）
        alignment: 元素自身如何对齐到锚点（left / center / right）
        """
        inside = (placement == 'inside')

        # --- 上方位置 ---
        if position in ('top-left', 'tl'):
            y = oy + m['top'] if inside else oy - eh - m['top']
            x = ox + m['left']
            return x, y
        if position in ('top-right', 'tr'):
            y = oy + m['top'] if inside else oy - eh - m['top']
            x = ox + ow - ew - m['right']
            return x, y
        if position in ('top-center', 'tc'):
            y = oy + m['top'] if inside else oy - eh - m['top']
            x = ox + (ow - ew) // 2
            return x, y
        if position == 'top':
            y = oy + m['top'] if inside else oy - eh - m['top']
            x = self._align_x(alignment, ox, ow, ew, m)
            return x, y

        # --- 下方位置 ---
        if position in ('bottom-left', 'bl'):
            y = (oy + oh - eh - m['bottom']) if inside else (oy + oh + m['bottom'])
            x = ox + m['left']
            return x, y
        if position in ('bottom-right', 'br'):
            y = (oy + oh - eh - m['bottom']) if inside else (oy + oh + m['bottom'])
            x = ox + ow - ew - m['right']
            return x, y
        if position in ('bottom-center', 'bc'):
            y = (oy + oh - eh - m['bottom']) if inside else (oy + oh + m['bottom'])
            x = ox + (ow - ew) // 2
            return x, y
        if position == 'bottom':
            y = (oy + oh - eh - m['bottom']) if inside else (oy + oh + m['bottom'])
            x = self._align_x(alignment, ox, ow, ew, m)
            return x, y

        # --- 左侧 ---
        if position == 'left':
            x = ox + m['left'] if inside else ox - ew - m['right']
            y = self._align_y(alignment, oy, oh, eh, m)
            return x, y

        # --- 右侧 ---
        if position == 'right':
            x = (ox + ow - ew - m['right']) if inside else (ox + ow + m['left'])
            y = self._align_y(alignment, oy, oh, eh, m)
            return x, y

        # --- 居中（画布中心，不受 placement 影响）---
        if position == 'center':
            x = (self.canvas_width - ew) // 2
            y = (self.canvas_height - eh) // 2
            return x, y

        # --- 默认：外部下方居中 ---
        return ox + (ow - ew) // 2, oy + oh + m['bottom']

    def _align_x(
        self,
        alignment: str,
        ox: int, ow: int, ew: int,
        m: Dict[str, int]
    ) -> int:
        if alignment in ('left', 'top-left', 'bottom-left'):
            return ox + m['left']
        if alignment in ('right', 'top-right', 'bottom-right'):
            return ox + ow - ew - m['right']
        return ox + (ow - ew) // 2

    def _align_y(
        self,
        alignment: str,
        oy: int, oh: int, eh: int,
        m: Dict[str, int]
    ) -> int:
        if alignment in ('top', 'top-left', 'top-right'):
            return oy + m['top']
        if alignment in ('bottom', 'bottom-left', 'bottom-right'):
            return oy + oh - eh - m['bottom']
        return oy + (oh - eh) // 2

    def _resolve_margins(self, config: Dict) -> Dict[str, int]:
        reference_side = self.reference_side

        def to_px(value):
            if isinstance(value, float):
                return int(reference_side * value)
            return int(value) if value is not None else None

        # 统一 margin 作为初始值（向后兼容），未设置时默认为 0
        unified = config.get('margin', None)
        if unified is not None:
            base = to_px(unified)
            base = base if base is not None else 0
        else:
            base = 0

        result = {'top': base, 'bottom': base, 'left': base, 'right': base}

        # 逐方向覆盖：显式定义的独立 margin 值覆盖对应方向
        for key in ('top', 'bottom', 'left', 'right'):
            val = config.get(f'margin_{key}', None)
            if val is not None:
                px = to_px(val)
                if px is not None:
                    result[key] = px

        return result

    def _shift_dependents(self, name: str, shift_x: int, shift_y: int):
        if name not in self._dependents:
            return
        for dep_name in self._dependents[name]:
            if dep_name in self.positions:
                self.positions[dep_name]['x'] += shift_x
                self.positions[dep_name]['y'] += shift_y
                self._shift_dependents(dep_name, shift_x, shift_y)

    def _calculate_relative(
        self,
        element_width: int,
        element_height: int,
        config: Dict
    ) -> Tuple[int, int]:
        relative_to = config.get('relative_to')
        relative_position = config.get('relative_position', 'after')
        relative_margin = config.get('relative_margin', 0.01)
        offset_x_ratio = config.get('offset_x_ratio', 0.0)
        offset_y_ratio = config.get('offset_y_ratio', 0.0)
        alignment = config.get('alignment', 'center')

        relative_margin_px = int(self.reference_side * relative_margin)

        target_coords = self.get_element_bounds(relative_to)
        if target_coords is None:
            return self._calculate_absolute(element_width, element_height, config)

        tx, ty, tw, th = target_coords

        # 获取参考元素的 ascent，用于校正基线偏移
        # 文字元素注册时做了 y -= descent，因此 registry 中的 ty = 基线 y
        # 而 ty + th = 基线 + (ascent + descent) ≠ 视觉底部
        # 视觉底部 = ty + (th - ascent) = ty + descent
        # 视觉顶部 = ty - ascent
        ref_data = self.positions.get(relative_to, {})
        ref_ascent = ref_data.get('ascent')

        if ref_ascent is not None and ref_ascent > 0:
            # 文字元素：注册的 ty 是基线 y
            ref_visual_top = ty - ref_ascent
            ref_visual_bottom = ty + (th - ref_ascent)
        else:
            # 非文字元素（Logo 等）：注册的 ty 是包围盒左上角
            ref_visual_top = ty
            ref_visual_bottom = ty + th

        if relative_position in ('after', 'below'):
            # 元素位于参考元素下方
            # 元素包围盒顶部 y_calc 位于 ref_visual_bottom + element_height + margin 处
            # 这样渲染器做 descent 偏移后，元素的视觉顶部恰好位于参考元素视觉底部 + margin
            y = ref_visual_bottom + element_height + relative_margin_px
            x = self._align_x(alignment, tx, tw, element_width, {'left': 0, 'right': 0})
        elif relative_position in ('before', 'above'):
            # 元素位于参考元素上方
            # 元素包围盒顶部 y_calc 位于 ref_visual_top - margin 处
            # 渲染器做 descent 偏移后，元素视觉底部恰好位于参考元素视觉顶部 - margin
            y = ref_visual_top - element_height - relative_margin_px
            x = self._align_x(alignment, tx, tw, element_width, {'left': 0, 'right': 0})
        elif relative_position == 'right-of':
            x = tx + tw + relative_margin_px
            if alignment in ('bottom', 'bottom-left', 'bottom-right'):
                # 元素视觉底部对齐参考元素视觉底部
                y = ref_visual_bottom
            elif alignment in ('top', 'top-left', 'top-right'):
                # 元素视觉顶部对齐参考元素视觉顶部
                y = ref_visual_top + element_height
            else:
                # 垂直居中
                y = (ref_visual_top + ref_visual_bottom + element_height) // 2
        elif relative_position == 'left-of':
            x = tx - element_width - relative_margin_px
            if alignment in ('bottom', 'bottom-left', 'bottom-right'):
                y = ref_visual_bottom
            elif alignment in ('top', 'top-left', 'top-right'):
                y = ref_visual_top + element_height
            else:
                y = (ref_visual_top + ref_visual_bottom + element_height) // 2
        else:
            return self._calculate_absolute(element_width, element_height, config)

        offset_x = int(self.reference_side * offset_x_ratio)
        offset_y = int(self.reference_side * offset_y_ratio)
        x += offset_x
        y += offset_y

        # 组合盒约束：将参考元素、当前元素、以及所有已注册的从属元素当作整体，
        # 整体平移确保不超出 padding 安全区域
        # padding 优先级高于 margin：margin 参与位置计算，但最终结果受 padding 截断
        # 使用视觉边界参与组合盒计算，与对齐计算保持一致
        pad_left, pad_top, pad_right, pad_bottom = self.padding_bounds

        group_left = min(tx, x)
        group_top = min(ref_visual_top, y)
        group_right = max(tx + tw, x + element_width)
        group_bottom = max(ref_visual_bottom, y + element_height)

        # 扩展组合盒以包含所有已注册的从属元素（支持多个元素 relative_to 同一参考元素）
        for dep_name in self._dependents.get(relative_to, []):
            dep_bounds = self.get_element_bounds(dep_name)
            if dep_bounds:
                dx, dy, dw, dh = dep_bounds
                dep_ascent = self.positions.get(dep_name, {}).get('ascent')
                if dep_ascent is not None and dep_ascent > 0:
                    dep_visual_top = dy - dep_ascent
                    dep_visual_bottom = dy + (dh - dep_ascent)
                else:
                    dep_visual_top = dy
                    dep_visual_bottom = dy + dh
                group_left = min(group_left, dx)
                group_top = min(group_top, dep_visual_top)
                group_right = max(group_right, dx + dw)
                group_bottom = max(group_bottom, dep_visual_bottom)

        shift_x = 0
        shift_y = 0
        if group_left < pad_left:
            shift_x = pad_left - group_left
        elif group_right > pad_right:
            shift_x = pad_right - group_right
        if group_top < pad_top:
            shift_y = pad_top - group_top
        elif group_bottom > pad_bottom:
            shift_y = pad_bottom - group_bottom

        if shift_x != 0 or shift_y != 0:
            ref_key = relative_to
            if ref_key not in self.positions:
                for key in self.positions:
                    if key.endswith(relative_to) or relative_to.endswith(key):
                        ref_key = key
                        break
            if ref_key in self.positions:
                self.positions[ref_key]['x'] += shift_x
                self.positions[ref_key]['y'] += shift_y
                self._shift_dependents(ref_key, shift_x, shift_y)
            x += shift_x
            y += shift_y

        x = max(pad_left, min(x, pad_right - element_width))
        y = max(pad_top, min(y, pad_bottom - element_height))

        return x, y
