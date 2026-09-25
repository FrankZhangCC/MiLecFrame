# Git 分支模型历史沿革

> 本文档记录 MiLecFrame 版本管理 / 分支模型的完整演进历史与各阶段的设计动机，
> 供回溯查阅。**当前有效的分支规则以 [AGENTS.md](../AGENTS.md)「Git 分支工作流」为准。**

## 时间线总览

| 时期 | 模型 | 关键变更 |
|------|------|----------|
| 2026-08 之前 | 旧编号体系 | 独立 release 编号序列（v0.1.0 / v1.0.0 / v1.1.0-release / v1.2.0） |
| 2026-08 | 三线模型（历史重建） | dev / mainline / release 共享共同祖先，版本同源规则确立 |
| 2026-08-19 | dev 归档机制 | 每次里程碑后 dev `reset --hard mainline` |
| 2026-09-22 | merge --no-ff 合入 | 版本 commit = merge commit，dev 细节历史经第二父并入 mainline |
| 2026-09-25 | **两线模型（现行）** | mainline 废止；dev 永久保留开发历史 + release 干净发行链（orphan） |

## 2026-08 之前：旧编号体系

- 发行使用独立编号序列：`v0.1.0`、`v1.0.0`、`v1.1.0-release`、`v1.2.0` 等。
- 发行 tag 与内部开发版号无对应关系，版本追溯困难。

## 2026-08：历史重建（三线模型）

- **背景**：mainline / release 原为 orphan 起步，与 dev 无共同祖先，
  `cherry-pick` 跨线搬运困难。
- **重建方式**：通过 `commit-tree` 重建父链，使三线共享 dev 的
  Initial commit 作为共同祖先；release 各发行 commit 的父**锚定其来源的
  mainline 版本**（v0.1.0→v1.12.0-dev、v1.0.0→v2.0.0-dev、
  v1.1.0→v2.2.0-dev、v1.2.0→v2.4.0-dev）。
- **版本同源规则**在此阶段确立：mainline 用 `vX.Y.Z-dev`（内部开发版），
  release 用同号去 `-dev` 后缀的 `vX.Y.Z`（公开发行版）。
- 全部同步操作由 `tools/release_sync.py` 脚本完成，禁止手工执行 read-tree。
- 重建前的状态保存在 `pre-rebuild-dev` / `pre-rebuild-mainline` /
  `pre-rebuild-release` 三个 tag 中。

## 2026-08-19：dev 归档机制

- 每次里程碑合入后，dev 自动 `reset --hard mainline`，两线 merge-base
  恒为最近版本 commit，保证下次合入只含新开发内容。
- **副作用**：dev 的任务级提交历史在归档后只能依赖 mainline 侧的合入形态
  保留，或靠备份分支（`dev-backup*`）/ 归档 tag 保存。
- 更早的 dev 松散历史归档至 `archive-dev-history-2026-08` tag。

## 2026-09-22：merge --no-ff 合入

- `new-version` 由 merge --squash 改为 **merge --no-ff**：版本 commit 即
  merge commit（第一父 = 上一版本 commit，第二父 = dev 本版本末端 commit），
  沿第一父遍历仍为线性版本链。
- **动机**：dev 归档（reset）后开发记录不丢——dev 的任务级提交经第二父
  完整并入 mainline 历史。
- **代价**（当时未被重视，后来成为两线化的导火索）：
  `git log mainline` 会遍历出 dev 全部细节提交，mainline 不再是
  "每 commit = 一版本"的干净链。

## 2026-09-25：两线模型（现行）

### 废止 mainline 的动机

- dev 改为**永久保留完整开发历史**（不再 reset 归档）后，历史保存不再
  依赖 mainline 的第二父，mainline 只剩"干净版本链"一个职责。
- 该职责与 release 的发行链几乎完全重合（只差 tag 是 `-dev` 还是发行号），
  三分支的存在失去意义——收敛为 **dev（开发历史）+ release（干净发行链）**。

### 变更内容

- **mainline 分支删除**（本地 + origin）：其历史版本 commit（含
  2026-09-22 的 merge commit）由 `v*-dev` tag 变达保留，不会丢失。
- **历史发行 tag 全部作废**（本地 + origin）：`v0.1.0`、`v1.0.0`、
  `v1.1.0-release`、`v1.2.0`、`v2.5.2`；`v*-dev` 里程碑 tag 全部保留。
- **release 推倒重建**：orphan 起步（与 dev 无共同祖先），发行号从
  **v2.6.0** 起重新累积；`CHANGELOG_RELEASE.md` 历史条目随旧号段一并
  作废，从 v2.6.0 起重新累积。
- **dev 归档机制废止**：dev 永不 reset，里程碑 tag 直接打在 dev 的
  "chore: 升版本"提交上（不产生专属版本 commit）。
- `tools/release_sync.py` 重写为两线命令：`check` / `milestone` /
  `release` / `cherry`。release / cherry 全程在临时 worktree 中执行，
  不触碰 dev 工作区。

### 设计权衡

- **merge --no-ff → read-tree 快照**：mainline（现 release）版本 commit
  不再携带 dev 细节历史；发行 commit 的树 = dev 时点快照，相邻发行
  commit 的 diff 即两次发行间的净变化。
- **dev 不 rebase、不归档**：dev 提交的 hash / 顺序 / 历史原封不动，
  满足"dev 分支保留完整开发 commit 记录"的要求。
- **代价**：dev 与 release 无共同祖先，`merge` 永不可用，跨线搬运只能
  `cherry-pick`（由 `release_sync.py cherry` 封装）；dev 开发历史只存在
  于本机，需自行备份。

## 遗留物索引

| 遗留物 | 说明 |
|--------|------|
| `pre-rebuild-dev` / `pre-rebuild-mainline` / `pre-rebuild-release` | 2026-08 历史重建前的三线状态快照 tag |
| `archive-dev-history-2026-08` | 2026-08 归档的 dev 松散历史 tag |
| `dev-backup` / `dev-backup-rotation-adaptation` / `dev-backup-v2.6.0-dev` / `dev-pre-squash` | 各时期 dev 状态的本地备份分支（仅本机） |
| 旧 mainline 版本 commit（v1.0.1-dev … v2.6.0-dev 链） | 由对应 `v*-dev` tag 变达；`v2.6.0-dev` 指向 2026-09-22 的 merge commit |
