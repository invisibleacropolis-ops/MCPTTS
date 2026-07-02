"""
Custom logging configuration with verbose debugging and GUI streaming support.

Provides:
- Detailed log formatting with timestamps, source location, and context
- QueueHandler for streaming logs to GUI
- Color-coded console output
- Log level filtering
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from logging.handlers import QueueHandler, RotatingFileHandler
from multiprocessing import Queue
from pathlib import Path

# Custom log format with verbose debugging info
VERBOSE_FORMAT = (
    "%(asctime)s.%(msecs)03d | %(levelname)-8s | "
    "%(name)s:%(funcName)s:%(lineno)d | %(message)s"
)
SIMPLE_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Color codes for console output
COLORS = {
    "DEBUG": "\033[36m",     # Cyan
    "INFO": "\033[32m",      # Green
    "WARNING": "\033[33m",   # Yellow
    "ERROR": "\033[31m",     # Red
    "CRITICAL": "\033[35m",  # Magenta
    "RESET": "\033[0m",
}


class ColoredFormatter(logging.Formatter):
    """Formatter that adds color codes to log output."""

    def format(self, record: logging.LogRecord) -> str:
        # Add color to levelname
        color = COLORS.get(record.levelname, COLORS["RESET"])
        reset = COLORS["RESET"]
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


class GUILogHandler(QueueHandler):
    """
    Custom QueueHandler that sends log records to a multiprocessing Queue
    for consumption by the GUI log viewer.

    Each log record is serialized as a dict for safe cross-process transfer.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the queue as a serializable dict."""
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "name": record.name,
                "function": record.funcName,
                "line": record.lineno,
                "message": self.format(record),
                "raw_message": record.getMessage(),
            }
            self.queue.put_nowait(log_entry)
        except Exception:
            self.handleError(record)


class LoggerManager:
    """
    Centralized logger management for the MCP TTS application.

    Supports:
    - Console output with colors
    - File logging with rotation
    - GUI streaming via multiprocessing Queue
    - Dynamic log level changes
    """

    _instance: LoggerManager | None = None
    _initialized: bool = False

    def __new__(cls) -> LoggerManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if LoggerManager._initialized:
            return

        self.root_logger = logging.getLogger("mcp_tts")
        self.gui_queue: Queue | None = None
        self.gui_handler: GUILogHandler | None = None
        self.console_handler: logging.StreamHandler | None = None
        self.file_handler: RotatingFileHandler | None = None

        LoggerManager._initialized = True

    def setup(
        self,
        level: int = logging.DEBUG,
        log_file: Path | None = None,
        gui_queue: Queue | None = None,
        verbose: bool = True,
    ) -> None:
        """
        Configure the logging system.

        Args:
            level: Minimum log level to capture
            log_file: Optional path to log file
            gui_queue: Optional multiprocessing Queue for GUI streaming
            verbose: If True, use detailed format; otherwise simple format
        """
        self.root_logger.setLevel(level)

        # Clear existing handlers
        self.root_logger.handlers.clear()

        log_format = VERBOSE_FORMAT if verbose else SIMPLE_FORMAT

        # Console handler with colors (use stderr to avoid MCP stdio conflicts)
        self.console_handler = logging.StreamHandler(sys.stderr)
        self.console_handler.setLevel(level)
        self.console_handler.setFormatter(ColoredFormatter(log_format, DATE_FORMAT))
        self.root_logger.addHandler(self.console_handler)

        # File handler with rotation (if path provided)
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            self.file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8",
            )
            self.file_handler.setLevel(level)
            self.file_handler.setFormatter(logging.Formatter(log_format, DATE_FORMAT))
            self.root_logger.addHandler(self.file_handler)

        # GUI queue handler (if queue provided)
        if gui_queue:
            self.gui_queue = gui_queue
            self.gui_handler = GUILogHandler(gui_queue)
            self.gui_handler.setLevel(level)
            self.gui_handler.setFormatter(logging.Formatter(log_format, DATE_FORMAT))
            self.root_logger.addHandler(self.gui_handler)

        self.root_logger.debug(
            f"Logging initialized: level={logging.getLevelName(level)}, "
            f"verbose={verbose}, file={log_file}, gui_queue={gui_queue is not None}"
        )

    def set_level(self, level: int) -> None:
        """Dynamically change the log level."""
        self.root_logger.setLevel(level)
        for handler in self.root_logger.handlers:
            handler.setLevel(level)
        self.root_logger.info(f"Log level changed to: {logging.getLevelName(level)}")

    def get_logger(self, name: str) -> logging.Logger:
        """Get a child logger with the given name."""
        if name.startswith("mcp_tts."):
            return logging.getLogger(name)
        return logging.getLogger(f"mcp_tts.{name}")


# Module-level convenience functions
_manager: LoggerManager | None = None


def setup_logging(
    level: int = logging.DEBUG,
    log_file: Path | None = None,
    gui_queue: Queue | None = None,
    verbose: bool = True,
) -> LoggerManager:
    """
    Initialize the logging system.

    Args:
        level: Minimum log level (default: DEBUG for verbose output)
        log_file: Optional path to write logs to file
        gui_queue: Optional Queue for GUI log streaming
        verbose: Use detailed format with source location info

    Returns:
        LoggerManager instance
    """
    global _manager
    _manager = LoggerManager()
    _manager.setup(level, log_file, gui_queue, verbose)
    return _manager


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for the given module/component name.

    Args:
        name: Logger name (will be prefixed with 'mcp_tts.' if not already)

    Returns:
        Configured Logger instance
    """
    global _manager
    if _manager is None:
        _manager = LoggerManager()
        _manager.setup()  # Use defaults
    return _manager.get_logger(name)


def set_log_level(level: int) -> None:
    """Change the global log level at runtime."""
    global _manager
    if _manager:
        _manager.set_level(level)
