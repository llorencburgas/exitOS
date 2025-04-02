import logging
import colorlog

def setup_logger(level=logging.DEBUG):
    """Setup logger for Home Assistant add-on."""
    logger = logging.getLogger("exitOS")
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()  # Important! Sends logs to stdout for HA
        handler.setLevel(level)

        formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(levelname)s:%(name)s: %(message)s",
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            }
        )

        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
