# utils/logger.py
import logging as _logging
import sys
from pathlib import Path


def setup_logging(name: str = "adDominum") -> _logging.Logger:
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    logger = _logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(_logging.INFO)
    formatter = _logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = _logging.FileHandler(log_dir / "automation.log", encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    ch = _logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger
