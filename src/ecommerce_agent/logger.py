"""Basic logging configuration."""

import logging
import sys
from .config import config


def setup_logger(name: str = "ecommerce_agent") -> logging.Logger:
    """Configure and return a logger instance."""
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))
    return logger


# Default logger instance
log = setup_logger()
