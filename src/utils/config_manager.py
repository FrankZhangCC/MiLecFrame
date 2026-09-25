# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
配置管理模块
用于管理用户配置和持久化数据
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

# 统一的路径定位工具：打包后 config.json 写入 exe 同目录（便携版可持久化）
from src.utils.app_paths import get_app_dir


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file or str(get_app_dir() / 'config.json')
        
        # 确保配置文件存在
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """
        从文件加载配置
        
        Returns:
            配置字典
        """
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载配置文件失败: {str(e)}")
                return {}
        else:
            # 创建默认配置
            default_config = {
                "last_used": {},
                "user_preferences": {},
                "saved_values": {}
            }
            self._save_config(default_config)
            return default_config
    
    def _save_config(self, config: Dict[str, Any]) -> None:
        """
        保存配置到文件
        
        Args:
            config: 配置字典
        """
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存配置文件失败: {str(e)}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """
        设置配置值
        
        Args:
            key: 配置键
            value: 配置值
        """
        keys = key.split('.')
        config_ref = self.config
        
        for k in keys[:-1]:
            if k not in config_ref or not isinstance(config_ref[k], dict):
                config_ref[k] = {}
            config_ref = config_ref[k]
        
        config_ref[keys[-1]] = value
        self._save_config(self.config)
    
    def save_user_author(self, author: str) -> None:
        """
        保存用户作者名
        
        Args:
            author: 作者名
        """
        self.set('saved_values.author', author)
    
    def get_saved_author(self) -> Optional[str]:
        """
        获取保存的作者名
        
        Returns:
            作者名，如果未保存则返回None
        """
        return self.get('saved_values.author')
    
    def save_last_used_settings(self, settings: Dict[str, Any]) -> None:
        """
        保存上次使用的设置
        
        Args:
            settings: 设置字典
        """
        self.set('last_used.settings', settings)
    
    def get_last_used_settings(self) -> Dict[str, Any]:
        """
        获取上次使用的设置
        
        Returns:
            设置字典
        """
        return self.get('last_used.settings', {})


# 创建默认配置管理器实例
default_config_manager = ConfigManager()