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
        self.original_longer_side = max(self.original_width, self.original_height)

        self.layout_config = layout_config
        self.canvas_size = self._calculate_canvas_size()
        self.canvas_width, self.canvas_height = self.canvas_size
        self.original_bounds = self._calculate_original_bounds()
        self.padding_bounds = self._calculate_padding_bounds()

        self.positions: Dict[str, dict] = {}

    def _calculate_canvas_size(self) -> Tuple[int, int]:
        expand_config = self.layout_config.get('expand_canvas', {})
        if not expand_config.get('enabled', False):
            return self.original_image_size

        top_exp = expand_config.get('top', 0)
        bottom_exp = expand_config.get('bottom', 0)
        left_exp = expand_config.get('left', 0)
        right_exp = expand_config.get('right', 0)

        new_width = self.original_width + int(self.original_longer_side * (left_exp + right_exp))
        new_height = self.original_height + int(self.original_longer_side * (top_exp + bottom_exp))

        return new_width, new_height

    def _calculate_original_bounds(self) -> Tuple[int, int, int, int]:
        expand_config = self.layout_config.get('expand_canvas', {})
        if not expand_config.get('enabled', False):
            x = (self.canvas_width - self.original_width) // 2
            y = (self.canvas_height - self.original_height) // 2
        else:
            top_exp = expand_config.get('top', 0)
            left_exp = expand_config.get('left', 0)
            x = int(self.original_longer_side * left_exp)
            y = int(self.original_longer_side * top_exp)

        return x, y, self.original_width, self.original_height

    def _calculate_padding_bounds(self) -> Tuple[int, int, int, int]:
        """
        计算叠加元素的安全区域（padding），从画布四边向内收缩。
        返回 (left_bound, top_bound, right_bound, bottom_bound)
        padding 值以 original_longer_side 比例为基准，默认为 0（即画布边界）
        """
        padding_config = self.layout_config.get('padding', {})
        if not padding_config:
            return 0, 0, self.canvas_width, self.canvas_height

        def to_px(value):
            if isinstance(value, (int, float)):
                return int(self.original_longer_side * float(value))
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

    def register_element(self, name: str, x: int, y: int, width: int, height: int):
        self.positions[name] = {'x': x, 'y': y, 'width': width, 'height': height}

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
        - relative_to: 参考元素名（有此键则使用相对定位）
        - relative_position: 'after', 'before', 'below', 'above', 'right-of', 'left-of'
        - relative_margin: 间距比例
        - offset_x_ratio / offset_y_ratio: 偏移比例
        - position: 绝对位置名 (如 'top-left', 'bottom-right', 'outside', 'inside' 等)
        - alignment: 对齐方式 (如 'left', 'center', 'right', 'top-left' 等)
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
        position = config.get('position', 'outside')
        alignment = config.get('alignment', 'center')

        x, y = self._get_anchor(
            position, alignment,
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
        position: str,
        alignment: str,
        ox: int, oy: int, ow: int, oh: int,
        ew: int, eh: int,
        m: Dict[str, int]
    ) -> Tuple[int, int]:
        """
        根据 position + alignment 计算坐标。

        position 决定主锚点（上下左右/内部/外部）
        alignment 决定垂直锚点轴的偏移（左中右/上中下）
        """
        # --- 上方位置 ---
        if position in ('top-left', 'tl'):
            return ox + m['left'], oy - eh - m['top']
        if position in ('top-right', 'tr'):
            return ox + ow - ew - m['right'], oy - eh - m['top']
        if position in ('top-center', 'tc'):
            return ox + (ow - ew) // 2, oy - eh - m['top']
        if position == 'top':
            y = oy - eh - m['top']
            x = self._align_x(alignment, ox, ow, ew, m)
            return x, y

        # --- 下方位置 ---
        if position in ('bottom-left', 'bl'):
            return ox + m['left'], oy + oh + m['bottom']
        if position in ('bottom-right', 'br'):
            return ox + ow - ew - m['right'], oy + oh + m['bottom']
        if position in ('bottom-center', 'bc'):
            return ox + (ow - ew) // 2, oy + oh + m['bottom']
        if position in ('bottom', 'outside'):
            if alignment == 'top-left':
                return ox + m['left'], oy - eh - m['top']
            y = oy + oh + m['bottom']
            x = self._align_x(alignment, ox, ow, ew, m)
            return x, y

        # --- 内部 ---
        if position == 'inside':
            if alignment == 'top-left':
                return ox + m['left'], oy + m['top']
            y = oy + oh - eh - m['bottom']
            x = self._align_x(alignment, ox, ow, ew, m)
            return x, y

        # --- 左侧 ---
        if position == 'left':
            x = ox - ew - m['right']
            y = self._align_y(alignment, oy, oh, eh, m)
            return x, y

        # --- 右侧 ---
        if position == 'right':
            x = ox + ow + m['left']
            y = self._align_y(alignment, oy, oh, eh, m)
            return x, y

        # --- 居中 ---
        if position == 'center':
            x = (self.canvas_width - ew) // 2
            y = (self.canvas_height - eh) // 2
            return x, y

        # --- 默认：下方居中 ---
        return ox + (ow - ew) // 2, oy + oh + m['bottom']

    def _align_x(
        self,
        alignment: str,
        ox: int, ow: int, ew: int,
        m: Dict[str, int]
    ) -> int:
        if alignment in ('left', 'top-left'):
            return ox + m['left']
        if alignment == 'right':
            return ox + ow - ew - m['right']
        return ox + (ow - ew) // 2

    def _align_y(
        self,
        alignment: str,
        oy: int, oh: int, eh: int,
        m: Dict[str, int]
    ) -> int:
        if alignment == 'top':
            return oy + m['top']
        if alignment == 'bottom':
            return oy + oh - eh - m['bottom']
        return oy + (oh - eh) // 2

    def _resolve_margins(self, config: Dict) -> Dict[str, int]:
        longer_side = self.original_longer_side

        def to_px(value):
            if isinstance(value, float):
                return int(longer_side * value)
            return int(value) if value is not None else None

        margin_top = config.get('margin_top', None)
        margin_bottom = config.get('margin_bottom', None)
        margin_left = config.get('margin_left', None)
        margin_right = config.get('margin_right', None)

        if margin_top is None or margin_left is None:
            margin = config.get('margin', 10)
            if isinstance(margin, float):
                margin = int(longer_side * margin)
            margin_top = margin_left = margin_bottom = margin_right = int(margin)
        else:
            margin_top = to_px(margin_top) if to_px(margin_top) is not None else 0
            margin_left = to_px(margin_left) if to_px(margin_left) is not None else 0
            margin_bottom = to_px(margin_bottom) if to_px(margin_bottom) is not None else 0
            margin_right = to_px(margin_right) if to_px(margin_right) is not None else 0

        return {
            'top': margin_top or 0,
            'bottom': margin_bottom or 0,
            'left': margin_left or 0,
            'right': margin_right or 0,
        }

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

        relative_margin_px = int(self.original_longer_side * relative_margin)

        target_coords = self.get_element_bounds(relative_to)
        if target_coords is None:
            return self._calculate_absolute(element_width, element_height, config)

        tx, ty, tw, th = target_coords

        if relative_position in ('after', 'below'):
            y = ty + th + relative_margin_px
            x = self._align_x(alignment, tx, tw, element_width, {'left': 0, 'right': 0})
        elif relative_position in ('before', 'above'):
            y = ty - element_height - relative_margin_px
            x = self._align_x(alignment, tx, tw, element_width, {'left': 0, 'right': 0})
        elif relative_position == 'right-of':
            x = tx + tw + relative_margin_px
            y = self._align_y(alignment, ty, th, element_height, {'top': 0, 'bottom': 0})
        elif relative_position == 'left-of':
            x = tx - element_width - relative_margin_px
            y = self._align_y(alignment, ty, th, element_height, {'top': 0, 'bottom': 0})
        else:
            return self._calculate_absolute(element_width, element_height, config)

        offset_x = int(self.original_longer_side * offset_x_ratio)
        offset_y = int(self.original_longer_side * offset_y_ratio)
        x += offset_x
        y += offset_y

        # 组合盒约束：将参考元素与当前元素当作整体，整体平移确保不超出 padding 安全区域
        # padding 优先级高于 margin：margin 参与位置计算，但最终结果受 padding 截断
        pad_left, pad_top, pad_right, pad_bottom = self.padding_bounds

        group_left = min(tx, x)
        group_top = min(ty, y)
        group_right = max(tx + tw, x + element_width)
        group_bottom = max(ty + th, y + element_height)

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
            x += shift_x
            y += shift_y

        x = max(pad_left, min(x, pad_right - element_width))
        y = max(pad_top, min(y, pad_bottom - element_height))

        return x, y
