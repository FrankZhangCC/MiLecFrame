# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
图像处理页配置卡构建（G2 页面拆分）

六张配置卡的控件创建与布局自 ImageProcessingPage 收敛于此；
页面以 create_*_card(page) 形式调用，控件仍以 page.combo_xxx 等
属性归属页面（原样搬运，不做 API 重设计）。
collect_render_options 为渲染配置收集的纯函数（只读控件，无副作用）。
"""
from qfluentwidgets import (
    ComboBox, DoubleSpinBox, ExpandGroupSettingCard, LineEdit, Slider,
    SwitchButton, FluentIcon,
)

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt

from src.utils.background_fill import BackgroundFillManager
from src.gui_pyside.widgets.style_selector_card import StyleSelectorCard
from src.utils.orientation_adaptation import (
    ADAPT_DEFAULT, ADAPT_NONE, ADAPT_CLOCKWISE, ADAPT_COUNTERCLOCKWISE,
)
from src.core.renderer import RenderMetadata, RenderOptions


# ── 下拉框选项（显示文本, 稳定内部值）─────────────────────
# G3 修复：userData 绑定稳定枚举值而非中文文本，渲染映射与
# config.json 持久化一律读写稳定 key；文案调整不影响映射。
# （旋转适配 PORTRAIT_ADAPTATION_ITEMS 为页面提示逻辑共用，同置于此）

PORTRAIT_ADAPTATION_ITEMS = (
    ('默认（跟随样式）', ADAPT_DEFAULT),
    ('不旋转', ADAPT_NONE),
    ('顺时针适配', ADAPT_CLOCKWISE),
    ('逆时针适配', ADAPT_COUNTERCLOCKWISE),
)

OUTPUT_FORMAT_ITEMS = (
    ('JPEG', 'JPEG'),
    ('PNG', 'PNG'),
)

FONT_WEIGHT_ITEMS = (
    ('中等 (Medium)', 'medium'),
    ('常规 (Regular)', 'regular'),
    ('细体 (Light)', 'light'),
)

TIMESTAMP_DISPLAY_ITEMS = (
    ('显示日期与时刻', 'full'),
    ('只显示日期', 'date_only'),
    ('不显示时间', 'hide'),
)

LENS_DISPLAY_ITEMS = (
    ('相机+镜头', 'combined'),
    ('只显示相机', 'camera_only'),
    ('只显示镜头', 'lens_only'),
)

# 镜头名模式三态选项（GUI 文案 → 稳定内部值，与 CLI --lens-name 对齐）。
# 默认 = 键归位（lens 出完整名、short_lens 出短版名）；
# 完整镜头名 = short_lens 键的输出被 lens_model 替代；
# 短版镜头名 = lens / camera_lens 键的输出被短版名替代。
LENS_NAME_ITEMS = (
    ('默认', 'default'),
    ('完整镜头名', 'full'),
    ('短版镜头名', 'short'),
)

WATERMARK_POSITION_ITEMS = (
    ('左上', 'top-left'),
    ('顶部居中', 'top-center'),
    ('右上', 'top-right'),
    ('左下', 'bottom-left'),
    ('底部居中', 'bottom-center'),
    ('右下', 'bottom-right'),
)

# 水印颜色 key → RGB（userData 存 JSON 可序列化的稳定 key，
# 不直接存 tuple：QVariant 往返对 tuple 的还原不可靠）
WATERMARK_COLOR_ITEMS = (
    ('白色', 'white'),
    ('黑色', 'black'),
)
_WM_COLOR_RGB = {'white': (255, 255, 255), 'black': (0, 0, 0)}

# Logo 下拉哨兵稳定 key（G3）；动态 logo 项的 userData 为文件名本身
LOGO_AUTO = 'auto'
LOGO_NONE = 'none'

# ── 历史文本 → 稳定 key 别名表（D5 决策：长期保留）────────
# 修复前的 config.json 以中文显示文本为值；加载恢复时 findData 失败
# 后查此表迁移到稳定 key，仍失败回退默认项。别名表长期保留不随版本
# 移除：findText 式一次性兼容只在"文案未变"时有效，恰好漏掉本条
# 要防的"文案已变"场景；bg_fill 的历史 label 来自
# BackgroundFillManager 注册表，加载时与静态表合并（见页面 __init__）。
_LEGACY_TEXT_ALIASES = {
    **{text: key for text, key in FONT_WEIGHT_ITEMS},
    **{text: key for text, key in TIMESTAMP_DISPLAY_ITEMS},
    **{text: key for text, key in LENS_DISPLAY_ITEMS},
    **{text: key for text, key in WATERMARK_POSITION_ITEMS},
    **{text: key for text, key in WATERMARK_COLOR_ITEMS},
    '自动匹配': LOGO_AUTO,
    '无': LOGO_NONE,
}


def create_output_settings_card(page) -> ExpandGroupSettingCard:
    """Tab 1: 输出设置"""
    card = ExpandGroupSettingCard(FluentIcon.DOWNLOAD, "输出设置", "选择输出文件格式")

    # 输出格式（G3：userData 绑定稳定 key）
    page.combo_output_format = ComboBox()
    for _text, _key in OUTPUT_FORMAT_ITEMS:
        page.combo_output_format.addItem(_text, userData=_key)
    page.combo_output_format.setCurrentIndex(0)
    card.addGroup(FluentIcon.DOWNLOAD, "输出格式", "JPEG 适合照片，PNG 适合透明背景", page.combo_output_format, 1)

    return card


def create_style_selection_card(page) -> ExpandGroupSettingCard:
    """Tab 2: 样式选择（缩略图网格）"""
    from src.frame_styles.style_manager import StyleManager
    page.style_manager = StyleManager()
    available_styles = page.style_manager.get_available_styles()
    if not available_styles:
        page.style_manager.create_sample_styles()
        available_styles = page.style_manager.get_available_styles()

    card = StyleSelectorCard()
    card.refresh_styles(available_styles, page.style_manager)
    card.style_selected.connect(page._on_style_changed)

    return card


def create_frame_config_card(page) -> ExpandGroupSettingCard:
    """Tab 3: 相框配置（背景、字体等，样式选择已独立为 Tab 2）"""
    card = ExpandGroupSettingCard(FluentIcon.PHOTO, "相框配置", "背景填充、字体字重等设置")

    # 背景填充（G3：userData 绑定稳定 fill key，显示 label 仅作文案；
    # 旧代码的 bg_fill_keys 反查表由 userData 取代）
    bg_choices = BackgroundFillManager.get_choices()
    page.combo_bg_fill = ComboBox()
    for _label, _key in bg_choices.items():
        page.combo_bg_fill.addItem(_label, userData=_key)
    page.combo_bg_fill.setCurrentIndex(
        page.combo_bg_fill.findData(BackgroundFillManager.DEFAULT_FILL))
    # 相框配置卡三个下拉框统一双端宽度约束（200–260）：上限容纳最长
    # 选项"模糊背景 (深色 65%)"文本 182px + 箭头与内边距；下限保持原
    # 可收缩性——窄侧边栏下收缩回原基线，避免硬性宽度过高时整组
    # 最小需求超过侧边栏宽度造成水平溢出
    page.combo_bg_fill.setMinimumWidth(200)
    page.combo_bg_fill.setMaximumWidth(260)
    bg_group = card.addGroup(FluentIcon.CHECKBOX, "背景填充样式", "选择背景填充方式", page.combo_bg_fill, 2)

    # 背景增强
    page.chk_enhance = SwitchButton()
    page.chk_enhance.setChecked(True)
    card.addGroup(FluentIcon.CHECKBOX, "背景增强", "仅高斯模糊背景有效", page.chk_enhance)

    # 旋转适配（方案 §6.2/§6.3）：渲染期整帧方向适配。默认模式
    # 跟随样式声明（预设仅对竖图生效）；显式选择顺/逆时针对所有
    # 图片生效。addGroup 返回 GroupWidget 并存引用，供内容行动态
    # 提示使用。历史命名 portrait_adaptation 与 config 键保持兼容
    page.combo_portrait_adaptation = ComboBox()
    for _text, _value in PORTRAIT_ADAPTATION_ITEMS:
        page.combo_portrait_adaptation.addItem(_text, userData=_value)
    page.combo_portrait_adaptation.setMinimumWidth(200)
    page.combo_portrait_adaptation.setMaximumWidth(260)
    page.combo_portrait_adaptation.setCurrentIndex(
        page.combo_portrait_adaptation.findData(ADAPT_DEFAULT))
    page.combo_portrait_adaptation.currentIndexChanged.connect(
        page._on_portrait_adaptation_changed)
    page.combo_portrait_adaptation.setAccessibleName('旋转适配')
    page.portrait_adaptation_group = card.addGroup(
        FluentIcon.ROTATE,
        '旋转适配',
        # content 行保持短文案（contentLabel 不换行，长文案会把
        # GroupWidget 撑宽超出侧边栏）；完整语义放 tooltip
        '默认跟随样式',
        page.combo_portrait_adaptation,
        2,
    )
    _adapt_tip = ('默认模式遵循当前样式的适配声明，仅对竖图生效；'
                  '显式选择顺/逆时针适配时对所有图片生效，并覆盖样式声明')
    page.combo_portrait_adaptation.setToolTip(_adapt_tip)
    page.portrait_adaptation_group.setToolTip(_adapt_tip)

    # 字重（G3：userData 绑定稳定 key）
    page.combo_font_weight = ComboBox()
    for _text, _key in FONT_WEIGHT_ITEMS:
        page.combo_font_weight.addItem(_text, userData=_key)
    page.combo_font_weight.setCurrentIndex(0)
    page.combo_font_weight.setMinimumWidth(200)
    page.combo_font_weight.setMaximumWidth(260)
    fw_group = card.addGroup(FluentIcon.FONT, "字重", "选择文字粗细", page.combo_font_weight, 2)

    # ── 三个带下拉框的组统一标签列宽 ─────────────────────────
    # GroupWidget 按剩余空间拉伸 ComboBox，各标签列宽不同会导致
    # 下拉框宽度/左缘参差（用户反馈"上下对齐"）。取三组标题与描述
    # 理想宽度的最大值统一设为标签最小宽：三组标签列严格等宽后，
    # 结构参数完全一致 → 任意容器宽度下三个下拉框宽度与边缘
    # 必然对齐（分配规则无关性），且不抬高整组最小需求
    combo_groups = (bg_group, page.portrait_adaptation_group, fw_group)
    label_w = max(
        label.sizeHint().width()
        for group in combo_groups
        for label in (group.titleLabel, group.contentLabel)
    )
    for group in combo_groups:
        group.titleLabel.setMinimumWidth(label_w)
        group.contentLabel.setMinimumWidth(label_w)

    return card


def create_personalization_card(page) -> ExpandGroupSettingCard:
    """Tab 3: 个性化配置"""
    card = ExpandGroupSettingCard(FluentIcon.PEOPLE, "个性化配置", "作者、地点和自定义文本")

    # 作者姓名
    page.edit_author = LineEdit()
    page.edit_author.setPlaceholderText("请输入作者姓名")
    card.addGroup(FluentIcon.PEOPLE, "作者姓名", "将显示在相框中", page.edit_author, 3)

    # 拍摄地点
    page.edit_location = LineEdit()
    page.edit_location.setPlaceholderText("请输入拍摄地点")
    card.addGroup(FluentIcon.HOME, "拍摄地点", "将显示在相框中", page.edit_location, 3)

    # GPS 替换
    page.chk_use_gps = SwitchButton()
    card.addGroup(FluentIcon.GLOBE, "GPS 替换", "使用 EXIF 中的 GPS 数据", page.chk_use_gps)

    # 自定义文本（始终可见，由样式配置控制启用状态）
    page.edit_custom_text = LineEdit()
    page.edit_custom_text.setPlaceholderText("输入自定义文本...")
    card.addGroup(FluentIcon.EDIT, "自定义文本", "样式启用时可输入", page.edit_custom_text, 3)

    return card


def create_shot_info_card(page) -> ExpandGroupSettingCard:
    """Tab 4: 拍摄信息配置"""
    card = ExpandGroupSettingCard(FluentIcon.CAMERA, "拍摄信息配置", "拍摄时间、镜头和 LOGO 设置")

    # 拍摄时间（G3：userData 绑定稳定 key）
    page.combo_timestamp = ComboBox()
    for _text, _key in TIMESTAMP_DISPLAY_ITEMS:
        page.combo_timestamp.addItem(_text, userData=_key)
    page.combo_timestamp.setCurrentIndex(0)
    card.addGroup(FluentIcon.DATE_TIME, "拍摄时间", "控制相框中显示的拍摄时间信息", page.combo_timestamp, 1)

    # 镜头显示（G3：userData 绑定稳定 key）
    page.combo_lens_display = ComboBox()
    for _text, _key in LENS_DISPLAY_ITEMS:
        page.combo_lens_display.addItem(_text, userData=_key)
    page.combo_lens_display.setCurrentIndex(0)
    card.addGroup(FluentIcon.CAMERA, "镜头显示", "控制相框中显示的设备信息", page.combo_lens_display, 1)

    # 短版镜头名
    # 镜头名（三态下拉，G3：userData 绑定稳定 key，与 combo_lens_display 同构）
    page.combo_lens_name = ComboBox()
    for _text, _key in LENS_NAME_ITEMS:
        page.combo_lens_name.addItem(_text, userData=_key)
    page.combo_lens_name.setCurrentIndex(0)
    card.addGroup(FluentIcon.CAMERA, "镜头名", "默认按样式键取值；可强制完整名或短版名", page.combo_lens_name, 1)

    # LOGO（G3：哨兵文案改 userData 稳定 key，动态 logo 项以文件名
    # 为 userData——文案调整不再使渲染分支静默失效）
    page.combo_logo = ComboBox()
    page.combo_logo.addItem('自动匹配', userData=LOGO_AUTO)
    page.combo_logo.addItem('无', userData=LOGO_NONE)
    # 读取 assets/logos/ 目录下的实际 logo 文件
    logos = page.logo_selector.scan_logos()
    for _logo in logos:
        page.combo_logo.addItem(_logo, userData=_logo)
    card.addGroup(FluentIcon.IMAGE_EXPORT, "LOGO", "根据相机品牌自动匹配", page.combo_logo, 3)

    return card


def create_watermark_card(page) -> ExpandGroupSettingCard:
    """Tab 5: 文本水印"""
    card = ExpandGroupSettingCard(FluentIcon.EDIT, "文本水印", "添加自定义文字水印")

    # 启用水印
    page.chk_watermark = SwitchButton()
    card.addGroup(FluentIcon.CHECKBOX, "启用水印", "开启后可在图片上添加文字", page.chk_watermark)

    # 水印内容
    page.edit_watermark_text = LineEdit()
    page.edit_watermark_text.setPlaceholderText("输入水印文字...")
    card.addGroup(FluentIcon.EDIT, "水印内容", "输入要显示的文字", page.edit_watermark_text, 3)

    # 水印位置（G3：userData 绑定稳定 key）
    page.combo_wm_position = ComboBox()
    for _text, _key in WATERMARK_POSITION_ITEMS:
        page.combo_wm_position.addItem(_text, userData=_key)
    page.combo_wm_position.setCurrentIndex(4)  # 默认底部居中
    card.addGroup(FluentIcon.MARKET, "水印位置", "选择水印显示位置", page.combo_wm_position, 1)

    # 不透明度
    page.slider_opacity = Slider(Qt.Orientation.Horizontal)
    page.slider_opacity.setRange(0, 100)
    page.slider_opacity.setValue(50)
    card.addGroup(FluentIcon.ZOOM, "不透明度", "调节水印透明程度", page.slider_opacity)

    # 颜色（G3：userData 绑定稳定 key，渲染时经 _WM_COLOR_RGB 取 RGB）
    page.combo_wm_color = ComboBox()
    for _text, _key in WATERMARK_COLOR_ITEMS:
        page.combo_wm_color.addItem(_text, userData=_key)
    card.addGroup(FluentIcon.PALETTE, "水印颜色", "选择水印文字颜色", page.combo_wm_color, 1)

    return card


def collect_render_options(page, item):
    """从页面控件收集渲染元数据与选项（纯读控件，无副作用）

    G2 拆分：原 _on_generate_frame 方法体中段的配置收集逻辑
    （含 LOGO 选择语义与水印装饰拼装）收敛为纯函数，便于独立验证。

    Returns:
        (metadata, options, fw_key) 三元组
    """
    # 下拉框 userData 即稳定 key（G3），直接读 currentData()
    bg_key = page.combo_bg_fill.currentData() or BackgroundFillManager.DEFAULT_FILL
    fw_key = page.combo_font_weight.currentData() or 'medium'
    lens_key = page.combo_lens_display.currentData() or 'combined'
    ts_mode = page.combo_timestamp.currentData() or 'full'

    # GPS 替换逻辑
    gps_on = page.chk_use_gps.isChecked()
    gps_str = item.exif_data.get('gps', '') if item.exif_data else ''
    location = gps_str if (gps_on and gps_str) else page.edit_location.text()

    # LOGO 选择逻辑（userData：LOGO_AUTO / LOGO_NONE / 文件名）
    logo_opt = page.combo_logo.currentData()
    logo_filename = None
    if logo_opt == LOGO_NONE:
        logo_filename = ""
    elif logo_opt not in (LOGO_AUTO, None):
        logo_filename = logo_opt
    # LOGO_AUTO 保持 None：由 render_frame 在样式背景覆盖解析之后，
    # 按最终背景与显示品牌统一匹配，避免样式覆盖背景后 Logo 明暗错位

    # 水印装饰
    decorations = []
    if page.chk_watermark.isChecked() and page.edit_watermark_text.text():
        decorations.append({
            'type': 'watermark',
            'params': {
                'text': page.edit_watermark_text.text(),
                'position': page.combo_wm_position.currentData() or 'bottom-right',
                'opacity': page.slider_opacity.value(),
                'color': _WM_COLOR_RGB.get(
                    page.combo_wm_color.currentData() or 'white',
                    (255, 255, 255))
            }
        })

    metadata = RenderMetadata(
        author=page.edit_author.text() or None,
        location=location or None,
        custom_text=page.edit_custom_text.text() or None,
        lens_display_mode=lens_key,
        lens_name_mode=page.combo_lens_name.currentData() or 'default',
        timestamp_display_mode=ts_mode,
    )
    options = RenderOptions(
        bg_fill_type=bg_key,
        decorations=decorations or None,
        logo_filename=logo_filename,
        saturation_override=None if page.chk_enhance.isChecked() else 1.0,
        source_cache_key=item.cache_key,
        prepared_blur_cache=page._blur_lru,
        portrait_adaptation=page._get_portrait_adaptation(),
    )
    return metadata, options, fw_key
