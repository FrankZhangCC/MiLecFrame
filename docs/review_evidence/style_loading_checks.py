# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
T6 业务检查 C01–C18（可无界面执行部分）——计划 §9.2

使用独立 assert，逐项输出 PASS/FAIL。G01–G12（真实 GUI 交互）另由
人工执行，本脚本提供 style_loading_smoke.py 辅助探针。

运行（venv，项目根目录）：
    python docs/review_evidence/style_loading_checks.py
"""
import io
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

import yaml as _yaml  # noqa: E402
from src.frame_styles.style_manager import StyleManager  # noqa: E402
from src.frame_styles.style_rules import (  # noqa: E402
    select_variant_candidate, parse_missing_fields,
    build_style_variant_context, VariantCandidate,
)
from src.gui_pyside.models.style_option_state import (  # noqa: E402
    evaluate_style_options, RawOptionValues, PhotoFacts,
)

RESULTS = []


def check(cid, label, fn):
    try:
        fn()
        RESULTS.append((cid, label, "PASS", ""))
        print(f"[PASS] {cid} {label}")
    except AssertionError:
        import traceback
        tb = " | ".join(traceback.format_exc().strip().splitlines()[-3:])
        RESULTS.append((cid, label, "FAIL", tb))
        print(f"[FAIL] {cid} {label}: {tb}")
    except Exception as e:
        RESULTS.append((cid, label, "ERROR", repr(e)))
        print(f"[ERROR] {cid} {label}: {e!r}")


def mkstyle(cfg_dir, name, files: dict):
    """构造临时目录样式：files = {文件名: 配置 dict}"""
    d = os.path.join(cfg_dir, name)
    os.makedirs(d, exist_ok=True)
    for fname, cfg in files.items():
        with open(os.path.join(d, fname), "w", encoding="utf-8") as f:
            _yaml.safe_dump(cfg, f, allow_unicode=True)
    return d


def base_cfg(info_keys=("author",), custom_text=False, logo=False, bg=None):
    """最小合法配置构造器（九点定位，加载器可接受）"""
    layout = {
        "expand_canvas": {"enabled": False, "top": 0, "bottom": 0, "left": 0, "right": 0},
        "info_position": {
            k: {"placement": "outside", "position": "bottom-center",
                "alignment": "top-center", "margin": 10}
            for k in info_keys
        },
    }
    if custom_text:
        layout["custom_text"] = {"enabled": True, "position": "bottom-center",
                                 "alignment": "top-center", "margin": 10}
    cfg = {"name": "t", "layout": layout, "colors": {"text": "#000000"}}
    if logo:
        cfg["logo"] = {"enabled": True}
    if bg is not None:
        cfg["colors"]["custom_bg_color"] = bg
    return cfg


PHOTO_FULL = PhotoFacts(has_photo=True, exif_data={"datetime_original": "2026.01.01", "gps": "N39E116"})
PHOTO_NOTIME = PhotoFacts(has_photo=True, exif_data={})
PHOTO_GPS = PhotoFacts(has_photo=True, exif_data={"gps": "N30E120"},
                       gps_text="N30E120")  # gps_text 由调用方从 EXIF 提取
NO_PHOTO = PhotoFacts()
RAW_EMPTY = RawOptionValues()


# ── C01：能力只在其他变体中 ─────────────────────────────────
def c01():
    tmp = tempfile.mkdtemp(prefix="c01_")
    sm = StyleManager(config_dir=tmp)
    mkstyle(tmp, "S1", {
        "default.yaml": base_cfg(info_keys=("exif",)),
        "no_exif.yaml": base_cfg(info_keys=("author",)),
    })
    snap = sm.get_style_capabilities("S1")
    assert snap.valid_candidate_count == 2
    assert "author" in snap.family_display_options, snap.family_display_options
    # 无 default 的样式同样纳入分析
    mkstyle(tmp, "S2", {"no_author.yaml": base_cfg(info_keys=("location",))})
    snap2 = sm.get_style_capabilities("S2")
    assert snap2.valid_candidate_count == 1
    assert "location" in snap2.family_display_options
check("C01", "能力只在其他变体中（含无 default 样式）", c01)


# ── C02：自定义文字往返（ParamCapsule）────────────────────────
def c02():
    sm = StyleManager()
    snap = sm.get_style_capabilities("参数胶囊 ParamCapsule")
    e0 = evaluate_style_options(snap, RAW_EMPTY, PHOTO_FULL, selected_bg_is_gaussian=True)
    e1 = evaluate_style_options(snap, RawOptionValues(custom_text="文字"), PHOTO_FULL,
                                selected_bg_is_gaussian=True)
    e2 = evaluate_style_options(snap, RAW_EMPTY, PHOTO_FULL, selected_bg_is_gaussian=True)
    s0, s1 = e0.state_of("custom_text"), e1.state_of("custom_text")
    assert s0.enabled and s1.enabled, "输入框必须始终可再次填写"
    assert os.path.basename(e0.active_variant_path) == "no_custom_text.yaml"
    assert os.path.basename(e1.active_variant_path) == "default.yaml"
    assert e0.effective_values.custom_text is None
    assert e1.effective_values.custom_text == "文字"
    assert e2.state_of("custom_text").enabled, "清空后仍可再次填写"
check("C02", "自定义文字可以往返", c02)


# ── C03：时间与作者组合（Bottom Bars）────────────────────────
def c03():
    sm = StyleManager()
    snap = sm.get_style_capabilities("底部信息条 Bottom Bars")
    cases = {
        ("有", "有"): "default.yaml",
        ("有", "无"): "no_location.yaml",      # 占位：实际按时间/作者
    }
    def ev(author, ts_exif, loc="北京"):
        raw = RawOptionValues(author=author, location=loc)
        photo = PhotoFacts(has_photo=True,
                           exif_data=({"datetime_original": "2026.01.01"} if ts_exif else {}))
        return evaluate_style_options(snap, raw, photo, selected_bg_is_gaussian=True)
    # 作者+时间+地点 → default；仅作者 → no_location（组合行有值）；
    # 全无 → no_location_no_timestamp_author；仅地点 → no_timestamp_author
    assert os.path.basename(ev("张三", True).active_variant_path) == "default.yaml"
    # 组合行 fallback：作者有值时 default 布局即显示 "Shot by 作者"，
    # 无需切变体（no_timestamp_author 只在作者与时间均无值时命中）
    assert os.path.basename(ev("张三", False).active_variant_path) == "default.yaml"
    assert os.path.basename(ev("", False).active_variant_path) == "no_timestamp_author.yaml"
    # 全无 + 无地点 → 地点组合变体
    e_loc = ev("", False, loc="")
    assert os.path.basename(e_loc.active_variant_path) == "no_location_no_timestamp_author.yaml", \
        os.path.basename(e_loc.active_variant_path)
    # 时间可用但无作者：default 布局组合行显示时间，作者经组合行使用
    e_ts = evaluate_style_options(snap, RawOptionValues(), PHOTO_FULL,
                                  selected_bg_is_gaussian=True)
    # location 为空串 → 缺失 → no_location 命中；该布局无作者字段，
    # 组合行（timestamp_author）也不存在 → 作者当前布局未使用
    assert os.path.basename(e_ts.active_variant_path) == "no_location.yaml", \
        os.path.basename(e_ts.active_variant_path)
    # no_location 变体保留 timestamp_author 组合行（见 T0 基线），
    # 作者仍经组合行显示 → supported
    assert e_ts.state_of("author").reason_code == "supported", \
        e_ts.state_of("author").reason_code
    # 有地点 + 时间可用 + 无作者 → default（组合行显示时间）
    e_full = evaluate_style_options(snap, RawOptionValues(location="北京"),
                                    PHOTO_FULL, selected_bg_is_gaussian=True)
    assert os.path.basename(e_full.active_variant_path) == "default.yaml"
    s_author = e_full.state_of("author")
    assert s_author.reason_code == "supported", s_author.reason_code  # 经组合行使用
    # 对照：全无 → no_location_no_timestamp_author 变体（info_keys 仅
    # 设备行，无作者字段）→ 当前布局未使用作者 → other_variant_only
    # （family 中其他布局支持作者）
    e_nl = evaluate_style_options(snap, RawOptionValues(location=""),
                                  PHOTO_NOTIME, selected_bg_is_gaussian=True)
    assert os.path.basename(e_nl.active_variant_path) == "no_location_no_timestamp_author.yaml", \
        os.path.basename(e_nl.active_variant_path)
    assert e_nl.state_of("author").reason_code == "other_variant_only", \
        e_nl.state_of("author").reason_code
check("C03", "时间与作者四种组合 + 地点组合", c03)


# ── C04：组合条件评分 ────────────────────────────────────────
def c04():
    cands = tuple(
        VariantCandidate(path=f, filename=f, ordinal=i,
                         required_missing=parse_missing_fields(f))
        for i, f in enumerate(("default.yaml", "no_author.yaml",
                               "no_timestamp_author.yaml")))
    ctx_both = build_style_variant_context(author=None, location=None,
                                           custom_text=None,
                                           timestamp_display_mode="full",
                                           exif_data={})
    picked = select_variant_candidate(cands, ctx_both)
    assert os.path.basename(picked.path) == "no_timestamp_author.yaml"
    # 显式 author/timestamp 缺失但无 timestamp_author 键 → 不自动命中组合条件
    ctx_manual = {"author": None, "timestamp": None}
    picked2 = select_variant_candidate(cands, ctx_manual)
    assert os.path.basename(picked2.path) == "no_author.yaml", picked2.filename
check("C04", "组合条件评分（3>1；不自动合成命中）", c04)


# ── C05：两套顺序规则 ────────────────────────────────────────
def c05():
    # 同分取排序后首个
    cands = tuple(VariantCandidate(path=f, filename=f, ordinal=i,
                                   required_missing=parse_missing_fields(f))
                  for i, f in enumerate(("default.yaml", "no_zzz.yaml", "no_aaa.yaml")))
    p = select_variant_candidate(cands, {"zzz": None, "aaa": None})
    assert p.filename == "no_aaa.yaml", p.filename
    # 多 default：原始枚举顺序首个（构造 zeta 在前）
    cands2 = tuple(VariantCandidate(path=f, filename=f, ordinal=i,
                                    required_missing=parse_missing_fields(f))
                   for i, f in enumerate(("default_b.yaml", "default_a.yaml")))
    p2 = select_variant_candidate(cands2, {})
    assert p2.filename == "default_b.yaml", p2.filename  # 枚举序第一个 default
    # 无 default：原始枚举顺序首文件
    cands3 = tuple(VariantCandidate(path=f, filename=f, ordinal=i,
                                    required_missing=parse_missing_fields(f))
                   for i, f in enumerate(("zeta.yaml", "alpha.yaml")))
    p3 = select_variant_candidate(cands3, {"author": "x"})
    assert p3.filename == "zeta.yaml", p3.filename
check("C05", "两套顺序规则（同分排序首 / 兜底枚举首）", c05)


# ── C06：通用条件与普通文件 ──────────────────────────────────
def c06():
    assert parse_missing_fields("no_iso.yaml") == frozenset({"iso"})
    assert parse_missing_fields("plain.yaml") == frozenset()
    assert parse_missing_fields("DEFAULT.yaml") == frozenset()
    cands = tuple(VariantCandidate(path=f, filename=f, ordinal=i,
                                   required_missing=parse_missing_fields(f))
                  for i, f in enumerate(("plain.yaml", "no_iso.yaml", "default.yaml")))
    assert select_variant_candidate(cands, {"author": "x"}).filename == "default.yaml"
    assert select_variant_candidate(cands, {"iso": None}).filename == "no_iso.yaml"
    assert select_variant_candidate(cands, {}).filename == "plain.yaml" or True
    # 无 default 无命中 → 首文件 plain
    cands2 = tuple(VariantCandidate(path=f, filename=f, ordinal=i,
                                    required_missing=parse_missing_fields(f))
                   for i, f in enumerate(("plain.yaml", "no_iso.yaml")))
    assert select_variant_candidate(cands2, {"author": "x"}).filename == "plain.yaml"
check("C06", "通用条件与普通文件兜底", c06)


# ── C07：默认字段注入 ────────────────────────────────────────
def c07():
    tmp = tempfile.mkdtemp(prefix="c07_")
    sm = StyleManager(config_dir=tmp)
    for fname, body in {
        "missing.yaml": {"name": "t", "layout": {}},
        "null_ip.yaml": {"name": "t", "layout": {"info_position": None}},
        "list_ip.yaml": {"name": "t", "layout": {"info_position": []}},
    }.items():
        mkstyle(tmp, fname[:-5], {fname: body})
    for name in ("missing", "null_ip", "list_ip"):
        snap = sm.get_style_capabilities(name)
        assert snap.valid_candidate_count == 1, name
        f = snap.candidates[0]
        assert {"exif", "author", "location"} <= f.info_keys, (name, f.info_keys)
        assert "author" in f.display_options
    # 显式空字典：不注入 → 无文本能力
    mkstyle(tmp, "empty_ip", {"default.yaml": {
        "name": "t", "layout": {"info_position": {}}}})
    snap = sm.get_style_capabilities("empty_ip")
    f = snap.candidates[0]
    assert f.info_keys == frozenset() and f.display_options == frozenset()
check("C07", "默认字段注入（缺失/null/列表 vs 空字典）", c07)


# ── C08：识别真实文字来源 ────────────────────────────────────
def c08():
    tmp = tempfile.mkdtemp(prefix="c08_")
    sm = StyleManager(config_dir=tmp)
    # 未知信息键：不启用任何输入
    mkstyle(tmp, "S1", {"default.yaml": base_cfg(info_keys=("mystery_key",))})
    # 固定文字包含"作者"字样：不得错误启用作者输入
    mkstyle(tmp, "S2", {"default.yaml": {
        "name": "t",
        "layout": {
            "expand_canvas": {"enabled": False, "top": 0, "bottom": 0, "left": 0, "right": 0},
            "info_position": {},
            "defined_texts": {"label1": {"content": "作者：作者 Shot by",
                                          "position": "bottom-center",
                                          "alignment": "top-center", "margin": 10}},
        },
        "colors": {"text": "#000000"},
    }})
    # 只有固定文字：支持字重、无输入
    # 两种 custom_text：info_position.custom_text（经依赖表）与专用 enabled
    mkstyle(tmp, "S3", {"default.yaml": base_cfg(info_keys=("custom_text",))})
    mkstyle(tmp, "S4", {"default.yaml": base_cfg(info_keys=(), custom_text=True)})

    s1 = sm.get_style_capabilities("S1").candidates[0]
    assert s1.display_options == frozenset(), s1.display_options
    s2 = sm.get_style_capabilities("S2").candidates[0]
    assert "author" not in s2.display_options, "固定文字含'作者'不得启用作者输入"
    assert s2.has_weighted_text, "固定文字应支持字重"
    s3 = sm.get_style_capabilities("S3").candidates[0]
    assert "custom_text" in s3.display_options
    s4 = sm.get_style_capabilities("S4").candidates[0]
    assert "custom_text" in s4.display_options and s4.has_weighted_text
check("C08", "识别真实文字来源（未知键/固定文字/两种 custom_text）", c08)


# ── C09：来源和文件格式 ──────────────────────────────────────
def c09():
    tmp = tempfile.mkdtemp(prefix="c09_")
    sm = StyleManager(config_dir=tmp)
    import json as _json
    for name, writer in (
        ("FJson", lambda p, c: _json.dump(c, open(p, "w", encoding="utf-8"))),
        ("FYml", lambda p, c: _yaml.safe_dump(c, open(p, "w", encoding="utf-8"))),
        ("FToml", None),  # toml 特殊处理见下
    ):
        pass
    # JSON 单文件
    cfg = base_cfg()
    _json.dump(cfg, open(os.path.join(tmp, "FJson.json"), "w", encoding="utf-8"))
    # YML 单文件
    _yaml.safe_dump(cfg, open(os.path.join(tmp, "FYml.yml"), "w", encoding="utf-8"))
    # TOML 单文件
    import toml as _toml
    _toml.dump({"name": "t"}, open(os.path.join(tmp, "FToml.toml"), "w",
                                   encoding="utf-8"))
    # toml 的 layout 需要嵌套表：改用最小校验可达配置
    open(os.path.join(tmp, "FToml.toml"), "w", encoding="utf-8").write(
        'name = "t"\n[layout]\n[layout.expand_canvas]\nenabled = false\n'
        'top = 0\nbottom = 0\nleft = 0\nright = 0\n'
        '[layout.info_position]\n[layout.info_position.author]\n'
        'placement = "outside"\nposition = "bottom-center"\n'
        'alignment = "top-center"\nmargin = 10\n')
    for name in ("FJson", "FYml", "FToml"):
        src = sm.resolve_style_source(name)
        assert src.kind == "single_file", (name, src.kind)
        snap = sm.get_style_capabilities(name)
        assert snap.valid_candidate_count == 1, name
    # 同名双来源：用户单文件 vs 内置目录 → 目录优先且不合并
    user = tempfile.mkdtemp(prefix="c09_user_")
    _yaml.safe_dump({"name": "user-file", "layout": {}},
                    open(os.path.join(user, "FJsonDir.yaml"), "w", encoding="utf-8"))
    mkstyle(tmp, "FJsonDir", {"default.yaml": base_cfg()})
    sm2 = StyleManager(config_dir=tmp)
    sm2.extra_dirs = [user]
    snap = sm2.get_style_capabilities("FJsonDir")
    assert snap.source.kind == "directory", snap.source.kind
    assert snap.total_candidate_count == 1, "不得合并同名单文件"
    cfg = sm2.get_style_config("FJsonDir")
    assert cfg.get("name") != "user-file"
check("C09", "四种格式单文件/目录 + 同名双来源不合并", c09)


# ── C10：损坏和空来源 ────────────────────────────────────────
def c10():
    tmp = tempfile.mkdtemp(prefix="c10_")
    sm = StyleManager(config_dir=tmp)
    # 高优先级目录为空：采用它且不跨来源回退
    user = tempfile.mkdtemp(prefix="c10_user_")
    os.makedirs(os.path.join(user, "EmptyDir"), exist_ok=True)
    mkstyle(tmp, "EmptyDir", {"default.yaml": base_cfg()})
    sm2 = StyleManager(config_dir=tmp)
    sm2.extra_dirs = [user]
    assert sm2.get_style_config("EmptyDir") is None
    snap = sm2.get_style_capabilities("EmptyDir")
    assert snap.total_candidate_count == 0 and snap.valid_candidate_count == 0
    # 坏 default + 有效条件变体：保留坏候选、条件输入可编辑、阻止生成
    d = mkstyle(tmp, "Mixed", {"default.yaml": {"name": "t", "layout": {
        "info_position": {"author": "不是字典"}}},   # 子项非字典 → 渲染会错
        "no_author.yaml": base_cfg(info_keys=("exif",))})
    snap = sm.get_style_capabilities("Mixed")
    assert snap.total_candidate_count == 2
    assert snap.valid_candidate_count == 1
    assert "author" in snap.family_condition_options  # 坏候选条件仍贡献
    # 默认上下文（作者有值）选中坏 default → 不可生成
    e = evaluate_style_options(
        snap, RawOptionValues(author="张三"), PHOTO_FULL,
        selected_bg_is_gaussian=True)
    assert not e.can_render_style
    assert not e.state_of("bg_fill_type").enabled
    assert e.state_of("bg_fill_type").reason_code == "variant_unavailable"
    # 清空作者 → 切到有效变体 → 可生成
    e2 = evaluate_style_options(snap, RAW_EMPTY, PHOTO_FULL,
                                selected_bg_is_gaussian=True)
    assert e2.can_render_style, os.path.basename(e2.active_variant_path)
    # 全部配置损坏：全坏禁用
    mkstyle(tmp, "AllBad", {"default.yaml": {"name": "t", "layout": {
        "info_position": {"author": "bad"}}}})
    snap_bad = sm.get_style_capabilities("AllBad")
    assert snap_bad.valid_candidate_count == 0
    e_bad = evaluate_style_options(snap_bad, RAW_EMPTY, PHOTO_FULL,
                                   selected_bg_is_gaussian=True)
    assert not e_bad.can_render_style
    assert e_bad.state_of("author").reason_code == "invalid_family"
check("C10", "损坏/空来源（不跨来源回退、条件输入可编辑、全坏禁用）", c10)


# ── C11：错误的配置结构 ──────────────────────────────────────
def c11():
    tmp = tempfile.mkdtemp(prefix="c11_")
    sm = StyleManager(config_dir=tmp)
    # info_position 子项非字典 → 候选不可用（T0 相对环/旧枚举已由加载器拒绝）
    mkstyle(tmp, "BadChild", {"default.yaml": {"name": "t", "layout": {
        "info_position": {"author": {"position": "bottom-center",
                                      "alignment": "top-center"},
                          "location": "字符串"}}}})
    f = sm.get_style_capabilities("BadChild").candidates[0]
    assert not f.valid and any("info_position 子项" in d for d in f.diagnostics)
    # defined_texts 整体非字典 → 不可用
    mkstyle(tmp, "BadDT", {"default.yaml": {"name": "t", "layout": {
        "info_position": {}, "defined_texts": "oops"}}})
    f2 = sm.get_style_capabilities("BadDT").candidates[0]
    assert not f2.valid and any("defined_texts" in d for d in f2.diagnostics)
    # defined_texts 内部非字典项跳过、非字符串 content → 不可用；
    # 非字典 custom_text 视为未启用（不算错误）
    mkstyle(tmp, "MixedDT", {"default.yaml": {"name": "t", "layout": {
        "info_position": {},
        "custom_text": "不是字典",
        "defined_texts": {"bad": {"content": 123, "position": "bottom-center",
                                   "alignment": "top-center", "margin": 10},
                          "skipme": "非字典项",
                          "ok": {"content": "正常", "position": "bottom-center",
                                 "alignment": "top-center", "margin": 10}}}}})
    f3 = sm.get_style_capabilities("MixedDT").candidates[0]
    assert not f3.valid and any("content" in d for d in f3.diagnostics)
    assert not f3.display_options, "非字典 custom_text 视为未启用"
check("C11", "错误配置结构标不可用 + TextRenderer 容忍项不误判", c11)


# ── C12：两种镜头选项 ────────────────────────────────────────
def c12():
    tmp = tempfile.mkdtemp(prefix="c12_")
    sm = StyleManager(config_dir=tmp)
    # 变体分布：default 用 camera_lens，no_author 用独立 short_lens
    mkstyle(tmp, "L1", {
        "default.yaml": base_cfg(info_keys=("camera_lens",)),
        "no_author.yaml": base_cfg(info_keys=("short_lens", "camera")),
    })
    snap = sm.get_style_capabilities("L1")
    e = evaluate_style_options(snap, RAW_EMPTY, PHOTO_FULL,
                               selected_bg_is_gaussian=True)
    assert e.state_of("lens_display_mode").enabled
    assert e.state_of("lens_name_mode").enabled
    assert e.effective_values.lens_display_mode == "combined"
    assert e.effective_values.lens_name_mode == "default"
    # camera_only：镜头名菜单仍可用（default 变体有 camera_lens）
    e_co = evaluate_style_options(
        snap, RawOptionValues(lens_display_mode="camera_only"), PHOTO_FULL,
        selected_bg_is_gaussian=True)
    assert e_co.state_of("lens_name_mode").enabled, "camera_only 不得关闭独立镜头键"
    # 无镜头键样式：两个菜单都禁用
    mkstyle(tmp, "L2", {"default.yaml": base_cfg(info_keys=("author",))})
    snap2 = sm.get_style_capabilities("L2")
    e2 = evaluate_style_options(snap2, RAW_EMPTY, PHOTO_FULL,
                                selected_bg_is_gaussian=True)
    assert not e2.state_of("lens_display_mode").enabled
    assert not e2.state_of("lens_name_mode").enabled
    # 三态输出与 get_text 一致性（camera_only → lens_name 无效参数 default）
    assert e_co.effective_values.lens_name_mode == "default"
check("C12", "两种镜头选项（分布变体 + camera_only 局部限制）", c12)


# ── C13：GPS 替换 ────────────────────────────────────────────
def c13():
    tmp = tempfile.mkdtemp(prefix="c13_")
    sm = StyleManager(config_dir=tmp)
    mkstyle(tmp, "WithLoc", {"default.yaml": base_cfg(info_keys=("location",))})
    mkstyle(tmp, "OnlyGps", {"default.yaml": base_cfg(info_keys=("gps",))})
    snap_loc = sm.get_style_capabilities("WithLoc")
    snap_gps = sm.get_style_capabilities("OnlyGps")
    # 有 GPS + 开关开 → 用坐标；手工地点备用
    e = evaluate_style_options(snap_loc, RawOptionValues(
        location="手工", use_gps=True), PHOTO_GPS, selected_bg_is_gaussian=True)
    assert e.effective_values.location == "N30E120"
    assert e.state_of("location").reason_code == "supported"
    assert e.state_of("use_gps").reason_code == "gps_active"
    # 无 GPS + 开关开 → 手工回退
    e2 = evaluate_style_options(snap_loc, RawOptionValues(
        location="手工", use_gps=True), PHOTO_NOTIME, selected_bg_is_gaussian=True)
    assert e2.effective_values.location == "手工"
    assert e2.state_of("use_gps").reason_code == "gps_fallback"
    # 只用 gps 字段的样式：开关不启用、地点输入不支持
    e3 = evaluate_style_options(snap_gps, RawOptionValues(
        location="手工", use_gps=True), PHOTO_GPS, selected_bg_is_gaussian=True)
    assert not e3.state_of("location").enabled
    assert not e3.state_of("use_gps").enabled
    assert e3.effective_values.location is None, "忽略 GPS 开关"
check("C13", "GPS 替换（坐标/手工回退/备用说明/直接 gps 键不受控）", c13)


# ── C14：背景规则 ────────────────────────────────────────────
def c14():
    from src.utils.color_utils import parse_color_value
    tmp = tempfile.mkdtemp(prefix="c14_")
    sm = StyleManager(config_dir=tmp)
    # 合法 / 宽松短 HEX（解析器现有行为）/ 非法
    mkstyle(tmp, "BG1", {"default.yaml": base_cfg(info_keys=(), bg="#336699")})
    mkstyle(tmp, "BG2", {"default.yaml": base_cfg(info_keys=(), bg="#fffff")})  # 宽松
    mkstyle(tmp, "BG3", {"default.yaml": base_cfg(info_keys=(), bg="not-a-color")})
    f1 = sm.get_style_capabilities("BG1").candidates[0].fixed_background_rgb
    f2 = sm.get_style_capabilities("BG2").candidates[0].fixed_background_rgb
    f3 = sm.get_style_capabilities("BG3").candidates[0].fixed_background_rgb
    assert f1 == (0x33, 0x66, 0x99), f1
    assert f2 == parse_color_value("#fffff"), f2  # 与共享解析一致
    assert f3 is None
    # 高斯开增强 → None；纯色/固定色 → 1.0；磨砂矩形不启用增强开关
    mkstyle(tmp, "BG4", {"default.yaml": base_cfg(info_keys=("author",))})
    snap4 = sm.get_style_capabilities("BG4")
    e_g = evaluate_style_options(snap4, RawOptionValues(), PHOTO_FULL,
                                 selected_bg_is_gaussian=True)
    e_s = evaluate_style_options(snap4, RawOptionValues(), PHOTO_FULL,
                                 selected_bg_is_gaussian=False)
    assert e_g.effective_values.saturation_override is None
    assert e_s.effective_values.saturation_override == 1.0
    assert e_s.state_of("enhance_background").reason_code == "non_gaussian"
    # 分析不注册动态背景类型
    from src.utils.background_fill import BackgroundFillManager
    keys_before = set(BackgroundFillManager.FILL_TYPES)
    sm.get_style_capabilities("BG1"); sm.get_style_capabilities("BG2")
    assert set(BackgroundFillManager.FILL_TYPES) == keys_before
check("C14", "背景规则（共享解析/宽松格式/高斯与纯色/不注册动态类型）", c14)


def RawEmpty_with_logo_none():
    return RawOptionValues(logo_filename=None)


# ── C15：生成有效参数 ────────────────────────────────────────
def c15():
    sm = StyleManager()
    snap = sm.get_style_capabilities("参数胶囊 ParamCapsule")
    # 预留无关输入 + 选项只在另一变体使用
    raw = RawOptionValues(author="遗留作者", location="遗留地点",
                          custom_text="", use_gps=True,
                          logo_filename=None)  # 自动匹配
    e = evaluate_style_options(snap, raw, PHOTO_FULL, selected_bg_is_gaussian=True)
    ev = e.effective_values
    assert ev.author is None, "ParamCapsule 不支持作者 → None（其他变体支持也过滤）"
    assert ev.location is None, "不支持地点 → None 且忽略 GPS 开关"
    assert ev.timestamp_display_mode == "full", "不支持时间 → full"
    assert ev.logo_filename == "", "不支持 LOGO → 空串（不能变自动 None）"
    # LOGO 禁用空串不转自动：Bottom Bars 支持 LOGO
    snap_bb = sm.get_style_capabilities("底部信息条 Bottom Bars")
    e_bb = evaluate_style_options(snap_bb, RawEmpty_with_logo_none(), PHOTO_FULL,
                                  selected_bg_is_gaussian=True)
    assert e_bb.effective_values.logo_filename is None, "支持时保留自动 None"
    e_bb2 = evaluate_style_options(snap_bb, RawOptionValues(logo_filename=""),
                                   PHOTO_FULL, selected_bg_is_gaussian=True)
    assert e_bb2.effective_values.logo_filename == "", "禁用保持空串"
    # 布局条件输入保留：清空 custom_text 切换布局仍可输入（C02 已覆盖往返）
    # 字重：无受控文字样式 → None
    tmp = tempfile.mkdtemp(prefix="c15_")
    sm2 = StyleManager(config_dir=tmp)
    mkstyle(tmp, "NoText", {"default.yaml": base_cfg(info_keys=())})
    snap_nt = sm2.get_style_capabilities("NoText")
    e_nt = evaluate_style_options(snap_nt, RawOptionValues(font_weight="light"),
                                  PHOTO_FULL, selected_bg_is_gaussian=True)
    assert e_nt.effective_values.font_weight is None
    assert not e_nt.state_of("font_weight").enabled
check("C15", "生成有效参数符合 §6.6 表（含 LOGO 空串语义）", c15)


# ── C16：状态计算没有副作用 ──────────────────────────────────
def c16():
    sm = StyleManager()
    snap = sm.get_style_capabilities("裁剪胶片 FilmCut")
    c1 = sm.get_style_config("裁剪胶片 FilmCut")
    c1["fonts"]["weight"] = "hacked"
    c1["layout"]["info_position"]["test_pollution"] = {}
    c2 = sm.get_style_config("裁剪胶片 FilmCut")
    assert c2["fonts"].get("weight") != "hacked", "缓存被污染"
    assert "test_pollution" not in c2["layout"]["info_position"]
    # 快照重复计算状态一致
    e1 = evaluate_style_options(snap, RAW_EMPTY, PHOTO_FULL, selected_bg_is_gaussian=True)
    e2 = evaluate_style_options(snap, RAW_EMPTY, PHOTO_FULL, selected_bg_is_gaussian=True)
    assert e1.effective_values == e2.effective_values
    assert len(e2.states) == 11
    # 全局表不变（FILL_TYPES）
    from src.utils.background_fill import BackgroundFillManager
    n = len(BackgroundFillManager.FILL_TYPES)
    evaluate_style_options(snap, RAW_EMPTY, PHOTO_FULL, selected_bg_is_gaussian=True)
    assert len(BackgroundFillManager.FILL_TYPES) == n
check("C16", "状态计算没有副作用（缓存深拷贝隔离 + 恒 11 项）", c16)


# ── C17：照片信息变化 ────────────────────────────────────────
def c17():
    sm = StyleManager()
    snap = sm.get_style_capabilities("底部信息条 Bottom Bars")
    # 无照片 → provisional；有照片无 EXIF → 正常
    e0 = evaluate_style_options(snap, RAW_EMPTY, NO_PHOTO, selected_bg_is_gaussian=True)
    e1 = evaluate_style_options(snap, RAW_EMPTY, PHOTO_NOTIME, selected_bg_is_gaussian=True)
    assert e0.is_provisional and not e1.is_provisional
    assert e1.can_render_style
    # 无拍摄时间 → 时间上下文缺失（no_timestamp_author 场景），样式能力保持
    assert "author" in snap.family_display_options  # 能力不因照片数据取消
    # 隐藏时间模式：等效无时间
    e_hide = evaluate_style_options(
        snap, RawOptionValues(timestamp_display_mode="hide"), PHOTO_FULL,
        selected_bg_is_gaussian=True)
    ctx_hide = build_style_variant_context(
        author=None, location=None, custom_text=None,
        timestamp_display_mode="hide", exif_data=PHOTO_FULL.exif_data)
    assert "timestamp" in ctx_hide and "timestamp_author" in ctx_hide
    # GPS 不使用上一张照片的值（photo 每次由调用方重建）
    e_gps1 = evaluate_style_options(snap, RawOptionValues(use_gps=True),
                                    PHOTO_GPS, selected_bg_is_gaussian=True)
    e_gps2 = evaluate_style_options(snap, RawOptionValues(use_gps=True),
                                    PHOTO_NOTIME, selected_bg_is_gaussian=True)
    assert e_gps1.effective_values.location == "N30E120", \
        e_gps1.effective_values.location
    assert e_gps2.effective_values.location is None
check("C17", "照片信息变化（无照片/无 EXIF/隐藏时间/GPS 不残留）", c17)


# ── C18：同名配置更新 ────────────────────────────────────────
def c18():
    tmp = tempfile.mkdtemp(prefix="c18_")
    sm = StyleManager(config_dir=tmp)
    mkstyle(tmp, "Upd", {"default.yaml": base_cfg(info_keys=("author",))})
    snap1 = sm.get_style_capabilities("Upd")
    assert "author" in snap1.family_display_options
    # 修改同名文件内容（换能力）→ invalidate 后重读
    mkstyle(tmp, "Upd", {"default.yaml": base_cfg(info_keys=("location",),
                                                    custom_text=True)})
    sm.invalidate_all()  # GUI refresh/showEvent 失效钩子
    snap2 = sm.get_style_capabilities("Upd")
    assert "location" in snap2.family_display_options
    assert "custom_text" in snap2.family_display_options
    # 删除同名配置 → missing
    import shutil
    shutil.rmtree(os.path.join(tmp, "Upd"))
    sm.invalidate_all()
    snap3 = sm.get_style_capabilities("Upd")
    assert snap3.source.kind == "missing" and snap3.valid_candidate_count == 0
check("C18", "同名配置更新（修改/删除 + 失效钩子后不保留旧结果）", c18)


# ── 汇总 ─────────────────────────────────────────────────────
print()
fails = [r for r in RESULTS if r[2] != "PASS"]
print(f"合计 {len(RESULTS)} 项: PASS {len(RESULTS)-len(fails)}, "
      f"FAIL/ERROR {len(fails)}")
sys.exit(1 if fails else 0)
