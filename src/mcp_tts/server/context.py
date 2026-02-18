"""
Server context — replaces global mutable state with a singleton.

Holds engine manager, audio player, and config.  Config is loaded
once at initialization; use ``reload_config()`` to pick up external
changes.
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from mcp_tts.tts.engine import TTSEngineType, resolve_engine_type
from mcp_tts.tts.manager import EngineManager
from mcp_tts.tts.audio import AudioPlayer
from mcp_tts.utils.config import Config
from mcp_tts.utils.logging import get_logger

logger = get_logger("server.context")


class ServerContext:
    """Singleton context that owns all server-wide state."""

    _instance: Optional["ServerContext"] = None

    def __new__(cls) -> "ServerContext":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def ensure_initialized(self, config: Optional[Config] = None) -> None:
        """Initialize engine manager, audio player, and config (idempotent)."""
        if self._initialized:
            return

        self.config = config or Config.load()
        self.config.ensure_directories()

        logger.info("Initializing MCP TTS Server...")
        logger.debug(f"Config loaded: {self.config.model_dump()}")

        # Create engine manager (lazy — doesn't load an engine yet)
        self.engine_manager = EngineManager(models_dir=self.config.models_directory)
        engine_type = resolve_engine_type(
            os.getenv("MCP_TTS_ENGINE"), TTSEngineType.EDGE
        )
        self.engine_manager.set_default_engine(engine_type)

        # Create audio player
        self.audio_player = AudioPlayer(device=self.config.audio.output_device)

        self._initialized = True
        logger.info("MCP TTS Server ready (engine will load on first use)")

        # Fire-and-forget background preload so first call is fast
        asyncio.create_task(self._preload_default_engine(engine_type))

    async def _preload_default_engine(self, engine_type: TTSEngineType) -> None:
        """Background preload — failures are silently logged."""
        try:
            await self.engine_manager.preload(engine_type)
            logger.info(f"Background preload complete: {engine_type.value}")
        except Exception as exc:
            logger.debug(f"Background preload skipped: {exc}")

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    def reload_config(self) -> Config:
        """Reload config from disk and return it."""
        self.config = Config.load()
        logger.info("Config reloaded from disk")
        return self.config

    @property
    def is_ready(self) -> bool:
        return self._initialized


# Module-level convenience accessor
def get_context() -> ServerContext:
    """Return the singleton ``ServerContext``."""
    return ServerContext()
