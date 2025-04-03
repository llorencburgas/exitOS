import logging
import colorlog

def setup_logger(level=logging.DEBUG):
    """Setup logger for Home Assistant add-on."""
    logger = logging.getLogger("exitOS")

    #prevent duplicate handlers
    if logger.hasHandlers():
        logger.handlers.clear()


    logger.setLevel(level)


    handler = logging.StreamHandler()  # Important! Sends logs to stdout for HA
    handler.setLevel(level)

    formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(levelname)s: %(message)s",
        log_colors={
            'DEBUG': 'green',
            'INFO': 'blue',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        }
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
