"""
TTS Engine abstraction layer.

Provides:
- Abstract base class for TTS engines
- Common data structures for TTS operations
- Factory function for creating engine instances
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import numpy as np

from mcp_tts.utils.config import Emotion, TTSSettings
from mcp_tts.utils.logging import get_logger

logger = get_logger("tts.engine")


class EmotionSupport(StrEnum):
    """How an engine/voice can honor emotion settings."""

    NATIVE = "native"
    SIMULATED = "simulated"
    UNAVAILABLE = "unavailable"


@dataclass
class EmotionValidation:
    """Result of checking whether an emotion request is usable."""

    allowed: bool
    message: str
    emotion_support: EmotionSupport
    supported_emotions: list[str]


@dataclass
class VoiceInfo:
    """Information about an available voice."""

    id: str
    name: str
    language: str
    gender: str | None = None
    description: str | None = None
    sample_rate: int = 22050
    supports_emotions: bool | None = None
    emotion_support: EmotionSupport | str = EmotionSupport.UNAVAILABLE
    emotion_support_reason: str = "This voice does not expose emotion controls."
    supported_emotions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Normalize legacy and explicit emotion capability fields."""
        if isinstance(self.emotion_support, str):
            self.emotion_support = EmotionSupport(self.emotion_support)

        has_legacy_support = (
            self.supports_emotions is not None
            and self.emotion_support == EmotionSupport.UNAVAILABLE
        )
        if has_legacy_support:
            if self.supports_emotions:
                self.emotion_support = EmotionSupport.SIMULATED
                if (
                    self.emotion_support_reason
                    == "This voice does not expose emotion controls."
                ):
                    self.emotion_support_reason = "Uses simulated emotion via prosody controls."

        if self.emotion_support == EmotionSupport.UNAVAILABLE:
            self.supported_emotions = []

    @property
    def emotions_available(self) -> bool:
        """Return True when non-neutral emotion choices are meaningful."""
        return self.emotion_support in (EmotionSupport.NATIVE, EmotionSupport.SIMULATED)

    def to_dict(self) -> dict:
        """Convert to dictionary for MCP responses."""
        return {
            "id": self.id,
            "name": self.name,
            "language": self.language,
            "gender": self.gender,
            "description": self.description,
            "sample_rate": self.sample_rate,
            "supports_emotions": self.emotions_available,
            "emotion_support": self.emotion_support.value,
            "emotion_support_reason": self.emotion_support_reason,
            "supported_emotions": self.supported_emotions,
        }


def validate_emotion_available(voice: VoiceInfo, emotion: Emotion) -> EmotionValidation:
    """Validate an emotion request against voice capability metadata."""
    supported_emotions = voice.supported_emotions.copy()

    if emotion == Emotion.NEUTRAL:
        return EmotionValidation(
            allowed=True,
            message="Neutral emotion is always available.",
            emotion_support=voice.emotion_support,
            supported_emotions=supported_emotions,
        )

    if not voice.emotions_available:
        return EmotionValidation(
            allowed=False,
            message=(
                f"Emotion '{emotion.value}' is unavailable for voice '{voice.id}'. "
                f"{voice.emotion_support_reason}"
            ),
            emotion_support=voice.emotion_support,
            supported_emotions=supported_emotions,
        )

    if supported_emotions and emotion.value not in supported_emotions:
        return EmotionValidation(
            allowed=False,
            message=(
                f"Emotion '{emotion.value}' is not supported for voice '{voice.id}'. "
                f"Available: {', '.join(supported_emotions)}"
            ),
            emotion_support=voice.emotion_support,
            supported_emotions=supported_emotions,
        )

    return EmotionValidation(
        allowed=True,
        message=(
            f"Emotion '{emotion.value}' is {voice.emotion_support.value} "
            f"for voice '{voice.id}'."
        ),
        emotion_support=voice.emotion_support,
        supported_emotions=supported_emotions,
    )


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
    saved_path: Path | None = None

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


class TTSEngineType(StrEnum):
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

    def __init__(self, models_dir: Path | None = None):
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
        settings: TTSSettings | None = None,
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
    async def get_voice(self, voice_id: str) -> VoiceInfo | None:
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
    models_dir: Path | None = None,
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


def resolve_engine_type(value: str | None, default: TTSEngineType) -> TTSEngineType:
    """Resolve engine type from string input."""
    if not value:
        return default

    value = value.strip().lower()
    for engine_type in TTSEngineType:
        if engine_type.value == value:
            return engine_type

    return default
