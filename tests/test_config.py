"""
Tests for Config model: load, save, roundtrip, defaults, and presets.
"""

import json
from pathlib import Path

import pytest

from mcp_tts.utils.config import (
    Config,
    TTSSettings,
    AudioSettings,
    Emotion,
    VOICE_PRESETS,
)


class TestConfigDefaults:
    """Config loads with sensible defaults."""

    def test_default_engine(self):
        s = TTSSettings()
        assert s.engine in ("auto", "edge", "piper", "system")

    def test_default_speed(self):
        assert TTSSettings().speed == 1.0

    def test_default_pitch(self):
        assert TTSSettings().pitch == 0.0

    def test_default_emotion(self):
        assert TTSSettings().emotion == Emotion.NEUTRAL

    def test_default_emotion_intensity(self):
        assert TTSSettings().emotion_intensity == 0.5

    def test_config_has_tts_section(self):
        config = Config()
        assert isinstance(config.tts, TTSSettings)

    def test_config_has_audio_section(self):
        config = Config()
        assert isinstance(config.audio, AudioSettings)


class TestConfigPersistence:
    """Config save/load roundtrip."""

    def test_save_creates_file(self, tmp_path: Path):
        config = Config()
        out = tmp_path / "cfg.json"
        config.save(out)
        assert out.exists()

    def test_roundtrip_preserves_tts(self, tmp_path: Path):
        original = Config()
        original.tts.speed = 1.7
        original.tts.pitch = -0.3
        original.tts.emotion = Emotion.HAPPY
        cfg_path = tmp_path / "cfg.json"
        original.save(cfg_path)

        loaded = Config.load(cfg_path)
        assert loaded.tts.speed == pytest.approx(1.7, abs=0.01)
        assert loaded.tts.pitch == pytest.approx(-0.3, abs=0.01)
        assert loaded.tts.emotion == Emotion.HAPPY

    def test_roundtrip_preserves_audio(self, tmp_path: Path):
        original = Config()
        original.audio.sample_rate = 44100
        cfg_path = tmp_path / "cfg.json"
        original.save(cfg_path)

        loaded = Config.load(cfg_path)
        assert loaded.audio.sample_rate == 44100

    def test_load_missing_file_returns_defaults(self, tmp_path: Path):
        config = Config.load(tmp_path / "nonexistent.json")
        assert config.tts.speed == 1.0

    def test_load_corrupt_file_returns_defaults(self, tmp_path: Path):
        cfg_path = tmp_path / "bad.json"
        cfg_path.write_text("{{{bad json", encoding="utf-8")
        config = Config.load(cfg_path)
        assert config.tts.speed == 1.0


class TestVoicePresets:
    """Preset dictionaries are valid."""

    def test_presets_exist(self):
        assert len(VOICE_PRESETS) > 0

    def test_presets_are_tts_settings(self):
        for name, preset in VOICE_PRESETS.items():
            assert isinstance(preset, TTSSettings), f"Preset '{name}' is not TTSSettings"

    def test_preset_speed_range(self):
        for name, preset in VOICE_PRESETS.items():
            assert 0.5 <= preset.speed <= 2.0, f"Preset '{name}' speed out of range"
