# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
样式管理器模块
负责管理相框样式配置文件
"""
import os
import json
import yaml
import toml
from pathlib import Path
from typing import Dict, Optional, List
import logging

# 统一的路径定位工具：
# - 内置样式目录为只读资源，随程序打包（_MEIPASS/src/frame_styles/configs）
# - 打包环境下用户新建样式保存在 exe 同目录 styles/（可写，升级不丢失）
from src.utils.app_paths import get_resource_root, get_app_dir, is_frozen
# 竖图旋转适配样式默认值校验（可选顶层字段，方案 §5.5 双层校验的第 1 层）
from src.utils.orientation_adaptation import validate_style_default
# 定位语义九点/交叉轴枚举（与 LayoutEngine 单一来源保持一致）
from src.utils.layout_engine import (
    ABSOLUTE_POSITIONS,
    ABSOLUTE_ALIGNMENTS,
    HORIZONTAL_CROSS_ALIGNMENTS,
    VERTICAL_CROSS_ALIGNMENTS,
    RELATIVE_POSITIONS,
)

# 旧 position 单轴别名 → 新九点迁移建议（唯一映射，直接给出目标值）
_POSITION_OLD_ALIAS_HINT = {
    'top': 'top-center',
    'tc': 'top-center',
    'bottom': 'bottom-center',
    'bc': 'bottom-center',
    'left': 'center-left',
    'right': 'center-right',
    'tl': 'top-left',
    'tr': 'top-right',
    'bl': 'bottom-left',
    'br': 'bottom-right',
}

# 旧 alignment 单轴值 → 新九点候选（单轴值无法唯一决定迁移结果，
# 只给候选集，由用户结合元素实际位置选择）
_ALIGNMENT_OLD_ALIAS_HINT = {
    'left': 'top-left / center-left / bottom-left',
    'right': 'top-right / center-right / bottom-right',
    'top': 'top-left / top-center / top-right',
    'bottom': 'bottom-left / bottom-center / bottom-right',
    'both-center': 'center',
}


class StyleManager:
    """相框样式管理器"""
    
    def __init__(self, config_dir: str = None):
        """
        初始化样式管理器
        
        Args:
            config_dir: 样式配置文件目录
        """
        if config_dir:
            # 显式指定目录时保持原有行为（不附加额外目录）
            self.config_dir = config_dir
            self.extra_dirs: List[str] = []
        else:
            # 内置样式目录：开发环境与打包环境统一指向资源目录
            self.config_dir = str(get_resource_root() / 'src' / 'frame_styles' / 'configs')
            # 打包环境下附加用户样式目录（exe 同目录 styles/），用户自建样式可持久保存
            self.extra_dirs = []
            if is_frozen():
                self.extra_dirs.append(str(get_app_dir() / 'styles'))
        
        self.logger = logging.getLogger(__name__)

    def _iter_style_dirs(self, style_name: str):
        """
        按优先级依次产出可能存在指定样式的目录（用户目录优先于内置目录）

        Args:
            style_name: 样式名称

        Yields:
            样式目录路径（仅产出实际存在的目录）
        """
        for base in self.extra_dirs + [self.config_dir]:
            d = os.path.join(base, style_name)
            if os.path.isdir(d):
                yield d

    def get_available_styles(self) -> List[str]:
        """
        获取所有可用的样式名称
        
        同时扫描单文件样式和文件夹样式（文件夹内包含变体配置），
        并合并内置目录与用户目录（用户目录同名样式优先，内置同名自动隐藏）
        
        Returns:
            样式名称列表
        """
        styles = []
        hidden = set()  # 用户目录已提供的内置同名样式
        
        for base in [*self.extra_dirs, self.config_dir]:
            if not os.path.exists(base):
                continue
            
            for entry_name in os.listdir(base):
                entry_path = os.path.join(base, entry_name)
                
                if os.path.isdir(entry_path):
                    # 文件夹样式：文件夹名即为样式名
                    if entry_name in hidden:
                        continue
                    if base != self.config_dir:
                        hidden.add(entry_name)  # 用户目录样式屏蔽内置同名
                    if entry_name not in styles:
                        styles.append(entry_name)
                elif entry_name.endswith(('.json', '.yaml', '.yml', '.toml')):
                    # 单文件样式：文件名（去扩展名）即为样式名
                    style_name = os.path.splitext(entry_name)[0]
                    if style_name in hidden:
                        continue
                    if base != self.config_dir:
                        hidden.add(style_name)
                    if style_name not in styles:
                        styles.append(style_name)
        
        return sorted(styles)
    
    def _load_config_file(self, config_path: str) -> Optional[Dict]:
        """加载单个配置文件"""
        ext = os.path.splitext(config_path)[1].lower()
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                if ext == '.json':
                    config = json.load(f)
                elif ext in ('.yaml', '.yml'):
                    config = yaml.safe_load(f)
                elif ext == '.toml':
                    config = toml.load(f)
                else:
                    return None
            
            if not isinstance(config, dict):
                self.logger.error(f"配置文件格式错误，应为字典类型: {config_path}")
                return None
            
            if self._validate_config(config, config_path):
                return config
            else:
                self.logger.error(f"样式配置无效: {config_path}")
                return None
                
        except Exception as e:
            self.logger.error(f"读取样式配置失败 {config_path}: {str(e)}")
            return None

    def _resolve_style_variant(self, style_dir: str, context: Optional[Dict]) -> Optional[str]:
        """
        根据上下文从文件夹中选取最佳变体配置文件
        
        命名规则（片段，无特定顺序）：
          default.yaml              → 默认配置（兜底）
          no_{field}.yaml            → 当 {field} 缺失时匹配
          no_{field1}_no_{field2}.yaml → 当多个字段同时缺失时匹配（更具体优先）
        
        Args:
            style_dir: 样式文件夹路径
            context: 上下文字典 {'location': ..., 'author': ...}，None 表示无上下文
        
        Returns:
            匹配的配置文件路径，未找到则返回 None
        """
        if not os.path.isdir(style_dir):
            return None
        
        # 收集文件夹内的所有配置文件
        config_files = []
        for fname in os.listdir(style_dir):
            if fname.endswith(('.json', '.yaml', '.yml', '.toml')):
                config_files.append(fname)
        
        if not config_files:
            return None
        
        # 确定缺失的字段集合
        missing_fields = set()
        if context:
            for field, value in context.items():
                if value is None or value == '':
                    missing_fields.add(field)
        
        # 从文件名解析匹配条件：no_{field}_.yaml → {field}
        def parse_missing_set(filename: str) -> set:
            name = os.path.splitext(filename)[0]
            if name.lower() == 'default':
                return set()
            parts = name.split('_')
            fields = set()
            i = 0
            while i < len(parts):
                if parts[i].lower() == 'no' and i + 1 < len(parts):
                    i += 1
                    field_parts = []
                    while i < len(parts) and parts[i].lower() != 'no':
                        field_parts.append(parts[i])
                        i += 1
                    if field_parts:
                        fields.add('_'.join(field_parts))
                else:
                    i += 1
            return fields
        
        # 按匹配精确度排序：匹配字段数越多越优先（更具体）
        best_file = None
        best_score = -1
        
        for fname in config_files:
            required_missing = parse_missing_set(fname)
            
            if required_missing == set():
                # default.yaml — 最低优先级，只在无更好选择时使用
                continue
            
            # 变体文件的缺失集合必须是实际缺失集合的子集
            if required_missing.issubset(missing_fields):
                score = len(required_missing)
                if score > best_score:
                    best_score = score
                    best_file = fname
        
        if best_file:
            return os.path.join(style_dir, best_file)
        
        # 兜底：查找 default.*
        for fname in config_files:
            if os.path.splitext(fname)[0].lower() == 'default':
                return os.path.join(style_dir, fname)
        
        # 无 default 文件时，返回第一个配置文件
        return os.path.join(style_dir, config_files[0])

    def get_style_config(self, style_name: str, context: Optional[Dict] = None) -> Optional[Dict]:
        """
        获取指定样式的配置，支持文件夹变体选择
        
        Args:
            style_name: 样式名称
            context: 上下文信息，如 {'location': '北京', 'author': '张三'}
                     用于从文件夹样式中选取最佳变体配置
            
        Returns:
            样式配置字典，如果不存在则返回None
        """
        # 1. 尝试作为文件夹样式加载（文件夹优先，用户目录优先于内置目录）
        for style_dir in self._iter_style_dirs(style_name):
            config_path = self._resolve_style_variant(style_dir, context)
            if config_path:
                return self._load_config_file(config_path)
            self.logger.error(f"样式文件夹内无有效配置文件: {style_name}")
            return None
        
        # 2. 尝试作为单文件样式加载（向后兼容，用户目录优先）
        for base in [*self.extra_dirs, self.config_dir]:
            for ext in ['.json', '.yaml', '.yml', '.toml']:
                config_path = os.path.join(base, f"{style_name}{ext}")
                if os.path.exists(config_path):
                    return self._load_config_file(config_path)
        
        self.logger.error(f"样式配置文件不存在: {style_name}")
        return None
    
    # ── 定位语义校验（position / alignment / cross_alignment） ──

    def _iter_positioned_elements(self, config: Dict):
        """
        统一遍历五类定位元素，产出 (字段路径, 定位配置) 元组。

        覆盖：layout.info_position.* / layout.defined_texts.* /
        layout.custom_text / layout.rectangles.* / 顶层 logo。
        未启用的 custom_text / logo（enabled: false）不参与渲染，跳过校验。
        """
        layout = config.get('layout', {})
        if not isinstance(layout, dict):
            return

        info_positions = layout.get('info_position', {})
        if isinstance(info_positions, dict):
            for key, cfg in info_positions.items():
                if isinstance(cfg, dict):
                    yield f"layout.info_position.{key}", cfg

        defined_texts = layout.get('defined_texts', {})
        if isinstance(defined_texts, dict):
            for key, cfg in defined_texts.items():
                if isinstance(cfg, dict):
                    yield f"layout.defined_texts.{key}", cfg

        custom_text = layout.get('custom_text', {})
        if isinstance(custom_text, dict) and custom_text.get('enabled', False):
            yield 'layout.custom_text', custom_text

        rectangles = layout.get('rectangles', {})
        if isinstance(rectangles, dict):
            for key, cfg in rectangles.items():
                if isinstance(cfg, dict):
                    yield f"layout.rectangles.{key}", cfg

        logo = config.get('logo', {})
        if isinstance(logo, dict) and logo.get('enabled', False):
            yield 'logo', logo

    def _validate_absolute_position_config(self, path: str, cfg: Dict) -> list:
        """
        绝对定位节点校验：必须显式提供九点 position 与九点 alignment，
        拒绝一切旧单轴别名 / both-center（返回错误信息列表）。
        """
        errors = []

        position = cfg.get('position', None)
        if position is None:
            errors.append(
                f"{path}.position 缺失：绝对定位节点必须显式提供九点 position"
                f"（{sorted(ABSOLUTE_POSITIONS)}）")
        elif position not in ABSOLUTE_POSITIONS:
            hint = _POSITION_OLD_ALIAS_HINT.get(str(position))
            extra = f"；建议迁移为 {hint}" if hint else ""
            errors.append(
                f"{path}.position 值非法: {position!r}{extra}。"
                f"合法九点值为 {sorted(ABSOLUTE_POSITIONS)}")

        alignment = cfg.get('alignment', None)
        if alignment is None:
            errors.append(
                f"{path}.alignment 缺失：绝对定位节点必须显式提供九点 alignment"
                f"（{sorted(ABSOLUTE_ALIGNMENTS)}）")
        elif alignment not in ABSOLUTE_ALIGNMENTS:
            hint = _ALIGNMENT_OLD_ALIAS_HINT.get(str(alignment))
            extra = f"；单轴旧值无法唯一迁移，请结合元素实际位置选择：{hint}" if hint else ""
            errors.append(
                f"{path}.alignment 值非法: {alignment!r}{extra}。"
                f"合法九点值为 {sorted(ABSOLUTE_ALIGNMENTS)}")

        return errors

    def _validate_relative_position_config(self, path: str, cfg: Dict) -> list:
        """
        相对定位节点校验：只接受 relative_to + relative_position +
        cross_alignment；出现旧 alignment 字段直接报错并提示改名为
        cross_alignment；cross_alignment 与方向轴必须匹配。
        """
        errors = []

        if 'alignment' in cfg:
            errors.append(
                f"{path}.alignment: 相对定位节点不允许使用 alignment 字段"
                f"（当前值: {cfg['alignment']!r}），请将该字段改名为 "
                f"cross_alignment（三值交叉轴对齐）")

        relative_position = cfg.get('relative_position', None)
        if relative_position is None:
            errors.append(
                f"{path}.relative_position 缺失：相对定位节点必须显式提供"
                f"（{sorted(RELATIVE_POSITIONS)}）")
        elif relative_position not in RELATIVE_POSITIONS:
            hint = {'after': 'below', 'before': 'above'}.get(
                str(relative_position))
            extra = f"；建议迁移为 {hint}" if hint else ""
            errors.append(
                f"{path}.relative_position 值非法: {relative_position!r}{extra}。"
                f"合法值为 {sorted(RELATIVE_POSITIONS)}")

        cross_alignment = cfg.get('cross_alignment', None)
        if cross_alignment is None:
            errors.append(
                f"{path}.cross_alignment 缺失：相对定位节点必须显式提供交叉轴"
                f"对齐（above/below → left/center/right；"
                f"left-of/right-of → top/center/bottom）")
        elif relative_position in ('above', 'below'):
            if cross_alignment not in HORIZONTAL_CROSS_ALIGNMENTS:
                errors.append(
                    f"{path}.cross_alignment 值非法: {cross_alignment!r} 与 "
                    f"relative_position={relative_position!r} 轴向不匹配；"
                    f"合法值为 {sorted(HORIZONTAL_CROSS_ALIGNMENTS)}")
        elif relative_position in ('left-of', 'right-of'):
            if cross_alignment not in VERTICAL_CROSS_ALIGNMENTS:
                errors.append(
                    f"{path}.cross_alignment 值非法: {cross_alignment!r} 与 "
                    f"relative_position={relative_position!r} 轴向不匹配；"
                    f"合法值为 {sorted(VERTICAL_CROSS_ALIGNMENTS)}")

        if cfg.get('tree_align', False):
            errors.append(
                f"{path}.tree_align: 相对定位节点不允许声明 tree_align"
                f"（tree_align 只属于绝对定位的树根节点）")

        return errors

    def _validate_positioning(self, config: Dict, source: str = '') -> bool:
        """
        遍历五类定位元素执行新语义校验。

        错误策略：任何旧别名、未知枚举、绝对/相对字段混用、轴向不匹配
        均视为样式加载失败；错误信息包含样式源文件、字段路径、错误值和
        人工迁移建议。返回 True 表示全部通过。
        """
        all_errors = []

        for path, cfg in self._iter_positioned_elements(config):
            if cfg.get('relative_to'):
                all_errors.extend(
                    self._validate_relative_position_config(path, cfg))
            else:
                all_errors.extend(
                    self._validate_absolute_position_config(path, cfg))

        for err in all_errors:
            src = f"[{source}] " if source else ""
            self.logger.error(f"[StyleValidation] {src}{err}")

        return not all_errors

    def _validate_config(self, config: Dict, source: str = '') -> bool:
        """
        验证配置是否有效
        
        Args:
            config: 配置字典
            
        Returns:
            配置是否有效
        """
        # 检查必需字段
        required_keys = ['name', 'layout']
        for key in required_keys:
            if key not in config:
                self.logger.error(f"配置缺少必需字段: {key}")
                return False
        
        # 确保layout是字典类型
        if not isinstance(config['layout'], dict):
            self.logger.error("layout字段应为字典类型")
            return False
            
        layout = config['layout']
        
        # 检查布局配置
        if 'expand_canvas' not in layout or not isinstance(layout['expand_canvas'], dict):
            layout['expand_canvas'] = {
                'enabled': False,
                'top': 0,
                'bottom': 0,
                'left': 0,
                'right': 0
            }
        
        # 检查信息位置配置
        if 'info_position' not in layout or not isinstance(layout['info_position'], dict):
            # 代码内默认配置直接使用唯一新 schema（九点 position + 九点 alignment）
            layout['info_position'] = {
                'exif': {'placement': 'outside', 'position': 'bottom-center', 'alignment': 'top-center', 'margin': 10},
                'author': {'placement': 'outside', 'position': 'bottom-center', 'alignment': 'top-center', 'margin': 10},
                'location': {'placement': 'outside', 'position': 'bottom-center', 'alignment': 'top-center', 'margin': 10}
            }
        else:
            # info_position 已有配置，不再注入默认条目
            # 渲染器按 info_position 中实际配置的元素驱动渲染
            pass
        
        # 检查颜色配置
        if 'colors' not in config or not isinstance(config['colors'], dict):
            config['colors'] = {
                'text': '#000000'
            }
        
        # 检查字体配置
        if 'fonts' not in config or not isinstance(config['fonts'], dict):
            config['fonts'] = {}
        else:
            # 确保字体大小配置存在
            if 'sizes' not in config['fonts'] or not isinstance(config['fonts']['sizes'], dict):
                config['fonts']['sizes'] = {}
            # 确保行间距配置存在
            if 'line_spacing_ratio' not in config['fonts']:
                config['fonts']['line_spacing_ratio'] = 0.005

        # 竖图旋转适配默认值校验（可选顶层字段；缺失=none，非法值
        # 如布尔/null/大小写变体/未知字符串时拒绝加载该样式）
        try:
            validate_style_default(config)
        except ValueError as e:
            self.logger.error(f"配置字段非法: {e}")
            return False

        # 语义版本开关检查：positioning_semantics 已随旧算法一并删除，
        # 出现即拒绝（不启用任何旧路径，提示直接删除该字段并迁移到新语义）
        if 'positioning_semantics' in config:
            self.logger.error(
                f"[StyleValidation] positioning_semantics="
                f"{config.get('positioning_semantics')!r}: "
                f"该语义版本开关字段已删除，运行时只有唯一一套定位算法；"
                f"请删除此字段并按新 schema 迁移 position/alignment"
                f"（参见 docs/plans/POSITION_ALIGNMENT_REPAIR_EXECUTION_PLAN.md §2）")
            return False

        # 定位语义校验：五类定位元素的 position/alignment/cross_alignment
        # 枚举与组合；旧别名不归一化、不猜测，直接拒绝并给迁移建议
        if not self._validate_positioning(config, source):
            return False

        return True
    
    def get_style_thumbnail(self, style_name: str) -> Optional[str]:
        """
        获取指定样式的缩略图路径
        
        在样式配置文件夹中查找 thumbnail.png / thumbnail.jpg / thumbnail.jpeg。
        
        Args:
            style_name: 样式名称
            
        Returns:
            缩略图文件绝对路径，不存在则返回 None
        """
        style_dirs = list(self._iter_style_dirs(style_name))
        if not style_dirs:
            return None
        
        for style_dir in style_dirs:
            for ext in ('.png', '.jpg', '.jpeg'):
                thumb_path = os.path.join(style_dir, f'thumbnail{ext}')
                if os.path.isfile(thumb_path):
                    return thumb_path
        
        return None

    def get_default_style(self) -> Optional[Dict]:
        """
        获取默认样式配置
        
        Returns:
            默认样式配置
        """
        # 尝试获取第一个可用样式作为默认样式
        available_styles = self.get_available_styles()
        if available_styles:
            return self.get_style_config(available_styles[0])
        
        return None
    
    def create_sample_styles(self):
        """创建示例样式配置文件"""
        # 创建configs目录（如果不存在）
        os.makedirs(self.config_dir, exist_ok=True)
        
        # 示例样式配置
        sample_config = {
            "name": "Classic",
            "description": "经典相框样式",
            "version": "1.0",
            "layout": {
                "expand_canvas": {
                    "enabled": True,
                    "top": 0.05,
                    "bottom": 0.1,
                    "left": 0.05,
                    "right": 0.05
                },
                "info_position": {
                    "exif": {
                        "placement": "outside",
                        "position": "bottom-center",
                        "alignment": "top-center",
                        "margin": 10
                    },
                    "author": {
                        "placement": "outside",
                        "position": "center-left",
                        "alignment": "center-right",
                        "margin": 10
                    },
                    "location": {
                        "placement": "outside",
                        "position": "center-right",
                        "alignment": "center-left",
                        "margin": 10
                    }
                }
            },
            "colors": {
                "text": "#000000"
            },
            "fonts": {
                "family": "Gotham",
                "weight": "medium",
                "size_ratio": 0.02,
                "sizes": {
                    "exif": 0.02,
                    "author": 0.018,
                    "location": 0.018
                }
            }
        }
        
        # 保存示例配置
        sample_path = os.path.join(self.config_dir, 'Default_TestFrame.json')
        with open(sample_path, 'w', encoding='utf-8') as f:
            json.dump(sample_config, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"示例样式配置已创建: {sample_path}")


# 创建默认样式管理器实例
default_style_manager = StyleManager()