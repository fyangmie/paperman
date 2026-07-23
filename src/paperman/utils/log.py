from __future__ import annotations

import sys

from loguru import logger


def setup_logger(verbose: bool = False) -> None:
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    fmt = "<green>{time:HH:mm:ss}</green> | <level>{level:^8}</level> | <cyan>{message}</cyan>"
    logger.add(sys.stderr, format=fmt, level=level, colorize=True)
