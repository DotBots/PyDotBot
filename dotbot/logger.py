# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Logger module."""

import logging
import logging.config
from pathlib import Path

import structlog

LOG_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

# Worst case on disk is (1 + LOG_FILE_BACKUP_COUNT) * LOG_FILE_MAX_BYTES.
LOG_FILE_MAX_BYTES = 10 * 1024 * 1024
LOG_FILE_BACKUP_COUNT = 5

SUPPORTED_HANDLERS_DEFAULT = {
    "console": {
        "formatter": "rich",
        "class": "logging.StreamHandler",
        "stream": "ext://sys.stderr",
    },
    "file": {
        "class": "logging.handlers.RotatingFileHandler",
        "formatter": "logfmt",
        "encoding": "utf-8",
        "maxBytes": LOG_FILE_MAX_BYTES,
        "backupCount": LOG_FILE_BACKUP_COUNT,
    },
}


def setup_logging(filename, level, handlers):
    """Setup logging, creating the folder `filename` goes in."""
    processors = [
        # First, so an event below the level costs no processing
        structlog.stdlib.filter_by_level,
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

    stdlib_handlers = {}
    for handler, value in SUPPORTED_HANDLERS_DEFAULT.items():
        if handler == "file":
            if filename is None:
                continue
            else:
                Path(filename).parent.mkdir(parents=True, exist_ok=True)
                value["filename"] = filename
        stdlib_handlers.update({handler: value})

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
        "handlers": stdlib_handlers,
        "loggers": {
            "pydotbot": {
                "handlers": handlers,
                "level": LOG_LEVEL_MAP[level],
                "propagate": True,
            },
        },
    }
    logging.config.dictConfig(stdlib_config)


def debug_enabled(logger) -> bool:
    """Whether `logger` emits DEBUG events.

    structlog's stdlib logger spells the check `isEnabledFor`, its native
    filtering logger `is_enabled_for` (from 25.1), and before that the native
    logger has neither, in which case this answers True.
    """
    is_enabled = getattr(logger, "isEnabledFor", None) or getattr(
        logger, "is_enabled_for", None
    )
    return is_enabled is None or is_enabled(logging.DEBUG)


LOGGER = structlog.get_logger("pydotbot")
