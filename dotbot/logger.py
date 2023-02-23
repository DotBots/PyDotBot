"""Logger module."""

import logging
import structlog


LOG_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def setup_logging(filename, level):
    """Setup logging."""
    logging.basicConfig(
        filename=filename, format="", encoding="utf-8", level=LOG_LEVEL_MAP[level]
    )
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt=None),
            structlog.processors.LogfmtRenderer(
                key_order=["timestamp", "level", "event"]
            ),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
