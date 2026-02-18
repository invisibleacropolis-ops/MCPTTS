"""
Pytest unit tests for MCP TTS engines.

Uses mocks to avoid requiring actual TTS binaries, cloud APIs, or audio hardware.
"""

import asyncio
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# _split_text helper (server.py)
# ---------------------------------------------------------------------------


class TestSplitText:
    """Test the _split_text chunking helper."""

    def setup_method(self):
        from mcp_tts.server.tools import _split_text
        self._split_text = _split_text

    def test_short_text_single_chunk(self):
        result = self._split_text("Hello world", 100)
        assert result == ["Hello world"]

    def test_exact_limit(self):
        text = "a" * 50
        result = self._split_text(text, 50)
        assert result == [text]

    def test_splits_on_space(self):
        text = "word1 word2 word3 word4"
        result = self._split_text(text, 12)
        assert len(result) > 1
        # All chunks should be <= max_chars
        for chunk in result:
            assert len(chunk) <= 12

    def test_preserves_all_words(self):
        text = "one two three four five"
        result = self._split_text(text, 10)
        recombined = " ".join(result)
        assert recombined == text

    def test_empty_string(self):
        result = self._split_text("", 100)
        assert result == [""]


# ---------------------------------------------------------------------------
# EngineManager fallback priority
# ---------------------------------------------------------------------------


class TestEngineManagerPriority:
    """Test engine manager priority/fallback logic."""

    def setup_method(self):
        pass  # editable install provides imports

    def test_build_priority_default(self):
        from mcp_tts.tts.manager import EngineManager
        from mcp_tts.tts.engine import TTSEngineType

        mgr = EngineManager()
        priority = mgr._build_priority(None, None)
        # Default priority should have EDGE first, SYSTEM always included
        assert priority[0] == TTSEngineType.EDGE
        assert TTSEngineType.SYSTEM in priority

    def test_build_priority_preferred(self):
        from mcp_tts.tts.manager import EngineManager
        from mcp_tts.tts.engine import TTSEngineType

        mgr = EngineManager()
        priority = mgr._build_priority(TTSEngineType.SYSTEM, None)
        assert priority[0] == TTSEngineType.SYSTEM

    def test_build_priority_fast_task(self):
        from mcp_tts.tts.manager import EngineManager
        from mcp_tts.tts.engine import TTSEngineType

        mgr = EngineManager()
        priority = mgr._build_priority(None, "fast")
        # fast task should include PIPER and SYSTEM
        assert TTSEngineType.PIPER in priority
        assert TTSEngineType.SYSTEM in priority

    def test_no_duplicates_in_priority(self):
        from mcp_tts.tts.manager import EngineManager
        from mcp_tts.tts.engine import TTSEngineType

        mgr = EngineManager()
        priority = mgr._build_priority(TTSEngineType.EDGE, "quality")
        assert len(priority) == len(set(priority))


# ---------------------------------------------------------------------------
# PiperTTSEngine
# ---------------------------------------------------------------------------


class TestPiperEngine:
    """Test Piper TTS engine with mocked subprocess."""

    def setup_method(self):
        pass  # editable install provides imports

    @pytest.mark.asyncio
    async def test_initialize_no_binary(self, tmp_path):
        """Engine should initialize even when piper binary is missing."""
        from mcp_tts.tts.piper import PiperTTSEngine

        engine = PiperTTSEngine(models_dir=tmp_path)

        original_exists = Path.exists

        def fake_exists(self_path):
            # Pretend piper.exe doesn't exist
            if "piper.exe" in str(self_path) or "piper" == self_path.name:
                return False
            return original_exists(self_path)

        with patch.object(Path, "exists", fake_exists), \
             patch("shutil.which", return_value=None):
            await engine.initialize()

        assert engine.is_initialized
        assert not engine._piper_available

    def test_engine_type(self, tmp_path):
        from mcp_tts.tts.piper import PiperTTSEngine
        from mcp_tts.tts.engine import TTSEngineType

        engine = PiperTTSEngine(models_dir=tmp_path)
        assert engine.engine_type == TTSEngineType.PIPER

    def test_name(self, tmp_path):
        from mcp_tts.tts.piper import PiperTTSEngine

        engine = PiperTTSEngine(models_dir=tmp_path)
        assert engine.name == "Piper TTS"

    def test_emotion_prosody(self, tmp_path):
        from mcp_tts.tts.piper import PiperTTSEngine
        from mcp_tts.utils.config import Emotion

        engine = PiperTTSEngine(models_dir=tmp_path)
        speed, pitch = engine._apply_emotion_prosody(
            "test", Emotion.HAPPY, 1.0, 1.0, 0.0
        )
        # Happy emotion should increase speed
        assert speed > 1.0


# ---------------------------------------------------------------------------
# EdgeTTSEngine
# ---------------------------------------------------------------------------


class TestEdgeEngine:
    """Test Edge TTS engine with mocked edge_tts."""

    def setup_method(self):
        pass  # editable install provides imports

    def test_engine_type(self, tmp_path):
        from mcp_tts.tts.edge import EdgeTTSEngine
        from mcp_tts.tts.engine import TTSEngineType

        engine = EdgeTTSEngine(models_dir=tmp_path)
        assert engine.engine_type == TTSEngineType.EDGE

    def test_active_device_is_cloud(self, tmp_path):
        from mcp_tts.tts.edge import EdgeTTSEngine

        engine = EdgeTTSEngine(models_dir=tmp_path)
        assert engine.active_device == "cloud"

    def test_resolve_voice_edge_format(self, tmp_path):
        from mcp_tts.tts.edge import EdgeTTSEngine

        engine = EdgeTTSEngine(models_dir=tmp_path)
        # Already an Edge voice name → pass through
        assert engine._resolve_voice("en-US-JennyNeural") == "en-US-JennyNeural"

    def test_resolve_voice_piper_format(self, tmp_path):
        from mcp_tts.tts.edge import EdgeTTSEngine

        engine = EdgeTTSEngine(models_dir=tmp_path)
        # Piper-style voice → map to Edge default
        result = engine._resolve_voice("en_US-amy-medium")
        assert "Neural" in result

    @pytest.mark.asyncio
    async def test_decode_mp3_no_decoders_returns_silence(self, tmp_path):
        """When all decoders fail, should return silence instead of crashing."""
        from mcp_tts.tts.edge import EdgeTTSEngine

        engine = EdgeTTSEngine(models_dir=tmp_path)

        with patch.dict("sys.modules", {
            "miniaudio": None,
            "pydub": None,
            "soundfile": None,
        }):
            # All imports will fail → should get silence
            audio, sr = await engine._decode_mp3(b"fake mp3 data")
            assert sr == 22050
            assert len(audio) > 0
            assert np.max(np.abs(audio)) == 0.0  # silence


# ---------------------------------------------------------------------------
# SystemTTSEngine
# ---------------------------------------------------------------------------


class TestSystemEngine:
    """Test System (fallback) TTS engine."""

    def setup_method(self):
        pass  # editable install provides imports

    def test_engine_type(self, tmp_path):
        from mcp_tts.tts.fallback import SystemTTSEngine
        from mcp_tts.tts.engine import TTSEngineType

        engine = SystemTTSEngine(models_dir=tmp_path)
        assert engine.engine_type == TTSEngineType.SYSTEM

    def test_name(self, tmp_path):
        from mcp_tts.tts.fallback import SystemTTSEngine

        engine = SystemTTSEngine(models_dir=tmp_path)
        assert engine.name == "System TTS"


# ---------------------------------------------------------------------------
# Engine factory
# ---------------------------------------------------------------------------


class TestEngineFactory:
    """Test the create_engine factory function."""

    def setup_method(self):
        pass  # editable install provides imports

    def test_create_piper(self, tmp_path):
        from mcp_tts.tts.engine import create_engine, TTSEngineType
        engine = create_engine(TTSEngineType.PIPER, tmp_path)
        assert engine.engine_type == TTSEngineType.PIPER

    def test_create_edge(self, tmp_path):
        from mcp_tts.tts.engine import create_engine, TTSEngineType
        engine = create_engine(TTSEngineType.EDGE, tmp_path)
        assert engine.engine_type == TTSEngineType.EDGE

    def test_create_system(self, tmp_path):
        from mcp_tts.tts.engine import create_engine, TTSEngineType
        engine = create_engine(TTSEngineType.SYSTEM, tmp_path)
        assert engine.engine_type == TTSEngineType.SYSTEM

    def test_resolve_engine_type(self):
        from mcp_tts.tts.engine import resolve_engine_type, TTSEngineType
        assert resolve_engine_type("edge", TTSEngineType.PIPER) == TTSEngineType.EDGE
        assert resolve_engine_type("piper", TTSEngineType.EDGE) == TTSEngineType.PIPER
        assert resolve_engine_type(None, TTSEngineType.EDGE) == TTSEngineType.EDGE
        assert resolve_engine_type("unknown", TTSEngineType.SYSTEM) == TTSEngineType.SYSTEM
