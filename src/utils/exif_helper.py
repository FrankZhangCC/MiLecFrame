"""
EXIF信息处理辅助模块
负责提取、解析和格式化照片的EXIF信息
"""
import io
import piexif
from PIL import Image, ImageCms
from datetime import datetime
from typing import Dict, Optional, Tuple, Union
from .device_mapper import DeviceMapper


class ExifHelper:
    """EXIF信息处理助手类"""
    
    def __init__(self):
        """初始化EXIF助手，创建设备映射器实例"""
        self.device_mapper = DeviceMapper()
    
    def extract_exif_data(self, image_source: Union[str, bytes]) -> Optional[Dict[str, str]]:
        """
        提取图像的EXIF数据
        
        Args:
            image_source: 图像文件路径(str)或图像二进制数据(bytes)
            
        Returns:
            EXIF数据字典，如果无法提取则返回None
        """
        try:
            exif_dict = piexif.load(image_source)
            
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
                
                # 焦距信息
                if piexif.ExifIFD.FocalLength in exif_dict["Exif"]:
                    focal_length = exif_dict["Exif"][piexif.ExifIFD.FocalLength]
                    if isinstance(focal_length, tuple):
                        # 如果是分数形式 (分子, 分母)，转换为浮点数
                        actual_focal = focal_length[0] / focal_length[1]
                        exif_data['focal_length'] = f"{actual_focal:.1f}"
                    else:
                        exif_data['focal_length'] = str(focal_length)
                
                # 35mm等效焦距（相机直接提供的，优先使用）
                if piexif.ExifIFD.FocalLengthIn35mmFilm in exif_dict["Exif"]:
                    fl35 = exif_dict["Exif"][piexif.ExifIFD.FocalLengthIn35mmFilm]
                    fl35_value = fl35[0] / fl35[1] if isinstance(fl35, tuple) else float(fl35)
                    exif_data['focal_length_35mm'] = str(int(round(fl35_value)))
                
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
            
            # GPS 信息提取
            # piexif 将 GPS 数据存储在 "GPS" IFD 中，经纬度以 Rational 元组存储：
            #   GPSLatitude: ((deg_num, deg_den), (min_num, min_den), (sec_num, sec_den))
            #   GPSLongitude: 同上
            #   GPSLatitudeRef: b'N' 或 b'S'
            #   GPSLongitudeRef: b'E' 或 b'W'
            gps_str, gps_raw = ExifHelper._extract_gps(exif_dict)
            if gps_str:
                exif_data['gps'] = gps_str
                exif_data['gps_raw'] = gps_raw
            
            # 将设备信息记录到CSV文件中
            self._record_device_info(exif_data)
            
            return exif_data
        except Exception as e:
            print(f"EXIF提取错误: {str(e)}")
            return None
    
    def extract_raw_exif(self, image_source: Union[str, bytes]) -> Optional[Dict]:
        """
        提取完整的原始EXIF字典（piexif格式），不做字段拆解
        
        Args:
            image_source: 图像文件路径(str)或图像二进制数据(bytes)
            
        Returns:
            完整的piexif EXIF字典，如果无法提取则返回None
        """
        try:
            return piexif.load(image_source)
        except Exception as e:
            print(f"EXIF原始提取错误: {str(e)}")
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
                    fieldnames = ['original_lens', 'mapped_lens', 'short_lens']
                    writer = csv.writer(csvfile)
                    
                    if not header_exists:
                        writer.writerow(fieldnames)
                    
                    # 默认情况下，映射值等于原始值
                    writer.writerow([original_lens, original_lens, original_lens])
    
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
            short_lens = self.device_mapper.get_short_lens(original_lens)
            formatted_data['lens_model'] = mapped_lens
            formatted_data['short_lens'] = short_lens
        
        # 其他非设备信息保持不变
        for key in ['focal_length', 'aperture', 'shutter_speed', 'iso', 'datetime_original', 'gps']:
            if key in exif_data:
                formatted_data[key] = exif_data[key]
        
        return formatted_data

    @staticmethod
    def get_file_info(image: Image.Image) -> Dict[str, str]:
        """
        提取图像文件级元数据（格式、色彩空间、像素尺寸）

        Args:
            image: PIL Image 对象

        Returns:
            包含 format, color_space, width, height 的字典
        """
        img_format = image.format or "未知"
        img_width, img_height = image.size

        icc = image.info.get('icc_profile')
        if icc:
            try:
                color_space = ImageCms.getProfileDescription(io.BytesIO(icc))
            except Exception:
                color_space = "未知色彩空间"
        else:
            color_space = "sRGB（默认）"

        return {
            'format': img_format,
            'color_space': color_space,
            'width': img_width,
            'height': img_height,
        }

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
        
        # 组合相机型号（品牌+型号），同时保留映射后的品牌供 render_context 暴露
        if 'camera_make' in formatted_exif and 'camera_model' in formatted_exif:
            camera_make = formatted_exif['camera_make']
            camera_model = formatted_exif['camera_model']
            display_data['camera_make'] = camera_make
            display_data['camera_combined'] = f"{camera_make} {camera_model}"
        elif 'camera_make' in formatted_exif:
            display_data['camera_make'] = formatted_exif['camera_make']
            display_data['camera_combined'] = formatted_exif['camera_make']
        elif 'camera_model' in formatted_exif:
            display_data['camera_combined'] = formatted_exif['camera_model']
        
        # 添加镜头型号
        if 'lens_model' in formatted_exif:
            display_data['lens_model'] = formatted_exif['lens_model']
        if 'short_lens' in formatted_exif:
            display_data['short_lens'] = formatted_exif['short_lens']
        
        # 合并相机+镜头为单行输出（用于样式配置中 camera_lens 元素）
        camera_str = display_data.get('camera_combined', '')
        lens_str = display_data.get('lens_model', '')
        if camera_str and lens_str:
            display_data['camera_lens_combined'] = f"{camera_str} | {lens_str}"
        elif camera_str:
            display_data['camera_lens_combined'] = camera_str
        elif lens_str:
            display_data['camera_lens_combined'] = lens_str

        # 竖幅/方形图片专用：相机 + 短版镜头合并
        short_lens_str = display_data.get('short_lens', '')
        if camera_str and short_lens_str:
            display_data['camera_lens_combined_short'] = f"{camera_str} | {short_lens_str}"
        elif camera_str:
            display_data['camera_lens_combined_short'] = camera_str
        elif short_lens_str:
            display_data['camera_lens_combined_short'] = short_lens_str
        
        # 添加格式化的曝光参数
        display_data['exif_formatted'] = ExifHelper.format_exif_for_display(exif_data)
        
        # 添加原始数据用于GUI展示
        for key in ['camera_make', 'camera_model', 'focal_length', 'aperture', 'shutter_speed', 'iso', 'datetime_original', 'gps']:
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
    def _extract_gps(exif_dict: dict) -> Tuple[Optional[str], Optional[dict]]:
        """
        从 EXIF 字典中提取 GPS 信息并格式化为度分秒 (DMS) 字符串
        
        piexif 将 GPS 坐标存储为 Rational 元组：
          GPSLatitude:  ((deg_num, deg_den), (min_num, min_den), (sec_num, sec_den))
          GPSLongitude: 同上
          GPSLatitudeRef:  b'N' 或 b'S'（bytes 类型）
          GPSLongitudeRef: b'E' 或 b'W'（bytes 类型）
        
        Args:
            exif_dict: piexif.load() 返回的完整 EXIF 字典
            
        Returns:
            (gps_dms_string, raw_gps_dict) 或 (None, None)
        """
        if 'GPS' not in exif_dict:
            return None, None
        
        gps = exif_dict['GPS']
        
        # 提取经纬度坐标和方向标识
        lat = gps.get(piexif.GPSIFD.GPSLatitude)
        lat_ref = gps.get(piexif.GPSIFD.GPSLatitudeRef)
        lon = gps.get(piexif.GPSIFD.GPSLongitude)
        lon_ref = gps.get(piexif.GPSIFD.GPSLongitudeRef)
        
        # 四个字段缺一不可
        if not all([lat, lat_ref, lon, lon_ref]):
            return None, None
        
        # 确保坐标是三个 Rational 元组的格式
        if not (isinstance(lat, tuple) and len(lat) == 3):
            return None, None
        if not (isinstance(lon, tuple) and len(lon) == 3):
            return None, None
        
        # 分别格式化为 DMS 字符串
        lat_str = ExifHelper._format_dms(lat, lat_ref)
        lon_str = ExifHelper._format_dms(lon, lon_ref)
        
        gps_str = f"{lat_str} {lon_str}"
        
        # 收集原始 GPS 数据（含海拔）
        raw = {
            'latitude': lat,
            'latitude_ref': lat_ref,
            'longitude': lon,
            'longitude_ref': lon_ref,
        }
        
        return gps_str, raw
    
    @staticmethod
    def _format_dms(coords: tuple, ref) -> str:
        """
        将 piexif Rational 坐标元组格式化为度分秒 (DMS) 字符串
        
        Args:
            coords: ((deg_num, deg_den), (min_num, min_den), (sec_num, sec_den))
            ref: 方向标识 (b'N'/b'S'/b'E'/b'W' 或字符串)
            
        Returns:
            格式化后的 DMS 字符串，如 "40°26'46.1\"N"
        """
        # 将 Rational 元组转为浮点数：值 = 分子 / 分母
        deg = float(coords[0][0]) / float(coords[0][1])
        min_val = float(coords[1][0]) / float(coords[1][1])
        sec = float(coords[2][0]) / float(coords[2][1])
        
        # 方向标识可能是 bytes，需解码
        ref_str = ref.decode('ascii') if isinstance(ref, bytes) else str(ref)
        
        return f"{int(deg)}°{int(min_val)}'{sec:.1f}\"{ref_str}"
    
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
        
        # 焦距 - 优先使用EXIF提供的35mm等效焦距，否则直接用物理焦距
        if 'focal_length_35mm' in exif_data:
            parts.append(f"{exif_data['focal_length_35mm']}mm")
        elif 'focal_length' in exif_data:
            parts.append(f"{exif_data['focal_length']}mm")
        
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