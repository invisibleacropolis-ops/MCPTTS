"""
Shared test fixtures for MCP TTS test suite.

Eliminates per-file sys.path hacks — the editable install handles imports.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import numpy as np

from mcp_tts.utils.config import Config, TTSSettings, AudioSettings


@pytest.fixture
def tmp_config(tmp_path: Path) -> Config:
    """Return a Config instance backed by a temporary file."""
    config_path = tmp_path / "config.json"
    config = Config()
    config._config_path = config_path
    config._models_directory = tmp_path / "models"
    return config


@pytest.fixture
def sample_audio() -> np.ndarray:
    """Generate a 0.5-second 440 Hz sine wave at 22050 Hz."""
    sr = 22050
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False, dtype=np.float32)
    return np.sin(2.0 * np.pi * 440.0 * t)


@pytest.fixture
def mock_engine():
    """Create a mock TTS engine."""
    engine = MagicMock()
    engine.name = "mock"
    engine.engine_type = MagicMock()
    engine.engine_type.value = "mock"
    engine.active_device = "cpu"
    engine.get_current_settings.return_value = TTSSettings()
    engine.list_voices = AsyncMock(return_value=[])
    engine.synthesize = AsyncMock()
    return engine
