"""
Mock-based tests for MCP tool handlers in server/tools.py.

These tests verify tool behavior without starting a real MCP server
or loading real TTS engines.
"""

from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

import numpy as np
import pytest

from mcp_tts.utils.config import Config, TTSSettings, Emotion


def _run(coro):
    """Helper to run an async function synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestSplitText:
    """Verify _split_text chunking logic."""

    def test_short_text(self):
        from mcp_tts.server.tools import _split_text
        assert _split_text("hi", 100) == ["hi"]

    def test_chunking(self):
        from mcp_tts.server.tools import _split_text
        text = "word " * 50
        chunks = _split_text(text.strip(), 20)
        assert all(len(c) <= 20 for c in chunks)
        assert " ".join(chunks) == text.strip()


class TestReloadConfig:
    """reload_config returns a summary dict."""

    def test_reload_returns_tts_and_audio(self):
        from mcp_tts.server.context import ServerContext

        # Reset singleton for isolation
        ServerContext._instance = None

        with patch("mcp_tts.server.context.Config") as MockConfig:
            mock_cfg = Config()
            MockConfig.load.return_value = mock_cfg

            from mcp_tts.server.tools import reload_config

            ctx = ServerContext()
            ctx._initialized = True
            ctx.config = mock_cfg
            ctx.engine_manager = MagicMock()
            ctx.audio_player = MagicMock()

            result = _run(reload_config())
            assert "status" in result
            assert result["status"] == "success"
            assert "tts" in result
            assert "audio" in result

        # Clean up singleton
        ServerContext._instance = None


class TestHealthCheck:
    """health_check returns status."""

    def test_returns_status_ok(self):
        from mcp_tts.server.context import ServerContext

        ServerContext._instance = None

        from mcp_tts.server.tools import health_check

        ctx = ServerContext()
        ctx._initialized = True
        ctx.config = Config()
        ctx.engine_manager = MagicMock()
        ctx.engine_manager.list_loaded.return_value = ["edge"]
        ctx.audio_player = MagicMock()

        result = _run(health_check())
        assert result["status"] == "healthy"
        assert "engines_loaded" in result

        ServerContext._instance = None


class TestConfigureTTS:
    """configure_tts merges partial settings."""

    def test_speed_only(self):
        from mcp_tts.server.context import ServerContext

        ServerContext._instance = None

        from mcp_tts.server.tools import configure_tts

        ctx = ServerContext()
        ctx._initialized = True
        ctx.config = Config()
        ctx.engine_manager = MagicMock()
        ctx.engine_manager.get_engine = AsyncMock(return_value=MagicMock())
        ctx.audio_player = MagicMock()

        result = _run(configure_tts(speed=1.5))
        assert result["status"] == "success"
        assert "speed" in result.get("updated", [])

        ServerContext._instance = None
