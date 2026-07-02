"""
Audio playback and file saving utilities.

Provides:
- Real-time audio playback via sounddevice
- WAV file saving
- Audio format conversion
"""

import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from mcp_tts.utils.config import AudioSettings
from mcp_tts.utils.gpu import get_gpu_manager
from mcp_tts.utils.logging import get_logger

logger = get_logger("tts.audio")


class AudioPlayer:
    """
    Audio playback manager using sounddevice.

    Supports:
    - Real-time playback
    - Device selection
    - Volume control
    """

    def __init__(self, device: str | None = None):
        """
        Initialize audio player.

        Args:
            device: Output device name (None for system default)
        """
        self._device = device
        self._sd = None
        logger.debug(f"AudioPlayer created with device: {device or 'default'}")

    def _ensure_sounddevice(self):
        """Lazy import sounddevice."""
        if self._sd is None:
            try:
                import sounddevice as sd

                self._sd = sd
                logger.debug(f"sounddevice loaded, default device: {sd.default.device}")
            except ImportError:
                logger.error("sounddevice not installed")
                raise RuntimeError(
                    "sounddevice not installed - install with: pip install sounddevice"
                )

    def play(
        self,
        audio_data: np.ndarray,
        sample_rate: int,
        blocking: bool = True,
        volume: float = 1.0,
    ) -> None:
        """
        Play audio data.

        Args:
            audio_data: Audio samples as numpy array
            sample_rate: Sample rate in Hz
            blocking: If True, wait for playback to complete
            volume: Volume multiplier (0.0 to 1.0)
        """
        self._ensure_sounddevice()

        logger.debug(
            f"Playing audio: {len(audio_data)} samples @ {sample_rate}Hz, "
            f"volume={volume:.2f}, blocking={blocking}"
        )

        # Apply volume
        adjusted_audio = audio_data * volume

        try:
            self._sd.play(adjusted_audio, sample_rate, device=self._device)
            if blocking:
                self._sd.wait()
                logger.debug("Playback complete")
        except Exception as e:
            logger.error(f"Audio playback error: {e}")
            raise

    def stop(self) -> None:
        """Stop any current playback."""
        if self._sd:
            self._sd.stop()
            logger.debug("Playback stopped")

    def list_devices(self) -> list[dict]:
        """List available audio output devices."""
        self._ensure_sounddevice()

        devices = []
        for i, device in enumerate(self._sd.query_devices()):
            if device["max_output_channels"] > 0:
                devices.append(
                    {
                        "id": i,
                        "name": device["name"],
                        "channels": device["max_output_channels"],
                        "default_samplerate": device["default_samplerate"],
                    }
                )

        logger.debug(f"Found {len(devices)} output devices")
        return devices


def apply_audio_effects(
    audio_data: np.ndarray,
    sample_rate: int,
    settings: AudioSettings | None,
) -> np.ndarray:
    """Apply optional audio effects (normalization, compression, reverb)."""
    if audio_data.size == 0:
        return audio_data

    if settings is None:
        return audio_data

    processed = audio_data.astype(np.float32)

    if settings.normalize_audio:
        max_val = np.max(np.abs(processed))
        if max_val > 0:
            processed = processed / max_val

    if not settings.effects_enabled:
        return processed

    if settings.compression_strength > 0:
        strength = max(0.1, min(1.0, settings.compression_strength))
        processed = np.tanh(processed * (1.0 + 4.0 * strength))

    if settings.reverb_wet > 0:
        processed = _apply_reverb(processed, sample_rate, settings.reverb_wet, settings)

    return processed


def _apply_reverb(
    audio_data: np.ndarray,
    sample_rate: int,
    wet: float,
    settings: AudioSettings,
) -> np.ndarray:
    wet = max(0.0, min(1.0, wet))
    decay_seconds = max(0.1, min(1.0, settings.reverb_decay))
    decay_length = int(sample_rate * decay_seconds)

    if decay_length <= 0:
        return audio_data

    impulse = np.exp(-np.linspace(0.0, 4.0, decay_length)).astype(np.float32)
    impulse[0] = 1.0

    try:
        import torch
        import torch.nn.functional as functional

        tensor = torch.from_numpy(audio_data).float().unsqueeze(0).unsqueeze(0)
        kernel = torch.from_numpy(impulse).float().unsqueeze(0).unsqueeze(0)

        if settings.effects_use_gpu and get_gpu_manager().is_gpu_available:
            device = get_gpu_manager().get_device()
            tensor = tensor.to(device)
            kernel = kernel.to(device)

        padded = functional.pad(tensor, (decay_length - 1, 0))
        convolved = functional.conv1d(padded, kernel)
        reverb = convolved.squeeze().cpu().numpy()

        if reverb.shape[0] > audio_data.shape[0]:
            reverb = reverb[: audio_data.shape[0]]

    except Exception:
        # Fallback to numpy convolution
        reverb = np.convolve(audio_data, impulse, mode="full")[: audio_data.shape[0]]

    return (1.0 - wet) * audio_data + wet * reverb


def save_audio(
    audio_data: np.ndarray,
    sample_rate: int,
    output_path: Path,
    normalize: bool = True,
) -> Path:
    """
    Save audio data to a WAV file.

    Args:
        audio_data: Audio samples as numpy array (float32, -1 to 1)
        sample_rate: Sample rate in Hz
        output_path: Output file path
        normalize: If True, normalize audio before saving

    Returns:
        Path to saved file
    """
    logger.debug(f"Saving audio to: {output_path}")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Normalize if requested
    if normalize:
        max_val = np.max(np.abs(audio_data))
        if max_val > 0:
            audio_data = audio_data / max_val

    # Convert to int16
    audio_int16 = (audio_data * 32767).astype(np.int16)

    # Write WAV file
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_int16.tobytes())

    logger.info(f"Audio saved to: {output_path}")
    return output_path


def generate_output_filename(
    text: str,
    output_dir: Path,
    extension: str = ".wav",
) -> Path:
    """
    Generate a unique output filename based on text and timestamp.

    Args:
        text: Input text (used to generate slug)
        output_dir: Output directory
        extension: File extension

    Returns:
        Path to output file
    """
    # Create a slug from first 20 chars of text
    slug = "".join(c if c.isalnum() else "_" for c in text[:20]).strip("_").lower()
    if not slug:
        slug = "output"

    # Add timestamp for uniqueness
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{slug}_{timestamp}{extension}"

    return output_dir / filename
