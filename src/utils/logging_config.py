"""
日志配置模块
提供项目统一的日志初始化，确保各入口（CLI/GUI）获得一致的日志输出
"""
import logging
import sys
from pathlib import Path

_initialized = False


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

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    if log_dir is None:
        log_dir = str(Path(__file__).resolve().parent.parent.parent)
    log_path = Path(log_dir) / "debug_log.txt"

    file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
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
