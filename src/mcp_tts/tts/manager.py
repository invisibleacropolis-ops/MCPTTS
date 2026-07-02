"""
Engine manager for coordinating multiple TTS engines.

Provides:
- Engine selection and fallback priority
- Lazy loading and VRAM-aware unloading
- Task-based routing
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from mcp_tts.tts.engine import TTSEngine, TTSEngineType, create_engine, resolve_engine_type
from mcp_tts.utils.gpu import get_gpu_manager
from mcp_tts.utils.logging import get_logger

logger = get_logger("tts.manager")


@dataclass
class EngineRecord:
    engine: TTSEngine
    last_used: float


class EngineManager:
    """
    Manage multiple TTS engines with fallback and VRAM constraints.
    """

    def __init__(self, models_dir=None):
        self._engines: dict[TTSEngineType, EngineRecord] = {}
        self._models_dir = models_dir
        self._default_engine = resolve_engine_type(os.getenv("MCP_TTS_ENGINE"), TTSEngineType.EDGE)
        self._required_vram_gb = {
            TTSEngineType.EDGE: 0.0,   # Cloud-based
            TTSEngineType.PIPER: 0.5,
            TTSEngineType.SYSTEM: 0.0,
        }
        self._priority = [
            TTSEngineType.EDGE,   # Primary - high quality neural TTS
            TTSEngineType.PIPER,  # Fallback - local neural TTS
            TTSEngineType.SYSTEM, # Last resort - Windows SAPI
        ]
        self._current_engine: TTSEngineType | None = None

    @property
    def current_engine(self) -> TTSEngineType | None:
        return self._current_engine

    def set_default_engine(self, engine_type: TTSEngineType) -> None:
        self._default_engine = engine_type

    async def get_engine(
        self,
        preferred: str | None = None,
        task: str | None = None,
    ) -> TTSEngine:
        preferred_type = None
        if preferred and preferred.lower() != "auto":
            preferred_type = resolve_engine_type(preferred, self._default_engine)

        priority = self._build_priority(preferred_type, task)

        for engine_type in priority:
            engine = await self._ensure_engine(engine_type)
            if engine:
                self._current_engine = engine_type
                return engine

        raise RuntimeError("No available TTS engines")

    async def preload(self, engine_type: TTSEngineType) -> None:
        await self._ensure_engine(engine_type)

    def list_loaded(self) -> list[str]:
        return [engine_type.value for engine_type in self._engines]

    async def shutdown_all(self) -> None:
        for engine_type in list(self._engines.keys()):
            await self._unload_engine(engine_type)

    def _build_priority(
        self, preferred: TTSEngineType | None, task: str | None
    ) -> list[TTSEngineType]:
        # Task-based priority (simplified - only piper and system now)
        if task == "fast":
            base = [TTSEngineType.PIPER, TTSEngineType.SYSTEM]
        elif task == "quality":
            base = [TTSEngineType.PIPER, TTSEngineType.SYSTEM]
        else:
            base = list(self._priority)

        if preferred:
            if preferred in base:
                base.remove(preferred)
            base.insert(0, preferred)

        if TTSEngineType.SYSTEM not in base:
            base.append(TTSEngineType.SYSTEM)

        seen = set()
        ordered = []
        for item in base:
            if item not in seen:
                ordered.append(item)
                seen.add(item)
        return ordered

    async def _ensure_engine(self, engine_type: TTSEngineType) -> TTSEngine | None:
        record = self._engines.get(engine_type)
        if record:
            record.last_used = time.monotonic()
            return record.engine

        await self._maybe_free_vram(engine_type)

        try:
            engine = create_engine(engine_type, self._models_dir)
            await engine.initialize()
            self._engines[engine_type] = EngineRecord(engine=engine, last_used=time.monotonic())
            logger.info(f"Loaded engine: {engine_type.value}")
            return engine
        except Exception as e:
            logger.warning(f"Failed to load engine {engine_type.value}: {e}")
            return None

    async def _unload_engine(self, engine_type: TTSEngineType) -> None:
        record = self._engines.pop(engine_type, None)
        if record:
            try:
                await record.engine.shutdown()
            finally:
                get_gpu_manager().clear_vram_cache()
                logger.info(f"Unloaded engine: {engine_type.value}")

    async def _maybe_free_vram(self, target_engine: TTSEngineType) -> None:
        required = self._required_vram_gb.get(target_engine, 0.0)
        if required <= 0:
            return

        gpu_manager = get_gpu_manager()
        if not gpu_manager.is_gpu_available:
            return

        if gpu_manager.check_vram_available(required):
            return

        # Unload least recently used GPU engine
        lru_engine = None
        lru_time = float("inf")
        for engine_type, record in self._engines.items():
            if self._required_vram_gb.get(engine_type, 0.0) <= 0:
                continue
            if record.last_used < lru_time:
                lru_time = record.last_used
                lru_engine = engine_type

        if lru_engine:
            await self._unload_engine(lru_engine)
