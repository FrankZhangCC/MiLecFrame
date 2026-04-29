"""
EXIF信息处理辅助模块
负责提取、解析和格式化照片的EXIF信息
"""
import piexif
from PIL import Image
from datetime import datetime
from typing import Dict, Optional, Tuple
from .device_mapper import DeviceMapper


class ExifHelper:
    """EXIF信息处理助手类"""
    
    def __init__(self):
        """初始化EXIF助手，创建设备映射器实例"""
        self.device_mapper = DeviceMapper()
    
    def extract_exif_data(self, image_path: str) -> Optional[Dict[str, str]]:
        """
        提取图像的EXIF数据
        
        Args:
            image_path: 图像文件路径
            
        Returns:
            EXIF数据字典，如果无法提取则返回None
        """
        try:
            # 打开图像并获取EXIF数据
            exif_dict = piexif.load(image_path)
            
            # 提取所需字段
            exif_data = {}
            
            # 图像信息
            if "0th" in exif_dict:
                # 相机品牌和型号
                if piexif.ImageIFD.Make in exif_dict["0th"]:
                    exif_data['camera_make'] = self._safe_decode(exif_dict["0th"][piexif.ImageIFD.Make])
                
                if piexif.ImageIFD.Model in exif_dict["0th"]:
                    exif_data['camera_model'] = self._safe_decode(exif_dict["0th"][piexif.ImageIFD.Model])
            
            # Exif子IFD信息
            if "Exif" in exif_dict:
                # 镜头信息
                if piexif.ExifIFD.LensModel in exif_dict["Exif"]:
                    exif_data['lens_model'] = self._safe_decode(exif_dict["Exif"][piexif.ExifIFD.LensModel])
                
                # 焦距信息（转换为35mm等效焦距）
                if piexif.ExifIFD.FocalLength in exif_dict["Exif"]:
                    focal_length = exif_dict["Exif"][piexif.ExifIFD.FocalLength]
                    if isinstance(focal_length, tuple):
                        # 如果是分数形式 (分子, 分母)，转换为浮点数
                        actual_focal = focal_length[0] / focal_length[1]
                        exif_data['focal_length'] = f"{actual_focal:.1f}"
                    else:
                        exif_data['focal_length'] = str(focal_length)
                
                # 光圈
                if piexif.ExifIFD.FNumber in exif_dict["Exif"]:
                    f_number = exif_dict["Exif"][piexif.ExifIFD.FNumber]
                    if isinstance(f_number, tuple):
                        aperture = f_number[0] / f_number[1]
                        exif_data['aperture'] = f"{aperture:.1f}"
                    else:
                        exif_data['aperture'] = str(f_number)
                
                # 快门速度
                if piexif.ExifIFD.ExposureTime in exif_dict["Exif"]:
                    exposure_time = exif_dict["Exif"][piexif.ExifIFD.ExposureTime]
                    if isinstance(exposure_time, tuple):
                        shutter_speed = exposure_time[0] / exposure_time[1]
                        exif_data['shutter_speed'] = ExifHelper._format_shutter_speed(shutter_speed)
                    else:
                        exif_data['shutter_speed'] = str(exposure_time)
                
                # ISO
                if piexif.ExifIFD.ISOSpeedRatings in exif_dict["Exif"]:
                    iso = exif_dict["Exif"][piexif.ExifIFD.ISOSpeedRatings]
                    exif_data['iso'] = str(iso)
                
                # 拍摄时间
                if piexif.ExifIFD.DateTimeOriginal in exif_dict["Exif"]:
                    date_str = self._safe_decode(exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal])
                    formatted_date = ExifHelper._format_datetime(date_str)
                    exif_data['datetime_original'] = formatted_date
            
            # 将设备信息记录到CSV文件中
            self._record_device_info(exif_data)
            
            return exif_data
        except Exception as e:
            print(f"EXIF提取错误: {str(e)}")
            return None
    
    def _safe_decode(self, byte_string):
        """
        安全解码字节串到字符串，尝试多种编码方式
        
        Args:
            byte_string: 需要解码的字节串
            
        Returns:
            解码后的字符串
        """
        if isinstance(byte_string, str):
            return byte_string
        
        if not isinstance(byte_string, bytes):
            return str(byte_string)
        
        # 常见编码列表
        encodings = ['utf-8', 'latin-1', 'cp1252', 'shift-jis', 'gbk', 'big5']
        
        for encoding in encodings:
            try:
                decoded = byte_string.decode(encoding, errors='replace')
                # 移除null字符和其他控制字符
                decoded = ''.join(char for char in decoded if ord(char) >= 32 or char in '\n\r\t')
                return decoded.strip()
            except UnicodeDecodeError:
                continue
        
        # 如果所有编码都失败，使用latin-1（永远不会失败）但替换非打印字符
        fallback = byte_string.decode('latin-1', errors='replace')
        fallback = ''.join(char for char in fallback if ord(char) >= 32 or char in '\n\r\t')
        return fallback.strip()
    
    def _record_device_info(self, exif_data: Dict[str, str]) -> None:
        """
        记录设备信息到CSV文件中
        
        Args:
            exif_data: EXIF数据字典
        """
        import csv
        from pathlib import Path
        import os
        from datetime import datetime
        
        # 确定记录文件路径
        camera_map_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'camera_map.csv')
        lens_map_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'lens_map.csv')
        
        # 添加时间戳
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 处理相机信息
        if 'camera_make' in exif_data and 'camera_model' in exif_data:
            original_brand = exif_data['camera_make']
            original_model = exif_data['camera_model']
            
            # 检查相机信息是否已存在
            camera_recorded = False
            camera_map_file = Path(camera_map_path)
            
            if camera_map_file.exists():
                with open(camera_map_file, 'r', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        if (
                            row.get('original_brand') == original_brand and
                            row.get('original_model') == original_model
                        ):
                            camera_recorded = True
                            break
            
            # 如果未记录过，则添加新记录
            if not camera_recorded:
                header_exists = camera_map_file.exists()
                with open(camera_map_path, 'a', newline='', encoding='utf-8') as csvfile:
                    fieldnames = ['original_brand', 'original_model', 'mapped_brand', 'mapped_model', 'timestamp']
                    writer = csv.writer(csvfile)
                    
                    if not header_exists:
                        writer.writerow(fieldnames)
                    
                    # 默认情况下，映射值等于原始值
                    writer.writerow([
                        original_brand,
                        original_model,
                        original_brand,  # 默认映射品牌等于原始品牌
                        original_model,  # 默认映射机型等于原始机型
                        timestamp
                    ])
        
        # 处理镜头信息
        if 'lens_model' in exif_data:
            original_lens = exif_data['lens_model']
            
            # 检查镜头信息是否已存在
            lens_recorded = False
            lens_map_file = Path(lens_map_path)
            
            if lens_map_file.exists():
                with open(lens_map_file, 'r', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        if row.get('original_lens') == original_lens:
                            lens_recorded = True
                            break
            
            # 如果未记录过，则添加新记录
            if not lens_recorded:
                header_exists = lens_map_file.exists()
                with open(lens_map_path, 'a', newline='', encoding='utf-8') as csvfile:
                    fieldnames = ['original_lens', 'mapped_lens']
                    writer = csv.writer(csvfile)
                    
                    if not header_exists:
                        writer.writerow(fieldnames)
                    
                    # 默认情况下，映射值等于原始值
                    writer.writerow([original_lens, original_lens])
    
    def get_formatted_exif_for_display(self, exif_data: Dict[str, str]) -> Dict[str, str]:
        """
        获取格式化的EXIF数据，包含映射后的信息
        
        Args:
            exif_data: 原始EXIF数据字典
            
        Returns:
            包含原始和映射后数据的字典
        """
        if not exif_data:
            return {}
        
        formatted_data = {}
        
        # 处理品牌和机型（一起处理，因为它们关联在一起）
        if 'camera_make' in exif_data and 'camera_model' in exif_data:
            original_make = exif_data['camera_make']
            original_model = exif_data['camera_model']
            
            mapped_make, mapped_model = self.device_mapper.get_mapped_brand_and_model(original_make, original_model)
            
            # 只返回映射后的值，不显示映射标记
            formatted_data['camera_make'] = mapped_make
            formatted_data['camera_model'] = mapped_model
        elif 'camera_make' in exif_data:
            # 如果只有品牌没有型号，使用原始值（虽然这种情况比较少见）
            original_make = exif_data['camera_make']
            formatted_data['camera_make'] = original_make
        elif 'camera_model' in exif_data:
            # 如果只有型号没有品牌，使用映射后的型号
            original_model = exif_data['camera_model']
            mapped_model = self.device_mapper.get_mapped_model(original_model)
            formatted_data['camera_model'] = mapped_model
        
        # 处理镜头
        if 'lens_model' in exif_data:
            original_lens = exif_data['lens_model']
            mapped_lens = self.device_mapper.get_mapped_lens(original_lens)
            formatted_data['lens_model'] = mapped_lens
        
        # 其他非设备信息保持不变
        for key in ['focal_length', 'aperture', 'shutter_speed', 'iso', 'datetime_original']:
            if key in exif_data:
                formatted_data[key] = exif_data[key]
        
        return formatted_data
    
    def get_display_data(self, exif_data: Dict[str, str]) -> Dict[str, str]:
        """
        获取用于显示的数据，包括相机型号（品牌+型号）和镜头型号的组合
        
        Args:
            exif_data: 原始EXIF数据字典
            
        Returns:
            包含用于显示的数据的字典
        """
        if not exif_data:
            return {}
        
        # 获取格式化的EXIF数据
        formatted_exif = self.get_formatted_exif_for_display(exif_data)
        
        display_data = {}
        
        # 组合相机型号（品牌+型号）
        if 'camera_make' in formatted_exif and 'camera_model' in formatted_exif:
            camera_make = formatted_exif['camera_make']
            camera_model = formatted_exif['camera_model']
            display_data['camera_combined'] = f"{camera_make} {camera_model}"
        elif 'camera_model' in formatted_exif:
            display_data['camera_combined'] = formatted_exif['camera_model']
        
        # 添加镜头型号
        if 'lens_model' in formatted_exif:
            display_data['lens_model'] = formatted_exif['lens_model']
        
        # 合并相机+镜头为单行输出（用于样式配置中 camera_lens 元素）
        camera_str = display_data.get('camera_combined', '')
        lens_str = display_data.get('lens_model', '')
        if camera_str and lens_str:
            display_data['camera_lens_combined'] = f"{camera_str} | {lens_str}"
        elif camera_str:
            display_data['camera_lens_combined'] = camera_str
        elif lens_str:
            display_data['camera_lens_combined'] = lens_str
        
        # 添加格式化的曝光参数
        display_data['exif_formatted'] = ExifHelper.format_exif_for_display(exif_data)
        
        # 添加原始数据用于GUI展示
        for key in ['camera_make', 'camera_model', 'focal_length', 'aperture', 'shutter_speed', 'iso', 'datetime_original']:
            if key in exif_data:
                display_data[f'raw_{key}'] = exif_data[key]
        
        return display_data
    
    @staticmethod
    def _format_shutter_speed(shutter_speed: float) -> str:
        """
        格式化快门速度显示
        
        Args:
            shutter_speed: 以秒为单位的快门速度
            
        Returns:
            格式化的快门速度字符串
        """
        if shutter_speed >= 1.0:
            # >=1秒时显示小数形式
            return f"{shutter_speed:.1f}"
        else:
            # <1秒时显示分数形式
            denominator = round(1 / shutter_speed)
            return f"1/{denominator}"
    
    @staticmethod
    def _format_datetime(datetime_str: str) -> str:
        """
        格式化日期时间字符串
        
        Args:
            datetime_str: 原始日期时间字符串
            
        Returns:
            格式化后的日期时间字符串 (yyyy.mm.dd hh:mm:ss)
        """
        try:
            # 解析原始日期时间
            dt = datetime.strptime(datetime_str, "%Y:%m:%d %H:%M:%S")
            # 格式化为指定格式
            return dt.strftime("%Y.%m.%d %H:%M:%S")
        except ValueError:
            # 如果解析失败，返回原始字符串
            return datetime_str
    
    @staticmethod
    def format_exif_for_display(exif_data: Dict[str, str]) -> str:
        """
        将EXIF数据格式化为相框显示文本
        
        Args:
            exif_data: EXIF数据字典
            
        Returns:
            格式化的EXIF显示文本
        """
        if not exif_data:
            return ""
        
        # 组装相框显示文本
        parts = []
        
        # 焦距 - 使用35mm等效焦距
        if 'focal_length' in exif_data:
            # 获取物理焦距
            physical_focal = float(exif_data['focal_length'])
            # 计算35mm等效焦距
            equivalent_focal = ExifHelper._calculate_equivalent_focal(physical_focal, exif_data)
            parts.append(f"{equivalent_focal}mm")
        
        # 光圈
        if 'aperture' in exif_data:
            parts.append(f"f/{exif_data['aperture']}")
        
        # 快门
        if 'shutter_speed' in exif_data:
            parts.append(f"{exif_data['shutter_speed']}s")
        
        # ISO
        if 'iso' in exif_data:
            parts.append(f"ISO{exif_data['iso']}")
        
        return ", ".join(parts)
    
    @staticmethod
    def _calculate_equivalent_focal(physical_focal: float, exif_data: Dict[str, str]) -> int:
        """
        计算35mm等效焦距
        
        Args:
            physical_focal: 物理焦距
            exif_data: EXIF数据，可能包含传感器信息
            
        Returns:
            35mm等效焦距（整数）
        """
        # 尝试从相机型号获取裁切系数，这里我们使用常见的裁切系数
        camera_model = exif_data.get('camera_model', '').lower()
        
        # 常见相机型号的裁切系数
        crop_factors = {
            # 小米系列
            'xiaomi 15 pro': 2.7,  # 假设值，实际需要根据具体传感器尺寸
            'xiaomi': 2.7,
            # 微型四三系统
            'om': 2.0,  # Olympus/Panasonic Micro Four Thirds
            # APS-C画幅
            'canon': 1.6,  # Canon APS-C
            'nikon': 1.5,  # Nikon DX
            'sony': 1.5,   # Sony APS-C
            'fuji': 1.5,   # Fujifilm X系列
            # 全画幅
            'r5': 1.0,     # Canon R5
            'a7r': 1.0,    # Sony A7R series
            'd850': 1.0,   # Nikon D850
        }
        
        # 尝试匹配相机型号
        crop_factor = 1.0  # 默认为全画幅
        for model, factor in crop_factors.items():
            if model in camera_model:
                crop_factor = factor
                break
        
        # 计算等效焦距
        equivalent_focal = physical_focal * crop_factor
        return round(equivalent_focal)
    
    @staticmethod
    def get_camera_brand(exif_data: Dict[str, str]) -> Optional[str]:
        """
        从EXIF数据中获取相机品牌
        
        Args:
            exif_data: EXIF数据字典
            
        Returns:
            相机品牌名称
        """
        if 'camera_make' in exif_data:
            return exif_data['camera_make'].strip().lower()
        return None
    
    @staticmethod
    def get_camera_model(exif_data: Dict[str, str]) -> Optional[str]:
        """
        从EXIF数据中获取相机型号
        
        Args:
            exif_data: EXIF数据字典
            
        Returns:
            相机型号
        """
        if 'camera_model' in exif_data:
            return exif_data['camera_model'].strip()
        return None