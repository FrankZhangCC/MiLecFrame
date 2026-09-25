"""审计文字逻辑盒、实际墨迹、横向推进和 padding 约束。

脚本只读取生产代码与字体，输出 JSON 证据，不修改应用配置。
"""

import json
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

from src.utils.app_paths import get_app_dir, get_resource_root
from src.utils.font_manager import FontManager
from src.utils.layout_engine import LayoutEngine


def measure_run(font, text):
    """返回当前算法宽度、正确排版推进量与相对基线的墨迹边界。"""
    bbox = font.getbbox(text, anchor='ls')
    return {
        'text': text,
        'bbox_ls': list(bbox),
        'current_width': bbox[2] - bbox[0],
        'advance': font.getlength(text),
        'left_bearing': bbox[0],
        'right_overhang': bbox[2] - font.getlength(text),
    }


def measure_mixed(font_manager, fonts, size_ratio, text):
    """按生产代码逐段绘制，比较注册宽度、advance 和真实像素范围。"""
    segments = FontManager.split_mixed_text(text)
    runs = []
    current_x = 80
    baseline = 180
    image = Image.new('L', (1600, 360))
    draw = ImageDraw.Draw(image)
    for segment, is_cjk in segments:
        font = font_manager.load_font(
            fonts, (2000, 2000), size_ratio, force_chinese=is_cjk)
        bbox = font.getbbox(segment)
        width = bbox[2] - bbox[0]
        ascent, _ = font.getmetrics()
        draw.text((current_x, baseline - ascent), segment, font=font, fill=255)
        runs.append({
            'text': segment,
            'font': Path(font.path).name,
            'current_x': current_x - 80,
            'current_width': width,
            'advance': font.getlength(segment),
            'bbox': list(bbox),
        })
        current_x += width
    ink = image.getbbox()
    registered_width = current_x - 80
    return {
        'text': text,
        'runs': runs,
        'registered_width': registered_width,
        'sum_advance': sum(run['advance'] for run in runs),
        'ink_x_relative_to_origin': [ink[0] - 80, ink[2] - 80] if ink else None,
    }


def measure_vertical_box(font_manager, fonts, size_ratio, text):
    """比较稳定逻辑行盒与实际字形墨迹，量化 padding 无法覆盖的越界。"""
    reference = font_manager.load_font(
        fonts, (2000, 2000), size_ratio, force_chinese=False)
    actual = font_manager.load_font(fonts, (2000, 2000), size_ratio, text)
    ref_ascent, ref_descent = reference.getmetrics()
    actual_ascent, _ = actual.getmetrics()
    # 生产代码基线为 layout_y + A_ref - D_ref；绘制原点再减实际字体 ascent。
    baseline = ref_ascent - ref_descent
    bbox = actual.getbbox(text)
    ink_top = baseline - actual_ascent + bbox[1]
    ink_bottom = baseline - actual_ascent + bbox[3]
    height = ref_ascent + ref_descent
    return {
        'text': text,
        'font': Path(actual.path).name,
        'reference_metrics': [ref_ascent, ref_descent],
        'logical_box': [0, height],
        'baseline': baseline,
        'ink_y': [ink_top, ink_bottom],
        'top_overflow': max(0, -ink_top),
        'bottom_overflow': max(0, ink_bottom - height),
    }


def inspect_styles(root):
    """静态检查文本命名冲突、缺失引用和依赖环；不加载或改写样式。"""
    findings = []
    config_root = root / 'src' / 'frame_styles' / 'configs'
    for path in config_root.rglob('*.yaml'):
        config = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        layout = config.get('layout', {})
        sections = {
            'info_position': layout.get('info_position', {}) or {},
            'defined_texts': layout.get('defined_texts', {}) or {},
        }
        if isinstance(layout.get('custom_text'), dict) and layout['custom_text'].get('enabled'):
            sections['custom_text'] = {'custom_text': layout['custom_text']}
        owners = {}
        nodes = {}
        for section, entries in sections.items():
            if not isinstance(entries, dict):
                continue
            for name, cfg in entries.items():
                owners.setdefault(name, []).append(section)
                if isinstance(cfg, dict):
                    nodes[name] = cfg.get('relative_to')
        duplicates = {key: value for key, value in owners.items() if len(value) > 1}
        missing = {name: ref for name, ref in nodes.items() if ref and ref not in nodes and ref != 'logo'}
        cycles = []
        for start in nodes:
            seen = []
            node = start
            while node in nodes and nodes[node]:
                if node in seen:
                    cycles.append(seen[seen.index(node):] + [node])
                    break
                seen.append(node)
                node = nodes[node]
        if duplicates or missing or cycles:
            findings.append({
                'file': str(path.relative_to(root)),
                'duplicate_names': duplicates,
                'missing_references': missing,
                'cycles': cycles,
            })
    return findings


def main():
    """执行审计并保存结构化结果。"""
    root = get_resource_root()
    output = get_app_dir() / 'docs' / 'diagnostics' / 'font_baseline' / 'text_box_audit.json'
    style = yaml.safe_load((
        root / 'src/frame_styles/configs/胶片夹风格 FilmClip/default.yaml'
    ).read_text(encoding='utf-8'))
    fonts = style['fonts']
    manager = FontManager()
    result = {
        'font_runs': [],
        'italic_examples': [],
        'mixed_runs': [],
        'vertical_boxes': [],
        'segmentation_cases': {},
        'oversized_padding': {},
        'fuzzy_reference': {},
        'style_graph_findings': inspect_styles(root),
    }
    samples = ['A', 'AV', 'To', 'j', 'fj', 'AaBbCc', 'gypq', '永和九年', '，。', '   ']
    for weight in ['light', 'regular', 'medium']:
        weighted = dict(fonts)
        weighted['weight'] = weight
        for size in [12, 27, 54, 81, 100]:
            ratio = size / 2000
            for is_cjk in [False, True]:
                font = manager.load_font(
                    weighted, (2000, 2000), ratio, force_chinese=is_cjk)
                entry = {
                    'font': Path(font.path).name,
                    'size': size,
                    'runs': [measure_run(font, text) for text in samples],
                }
                result['font_runs'].append(entry)
            for text in ['j永', '永j', 'fj永和', 'A永j和', '永和 AaBbCc', 'AaBbCc永和九年']:
                entry = measure_mixed(manager, weighted, ratio, text)
                entry.update({'weight': weight, 'size': size})
                result['mixed_runs'].append(entry)
            for text in ['AaBbCc', 'gypq', '永和九年', '，。']:
                entry = measure_vertical_box(manager, weighted, ratio, text)
                entry.update({'weight': weight, 'size': size})
                result['vertical_boxes'].append(entry)

    # 样式允许任意 family/weight 文件；斜体是 bearing/overhang 缺陷的放大样本。
    for filename in ['Gotham-BookItalic.otf', 'Gotham-MediumItalic.otf']:
        font = ImageFont.truetype(str(root / 'assets' / 'fonts' / filename), 100)
        result['italic_examples'].append({
            'font': filename,
            'size': 100,
            'runs': [measure_run(font, text) for text in ['A', 'j', 'f', 'AV', 'AaBbCc']],
        })

    # 记录正则脚本分类边界：False 会走西文字体。
    for text in ['中文한글', '中文𠀀', '永\ufe00', '中文🙂']:
        result['segmentation_cases'][text] = FontManager.split_mixed_text(text)

    # 盒大于 padding 可用区时，夹持函数固定贴左/上边，但右/下仍然越界。
    engine = LayoutEngine((100, 100), {
        'expand_canvas': {'enabled': False},
        'padding': {'top': 0.1, 'right': 0.1, 'bottom': 0.1, 'left': 0.1},
    })
    x, y, _, _ = engine._clamp_box_to_padding(0, 0, 100, 100)
    left, top, right, bottom = engine.padding_bounds
    result['oversized_padding'] = {
        'padding_bounds': [left, top, right, bottom],
        'box': [x, y, 100, 100],
        'overflow_right': x + 100 - right,
        'overflow_bottom': y + 100 - bottom,
    }
    # 后缀模糊匹配会把不存在的短名称解析到另一个元素。
    engine.register_element('custom_text', 11, 22, 33, 44)
    result['fuzzy_reference'] = {
        'requested_missing_name': 'text',
        'resolved_bounds': engine.get_element_bounds('text'),
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
