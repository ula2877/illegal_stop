import logging
import os
from logging.handlers import TimedRotatingFileHandler
from utils.config_loader import load_config


def setup_logger():
    config = load_config()
    log_dir = config.get("evidence_path", "./logs")

    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "app.log")

    logger = logging.getLogger("app_logger")
    logger.setLevel(logging.INFO)

    if logger.hasHandlers():
        return logger  # hindari duplicate handler

    # Format log
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(threadName)s | %(message)s"
    )

    # Rotasi harian
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=7  # simpan 7 hari
    )
    file_handler.setFormatter(formatter)

    # Optional: tampilkan juga di console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# singleton instance
logger = setup_logger()