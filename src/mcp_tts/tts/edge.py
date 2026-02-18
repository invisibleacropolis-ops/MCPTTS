"""
Edge TTS Engine implementation.

Uses Microsoft's Edge TTS service for high-quality neural synthesis.
This is free to use and requires no API key.

Voices available: https://docs.microsoft.com/en-us/azure/cognitive-services/speech-service/language-support
"""

from __future__ import annotations

import asyncio
import io
import time
from pathlib import Path
from typing import Optional

import numpy as np

from mcp_tts.tts.engine import TTSEngine, TTSEngineType, TTSResult, TTSSettings, Emotion, VoiceInfo
from mcp_tts.utils.logging import get_logger

logger = get_logger("tts.edge")

# Default voice mappings
DEFAULT_VOICES = {
    "en-US": "en-US-JennyNeural",
    "en-GB": "en-GB-SoniaNeural",
    "en-AU": "en-AU-NatashaNeural",
    "default": "en-US-JennyNeural",
}

# Emotion to SSML style mappings
EMOTION_STYLES = {
    Emotion.NEUTRAL: None,
    Emotion.HAPPY: "cheerful",
    Emotion.SAD: "sad",
    Emotion.ANGRY: "angry",
    Emotion.EXCITED: "excited",
    Emotion.CALM: "calm",
    Emotion.FEARFUL: "terrified",
    Emotion.SURPRISED: "surprised",
}


class EdgeTTSEngine(TTSEngine):
    """
    Edge TTS engine using Microsoft's neural TTS service.
    
    Features:
    - High-quality neural voices
    - Multiple languages and voices
    - Emotional expression via SSML styles
    - No API key required (uses Edge browser's TTS endpoint)
    """

    def __init__(self, models_dir: Optional[Path] = None):
        super().__init__(models_dir)
        self._edge_available = False
        self._voices: list[dict] = []
        logger.debug("EdgeTTSEngine created")

    @property
    def engine_type(self) -> TTSEngineType:
        return TTSEngineType.EDGE

    @property
    def name(self) -> str:
        return "Edge TTS"

    @property
    def active_device(self) -> str:
        return "cloud"  # Edge TTS runs on Microsoft's servers

    async def initialize(self) -> None:
        """Initialize Edge TTS engine."""
        logger.info("Initializing Edge TTS engine...")
        
        try:
            import edge_tts
            self._edge_available = True
            
            # Fetch available voices
            voices = await edge_tts.list_voices()
            self._voices = voices
            logger.info(f"Edge TTS initialized with {len(voices)} voices")
            
        except ImportError:
            logger.error("edge-tts not installed - install with: pip install edge-tts")
            self._edge_available = False
        except Exception as e:
            logger.error(f"Failed to initialize Edge TTS: {e}")
            self._edge_available = False

    async def shutdown(self) -> None:
        """Shutdown Edge TTS engine."""
        logger.info("Edge TTS engine shutdown")

    async def synthesize(
        self,
        text: str,
        settings: Optional[TTSSettings] = None,
        use_direct_playback: bool = False,
    ) -> TTSResult:
        """Synthesize speech using Edge TTS."""
        import edge_tts
        import tempfile
        import os
        
        start_time = time.perf_counter()
        settings = settings or TTSSettings()
        
        logger.info(f"Synthesizing text ({len(text)} chars): '{text[:50]}...'")
        logger.debug(f"Settings: voice={settings.voice}, speed={settings.speed}")
        
        if not self._edge_available:
            raise RuntimeError("Edge TTS not available")
        
        # Map voice setting to Edge TTS voice
        voice = self._resolve_voice(settings.voice)
        
        # Calculate rate adjustment
        rate = f"+{int((settings.speed - 1) * 100)}%" if settings.speed >= 1 else f"{int((settings.speed - 1) * 100)}%"
        
        # Create communicate instance
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        
        # Save to temp file (edge-tts outputs MP3)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_mp3_path = f.name
        
        try:
            await communicate.save(temp_mp3_path)
            
            # Read back file
            with open(temp_mp3_path, "rb") as f:
                mp3_data = f.read()
            
            # Decode MP3 to PCM
            audio_data, sample_rate = await self._decode_mp3(mp3_data)
            
            # Direct playback if requested
            if use_direct_playback:
                await self._play_audio(audio_data, sample_rate)
        finally:
            # Clean up temp file
            if os.path.exists(temp_mp3_path):
                os.unlink(temp_mp3_path)
        
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
            voice_id=voice,
            text=text,
            settings_used=settings,
        )

    async def _load_and_play_mp3(
        self, 
        mp3_path: str, 
        play: bool, 
        volume: float
    ) -> tuple[np.ndarray, int]:
        """Load MP3 file and optionally play it."""
        import wave
        import subprocess
        import tempfile
        import os
        
        # Convert MP3 to WAV using ffmpeg if available, otherwise try pygame
        wav_path = mp3_path.replace(".mp3", ".wav")
        
        # Try pygame for direct playback (it handles MP3 natively)
        if play:
            try:
                import pygame
                pygame.mixer.init()
                pygame.mixer.music.load(mp3_path)
                pygame.mixer.music.set_volume(volume)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    await asyncio.sleep(0.1)
                pygame.mixer.quit()
                # Return dummy audio data since we played directly
                return np.zeros(22050, dtype=np.float32), 22050
            except ImportError:
                logger.debug("pygame not available, trying playsound")
            except Exception as e:
                logger.debug(f"pygame playback failed: {e}")
        
        # Try playsound for simple playback
        if play:
            try:
                from playsound import playsound
                playsound(mp3_path)
                return np.zeros(22050, dtype=np.float32), 22050
            except ImportError:
                logger.debug("playsound not available")
            except Exception as e:
                logger.debug(f"playsound failed: {e}")
        
        # For non-playback cases or if playback libraries fail, just return dummy data
        # The main use case is direct playback which works with pygame/playsound
        logger.warning("No MP3 playback library available - install pygame: pip install pygame")
        return np.zeros(22050, dtype=np.float32), 22050

    async def list_voices(self) -> list[VoiceInfo]:
        """List available Edge TTS voices."""
        logger.debug("Listing available voices")
        
        if not self._voices:
            try:
                import edge_tts
                self._voices = await edge_tts.list_voices()
            except Exception as e:
                logger.error(f"Failed to list voices: {e}")
                return []
        
        # Format for our voice list
        result = []
        for voice in self._voices:
            if voice.get("Locale", "").startswith("en-"):  # Filter English voices
                result.append(VoiceInfo(
                    id=voice.get("ShortName", ""),
                    name=voice.get("FriendlyName", ""),
                    language=voice.get("Locale", ""),
                    gender=voice.get("Gender", ""),
                    sample_rate=24000, # Edge TTS usually 24k
                    supports_emotions=True,
                    supported_emotions=list(EMOTION_STYLES.keys())
                ))
        
        logger.info(f"Found {len(result)} English voices")
        return result

    async def get_voice(self, voice_id: str) -> Optional[VoiceInfo]:
        """Get info for a specific voice."""
        voices = await self.list_voices()
        for voice in voices:
            if voice.id == voice_id:
                return voice
        return None

    def _resolve_voice(self, voice_setting: str) -> str:
        """Resolve voice setting to Edge TTS voice name."""
        # If it looks like an Edge TTS voice name, use it directly
        if "-" in voice_setting and "Neural" in voice_setting:
            return voice_setting
        
        # Try to map Piper-style voice to Edge voice
        if voice_setting.startswith("en_US"):
            return DEFAULT_VOICES["en-US"]
        elif voice_setting.startswith("en_GB"):
            return DEFAULT_VOICES["en-GB"]
        elif voice_setting.startswith("en_AU"):
            return DEFAULT_VOICES["en-AU"]
        
        return DEFAULT_VOICES["default"]

    async def _decode_mp3(self, mp3_data: bytes) -> tuple[np.ndarray, int]:
        """Decode MP3 data to numpy array."""
        import io
        
        # Try miniaudio first (pure Python, no external deps)
        try:
            import miniaudio
            decoded = miniaudio.decode(mp3_data, nchannels=1, sample_rate=22050)
            audio_data = np.array(decoded.samples, dtype=np.float32)
            audio_data /= 32768.0  # Normalize int16 to float
            return audio_data, decoded.sample_rate
        except ImportError:
            logger.debug("miniaudio not available, trying pydub")
        except Exception as e:
            logger.debug(f"miniaudio decode failed: {e}, trying pydub")
        
        # Try pydub (requires ffmpeg)
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))
            samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
            samples /= 32768.0
            if audio.channels == 2:
                samples = samples.reshape(-1, 2).mean(axis=1)
            return samples, audio.frame_rate
        except ImportError:
            logger.debug("pydub not available")
        except Exception as e:
            logger.debug(f"pydub decode failed: {e}")
        
        # Try soundfile
        try:
            import soundfile as sf
            audio_data, sample_rate = sf.read(io.BytesIO(mp3_data))
            if len(audio_data.shape) > 1:
                audio_data = audio_data.mean(axis=1)
            return audio_data.astype(np.float32), sample_rate
        except ImportError:
            logger.debug("soundfile not available")
        except Exception as e:
            logger.debug(f"soundfile decode failed: {e}")
        
        logger.error(
            "No MP3 decoder available - returning silence. "
            "Install one of: miniaudio, pydub, soundfile"
        )
        # Return 1 second of silence so the call doesn't crash
        sample_rate = 22050
        return np.zeros(sample_rate, dtype=np.float32), sample_rate

    async def _play_audio(self, audio_data: np.ndarray, sample_rate: int) -> None:
        """Play audio directly using sounddevice."""
        try:
            import sounddevice as sd
            sd.play(audio_data, sample_rate)
            sd.wait()
        except Exception as e:
            logger.error(f"Failed to play audio: {e}")
