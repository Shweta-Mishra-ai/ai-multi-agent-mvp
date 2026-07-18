import logging
import os

_configured = False


def get_logger(name):
    global _configured
    if not _configured:
        root = logging.getLogger("agentos")
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        ))
        root.addHandler(handler)
        root.setLevel(os.getenv("AGENTOS_LOG_LEVEL", "WARNING").upper())
        root.propagate = False
        _configured = True
    return logging.getLogger(name)
