import logging
import logging.handlers

from dotbot.logger import LOG_FILE_BACKUP_COUNT, LOG_FILE_MAX_BYTES, setup_logging


def test_log_file_rotates_by_size(tmp_path):
    """Guards against the file handler growing without bound."""
    setup_logging(str(tmp_path / "pydotbot.log"), "info", ["file"])
    logger = logging.getLogger("pydotbot")
    try:
        (handler,) = logger.handlers
        assert isinstance(handler, logging.handlers.RotatingFileHandler)
        assert handler.maxBytes == LOG_FILE_MAX_BYTES > 0
        assert handler.backupCount == LOG_FILE_BACKUP_COUNT > 0
    finally:
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()
