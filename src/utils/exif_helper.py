"""
EXIF信息处理辅助模块
负责提取、解析和格式化照片的EXIF信息
"""
import piexif
from PIL import Image
from datetime import datetime
from typing import Dict, Optional, Tuple


class ExifHelper:
    """EXIF信息处理助手类"""
    
    @staticmethod
    def extract_exif_data(image_path: str) -> Optional[Dict[str, str]]:
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
                    exif_data['camera_make'] = exif_dict["0th"][piexif.ImageIFD.Make].decode('utf-8')
                
                if piexif.ImageIFD.Model in exif_dict["0th"]:
                    exif_data['camera_model'] = exif_dict["0th"][piexif.ImageIFD.Model].decode('utf-8')
            
            # Exif子IFD信息
            if "Exif" in exif_dict:
                # 镜头信息
                if piexif.ExifIFD.LensModel in exif_dict["Exif"]:
                    exif_data['lens_model'] = exif_dict["Exif"][piexif.ExifIFD.LensModel].decode('utf-8')
                
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
                    date_str = exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal].decode('utf-8')
                    formatted_date = ExifHelper._format_datetime(date_str)
                    exif_data['datetime_original'] = formatted_date
            
            return exif_data
        except Exception as e:
            print(f"EXIF提取错误: {str(e)}")
            return None
    
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