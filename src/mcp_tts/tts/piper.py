"""
Piper TTS Engine implementation.

Piper is a fast, local neural text-to-speech system that:
- Runs entirely on CPU with low latency
- Supports multiple voices and languages
- Uses ONNX runtime for inference
- Provides high-quality, natural-sounding speech
"""

import asyncio
import json
import os
import time
from inspect import signature
from pathlib import Path
from typing import Any
from urllib import request

import numpy as np

from mcp_tts.tts.engine import EmotionSupport, TTSEngine, TTSEngineType, TTSResult, VoiceInfo
from mcp_tts.utils.config import Emotion, TTSSettings
from mcp_tts.utils.gpu import GPUStatus, get_gpu_manager
from mcp_tts.utils.logging import get_logger

logger = get_logger("tts.piper")

PIPER_VOICE_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
PIPER_DEFAULT_VOICES = [
    "en_US-libritts_r-medium",
    "en_US-lessac-high",
]


# Mapping of emotions to SSML prosody adjustments
# Piper doesn't have native emotion support, so we simulate via prosody
EMOTION_PROSODY = {
    Emotion.NEUTRAL: {"rate": 1.0, "pitch": 0},
    Emotion.HAPPY: {"rate": 1.1, "pitch": 5},
    Emotion.SAD: {"rate": 0.9, "pitch": -5},
    Emotion.ANGRY: {"rate": 1.15, "pitch": 3},
    Emotion.EXCITED: {"rate": 1.2, "pitch": 8},
    Emotion.CALM: {"rate": 0.85, "pitch": -2},
    Emotion.FEARFUL: {"rate": 1.05, "pitch": 2},
    Emotion.SURPRISED: {"rate": 1.1, "pitch": 10},
}


class PiperTTSEngine(TTSEngine):
    """
    Piper TTS engine implementation.

    Uses piper-tts library for local neural TTS synthesis.
    Simulates emotional expression through prosody adjustments.
    """

    def __init__(self, models_dir: Path | None = None):
        super().__init__(models_dir)
        self._piper = None
        self._voice_cache: dict[str, VoiceInfo] = {}
        self._voice_runtime_cache: dict[tuple[str, tuple[str, ...]], Any] = {}
        self._default_voice = "en_US-amy-medium"
        self._active_device = "cpu"
        self._active_providers: tuple[str, ...] = ("CPUExecutionProvider",)
        self._min_vram_gb = 0.5
        self._piper_available = False
        logger.debug("PiperTTSEngine created")

    @property
    def engine_type(self) -> TTSEngineType:
        return TTSEngineType.PIPER

    @property
    def name(self) -> str:
        return "Piper TTS"

    @property
    def active_device(self) -> str:
        return self._active_device

    @property
    def active_providers(self) -> tuple[str, ...]:
        return self._active_providers

    async def initialize(self) -> None:
        """Initialize Piper TTS engine."""
        logger.info("Initializing Piper TTS engine...")

        try:
            # Check for piper binary availability
            logger.debug("Checking for piper.exe installation...")

            piper_exe = Path(os.path.expanduser("~/.mcp-tts/piper/piper.exe"))
            if piper_exe.exists():
                logger.info(f"Found Piper binary at {piper_exe}")
                self._piper_available = True
            else:
                # Check PATH
                import shutil
                if shutil.which("piper"):
                    logger.info("Found Piper binary in PATH")
                    self._piper_available = True
                else:
                    logger.warning(f"Piper binary not found at {piper_exe} or in PATH")
                    self._piper_available = False

            self._initialized = True

            gpu_manager = get_gpu_manager()
            gpu_info = gpu_manager.gpu_info
            if gpu_info:
                logger.info(
                    f"GPU status: {gpu_info.name} | {gpu_info.available_vram_gb:.2f}GB free"
                )

            await self._download_default_voices()

            if self._piper_available:
                logger.info("Piper TTS engine initialized successfully (binary mode)")
            else:
                logger.warning(
                    "Piper TTS initialized but binary not found - synthesis will fallback"
                )

        except Exception as e:
            logger.error(f"Failed to initialize Piper TTS: {e}")
            self._piper_available = False
            self._initialized = True
            # Don't raise, allow fallback

    async def shutdown(self) -> None:
        """Clean up Piper resources."""
        logger.info("Shutting down Piper TTS engine...")
        self._piper = None
        self._voice_cache.clear()
        self._voice_runtime_cache.clear()
        self._initialized = False
        logger.debug("Piper TTS shutdown complete")

    def _apply_emotion_prosody(
        self,
        text: str,
        emotion: Emotion,
        intensity: float,
        base_speed: float,
        base_pitch: float,
    ) -> tuple[float, float]:
        """
        Calculate adjusted speed and pitch based on emotion.

        Args:
            text: Original text (for potential SSML wrapping)
            emotion: Emotional expression
            intensity: Emotion intensity (0-1)
            base_speed: User's speed setting
            base_pitch: User's pitch setting

        Returns:
            Tuple of (adjusted_speed, adjusted_pitch)
        """
        prosody = EMOTION_PROSODY.get(emotion, EMOTION_PROSODY[Emotion.NEUTRAL])

        # Scale prosody adjustments by intensity
        rate_adjustment = (prosody["rate"] - 1.0) * intensity
        pitch_adjustment = prosody["pitch"] * intensity

        # Apply to base settings
        final_speed = base_speed * (1.0 + rate_adjustment)
        final_pitch = base_pitch + (pitch_adjustment / 20.0)  # Normalize pitch adjustment

        # Clamp to valid ranges
        final_speed = max(0.5, min(2.0, final_speed))
        final_pitch = max(-1.0, min(1.0, final_pitch))

        logger.debug(
            f"Emotion prosody: {emotion.value} @ {intensity:.2f} -> "
            f"speed={final_speed:.2f}, pitch={final_pitch:.2f}"
        )

        return final_speed, final_pitch

    async def synthesize(
        self,
        text: str,
        settings: TTSSettings | None = None,
        use_direct_playback: bool = False,
    ) -> TTSResult:
        """
        Synthesize speech from text using Piper.

        Args:
            text: Text to synthesize
            settings: TTS settings (uses current if None)

        Returns:
            TTSResult with audio data
        """
        if not self._initialized:
            await self.initialize()

        settings = settings or self._current_settings
        start_time = time.perf_counter()

        logger.info(f"Synthesizing text ({len(text)} chars): '{text[:50]}...'")
        logger.debug(
            f"Settings: voice={settings.voice}, speed={settings.speed}, "
            f"pitch={settings.pitch}, emotion={settings.emotion.value}"
        )

        # Apply emotion-based prosody adjustments
        adjusted_speed, adjusted_pitch = self._apply_emotion_prosody(
            text,
            settings.emotion,
            settings.emotion_intensity,
            settings.speed,
            settings.pitch,
        )

        try:
            # Attempt to use piper for synthesis
            audio_data, sample_rate = await self._synthesize_with_piper(
                text, settings.voice, adjusted_speed, adjusted_pitch
            )
        except Exception as e:
            logger.warning(f"Piper synthesis failed: {e}, using system TTS fallback")
            # Use system TTS fallback for actual speech
            audio_data, sample_rate = await self._synthesize_with_system_tts(
                text, settings, adjusted_speed
            )

        duration = len(audio_data) / sample_rate if sample_rate > 0 else 0.0
        synthesis_time = time.perf_counter() - start_time

        rtf = synthesis_time / duration if duration > 0 else 0.0
        logger.info(
            f"Synthesis complete: {duration:.2f}s audio in {synthesis_time:.3f}s "
            f"(RTF: {rtf:.2f}x)"
        )

        return TTSResult(
            audio_data=audio_data,
            sample_rate=sample_rate,
            duration_seconds=duration,
            voice_id=settings.voice,
            text=text,
            settings_used=settings,
        )

    async def _synthesize_with_piper(
        self,
        text: str,
        voice: str,
        speed: float,
        pitch: float,
    ) -> tuple[np.ndarray, int]:
        """
        Synthesize using the external piper.exe binary.
        """
        # Path to piper binary (extracted in ~/.mcp-tts/piper/piper.exe)
        # Assuming it's in the same base dir as models for now, or finding it relative to home
        piper_exe = Path(os.path.expanduser("~/.mcp-tts/piper/piper.exe"))

        if not piper_exe.exists():
             # Fallback check for system path or relative path
             piper_exe = Path("piper.exe")

        logger.debug(f"Attempting Piper binary synthesis with voice: {voice} using {piper_exe}")

        # Get voice model path
        model_path = self.models_dir / f"{voice}.onnx"
        config_path = self.models_dir / f"{voice}.onnx.json"

        if not model_path.exists() or not config_path.exists():
            logger.warning(f"Voice model not found: {model_path}")
            await self._download_voice(voice)

        if not model_path.exists() or not config_path.exists():
            raise FileNotFoundError(f"Voice model not found: {voice}")

        # Construct command
        # piper.exe --model <model> --config <config> --output_raw
        cmd = [
            str(piper_exe),
            "--model",
            str(model_path),
            "--config",
            str(config_path),
            "--output_raw",
            "--length_scale",
            str(1.0 / speed),
            # Pitch support depends on the binary/model; synthesis uses speed only here.
            # For now we focus on basic synthesis
        ]

        logger.debug(f"Running command: {' '.join(cmd)}")

        try:
            # Run subprocess
            # We pipe text to stdin and capture stdout
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout_data, stderr_data = await process.communicate(input=text.encode("utf-8"))

            if process.returncode != 0:
                error_msg = stderr_data.decode("utf-8", errors="replace")
                logger.error(f"Piper binary failed with code {process.returncode}: {error_msg}")
                raise RuntimeError(f"Piper binary failed: {error_msg}")

            # Piper --output_raw outputs raw PCM samples, usually 16-bit mono
            # We need to know the sample rate from the voice config
            with open(config_path, encoding="utf-8") as f:
                 config = json.load(f)
                 # Config structure varies, usually top level or under 'audio'
                 sample_rate = config.get("audio", {}).get("sample_rate", 22050)

            # Convert raw bytes to numpy array
            # Assuming 16-bit signed integer (S16LE)
            logger.debug(f"Piper stdout bytes: {len(stdout_data)}")
            audio_data = np.frombuffer(stdout_data, dtype=np.int16).astype(np.float32)

            if len(audio_data) > 0:
                max_amp = np.max(np.abs(audio_data))
                logger.debug(f"Raw int16 max amplitude: {max_amp}")

            audio_data /= 32768.0  # Normalize to [-1, 1]

            if len(audio_data) > 0:
                logger.debug(f"Normalized float32 max amplitude: {np.max(np.abs(audio_data))}")

            logger.debug(f"Synthesized {len(audio_data)} samples at {sample_rate}Hz")

            return audio_data, sample_rate

        except Exception as e:
            logger.error(f"Piper binary synthesis error: {e}")
            raise

    def _load_voice(self, piper_voice_cls, model_path: Path, config_path: Path) -> Any:
        providers, device = self._get_onnx_providers()
        cache_key = (model_path.stem, tuple(providers))

        if cache_key in self._voice_runtime_cache:
            self._active_device = device
            self._active_providers = tuple(providers)
            return self._voice_runtime_cache[cache_key]

        load_kwargs = {}
        load_signature = signature(piper_voice_cls.load)
        if "providers" in load_signature.parameters:
            load_kwargs["providers"] = providers
        if "use_cuda" in load_signature.parameters:
            load_kwargs["use_cuda"] = "CUDAExecutionProvider" in providers
        if "device" in load_signature.parameters:
            load_kwargs["device"] = device

        voice_obj = piper_voice_cls.load(str(model_path), str(config_path), **load_kwargs)
        self._voice_runtime_cache[cache_key] = voice_obj
        self._active_device = device
        self._active_providers = tuple(providers)
        return voice_obj

    def _get_onnx_providers(self) -> tuple[list[str], str]:
        gpu_manager = get_gpu_manager()

        if gpu_manager.is_gpu_available and gpu_manager.check_vram_available(self._min_vram_gb):
            providers = gpu_manager.get_onnx_providers()
            device = gpu_manager.get_device()
            return providers, device

        if gpu_manager.gpu_info and gpu_manager.gpu_info.status == GPUStatus.VRAM_LOW:
            logger.warning("GPU VRAM low - falling back to CPU for Piper")
        elif gpu_manager.gpu_info and gpu_manager.gpu_info.status == GPUStatus.CUDA_NOT_AVAILABLE:
            logger.info("CUDA not available - using CPU for Piper")
        return ["CPUExecutionProvider"], "cpu"

    async def _download_default_voices(self) -> None:
        for voice in PIPER_DEFAULT_VOICES:
            if not (self.models_dir / f"{voice}.onnx").exists():
                await self._download_voice(voice)

    async def _download_voice(self, voice: str) -> None:
        if not voice:
            return

        model_path = self.models_dir / f"{voice}.onnx"
        config_path = self.models_dir / f"{voice}.onnx.json"

        if model_path.exists() and config_path.exists():
            return

        # Parse voice ID to construct URL
        # Format: language_COUNTRY-name-quality
        parts = voice.split("-")
        if len(parts) < 3:
            logger.warning(f"Invalid voice ID format: {voice}")
            return

        lang_code = parts[0]  # e.g., en_US
        name = parts[1]       # e.g., amy
        quality = parts[2]    # e.g., medium

        # Approximate language family (e.g., en from en_US)
        lang_family = lang_code.split("_")[0]

        # Construct URL
        # Pattern: family/code/name/quality/filename
        # e.g., en/en_US/amy/medium/en_US-amy-medium.onnx

        rel_path = f"{lang_family}/{lang_code}/{name}/{quality}/{voice}"
        model_url = f"{PIPER_VOICE_BASE_URL}/{rel_path}.onnx"
        config_url = f"{PIPER_VOICE_BASE_URL}/{rel_path}.onnx.json"

        logger.info(f"Downloading Piper voice: {voice}")
        logger.debug(f"URL: {model_url}")

        def download_file(url: str, dest: Path) -> None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            request.urlretrieve(url, dest)

        try:
            await asyncio.to_thread(download_file, model_url, model_path)
            await asyncio.to_thread(download_file, config_url, config_path)
            logger.info(f"Downloaded Piper voice: {voice}")
        except Exception as e:
            logger.warning(f"Failed to download Piper voice '{voice}': {e}")
            # cleanup partial downloads
            if model_path.exists():
                model_path.unlink()
            if config_path.exists():
                config_path.unlink()

    async def _synthesize_with_system_tts(
        self,
        text: str,
        settings: TTSSettings,
        adjusted_speed: float,
    ) -> tuple[np.ndarray, int]:
        """
        Fallback synthesis using system TTS (pyttsx3).

        Used when Piper is not available or fails.
        """
        logger.debug("Using system TTS fallback for synthesis")

        # Import and use SystemTTSEngine
        from mcp_tts.tts.fallback import SystemTTSEngine

        # Create a temporary fallback engine if we don't have one cached
        if not hasattr(self, "_fallback_engine"):
            self._fallback_engine = SystemTTSEngine(self.models_dir)
            await self._fallback_engine.initialize()

        # Adjust settings for fallback
        fallback_settings = settings.model_copy()
        fallback_settings.speed = adjusted_speed

        # Synthesize
        result = await self._fallback_engine.synthesize(text, fallback_settings)

        return result.audio_data, result.sample_rate

    async def list_voices(self) -> list[VoiceInfo]:
        """List available Piper voices."""
        logger.debug("Listing available voices")

        voices = []

        # Check for downloaded models
        if self.models_dir.exists():
            for model_file in self.models_dir.glob("*.onnx"):
                voice_id = model_file.stem
                if voice_id not in self._voice_cache:
                    # Parse voice ID to extract info
                    # Format: language_COUNTRY-name-quality
                    parts = voice_id.split("-")
                    if len(parts) >= 2:
                        language = parts[0]
                        name = parts[1] if len(parts) > 1 else voice_id
                        quality = parts[2] if len(parts) > 2 else "medium"

                        self._voice_cache[voice_id] = VoiceInfo(
                            id=voice_id,
                            name=f"{name.title()} ({quality})",
                            language=language,
                            description=f"Piper voice: {voice_id}",
                            sample_rate=22050,
                            emotion_support=EmotionSupport.SIMULATED,
                            emotion_support_reason=(
                                "Piper emotion is simulated with speed and pitch changes."
                            ),
                            supported_emotions=[e.value for e in Emotion],
                        )

        # Add default voice if no models found
        if not self._voice_cache:
            self._voice_cache[self._default_voice] = VoiceInfo(
                id=self._default_voice,
                name="Amy (Medium)",
                language="en_US",
                description="Default Piper voice (download required)",
                sample_rate=22050,
                emotion_support=EmotionSupport.SIMULATED,
                emotion_support_reason="Piper emotion is simulated with speed and pitch changes.",
                supported_emotions=[e.value for e in Emotion],
            )

        voices = list(self._voice_cache.values())
        logger.info(f"Found {len(voices)} voices")
        return voices

    async def get_voice(self, voice_id: str) -> VoiceInfo | None:
        """Get info for a specific voice."""
        if voice_id in self._voice_cache:
            return self._voice_cache[voice_id]

        # Try to refresh voice list
        await self.list_voices()
        return self._voice_cache.get(voice_id)
