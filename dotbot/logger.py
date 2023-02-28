"""Logger module."""

import logging
import structlog


LOG_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def setup_logging(filename, level, handlers):
    """Setup logging."""
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    stdlib_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "logfmt": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.processors.LogfmtRenderer(
                    key_order=["timestamp", "level", "logger", "event"],
                    drop_missing=True,
                ),
            },
            "rich": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.dev.ConsoleRenderer(),
            },
        },
        "handlers": {
            "console": {
                "formatter": "rich",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "logfmt",
                "filename": filename,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "pydotbot": {
                "handlers": handlers,
                "level": LOG_LEVEL_MAP[level],
                "propagate": True,
            },
        },
    }
    logging.config.dictConfig(stdlib_config)


LOGGER = structlog.get_logger("pydotbot")
