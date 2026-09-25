# gui_legacy — Streamlit Web GUI（已封存）

此目录是原始的 Streamlit Web 界面，已由 `gui_pyside/`（PySide6 原生桌面）替代。

**恢复方式**：如需重新启用，只需：
1. 将目录重命名回 `gui/`
2. 在 `src/__init__.py` 中添加 `from .gui import *`
3. 通过 `streamlit run src/gui/app.py` 启动
