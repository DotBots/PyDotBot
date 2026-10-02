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


def _drop_handlers():
    logger = logging.getLogger("pydotbot")
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()


def test_log_file_folder_is_created(tmp_path):
    path = tmp_path / "not" / "there" / "pydotbot.log"
    try:
        setup_logging(str(path), "info", ["file"])
    finally:
        _drop_handlers()
    assert path.parent.is_dir()


def test_run_controller_names_a_log_file_it_cannot_write(tmp_path):
    from click.testing import CliRunner

    from dotbot.controller_app import main

    blocker = tmp_path / "a-file"
    blocker.write_text("")
    result = CliRunner().invoke(
        main,
        ["--conn", "simulator", "--log-output", str(blocker / "pydotbot.log")],
    )
    _drop_handlers()
    assert result.exit_code == 1, result.output
    assert f"cannot write the log file {blocker / 'pydotbot.log'}" in result.output
    assert "Traceback" not in result.output
