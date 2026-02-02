"""
MCP TTS Server - Main Entry Point.

Provides CLI interface for running the server in various modes:
- GUI mode (default): Full GUI with settings and log viewer
- Server mode: Run MCP server directly (for MCP clients)
- Headless mode: Server without GUI for automation
"""

import argparse
import logging
import os
import socket
import subprocess
import time
import sys
from typing import Optional
from pathlib import Path

from mcp_tts import __version__
from mcp_tts.utils.config import Config
from mcp_tts.utils.logging import setup_logging, get_logger


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="mcp-tts",
        description="MCP Text-to-Speech Server - Convert LLM text output to speech",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mcp-tts                    # Run with GUI (default)
  mcp-tts --server           # Run server only (for MCP clients)
  mcp-tts --headless         # Run server without GUI
  mcp-tts --config path.json # Use custom config file
        """,
    )

    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--gui",
        action="store_true",
        default=True,
        help="Run with GUI (default)",
    )
    mode_group.add_argument(
        "--server",
        "-s",
        action="store_true",
        help="Run MCP server only (no GUI)",
    )
    mode_group.add_argument(
        "--headless",
        action="store_true",
        help="Run server without GUI (for automation)",
    )

    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        help="Path to configuration file",
    )

    parser.add_argument(
        "--log-level",
        "-l",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="DEBUG",
        help="Logging level (default: DEBUG)",
    )

    parser.add_argument(
        "--log-file",
        type=Path,
        help="Path to log file",
    )

    parser.add_argument(
        "--fish-repo",
        type=Path,
        help="Path to Fish Speech repo for auto-launch",
    )

    parser.add_argument(
        "--fish-port",
        type=int,
        default=8080,
        help="Fish Speech API port (default: 8080)",
    )

    parser.add_argument(
        "--transport",
        "-t",
        choices=["stdio", "http"],
        default="stdio",
        help="MCP transport type (default: stdio)",
    )

    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8000,
        help="Port for HTTP transport (default: 8000)",
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Set up logging
    log_level = getattr(logging, args.log_level)
    setup_logging(
        level=log_level,
        log_file=args.log_file,
        verbose=True,
    )

    logger = get_logger("main")
    logger.info(f"MCP TTS Server v{__version__} starting...")
    logger.debug(f"Arguments: {args}")

    # Load configuration
    config = Config.load(args.config)
    config.ensure_directories()

    # Override config with CLI args
    if args.transport:
        config.server.transport = args.transport
    if args.port:
        config.server.port = args.port

    _maybe_start_fish_server(args.fish_repo, args.fish_port)

    try:
        if args.server or args.headless:
            # Run server directly
            logger.info("Running in server mode...")

            from mcp_tts.server import run_server

            run_server()

        else:
            # Run with GUI (default)
            logger.info("Running with GUI...")

            from mcp_tts.gui.app import run_gui

            run_gui()

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _maybe_start_fish_server(repo_path: Optional[Path], port: int) -> None:
    if _is_port_open("127.0.0.1", port):
        return

    env_repo = os.getenv("FISH_SPEECH_REPO")
    repo = repo_path or (Path(env_repo) if env_repo else None)
    if repo is None:
        return

    if not repo.exists():
        logger = get_logger("main")
        logger.warning(f"Fish Speech repo not found: {repo}")
        return

    logger = get_logger("main")
    logger.info("Starting Fish Speech API server...")

    cmd = [
        sys.executable,
        "-m",
        "tools.api_server",
        "--listen",
        f"127.0.0.1:{port}",
    ]

    try:
        subprocess.Popen(cmd, cwd=str(repo))
        for _ in range(10):
            if _is_port_open("127.0.0.1", port):
                logger.info("Fish Speech API server is ready")
                return
            time.sleep(0.5)
        logger.warning("Fish Speech API server did not respond in time")
    except Exception as exc:
        logger.warning(f"Failed to launch Fish Speech server: {exc}")


if __name__ == "__main__":
    main()
