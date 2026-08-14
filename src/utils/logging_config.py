# Copyright (c) 2026 FrankZhangCC
# GNU General Public License v3.0 - see LICENSE file for details

"""
日志配置模块
提供项目统一的日志初始化，确保各入口（CLI/GUI）获得一致的日志输出
"""
import logging
import sys
from pathlib import Path

# 统一的路径定位工具：打包后 debug_log.txt 写入 exe 同目录（便携版可持久化）
from src.utils.app_paths import get_app_dir

_initialized = False


class LineCountRotatingFileHandler(logging.FileHandler):
    """
    按行数滚动更新的日志处理器。

    继承自 logging.FileHandler，在每次写入日志后跟踪文件行数。
    当文件总行数超过 max_lines 时，自动删除最旧的记录，
    使文件始终保持最新的 max_lines 行。
    """

    def __init__(self, filename, max_lines=1000, encoding=None, delay=False):
        """
        初始化滚动日志处理器。

        Args:
            filename: 日志文件路径
            max_lines: 文件最大行数，超过时自动滚动（默认 1000）
            encoding: 文件编码（默认 None，由 FileHandler 自行决定）
            delay: 是否延迟打开文件直到第一次写入（默认 False）
        """
        # 以追加模式打开文件，不覆盖已有日志
        super().__init__(filename, mode='a', encoding=encoding, delay=delay)
        self.max_lines = max_lines
        # 启动时同步文件实际行数到内存计数器
        self._line_count = self._count_existing_lines()

    def _count_existing_lines(self):
        """
        统计当前日志文件的实际行数。

        用于初始化时与已有日志行数同步，以及在异常后重新校准计数器。

        Returns:
            文件行数（文件不存在时返回 0）
        """
        try:
            with open(self.baseFilename, 'r', encoding=self.encoding or 'utf-8') as f:
                return sum(1 for _ in f)
        except FileNotFoundError:
            return 0

    def emit(self, record):
        """
        写入一条日志记录，并在超过行数上限时触发滚动。

        重写自 logging.Handler.emit()，在父类写入完成后：
        1. 内存计数器 +1
        2. 如果超过 max_lines，调用 _roll_excess() 删除最旧的多余行

        Args:
            record: 日志记录对象（由 logging 框架自动传入）
        """
        # 先让父类完成正常的文件写入
        super().emit(record)
        # 内存计数器 +1（注意：若日志消息本身包含换行符，实际新增行数可能 >1，
        # 但计数偏差会在下次 _roll_excess 从文件重新统计时自动修正）
        self._line_count += 1
        if self._line_count > self.max_lines:
            self._roll_excess()

    def _roll_excess(self):
        """
        执行 FIFO 滚动：删除文件中最旧的记录，使行数降到 max_lines。

        流程：
        1. 读取当前文件的全部行
        2. 计算超出 max_lines 的行数
        3. 如果超出，仅保留最后 max_lines 行（即删除最旧的多余行）
        4. 重置内存计数器为 max_lines

        若文件读取/写入异常（如权限不足或被其他进程占用），
        则静默忽略并通过重新统计文件行数来校准计数器，
        确保不因单次失败导致计数器永久偏移。
        """
        try:
            with open(self.baseFilename, 'r', encoding=self.encoding or 'utf-8') as f:
                all_lines = f.readlines()
            # 计算实际超出多少行（可能 >1，因为多行消息一次可以写入多行）
            excess = len(all_lines) - self.max_lines
            if excess > 0:
                # 保留后 max_lines 行，即丢弃前面 excess 行（最旧的记录）
                with open(self.baseFilename, 'w', encoding=self.encoding or 'utf-8') as f:
                    f.writelines(all_lines[excess:])
            # 重置计数器为 max_lines（或实际行数，如果低于上限）
            self._line_count = min(len(all_lines), self.max_lines)
        except Exception:
            # 滚动失败时重新从文件统计，确保计数器不漂移
            self._line_count = self._count_existing_lines()


def setup_logging(log_dir: str = None) -> None:
    """
    初始化项目根日志配置

    将 DEBUG 级别日志输出到 debug_log.txt，INFO 及以上输出到控制台。
    已有配置时不会重复初始化。

    Args:
        log_dir: 日志目录，默认为项目根目录
    """
    global _initialized
    if _initialized:
        return

    # 幂等守卫（跨模块身份版）：
    # 打包环境中本模块会以 utils.logging_config 与 src.utils.logging_config
    # 两种身份各加载一份，各自的 _initialized 标志互不共享。
    # 此处再检查 root logger 上是否已挂载本类的 handler，避免日志重复写入。
    root_logger = logging.getLogger()
    if any(isinstance(h, LineCountRotatingFileHandler) for h in root_logger.handlers):
        return

    root_logger.setLevel(logging.DEBUG)

    if log_dir is None:
        log_dir = str(get_app_dir())
    log_path = Path(log_dir) / "debug_log.txt"

    # 使用按行数滚动的文件处理器替代普通 FileHandler
    file_handler = LineCountRotatingFileHandler(str(log_path), max_lines=1000, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        "%(levelname)s - %(message)s"
    ))

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    _initialized = True
