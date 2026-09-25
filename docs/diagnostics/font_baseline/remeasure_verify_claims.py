"""复核复评提出的三项关键主张，并补测原复测缺失的对照样本。

背景
----
另一智能体复评 remeasure_visual_shift.py 后提出四条批评。本脚本对其中三项
可测主张做独立复算（第四条 pad bug 已在 remeasure_visual_shift.py 修正）：

主张 A：把混排基线恢复到原西文基线后，墨迹顶/中心仍有残余位移（-5/-1px），
        该残余来自中文字形固有高度差，不应作为归零目标。
主张 B：`Hello世界`/`世界Hello` 的 bbox 宽 == advance，横向重心差异不能归因于
        "bbox 当 advance"；只有特定字形（如 j）两者才不等。
主张 C：小字号（12/27px）受整数取整影响，位移占字号比例会波动。

另补一个干净对照：同一文本分别用 bbox 推进与 advance 推进绘制，量化
"bbox 当 advance" 的真实横向误差（内容完全一致，排除内容差异干扰）。

只读取生产字体与分段函数，不修改任何生产代码或配置。
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.utils.app_paths import get_app_dir, get_resource_root
from src.utils.font_manager import FontManager

OUT = get_app_dir() / 'docs' / 'diagnostics' / 'font_baseline'


def load_fonts(size):
    """加载 FilmClip 实际使用的两款字体（Medium 字重）。"""
    fd = get_resource_root() / 'assets' / 'fonts'
    return (ImageFont.truetype(str(fd / 'Gotham-Medium.otf'), size),
            ImageFont.truetype(str(fd / 'GlowSansSC-Normal-Medium.otf'), size))


def claim_a_baseline_restore(sizes=(54, 81, 108)):
    """主张 A：恢复基线后的残余位移 = 中文字形固有差异（诊断量，非归零目标）。

    方法：以基线为 y=0 参考。纯西文墨迹 = 西文段墨迹；混排墨迹 = 西文段 ∪ 中文段
    （两段共享同一基线，这正是"恢复到原西文基线"的含义）。此时西文段逐像素不动，
    剩下的墨迹差异只能来自中文字形本身。
    """
    rows = []
    for size in sizes:
        latin, cjk = load_fonts(size)
        ink_l = latin.getbbox('AaBbCc', anchor='ls')
        ink_c = cjk.getbbox('永和九年', anchor='ls')
        p_top, p_bot = ink_l[1], ink_l[3]
        m_top = min(ink_l[1], ink_c[1])
        m_bot = max(ink_l[3], ink_c[3])
        rows.append({
            'size': size,
            'latin_ink_rel_baseline': list(ink_l),
            'cjk_ink_rel_baseline': list(ink_c),
            'pure_ink': [p_top, p_bot],
            'mixed_ink_after_restore': [m_top, m_bot],
            # 西文段完全不动（同一基线同一字体）→ 位置跳动项 = 0
            'latin_glyph_shift': 0,
            # 残余差异 = 中文字形固有高度差
            'ink_top_shift': m_top - p_top,
            'ink_bottom_shift': m_bot - p_bot,
            'ink_center_shift': (m_top + m_bot) / 2 - (p_top + p_bot) / 2,
        })
    return rows


def claim_b_advance_vs_bbox(sizes=(54, 108)):
    """主张 B：逐字形比较 bbox 宽与 advance，找出真正不等的样本。"""
    samples = ['Hello', '世界', 'AaBbCc', '永和九年', 'j', 'fj', 'f', 'y',
               'j永', '永j', '摄影Photo 2024永和九年', 'Hello世界', '世界Hello']
    rows = []
    for size in sizes:
        latin, cjk = load_fonts(size)
        for text in samples:
            segs = FontManager.split_mixed_text(text)
            # 按生产分段各取对应字体
            total_bbox_w = 0.0
            total_adv = 0.0
            seg_detail = []
            for seg, is_cjk in segs:
                f = cjk if is_cjk else latin
                bb = f.getbbox(seg)
                adv = f.getlength(seg)
                bw = bb[2] - bb[0]
                total_bbox_w += bw
                total_adv += adv
                seg_detail.append({
                    'seg': seg, 'font': 'cjk' if is_cjk else 'latin',
                    'bbox_width': bw, 'advance': adv, 'delta': bw - adv,
                })
            rows.append({
                'size': size, 'text': text,
                'sum_bbox_width': total_bbox_w,
                'sum_advance': total_adv,
                'delta': total_bbox_w - total_adv,
                'segments': seg_detail,
            })
    return rows


def claim_b_clean_contrast(text='j永和九年', size=54):
    """主张 B 补充：同一文本、同一内容，仅推进算法不同，量化真实横向误差。

    这是排除内容差异的干净对照：
      当前算法 = 各段用 bbox 宽推进（text_renderer.py:321）
      对照算法 = 各段用 advance 推进
    两组内容完全一致，差异只能来自推进量算法。
    """
    latin, cjk = load_fonts(size)
    segs = FontManager.split_mixed_text(text)

    def draw_with(advance_mode):
        """按指定推进方式绘制，返回各段绘制原点 x 与整行墨迹盒。"""
        mask = Image.new('L', (2000, 400))
        md = ImageDraw.Draw(mask)
        x = 80.0
        origins = []
        for seg, is_cjk in segs:
            f = cjk if is_cjk else latin
            origins.append(round(x))
            ascent = f.getmetrics()[0]
            md.text((round(x), 200 - ascent), seg, font=f, fill=255)
            x += f.getlength(seg) if advance_mode else (f.getbbox(seg)[2] - f.getbbox(seg)[0])
        return origins, mask.getbbox(), x - 80

    o_bbox, ink_bbox, reg_w = draw_with(False)
    o_adv, ink_adv, adv_w = draw_with(True)
    return {
        'text': text, 'size': size,
        'segments': [s[0] for s in segs],
        'origins_current_bbox_advance': o_bbox,
        'origins_reference_advance': o_adv,
        'origin_delta': [a - b for a, b in zip(o_bbox, o_adv)],
        'ink_bbox_mode': list(ink_bbox) if ink_bbox else None,
        'ink_advance_mode': list(ink_adv) if ink_adv else None,
        'registered_width_current': reg_w,
        'registered_width_reference': adv_w,
    }


def claim_c_small_sizes():
    """主张 C：小字号取整波动——字号 = max(12, int(min(w,h) * ratio))。"""
    ratio = 0.027
    rows = []
    for min_side in [200, 300, 400, 444, 450, 500, 600, 740, 750, 800, 1000]:
        size = max(12, int(min_side * ratio))
        latin, cjk = load_fonts(size)
        ink_l = latin.getbbox('AaBbCc', anchor='ls')
        ink_c = cjk.getbbox('永和九年', anchor='ls')
        m_l, m_c = latin.getmetrics(), cjk.getmetrics()
        h_l = m_l[0] + m_l[1]
        h_m = max(m_l[0], m_c[0]) + max(m_l[1], m_c[1])
        # center 对齐基线位移 = (Y - H_M//2) - (Y - H_L//2)，整数除法与生产一致。
        # 注意不能写成 -((H_M-H_L)//2)：两者在 H_M/H_L 奇偶不同时结果不同
        # （12px 时 H_L=15/H_M=18，正确值 -2，误写会得 -1）。
        baseline_shift = -(h_m // 2) + (h_l // 2)
        ink_top_shift = min(ink_l[1], ink_c[1]) - ink_l[1]
        rows.append({
            'min_side': min_side, 'font_size': size,
            'H_latin': h_l, 'H_mixed': h_m,
            'baseline_shift': baseline_shift,
            'ink_top_shift': ink_top_shift,
            'baseline_shift_over_size': baseline_shift / size,
            'ink_top_shift_over_size': ink_top_shift / size,
        })
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        'purpose': '复核复评主张 A/B/C，并做 bbox vs advance 干净对照',
        'claim_A_baseline_restore': claim_a_baseline_restore(),
        'claim_B_advance_vs_bbox': claim_b_advance_vs_bbox(),
        'claim_B_clean_contrast': claim_b_clean_contrast(),
        'claim_C_small_sizes': claim_c_small_sizes(),
    }
    path = OUT / 'remeasure_verify_claims.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(path)


if __name__ == '__main__':
    main()
