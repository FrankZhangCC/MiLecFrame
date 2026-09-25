"""独立采集并比较 Latin 定位基线契约的诊断工具。

本脚本直接调用真实 TextRenderer 和 LayoutEngine；临时 hook 仅旁路记录
ImageDraw.text 的真实输入坐标，并用原始 draw 方法生成独立灰度 mask。
诊断结果只写入显式 --output 目录，不修改样式、字体或应用配置。

从项目根目录执行前应激活 venv，并将项目根加入 PYTHONPATH。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import os
import platform
import subprocess
import sys
import traceback
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest.mock import patch

import PIL
import yaml
from PIL import Image, ImageDraw, features

from src.core.text_renderer import TextRenderer
from src.frame_styles.style_manager import StyleManager
from src.utils.app_paths import get_resource_root
from src.utils.font_manager import FontManager
from src.utils.layout_engine import LayoutEngine
from src.utils.render_context import RenderContext


ROOT = get_resource_root()
STYLE_NAME = '胶片夹风格 FilmClip'
IMAGE_SIZE = (3000, 2000)
FONT_RATIOS = (0.006, 0.0135, 0.0215, 0.027, 0.0405, 0.05, 0.054)
WEIGHTS = ('light', 'regular', 'medium')
ALIGNMENTS = ('top-center', 'center', 'bottom-center')
TEXTS = {
    'latin': 'AaBbCc',
    'mixed': 'AaBbCc永和九年',
    'cjk': '永和九年',
}


def sha256_file(path: Path) -> str | None:
    """对可读文件计算稳定指纹；字体回退对象没有文件时返回 None。"""
    try:
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        return digest.hexdigest()
    except (OSError, TypeError, ValueError):
        return None


def json_write(path: Path, value: Any) -> None:
    """以 UTF-8 和稳定缩进保存诊断事实，便于人工审阅和后续 diff。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def git_text(*args: str) -> str:
    """读取当前仓库状态；诊断失败时保留错误信息而不中断采集。"""
    try:
        result = subprocess.run(
            ['git', *args], cwd=ROOT, check=True, capture_output=True,
            text=True, encoding='utf-8', errors='replace')
        return result.stdout.strip()
    except Exception as exc:  # pragma: no cover - 仅在 Git 状态异常时触发
        return f'<unavailable: {type(exc).__name__}: {exc}>'


def resolve_style() -> tuple[dict, Path]:
    """经 StyleManager 实际变体解析取得 FilmClip 配置与命中路径。"""
    manager = StyleManager()
    style_dir = next(manager._iter_style_dirs(STYLE_NAME), None)
    if style_dir is None:
        raise FileNotFoundError(f'找不到内置样式目录: {STYLE_NAME}')
    selected = manager._resolve_style_variant(style_dir, {'author': 'Baseline', 'location': 'Baseline'})
    if selected is None:
        raise FileNotFoundError(f'StyleManager 未解析出样式变体: {STYLE_NAME}')
    config = manager.get_style_config(
        STYLE_NAME, context={'author': 'Baseline', 'location': 'Baseline'})
    if not isinstance(config, dict):
        raise ValueError(f'StyleManager 无法加载有效样式: {selected}')
    return config, Path(selected).resolve()


def source_manifest(style_path: Path) -> dict:
    """在任何生产源码变更前保存提交、状态、依赖与关键输入文件指纹。"""
    source_paths = {
        'text_renderer': ROOT / 'src/core/text_renderer.py',
        'layout_engine': ROOT / 'src/utils/layout_engine.py',
        'font_manager': ROOT / 'src/utils/font_manager.py',
        'style_variant': style_path,
    }
    try:
        import PIL._imagingft as imagingft
        freetype = getattr(imagingft, 'freetype2_version', None)
    except Exception:
        freetype = features.version('freetype2')
    return {
        'commit': git_text('rev-parse', 'HEAD'),
        'branch_status': git_text('status', '--short', '--branch'),
        'python': sys.version,
        'platform': platform.platform(),
        'pillow': PIL.__version__,
        'freetype': freetype or features.version('freetype2'),
        'style_name': STYLE_NAME,
        'selected_variant': str(style_path),
        'original_image_size': list(IMAGE_SIZE),
        'source_sha256': {
            key: sha256_file(path) for key, path in source_paths.items()},
    }


def case_catalog() -> list[dict]:
    """构造固定主矩阵及边界样本；每例只改变一个待测输入维度。"""
    cases: list[dict] = []
    for ratio in FONT_RATIOS:
        for weight in WEIGHTS:
            for alignment in ALIGNMENTS:
                for text_kind, text in TEXTS.items():
                    cases.append({
                        'id': f'matrix_r{ratio:g}_{weight}_{alignment}_{text_kind}',
                        'source': 'custom_text', 'text': text,
                        'text_kind': text_kind, 'size_ratio': ratio,
                        'weight': weight, 'alignment': alignment,
                    })

    # 把 54px 三种对齐的经典样本显式标注，方便人工定位 A4 反例。
    for alignment in ALIGNMENTS:
        for text_kind, text in TEXTS.items():
            cases.append({
                'id': f'anchor54_medium_{alignment}_{text_kind}',
                'source': 'custom_text', 'text': text,
                'text_kind': text_kind, 'size_ratio': 0.027,
                'weight': 'medium', 'alignment': alignment,
                'anchor_case': True,
            })

    # 验证配置字号低于 0.006 时，FontManager 仍按 12px 下限取值。
    cases.append({
        'id': 'minimum_font_below_12px', 'source': 'custom_text',
        'text': TEXTS['mixed'], 'text_kind': 'minimum_size', 'size_ratio': 0.002,
        'weight': 'medium', 'alignment': 'center', 'minimum_size_case': True,
    })

    # 内容顺序、ASCII 空格、下行部以及中文标点都作为独立定位反例。
    for index, text in enumerate((
            '永和九年AaBbCc', ' AaBbCc永和九年', 'AaBbCc 永和九年',
            'gypq', 'gypq永和九年', 'AaBbCc永和九年，。')):
        cases.append({
            'id': f'content_edge_{index:02d}', 'source': 'custom_text',
            'text': text, 'text_kind': 'content_edge', 'size_ratio': 0.027,
            'weight': 'medium', 'alignment': 'center',
        })

    # defined_texts 是当前公开的真实多行入口；覆盖反向顺序和空行槽。
    multiline_texts = (
        'AaBbCc\n永和九年', '永和九年\nAaBbCc',
        'AaBbCc\n\nAaBbCc', '\nAaBbCc\n', '\n', '\n\n',
    )
    for line_alignment in ('left', 'center', 'right'):
        for index, text in enumerate(multiline_texts):
            cases.append({
                'id': f'multiline_{line_alignment}_{index:02d}',
                'source': 'defined_texts', 'text': text,
                'text_kind': 'multiline', 'size_ratio': 0.027,
                'weight': 'medium', 'alignment': 'top-center',
                'line_alignment': line_alignment,
            })

    # custom_text 会先把换行折叠为空格；单独记录现有入口行为。
    cases.append({
        'id': 'custom_text_newline_is_space', 'source': 'custom_text',
        'text': 'AaBbCc\n永和九年', 'text_kind': 'custom_text_newline',
        'size_ratio': 0.027, 'weight': 'medium', 'alignment': 'center',
    })

    # 相对定位及 tree_align 组合用于检查基线是否从最终布局盒读取。
    for tree_align in (False, True):
        for cross_alignment in ('top', 'center', 'bottom'):
            for text_kind, text in TEXTS.items():
                cases.append({
                    'id': f'relative_tree_{int(tree_align)}_{cross_alignment}_{text_kind}',
                    'source': 'relative', 'text': text,
                    'text_kind': text_kind, 'size_ratio': 0.027,
                    'weight': 'medium', 'alignment': 'top-center',
                    'tree_align': tree_align, 'cross_alignment': cross_alignment,
                })
    return cases


def _font_record(font) -> dict:
    """提取可核实的实际字体身份；回退对象无路径时记录对象类型。"""
    raw_path = getattr(font, 'path', None)
    try:
        path = str(Path(raw_path).resolve()) if raw_path else None
    except (OSError, TypeError, ValueError):
        path = str(raw_path) if raw_path else None
    try:
        ascent, descent = font.getmetrics()
        metrics = [int(ascent), int(descent)]
    except Exception as exc:
        metrics = {'error': f'{type(exc).__name__}: {exc}'}
    return {
        'object_type': f'{type(font).__module__}.{type(font).__qualname__}',
        'path': path,
        'sha256': sha256_file(Path(path)) if path else None,
        'size': getattr(font, 'size', None),
        'metrics': metrics,
    }


def _configure_case(base_style: dict, case: dict) -> tuple[dict, str, str]:
    """复制内存样式，仅配置目标文本和本例需要的布局属性。"""
    style = copy.deepcopy(base_style)
    layout = style['layout']
    layout['info_position'] = {}
    layout['defined_texts'] = {}
    ratio = case['size_ratio']
    style['fonts']['weight'] = case['weight']

    if case['source'] in ('custom_text', 'relative'):
        custom_cfg = dict(layout.get('custom_text', {}))
        custom_cfg.update({'enabled': True, 'alignment': case['alignment']})
        if case['source'] == 'relative':
            # 父项固定在同一锚点；tree_align 是布局树选项，不改文字样式。
            layout['defined_texts'] = {
                'baseline_parent': {
                    'content': 'ParentProbe', 'position': 'top-center',
                    'alignment': 'top-center', 'margin_top': 0.11,
                    'tree_align': case['tree_align'],
                }}
            custom_cfg.update({
                'relative_to': 'baseline_parent',
                'relative_position': 'right-of',
                'cross_alignment': case['cross_alignment'],
                'relative_margin': 0.01,
            })
        else:
            custom_cfg.pop('relative_to', None)
            custom_cfg.pop('relative_position', None)
            custom_cfg.pop('cross_alignment', None)
        layout['custom_text'] = custom_cfg
        style['fonts'].setdefault('sizes', {})['custom_text'] = ratio
        effective_text = case['text'].replace('\n', ' ')
        target_key = 'custom_text'
    elif case['source'] == 'info_position':
        custom_cfg = dict(layout.get('custom_text', {}))
        custom_cfg['enabled'] = False
        layout['custom_text'] = custom_cfg
        layout['info_position'] = {
            'author': {
                'position': 'top-center', 'alignment': case['alignment'],
                'margin_top': 0.11,
            }}
        style['fonts'].setdefault('sizes', {})['author'] = ratio
        effective_text = case['text']
        target_key = 'author'
    else:
        custom_cfg = dict(layout.get('custom_text', {}))
        custom_cfg['enabled'] = False
        layout['custom_text'] = custom_cfg
        line_cfg = {
            'content': case['text'], 'position': 'top-center',
            'alignment': 'top-center', 'margin_top': 0.11,
            'line_spacing_ratio': 0.006,
            'line_alignment': case.get('line_alignment', 'left'),
        }
        layout['defined_texts'] = {'baseline_probe': line_cfg}
        style['fonts'].setdefault('sizes', {})['baseline_probe'] = ratio
        effective_text = case['text']
        target_key = 'baseline_probe'

    # 配置健壮性补充样本通过局部样式覆盖测试缺省、null 和非法类型。
    for key, value in case.get('font_overrides', {}).items():
        if value == '__REMOVE__':
            style['fonts'].pop(key, None)
        else:
            style['fonts'][key] = value
    return style, target_key, effective_text


def render_case(base_style: dict, case: dict, output_dir: Path) -> dict:
    """真实运行 TextRenderer 并捕获每个 run 的屏幕坐标和独立 mask。"""
    style, target_key, effective_text = _configure_case(base_style, case)
    engine = LayoutEngine(IMAGE_SIZE, style['layout'])
    renderer = TextRenderer(FontManager(), engine)
    # 空槽没有 draw run，因此独立加载 Latin 参考度量；只把 null 归一为
    # 默认映射，非法值仍留给生产 TextRenderer 按字段名报告配置错误。
    reference_font_record = None
    verifier_font_config = dict(style['fonts'])
    for font_key in ('latin', 'cjk'):
        font_entry = style['fonts'].get(font_key)
        if font_entry is None:
            verifier_font_config[font_key] = {}
        elif isinstance(font_entry, Mapping):
            verifier_font_config[font_key] = dict(font_entry)
    try:
        reference_font = renderer.font_manager.load_font(
            verifier_font_config, IMAGE_SIZE, case['size_ratio'], force_chinese=False)
        reference_font_record = _font_record(reference_font)
    except Exception:
        # 非法配置的主断言来自真实 renderer.render()，此处的独立度量仅留空。
        reference_font_record = None
    canvas_size = engine.canvas_size
    actual_image = Image.new('RGB', canvas_size, 'white')
    aggregate_mask = Image.new('L', canvas_size, 0)
    original_text = ImageDraw.ImageDraw.text
    original_layout_lines = engine.layout_multiline_lines
    draw_records: list[dict] = []
    line_layout_records: list[dict] = []
    mask_dir = output_dir / 'masks' / case['id']
    mask_dir.mkdir(parents=True, exist_ok=True)

    def capture_draw(draw_obj, xy, text, *args, **kwargs):
        """先按相同参数调用原始绘制函数生成 mask，再原样绘制真实结果。"""
        font = kwargs.get('font')
        if font is None and len(args) >= 2:
            font = args[1]
        if font is None:
            raise AssertionError(f'{case["id"]}: draw.text 调用未提供可识别字体')

        mask_kwargs = dict(kwargs)
        mask_kwargs['fill'] = 255
        run_mask = Image.new('L', canvas_size, 0)
        original_text(ImageDraw.Draw(run_mask), xy, text, *args, **mask_kwargs)
        original_text(ImageDraw.Draw(aggregate_mask), xy, text, *args, **mask_kwargs)
        bbox = run_mask.getbbox()
        mask_name = None
        crop_origin = None
        if bbox is not None:
            crop_origin = [bbox[0], bbox[1]]
            mask_name = f'run_{len(draw_records):02d}.png'
            run_mask.crop(bbox).save(mask_dir / mask_name)

        ascent, descent = font.getmetrics()
        record = {
            'text': str(text),
            'xy': [int(xy[0]), int(xy[1])],
            'font': _font_record(font),
            'ascent': int(ascent), 'descent': int(descent),
            'baseline': int(xy[1] + ascent),
            'mask_bbox_half_open': list(bbox) if bbox else None,
            'mask_crop_origin': crop_origin,
            'mask_file': str(Path('masks') / case['id'] / mask_name) if mask_name else None,
        }
        draw_records.append(record)
        return original_text(draw_obj, xy, text, *args, **kwargs)

    def capture_line_layout(**kwargs):
        """旁路记录 TextRenderer 实际交给 LayoutEngine 的行槽及最终基线。"""
        line_count = len(kwargs.get('lines', []))
        positions = original_layout_lines(**kwargs)
        line_layout_records.append({
            'input_slot_count': line_count,
            'positions': [[int(x), int(y)] for x, y in positions],
        })
        return positions

    exception = None
    # patch 的上下文管理器确保异常路径也恢复 Pillow 原绘制方法。
    try:
        with patch.object(ImageDraw.ImageDraw, 'text', capture_draw), \
                patch.object(engine, 'layout_multiline_lines', capture_line_layout):
            renderer.render(
                actual_image,
                RenderContext(
                    IMAGE_SIZE,
                    exif_data={
                        'focal_length': '50', 'aperture': '2.8',
                        'shutter_speed': '1/125', 'iso': '100',
                    },
                    author=case['text'] if case['source'] == 'info_position' else 'Baseline',
                    location='Baseline',
                    custom_text=case['text']
                        if case['source'] in ('custom_text', 'relative') else None,
                ),
                style['colors'], style['fonts'], 'white')
    except Exception as exc:  # 旧实现的空行异常必须保留并继续采集
        exception = {
            'type': type(exc).__name__, 'message': str(exc),
            'traceback': traceback.format_exc(),
        }

    positions = engine.positions.get(target_key)
    box = None
    if positions is not None:
        box = {key: positions.get(key) for key in ('x', 'y', 'width', 'height')}
    else:
        # get_element_bounds 是 LayoutEngine 对外的最终布局盒接口。
        bounds = engine.get_element_bounds(target_key)
        if bounds is not None:
            box = dict(zip(('x', 'y', 'width', 'height'), bounds))

    aggregate_name = None
    aggregate_bbox = aggregate_mask.getbbox()
    if aggregate_bbox is not None:
        # 锚点案例保留整画布 mask，用于校验 crop 坐标还原没有偏差。
        if case.get('anchor_case') and case['size_ratio'] == 0.027:
            aggregate_name = str(Path('masks') / f'{case["id"]}_canvas.png')
            aggregate_mask.save(output_dir / aggregate_name)

    actual_font_fingerprints = {}
    all_font_records = [reference_font_record] if reference_font_record else []
    for record in draw_records:
        font = record['font']
        all_font_records.append(font)
    for font in all_font_records:
        key = font['path'] or font['object_type']
        actual_font_fingerprints[key] = {
            'path': font['path'], 'sha256': font['sha256'],
            'object_type': font['object_type'], 'size': font['size'],
            'metrics': font['metrics'],
        }

    actual_size = None
    if draw_records:
        sizes = sorted({record['font']['size'] for record in draw_records
                        if isinstance(record['font']['size'], int)})
        actual_size = sizes[0] if len(sizes) == 1 else sizes

    result = {
        'case_id': case['id'], 'source': case['source'],
        'original_text': case['text'], 'effective_text': effective_text,
        'text_kind': case.get('text_kind'), 'alignment': case.get('alignment'),
        'line_alignment': case.get('line_alignment'),
        'requested_size_ratio': case['size_ratio'], 'actual_font_size': actual_size,
        'weight': case['weight'], 'canvas_size': list(canvas_size),
        'latin_reference_font': reference_font_record,
        'logical_box': box, 'expected_line_slot_count': len(case['text'].split('\n'))
            if case['source'] == 'defined_texts' else 1,
        'actual_line_slot_count': line_layout_records[-1]['input_slot_count']
            if line_layout_records else 1,
        'line_layout': line_layout_records,
        'line_spacing': int(engine.reference_side * 0.006)
            if case['source'] == 'defined_texts' else None,
        'draws': draw_records, 'aggregate_mask_bbox_half_open':
            list(aggregate_bbox) if aggregate_bbox else None,
        'aggregate_mask_file': aggregate_name,
        'font_fingerprints': actual_font_fingerprints,
        'exception': exception,
    }
    json_write(output_dir / 'cases' / f'{case["id"]}.json', result)
    return result


def _safe_output(path: Path, mode: str) -> None:
    """capture/compare 不覆盖旧证据；measure 也遵守相同的可追溯约定。"""
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f'输出目录必须不存在或为空，拒绝覆盖: {path}')
    path.mkdir(parents=True, exist_ok=True)


def _case_by_id(results: list[dict]) -> dict[str, dict]:
    """把序列化结果转换为索引，并拒绝重复案例 ID。"""
    indexed = {result['case_id']: result for result in results}
    if len(indexed) != len(results):
        raise ValueError('诊断结果中存在重复 case_id')
    return indexed


def _latin_draw(case: dict) -> dict | None:
    """按原始 run 文本精确找到本任务关注的共同 ASCII 段。"""
    return next((draw for draw in case['draws'] if draw['text'] == TEXTS['latin']), None)


def _latin_containing_draw(case: dict, text: str) -> dict | None:
    """找到包含目标西文片段的 Latin run，允许同段保留 ASCII 前后空格。"""
    return next((draw for draw in case['draws'] if text in draw['text']), None)


def _text_draw(case: dict, text: str) -> dict | None:
    """按文本内容查找纯文本 run；找不到时返回 None 供失败报告使用。"""
    return next((draw for draw in case['draws'] if draw['text'] == text), None)


def _mask_pixels(output_dir: Path, record: dict) -> tuple[Image.Image, list[int]] | None:
    """加载裁剪 mask 并返回其真实画布原点，便于按原点对齐比较。"""
    if not record or not record.get('mask_file') or not record.get('mask_crop_origin'):
        return None
    path = output_dir / record['mask_file']
    if not path.is_file():
        return None
    with Image.open(path) as image:
        return image.convert('L').copy(), list(record['mask_crop_origin'])


def _normalized_mask_equal(
    output_a: Path, record_a: dict, output_b: Path, record_b: dict,
    *, require_same_y: bool = True,
) -> tuple[bool, dict]:
    """先按 x 原点归一，再核对 run mask 逐像素相同及 y 坐标一致。"""
    left = _mask_pixels(output_a, record_a)
    right = _mask_pixels(output_b, record_b)
    if left is None or right is None:
        return False, {'reason': '缺少 run mask'}
    image_a, origin_a = left
    image_b, origin_b = right
    details = {
        'left_origin': origin_a, 'right_origin': origin_b,
        'left_size': list(image_a.size), 'right_size': list(image_b.size),
        'y_delta': origin_b[1] - origin_a[1],
    }
    if require_same_y and origin_a[1] != origin_b[1]:
        return False, details
    # 两块图的 x 原点不同是正常的块宽变化；补到共同局部原点后比较灰度。
    width = max(image_a.width, image_b.width)
    height = max(image_a.height, image_b.height)
    aligned_a = Image.new('L', (width, height), 0)
    aligned_b = Image.new('L', (width, height), 0)
    aligned_a.paste(image_a, (0, 0))
    aligned_b.paste(image_b, (0, 0))
    same = aligned_a.tobytes() == aligned_b.tobytes()
    details['pixels_equal_after_x_normalization'] = same
    return same, details


def capture(mode: str, output_dir: Path, baseline_dir: Path | None) -> int:
    """逐例运行真实渲染，保存清单、run JSON、mask 与异常堆栈。"""
    base_style, selected_style_path = resolve_style()
    manifest = source_manifest(selected_style_path)
    manifest.update({
        'mode': mode,
        'cases_expected': len(case_catalog()),
        'baseline_dir': str(baseline_dir) if baseline_dir else None,
        'font_fingerprints': {},
    })
    json_write(output_dir / 'manifest.json', manifest)
    results = []
    for index, case in enumerate(case_catalog(), start=1):
        result = render_case(base_style, case, output_dir)
        results.append(result)
        for font_key, fingerprint in result['font_fingerprints'].items():
            manifest['font_fingerprints'][font_key] = fingerprint
        if index % 25 == 0 or index == len(case_catalog()):
            print(f'capture {index}/{len(case_catalog())}: {case["id"]}')
    json_write(output_dir / 'manifest.json', manifest)
    json_write(output_dir / 'index.json', {
        'case_ids': [result['case_id'] for result in results],
        'exception_count': sum(bool(result['exception']) for result in results),
    })
    if mode == 'compare':
        return compare(output_dir, baseline_dir, results, base_style)
    if mode == 'measure':
        return measure(output_dir, results)
    return 0


def _load_baseline(baseline_dir: Path) -> tuple[dict, list[dict]]:
    """读取完整基准并检查其文件清单是否可用。"""
    manifest_path = baseline_dir / 'manifest.json'
    index_path = baseline_dir / 'index.json'
    if not manifest_path.is_file() or not index_path.is_file():
        raise FileNotFoundError(f'基准缺少 manifest.json 或 index.json: {baseline_dir}')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    index = json.loads(index_path.read_text(encoding='utf-8'))
    results = []
    for case_id in index.get('case_ids', []):
        path = baseline_dir / 'cases' / f'{case_id}.json'
        if not path.is_file():
            raise FileNotFoundError(f'基准缺少案例文件: {path}')
        results.append(json.loads(path.read_text(encoding='utf-8')))
    if len(results) != len(case_catalog()):
        raise ValueError(
            f'基准案例数量不完整: expected={len(case_catalog())}, actual={len(results)}')
    return manifest, results


def _supplemental_cases() -> list[dict]:
    """列出三类文本入口以及缺省/null/非法字体配置的辅助实测案例。"""
    cases = []
    for source in ('info_position', 'defined_text_single'):
        for text_kind, text in TEXTS.items():
            cases.append({
                'id': f'entrypoint_{source}_{text_kind}',
                'source': source, 'text': text, 'text_kind': text_kind,
                'size_ratio': 0.027, 'weight': 'medium',
                'alignment': 'center',
            })

    config_variants = (
        ('latin_missing', {'latin': '__REMOVE__'}, None),
        ('latin_empty_mapping', {'latin': {}}, None),
        ('latin_null', {'latin': None}, None),
        ('cjk_missing', {'cjk': '__REMOVE__'}, None),
        ('cjk_empty_mapping', {'cjk': {}}, None),
        ('cjk_null', {'cjk': None}, None),
        ('both_null', {'latin': None, 'cjk': None}, None),
        ('font_files_missing', {
            'latin': {'family': 'MissingBaselineProbe'},
            'cjk': {'family': 'MissingBaselineProbe'},
        }, None),
        ('invalid_latin_type', {'latin': ''}, 'fonts.latin'),
        ('invalid_cjk_type', {'cjk': []}, 'fonts.cjk'),
    )
    for name, overrides, expected_error in config_variants:
        cases.append({
            'id': f'font_config_{name}', 'source': 'custom_text',
            'text': TEXTS['mixed'], 'text_kind': 'font_config',
            'size_ratio': 0.027, 'weight': 'medium',
            'alignment': 'center', 'font_overrides': overrides,
            'expected_error_field': expected_error,
        })
    return cases


def supplemental_contract_checks(base_style: dict, output_dir: Path) -> list[dict]:
    """实测三种入口共用基线，并验证字体配置回退/报错字段。"""
    cases = _supplemental_cases()
    results = [render_case(base_style, case, output_dir) for case in cases]
    indexed = _case_by_id(results)
    failures = []

    for source in ('info_position', 'defined_text_single'):
        pure = indexed[f'entrypoint_{source}_latin']
        pure_draw = _text_draw(pure, TEXTS['latin'])
        expected_baseline = pure_draw.get('baseline') if pure_draw else None
        for text_kind in ('mixed', 'cjk'):
            current = indexed[f'entrypoint_{source}_{text_kind}']
            draw = (_latin_draw(current) if text_kind == 'mixed'
                    else _text_draw(current, TEXTS['cjk']))
            actual_baseline = draw.get('baseline') if draw else None
            if expected_baseline is None or actual_baseline != expected_baseline:
                failures.append({
                    'ac': f'AC-3-entrypoint-{source}',
                    'case_id': current['case_id'],
                    'expected': expected_baseline, 'actual': actual_baseline,
                    'delta': None if expected_baseline is None or actual_baseline is None
                        else actual_baseline - expected_baseline,
                })

    for case in results:
        if case['text_kind'] != 'font_config':
            continue
        expected_field = next(
            item['expected_error_field'] for item in cases if item['id'] == case['case_id'])
        error = case.get('exception')
        if expected_field is None:
            if error is not None or not case.get('draws'):
                failures.append({
                    'ac': 'AC-3-font-fallback', 'case_id': case['case_id'],
                    'expected': '成功绘制，并记录实际回退字体',
                    'actual': error or '没有 draw run', 'delta': '回退失败',
                })
        elif (not error or error.get('type') != 'ValueError'
              or expected_field not in error.get('message', '')):
            failures.append({
                'ac': 'AC-3-font-config-validation', 'case_id': case['case_id'],
                'expected': f"ValueError 包含 {expected_field}",
                'actual': error, 'delta': '未按字段拒绝非法配置',
            })

    json_write(output_dir / 'supplemental_checks.json', {
        'case_ids': [case['case_id'] for case in results],
        'failure_count': len(failures), 'failures': failures,
        'font_config_actual_fingerprints': {
            case['case_id']: case['font_fingerprints']
            for case in results if case['text_kind'] == 'font_config'
        },
    })
    return failures


def compare(
    output_dir: Path, baseline_dir: Path | None, current_results: list[dict],
    base_style: dict,
) -> int:
    """执行 AC-1～AC-5：pure-Latin 兼容、语言共享基线及多行槽位契约。"""
    if baseline_dir is None:
        raise ValueError('compare 模式必须提供 --baseline')
    baseline_manifest, baseline_results = _load_baseline(baseline_dir)
    current_manifest = json.loads((output_dir / 'manifest.json').read_text(encoding='utf-8'))
    failures: list[dict] = []
    baseline = _case_by_id(baseline_results)
    current = _case_by_id(current_results)

    # 只对像素环境指纹做严格比较；生产源码哈希允许因本次修复而变化。
    baseline_env = (
        baseline_manifest.get('pillow'), baseline_manifest.get('freetype'),
        baseline_manifest.get('python', '').split()[0],
        baseline_manifest.get('source_sha256', {}).get('style_variant'),
    )
    current_env = (
        current_manifest.get('pillow'), current_manifest.get('freetype'),
        current_manifest.get('python', '').split()[0],
        current_manifest.get('source_sha256', {}).get('style_variant'),
    )
    if baseline_env != current_env:
        failures.append({
            'ac': 'environment', 'case_id': 'manifest',
            'expected': list(baseline_env), 'actual': list(current_env),
            'delta': '环境不一致；像素阈值不放宽',
        })
    if baseline_manifest.get('font_fingerprints') != current_manifest.get('font_fingerprints'):
        failures.append({
            'ac': 'environment-fonts', 'case_id': 'manifest',
            'expected': baseline_manifest.get('font_fingerprints'),
            'actual': current_manifest.get('font_fingerprints'),
            'delta': '实际字体路径、metrics 或文件哈希发生变化',
        })
    if set(baseline) != set(current):
        failures.append({
            'ac': 'coverage', 'case_id': 'manifest',
            'expected': len(baseline), 'actual': len(current),
            'delta': f'missing={sorted(set(baseline) - set(current))[:8]} '
                     f'extra={sorted(set(current) - set(baseline))[:8]}',
        })

    # AC-1：所有字号/字重/对齐的纯西文实际 draw 坐标、字体和 mask 对旧基准不变。
    for case_id, old_case in baseline.items():
        now_case = current.get(case_id)
        if now_case is None or old_case.get('text_kind') != 'latin':
            continue
        old_draw = _text_draw(old_case, TEXTS['latin'])
        now_draw = _text_draw(now_case, TEXTS['latin'])
        expected = old_draw and old_draw.get('baseline')
        actual = now_draw and now_draw.get('baseline')
        mask_same, mask_detail = _normalized_mask_equal(
            baseline_dir, old_draw, output_dir, now_draw, require_same_y=True)
        exact_draw = bool(old_draw and now_draw and
                          old_draw.get('xy') == now_draw.get('xy') and
                          old_draw.get('font', {}).get('path') == now_draw.get('font', {}).get('path') and
                          old_draw.get('font', {}).get('size') == now_draw.get('font', {}).get('size'))
        if expected != actual or not exact_draw or not mask_same:
            failures.append({
                'ac': 'AC-1', 'case_id': case_id,
                'expected': {'baseline': expected, 'xy': old_draw.get('xy') if old_draw else None,
                             'mask': 'identical'},
                'actual': {'baseline': actual, 'xy': now_draw.get('xy') if now_draw else None,
                           'mask': mask_detail},
                'delta': None if expected is None or actual is None else actual - expected,
            })

    # AC-2/3：每个字号、字重和 alignment 中，混排西文及纯中文都沿用纯西文基线。
    group_keys = sorted({
        (case['requested_size_ratio'], case['weight'], case['alignment'])
        for case in current_results
        if case.get('source') == 'custom_text' and case.get('text_kind') in TEXTS
        and not case.get('minimum_size_case')
    })
    for ratio, weight, alignment in group_keys:
        suffix = f'{ratio:g}_{weight}_{alignment}'
        pure = current.get(f'matrix_r{suffix}_latin')
        mixed = current.get(f'matrix_r{suffix}_mixed')
        cjk = current.get(f'matrix_r{suffix}_cjk')
        pure_draw = _text_draw(pure, TEXTS['latin']) if pure else None
        mixed_draw = _latin_draw(mixed) if mixed else None
        cjk_draw = _text_draw(cjk, TEXTS['cjk']) if cjk else None
        expected = pure_draw.get('baseline') if pure_draw else None
        for ac, case_id, draw in (
                ('AC-2', mixed.get('case_id') if mixed else f'matrix_r{suffix}_mixed', mixed_draw),
                ('AC-3', cjk.get('case_id') if cjk else f'matrix_r{suffix}_cjk', cjk_draw)):
            actual = draw.get('baseline') if draw else None
            if expected is None or actual != expected:
                failures.append({
                    'ac': ac, 'case_id': case_id, 'expected': expected,
                    'actual': actual,
                    'delta': None if expected is None or actual is None else actual - expected,
                })
        if pure_draw and mixed_draw:
            same, details = _normalized_mask_equal(
                output_dir, pure_draw, output_dir, mixed_draw, require_same_y=True)
            if not same:
                failures.append({
                    'ac': 'AC-2-mask', 'case_id': mixed['case_id'],
                    'expected': '共同西文 run 的 y mask 精确相同',
                    'actual': details, 'delta': details.get('y_delta'),
                })

    # A3 的中文前置、ASCII 空格、gypq 与中文标点样本也必须保持共同西文 run。
    for index in range(6):
        case_id = f'content_edge_{index:02d}'
        example = current.get(case_id)
        if example is None:
            failures.append({
                'ac': 'coverage', 'case_id': case_id,
                'expected': '已捕获的内容边界案例', 'actual': None,
                'delta': '缺少案例',
            })
            continue
        if index in (3, 4):
            reference = current.get('content_edge_03')
            needle = 'gypq'
        else:
            reference = current.get('matrix_r0.027_medium_center_latin')
            needle = TEXTS['latin']
        expected_draw = _latin_containing_draw(reference, needle) if reference else None
        actual_draw = _latin_containing_draw(example, needle)
        expected = expected_draw.get('baseline') if expected_draw else None
        actual = actual_draw.get('baseline') if actual_draw else None
        if expected is None or actual != expected:
            failures.append({
                'ac': 'AC-2-content-edge', 'case_id': case_id,
                'expected': expected, 'actual': actual,
                'delta': None if expected is None or actual is None else actual - expected,
            })
        if expected_draw and actual_draw:
            same, details = _normalized_mask_equal(
                output_dir, expected_draw, output_dir, actual_draw, require_same_y=True)
            if not same:
                failures.append({
                    'ac': 'AC-2-content-mask', 'case_id': case_id,
                    'expected': '共同西文 run 的 y mask 精确相同',
                    'actual': details, 'delta': details.get('y_delta'),
                })

    # 12px 下限样本独立于比例矩阵，检查 FontManager 的实际返回字号。
    for case in current_results:
        if case.get('text_kind') == 'minimum_size' and case.get('actual_font_size') != 12:
            failures.append({
                'ac': 'AC-1-minimum-size', 'case_id': case['case_id'],
                'expected': 12, 'actual': case.get('actual_font_size'),
                'delta': None if case.get('actual_font_size') is None
                    else case['actual_font_size'] - 12,
            })

    # AC-5：defined_texts 的行槽数、总逻辑高度與空槽无 draw 契约。
    for case in current_results:
        if case.get('source') == 'defined_texts':
            slots = case.get('actual_line_slot_count', 0)
            draw_lines = case.get('draws', [])
            error = case.get('exception')
            expected_slots = len(case['original_text'].split('\n'))
            if error or slots != expected_slots:
                failures.append({
                    'ac': 'AC-5', 'case_id': case['case_id'],
                    'expected': {'slots': expected_slots, 'exception': None},
                    'actual': {'slots': slots, 'exception': error},
                    'delta': '旧实现空行/纯换行失败' if error else slots - expected_slots,
                })
            if case['original_text'] in ('\n', '\n\n') and draw_lines:
                failures.append({
                    'ac': 'AC-5', 'case_id': case['case_id'],
                    'expected': '空行槽无 draw 调用',
                    'actual': [draw['text'] for draw in draw_lines],
                    'delta': len(draw_lines),
                })
            if case.get('logical_box'):
                # 参考字体信息由独立诊断器在真实渲染外加载，含全空行案例。
                metrics = case['latin_reference_font'].get('metrics')
                if isinstance(metrics, list) and len(metrics) == 2:
                    ascent, descent = metrics
                    logical_height = case['logical_box']['height']
                    spacing = case['line_spacing'] or 0
                    expected_height = (
                        expected_slots * (ascent + descent)
                        + max(0, expected_slots - 1) * spacing)
                    if logical_height != expected_height:
                        failures.append({
                            'ac': 'AC-5-height', 'case_id': case['case_id'],
                            'expected': expected_height, 'actual': logical_height,
                            'delta': logical_height - expected_height,
                            'font_path': case['latin_reference_font'].get('path'),
                        })
                    layout_records = case.get('line_layout', [])
                    if layout_records:
                        positions = layout_records[-1]['positions']
                        expected_step = ascent + descent + spacing
                        for line_index, (previous, current_position) in enumerate(
                                zip(positions, positions[1:]), start=1):
                            actual_step = current_position[1] - previous[1]
                            if actual_step != expected_step:
                                failures.append({
                                    'ac': 'AC-5-baseline-step',
                                    'case_id': case['case_id'],
                                    'expected': expected_step,
                                    'actual': actual_step,
                                    'delta': actual_step - expected_step,
                                    'line_index': line_index,
                                })

    # AC-4：同一 relative/tree/cross 配置下，内容类别变化不应改变目标基线。
    relative_groups = sorted({
        case['case_id'].rsplit('_', 1)[0]
        for case in current_results if case.get('source') == 'relative'
    })
    for group in relative_groups:
        pure = current.get(f'{group}_latin')
        mixed = current.get(f'{group}_mixed')
        cjk = current.get(f'{group}_cjk')
        pure_draw = _text_draw(pure, TEXTS['latin']) if pure else None
        expected = pure_draw.get('baseline') if pure_draw else None
        for ac, example, draw in (
                ('AC-4-mixed', mixed, _latin_draw(mixed) if mixed else None),
                ('AC-4-cjk', cjk, _text_draw(cjk, TEXTS['cjk']) if cjk else None)):
            actual = draw.get('baseline') if draw else None
            if expected is None or actual != expected:
                failures.append({
                    'ac': ac, 'case_id': example.get('case_id') if example else group,
                    'expected': expected, 'actual': actual,
                    'delta': None if expected is None or actual is None else actual - expected,
                })

    # 三个文本入口与 Latin/CJK 配置归一化不属于像素基准矩阵，单独逐项实测。
    failures.extend(supplemental_contract_checks(base_style, output_dir))

    # 以 JSON 和可读文本双份保存失败原因，control 应明确呈现旧版 -7/-14/+1。
    json_write(output_dir / 'comparison.json', {
        'baseline': str(baseline_dir), 'failure_count': len(failures),
        'passed': not failures, 'failures': failures,
    })
    lines = []
    for failure in failures:
        lines.append(
            f"{failure['ac']} {failure['case_id']}: expected={failure['expected']} "
            f"actual={failure['actual']} delta={failure['delta']}")
    (output_dir / 'comparison.txt').write_text(
        '\n'.join(lines) + ('\n' if lines else '全部 AC-1～AC-5 通过\n'),
        encoding='utf-8')
    print(f"compare: {'PASS' if not failures else 'FAIL'}; "
          f'{len(failures)} 条失败，详见 {output_dir / "comparison.txt"}')
    return 0 if not failures else 1


def measure(output_dir: Path, results: list[dict]) -> int:
    """汇总实际 run 的像素墨迹边界和灰度重心，不参与通过/失败判定。"""
    summary = []
    for case in results:
        for draw in case['draws']:
            loaded = _mask_pixels(output_dir, draw)
            if loaded is None:
                summary.append({'case_id': case['case_id'], 'text': draw['text'], 'ink': None})
                continue
            mask, origin = loaded
            histogram = mask.histogram()
            total = sum(value * count for value, count in enumerate(histogram))
            weighted_x = sum(x * mask.getpixel((x, y))
                             for y in range(mask.height) for x in range(mask.width))
            weighted_y = sum(y * mask.getpixel((x, y))
                             for y in range(mask.height) for x in range(mask.width))
            summary.append({
                'case_id': case['case_id'], 'text': draw['text'],
                'canvas_bbox_half_open': draw['mask_bbox_half_open'],
                'crop_origin': origin,
                'gravity_center_canvas': [
                    origin[0] + weighted_x / total,
                    origin[1] + weighted_y / total,
                ] if total else None,
            })
    json_write(output_dir / 'measurements.json', summary)
    print(f'measure: {len(summary)} run 已输出墨迹框/重心诊断')
    return 0


def parse_args() -> argparse.Namespace:
    """解析 capture、compare、measure 三种只写入显式目录的模式。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', required=True, choices=('capture', 'compare', 'measure'))
    parser.add_argument('--output', required=True, type=Path,
                        help='本次运行的全新空输出目录')
    parser.add_argument('--baseline', type=Path,
                        help='compare/measure 使用的 capture 基准目录')
    return parser.parse_args()


def main() -> int:
    """启动采集；compare 的失败以非零状态返回，允许旧缺陷继续留证。"""
    args = parse_args()
    output_dir = args.output.expanduser().resolve()
    baseline_dir = args.baseline.expanduser().resolve() if args.baseline else None
    _safe_output(output_dir, args.mode)
    logging.basicConfig(
        filename=output_dir / 'diagnostic.log', filemode='w',
        encoding='utf-8', level=logging.DEBUG,
        format='%(asctime)s %(levelname)s %(name)s %(message)s')
    return capture(args.mode, output_dir, baseline_dir)


if __name__ == '__main__':
    raise SystemExit(main())
