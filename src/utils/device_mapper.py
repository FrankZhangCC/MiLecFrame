"""
设备映射数据库模块
用于管理和维护相机品牌及其别名的映射关系
"""
import csv
import os
from pathlib import Path
from typing import Dict, List, Optional


class DeviceMapper:
    """设备映射管理器"""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        初始化设备映射管理器
        
        Args:
            db_path: 设备映射数据库文件路径
        """
        self.db_path = db_path or os.path.join(
            os.path.dirname(__file__), '..', '..', 'data', 'device_map.csv'
        )
        
        # 确保数据库文件存在
        self._ensure_db_exists()
        
        # 加载设备映射
        self.device_map = self._load_device_map()
    
    def _ensure_db_exists(self) -> None:
        """确保设备映射数据库文件存在"""
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        
        if not db_file.exists():
            # 创建默认设备映射数据库
            with open(db_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['brand', 'alias'])  # 写入表头
                # 写入一些默认的设备映射
                default_mappings = [
                    ['Canon', '佳能'],
                    ['Nikon', '尼康'],
                    ['Sony', '索尼'],
                    ['Fujifilm', '富士'],
                    ['Olympus', '奥林巴斯'],
                    ['Panasonic', '松下'],
                    ['Leica', '莱卡'],
                    ['Hasselblad', '哈苏'],
                    ['Phase One', '飞思'],
                    ['Apple', '苹果'],
                    ['Google', '谷歌']
                ]
                
                for mapping in default_mappings:
                    writer.writerow(mapping)
    
    def _load_device_map(self) -> Dict[str, str]:
        """
        从CSV文件加载设备映射
        
        Returns:
            设备映射字典，键为别名，值为标准品牌名
        """
        device_map = {}
        
        try:
            with open(self.db_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    brand = row['brand'].strip().lower()
                    alias = row['alias'].strip().lower()
                    device_map[alias] = brand
        except FileNotFoundError:
            print(f"警告: 设备映射数据库文件不存在: {self.db_path}")
        except Exception as e:
            print(f"加载设备映射数据库时出错: {str(e)}")
        
        return device_map
    
    def get_standard_brand(self, brand_name: str) -> Optional[str]:
        """
        根据品牌名或别名获取标准品牌名
        
        Args:
            brand_name: 品牌名或别名
            
        Returns:
            标准品牌名，如果找不到则返回原始名称
        """
        if not brand_name:
            return None
            
        brand_lower = brand_name.lower()
        
        # 首先尝试直接匹配标准品牌名
        if brand_lower in self.device_map.values():
            return brand_lower.title()
        
        # 然后尝试匹配别名
        if brand_lower in self.device_map:
            return self.device_map[brand_lower].title()
        
        # 如果都找不到，返回原始名称
        return brand_name
    
    def add_mapping(self, brand: str, alias: str) -> bool:
        """
        添加新的品牌别名映射
        
        Args:
            brand: 标准品牌名
            alias: 别名
            
        Returns:
            是否添加成功
        """
        try:
            # 检查映射是否已存在
            if alias.lower() in self.device_map:
                print(f"警告: 别名 '{alias}' 已存在，映射到 '{self.device_map[alias.lower()]}'")
                return False
            
            # 添加到内存中的映射
            self.device_map[alias.lower()] = brand.lower()
            
            # 追加到CSV文件
            with open(self.db_path, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([brand, alias])
            
            print(f"成功添加映射: {alias} -> {brand}")
            return True
            
        except Exception as e:
            print(f"添加映射时出错: {str(e)}")
            return False
    
    def get_all_brands(self) -> List[str]:
        """
        获取所有标准品牌名
        
        Returns:
            标准品牌名列表
        """
        return list(set(self.device_map.values()))
    
    def refresh(self) -> None:
        """刷新设备映射，重新从文件加载"""
        self.device_map = self._load_device_map()
        print("设备映射数据库已刷新")