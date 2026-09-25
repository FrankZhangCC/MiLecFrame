# -*- coding: utf-8 -*-
"""两线版本同步脚本（dev / release）。

模型（2026-09-25 起；mainline 已废除——其历史版本 commit 由 v*-dev tag
变达保留，不再有任何分支引用）：
    dev     完整开发历史（feat/fix/docs 细节提交，永不归档 / 永不 reset），
            里程碑提交（如"chore: 升版本 x.y.z-dev"）上打轻量 vX.Y.Z-dev tag
    release 干净发行链（orphan 起步，与 dev 无共同祖先），每个发行 commit
            的树 = dev 某个时点的快照（read-tree，不含 dev 细节历史），
            首行 "vX.Y.Z: 发行说明"，带注解 tag vX.Y.Z（同源号去 -dev）

版本同源规则不变：dev 里程碑 v2.6.0-dev ↔ 发行 v2.6.0（同号去 -dev）；
补丁修复走 patch 号递增（v2.6.0 → v2.6.1）。

用法：
    python tools/release_sync.py check
        # 两线体检：发行链完整性 / 同源 tag 对齐 / 版本号与文档一致性

    python tools/release_sync.py milestone <ver> [--push]
        # 在 dev HEAD 打轻量 vX.Y.Z-dev 里程碑 tag（ver 形如 2.7.0-dev）
        # 前置：dev 上已完成"chore: 升版本"提交（_version.py 与
        # CHANGELOG.md 条目均已就绪并提交）

    python tools/release_sync.py release <ver> --msg "发行说明"
            [--from <ref>] [--notes-file <path>] [--push]
        # dev → release 发行（ver 形如 2.6.0，无 -dev 后缀）：临时
        # worktree 中 read-tree 快照 <from>（默认 dev HEAD）+ 发行准备
        # （_version.py 去 -dev、可选以 --notes-file 覆盖
        # CHANGELOG_RELEASE.md）+ 发行 commit + 注解 tag
        # 前置：同源 v<ver>-dev 里程碑 tag 已存在

    python tools/release_sync.py cherry <commit> <ver> --msg "补丁说明" [--push]
        # dev 上的修复 commit → cherry-pick 到 release 干净链上补丁发行
        # （ver 形如 2.6.1，patch 号递增），并在 dev 源 commit 上打同源
        # v<ver>-dev 里程碑 tag

约定：
    - release / cherry 全程在临时 worktree 中操作，不触碰主工作区
      （dev 分支与未提交改动不受影响），因此执行时不要求工作区干净。
    - milestone tag 为轻量 tag，发行 tag 为注解 tag。
    - 脚本不提供 force push；release 分支受保护，历史不可改写。
    - dev 分支只在本机（不推送 origin），--push 只推送 tag 与 release 分支。
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

# Windows 控制台默认 GBK，强制 UTF-8 输出避免 ✗/✓ 等符号编码崩溃
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# 项目根目录（脚本位于 <root>/tools/ 下）
ROOT = Path(__file__).resolve().parent.parent

# 两线分支名（mainline 已废除）
BRANCH_DEV = "dev"
BRANCH_RELEASE = "release"

# 版本号正则：2.6.0-dev / v2.6.0 / v2.6.1 均可，split 后比较
VER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-(dev))?$")

# CHANGELOG 条目行示例："## v2.6.0-dev (2026-09-22)"，匹配时转义版本号
CHANGELOG_ENTRY_RE = re.compile(r"^##\s+v(\d+\.\d+\.\d+(?:-dev)?)\b", re.MULTILINE)

# 发行 commit 首行格式："v2.6.0: 发行说明"
RELEASE_SUBJECT_RE = re.compile(r"^(v\d+\.\d+\.\d+):")

# -dev 里程碑 tag 名格式："v2.6.0-dev"
DEV_TAG_RE = re.compile(r"^v(\d+\.\d+\.\d+)-dev$")

# 发行 tag 名格式："v2.6.0"（排除 -dev / pre-rebuild / archive 等非发行 tag）
RELEASE_TAG_RE = re.compile(r"^v(\d+\.\d+\.\d+)$")


class SyncError(RuntimeError):
    """同步流程中止异常（携带面向用户的错误提示）。"""


def git(*args, cwd=None, check=True, env=None):
    """执行 git 命令并返回 stdout（UTF-8 解码，去首尾空白）。

    参数:
        cwd: 工作目录（默认项目根）。
        check: True 时命令失败抛出 SyncError。
    """
    import os

    e = os.environ.copy()
    if env:
        e.update(env)
    r = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd or str(ROOT),
        env=e,
    )
    if check and r.returncode != 0:
        raise SyncError(f"git {' '.join(args)} 失败:\n{r.stderr.strip()}")
    return r.stdout.strip()


def is_ancestor(commit, branch):
    """判断 commit 是否可从 branch 到达（利用 --is-ancestor 的退出码）。"""
    import os

    r = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, branch],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        env=os.environ.copy(),
    )
    return r.returncode == 0


def parse_version(ver):
    """解析版本号字符串，返回 (major, minor, patch, suffix)。

    suffix: 'dev' 或 ''（公开发行）。
    返回元组可直接用于元组比较（'' < 'dev'，均参与比较即可）。
    """
    m = VER_RE.match(ver.strip())
    if not m:
        raise SyncError(f"版本号格式非法: {ver!r}（应为 X.Y.Z 或 X.Y.Z-dev）")
    major, minor, patch, suffix = m.groups()
    return (int(major), int(minor), int(patch), suffix or "")


def format_version(t):
    """把 parse_version 结果格式化回字符串（不含 v 前缀）。"""
    major, minor, patch, suffix = t
    base = f"{major}.{minor}.{patch}"
    return f"{base}-{suffix}" if suffix else base


def tag_name(t):
    """生成 tag 名：v2.6.0-dev / v2.6.0。"""
    return "v" + format_version(t)


def current_branch():
    """返回当前分支名。"""
    return git("rev-parse", "--abbrev-ref", "HEAD")


def ensure_branch(branch):
    """确保当前位于指定分支（流程约束，避免在错误分支上打 tag）。"""
    cur = current_branch()
    if cur != branch:
        raise SyncError(f"当前分支为 {cur}，此命令必须在 {branch} 分支上执行。")


def latest_dev_tag():
    """返回版本号最大的 -dev 里程碑 tag（无则 None）。

    不用 git describe：里程碑 tag 散布在 dev 可达历史（含已废除 mainline
    的旧版本 commit）上，describe 按拓扑距离取"最近"，未必是版本号最大。
    """
    best, best_t = None, None
    for t in git("tag", "-l", check=False).splitlines():
        m = DEV_TAG_RE.match(t)
        if not m:
            continue
        try:
            v = parse_version(t)
        except SyncError:
            continue
        if best is None or v > best:
            best, best_t = v, t
    return best_t


def latest_release_tag():
    """返回版本号最大的发行 tag（无则 None）。"""
    best, best_t = None, None
    for t in git("tag", "-l", check=False).splitlines():
        if not RELEASE_TAG_RE.match(t):
            continue
        try:
            v = parse_version(t)
        except SyncError:
            continue
        if best is None or v > best:
            best, best_t = v, t
    return best_t


def require_newer(new_ver, old_tag):
    """校验新版本号必须大于分支上的最新 tag。"""
    if old_tag is None:
        return
    try:
        old = parse_version(old_tag)
    except SyncError:
        # 历史遗留 tag（如 v0.1.0-release）解析不了的按可比较处理：都兼容即可
        return
    if new_ver <= old:
        raise SyncError(f"新版本 {format_version(new_ver)} 必须大于当前最新 tag {old_tag}。")


def read_version_py_at(ref):
    """读取指定 ref 的 src/_version.py 中的 __version__ 字符串。

    读分支头（而非工作区文件）：工作区可以有未提交改动，版本校验一律
    以分支头为准。
    """
    text = git("show", f"{ref}:src/_version.py", check=False)
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', text or "", re.MULTILINE)
    if not m:
        raise SyncError(f"无法从 {ref}:src/_version.py 读取 __version__。")
    return m.group(1)


def write_version_py(ver_tuple, path):
    """按新版本号重写指定 _version.py 的 __version__ 与 __version_info__。

    dev 后缀版本写 'dev'，公开发行写 'release'（与 release 线历史一致）。
    path 指向临时 worktree 内的文件，主工作区的 _version.py 不受影响。
    """
    major, minor, patch, suffix = ver_tuple
    version_str = format_version(ver_tuple)
    tag_str = suffix if suffix else "release"
    text = path.read_text(encoding="utf-8")
    text = re.sub(
        r'^__version__\s*=\s*"[^"]*"',
        f'__version__ = "{version_str}"',
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^__version_info__\s*=\s*\([^)]*\)",
        f"__version_info__ = ({major}, {minor}, {patch}, {tag_str!r})",
        text,
        flags=re.MULTILINE,
    )
    path.write_text(text, encoding="utf-8")


def changelog_text_has_version(text, ver_tuple):
    """检查一段 CHANGELOG 文本是否含指定版本条目。"""
    target = format_version(ver_tuple)
    for m in CHANGELOG_ENTRY_RE.finditer(text or ""):
        if m.group(1) == target:
            return True
    return False


def changelog_has_version(changelog, ver_tuple, ref=None):
    """检查 CHANGELOG.md / CHANGELOG_RELEASE.md 是否含指定版本条目。

    ref 给定时读该 ref 的文件内容（分支头），否则读主工作区文件。
    """
    if ref:
        text = git("show", f"{ref}:{changelog}", check=False)
    else:
        path = ROOT / changelog
        text = path.read_text(encoding="utf-8") if path.exists() else ""
    return changelog_text_has_version(text, ver_tuple)


def commit_message_for_cherry(tag, src_subject):
    """生成 cherry-pick 提交消息：版本 tag + 原提交主题（去掉 conventional 前缀）。"""
    subject = re.sub(
        r"^(feat|fix|docs|chore|refactor|style|test)(\(.+?\))?!?: ",
        "",
        src_subject.strip(),
    )
    return f"{tag}: {subject}"


def do_push(refs):
    """推送到 origin：逐个推送分支 / tag（轻量与注解 tag 均可直接推）。"""
    for ref in refs:
        git("push", "origin", ref)


@contextmanager
def temp_worktree(ref):
    """创建指向 ref 的临时 worktree，yield 其路径，退出时强制清理。

    release / cherry 的全部 git 写操作都在 worktree 内进行：
    主工作区（dev 分支与用户的未提交改动）完全不受影响。
    """
    tmp = tempfile.mkdtemp(prefix="release_sync_")
    path = Path(tmp) / "wt"
    git("worktree", "add", "--detach", str(path), ref)
    try:
        yield path
    finally:
        # 无论成功失败都清理 worktree（--force 兜底残留改动），再删临时目录
        git("worktree", "remove", "--force", str(path), check=False)
        shutil.rmtree(tmp, ignore_errors=True)


def ensure_release_branch():
    """确保 release 分支已存在（orphan 首发由人工或脚本首次运行建立）。"""
    if not git("rev-parse", "--verify", BRANCH_RELEASE, check=False):
        raise SyncError(
            f"{BRANCH_RELEASE} 分支不存在。请先执行 release 命令完成首发"
            "（脚本会自动 orphan 起步），或手动创建该分支。"
        )


def cmd_check(_args):
    """两线体检：发行链完整性、同源 tag 对齐、版本号与文档一致性。"""
    problems = []

    # 1. 两线分支存在性
    for b in (BRANCH_DEV, BRANCH_RELEASE):
        if not git("rev-parse", "--verify", b, check=False):
            problems.append(f"分支 {b} 不存在")

    has_release = bool(git("rev-parse", "--verify", BRANCH_RELEASE, check=False))

    # 2. release 发行链：沿第一父遍历，每个发行 commit 首行 vX.Y.Z: 前缀
    #    且恰好带一个同名 tag（orphan 链上全部是发行 commit，无链尾特例）
    if has_release:
        commits = git("log", "--first-parent", "--format=%H %s", BRANCH_RELEASE).splitlines()
        for line in commits:
            h, subject = line.split(" ", 1)
            m = RELEASE_SUBJECT_RE.match(subject)
            if not m:
                problems.append(f"release commit {h[:12]} 首行无发行前缀: {subject[:50]}")
                continue
            expected = m.group(1)
            tags = git("tag", "--points-at", h, check=False).splitlines()
            tags = [t for t in tags if t and not t.startswith("pre-rebuild")]
            if expected not in tags:
                problems.append(f"release commit {h[:12]} 缺少 tag {expected}")
            if len(tags) != 1:
                problems.append(f"release commit {h[:12]} tag 数异常: {tags}")

    # 3. 发行 tag 指向的 commit 首行应为发行前缀
    #    注解 tag 的 rev-parse 返回 tag 对象本身，须解引用到 commit
    for t in git("tag", "-l", check=False).splitlines():
        if not RELEASE_TAG_RE.match(t):
            continue
        h = git("rev-parse", f"{t}^{{commit}}", check=False)
        subject = git("show", "-s", "--format=%s", h, check=False)
        if not RELEASE_SUBJECT_RE.match(subject):
            problems.append(f"发行 tag {t} 指向的 commit {h[:12]} 首行无发行前缀: {subject[:50]}")

    # 4. 同源对齐：每个发行 tag vX.Y.Z 应存在 v(X.Y.Z)-dev 里程碑 tag
    for t in git("tag", "-l", check=False).splitlines():
        if not RELEASE_TAG_RE.match(t):
            continue
        if not git("rev-parse", "--verify", f"{t}-dev", check=False):
            problems.append(f"发行 tag {t} 缺少同源里程碑 tag {t}-dev")

    # 5. -dev 里程碑 tag 可达性：应全部可从 dev 到达
    #    （历史里程碑 tag 指向已废除 mainline 的版本 commit，靠 dev 历史
    #    中的旧 merge 链保持可达；若不可达说明有孤儿 tag）
    for t in git("tag", "-l", check=False).splitlines():
        if not DEV_TAG_RE.match(t):
            continue
        h = git("rev-parse", f"{t}^{{commit}}", check=False)
        if not is_ancestor(h, BRANCH_DEV):
            problems.append(f"里程碑 tag {t} 指向的 commit {h[:12]} 不可从 dev 到达")

    # 6. _version.py 与最新 tag 一致
    latest_rel = latest_release_tag()
    latest_dev = latest_dev_tag()
    if has_release and latest_rel:
        file_ver = read_version_py_at(BRANCH_RELEASE)
        if tag_name(parse_version(file_ver)) != latest_rel:
            problems.append(
                f"{BRANCH_RELEASE} 的 _version.py={file_ver} 与最新发行 tag {latest_rel} 不一致"
            )
    if latest_dev:
        file_ver = read_version_py_at(BRANCH_DEV)
        if tag_name(parse_version(file_ver)) != latest_dev:
            problems.append(
                f"{BRANCH_DEV} 的 _version.py={file_ver} 与最新里程碑 tag {latest_dev} 不一致"
                "（若已完成升版本提交请打 milestone tag）"
            )

    # 7. CHANGELOG 条目：最新版本均应有对应条目
    if latest_dev and not changelog_has_version("CHANGELOG.md", parse_version(latest_dev), ref=BRANCH_DEV):
        problems.append(f"CHANGELOG.md 缺少 {latest_dev} 条目")
    if has_release and latest_rel and not changelog_has_version(
        "CHANGELOG_RELEASE.md", parse_version(latest_rel), ref=BRANCH_RELEASE
    ):
        problems.append(f"CHANGELOG_RELEASE.md（release 分支）缺少 {latest_rel} 条目")

    # 8. 提示性信息：里程碑后 dev 的新提交、工作区状态
    ahead = ""
    if latest_dev:
        ahead = git("log", "--oneline", f"{latest_dev}..{BRANCH_DEV}", check=False)
    dirty = git("status", "--porcelain", check=False)

    print("=== 两线体检 ===")
    print(f"dev:       {git('rev-parse', '--short', BRANCH_DEV)} (最新里程碑: {latest_dev})")
    print(
        f"release:   {git('rev-parse', '--short', BRANCH_RELEASE) if has_release else '(不存在)'}"
        f" (最新发行: {latest_rel})"
    )
    if ahead:
        print(f"提示: dev 自 {latest_dev} 后有 {len(ahead.splitlines())} 个未发行提交")
    if dirty:
        print("提示: 工作区有未提交改动（不影响同步命令）")
    if problems:
        print("\n发现问题:")
        for p in problems:
            print(f"  ✗ {p}")
        sys.exit(1)
    print("\n✓ 两线状态健康")


def cmd_milestone(args):
    """dev HEAD 打轻量 -dev 里程碑 tag（不触碰工作区）。"""
    ensure_branch(BRANCH_DEV)
    ver = parse_version(args.ver)
    if ver[3] != "dev":
        raise SyncError("里程碑版本号必须带 -dev 后缀，如 2.7.0-dev。")
    tag = tag_name(ver)
    require_newer(ver, latest_dev_tag())

    # dev 分支头的 _version.py 必须已写好该版本号（升版本提交应先行）
    file_ver = read_version_py_at(BRANCH_DEV)
    if file_ver != format_version(ver):
        raise SyncError(
            f"dev HEAD 的 _version.py={file_ver} 与里程碑版本 {format_version(ver)} 不一致，"
            "请先提交\"chore: 升版本\"（_version.py + CHANGELOG.md 条目）再打 tag。"
        )
    if not changelog_has_version("CHANGELOG.md", ver, ref=BRANCH_DEV):
        raise SyncError(f"CHANGELOG.md 缺少 {tag} 条目，请先在 dev 上补充。")

    print(f"打里程碑 tag {tag} → dev HEAD")
    git("tag", tag, BRANCH_DEV)

    if args.push:
        print("推送 tag 到 origin ...")
        do_push([tag])

    print(f"✓ 里程碑 {tag} 已创建" + ("并推送" if args.push else "（本地）"))


def cmd_release(args):
    """dev → release 干净发行链：read-tree 快照 + 发行准备 + 注解 tag。

    全程在临时 worktree 中进行：
      - release 分支不存在 → orphan 起步（首发场景，历史从 v2.6.0 起）
      - release 分支已存在 → 检出 release，在其 HEAD 上接续快照
    快照树 = <from> 的树（默认 dev HEAD），因此发行 commit 的 diff
    （相对上一发行 commit）天然只含两次发行之间的净变化，
    dev 的任务级提交历史不会进入 release 链。
    """
    ver = parse_version(args.ver)
    if ver[3]:
        raise SyncError("发行版本号不能带 -dev 后缀，如 2.6.0。")
    tag = tag_name(ver)
    require_newer(ver, latest_release_tag())

    # 同源校验：发行前必须已有 v<ver>-dev 里程碑（版本同源规则）
    milestone_tag = tag + "-dev"
    if not git("rev-parse", "--verify", milestone_tag, check=False):
        raise SyncError(
            f"缺少同源里程碑 tag {milestone_tag}，请先在 dev 上执行"
            f"\"release_sync.py milestone {format_version(ver)}-dev\"。"
        )
    if not args.msg:
        raise SyncError("必须提供 --msg 发行说明。")

    src = args.from_ref or BRANCH_DEV
    if not git("rev-parse", "--verify", src, check=False):
        raise SyncError(f"快照源 {src} 不存在。")

    has_release = bool(git("rev-parse", "--verify", BRANCH_RELEASE, check=False))

    with temp_worktree(src if not has_release else BRANCH_RELEASE) as path:
        if not has_release:
            # 首发：orphan 起步（无父发行 commit，release 链与 dev 无共同祖先）
            print(f"[1/4] release 分支不存在，orphan 起步（快照源 {src}）")
            git("checkout", "--orphan", BRANCH_RELEASE, cwd=str(path))
        else:
            print(f"[1/4] 快照 {src} → release HEAD（临时 worktree）")

        # read-tree 快照：<from> 的树覆盖 worktree 的索引与工作树
        src_tree = git("rev-parse", f"{src}^{{tree}}")
        git("read-tree", "--reset", "-u", src_tree, cwd=str(path))

        # 发行准备 1：_version.py 去 -dev 后缀
        print(f"[2/4] 发行准备: _version.py = {format_version(ver)}")
        write_version_py(ver, path / "src" / "_version.py")

        # 发行准备 2：--notes-file 给定时以该文件覆盖 CHANGELOG_RELEASE.md
        # （首发场景用于抛掉历史发行条目，从新号段重新累积）
        if args.notes_file:
            notes_src = Path(args.notes_file)
            if not notes_src.is_absolute():
                notes_src = ROOT / notes_src
            if not notes_src.exists():
                raise SyncError(f"--notes-file 文件不存在: {notes_src}")
            shutil.copyfile(notes_src, path / "CHANGELOG_RELEASE.md")
            print(f"          CHANGELOG_RELEASE.md 由 {notes_src.name} 覆盖")

        # 发行校验：CHANGELOG_RELEASE.md 必须含本发行条目
        notes_text = (path / "CHANGELOG_RELEASE.md").read_text(encoding="utf-8")
        if not changelog_text_has_version(notes_text, ver):
            raise SyncError(
                f"CHANGELOG_RELEASE.md 缺少 {tag} 条目，请先补充（或用 --notes-file 传入）。"
            )

        print(f"[3/4] 发行 commit + 注解 tag {tag}")
        git("add", "-A", cwd=str(path))
        git("commit", "-m", f"{tag}: {args.msg}", cwd=str(path))
        git("tag", "-a", tag, "-m", f"{tag}: {args.msg}", cwd=str(path))

        print("[4/4] 清理临时 worktree")

    if args.push:
        print("推送到 origin ...")
        do_push([BRANCH_RELEASE, tag])

    print(f"✓ release 新发行 {tag} 已创建" + ("并推送" if args.push else "（本地）"))
    print("  发行 commit 为 dev 快照（干净发行链），可在 release 分支上打包发行。")


def cmd_cherry(args):
    """dev 的单点修复 → cherry-pick 到 release 干净链补丁发行 + 同源里程碑 tag。"""
    ver = parse_version(args.ver)
    if ver[3]:
        raise SyncError("补丁发行版本号不能带 -dev 后缀，如 2.6.1。")
    tag = tag_name(ver)
    require_newer(ver, latest_release_tag())
    ensure_release_branch()

    # 校验修复 commit 存在于 dev（快照合入后两线无祖先关系，必须显式检查）
    src_commit = git("rev-parse", args.commit)
    if not is_ancestor(src_commit, BRANCH_DEV):
        raise SyncError(f"commit {args.commit} 不在 dev 分支历史中，无法搬运。")
    src_subject = git("show", "-s", "--format=%s", src_commit)

    # 同源里程碑 tag 将打在 dev 源 commit 上（版本同源规则）
    milestone_tag = tag + "-dev"
    if git("rev-parse", "--verify", milestone_tag, check=False):
        raise SyncError(f"里程碑 tag {milestone_tag} 已存在，请换更高的 patch 号。")

    msg = args.msg or commit_message_for_cherry(tag, src_subject)

    with temp_worktree(BRANCH_RELEASE) as path:
        print(f"[1/3] cherry-pick {src_commit[:12]} → release（临时 worktree）")
        git("cherry-pick", src_commit, cwd=str(path), check=False)
        # 冲突检测：git status --porcelain 中 unmerged 条目形如 "UU file"
        status_out = git("status", "--porcelain", cwd=str(path), check=False) or ""
        if any(
            line[:2] in ("UU", "AA", "AU", "UA", "DD", "DU", "UD")
            for line in status_out.splitlines()
        ):
            git("cherry-pick", "--abort", cwd=str(path), check=False)
            raise SyncError(
                "cherry-pick 到 release 冲突（该修复依赖尚未发行的代码）。\n"
                "建议: 改用 release 命令发行包含该修复的完整新版本。"
            )

        print(f"[2/3] 发行准备: _version.py = {format_version(ver)} + commit + 注解 tag {tag}")
        # write_version_py 覆盖 cherry-pick 带入的 _version.py 改动（如有），
        # 并入 cherry-pick 提交，保持 1 发行 = 1 commit
        write_version_py(ver, path / "src" / "_version.py")
        git("add", "src/_version.py", cwd=str(path))
        git("commit", "--amend", "-m", msg, cwd=str(path))
        git("tag", "-a", tag, "-m", msg, cwd=str(path))

        print("[3/3] 清理临时 worktree")

    # dev 源 commit 上打同源 -dev 里程碑 tag（补丁同样版本同源）
    print(f"打同源里程碑 tag {milestone_tag} → dev {src_commit[:12]}")
    git("tag", milestone_tag, src_commit)

    if args.push:
        print("推送到 origin ...")
        do_push([BRANCH_RELEASE, tag, milestone_tag])

    print(f"✓ 补丁发行 {tag} 已创建" + ("并推送" if args.push else "（本地）"))


def build_parser():
    """构建命令行参数解析器。"""
    p = argparse.ArgumentParser(
        prog="release_sync.py",
        description="两线版本同步脚本（dev/release，版本同源规则）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("用法:")[1] if "用法:" in __doc__ else None,
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="两线体检")

    p_ms = sub.add_parser("milestone", help="dev HEAD 打 -dev 里程碑 tag")
    p_ms.add_argument("ver", help="里程碑版本号，如 2.7.0-dev")
    p_ms.add_argument("--push", action="store_true", help="完成后推送 tag 到 origin")

    p_new = sub.add_parser("release", help="dev → release 发行（快照干净发行链）")
    p_new.add_argument("ver", help="发行版本号，如 2.6.0")
    p_new.add_argument("--msg", help="发行说明（commit 消息主体）")
    p_new.add_argument(
        "--from", dest="from_ref", help="快照源 ref（默认 dev；首发可指定里程碑 tag）"
    )
    p_new.add_argument(
        "--notes-file",
        help="用指定文件覆盖发行树的 CHANGELOG_RELEASE.md（首发抛历史条目用）",
    )
    p_new.add_argument("--push", action="store_true", help="完成后推送到 origin")

    p_cherry = sub.add_parser("cherry", help="修复 commit 跨线补丁发行（patch 号递增）")
    p_cherry.add_argument("commit", help="dev 上的修复 commit hash")
    p_cherry.add_argument("ver", help="补丁发行版本号，如 2.6.1")
    p_cherry.add_argument("--msg", help="补丁说明（缺省取源 commit 主题）")
    p_cherry.add_argument("--push", action="store_true", help="完成后推送到 origin")

    return p


def main():
    """脚本入口。"""
    args = build_parser().parse_args()
    try:
        if args.command == "check":
            cmd_check(args)
        elif args.command == "milestone":
            cmd_milestone(args)
        elif args.command == "release":
            cmd_release(args)
        elif args.command == "cherry":
            cmd_cherry(args)
    except SyncError as e:
        print(f"✗ 同步中止: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
