"""
Server lifecycle — entry point for the ``mcp-tts-server`` console script.
"""

import logging

from mcp_tts.utils.logging import get_logger, setup_logging

logger = get_logger("server.lifecycle")


def run_server() -> None:
    """Run the MCP server (entry point for ``mcp-tts-server`` command)."""
    from mcp_tts.server import mcp  # lazy import to avoid circular init

    setup_logging(level=logging.DEBUG, verbose=True)
    logger.info("Starting MCP TTS Server...")
    mcp.run()


if __name__ == "__main__":
    run_server()
