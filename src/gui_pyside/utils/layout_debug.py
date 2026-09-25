# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
ExpandSettingCard 布局诊断工具
用于排查折叠卡片展开/收起/灰色区域等布局问题
"""
import logging

logger = logging.getLogger(__name__)


def dump_expand_card(card) -> None:
    """
    打印折叠卡片的各层尺寸，用于诊断布局异常
    
    典型检查点：
      - 收起时 card.height() == card.card.height()（无底部间隙）
      - 展开时 spaceWidget.h >= view.h（滚动范围充足）
      - 任意子控件的 sizeHint 是否明显偏离实际视觉高度
    """
    cls_name = card.__class__.__name__
    header_h = card.card.height()
    gap = card.height() - header_h if not card.isExpand else 0
    space_ok = card.spaceWidget.height() >= card.view.height() if card.isExpand else True

    lines = [
        f'--- {cls_name} (isExpand={card.isExpand}) ---',
        f'  header height:     {header_h}',
        f'  card height:       {card.height()}',
        f'  scrollWidget:      {card.scrollWidget.height()}',
        f'  view:              {card.view.height()}',
        f'  spaceWidget:       {card.spaceWidget.height()}',
        f'  vScrollBar max:    {card.verticalScrollBar().maximum()}',
        f'  vScrollBar value:  {card.verticalScrollBar().value()}',
        f'  viewLayout sHint:  {card.viewLayout.sizeHint().height()}',
        f'  widgets count:     {len(card.widgets)}',
    ]

    if gap > 0:
        lines.append(f'  ⚠ 收起底部间隙: {gap}px (正常应为 0)')
    if not space_ok:
        lines.append(f'  ⚠ 滚动范围不足: spaceWidget({card.spaceWidget.height()}) < view({card.view.height()})')

    for i, w in enumerate(card.widgets):
        sh = w.sizeHint()
        mh = w.maximumHeight()
        lines.append(f'    widget[{i}] sizeHint.h={sh.height()} maxH={mh}')
        if mh > sh.height() + 20:
            lines.append(f'      ← 可能使用了 setFixedHeight({mh})，sizeHint 不可靠')

    lines.append('')
    for line in lines:
        logger.info(line)
    print('\n'.join(lines))
