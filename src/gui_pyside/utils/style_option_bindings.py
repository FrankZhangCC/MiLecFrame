# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
样式选项控件绑定（计划 §7.1/§7.2，T4：把计算结果接到 QFluentWidgets）

职责：维护 11 项 GUI 选项与页面控件 / GroupWidget 说明行的绑定关系，
提供三个操作：
- read_raw_values：读控件原值 → RawOptionValues（LOGO userData 在此
  转换为 None/空字符串/文件名三态，业务层不判断中文显示文案）；
- apply_states：应用 OptionState——只调 setEnabled（LineEdit /
  SwitchButton / ComboBox）与 GroupWidget.setContent（分组常驻说明），
  不清空原值、不重建卡片、不禁用整个折叠卡；
- on_evaluation_failed：无可评估结果时的兜底展示。

设计约束（§7.4）：说明行是单行 contentLabel，content 必须是短句
（宽度硬约束，完整语义在 OptionState.tooltip）；不直接操作 viewLayout。
"""
import logging

from src.gui_pyside.models.style_option_state import (
    OPTION_IDS,
    RawOptionValues,
)
from src.utils.background_fill import BackgroundFillManager
from src.gui_pyside.pages.image_processing_config_cards import (
    LOGO_AUTO,
    LOGO_NONE,
)

logger = logging.getLogger(__name__)

# 选项 ID → (控件属性名, GroupWidget 属性名)
# GroupWidget 由 image_processing_config_cards 的 create_*_card 在构建时
# 保存到 page 属性（addGroup 返回对象），此处只按名引用、不创建控件。
OPTION_BINDINGS = {
    'author': ('edit_author', 'group_author'),
    'location': ('edit_location', 'group_location'),
    'use_gps': ('chk_use_gps', 'group_use_gps'),
    'custom_text': ('edit_custom_text', 'group_custom_text'),
    'timestamp_display_mode': ('combo_timestamp', 'group_timestamp'),
    'lens_display_mode': ('combo_lens_display', 'group_lens_display'),
    'lens_name_mode': ('combo_lens_name', 'group_lens_name'),
    'logo': ('combo_logo', 'group_logo'),
    'bg_fill_type': ('combo_bg_fill', 'group_bg_fill'),
    'enhance_background': ('chk_enhance', 'group_enhance'),
    'font_weight': ('combo_font_weight', 'group_font_weight'),
}

assert set(OPTION_BINDINGS) == set(OPTION_IDS), '绑定表必须覆盖全部 11 项'


def read_raw_values(page) -> RawOptionValues:
    """读取 11 项控件原值（纯读；LOGO userData → 三态语义）

    下拉框 userData 即稳定 key（G3 约定），非法/缺失时回退默认项，
    与 collect 旧逻辑一致。
    """
    logo_opt = page.combo_logo.currentData()
    if logo_opt == LOGO_NONE:
        logo_filename = ''          # 明确禁用
    elif logo_opt in (LOGO_AUTO, None):
        logo_filename = None        # 自动匹配
    else:
        logo_filename = logo_opt    # 指定文件名
    return RawOptionValues(
        author=page.edit_author.text(),
        location=page.edit_location.text(),
        custom_text=page.edit_custom_text.text(),
        use_gps=page.chk_use_gps.isChecked(),
        timestamp_display_mode=page.combo_timestamp.currentData() or 'full',
        lens_display_mode=page.combo_lens_display.currentData() or 'combined',
        lens_name_mode=page.combo_lens_name.currentData() or 'default',
        logo_filename=logo_filename,
        bg_fill_type=page.combo_bg_fill.currentData()
        or BackgroundFillManager.DEFAULT_FILL,
        enhance_background=page.chk_enhance.isChecked(),
        font_weight=page.combo_font_weight.currentData() or 'medium',
    )


def apply_states(page, evaluation) -> None:
    """应用 11 项 OptionState（只调 setEnabled，不修改说明行）

    用户反馈（2026-10-05）裁定：不同可用状态下**不修改**分组说明——
    GroupWidget 行内布局为"标题 + contentLabel + 控件占剩余空间"，
    setContent 改变 contentLabel 宽度会牵动同行控件的起点与尺寸
    （已实测复现：切样式后 4 个控件 x/宽度漂移）。说明行保持构建时
    的初始文案；禁用原因不再有行内常驻说明，由样式卡诊断说明
    （set_page_style_hint，坏变体时）与生成禁用兜底。

    - setEnabled 只作用于具体控件（LineEdit/SwitchButton/ComboBox），
      不禁用整个 GroupWidget 或折叠卡——否则说明与展开交互也会失效；
    - setEnabled 不改变控件几何（仅视觉态），尺寸保持固定；
    - states 每次完整 11 项，全部应用，防止旧样式的启禁残留。
    """
    for st in evaluation.states:
        names = OPTION_BINDINGS.get(st.option_id)
        if not names:
            continue
        widget = getattr(page, names[0], None)
        if widget is not None:
            widget.setEnabled(st.enabled)


def set_page_style_hint(page, evaluation) -> None:
    """坏变体/无样式的全局错误提示（§7.2：放样式说明处，不逐项掩盖，
    也不在每次输入时弹 InfoBar——生成按钮的可用性已兜底阻止）

    使用 StyleSelectorCard 的副标题位置（contentLabel）显示首条诊断。
    """
    card = getattr(page, 'style_selector_card', None)
    if card is None:
        return
    if evaluation.can_render_style or not evaluation.diagnostics:
        return
    first = evaluation.diagnostics[0]
    # contentLabel 单行宽度约束：超长诊断截断到安全长度，完整信息在
    # debug 日志（§8.4 已记录 reason/路径）
    safe = first if len(first) <= 60 else first[:57] + '…'
    try:
        card.setContent(safe)
    except Exception as e:  # 防御：说明展示失败不影响主流程
        logger.debug(f"样式说明更新失败（忽略）: {e}")


def clear_page_style_hint(page) -> None:
    """清空样式卡诊断说明（恢复默认副标题）"""
    card = getattr(page, 'style_selector_card', None)
    if card is None:
        return
    try:
        card.setContent('点击 (或滚轮浏览) 缩略图选择相框样式')
    except Exception as e:
        logger.debug(f"样式说明清理失败（忽略）: {e}")
