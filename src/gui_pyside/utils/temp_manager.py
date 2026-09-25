# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
临时文件生命周期管理器

TempManager 负责跟踪和清理所有在 GUI 运行期间创建的临时文件，
确保关闭窗口时不会留下残留文件。
"""
import os
import shutil
import tempfile
import logging
from typing import List


class TempManager:
    """临时文件生命周期管理器

    使用方法:
        temp_mgr = TempManager()
        tmp_path = temp_mgr.create_temp_file(suffix=".jpg")
        # ... 使用临时文件 ...
        temp_mgr.cleanup()  # 清理所有临时文件

    也可以作为上下文管理器使用:
        with TempManager() as temp_mgr:
            tmp_path = temp_mgr.create_temp_file(suffix=".jpg")
            # ... 使用临时文件 ...
        # 退出时自动清理
    """

    def __init__(self):
        self._temp_files: List[str] = []
        self._temp_dirs: List[str] = []
        self.logger = logging.getLogger(__name__)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False

    def create_temp_file(self, suffix: str = ".jpg", prefix: str = "mileica_") -> str:
        """创建临时文件并注册到跟踪列表

        Args:
            suffix: 文件后缀（如 ".jpg", ".png"）
            prefix: 文件名前缀

        Returns:
            临时文件的完整路径
        """
        fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
        os.close(fd)
        self._temp_files.append(path)
        self.logger.debug(f"创建临时文件: {path}")
        return path

    def create_temp_dir(self, prefix: str = "mileica_") -> str:
        """创建临时目录并注册到跟踪列表

        Args:
            prefix: 目录名前缀

        Returns:
            临时目录的完整路径
        """
        path = tempfile.mkdtemp(prefix=prefix)
        self._temp_dirs.append(path)
        self.logger.debug(f"创建临时目录: {path}")
        return path

    def cleanup(self):
        """清理所有临时文件和目录

        在窗口关闭时调用，确保不留下残留文件。
        单个文件删除失败不影响其他文件的清理。
        """
        cleaned_files = 0
        cleaned_dirs = 0

        # 清理临时文件
        for f in self._temp_files:
            try:
                if os.path.exists(f):
                    os.unlink(f)
                    cleaned_files += 1
            except OSError as e:
                self.logger.warning(f"清理临时文件失败 {f}: {e}")

        # 清理临时目录
        for d in self._temp_dirs:
            try:
                if os.path.exists(d):
                    shutil.rmtree(d, ignore_errors=True)
                    cleaned_dirs += 1
            except OSError as e:
                self.logger.warning(f"清理临时目录失败 {d}: {e}")

        self._temp_files.clear()
        self._temp_dirs.clear()

        if cleaned_files or cleaned_dirs:
            self.logger.info(f"清理完成: {cleaned_files} 个文件, {cleaned_dirs} 个目录")

    @property
    def temp_file_count(self) -> int:
        """当前跟踪的临时文件数量"""
        return len(self._temp_files)

    @property
    def temp_dir_count(self) -> int:
        """当前跟踪的临时目录数量"""
        return len(self._temp_dirs)
