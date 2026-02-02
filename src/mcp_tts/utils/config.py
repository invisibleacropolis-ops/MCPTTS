"""
Configuration management for MCP TTS Server.

Provides:
- Pydantic-based configuration models
- JSON persistence for settings
- Default presets for voice, speed, pitch, emotion
- Runtime configuration updates
"""

import json
import os
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class Emotion(str, Enum):
    """Available emotional expressions for TTS output."""

    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    EXCITED = "excited"
    CALM = "calm"
    FEARFUL = "fearful"
    SURPRISED = "surprised"


class TTSSettings(BaseModel):
    """Text-to-Speech engine settings."""

    voice: str = Field(default="en_US-amy-medium", description="Voice model identifier")
    engine: str = Field(
        default=os.getenv("MCP_TTS_ENGINE", "auto"),
        description="TTS engine identifier (auto, fish, xtts, piper, system)",
    )
    speed: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
        description="Speech rate multiplier (0.5 = half speed, 2.0 = double speed)",
    )
    pitch: float = Field(
        default=0.0, ge=-1.0, le=1.0, description="Pitch adjustment (-1.0 = lower, 1.0 = higher)"
    )
    emotion: Emotion = Field(default=Emotion.NEUTRAL, description="Emotional expression for speech")
    emotion_intensity: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Intensity of emotional expression"
    )
    volume: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Output volume (0.0 = silent, 1.0 = full)"
    )


class ServerSettings(BaseModel):
    """MCP Server configuration."""

    host: str = Field(default="127.0.0.1", description="Server bind address")
    port: int = Field(default=8000, ge=1024, le=65535, description="Server port number")
    transport: str = Field(
        default="stdio", description="Transport type: 'stdio' or 'streamable-http'"
    )
    debug: bool = Field(default=True, description="Enable debug mode with verbose logging")


class AudioSettings(BaseModel):
    """Audio output configuration."""

    output_device: Optional[str] = Field(
        default=None, description="Audio output device name (None = system default)"
    )
    sample_rate: int = Field(default=22050, description="Audio sample rate in Hz")
    auto_play: bool = Field(default=True, description="Automatically play audio after synthesis")
    use_direct_playback: bool = Field(
        default=True,
        description="Use real-time direct playback (no file creation). When False, creates WAV file first.",
    )
    save_to_file: bool = Field(
        default=False,
        description="Save audio to file (only applies when use_direct_playback is False)",
    )
    normalize_audio: bool = Field(
        default=True,
        description="Normalize audio before playback/output",
    )
    effects_enabled: bool = Field(
        default=False,
        description="Enable audio effects pipeline",
    )
    effects_use_gpu: bool = Field(
        default=True,
        description="Use GPU for audio effects when available",
    )
    compression_strength: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Soft compression strength",
    )
    reverb_wet: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Reverb wet mix",
    )
    reverb_decay: float = Field(
        default=0.4,
        ge=0.1,
        le=1.0,
        description="Reverb decay seconds",
    )
    output_directory: Path = Field(
        default=Path.home() / ".mcp-tts" / "output", description="Directory for saved audio files"
    )


class GUISettings(BaseModel):
    """GUI appearance and behavior settings."""

    theme: str = Field(default="dark-blue", description="CustomTkinter theme")
    window_width: int = Field(default=1200, ge=800)
    window_height: int = Field(default=800, ge=600)
    log_max_lines: int = Field(default=1000, description="Maximum lines to keep in log viewer")
    auto_scroll: bool = Field(default=True, description="Auto-scroll log viewer to latest entries")


class Config(BaseModel):
    """
    Root configuration model for MCP TTS Server.

    Combines all settings categories and provides persistence.
    """

    tts: TTSSettings = Field(default_factory=TTSSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    gui: GUISettings = Field(default_factory=GUISettings)

    # Model storage location
    models_directory: Path = Field(default=Path.home() / ".mcp-tts" / "models")

    # Config file location
    _config_path: Optional[Path] = None

    @classmethod
    def get_default_config_path(cls) -> Path:
        """Get the default configuration file path."""
        return Path.home() / ".mcp-tts" / "config.json"

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        """
        Load configuration from file.

        Args:
            path: Path to config file. Uses default if None.

        Returns:
            Config instance (defaults if file doesn't exist)
        """
        config_path = path or cls.get_default_config_path()

        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                config = cls.model_validate(data)
                config._config_path = config_path
                return config
            except Exception as e:
                # Log will be available after setup
                print(f"Warning: Failed to load config from {config_path}: {e}")

        # Return defaults
        config = cls()
        config._config_path = config_path
        return config

    def save(self, path: Optional[Path] = None) -> None:
        """
        Save configuration to file.

        Args:
            path: Path to save to. Uses stored path or default if None.
        """
        save_path = path or self._config_path or self.get_default_config_path()
        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, "w", encoding="utf-8") as f:
            # Convert Path objects to strings for JSON serialization
            data = self.model_dump(mode="json")
            json.dump(data, f, indent=2, default=str)

        self._config_path = save_path

    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.models_directory.mkdir(parents=True, exist_ok=True)
        self.audio.output_directory.mkdir(parents=True, exist_ok=True)


# Voice presets for quick selection
VOICE_PRESETS = {
    "default": TTSSettings(),
    "fast_narrator": TTSSettings(
        speed=1.4,
        pitch=0.1,
        emotion=Emotion.NEUTRAL,
    ),
    "slow_storyteller": TTSSettings(
        speed=0.8,
        pitch=-0.1,
        emotion=Emotion.CALM,
        emotion_intensity=0.7,
    ),
    "excited_announcer": TTSSettings(
        speed=1.2,
        pitch=0.2,
        emotion=Emotion.EXCITED,
        emotion_intensity=0.8,
    ),
    "calm_assistant": TTSSettings(
        speed=0.95,
        pitch=0.0,
        emotion=Emotion.CALM,
        emotion_intensity=0.5,
    ),
}
