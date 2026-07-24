# Copyright (c) 2026 FrankZhangCC
# MIT License - see LICENSE file for details

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


class StyleManager:
    """相框样式管理器"""
    
    def __init__(self, config_dir: str = None):
        """
        初始化样式管理器
        
        Args:
            config_dir: 样式配置文件目录
        """
        if config_dir:
            self.config_dir = config_dir
        else:
            # 默认配置目录为当前目录下的configs子目录
            self.config_dir = os.path.join(os.path.dirname(__file__), 'configs')
        
        self.logger = logging.getLogger(__name__)
    
    def get_available_styles(self) -> List[str]:
        """
        获取所有可用的样式名称
        
        同时扫描单文件样式和文件夹样式（文件夹内包含变体配置）
        
        Returns:
            样式名称列表
        """
        styles = []
        
        if not os.path.exists(self.config_dir):
            return styles
        
        for entry_name in os.listdir(self.config_dir):
            entry_path = os.path.join(self.config_dir, entry_name)
            
            if os.path.isdir(entry_path):
                # 文件夹样式：文件夹名即为样式名
                styles.append(entry_name)
            elif entry_name.endswith(('.json', '.yaml', '.yml', '.toml')):
                # 单文件样式：文件名（去扩展名）即为样式名
                style_name = os.path.splitext(entry_name)[0]
                # 避免与同名文件夹冲突，文件夹优先
                if style_name not in styles:
                    styles.append(style_name)
        
        return styles
    
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
            
            if self._validate_config(config):
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
        # 1. 尝试作为文件夹样式加载（文件夹优先）
        style_dir = os.path.join(self.config_dir, style_name)
        if os.path.isdir(style_dir):
            config_path = self._resolve_style_variant(style_dir, context)
            if config_path:
                return self._load_config_file(config_path)
            self.logger.error(f"样式文件夹内无有效配置文件: {style_name}")
            return None
        
        # 2. 尝试作为单文件样式加载（向后兼容）
        for ext in ['.json', '.yaml', '.yml', '.toml']:
            config_path = os.path.join(self.config_dir, f"{style_name}{ext}")
            if os.path.exists(config_path):
                return self._load_config_file(config_path)
        
        self.logger.error(f"样式配置文件不存在: {style_name}")
        return None
    
    def _validate_config(self, config: Dict) -> bool:
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
            layout['info_position'] = {
                'exif': {'placement': 'outside', 'position': 'bottom', 'alignment': 'center', 'margin': 10},
                'author': {'placement': 'outside', 'position': 'bottom', 'alignment': 'center', 'margin': 10},
                'location': {'placement': 'outside', 'position': 'bottom', 'alignment': 'center', 'margin': 10}
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
        
        return True
    
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
                        "position": "bottom",
                        "alignment": "center",
                        "margin": 10
                    },
                    "author": {
                        "placement": "outside",
                        "position": "left",
                        "alignment": "center",
                        "margin": 10
                    },
                    "location": {
                        "placement": "outside",
                        "position": "right", 
                        "alignment": "center",
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