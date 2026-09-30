"""T8（Q15 legacy 矩形合成性能优化）的等价性与性能证据脚本。

从项目根目录激活 venv 后运行（无需 --pre：优化前后等价性用脚本内
置的旧实现参考副本逐像素比对，性能数据与本轮优化前的实现同源）。

等价性验证（审计报告 §8 验收矩阵 Q15 行）：
- 新实现（rectangle_layer.draw_legacy_rectangles）与旧实现参考副本
  （原"每矩形全画布建层 → convert → composite → convert"逐字照抄）
  在随机 fuzz 场景下输出逐字节一致：重叠半透明矩形、不同绘制顺序、
  圆角抗锯齿、跨画布边界/负坐标；
- 1×1 合成顺序反例：逐次合成（本实现语义）与"先合组再合背景"结果
  必须不同，锁定逐次语义不被优化偷偷改变。

性能数据：大画布 × 多矩形新旧耗时对比 + tracemalloc 峰值内存。
"""

import json
import random
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

import numpy as np
from PIL import Image

from src.core.rectangle_layer import (
    RectangleSpec,
    draw_legacy_rectangles,
    rounded_corner_mask,
)

EVIDENCE_DIR = Path(__file__).resolve().parent
OUT_FILE = EVIDENCE_DIR / 'core_pipeline_t8_composite_perf.json'


def _legacy_draw_single(background, rect_w, rect_h, position, color,
                        opacity, corner_radius, reference_side):
    """旧实现参考副本：优化前 draw_single_rectangle 的逐字照抄。

    作为等价性基准保留在本脚本内，不得为通过验证而修改其行为。
    """
    alpha_val = int(round(255 * opacity))
    rect_layer = Image.new('RGBA', background.size, (0, 0, 0, 0))
    rect_img = Image.new('RGBA', (rect_w, rect_h), (*color, alpha_val))

    if corner_radius and isinstance(corner_radius, dict):
        r_tl = int(reference_side * corner_radius.get('top_left', 0))
        r_tr = int(reference_side * corner_radius.get('top_right', 0))
        r_bl = int(reference_side * corner_radius.get('bottom_left', 0))
        r_br = int(reference_side * corner_radius.get('bottom_right', 0))
        if any(r > 0 for r in [r_tl, r_tr, r_bl, r_br]):
            mask = rounded_corner_mask(rect_w, rect_h, r_tl, r_tr, r_bl, r_br)
            mask_array = np.array(mask, dtype=np.float32) * opacity
            rect_img.putalpha(Image.fromarray(mask_array.astype(np.uint8)))

    rect_layer.paste(rect_img, position)
    result = background.convert('RGBA')
    result = Image.alpha_composite(result, rect_layer)
    return result.convert('RGB')


def _legacy_draw_all(background, specs, reference_side):
    """旧实现循环：逐矩形调用参考副本（与优化前 draw_legacy_rectangles
    的调用方式一致）。"""
    result = background
    for spec in specs:
        result = _legacy_draw_single(
            result, spec.box[2], spec.box[3], (spec.box[0], spec.box[1]),
            spec.legacy_color, spec.legacy_opacity,
            spec.legacy_corner_radius, reference_side)
    return result


def _make_specs(rng, canvas_wh, count):
    """随机生成矩形序列：半透明重叠、负坐标、越界、圆角混合。"""
    specs = []
    for i in range(count):
        w = rng.randint(10, max(11, canvas_wh[0] // 2))
        h = rng.randint(10, max(11, canvas_wh[1] // 2))
        x = rng.randint(-w // 2, canvas_wh[0] - w // 2)
        y = rng.randint(-h // 2, canvas_wh[1] - h // 2)
        color = tuple(rng.randint(0, 255) for _ in range(3))
        opacity = rng.choice([0.0, 0.15, 0.5, 0.75, 1.0,
                              rng.random()])
        corner = None
        if rng.random() < 0.4:
            corner = {k: rng.random() * 0.05
                      for k in ('top_left', 'top_right',
                                'bottom_left', 'bottom_right')}
        specs.append(RectangleSpec(
            name=f'r{i}', kind='legacy', box=(x, y, w, h),
            legacy_color=color, legacy_opacity=opacity,
            legacy_corner_radius=corner))
    return specs


def verify_equivalence():
    """随机 fuzz：新旧实现输出逐字节一致。"""
    rng = random.Random(20260930)
    cases = 0
    for trial in range(60):
        canvas_wh = (rng.randint(40, 300), rng.randint(40, 300))
        bg_color = tuple(rng.randint(0, 255) for _ in range(3))
        background = Image.new('RGB', canvas_wh, bg_color)
        specs = _make_specs(rng, canvas_wh, rng.randint(1, 6))
        ref_side = min(canvas_wh)
        old_out = _legacy_draw_all(background, specs, ref_side)
        new_out = draw_legacy_rectangles(background, specs, ref_side)
        assert old_out.tobytes() == new_out.tobytes(), \
            f"fuzz 第 {trial} 轮新旧输出不一致（画布 {canvas_wh}）"
        cases += 1

    # 1×1 合成顺序反例：逐次（本实现语义）必须与"先合组"结果不同
    background = Image.new('RGBA', (1, 1), (17, 83, 191, 255))
    first = Image.new('RGBA', (1, 1), (231, 31, 7, 2))
    second = Image.new('RGBA', (1, 1), (2, 219, 101, 127))
    sequential = Image.alpha_composite(
        Image.alpha_composite(background, first), second).convert('RGB')
    grouped = Image.alpha_composite(
        background, Image.alpha_composite(first, second)).convert('RGB')
    assert sequential.tobytes() != grouped.tobytes(), \
        "1×1 反例不再区分合成顺序，逐次语义可能被优化改变"
    # 用矩形路径重现 sequential 值：背景 (17,83,191) + 两个半透明矩形
    bg_rgb = Image.new('RGB', (1, 1), (17, 83, 191))
    specs = [
        RectangleSpec(name='a', kind='legacy', box=(0, 0, 1, 1),
                      legacy_color=(231, 31, 7), legacy_opacity=2 / 255),
        RectangleSpec(name='b', kind='legacy', box=(0, 0, 1, 1),
                      legacy_color=(2, 219, 101), legacy_opacity=127 / 255),
    ]
    via_rects = draw_legacy_rectangles(bg_rgb, specs, 1.0)
    assert via_rects.getpixel((0, 0)) == sequential.getpixel((0, 0)), \
        (f"矩形路径逐次合成偏离参考 sequential: "
         f"{via_rects.getpixel((0, 0))} vs {sequential.getpixel((0, 0))}")
    return {'fuzz_cases': cases,
            'sequential_pixel': list(sequential.getpixel((0, 0))),
            'grouped_pixel': list(grouped.getpixel((0, 0))),
            'rects_match_sequential': True}


def benchmark():
    """大画布多矩形：新旧耗时与峰值内存（同输入 3 轮取最小）。"""
    rng = random.Random(7)
    background = Image.new('RGB', (3000, 2000), (40, 60, 90))
    specs = _make_specs(rng, (3000, 2000), 12)
    ref_side = 2000

    def run(fn):
        best_t = float('inf')
        out = None
        for _ in range(3):
            t0 = time.perf_counter()
            out = fn(background, specs, ref_side)
            best_t = min(best_t, time.perf_counter() - t0)
        return best_t, out

    tracemalloc.start()
    old_t, old_out = run(_legacy_draw_all)
    old_peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.reset_peak()
    new_t, new_out = run(draw_legacy_rectangles)
    new_peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()

    assert old_out.tobytes() == new_out.tobytes(), \
        "基准场景新旧输出不一致"
    return {
        'canvas': [3000, 2000], 'rect_count': len(specs),
        'old_seconds': round(old_t, 4),
        'new_seconds': round(new_t, 4),
        'speedup': round(old_t / new_t, 2) if new_t else None,
        'old_peak_mib': round(old_peak / 1024 / 1024, 1),
        'new_peak_mib': round(new_peak / 1024 / 1024, 1),
        'peak_reduction_mib': round((old_peak - new_peak) / 1024 / 1024, 1),
    }


def main():
    equiv = verify_equivalence()
    perf = benchmark()
    results = {'equivalence': equiv, 'benchmark': perf}
    OUT_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"[t8] 等价性与性能证据已写入 {OUT_FILE.name}")


if __name__ == '__main__':
    main()
