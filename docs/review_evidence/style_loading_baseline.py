# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
T0 基线记录脚本（STYLE_OPTION_CAPABILITIES_PLAN.md §3）

在重构（T1 样式加载层）之前，记录两类可复核基线：
1. 变体选择结果：作者与时间组合、同分条件、多个 default、没有 default、
   同名多来源——供 T1 抽取共享选择函数后逐条比对，保证只共享逻辑、
   不改变任何选择规则；
2. 定位校验结果：现有 9 个样式 17 份配置全部通过；另构造旧别名、
   非法九点枚举、相对定位环、交叉轴不匹配等非法样例，记录拒绝结果
   与错误信息文本——供 4.0 纯搬运拆分（style_validator.py）前后比对。

运行方式（venv，项目根目录）：
    python docs/review_evidence/style_loading_baseline.py
输出写入同目录 style_loading_baseline.txt。
"""
import io
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from src.frame_styles.style_manager import StyleManager  # noqa: E402

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "style_loading_baseline.txt")
_lines = []


def emit(line=""):
    _lines.append(line)
    print(line)


# ─────────────────────────────────────────────────────────────
# 1. 变体选择基线（临时目录构造，不触碰真实样式目录）
# ─────────────────────────────────────────────────────────────

def record_variant_baselines():
    emit("=" * 72)
    emit("一、变体选择基线（_resolve_style_variant，临时目录构造）")
    emit("=" * 72)
    sm = StyleManager(config_dir=tempfile.mkdtemp(prefix="t0_cfg_"))

    cases = []

    def make_style(name, files):
        d = os.path.join(sm.config_dir, name)
        os.makedirs(d, exist_ok=True)
        for fname in files:
            # 文件内容不影响选择逻辑（选择只看文件名），写最小合法 YAML
            with open(os.path.join(d, fname), "w", encoding="utf-8") as f:
                f.write("name: t0\nlayout: {}\n")
        return d

    # 1.1 作者与时间组合（模拟 Bottom Bars 结构）
    make_style("Combo", ["default.yaml", "no_timestamp_author.yaml",
                         "no_location.yaml", "no_location_no_timestamp_author.yaml"])
    combo_ctxs = [
        ("作者+时间+地点", {"location": "北京", "author": "张三"}),
        ("仅作者", {"location": None, "author": "张三", "timestamp_author": None}),
        ("仅时间", {"location": None, "author": None, "timestamp": "2026.01.01",
                    "timestamp_author": "2026.01.01"}),
        ("全无", {"location": None, "author": None, "timestamp": None,
                  "timestamp_author": None, "custom_text": None}),
        ("地点+全无作者时间", {"location": "上海", "author": None,
                              "timestamp": None, "timestamp_author": None}),
    ]
    for label, ctx in combo_ctxs:
        cases.append(("Combo", ctx, label))

    # 1.2 同分条件：no_author 与 no_location 同为 1 分（作者与地点同时缺失）
    make_style("SameScore", ["default.yaml", "no_author.yaml", "no_location.yaml"])
    cases.append(("SameScore", {"author": None, "location": None},
                  "同分条件（应取文件名排序后的首个 no_author.yaml）"))

    # 1.3 多个 default：default.json 与 default.yaml（原始枚举顺序的 default 优先）
    make_style("MultiDefault", ["default.yaml", "default.json", "no_author.yaml"])
    cases.append(("MultiDefault", {"author": None},
                  "作者缺失（no_author 条件命中，1 分）"))
    cases.append(("MultiDefault", {},
                  "无缺失字段（default 兜底，取原始枚举顺序首个 default）"))

    # 1.4 没有 default：只有条件文件，全部不命中 → 原始枚举顺序首文件
    make_style("NoDefault", ["zeta.yaml", "no_author.yaml", "alpha.yaml"])
    cases.append(("NoDefault", {"author": "张三"},
                  "条件不命中且无 default（应取原始枚举顺序首文件 zeta.yaml）"))

    # 1.5 同名多来源：用户目录（extra_dirs）单文件 vs 内置目录
    user_dir = tempfile.mkdtemp(prefix="t0_user_")
    with open(os.path.join(user_dir, "Dual.yaml"), "w", encoding="utf-8") as f:
        f.write("name: dual-user-file\nlayout: {}\n")
    make_style("Dual", ["default.yaml"])
    sm_dual = StyleManager(config_dir=sm.config_dir)
    sm_dual.extra_dirs = [user_dir]
    emit("")
    emit("[同名多来源] 用户目录 Dual.yaml（单文件） vs 内置 Dual/（目录）")
    cfg = sm_dual.get_style_config("Dual")
    emit(f"  实际加载 name 字段: {cfg.get('name') if cfg else None} "
         f"（预期目录样式优先 → t0，而非 dual-user-file）")

    # 1.6 未知条件与普通文件兜底（C06 预研）
    make_style("UnknownCond", ["plain.yaml", "no_iso.yaml", "default.yaml"])
    cases.append(("UnknownCond", {"author": "张三"},
                  "iso 未出现在 context（no_iso 不命中 → default 兜底）"))
    cases.append(("UnknownCond", {"author": "张三", "iso": None},
                  "显式 iso=None（no_iso 命中）"))

    for style, ctx, label in cases:
        d = os.path.join(sm.config_dir, style)
        picked = sm._resolve_style_variant(d, ctx)
        picked_name = os.path.basename(picked) if picked else None
        emit(f"[{style}] {label:40s} ctx={ctx} -> {picked_name}")

    # 无 context 调用（GUI 现状：_update_style_dependent_controls 无 context）
    for style in ("Combo", "MultiDefault", "NoDefault"):
        d = os.path.join(sm.config_dir, style)
        picked = sm._resolve_style_variant(d, None)
        emit(f"[{style}] {'无 context 调用':40s} -> "
             f"{os.path.basename(picked) if picked else None}")


# ─────────────────────────────────────────────────────────────
# 2. 定位校验基线（真实 17 份配置 + 构造非法样例）
# ─────────────────────────────────────────────────────────────

def record_validation_baselines():
    emit("")
    emit("=" * 72)
    emit("二、定位校验基线（真实配置 + 非法样例，含错误信息全文）")
    emit("=" * 72)
    sm = StyleManager()
    styles = sm.get_available_styles()
    emit(f"内置样式数: {len(styles)}")
    total = 0
    failed = []
    for name in styles:
        dirs = list(sm._iter_style_dirs(name))
        if not dirs:
            emit(f"  [单文件样式] {name}（无变体目录，跳过逐份校验记录）")
            continue
        d = dirs[0]
        variants = sorted(f for f in os.listdir(d)
                          if f.endswith((".json", ".yaml", ".yml", ".toml")))
        for v in variants:
            total += 1
            cfg = sm._load_config_file(os.path.join(d, v))
            status = "通过" if cfg else "拒绝"
            if not cfg:
                failed.append(f"{name}/{v}")
            emit(f"  [{status}] {name}/{v}")

        # 记录每份配置的九点关键字段，供拆分后比对（取 default 变体）
        default_path = os.path.join(d, "default.yaml")
        if os.path.exists(default_path):
            cfg = sm._load_config_file(default_path)
            ip = (cfg.get("layout", {}) or {}).get("info_position", {}) or {}
            emit(f"    default 注入后 info_position 键: {sorted(ip)}")
    emit(f"真实配置合计: {total} 份, 拒绝 {len(failed)} 份 {failed if failed else ''}")

    emit("")
    emit("── 非法样例（预期全部拒绝，记录错误信息全文）──")
    import yaml as _yaml

    def check_invalid(label, yaml_text):
        tmp = os.path.join(tempfile.mkdtemp(prefix="t0_bad_"), "bad.yaml")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(yaml_text)
        # 逐条捕获日志：_validate_config 内部 logger.error 输出错误信息
        import logging
        records = []
        handler = logging.Handler()
        handler.emit = lambda rec: records.append(rec.getMessage())
        logger = logging.getLogger("src.frame_styles.style_manager")
        logger.addHandler(handler)
        try:
            cfg = _yaml.safe_load(yaml_text)
            ok = sm._validate_config(cfg, label)
        finally:
            logger.removeHandler(handler)
        emit(f"[{'通过(异常!)' if ok else '拒绝'}] {label}")
        for msg in records:
            emit(f"    错误: {msg}")

    check_invalid("旧 position 别名 tc", """
name: bad
layout:
  info_position:
    author:
      placement: outside
      position: tc
      alignment: top-center
      margin: 10
""")
    check_invalid("非法九点枚举 position=middle", """
name: bad
layout:
  info_position:
    author:
      placement: outside
      position: middle
      alignment: top-center
      margin: 10
""")
    check_invalid("相对定位环 A<->B", """
name: bad
layout:
  info_position:
    author:
      relative_to: location
      relative_position: below
      cross_alignment: center
    location:
      relative_to: author
      relative_position: above
      cross_alignment: center
""")
    check_invalid("相对节点使用旧 alignment 字段", """
name: bad
layout:
  info_position:
    author:
      relative_to: location
      relative_position: below
      alignment: center
""")
    check_invalid("交叉轴不匹配 above+top", """
name: bad
layout:
  info_position:
    location:
      position: bottom-center
      alignment: top-center
      margin: 10
    author:
      relative_to: location
      relative_position: above
      cross_alignment: top
""")
    check_invalid("交叉轴不匹配 left-of+left", """
name: bad
layout:
  info_position:
    location:
      position: bottom-center
      alignment: top-center
      margin: 10
    author:
      relative_to: location
      relative_position: left-of
      cross_alignment: left
""")
    check_invalid("已删除的 positioning_semantics 字段", """
name: bad
positioning_semantics: v2
layout:
  info_position:
    author:
      position: bottom-center
      alignment: top-center
      margin: 10
""")


if __name__ == "__main__":
    record_variant_baselines()
    record_validation_baselines()
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines) + "\n")
    print(f"\n基线已写入: {OUT_PATH}")
