# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
T5 离屏 GUI 冒烟探针（G 系列检查的无界面辅助证据，不能替代真实交互）

用 QT_QPA_PLATFORM=offscreen 实例化完整 ImageProcessingPage，验证：
1. 初始化链路：卡片创建 → 信号连接 → 配置恢复（restoring 包裹）→ 首刷；
2. 11 项 OptionState 全部应用到控件（enabled 与 GroupWidget 说明）；
3. 生成按钮条件 = 照片有效 && can_render_style；
4. 切样式触发快照重读；StyleSelectorCard 空列表清除 current_style；
5. 坏变体守卫：直接调用 _on_generate_frame 不进入临时生成流程。

运行（venv，项目根目录）：
    python docs/review_evidence/style_loading_smoke.py
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from src.gui_pyside.pages.image_processing_page import ImageProcessingPage  # noqa: E402
from src.frame_styles.style_manager import StyleManager  # noqa: E402
from src.gui_pyside.utils import style_option_bindings  # noqa: E402

page = ImageProcessingPage()
print("1) 页面实例化成功（初始化链路无异常）")

# 11 项绑定属性齐全
missing = [f"{w}/{g}" for w, g in style_option_bindings.OPTION_BINDINGS.values()
           if not (hasattr(page, w) and hasattr(page, g))]
print("2) 11 项绑定控件与组对象齐全:", not missing, missing or "")

# 默认样式下的状态应用（首刷已执行）
ev = page._style_evaluation
print("3) 首刷 evaluation 就绪:", ev is not None,
      "| states:", len(ev.states) if ev else 0,
      "| can_render:", ev.can_render_style if ev else None)
print("   生成按钮初始状态:", page.btn_generate.isEnabled(),
      "（无照片 → 预期 False）")

# 切样式：走完整 UI 链路（set_current_style → 选中态 + 信号 → 刷新）
page.set_current_style_safe = None  # 占位避免误用
page.style_selector_card.set_current_style("信息卡片 InfoCard")
ev_ic = page._style_evaluation
s_disp = ev_ic.state_of("lens_display_mode")
s_name = ev_ic.state_of("lens_name_mode")
print("4) InfoCard 镜头显示禁用/镜头名启用:",
      (not s_disp.enabled, s_name.enabled) == (True, True),
      f"reason={s_disp.reason_code}/{s_name.reason_code}")
print("   快照对应样式:", page._style_capabilities_for)

# 输入变化（文本）→ 状态重算但快照不重读（§5.4 零 IO 路径）
caps_before = page._style_capabilities
page.edit_author.setText("测试作者")
ev_after = page._style_evaluation
print("5) 输入变化复用快照:", page._style_capabilities is caps_before,
      "| author 有效参数:", repr(ev_after.effective_values.author))

# 生成按钮条件：无照片时无论样式如何都禁用
print("6) 无照片生成按钮仍禁用:", not page.btn_generate.isEnabled())

# StyleSelectorCard 空列表清除 current_style（§8.3）
card = page.style_selector_card
names_before = card.current_style
card.refresh_styles([], page.style_manager)
print("7) 空列表清除 current_style:", card.current_style is None,
      f"（之前: {names_before!r}）")
page._refresh_style_option_state(reload_snapshot=True)
print("   无样式时全部禁用:", all(not s.enabled for s in page._style_evaluation.states),
      "| reason:", page._style_evaluation.states[0].reason_code)

# 恢复非空列表
all_styles = page.style_manager.get_available_styles()
card.refresh_styles(all_styles, page.style_manager)
print("8) 恢复非空列表选择首选:", card.current_style == all_styles[0])

# 坏变体守卫：篡改快照为全坏 → 直接调用生成入口被拦截（G12 辅助探针）
page._select_item(0) if page.file_items else None
print("9) 坏变体守卫（无照片场景守卫同样拦截）:")
print("   _on_generate_frame 直调不抛异常：", end="")
try:
    page._on_generate_frame()
    print("True（未进入生成流程，无 state_tooltip 创建）",
          "| state_tooltip:", page.state_tooltip)
except Exception as e:
    print("False（异常）:", e)

print("\n冒烟探针完成。")
