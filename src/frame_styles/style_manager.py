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
        
        Returns:
            样式名称列表
        """
        styles = []
        
        if not os.path.exists(self.config_dir):
            return styles
        
        for file_name in os.listdir(self.config_dir):
            if file_name.endswith(('.json', '.yaml', '.yml', '.toml')):
                # 移除文件扩展名作为样式名
                style_name = os.path.splitext(file_name)[0]
                styles.append(style_name)
        
        return styles
    
    def get_style_config(self, style_name: str) -> Optional[Dict]:
        """
        获取指定样式的配置
        
        Args:
            style_name: 样式名称
            
        Returns:
            样式配置字典，如果不存在则返回None
        """
        # 查找对应的配置文件
        for ext in ['.json', '.yaml', '.yml', '.toml']:
            config_path = os.path.join(self.config_dir, f"{style_name}{ext}")
            
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        if ext == '.json':
                            config = json.load(f)
                        elif ext in ['.yaml', '.yml']:
                            config = yaml.safe_load(f)
                        elif ext == '.toml':
                            config = toml.load(f)
                        else:
                            continue
                    
                    # 确保配置是字典类型
                    if not isinstance(config, dict):
                        self.logger.error(f"配置文件格式错误，应为字典类型: {style_name}")
                        return None
                    
                    # 验证配置
                    if self._validate_config(config):
                        return config
                    else:
                        self.logger.error(f"样式配置无效: {style_name}")
                        return None
                        
                except Exception as e:
                    self.logger.error(f"读取样式配置失败 {style_name}: {str(e)}")
                    return None
        
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
                'exif': {'position': 'outside', 'alignment': 'center', 'margin': 10},
                'author': {'position': 'outside', 'alignment': 'center', 'margin': 10},
                'location': {'position': 'outside', 'alignment': 'center', 'margin': 10},
                'camera_icon': {'position': 'outside', 'alignment': 'top-left', 'margin': 10}
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
            config['fonts'] = {
                'family': 'Gotham',
                'weight': 'medium',
                'size_ratio': 0.02
            }
        else:
            # 确保字体大小配置存在
            if 'sizes' not in config['fonts'] or not isinstance(config['fonts']['sizes'], dict):
                config['fonts']['sizes'] = {}
        
        # 检查背景填充配置
        if 'background_fill' not in config or not isinstance(config['background_fill'], dict):
            config['background_fill'] = {
                'type': 'pure_white',
                'gaussian_blur_radius': 200,
                'gaussian_blur_opacity': 50
            }
        
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
                        "position": "outside",
                        "alignment": "center",
                        "margin": 10
                    },
                    "author": {
                        "position": "outside", 
                        "alignment": "left",
                        "margin": 10
                    },
                    "location": {
                        "position": "outside",
                        "alignment": "right", 
                        "margin": 10
                    },
                    "camera_icon": {
                        "position": "inside",
                        "alignment": "top-left",
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
            },
            "background_fill": {
                "type": "pure_white",
                "gaussian_blur_radius": 200,
                "gaussian_blur_opacity": 50
            }
        }
        
        # 保存示例配置
        sample_path = os.path.join(self.config_dir, 'Default_TestFrame.json')
        with open(sample_path, 'w', encoding='utf-8') as f:
            json.dump(sample_config, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"示例样式配置已创建: {sample_path}")


# 创建默认样式管理器实例
default_style_manager = StyleManager()