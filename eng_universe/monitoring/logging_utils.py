import logging
from functools import partial
from typing import Callable

from eng_universe.config import Settings

LOG_FORMAT = "%(asctime)s | %(message)s"
LOG_DATEFMT = "%H:%M:%S"


def _ensure_logging_configured() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATEFMT)


def get_logger(name: str) -> logging.Logger:
    _ensure_logging_configured()
    return logging.getLogger(name)


def log_event(logger: logging.Logger, event: str, **fields: object) -> None:
    if not Settings.crawl_log:
        return
    parts = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info("%-8s %s", event.upper(), parts)


def get_event_logger(name: str) -> Callable[..., None]:
    logger = get_logger(name)
    return partial(log_event, logger)
