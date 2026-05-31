# Copyright (c) 2026 FrankZhangCC
# MIT License - see LICENSE file for details

"""
文字排版模块
负责三源文本（info_position / defined_texts / custom_text）的
测量、定位坐标计算和绘制。
"""
import logging
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
        if dark_key not in colors_config or light_key not in colors_config:
            return None
        is_dark_bg = BackgroundFillManager.is_dark_bg(bg_fill_type)
        custom_color = colors_config[dark_key] if is_dark_bg else colors_config[light_key]
        return self._parse_color_value(custom_color)

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
        font_size_config = fonts.get('sizes', {})
        default_size_ratio = fonts.get('size_ratio', 0.02)
        default_line_spacing_ratio = fonts.get('line_spacing_ratio', 0.005)

        for text_type, text in text_elements:
            text_config = all_positions.get(text_type, {})
            text_specific_size_ratio = font_size_config.get(text_type, default_size_ratio)
            text_color = self._determine_text_color(bg_fill_type, colors, text_type)
            line_spacing_ratio = text_config.get('line_spacing_ratio', default_line_spacing_ratio)
            line_spacing_px = int(reference_side * line_spacing_ratio)

            if '\n' in text:
                # ── 多行文本 ──
                lines = text.split('\n')
                line_infos = []
                total_width = 0
                total_height = 0

                for line_text in lines:
                    if not line_text:
                        total_height += line_spacing_px
                        continue

                    segments = FontManager.split_mixed_text(line_text)

                    if len(segments) <= 1:
                        font = self.font_manager.load_font(
                            fonts, original_image_size, text_specific_size_ratio, line_text)
                        bbox = font.getbbox(line_text)
                        line_width = bbox[2] - bbox[0]
                        ascent, descent = font.getmetrics()
                        line_height = ascent + descent

                        seg_info = [(line_text, font, line_width, ascent, descent)]
                        line_infos.append({
                            'seg_info': seg_info, 'ref_ascent': ascent,
                            'ref_descent': descent, 'width': line_width,
                            'height': line_height, 'mixed': True
                        })
                        total_width = max(total_width, line_width)
                        total_height += line_height + line_spacing_px
                    else:
                        drawn_fonts = {}

                        def _get_segment_font_line(is_cjk):
                            k = 'cjk' if is_cjk else 'latin'
                            if k not in drawn_fonts:
                                drawn_fonts[k] = self.font_manager.load_font(
                                    fonts, original_image_size, text_specific_size_ratio,
                                    force_chinese=is_cjk
                                )
                            return drawn_fonts[k]

                        seg_info = []
                        line_total_width = 0
                        for seg_text, is_cjk in segments:
                            font = _get_segment_font_line(is_cjk)
                            bbox = font.getbbox(seg_text)
                            seg_width = bbox[2] - bbox[0]
                            s_ascent, s_descent = font.getmetrics()
                            seg_info.append((seg_text, font, seg_width, s_ascent, s_descent))
                            line_total_width += seg_width

                        ref_font = drawn_fonts.get('latin') or drawn_fonts.get('cjk')
                        ref_ascent, ref_descent = ref_font.getmetrics()
                        max_ascent = max(s[3] for s in seg_info)
                        max_descent = max(s[4] for s in seg_info)
                        line_height = max_ascent + max_descent

                        logger.debug(
                            f"[测量 混排行] text_type={text_type}, line_text={line_text}, "
                            f"ref_ascent={ref_ascent}, ref_descent={ref_descent}, "
                            f"max_ascent={max_ascent}, max_descent={max_descent}, "
                            f"line_height={line_height}")
                        for i, (st, _, sw, sa, sd) in enumerate(seg_info):
                            logger.debug(f"  段{i}: text={st}, width={sw}, ascent={sa}, descent={sd}")

                        line_infos.append({
                            'seg_info': seg_info, 'ref_ascent': ref_ascent,
                            'ref_descent': ref_descent, 'width': line_total_width,
                            'height': line_height, 'mixed': True
                        })
                        total_width = max(total_width, line_total_width)
                        total_height += line_height + line_spacing_px

                if line_infos:
                    total_height -= line_spacing_px

                draw_items[text_type] = {
                    'type': 'multiline',
                    'lines': line_infos,
                    'color': text_color,
                    'width': total_width,
                    'height': total_height,
                    'line_spacing': line_spacing_px,
                }
            else:
                # ── 单行文本 ──
                segments = FontManager.split_mixed_text(text)

                if len(segments) <= 1:
                    font = self.font_manager.load_font(
                        fonts, original_image_size, text_specific_size_ratio, text)
                    bbox = font.getbbox(text)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    ascent, descent = font.getmetrics()

                    draw_items[text_type] = {
                        'text': text, 'font': font, 'color': text_color,
                        'width': text_width, 'height': ascent + descent,
                        'descent': descent, 'ascent': ascent, 'mixed': False
                    }
                else:
                    drawn_fonts = {}

                    def _get_segment_font(is_cjk):
                        key = 'cjk' if is_cjk else 'latin'
                        if key not in drawn_fonts:
                            drawn_fonts[key] = self.font_manager.load_font(
                                fonts, original_image_size, text_specific_size_ratio,
                                force_chinese=is_cjk
                            )
                        return drawn_fonts[key]

                    seg_info = []
                    total_width = 0
                    for seg_text, is_cjk in segments:
                        font = _get_segment_font(is_cjk)
                        bbox = font.getbbox(seg_text)
                        seg_width = bbox[2] - bbox[0]
                        ascent, descent = font.getmetrics()
                        seg_info.append((seg_text, font, seg_width, ascent, descent))
                        total_width += seg_width

                    ref_font = drawn_fonts.get('latin') or drawn_fonts.get('cjk')
                    ref_ascent, ref_descent = ref_font.getmetrics()
                    max_ascent = max(s[3] for s in seg_info)
                    max_descent = max(s[4] for s in seg_info)
                    text_height = max_ascent + max_descent

                    draw_items[text_type] = {
                        'seg_info': seg_info, 'ref_ascent': ref_ascent,
                        'ref_descent': ref_descent, 'color': text_color,
                        'width': total_width, 'height': text_height,
                        'ascent': ref_ascent, 'mixed': True
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

            logger.debug(
                f"[Pos] {name}: calc=({x}, {y}), bbox=({item['width']}x{item['height']}), "
                f"config={cfg.get('position', '?')}/{cfg.get('alignment', '?')} "
                f"marg={self.layout_engine._resolve_margins(cfg)}"
            )

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

            if item.get('type') == 'multiline':
                # 多行文本：通过 LayoutEngine 计算每行位置
                positions = self.layout_engine.layout_multiline_lines(
                    block_x=x, block_y=y, block_w=w, block_h=h,
                    lines=item['lines'],
                    line_spacing=item['line_spacing'],
                    alignment=cfg.get('alignment', 'left'),
                )
                for line_info, (line_x, baseline_y) in zip(item['lines'], positions):
                    if 'seg_info' not in line_info:
                        continue
                    seg_current_x = line_x
                    for seg_text, font, seg_width, seg_ascent, seg_descent in line_info['seg_info']:
                        seg_y = baseline_y - seg_ascent
                        draw.text((seg_current_x, seg_y), seg_text,
                                  fill=item['color'], font=font)
                        seg_current_x += seg_width
            elif not item['mixed']:
                draw.text((x, y - item['descent']), item['text'],
                          fill=item['color'], font=item['font'])
            else:
                baseline_y = y + item['ref_ascent'] - item['ref_descent']
                current_x = x
                for seg_text, font, seg_width, seg_ascent, seg_descent in item['seg_info']:
                    seg_y = baseline_y - seg_ascent
                    draw.text((current_x, seg_y), seg_text, fill=item['color'], font=font)
                    current_x += seg_width

        logger.debug("文字图层添加完成")
        return result
