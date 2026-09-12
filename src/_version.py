# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
MiLeica Frame - 版本号单点入口

版本标记规范（版本同源，2026-08 历史重建后）：
  - 内部开发版（mainline）：vX.Y.Z-dev（如 v2.4.0-dev）
  - 公开发行版（release）：  vX.Y.Z（同号去 -dev 后缀，如 v2.4.0）
  - 增补修复提升 patch 号：  v2.4.0-dev → v2.4.1-dev；v2.4.0 → v2.4.1
"""
__version__ = "2.5.2-dev"
__version_info__ = (2, 5, 2, 'dev')
