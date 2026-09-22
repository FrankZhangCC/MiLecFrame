# positioning_v1 — 旧定位算法离线归档

> **仅供参考，禁止 import，禁止打包进发行包。**
> 本目录中的 `.txt` 文件不参与任何运行时执行，仅作为排查历史输出
> 与迁移参考的只读源码快照。

## 归档内容

| 文件 | 说明 |
|---|---|
| `layout_engine.py.txt` | 重写前的 `src/utils/layout_engine.py` 原样副本（含旧 `_get_anchor()` / `_align_x()` / `_align_y()` / `_resolve_tree_ref()` 与旧 position/alignment 别名语义） |

## 来源信息

- **来源 commit**：`499a676`（dev 分支，v2.6.0-dev 里程碑 commit，
  `src/utils/layout_engine.py` 最后实质修改于 `2248c7f`）
- **归档日期**：2026-09-23
- **适用版本**：≤ v2.6.0-dev 的全部版本（旧 `position`/`alignment`
  复合语义、`both-center`、单轴别名 `top`/`bottom`/`left`/`right`/
  `tl`/`tr`/`bl`/`br`/`tc`/`bc` 均在此版本线上有效）
- **归档原因**：执行
  [`docs/plans/POSITION_ALIGNMENT_REPAIR_EXECUTION_PLAN.md`](../../plans/POSITION_ALIGNMENT_REPAIR_EXECUTION_PLAN.md)
  中的一次性破坏性重构——`position` 只选择照片九点参考位，
  `alignment` 只决定元素布局盒自对齐，两者不再复合解释。

## 旧值 → 新 schema 迁移入口

人工迁移对照表见执行方案 §2.2 / §2.3 / §5（内置样式逐项迁移表）。
运行时**不做**旧值自动猜测或静默转换：旧别名会由 StyleManager
在校验阶段直接拒绝并给出迁移建议。

## 边界约束

1. 本目录文件**不得**被任何 Python 代码 import；
2. 不得作为 PyInstaller datas 资源加入发行包；
3. "恢复旧算法"只能通过工程级代码回退（git revert）或参考本归档
   重新实现，不能由样式配置切换；
4. 本目录位于 `docs/` 下，不会被 `src/frame_styles` 样式扫描路径触及。
