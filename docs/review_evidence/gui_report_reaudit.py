"""GUI 审计报告二审的独立运行探针；不修改业务源码或用户配置。

在项目虚拟环境中运行，PYTHONPATH 指向项目根目录。
使用 Qt offscreen 创建真实控件，结果写入同目录 JSON；这不是测试框架。
"""

import ast
import hashlib
import json
import os
import subprocess
import tempfile
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# 不弹出窗口，仍让 Qt 执行真实布局与展开动画。
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import yaml
from PIL import Image
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.gui_pyside.models.style_config_form import (
    DefinedTextConfig, ElementConfig, StyleConfigFormData, _build_yaml_config,
)
from src.gui_pyside.pages.camera_mapping_page import CameraMappingPage
from src.gui_pyside.pages.image_processing_page import ImageProcessingPage
from src.gui_pyside.pages.lens_mapping_page import LensMappingPage
from src.gui_pyside.utils.layout_debug import dump_expand_card
from src.gui_pyside.widgets.element_editor import ElementEditor
from src.gui_pyside.widgets.style_config_sections.custom_text_section import CustomTextSection
from src.gui_pyside.widgets.style_config_sections.defined_texts_section import DefinedTextsSection
from src.gui_pyside.widgets.style_config_sections.elements_section import ElementsSection
from src.gui_pyside.widgets.style_config_sections.logo_section import LogoSection
from src.utils.app_paths import get_app_dir, get_resource_root
from src.utils.output_metadata import prepare_output_metadata, verify_output_metadata


def settle():
    """等待布局请求与 200 ms 折叠动画完成，避免采到动画中间态。"""
    QApplication.processEvents()
    QTest.qWait(300)
    QApplication.processEvents()


def card_state(card):
    """保存卡片真实尺寸和 sizeHint，配合项目既有诊断输出。"""
    dump_expand_card(card)
    return {
        "expanded": card.isExpand,
        "card_h": card.height(),
        "header_h": card.card.height(),
        "space_h": card.spaceWidget.height(),
        "view_h": card.view.height(),
        "content_hint_h": card.widgets[0].sizeHint().height(),
    }


def rect(widget):
    """把 QRect 转成 JSON 可序列化的四元组。"""
    bounds = widget.geometry()
    return [bounds.x(), bounds.y(), bounds.width(), bounds.height()]


def probe_layouts():
    """分别探测两张列表卡的定位切换以及四张卡展开/收起状态。"""
    result = {}
    for cls, item in ((ElementsSection, ElementConfig()),
                      (DefinedTextsSection, DefinedTextConfig(key="defined_text_01"))):
        card = cls()
        card.resize(700, card.height())
        card.set_items([item])
        card.show()
        settle()
        card.setExpand(True)
        settle()
        editor = card._items[0]["editor"]
        before = card_state(card)
        editor.set_mode("relative")
        settle()
        after = card_state(card)
        after.update({
            "editor_rect": rect(editor),
            "relative_rect": rect(editor.rel_widget),
            "relative_hint_h": editor.rel_widget.sizeHint().height(),
            "relative_layout_index": editor.layout().indexOf(editor.rel_widget),
        })
        card.setExpand(False)
        settle()
        result[cls.__name__] = {"absolute": before, "relative": after,
                                "collapsed": card_state(card)}
        card.close()
    for cls in (LogoSection, CustomTextSection):
        card = cls()
        card.resize(700, card.height())
        card.show()
        settle()
        card.setExpand(True)
        settle()
        expanded = card_state(card)
        card.setExpand(False)
        settle()
        result[cls.__name__] = {"expanded": expanded, "collapsed": card_state(card)}
        card.close()
    return result


def probe_mapping_guards():
    """记录首次刷新时表格是否存在，再在内存中模拟删掉保护分支。"""
    result = {}
    for cls in (CameraMappingPage, LensMappingPage):
        calls = []
        original = cls._refresh_table

        def trace(page):
            calls.append(hasattr(page, "_table"))
            return original(page)

        with patch.object(cls, "_refresh_table", trace):
            page = cls()
            page.close()

        # 构造执行原函数体的副本，只删 hasattr 保护；不写入源码。
        import inspect
        import textwrap
        tree = ast.parse(textwrap.dedent(inspect.getsource(original)))
        tree.body[0].body = tree.body[0].body[1:]
        namespace = {}
        exec(compile(tree, "<guard-removal-probe>", "exec"), original.__globals__, namespace)
        try:
            with patch.object(cls, "_refresh_table", namespace["_refresh_table"]):
                broken = cls()
                broken.close()
            removal = "no exception"
        except Exception as exc:
            removal = f"{type(exc).__name__}: {exc}"
        result[cls.__name__] = {"table_exists_at_refresh": calls,
                                "guard_removed_constructor": removal}
    return result


def probe_exports():
    """使用带真实品牌元数据的 JPEG/PNG，调用现有导出路径验证格式误判。"""
    result = {}
    receiver = SimpleNamespace(_file_sha256=ImageProcessingPage._file_sha256)
    with tempfile.TemporaryDirectory(prefix="milec_gui_reaudit_") as temp:
        for fmt, suffix in (("JPEG", ".jpg"), ("PNG", ".png")):
            source = Path(temp) / ("source" + suffix)
            target = Path(temp) / ("export" + suffix)
            prepared = prepare_output_metadata(None, fmt)
            kwargs = {"exif": prepared.exif_bytes}
            if fmt == "PNG":
                kwargs["pnginfo"] = prepared.pnginfo
            Image.new("RGB", (16, 16), (100, 150, 200)).save(source, format=fmt, **kwargs)
            verify_output_metadata(str(source), fmt, prepared.software_text)
            try:
                ImageProcessingPage._export_verified(receiver, str(source), str(target))
                outcome = "success"
            except Exception as exc:
                outcome = f"{type(exc).__name__}: {exc}"
            result[fmt] = {"source_verification": "success", "export": outcome,
                           "target_exists": target.exists(),
                           "part_exists": Path(str(target) + ".part").exists()}
    return result


def probe_models():
    """区分序列化全局副作用、已有字段损失及方向切换策略差异。"""
    sample = {"items": [1, 2]}
    before_dump = yaml.dump(sample)
    before_representer = yaml.Dumper.yaml_representers[list]
    _build_yaml_config(sample)
    after_dump = yaml.dump(sample)
    config = {
        "layout": {
            "info_position": {"exif": {"position": "bottom-left", "alignment": "top-left"}},
            "defined_texts": {"defined_text_01": {
                "content": "first\nsecond", "relative_to": "exif",
                "relative_position": "below", "cross_alignment": "left",
                "line_alignment": "right",
            }},
        }, "logo": {"enabled": False},
    }
    model = StyleConfigFormData.from_yaml_dict(config)
    saved = model.to_yaml_dict()["layout"]["defined_texts"]["defined_text_01"]
    directions = {}
    for cls in (ElementEditor, LogoSection, CustomTextSection):
        editor = cls()
        cross = editor.rel_cross_alignment if cls is ElementEditor else editor.rel_cross_combo
        cross.clear()
        cross.addItems(["top", "center", "bottom"])
        cross.setCurrentText("top")
        editor._on_relative_position_changed("below")
        directions[cls.__name__] = cross.currentText()
        editor.close()
    return {"dumper_before": before_dump, "dumper_after": after_dump,
            "representer_changed": before_representer is not yaml.Dumper.yaml_representers[list],
            "relative_defined_text_line_alignment": {"input": "right", "output": saved.get("line_alignment")},
            "invalid_cross_alignment_fallback": directions}


def differences(before, after, prefix=""):
    """递归比较字典语义，保留路径；不把 YAML 注释或排版差异混进来。"""
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            path = f"{prefix}.{key}" if prefix else key
            if key not in before or key not in after:
                result.append({"path": path, "before": before.get(key), "after": after.get(key)})
            else:
                result.extend(differences(before[key], after[key], path))
        return result
    if before != after:
        return [{"path": prefix, "before": before, "after": after}]
    return []


def probe_style_roundtrips():
    """区分原 YAML→模型损失与模型→真实控件→模型损失，覆盖全部内置样式。"""
    configs = get_resource_root() / "src" / "frame_styles" / "configs"
    result = []
    for path in sorted(configs.rglob("*.yaml")):
        source = yaml.safe_load(path.read_text(encoding="utf-8"))
        before = StyleConfigFormData.from_yaml_dict(source)
        canonical = before.to_yaml_dict()
        after = before.clone()
        # 只操作四张定位卡，避免渲染、写配置或写样式文件。
        for cls in (ElementsSection, DefinedTextsSection, LogoSection, CustomTextSection):
            card = cls()
            card.load_from_model(before)
            card.save_to_model(after)
            card.close()
        result.append({"style": str(path.relative_to(configs)),
                       "source_to_model": differences(source, canonical),
                       "model_to_widgets_to_model": differences(canonical, after.to_yaml_dict())})
    return result


def main():
    """一次性执行探针并保存证据；所有图片只放在自动清理的临时目录。"""
    app = QApplication.instance() or QApplication([])
    # 保存源码指纹，方便并行工作区变化后确认本次二审的准确版本。
    root = get_resource_root()
    source_paths = list((root / "src" / "gui_pyside").rglob("*.py"))
    source_paths.append(root / "src" / "utils" / "output_metadata.py")
    before_hashes = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in source_paths}
    evidence = {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "versions": {name: version(name) for name in ("PySide6", "PySide6-Fluent-Widgets", "PyYAML")},
        "exports": probe_exports(),
        "mapping_guards": probe_mapping_guards(),
        "layouts": probe_layouts(),
        "models": probe_models(),
        "style_roundtrips": probe_style_roundtrips(),
        "source_hashes": before_hashes,
    }
    evidence["sources_unchanged_during_probe"] = all(
        hashlib.sha256(path.read_bytes()).hexdigest() == before_hashes[str(path.relative_to(root))]
        for path in source_paths)
    # 资源与输出路径统一使用项目 app_paths 约定，不基于脚本 __file__ 推导。
    configs = get_resource_root() / "src" / "frame_styles" / "configs"
    evidence["yaml_count"] = len(list(configs.rglob("*.yaml")))
    output = get_app_dir() / "docs" / "review_evidence" / "gui_report_reaudit.json"
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    app.quit()


if __name__ == "__main__":
    main()
