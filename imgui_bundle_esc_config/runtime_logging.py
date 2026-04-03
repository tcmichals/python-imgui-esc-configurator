"""Runtime logging helpers for the ImGui ESC configurator."""

from __future__ import annotations

from logging.handlers import RotatingFileHandler
import logging
import os
from pathlib import Path
import threading

APP_LOGGER_NAME = "imgui_esc_config"
DEFAULT_LOG_FILENAME = "imgui_esc_config.log"
_DEFAULT_MAX_BYTES = 1_048_576
_DEFAULT_BACKUP_COUNT = 3

_config_lock = threading.Lock()
_configured_log_path: Path | None = None


def get_runtime_log_dir(base_dir: str | os.PathLike[str] | None = None) -> Path:
    if base_dir is not None:
        return Path(base_dir)
    env_override = os.environ.get("ESC_CONFIG_LOG_DIR", "").strip()
    if env_override:
        return Path(env_override)
    return Path.cwd() / "logs"


def get_runtime_log_path(base_dir: str | os.PathLike[str] | None = None) -> Path:
    return get_runtime_log_dir(base_dir) / DEFAULT_LOG_FILENAME


def get_logger(component: str | None = None) -> logging.Logger:
    if component:
        return logging.getLogger(f"{APP_LOGGER_NAME}.{component}")
    return logging.getLogger(APP_LOGGER_NAME)


def configure_runtime_logging(base_dir: str | os.PathLike[str] | None = None) -> Path:
    global _configured_log_path

    log_path = get_runtime_log_path(base_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with _config_lock:
        root_logger = get_logger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.propagate = False

        if _configured_log_path != log_path or not root_logger.handlers:
            for handler in list(root_logger.handlers):
                root_logger.removeHandler(handler)
                handler.close()

            handler = RotatingFileHandler(
                log_path,
                maxBytes=_DEFAULT_MAX_BYTES,
                backupCount=_DEFAULT_BACKUP_COUNT,
                encoding="utf-8",
            )
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(
                logging.Formatter(
                    fmt="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            root_logger.addHandler(handler)
            _configured_log_path = log_path

    return log_path


def flush_runtime_logging() -> None:
    root_logger = get_logger()
    for handler in root_logger.handlers:
        handler.flush()


def log_ui_message(level: str, message: str, source: str = "ui") -> None:
    logger = get_logger(source.lower())
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.log(numeric_level, message)


def log_protocol_trace(channel: str, message: str) -> None:
    get_logger("protocol").debug("[%s] %s", channel, message)
