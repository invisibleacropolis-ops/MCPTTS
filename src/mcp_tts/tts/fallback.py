"""
Fallback TTS Engine using system TTS (pyttsx3).

Used when Piper is not available or fails to initialize.
Provides basic TTS functionality without advanced features.
"""

import threading
import time
from pathlib import Path

import numpy as np

from mcp_tts.tts.engine import EmotionSupport, TTSEngine, TTSEngineType, TTSResult, VoiceInfo
from mcp_tts.utils.config import Emotion, TTSSettings
from mcp_tts.utils.logging import get_logger

logger = get_logger("tts.fallback")

# Thread-local storage for pyttsx3 engine instances
_thread_local = threading.local()


# Emotion-based rate adjustments (since pyttsx3 doesn't support emotions natively)
# These multiply the base rate to simulate emotional delivery
EMOTION_RATE_ADJUSTMENTS = {
    Emotion.NEUTRAL: 1.0,
    Emotion.HAPPY: 1.1,      # Slightly faster, upbeat
    Emotion.SAD: 0.85,       # Slower, more drawn out
    Emotion.ANGRY: 1.15,     # Faster, more intense
    Emotion.EXCITED: 1.25,   # Much faster, energetic
    Emotion.CALM: 0.9,       # Slower, relaxed
    Emotion.FEARFUL: 1.1,    # Slightly faster, nervous
    Emotion.SURPRISED: 1.15, # Quick, higher energy
}


class SystemTTSEngine(TTSEngine):
    """
    Fallback TTS engine using system speech synthesis.

    Uses pyttsx3 which wraps:
    - SAPI5 on Windows
    - NSSpeechSynthesizer on macOS
    - espeak on Linux
    """

    def __init__(self, models_dir: Path | None = None):
        super().__init__(models_dir)
        self._engine = None
        self._voices: list[VoiceInfo] = []
        self._rate_control_available = False
        logger.debug("SystemTTSEngine created")

    @property
    def engine_type(self) -> TTSEngineType:
        return TTSEngineType.SYSTEM

    @property
    def name(self) -> str:
        return "System TTS"

    async def initialize(self) -> None:
        """Initialize system TTS engine."""
        logger.info("Initializing System TTS engine...")

        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._rate_control_available = self._detect_rate_control(self._engine)
            emotion_support = (
                EmotionSupport.SIMULATED
                if self._rate_control_available
                else EmotionSupport.UNAVAILABLE
            )
            emotion_reason = (
                "System TTS emotion is simulated with speech rate changes."
                if self._rate_control_available
                else "System TTS rate control is unavailable for this driver."
            )
            supported_emotions = (
                [e.value for e in Emotion] if self._rate_control_available else []
            )

            # Get available voices
            voices = self._engine.getProperty("voices")
            self._voices = [
                VoiceInfo(
                    id=v.id,
                    name=v.name,
                    language=(
                        getattr(v, "languages", ["unknown"])[0]
                        if hasattr(v, "languages")
                        else "unknown"
                    ),
                    gender=getattr(v, "gender", None),
                    description=f"System voice: {v.name}",
                    emotion_support=emotion_support,
                    emotion_support_reason=emotion_reason,
                    supported_emotions=supported_emotions,
                )
                for v in voices
            ]

            self._initialized = True
            logger.info(f"System TTS initialized with {len(self._voices)} voices")

        except ImportError:
            logger.error("pyttsx3 not installed - install with: pip install pyttsx3")
            raise RuntimeError("System TTS (pyttsx3) not installed")
        except Exception as e:
            logger.error(f"Failed to initialize System TTS: {e}")
            raise

    async def shutdown(self) -> None:
        """Clean up resources."""
        logger.info("Shutting down System TTS engine...")
        if self._engine:
            self._engine.stop()
            self._engine = None
        # Clean up thread-local engine if present
        if hasattr(_thread_local, "engine") and _thread_local.engine is not None:
            try:
                _thread_local.engine.stop()
            except Exception:
                pass
            _thread_local.engine = None
        self._voices.clear()
        self._rate_control_available = False
        self._initialized = False
        logger.debug("System TTS shutdown complete")

    def _detect_rate_control(self, engine) -> bool:
        """Return True when pyttsx3 exposes usable rate controls."""
        try:
            rate = engine.getProperty("rate")
            engine.setProperty("rate", rate)
            return True
        except Exception as exc:
            logger.warning(f"System TTS rate control unavailable: {exc}")
            return False

    def _get_thread_engine(self):
        """Get or create a pyttsx3 engine for the current thread."""
        if not hasattr(_thread_local, "engine") or _thread_local.engine is None:
            import pyttsx3
            _thread_local.engine = pyttsx3.init()
            logger.debug("Created new pyttsx3 engine for current thread")
        engine = _thread_local.engine
        # Force clear loop state if it was left open
        if hasattr(engine, "_inLoop") and engine._inLoop:
            engine.endLoop()
        return engine

    async def synthesize(
        self,
        text: str,
        settings: TTSSettings | None = None,
        use_direct_playback: bool = True,
    ) -> TTSResult:
        """
        Synthesize speech using system TTS.

        Args:
            text: Text to synthesize
            settings: TTS settings
            use_direct_playback: If True, plays directly (no audio data returned).
                                If False, creates temp file and returns audio data.
        """
        settings = settings or self._current_settings
        start_time = time.perf_counter()

        logger.info(f"Synthesizing with System TTS: '{text[:50]}...'")

        # Use thread-local cached engine for thread-safety without reinit overhead
        engine = self._get_thread_engine()

        # Apply settings
        # Calculate effective rate with emotion adjustment
        emotion_rate_mult = (
            EMOTION_RATE_ADJUSTMENTS.get(settings.emotion, 1.0)
            if self._rate_control_available
            else 1.0
        )
        # Scale emotion effect by intensity (0.0 = no effect, 1.0 = full effect)
        effective_emotion_mult = (
            1.0 + (emotion_rate_mult - 1.0) * settings.emotion_intensity
        )
        effective_rate = int(150 * settings.speed * effective_emotion_mult)

        logger.debug(
            f"TTS Rate: base=150, speed={settings.speed}, "
            f"emotion={settings.emotion.value}, "
            f"intensity={settings.emotion_intensity:.2f} -> effective_rate={effective_rate}"
        )

        engine.setProperty("rate", effective_rate)
        engine.setProperty("volume", settings.volume)

        # Set voice if specified
        if settings.voice:
            for voice in engine.getProperty("voices"):
                if settings.voice in voice.id or settings.voice.lower() in voice.name.lower():
                    engine.setProperty('voice', voice.id)
                    break

        if use_direct_playback:
            # Direct playback mode - speak immediately, no file created
            return await self._synthesize_direct(engine, text, settings, start_time)
        else:
            # File-based mode - create temp file and return audio data
            return await self._synthesize_to_file(engine, text, settings, start_time)

    async def _synthesize_direct(
        self,
        engine,
        text: str,
        settings: TTSSettings,
        start_time: float,
    ) -> TTSResult:
        """Direct playback mode - pyttsx3 speaks immediately through system audio."""
        logger.debug("Using direct playback mode (no file)")

        try:
            engine.say(text)
            try:
                engine.runAndWait()
            except RuntimeError as e:
                if "run loop already started" in str(e):
                    logger.warning("TTS run loop already active, command queued")
                else:
                    raise

            synthesis_time = time.perf_counter() - start_time
            # Estimate duration based on text length and rate
            estimated_duration = len(text) * 0.06 / settings.speed

            logger.info(f"Direct playback complete in {synthesis_time:.3f}s")

            # Return empty audio data for direct mode
            return TTSResult(
                audio_data=np.array([], dtype=np.float32),
                sample_rate=22050,
                duration_seconds=estimated_duration,
                voice_id=settings.voice,
                text=text,
                settings_used=settings,
            )
        except Exception as e:
            logger.error(f"Direct playback failed: {e}")
            raise

    async def _synthesize_to_file(
        self,
        engine,
        text: str,
        settings: TTSSettings,
        start_time: float,
    ) -> TTSResult:
        """File-based mode - save to temp file and return audio data."""
        logger.debug("Using file-based mode (creating WAV)")

        import os
        import tempfile
        import wave

        temp_path = None
        try:
            # Create temp file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_path = f.name

            # Synthesize to file
            logger.debug(f"Saving synthesis to temp file: {temp_path}")
            engine.save_to_file(text, temp_path)
            engine.runAndWait()

            # Read audio data from file
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                with wave.open(temp_path, 'rb') as wav_file:
                    sample_rate = wav_file.getframerate()
                    n_frames = wav_file.getnframes()
                    audio_bytes = wav_file.readframes(n_frames)

                    # Convert to float32 numpy array
                    sample_width = wav_file.getsampwidth()
                    if sample_width == 2:  # 16-bit
                        audio_data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
                        audio_data /= 32768.0
                    elif sample_width == 1:  # 8-bit
                        audio_data = np.frombuffer(audio_bytes, dtype=np.uint8).astype(np.float32)
                        audio_data = (audio_data - 128) / 128.0
                    else:
                        # 32-bit or other
                        audio_data = np.frombuffer(audio_bytes, dtype=np.int32).astype(np.float32)
                        audio_data /= 2147483648.0

                    duration = n_frames / sample_rate
                    logger.info(f"Read {n_frames} frames @ {sample_rate}Hz ({duration:.2f}s)")
            else:
                raise RuntimeError("TTS synthesis produced no audio output")

        except Exception as e:
            logger.error(f"System TTS synthesis failed: {e}")
            # Generate silent audio as last resort
            sample_rate = 22050
            duration = max(0.5, len(text) * 0.05 / settings.speed)
            audio_data = np.zeros(int(sample_rate * duration), dtype=np.float32)

        finally:
            # Clean up temp file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temp file: {e}")

        synthesis_time = time.perf_counter() - start_time
        logger.info(f"System TTS synthesis complete in {synthesis_time:.3f}s")

        return TTSResult(
            audio_data=audio_data,
            sample_rate=sample_rate,
            duration_seconds=duration,
            voice_id=settings.voice,
            text=text,
            settings_used=settings,
        )

    async def list_voices(self) -> list[VoiceInfo]:
        """List available system voices."""
        if not self._initialized:
            await self.initialize()
        return self._voices.copy()

    async def get_voice(self, voice_id: str) -> VoiceInfo | None:
        """Get info for a specific voice."""
        for voice in self._voices:
            if voice.id == voice_id:
                return voice
        return None
