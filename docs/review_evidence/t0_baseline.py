"""T0 基线留存脚本：GUI 修复实施前冻结行为基线（审计文档 §7 T0）。

按 docs/CODE_QUALITY_AUDIT_GUI.md 的 T0 任务包要求，留存：
  1. 源码指纹（HEAD + 未提交改动清单 + 全部 GUI 源文件 SHA-256）；
  2. 全部内置样式 YAML 原文存档（styles/ 目录，保留相对结构）；
  3. 三层往返输出存档（源 → 模型 → 控件 → 模型，逐字段差异）；
  4. 四张折叠卡 dump_expand_card() + 子控件几何存档；
  5. 主窗口 / 样式编辑器 light+dark 截图存档（Qt offscreen grab）。

复用 v2 复审探针 gui_report_reaudit.py 的往返与几何探测函数，
保证基线口径与审查证据一致。在项目虚拟环境中运行：
  PYTHONPATH=. python docs/review_evidence/t0_baseline.py
不修改业务源码或用户配置。
"""

import hashlib
import json
import os
import shutil
import subprocess
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

# 不弹出窗口，仍让 Qt 执行真实布局与渲染。
os.environ["QT_QPA_PLATFORM"] = "offscreen"
# offscreen 平台不读 Windows 字体注册表，中文界面会渲染为方块；
# 显式指向系统字体目录后中文截图才可读（仅影响本探针进程）。
_WINDOWS_FONTS = "C:\\Windows\\Fonts"
if os.path.isdir(_WINDOWS_FONTS):
    os.environ["QT_QPA_FONTDIR"] = _WINDOWS_FONTS

from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme

from src.utils.app_paths import get_app_dir, get_resource_root

# ── 加载 v2 复审探针脚本（文件名含连字符，需用 importlib 显式加载）──
# 复用其中的 settle / card_state / rect / differences / probe_layouts /
# probe_style_roundtrips，确保 T0 基线与审查证据的采集口径完全一致。
_HERE = Path(__file__).resolve().parent
_SPEC = spec_from_file_location("gui_report_reaudit", _HERE / "gui_report_reaudit.py")
_PROBE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_PROBE)

# ── 基线存档根目录：跟随探针的 app_paths 约定（开发环境 = 项目根）──
OUTPUT_DIR = get_app_dir() / "docs" / "review_evidence" / "t0_baseline"
STYLES_DIR = OUTPUT_DIR / "styles"
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"


def save_source_fingerprint(evidence: dict) -> None:
    """留存源码指纹：HEAD、未提交改动清单、GUI 源文件 SHA-256。"""
    evidence["head"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True).strip()
    # 未提交改动逐条记录（含未跟踪文件），修复实施期间据此确认基线漂移。
    evidence["uncommitted"] = [
        line for line in subprocess.check_output(
            ["git", "status", "--porcelain"], text=True).splitlines()
    ]
    # 与 v2 探针相同的源文件集合：全部 gui_pyside Python 文件 + 导出元数据模块。
    root = get_resource_root()
    source_paths = list((root / "src" / "gui_pyside").rglob("*.py"))
    source_paths.append(root / "src" / "utils" / "output_metadata.py")
    evidence["source_hashes"] = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_paths
    }


def archive_style_yamls() -> list:
    """把全部内置样式 YAML 原文复制进基线存档，返回存档清单。"""
    configs = get_resource_root() / "src" / "frame_styles" / "configs"
    archived = []
    for path in sorted(configs.rglob("*.yaml")):
        target = STYLES_DIR / path.relative_to(configs)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        archived.append(str(path.relative_to(configs)))
    return archived


def take_screenshots(app) -> list:
    """主窗口与样式编辑器各截 light/dark 两张；只读操作，不写任何配置。"""
    from src.gui_pyside.main_window import MainWindow

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    saved = []
    window = MainWindow()
    window.show()
    _PROBE.settle()

    for theme_name, theme in (("light", Theme.LIGHT), ("dark", Theme.DARK)):
        setTheme(theme)
        # 主题切换是信号驱动的样式重算，等动画与重绘完成后截取。
        _PROBE.settle()
        # 图像处理页（默认页）
        window.stackedWidget.setCurrentWidget(window.image_page)
        _PROBE.settle()
        pixmap = window.grab()
        target = SCREENSHOT_DIR / f"main_window_{theme_name}.png"
        pixmap.save(str(target))
        saved.append(target.name)
        # 样式编辑器页
        window.stackedWidget.setCurrentWidget(window.style_page)
        _PROBE.settle()
        pixmap = window.grab()
        target = SCREENSHOT_DIR / f"style_creator_{theme_name}.png"
        pixmap.save(str(target))
        saved.append(target.name)

    window.close()
    return saved


def main():
    """一次性采集全部基线并写 JSON 汇总；探针控件在采集后全部关闭。"""
    app = QApplication.instance() or QApplication([])
    evidence = {}

    # 1. 源码指纹
    save_source_fingerprint(evidence)

    # 2. 内置样式 YAML 原文存档
    evidence["archived_styles"] = archive_style_yamls()

    # 3. 三层往返输出存档（源 → 模型 → 控件 → 模型，逐字段差异，
    #    复用探针 probe_style_roundtrips：差异已按 source_to_model 与
    #    model_to_widgets_to_model 两段分开记录）
    evidence["style_roundtrips"] = _PROBE.probe_style_roundtrips()

    # 4. 四张折叠卡 dump_expand_card() + 子控件几何存档
    #    （probe_layouts 内部对每张卡调用 dump_expand_card 并记录
    #    card_state / relative_rect / relative_layout_index 等结构化几何）
    evidence["layouts"] = _PROBE.probe_layouts()

    # 5. 双主题截图存档
    evidence["screenshots"] = take_screenshots(app)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / "baseline.json"
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({k: v for k, v in evidence.items()
                      if k not in ("style_roundtrips", "layouts", "source_hashes")},
                     ensure_ascii=False, indent=2))
    print(f"基线已写入: {output}")
    app.quit()


if __name__ == "__main__":
    main()
