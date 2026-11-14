import os
import sys

from loguru import logger

LEVELS = ("TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL")


def setup_logging():
    # ZENITH_LOG_LEVEL=DEBUG zenith-shell for the details
    level = os.environ.get("ZENITH_LOG_LEVEL", "INFO").upper()
    if level not in LEVELS:
        level = "INFO"

    logger.remove()
    logger.add(sys.stderr, level=level)
