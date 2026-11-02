"""Centralized loguru-based logging for the IFQM Case Study Generator.

Every module imports `get_logger` from here instead of using print(). Logs go to
both the console and a date-stamped rotating file under LOG_DIR. A small
`stage_timer` context manager standardizes the "[STAGE entry/exit + timing]"
pattern the build protocol expects.

Usage:
    from src.logger import get_logger, stage_timer

    log = get_logger(__name__)
    with stage_timer("ingestion"):
        ...
"""
from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv
from loguru import logger

# Load .env so LOG_DIR (and everything else) is available at import time.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")

_LOG_DIR = Path(os.getenv("LOG_DIR", str(_PROJECT_ROOT / "logs")))
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / f"pipeline_{date.today().isoformat()}.log"

# loguru uses a single global logger; configure handlers exactly once even if
# this module is imported many times (Streamlit re-imports on every rerun).
_CONFIGURED = False


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    logger.remove()  # drop loguru's default stderr handler
    level = os.getenv("LOG_LEVEL", "INFO").upper()

    def format_stderr(record):
        module_name = record["extra"].get("module", record["name"].split(".")[-1] or "ifqm")
        record["extra"]["module"] = module_name
        return (
            "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
            "<cyan>{extra[module]}</cyan> - <level>{message}</level>\n"
        )

    def format_file(record):
        module_name = record["extra"].get("module", record["name"].split(".")[-1] or "ifqm")
        record["extra"]["module"] = module_name
        return (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{extra[module]} | {message}\n"
        )

    logger.add(
        sys.stderr,
        level=level,
        colorize=True,
        format=format_stderr,
    )
    logger.add(
        _LOG_FILE,
        level="DEBUG",
        rotation="20 MB",
        retention="14 days",
        encoding="utf-8",
        enqueue=True,  # process-safe; tolerant of Streamlit's threads
        backtrace=True,
        diagnose=False,
        format=format_file,
    )
    _CONFIGURED = True


def get_logger(name: str = "ifqm"):
    """Return a logger bound to a short module name."""
    _configure()
    short = name.split(".")[-1] if name else "ifqm"
    return logger.bind(module=short)


@contextmanager
def stage_timer(stage_name: str) -> Iterator[None]:
    """Log entry/exit of a pipeline stage with elapsed time, in minutes."""
    log = get_logger(stage_name)
    start = time.perf_counter()
    log.info(f"[STAGE ENTRY] {stage_name}")
    try:
        yield
    except Exception:
        elapsed = (time.perf_counter() - start) / 60.0
        log.exception(f"[STAGE FAIL] {stage_name} after {elapsed:.2f} min")
        raise
    else:
        elapsed = (time.perf_counter() - start) / 60.0
        log.info(f"[STAGE EXIT] {stage_name} in {elapsed:.2f} min")
