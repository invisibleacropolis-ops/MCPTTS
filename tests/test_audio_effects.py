"""
Tests for audio effects: normalization, compression, reverb, edge cases.
"""

import numpy as np
import pytest

from mcp_tts.tts.audio import apply_audio_effects, save_audio, generate_output_filename
from mcp_tts.utils.config import AudioSettings


class TestNormalization:
    """Audio normalization rescales peak to 1.0."""

    def test_normalization_rescales(self, sample_audio: np.ndarray):
        settings = AudioSettings(normalize_audio=True, effects_enabled=False)
        result = apply_audio_effects(sample_audio * 0.5, 22050, settings)
        assert np.max(np.abs(result)) == pytest.approx(1.0, abs=0.01)

    def test_normalization_no_op_when_disabled(self, sample_audio: np.ndarray):
        settings = AudioSettings(normalize_audio=False, effects_enabled=False)
        result = apply_audio_effects(sample_audio * 0.5, 22050, settings)
        assert np.max(np.abs(result)) == pytest.approx(0.5, abs=0.01)

    def test_normalization_handles_silence(self):
        silence = np.zeros(1000, dtype=np.float32)
        settings = AudioSettings(normalize_audio=True, effects_enabled=False)
        result = apply_audio_effects(silence, 22050, settings)
        assert np.max(np.abs(result)) == 0.0


class TestCompression:
    """Compression via tanh keeps audio in [-1, 1]."""

    def test_compression_limits_peaks(self, sample_audio: np.ndarray):
        loud = sample_audio * 10.0
        settings = AudioSettings(
            normalize_audio=False,
            effects_enabled=True,
            compression_strength=1.0,
            reverb_wet=0.0,
        )
        result = apply_audio_effects(loud, 22050, settings)
        assert np.max(np.abs(result)) <= 1.01  # tanh ≤ 1

    def test_no_compression_when_zero(self, sample_audio: np.ndarray):
        settings = AudioSettings(
            normalize_audio=False,
            effects_enabled=True,
            compression_strength=0.0,
            reverb_wet=0.0,
        )
        result = apply_audio_effects(sample_audio, 22050, settings)
        np.testing.assert_array_almost_equal(result, sample_audio, decimal=4)


class TestReverb:
    """Reverb adds tail energy without exploding."""

    def test_reverb_changes_audio(self, sample_audio: np.ndarray):
        settings = AudioSettings(
            normalize_audio=False,
            effects_enabled=True,
            compression_strength=0.0,
            reverb_wet=0.5,
            reverb_decay=0.3,
        )
        result = apply_audio_effects(sample_audio, 22050, settings)
        assert result.shape == sample_audio.shape
        # Reverb mixes dry+wet so result should differ
        assert not np.allclose(result, sample_audio)

    def test_reverb_zero_wet_is_passthrough(self, sample_audio: np.ndarray):
        settings = AudioSettings(
            normalize_audio=False,
            effects_enabled=True,
            compression_strength=0.0,
            reverb_wet=0.0,
        )
        result = apply_audio_effects(sample_audio, 22050, settings)
        np.testing.assert_array_almost_equal(result, sample_audio, decimal=4)


class TestEdgeCases:
    """Empty input, None settings."""

    def test_empty_array(self):
        result = apply_audio_effects(np.array([], dtype=np.float32), 22050, AudioSettings())
        assert result.size == 0

    def test_none_settings(self, sample_audio: np.ndarray):
        result = apply_audio_effects(sample_audio, 22050, None)
        np.testing.assert_array_equal(result, sample_audio)

    def test_effects_disabled(self, sample_audio: np.ndarray):
        settings = AudioSettings(
            normalize_audio=False,
            effects_enabled=False,
            compression_strength=1.0,
            reverb_wet=1.0,
        )
        result = apply_audio_effects(sample_audio, 22050, settings)
        np.testing.assert_array_almost_equal(result, sample_audio, decimal=4)


class TestSaveAudio:
    """save_audio writes a readable WAV."""

    def test_save_creates_file(self, sample_audio: np.ndarray, tmp_path):
        out = tmp_path / "test.wav"
        result = save_audio(sample_audio, 22050, out)
        assert result.exists()
        assert result.stat().st_size > 0

    def test_save_creates_dirs(self, sample_audio: np.ndarray, tmp_path):
        out = tmp_path / "sub" / "dir" / "test.wav"
        save_audio(sample_audio, 22050, out)
        assert out.exists()


class TestOutputFilename:
    """generate_output_filename creates unique names."""

    def test_slug_from_text(self, tmp_path):
        path = generate_output_filename("Hello World!", tmp_path)
        assert "hello_world" in path.name.lower()

    def test_empty_text_uses_output(self, tmp_path):
        path = generate_output_filename("", tmp_path)
        assert "output" in path.name.lower()
