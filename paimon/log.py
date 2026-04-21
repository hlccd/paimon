import sys
from pathlib import Path

from loguru import logger


def setup_logging(debug: bool = False, log_dir: Path | None = None):
    logger.remove()
    level = "TRACE" if debug else "INFO"

    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}",
    )

    if log_dir:
        log_path = log_dir / "paimon.log"
        logger.add(
            log_path,
            rotation="10 MB",
            retention="7 days",
            level="DEBUG",
        )
