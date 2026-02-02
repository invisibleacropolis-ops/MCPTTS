"""
TTS Engine abstraction layer.

Provides:
- Abstract base class for TTS engines
- Common data structures for TTS operations
- Factory function for creating engine instances
"""

import io
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import numpy as np

from mcp_tts.utils.logging import get_logger
from mcp_tts.utils.config import Emotion, TTSSettings

logger = get_logger("tts.engine")


@dataclass
class VoiceInfo:
    """Information about an available voice."""

    id: str
    name: str
    language: str
    gender: Optional[str] = None
    description: Optional[str] = None
    sample_rate: int = 22050
    supports_emotions: bool = False
    supported_emotions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for MCP responses."""
        return {
            "id": self.id,
            "name": self.name,
            "language": self.language,
            "gender": self.gender,
            "description": self.description,
            "sample_rate": self.sample_rate,
            "supports_emotions": self.supports_emotions,
            "supported_emotions": self.supported_emotions,
        }


@dataclass
class TTSResult:
    """Result of a TTS synthesis operation."""

    audio_data: np.ndarray
    sample_rate: int
    duration_seconds: float
    voice_id: str
    text: str
    settings_used: TTSSettings

    # Optional file path if saved
    saved_path: Optional[Path] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for MCP responses (excluding audio data)."""
        return {
            "duration_seconds": self.duration_seconds,
            "voice_id": self.voice_id,
            "text_length": len(self.text),
            "sample_rate": self.sample_rate,
            "saved_path": str(self.saved_path) if self.saved_path else None,
            "settings": {
                "speed": self.settings_used.speed,
                "pitch": self.settings_used.pitch,
                "emotion": self.settings_used.emotion.value,
                "emotion_intensity": self.settings_used.emotion_intensity,
            },
        }


class TTSEngineType(str, Enum):
    """Available TTS engine types."""

    EDGE = "edge"      # Primary - Microsoft Edge neural TTS (cloud)
    PIPER = "piper"    # Local neural TTS (requires piper-phonemize)
    SYSTEM = "system"  # Fallback to pyttsx3 (Windows SAPI)


class TTSEngine(ABC):
    """
    Abstract base class for TTS engines.

    All TTS engine implementations must inherit from this class
    and implement the abstract methods.
    """

    def __init__(self, models_dir: Optional[Path] = None):
        """
        Initialize the TTS engine.

        Args:
            models_dir: Directory for storing voice models
        """
        self.models_dir = models_dir or Path.home() / ".mcp-tts" / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._current_settings = TTSSettings()
        self._initialized = False
        logger.debug(f"TTS engine initialized with models_dir: {self.models_dir}")

    @property
    @abstractmethod
    def engine_type(self) -> TTSEngineType:
        """Return the engine type identifier."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return human-readable engine name."""
        pass

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the engine (load models, etc.).

        This may be a long-running operation.
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean up resources."""
        pass

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        settings: Optional[TTSSettings] = None,
        use_direct_playback: bool = False,
    ) -> TTSResult:
        """
        Synthesize speech from text.

        Args:
            text: Text to convert to speech
            settings: TTS settings (uses current if None)

        Returns:
            TTSResult with audio data and metadata
        """
        pass

    @abstractmethod
    async def list_voices(self) -> list[VoiceInfo]:
        """
        Get list of available voices.

        Returns:
            List of VoiceInfo objects
        """
        pass

    @abstractmethod
    async def get_voice(self, voice_id: str) -> Optional[VoiceInfo]:
        """
        Get info for a specific voice.

        Args:
            voice_id: Voice identifier

        Returns:
            VoiceInfo if found, None otherwise
        """
        pass

    def get_current_settings(self) -> TTSSettings:
        """Get the current TTS settings."""
        return self._current_settings.model_copy()

    def update_settings(self, **kwargs) -> TTSSettings:
        """
        Update current settings with provided values.

        Args:
            **kwargs: Setting values to update

        Returns:
            Updated TTSSettings
        """
        logger.debug(f"Updating TTS settings: {kwargs}")
        data = self._current_settings.model_dump()
        data.update(kwargs)
        self._current_settings = TTSSettings.model_validate(data)
        logger.info(f"TTS settings updated: {self._current_settings}")
        return self._current_settings

    def set_voice(self, voice_id: str) -> None:
        """Set the default voice."""
        logger.info(f"Setting voice to: {voice_id}")
        self._current_settings.voice = voice_id

    def set_emotion(self, emotion: Emotion, intensity: float = 0.5) -> None:
        """Set the emotional expression."""
        logger.info(f"Setting emotion to: {emotion.value} (intensity: {intensity})")
        self._current_settings.emotion = emotion
        self._current_settings.emotion_intensity = intensity

    @property
    def is_initialized(self) -> bool:
        """Check if the engine is initialized and ready."""
        return self._initialized


def create_engine(
    engine_type: TTSEngineType = TTSEngineType.PIPER,
    models_dir: Optional[Path] = None,
) -> TTSEngine:
    """
    Factory function to create a TTS engine instance.

    Args:
        engine_type: Type of engine to create
        models_dir: Optional models directory override

    Returns:
        TTSEngine instance

    Raises:
        ValueError: If engine type is not supported
    """
    logger.info(f"Creating TTS engine: {engine_type.value}")

    if engine_type == TTSEngineType.EDGE:
        from mcp_tts.tts.edge import EdgeTTSEngine

        return EdgeTTSEngine(models_dir)
    elif engine_type == TTSEngineType.PIPER:
        from mcp_tts.tts.piper import PiperTTSEngine

        return PiperTTSEngine(models_dir)
    elif engine_type == TTSEngineType.SYSTEM:
        from mcp_tts.tts.fallback import SystemTTSEngine

        return SystemTTSEngine(models_dir)
    else:
        raise ValueError(f"Unsupported engine type: {engine_type}")


def resolve_engine_type(value: Optional[str], default: TTSEngineType) -> TTSEngineType:
    """Resolve engine type from string input."""
    if not value:
        return default

    value = value.strip().lower()
    for engine_type in TTSEngineType:
        if engine_type.value == value:
            return engine_type

    return default
