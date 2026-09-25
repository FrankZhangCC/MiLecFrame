# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
文字排版模块
负责三源文本（info_position / defined_texts / custom_text）的
测量、定位坐标计算和绘制。
"""
import logging
from collections.abc import Mapping
from typing import Tuple, Dict, Optional, List

from PIL import Image, ImageDraw

from src.utils.font_manager import FontManager
from src.utils.layout_engine import LayoutEngine
from src.utils.render_context import RenderContext
from src.utils.background_fill import BackgroundFillManager

logger = logging.getLogger(__name__)


class TextRenderer:
    """文字排版器，消费 LayoutEngine 的几何服务，不关心图层合成顺序"""

    def __init__(self, font_manager: FontManager, layout_engine: LayoutEngine):
        self.font_manager = font_manager
        self.layout_engine = layout_engine

    # ── 行内对齐解析 ────────────────────────────────────────

    def _resolve_line_alignment(self, cfg: Dict) -> str:
        """
        多行文本块内部行对齐，与"布局盒相对元素锚点的 alignment"完全分离：
        只读专用字段 line_alignment，缺省为 left，禁止从元素 alignment 推断。
        单行文字不经过此方法，不受 line_alignment 影响。
        """
        return cfg.get('line_alignment', 'left')

    @staticmethod
    def _read_font_metrics(font, label: str) -> Tuple[int, int]:
        """读取可信的 Pillow 正值度量；无度量字体不能参与基线布局。"""
        try:
            ascent, descent = font.getmetrics()
            ascent, descent = int(ascent), int(descent)
        except Exception as exc:
            raise ValueError(f"{label} 字体无法提供可信的 getmetrics()") from exc
        if ascent < 0 or descent < 0 or ascent + descent <= 0:
            raise ValueError(
                f"{label} 字体返回非法度量: ascent={ascent}, descent={descent}")
        return ascent, descent

    def _measure_text_line(
        self,
        line_text: str,
        fonts_config: Dict,
        original_image_size: Tuple[int, int],
        size_ratio: float,
        latin_height: int,
        baseline_offset: int,
    ) -> Dict:
        """按既有分段和 bbox 宽度测量一行，纵向统一沿用 Latin 行盒。"""
        if not line_text:
            # 空槽仍占用一个正常 Latin 行高，但不会生成任何可绘制 run。
            return {
                'seg_info': [], 'width': 0, 'height': latin_height,
                'baseline_offset': baseline_offset,
            }

        segments = FontManager.split_mixed_text(line_text)
        if len(segments) <= 1:
            # 纯文本继续由 FontManager 按内容选择 Gotham 或 GlowSans。
            font = self.font_manager.load_font(
                fonts_config, original_image_size, size_ratio, line_text)
            bbox = font.getbbox(line_text)
            width = bbox[2] - bbox[0]
            ascent, descent = self._read_font_metrics(font, '字形')
            seg_info = [(line_text, font, width, ascent, descent)]
        else:
            # 混排保留原分段顺序、实际字形字体与 bbox 宽度推进规则。
            loaded_fonts = {}
            seg_info = []
            width = 0
            for segment_text, is_cjk in segments:
                font_key = 'cjk' if is_cjk else 'latin'
                if font_key not in loaded_fonts:
                    loaded_fonts[font_key] = self.font_manager.load_font(
                        fonts_config, original_image_size, size_ratio,
                        force_chinese=is_cjk)
                font = loaded_fonts[font_key]
                bbox = font.getbbox(segment_text)
                segment_width = bbox[2] - bbox[0]
                ascent, descent = self._read_font_metrics(font, '字形')
                seg_info.append((segment_text, font, segment_width, ascent, descent))
                width += segment_width

        return {
            'seg_info': seg_info, 'width': width, 'height': latin_height,
            'baseline_offset': baseline_offset,
        }

    @staticmethod
    def _draw_line_runs(draw, seg_info: List[tuple], line_x: int,
                        baseline_y: int, color: Tuple[int, int, int]) -> None:
        """以同一行基线绘制各字体 run，并保留原 bbox 宽度水平推进。"""
        current_x = line_x
        for segment_text, font, segment_width, segment_ascent, _ in seg_info:
            # Pillow 默认 la 锚点的 y 是 ascender 顶；减去字形 ascent 可让
            # Latin/CJK 两类 run 共用由 Latin 逻辑行盒确定的基线。
            draw_y = baseline_y - segment_ascent
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    f"[文字段绘制] text={segment_text!r}, "
                    f"font={getattr(font, 'path', type(font).__name__)}, "
                    f"ascent={segment_ascent}, baseline={baseline_y}, "
                    f"draw_y={draw_y}, x={current_x}, width={segment_width}")
            draw.text((current_x, draw_y), segment_text,
                      fill=color, font=font)
            current_x += segment_width


    # ── 颜色解析 ────────────────────────────────────────────

    def _parse_color_value(self, custom_color) -> Optional[Tuple[int, int, int]]:
        if not custom_color:
            return None
        if isinstance(custom_color, str) and custom_color.startswith('#'):
            return tuple(int(custom_color[i:i+2], 16) for i in (1, 3, 5))
        elif isinstance(custom_color, (tuple, list)) and len(custom_color) == 3:
            return tuple(custom_color)
        return None

    def _resolve_color_from_config(
        self, colors_config: Dict, dark_key: str, light_key: str, bg_fill_type: str
    ) -> Optional[Tuple[int, int, int]]:
        is_dark_bg = BackgroundFillManager.is_dark_bg(bg_fill_type)
        target_key = dark_key if is_dark_bg else light_key
        if target_key not in colors_config:
            return None
        return self._parse_color_value(colors_config[target_key])

    def _determine_text_color(
        self, bg_fill_type: str, colors_config: Dict, text_type: str = None
    ) -> Tuple[int, int, int]:
        if text_type:
            color = self._resolve_color_from_config(
                colors_config,
                f'custom_{text_type}_dark_color',
                f'custom_{text_type}_light_color',
                bg_fill_type
            )
            if color:
                return color

        color = self._resolve_color_from_config(
            colors_config, 'custom_text_dark_color', 'custom_text_light_color', bg_fill_type
        )
        if color:
            return color

        if BackgroundFillManager.is_dark_bg(bg_fill_type):
            return (255, 255, 255)
        else:
            return (0, 0, 0)

    # ── 拓扑排序 ────────────────────────────────────────────

    def _resolve_element_order(
        self,
        text_elements: List[Tuple[str, str]],
        info_positions: Dict
    ) -> List[str]:
        names_in_list = [t[0] for t in text_elements]
        names_set = set(names_in_list)

        dependents = {name: [] for name in names_in_list}
        in_degree = {name: 0 for name in names_in_list}

        for name in names_in_list:
            cfg = info_positions.get(name, {})
            ref = cfg.get('relative_to')
            if ref and ref in names_set:
                dependents[ref].append(name)
                in_degree[name] += 1

        queue = [name for name in names_in_list if in_degree[name] == 0]
        ordered = []

        while queue:
            name = queue.pop(0)
            ordered.append(name)
            for dep in dependents[name]:
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)

        for name in names_in_list:
            if name not in ordered:
                ordered.append(name)

        return ordered

    # ── 主入口 ──────────────────────────────────────────────

    def render(
        self,
        image: Image.Image,
        context: RenderContext,
        colors: Dict,
        fonts: Dict,
        bg_fill_type: str,
    ) -> Image.Image:
        """
        在图像上渲染所有文本元素（三源合并）。
        layout_engine 需在调用前已初始化并完成画布几何计算。
        """
        result = image.copy()
        draw = ImageDraw.Draw(result)

        layout_config = self.layout_engine.layout_config
        original_image_size = self.layout_engine.original_image_size
        reference_side = self.layout_engine.reference_side

        logger.debug("开始添加文字图层...")
        logger.debug(f"EXIF数据: {context.exif_data}")
        logger.debug(f"作者: {context.author}")
        logger.debug(f"地点: {context.location}")
        logger.debug(f"自定义文本: {context.custom_text}")
        logger.debug(f"图像尺寸: {image.size}")
        logger.debug(f"原始图像尺寸: {original_image_size}")

        # ── 构建 all_positions 注册表 & text_elements ──
        all_positions = {}
        text_elements = []

        info_positions = layout_config.get('info_position', {})
        for key in info_positions:
            cfg = info_positions.get(key, {})
            all_positions[key] = cfg
            text = context.get_text(key)
            if text:
                text_elements.append((key, text))

        defined_texts_cfg = layout_config.get('defined_texts', {})
        for key, entry in defined_texts_cfg.items():
            if not isinstance(entry, dict):
                continue
            content = entry.get('content', '')
            if content:
                layout_cfg = {k: v for k, v in entry.items() if k != 'content'}
                all_positions[key] = layout_cfg
                text_elements.append((key, content))

        custom_text_cfg = layout_config.get('custom_text', {})
        if isinstance(custom_text_cfg, dict) and custom_text_cfg.get('enabled', False):
            custom_text_content = context.get_text('custom_text')
            if custom_text_content:
                custom_text_content = custom_text_content.replace('\n', ' ')
                layout_cfg = {k: v for k, v in custom_text_cfg.items() if k != 'enabled'}
                all_positions['custom_text'] = layout_cfg
                text_elements.append(('custom_text', custom_text_content))

        if not text_elements:
            logger.debug("没有需要显示的文本信息")
            return result

        logger.debug(f"待渲染的文本元素: {[t[0] for t in text_elements]}")

        # ────────────────────────────────────────────────
        # Phase 1: 测量所有元素尺寸
        # ────────────────────────────────────────────────
        draw_items = {}
        # Latin/CJK 缺省或 YAML null 表示使用 FontManager 的默认配置；
        # 其他非映射值属于配置错误，明确指出字段且不修改调用方原配置。
        fonts_config = dict(fonts)
        for font_key in ('latin', 'cjk'):
            font_entry = fonts.get(font_key)
            if font_entry is None:
                fonts_config[font_key] = {}
            elif not isinstance(font_entry, Mapping):
                raise ValueError(f'fonts.{font_key} 必须是映射或 null')
            else:
                fonts_config[font_key] = dict(font_entry)

        font_size_config = fonts_config.get('sizes', {})
        default_size_ratio = fonts_config.get('size_ratio', 0.02)
        default_line_spacing_ratio = fonts_config.get('line_spacing_ratio', 0.005)

        for text_type, text in text_elements:
            text_config = all_positions.get(text_type, {})
            text_specific_size_ratio = font_size_config.get(text_type, default_size_ratio)
            text_color = self._determine_text_color(bg_fill_type, colors, text_type)
            line_spacing_ratio = text_config.get('line_spacing_ratio', default_line_spacing_ratio)
            line_spacing_px = int(reference_side * line_spacing_ratio)
            # 每个非空文本元素仅加载一次 Latin 定位参考字体，内容类别不会切换基线。
            latin_reference_font = self.font_manager.load_font(
                fonts_config, original_image_size, text_specific_size_ratio,
                force_chinese=False)
            latin_ascent, latin_descent = self._read_font_metrics(
                latin_reference_font, 'Latin 定位参考')
            latin_height = latin_ascent + latin_descent
            baseline_offset = latin_ascent - latin_descent

            # 无换行文本自然得到一个行槽；有换行时保留首尾与连续空槽。
            raw_lines = text.split('\n')
            line_infos = [
                self._measure_text_line(
                    line_text, fonts_config, original_image_size,
                    text_specific_size_ratio, latin_height, baseline_offset)
                for line_text in raw_lines
            ]
            total_width = max((line['width'] for line in line_infos), default=0)
            total_height = (
                len(line_infos) * latin_height
                + max(0, len(line_infos) - 1) * line_spacing_px
            )

            # DEBUG 关闭时不构造每行、每段的诊断字符串，避免正常渲染承担日志开销。
            if logger.isEnabledFor(logging.DEBUG):
                latin_path = getattr(latin_reference_font, 'path', None)
                logger.debug(
                    f"[测量文字] name={text_type}, latin_reference={latin_path or type(latin_reference_font).__name__}, "
                    f"font_size={getattr(latin_reference_font, 'size', None)}, "
                    f"A_L={latin_ascent}, D_L={latin_descent}, H_L={latin_height}, "
                    f"baseline_offset={baseline_offset}, line_slots={len(line_infos)}, "
                    f"line_spacing={line_spacing_px}, box={total_width}x{total_height}")
                for line_index, line_info in enumerate(line_infos):
                    logger.debug(
                        f"  行槽{line_index}: text={raw_lines[line_index]!r}, "
                        f"width={line_info['width']}, height={line_info['height']}, "
                        f"baseline_offset={line_info['baseline_offset']}, "
                        f"runs={len(line_info['seg_info'])}")
                    for run_index, (run_text, run_font, run_width, run_ascent, run_descent) in enumerate(
                            line_info['seg_info']):
                        logger.debug(
                            f"    段{run_index}: text={run_text!r}, "
                            f"font={getattr(run_font, 'path', type(run_font).__name__)}, "
                            f"width={run_width}, ascent={run_ascent}, descent={run_descent}")

            if len(line_infos) > 1:
                draw_items[text_type] = {
                    'type': 'multiline', 'lines': line_infos,
                    'color': text_color, 'width': total_width,
                    'height': total_height, 'line_spacing': line_spacing_px,
                    'latin_height': latin_height,
                    'baseline_offset': baseline_offset,
                }
            else:
                # 单行 item 沿用同一 line_info 契约；不会再保存旧 descent/ref_ascent。
                draw_items[text_type] = {
                    'type': 'single', 'seg_info': line_infos[0]['seg_info'],
                    'color': text_color, 'width': total_width,
                    'height': total_height,
                    'baseline_offset': baseline_offset,
                    'latin_height': latin_height,
                }

        # ────────────────────────────────────────────────
        # Phase 2: 拓扑排序 + 定位 + 注册
        # ────────────────────────────────────────────────
        for name in draw_items:
            cfg = all_positions.get(name, {})
            ref = cfg.get('relative_to')
            if ref and ref not in draw_items and ref in all_positions:
                ref_cfg = all_positions[ref]
                if not ref_cfg.get('relative_to'):
                    rx, ry = self.layout_engine.calculate_position(0, 0, ref_cfg)
                    self.layout_engine.register_element(ref, rx, ry, 0, 0, ascent=0)

        ordered_names = self._resolve_element_order(text_elements, all_positions)

        for name in ordered_names:
            item = draw_items[name]
            cfg = all_positions.get(name, {})

            defer_pad = False
            if cfg.get('relative_to'):
                walk = name
                while walk:
                    wc = all_positions.get(walk, {})
                    wp = wc.get('relative_to')
                    if wp:
                        walk = wp
                    else:
                        if wc.get('tree_align'):
                            defer_pad = True
                        break

            x, y = self.layout_engine.calculate_position(
                item['width'], item['height'], cfg, defer_padding=defer_pad)

            if cfg.get('relative_to'):
                # 相对定位日志：参考元素、方向、交叉轴对齐与最终坐标
                logger.debug(
                    f"[Relative] name={name} relative_to={cfg.get('relative_to')} "
                    f"direction={cfg.get('relative_position')} "
                    f"cross={cfg.get('cross_alignment')} "
                    f"box=({item['width']}x{item['height']}) final=({x},{y})")
            else:
                # 绝对定位日志：照片参考点 → 元素锚点 → alignment 偏移 →
                # raw box → final box → clamp delta（完整几何链路各一值）
                info = self.layout_engine.get_absolute_layout_info(
                    item['width'], item['height'], cfg)
                raw_x, raw_y = info['raw']
                logger.debug(
                    f"[Layout] name={name} position={info['position']} "
                    f"placement={info['placement']} alignment={info['alignment']} "
                    f"photo_ref={info['photo_ref']} anchor={info['anchor']} "
                    f"self={info['offset']} "
                    f"raw=({raw_x},{raw_y},{item['width']},{item['height']}) "
                    f"final=({x},{y}) clamp=({x - raw_x},{y - raw_y})")

            self.layout_engine.register_element(
                name, x, y, item['width'], item['height'], cfg.get('relative_to'))

        # Phase 2.5: 依赖树组合定位
        self.layout_engine.apply_tree_positioning(all_positions)

        # ────────────────────────────────────────────────
        # Phase 3: 绘制
        # ────────────────────────────────────────────────
        for name in ordered_names:
            bounds = self.layout_engine.get_element_bounds(name)
            if bounds is None:
                continue
            x, y, w, h = bounds

            item = draw_items[name]
            cfg = all_positions.get(name, {})

            logger.debug(
                f"[最终布局盒] name={name}, box=({x},{y},{w},{h}), "
                f"baseline_offset={item['baseline_offset']}, "
                f"baseline={y + item['baseline_offset']}")

            if item.get('type') == 'multiline':
                # 多行文本：行内对齐只读专用 line_alignment 字段，
                # 与元素布局盒相对元素锚点的 alignment 完全分离
                positions = self.layout_engine.layout_multiline_lines(
                    block_x=x, block_y=y, block_w=w, block_h=h,
                    lines=item['lines'],
                    line_spacing=item['line_spacing'],
                    line_alignment=self._resolve_line_alignment(cfg),
                )
                if len(positions) != len(item['lines']):
                    raise ValueError(
                        f"多行定位契约错误: name={name}, "
                        f"行槽={len(item['lines'])}, 位置={len(positions)}")
                for line_index, (line_info, (line_x, baseline_y)) in enumerate(
                        zip(item['lines'], positions)):
                    logger.debug(
                        f"  [行基线] name={name}, slot={line_index}, "
                        f"line_top={y + line_index * (item['latin_height'] + item['line_spacing'])}, "
                        f"baseline={baseline_y}, ink_runs={len(line_info['seg_info'])}")
                    if not line_info['seg_info']:
                        # 空槽保留行高与位置，不调用 draw.text，也不伪造墨迹边界。
                        continue
                    self._draw_line_runs(
                        draw, line_info['seg_info'], line_x, baseline_y, item['color'])
            else:
                # Phase 3 才基于树布局/夹持后的最终盒顶确定单行基线。
                baseline_y = y + item['baseline_offset']
                self._draw_line_runs(
                    draw, item['seg_info'], x, baseline_y, item['color'])

        logger.debug("文字图层添加完成")
        return result
