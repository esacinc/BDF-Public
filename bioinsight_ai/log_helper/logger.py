# log_helper/logger.py
import logging
import sys

LOG_NAME = "bdf_chatbot"

def get_logger():
    logger = logging.getLogger(LOG_NAME)
    logger.propagate = False

    # Clear old handlers to avoid duplicate logs
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(filename)s:%(lineno)d | %(message)s'
    )

    stream_handler = logging.StreamHandler(sys.stdout)  # 🚀 Write to stdout
    stream_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)

    return logger
