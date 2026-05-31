# Copyright (c) 2026 FrankZhangCC
# MIT License - see LICENSE file for details

"""
设备映射数据库模块
用于管理和维护相机品牌、机型及镜头的映射关系
"""
import csv
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DeviceMapper:
    """设备映射管理器"""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        初始化设备映射管理器
        
        Args:
            db_path: 设备映射数据库文件路径
        """
        self.db_base_path = db_path or os.path.join(
            os.path.dirname(__file__), '..', '..', 'data'
        )
        
        # 构建各个映射文件路径
        self.camera_db_path = os.path.join(self.db_base_path, 'camera_map.csv')
        self.lens_db_path = os.path.join(self.db_base_path, 'lens_map.csv')
        
        # 确保数据库文件存在
        self._ensure_dbs_exist()
        
        # 加载设备映射
        self.camera_map = self._load_camera_map()
        self.lens_map = self._load_lens_map()
        self.short_lens_map = self._load_short_lens_map()
    
    def _ensure_dbs_exist(self) -> None:
        """确保设备映射数据库文件存在"""
        db_files = [self.camera_db_path, self.lens_db_path]
        
        for db_file in db_files:
            file_path = Path(db_file)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            if not file_path.exists():
                # 创建默认设备映射数据库
                with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    
                    if 'camera' in str(file_path):
                        writer.writerow(['original_brand', 'original_model', 'mapped_brand', 'mapped_model', 'timestamp'])  # 写入表头
                    elif 'lens' in str(file_path):
                        writer.writerow(['original_lens', 'mapped_lens', 'short_lens'])  # 写入表头
    
    def _load_camera_map(self) -> Dict[Tuple[str, str], Dict[str, str]]:
        """
        从CSV文件加载相机映射
        
        Returns:
            相机映射字典，键为(原始品牌, 原始机型)，值为{映射品牌, 映射机型}
        """
        camera_map = {}
        
        try:
            with open(self.camera_db_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    original_brand = row['original_brand'].strip()
                    original_model = row['original_model'].strip()
                    mapped_brand = row['mapped_brand'].strip()
                    mapped_model = row['mapped_model'].strip()
                    
                    # 构建相机映射：键为(原始品牌, 原始机型)，值为{映射品牌, 映射机型}
                    camera_map[(original_brand, original_model)] = {
                        'mapped_brand': mapped_brand,
                        'mapped_model': mapped_model
                    }
        except FileNotFoundError:
            logger.warning("相机映射数据库文件不存在: %s", self.camera_db_path)
        except Exception as e:
            logger.warning("加载相机映射数据库时出错: %s", e)
        
        return camera_map
    
    def _load_lens_map(self) -> Dict[str, str]:
        """
        从CSV文件加载镜头映射
        
        Returns:
            镜头映射字典，键为原始镜头，值为映射后的镜头
        """
        lens_map = {}
        
        try:
            with open(self.lens_db_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    original_lens = row['original_lens'].strip()
                    mapped_lens = row['mapped_lens'].strip()
                    if original_lens and mapped_lens:
                        lens_map[original_lens] = mapped_lens
        except FileNotFoundError:
            logger.warning("镜头映射数据库文件不存在: %s", self.lens_db_path)
        except Exception as e:
            logger.warning("加载镜头映射数据库时出错: %s", e)

        return lens_map

    def _load_short_lens_map(self) -> Dict[str, str]:
        """
        从CSV文件加载短版镜头名称映射
        
        如果 CSV 中不存在 short_lens 列（旧格式兼容），回退使用 mapped_lens 作为短版名称
        
        Returns:
            短版镜头映射字典，键为原始镜头，值为短版镜头名
        """
        short_lens_map = {}
        
        try:
            with open(self.lens_db_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                has_short_column = 'short_lens' in (reader.fieldnames or [])
                for row in reader:
                    original_lens = row['original_lens'].strip()
                    if not original_lens:
                        continue
                    if has_short_column and row.get('short_lens', '').strip():
                        short_lens_map[original_lens] = row['short_lens'].strip()
                    elif row.get('mapped_lens', '').strip():
                        short_lens_map[original_lens] = row['mapped_lens'].strip()
        except FileNotFoundError:
            logger.warning("镜头映射数据库文件不存在: %s", self.lens_db_path)
        except Exception as e:
            logger.warning("加载短版镜头映射时出错: %s", e)
        
        return short_lens_map

    def get_mapped_brand_and_model(self, brand_name: str, model_name: str) -> Tuple[str, str]:
        """
        根据品牌和机型获取映射后的品牌和机型
        
        Args:
            brand_name: 原始品牌名
            model_name: 原始机型名
            
        Returns:
            映射后的品牌名和机型名
        """
        if not brand_name or not model_name:
            return brand_name, model_name
            
        # 检查是否存在于映射中
        if (brand_name, model_name) in self.camera_map:
            mapped_data = self.camera_map[(brand_name, model_name)]
            return mapped_data['mapped_brand'], mapped_data['mapped_model']
        
        # 如果不存在映射，则返回原始值
        return brand_name, model_name

    def get_mapped_model(self, model_name: str) -> str:
        """
        根据原始机型获取映射后的机型
        
        Args:
            model_name: 原始机型名
            
        Returns:
            映射后的机型名，如果找不到则返回原始名称
        """
        if not model_name:
            return model_name
            
        # 由于现在机型映射是与品牌一起存储的，需要遍历整个映射表
        for (original_brand, original_model), mapped_data in self.camera_map.items():
            if original_model == model_name:
                return mapped_data['mapped_model']
        
        # 如果没找到，返回原始值
        return model_name
    
    def get_mapped_lens(self, lens_name: str) -> str:
        """
        根据原始镜头名获取映射后的镜头名
        
        Args:
            lens_name: 原始镜头名
            
        Returns:
            映射后的镜头名，如果找不到则返回原始名称
        """
        if not lens_name:
            return lens_name
            
        return self.lens_map.get(lens_name, lens_name)

    def get_short_lens(self, lens_name: str) -> str:
        """
        根据原始镜头名获取短版镜头名称（用于竖幅/方形图片）
        
        Args:
            lens_name: 原始镜头名
            
        Returns:
            短版镜头名，如果找不到则回退到 mapped_lens 或原始名称
        """
        if not lens_name:
            return lens_name
        
        short = self.short_lens_map.get(lens_name)
        if short:
            return short
        return self.lens_map.get(lens_name, lens_name)

    def add_camera_mapping(self, original_brand: str, original_model: str, mapped_brand: str, mapped_model: str, timestamp: str) -> bool:
        """
        添加新的相机映射
        
        Args:
            original_brand: 原始品牌名
            original_model: 原始机型名
            mapped_brand: 映射后的品牌名
            mapped_model: 映射后的机型名
            timestamp: 时间戳
            
        Returns:
            是否添加成功
        """
        try:
            # 检查映射是否已存在
            if (original_brand, original_model) in self.camera_map:
                print(f"警告: 相机 '{original_brand} {original_model}' 的映射已存在")
                return False
            
            # 添加到内存中的映射
            self.camera_map[(original_brand, original_model)] = {
                'mapped_brand': mapped_brand,
                'mapped_model': mapped_model
            }
            
            # 追加到CSV文件
            with open(self.camera_db_path, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([original_brand, original_model, mapped_brand, mapped_model, timestamp])
            
            print(f"成功添加相机映射: {original_brand} {original_model} -> {mapped_brand} {mapped_model}")
            return True
            
        except Exception as e:
            print(f"添加相机映射时出错: {str(e)}")
            return False
    
    def add_lens_mapping(self, original_lens: str, mapped_lens: str, short_lens: Optional[str] = None) -> bool:
        """
        添加新的镜头映射
        
        Args:
            original_lens: 原始镜头名
            mapped_lens: 映射后的镜头名
            short_lens: 短版镜头名（可选，默认等于 mapped_lens）
            
        Returns:
            是否添加成功
        """
        try:
            if short_lens is None:
                short_lens = mapped_lens

            # 检查映射是否已存在
            if original_lens in self.lens_map:
                print(f"警告: 镜头 '{original_lens}' 的映射已存在，当前映射为: '{self.lens_map[original_lens]}'")
                return False
            
            # 添加到内存中的映射
            self.lens_map[original_lens] = mapped_lens
            self.short_lens_map[original_lens] = short_lens
            
            # 追加到CSV文件
            with open(self.lens_db_path, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([original_lens, mapped_lens, short_lens])
            
            print(f"成功添加镜头映射: {original_lens} -> {mapped_lens} [短版: {short_lens}]")
            return True
            
        except Exception as e:
            print(f"添加镜头映射时出错: {str(e)}")
            return False

    def refresh(self) -> None:
        """刷新设备映射，重新从文件加载"""
        self.camera_map = self._load_camera_map()
        self.lens_map = self._load_lens_map()
        self.short_lens_map = self._load_short_lens_map()
        logger.info("设备映射数据库已刷新")