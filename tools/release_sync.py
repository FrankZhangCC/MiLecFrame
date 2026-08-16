# -*- coding: utf-8 -*-
"""三线版本同步脚本（dev / mainline / release）。

在重建历史（2026-08）之后，三线共享共同祖先（dev 的 Initial commit），
版本规则更新为「版本同源」：mainline 用 vX.Y.Z-dev，release 用同号去
-dev 后缀的 vX.Y.Z；一个版本 = 一个 commit + 一个 tag；修复走 patch
号递增，禁止"增补"commit。

用法：
    python tools/release_sync.py check
        # 三线体检：共同祖先 / tag 完整性 / 版本号与 CHANGELOG 一致性

    python tools/release_sync.py new-version <ver> --msg "功能简述" [--push]
        # 把 dev 快照为 mainline 新版本（ver 形如 2.5.0-dev），
        # 自动执行 read-tree 快照 + 写 _version.py + commit + tag

    python tools/release_sync.py cherry <commit> <ver> [--also-release] [--push]
        # 把 dev 上的单个修复 commit cherry-pick 到 mainline 并升 patch 号
        # （ver 形如 2.4.1-dev 或 2.4.1；带 --also-release 时同步到 release）

    python tools/release_sync.py release <ver> --msg "发行说明" [--push]
        # 把 mainline 快照为 release 公开发行（ver 形如 2.4.0，无 -dev 后缀），
        # 自动改 _version.py 去 -dev + commit + tag

约定：
    - 所有命令必须在 dev 分支、工作区干净的状态下执行（read-tree 会覆盖工作树）。
    - tag 均为轻量 tag，推送时用 --follow-tags + --tags 兜底。
    - 脚本不提供 force push；release 分支受保护，历史不可改写。
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Windows 控制台默认 GBK，强制 UTF-8 输出避免 ✗/✓ 等符号编码崩溃
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# 项目根目录（脚本位于 <root>/tools/ 下）
ROOT = Path(__file__).resolve().parent.parent

# 三线分支名
BRANCH_DEV = "dev"
BRANCH_MAINLINE = "mainline"
BRANCH_RELEASE = "release"

# 版本号正则：2.4.0-dev / v2.4.0 / v2.4.1-dev 均可，split 后比较
VER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-(dev))?$")

# CHANGELOG 条目行示例："## v2.4.0-dev (2026-08-14)"，匹配时转义版本号
CHANGELOG_ENTRY_RE = re.compile(r"^##\s+v(\d+\.\d+\.\d+(?:-dev)?)\b", re.MULTILINE)


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

    suffix: 'dev' 或 None（公开发行）。
    返回元组可直接用于元组比较（None < 'dev'，均参与比较即可）。
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
    """生成 tag 名：v2.4.0-dev / v2.4.0。"""
    return "v" + format_version(t)


def current_branch():
    """返回当前分支名。"""
    return git("rev-parse", "--abbrev-ref", "HEAD")


def ensure_clean_worktree():
    """确保工作区干净（含未跟踪文件），否则中止。"""
    dirty = git("status", "--porcelain", check=True)
    if dirty:
        raise SyncError(
            "工作区不干净，无法执行同步操作。\n"
            f"未提交/未跟踪文件:\n{dirty}\n"
            "请先提交或暂存这些改动。"
        )


def ensure_branch(branch):
    """确保当前位于指定分支。"""
    cur = current_branch()
    if cur != branch:
        raise SyncError(f"当前分支为 {cur}，此命令必须在 {branch} 分支上执行。")


def latest_tag_on(branch):
    """返回指定分支可达的最新 tag 名（无 tag 返回 None）。"""
    return git("describe", "--tags", "--abbrev=0", branch, check=False) or None


def require_newer(new_ver, old_tag):
    """校验新版本号必须大于分支上的最新 tag。"""
    if old_tag is None:
        return
    try:
        old = parse_version(old_tag)
    except SyncError:
        # 历史遗留 tag（如 v0.1.0）解析不了的按可比较处理：都兼容即可
        return
    if new_ver <= old:
        raise SyncError(f"新版本 {format_version(new_ver)} 必须大于当前最新 tag {old_tag}。")


def read_version_py():
    """读取当前工作树 src/_version.py 中的 __version__ 字符串。"""
    path = ROOT / "src" / "_version.py"
    text = path.read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise SyncError("无法从 src/_version.py 读取 __version__。")
    return m.group(1)


def write_version_py(ver_tuple):
    """按新版本号重写 src/_version.py 的 __version__ 与 __version_info__。

    dev 后缀版本写 'dev'，公开发行写 'release'（与 release 线历史一致）。
    """
    major, minor, patch, suffix = ver_tuple
    version_str = format_version(ver_tuple)
    tag_str = suffix if suffix else "release"
    path = ROOT / "src" / "_version.py"
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


def changelog_has_version(changelog, ver_tuple):
    """检查 CHANGELOG.md / CHANGELOG_RELEASE.md 是否含指定版本条目。"""
    path = ROOT / changelog
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    target = "v" + format_version(ver_tuple)
    for m in CHANGELOG_ENTRY_RE.finditer(text):
        if m.group(1) == target[1:]:
            return True
    return False


def commit_message_for_cherry(tag, src_subject):
    """生成 cherry-pick 提交消息：版本 tag + 原提交主题（去掉 conventional 前缀）。"""
    subject = re.sub(
        r"^(feat|fix|docs|chore|refactor|style|test)(\(.+?\))?!?: ",
        "",
        src_subject.strip(),
    )
    return f"{tag}: {subject}"


def do_push(push_refspecs):
    """推送到 origin：各分支 refspec + --tags 兜底轻量 tag。"""
    for refspec in push_refspecs:
        git("push", "origin", refspec, "--follow-tags")
    git("push", "origin", "--tags")


def cmd_check(_args):
    """三线体检：共同祖先、tag 完整性、版本号与文档一致性。"""
    problems = []

    # 1. 共同祖先：三线 merge-base 应回到 dev 的根 commit（无父的 Initial commit）
    initial = git("rev-list", "--max-parents=0", BRANCH_DEV)
    base_mainline = git("merge-base", BRANCH_DEV, BRANCH_MAINLINE, check=False)
    base_release = git("merge-base", BRANCH_DEV, BRANCH_RELEASE, check=False)
    for name, base in ((BRANCH_MAINLINE, base_mainline), (BRANCH_RELEASE, base_release)):
        if not base:
            problems.append(f"{name} 与 dev 无共同祖先")
        elif base != initial:
            problems.append(f"{name} 与 dev 的共同祖先不是 Initial commit: {base[:12]}")

    # 2. mainline：每个版本 commit 恰好一个 tag，commit 首行以版本号开头
    #    沿第一父遍历版本链，Initial commit（无版本前缀）为链尾
    commits = git("log", "--first-parent", "--format=%H %s", BRANCH_MAINLINE).splitlines()
    for line in commits:
        h, subject = line.split(" ", 1)
        m = re.match(r"^(v\d+\.\d+\.\d+(?:-dev)?):", subject)
        if not m:
            if h == initial:
                break  # 到达 Initial commit，mainline 链结束
            problems.append(f"mainline commit {h[:12]} 首行无版本号前缀: {subject[:50]}")
            continue
        expected = m.group(1)
        tags = git("tag", "--points-at", h, check=False).splitlines()
        tags = [t for t in tags if t and not t.startswith("pre-rebuild")]
        if expected not in tags:
            problems.append(f"mainline commit {h[:12]} 缺少 tag {expected}")
        if len(tags) != 1:
            problems.append(f"mainline commit {h[:12]} tag 数异常: {tags}")

    # 3. release：沿第一父遍历发行链，遇到 mainline 链上的 commit 即止
    commits = git("log", "--first-parent", "--format=%H %s", BRANCH_RELEASE).splitlines()
    for line in commits:
        h, subject = line.split(" ", 1)
        # release 首 commit 的父是 mainline 链，此处即发行链终点
        if is_ancestor(h, BRANCH_MAINLINE):
            break
        m = re.match(r"^(v\d+\.\d+\.\d+(?:-release)?):", subject)
        if not m:
            problems.append(f"release commit {h[:12]} 首行无版本号前缀: {subject[:50]}")
            continue
        tags = git("tag", "--points-at", h, check=False).splitlines()
        tags = [t for t in tags if t and not t.startswith("pre-rebuild")]
        if len(tags) != 1:
            problems.append(f"release commit {h[:12]} tag 数异常: {tags}")

    # 4. _version.py 与分支最新 tag 一致
    for branch in (BRANCH_MAINLINE, BRANCH_RELEASE):
        latest = latest_tag_on(branch)
        if latest and not latest.startswith("pre-rebuild"):
            file_ver = git("show", f"{branch}:src/_version.py", check=False)
            m = re.search(r'^__version__\s*=\s*"([^"]+)"', file_ver or "", re.MULTILINE)
            if m and tag_name(parse_version(m.group(1))) != latest:
                problems.append(
                    f"{branch} 的 _version.py={m.group(1)} 与最新 tag {latest} 不一致"
                )

    # 5. CHANGELOG 条目：mainline 最新版本应有 CHANGELOG.md 条目
    latest = latest_tag_on(BRANCH_MAINLINE)
    if latest and not latest.startswith("pre-rebuild"):
        if not changelog_has_version("CHANGELOG.md", parse_version(latest)):
            problems.append(f"CHANGELOG.md 缺少 {latest} 条目")

    # 6. 提示性信息：dev 有待快照的提交
    ahead = git("log", "--oneline", f"{BRANCH_MAINLINE}..{BRANCH_DEV}", check=False)
    dirty = git("status", "--porcelain", check=False)

    print("=== 三线体检 ===")
    print(f"dev:       {git('rev-parse', '--short', BRANCH_DEV)}")
    print(f"mainline:  {git('rev-parse', '--short', BRANCH_MAINLINE)} (最新 tag: {latest_tag_on(BRANCH_MAINLINE)})")
    print(f"release:   {git('rev-parse', '--short', BRANCH_RELEASE)} (最新 tag: {latest_tag_on(BRANCH_RELEASE)})")
    if ahead:
        print(f"提示: dev 领先 mainline {len(ahead.splitlines())} 个未快照提交")
    if dirty:
        print(f"提示: 工作区有未提交改动")
    if problems:
        print("\n发现问题:")
        for p in problems:
            print(f"  ✗ {p}")
        sys.exit(1)
    print("\n✓ 三线状态健康")


def cmd_new_version(args):
    """dev → mainline：树快照 + 写版本号 + commit + tag。"""
    ensure_branch(BRANCH_DEV)
    ensure_clean_worktree()
    ver = parse_version(args.ver)
    if ver[3] != "dev":
        raise SyncError("mainline 版本号必须带 -dev 后缀，如 2.5.0-dev。")
    tag = tag_name(ver)
    require_newer(ver, latest_tag_on(BRANCH_MAINLINE))
    if not changelog_has_version("CHANGELOG.md", ver):
        raise SyncError(f"CHANGELOG.md 缺少 v{format_version(ver)} 条目，请先在 dev 上补充。")
    if not args.msg:
        raise SyncError("必须提供 --msg 版本描述。")

    print(f"[1/4] 树快照: dev → mainline")
    git("checkout", BRANCH_MAINLINE)
    git("read-tree", "-u", "--reset", BRANCH_DEV)

    print(f"[2/4] 写入 _version.py = {format_version(ver)}")
    write_version_py(ver)

    print(f"[3/4] commit + tag {tag}")
    git("add", "-A")
    git("commit", "-m", f"{tag}: {args.msg}")
    git("tag", tag)

    print(f"[4/4] 回到 dev")
    git("checkout", BRANCH_DEV)

    if args.push:
        print("推送到 origin ...")
        do_push([BRANCH_MAINLINE])

    print(f"✓ mainline 新版本 {tag} 已创建" + ("并推送" if args.push else "（本地）"))


def cmd_cherry(args):
    """dev 的单点修复 → cherry-pick 到 mainline（升 patch 号）+ 可选 release。"""
    ensure_branch(BRANCH_DEV)
    ensure_clean_worktree()

    # 版本号两种写法：2.4.1-dev（mainline 目标）或 2.4.1（配合 --also-release）
    ver = parse_version(args.ver)
    mainline_ver = (ver[0], ver[1], ver[2], "dev")
    mainline_tag = tag_name(mainline_ver)
    require_newer(mainline_ver, latest_tag_on(BRANCH_MAINLINE))

    # 校验修复 commit 存在于 dev 且尚未在 mainline
    src_commit = git("rev-parse", args.commit)
    if is_ancestor(src_commit, BRANCH_MAINLINE):
        raise SyncError(f"commit {args.commit} 已在 mainline，无需重复搬运。")
    src_subject = git("show", "-s", "--format=%s", src_commit)

    # 目标分支与目标版本：mainline 必选；--also-release 时同步 release
    targets = [(BRANCH_MAINLINE, mainline_ver, mainline_tag)]
    if args.also_release:
        release_ver = (ver[0], ver[1], ver[2], "")
        require_newer(release_ver, latest_tag_on(BRANCH_RELEASE))
        targets.append((BRANCH_RELEASE, release_ver, tag_name(release_ver)))

    for branch, tver, tag in targets:
        print(f"--- 处理 {branch}: cherry-pick → {tag}")
        git("checkout", branch)
        git("cherry-pick", src_commit, check=False)
        # 冲突检测：git status --porcelain 中 unmerged 条目形如 "UU file"
        status_out = git("status", "--porcelain", check=False) or ""
        if any(line[:2] in ("UU", "AA", "AU", "UA", "DD", "DU", "UD") for line in status_out.splitlines()):
            git("cherry-pick", "--abort", check=False)
            git("checkout", BRANCH_DEV, check=False)
            raise SyncError(
                f"cherry-pick 到 {branch} 冲突（修复依赖的代码尚未进入该分支）。\n"
                "建议: 在 dev 上将修复变基到更早的提交后再试，或手动解决冲突。"
            )
        # 写入目标版本号并并入 cherry-pick 提交（保持 1 版本 = 1 commit）
        write_version_py(tver)
        git("add", "src/_version.py")
        git("commit", "--amend", "-m", commit_message_for_cherry(tag, src_subject))
        git("tag", tag)

    git("checkout", BRANCH_DEV)

    if args.push:
        print("推送到 origin ...")
        refspecs = [BRANCH_MAINLINE]
        if args.also_release:
            refspecs.append(BRANCH_RELEASE)
        do_push(refspecs)

    print("✓ cherry-pick 完成: " + ", ".join(t[2] for t in targets))


def cmd_release(args):
    """mainline → release：树快照 + 去 -dev 后缀 + commit + tag。"""
    ensure_branch(BRANCH_DEV)
    ensure_clean_worktree()
    ver = parse_version(args.ver)
    if ver[3]:
        raise SyncError("公开发行版本号不能带 -dev 后缀，如 2.4.0。")
    tag = tag_name(ver)

    # 要求 mainline 已存在同号 -dev 版本
    src_tag = tag + "-dev"
    if not git("rev-parse", src_tag, check=False):
        raise SyncError(f"mainline 上不存在 tag {src_tag}，请先执行 new-version。")
    require_newer(ver, latest_tag_on(BRANCH_RELEASE))
    if not changelog_has_version("CHANGELOG_RELEASE.md", ver):
        raise SyncError(f"CHANGELOG_RELEASE.md 缺少 v{format_version(ver)} 条目，请先在 dev 上补充。")
    if not args.msg:
        raise SyncError("必须提供 --msg 发行说明。")

    print(f"[1/4] 树快照: mainline → release")
    git("checkout", BRANCH_RELEASE)
    git("read-tree", "-u", "--reset", BRANCH_MAINLINE)

    print(f"[2/4] 写入 _version.py = {format_version(ver)} (release)")
    write_version_py(ver)

    print(f"[3/4] commit + tag {tag}")
    git("add", "-A")
    git("commit", "-m", f"{tag}-release: {args.msg}")
    git("tag", tag)

    print(f"[4/4] 回到 dev")
    git("checkout", BRANCH_DEV)

    if args.push:
        print("推送到 origin ...")
        do_push([BRANCH_RELEASE])

    print(f"✓ release 新版本 {tag} 已创建" + ("并推送" if args.push else "（本地）"))


def build_parser():
    """构建命令行参数解析器。"""
    p = argparse.ArgumentParser(
        prog="release_sync.py",
        description="三线版本同步脚本（dev/mainline/release，版本同源规则）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("用法:")[1] if "用法:" in __doc__ else None,
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="三线体检")

    p_new = sub.add_parser("new-version", help="dev → mainline 新版本快照")
    p_new.add_argument("ver", help="新版本号，如 2.5.0-dev")
    p_new.add_argument("--msg", help="版本描述（commit 消息主体）")
    p_new.add_argument("--push", action="store_true", help="完成后推送到 origin")

    p_cherry = sub.add_parser("cherry", help="修复 commit 跨线搬运（patch 号递增）")
    p_cherry.add_argument("commit", help="dev 上的修复 commit hash")
    p_cherry.add_argument("ver", help="目标版本号，如 2.4.1-dev（或 2.4.1 + --also-release）")
    p_cherry.add_argument("--also-release", action="store_true", help="同时同步到 release")
    p_cherry.add_argument("--push", action="store_true", help="完成后推送到 origin")

    p_rel = sub.add_parser("release", help="mainline → release 公开发行")
    p_rel.add_argument("ver", help="公开发行版本号，如 2.4.0")
    p_rel.add_argument("--msg", help="发行说明（commit 消息主体）")
    p_rel.add_argument("--push", action="store_true", help="完成后推送到 origin")

    return p


def main():
    """脚本入口。"""
    args = build_parser().parse_args()
    try:
        if args.command == "check":
            cmd_check(args)
        elif args.command == "new-version":
            cmd_new_version(args)
        elif args.command == "cherry":
            cmd_cherry(args)
        elif args.command == "release":
            cmd_release(args)
    except SyncError as e:
        print(f"✗ 同步中止: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
