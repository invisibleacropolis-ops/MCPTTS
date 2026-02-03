"""
MCP Server implementation for Text-to-Speech.

Exposes TTS functionality as MCP tools and resources that can be
used by LLMs via the Model Context Protocol.
"""

import asyncio
import json
import os
import numpy as np
from inspect import signature
from pathlib import Path
from typing import Optional

from mcp.server import FastMCP

from mcp_tts.tts.engine import resolve_engine_type, TTSEngineType, TTSResult, VoiceInfo
from mcp_tts.tts.manager import EngineManager
from mcp_tts.tts.audio import AudioPlayer, apply_audio_effects, save_audio, generate_output_filename
from mcp_tts.utils.config import Config, Emotion, TTSSettings
from mcp_tts.utils.gpu import detect_gpu, get_gpu_manager
from mcp_tts.utils.logging import setup_logging, get_logger

# Initialize logging
logger = get_logger("server")

# Create MCP server instance
mcp = FastMCP(
    name="MCP TTS Server",
)

# Global state (initialized on startup)
_engine_manager = None
_audio_player = None
_config = None


def _split_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    parts = []
    buffer = ""
    for chunk in text.split(" "):
        if len(buffer) + len(chunk) + 1 > max_chars:
            parts.append(buffer.strip())
            buffer = chunk
        else:
            buffer = f"{buffer} {chunk}".strip()

    if buffer:
        parts.append(buffer.strip())

    return [part for part in parts if part]


async def initialize_server(config: Optional[Config] = None):
    """Initialize the TTS engine and audio player (lazy - defers engine loading)."""
    global _engine_manager, _audio_player, _config

    if _config is not None:
        return  # Already initialized

    _config = config or Config.load()
    _config.ensure_directories()

    logger.info("Initializing MCP TTS Server...")
    logger.debug(f"Config loaded: {_config.model_dump()}")

    # Create engine manager (lazy - doesn't load engine yet)
    _engine_manager = EngineManager(models_dir=_config.models_directory)
    
    # Set default to Edge TTS (fast cloud-based)
    engine_type = resolve_engine_type(os.getenv("MCP_TTS_ENGINE"), TTSEngineType.EDGE)
    _engine_manager.set_default_engine(engine_type)
    
    # Don't preload - let it load on first use to avoid startup timeout

    # Create audio player
    _audio_player = AudioPlayer(device=_config.audio.output_device)

    logger.info("MCP TTS Server ready (engine will load on first use)")


# ============================================================================
# MCP TOOLS
# ============================================================================


@mcp.tool()
async def talk(text: str, voice: Optional[str] = None) -> dict:
    """
    Speak text aloud using the TTS engine.
    
    Use this tool to give voice to your responses. The audio will play
    immediately on the user's device.
    
    Args:
        text: The text to speak aloud
        voice: Optional voice to use (default: current configured voice)
    
    Returns:
        Dictionary with success status and duration
    """
    global _engine_manager, _config
    
    if _engine_manager is None:
        await initialize_server()
    
    # Reload config to pick up external changes
    _config = Config.load()
    
    try:
        # Get the engine
        engine = await _engine_manager.get_engine()
        
        # Build settings
        settings = TTSSettings(
            voice=voice or _config.tts.voice,
            speed=_config.tts.speed,
            pitch=_config.tts.pitch,
            emotion=_config.tts.emotion,
            emotion_intensity=_config.tts.emotion_intensity,
            volume=_config.audio.volume if hasattr(_config.audio, 'volume') else 1.0,
        )
        
        # Synthesize with direct playback
        result = await engine.synthesize(text, settings, use_direct_playback=True)
        
        logger.info(f"Talk: '{text[:50]}...' ({result.duration_seconds:.2f}s)")
        
        return {
            "success": True,
            "text": text,
            "duration_seconds": result.duration_seconds,
            "voice": settings.voice,
        }
        
    except Exception as e:
        logger.error(f"Talk failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool()
async def speak_text(
    text: str,
    voice: Optional[str] = None,
    engine: Optional[str] = None,
    task: Optional[str] = None,
    speed: float = 1.0,
    pitch: float = 0.0,
    emotion: str = "neutral",
    emotion_intensity: float = 0.5,
    auto_play: bool = True,
    save_to_file: bool = False,
    streaming: bool = False,
    chunk_size: int = 220,
) -> dict:
    """
    Convert text to speech with configurable parameters.

    Args:
        text: The text to convert to speech
        voice: Voice model to use (default: current voice)
        engine: Engine identifier (auto, fish, xtts, piper, system)
        task: Routing hint (quality, fast)
        speed: Speech rate multiplier (0.5-2.0, default: 1.0)
        pitch: Pitch adjustment (-1.0 to 1.0, default: 0.0)
        emotion: Emotional expression (neutral, happy, sad, angry, excited, calm, fearful, surprised)
        emotion_intensity: Intensity of emotion (0.0-1.0, default: 0.5)
        auto_play: Automatically play the audio (default: True)
        save_to_file: Save audio to a file (default: False)

    Returns:
        Dictionary with synthesis results including duration and file path if saved
    """
    global _engine_manager, _audio_player, _config

    if _engine_manager is None:
        await initialize_server()

    # Reload config to pick up external changes
    _config = Config.load()

    logger.info(f"[TOOL] speak_text called: '{text[:50]}...'")
    logger.debug(
        f"Parameters: voice={voice}, speed={speed}, pitch={pitch}, "
        f"emotion={emotion}, intensity={emotion_intensity}"
    )

    logger.info(f"Synthesizing: {text[:30]}...")

    # Build settings
    try:
        emotion_enum = Emotion(emotion.lower())
    except ValueError:
        logger.warning(f"Unknown emotion '{emotion}', using neutral")
        emotion_enum = Emotion.NEUTRAL

    engine_key = engine or (_config.tts.engine if _config else None)
    tts_engine = await _engine_manager.get_engine(engine_key, task=task)

    resolved_engine = tts_engine.engine_type.value
    if engine_key and engine_key.lower() != "auto":
        resolved_engine = engine_key

    settings = TTSSettings(
        voice=voice or tts_engine.get_current_settings().voice,
        engine=resolved_engine,
        speed=max(0.5, min(2.0, speed)),
        pitch=max(-1.0, min(1.0, pitch)),
        emotion=emotion_enum,
        emotion_intensity=max(0.0, min(1.0, emotion_intensity)),
    )

    # Report progress
    logger.debug("Starting synthesis...")

    # Synthesize
    played_in_streaming = False
    if streaming:
        chunks = _split_text(text, max(80, chunk_size))
        combined_audio = []
        sample_rate = None
        for idx, chunk in enumerate(chunks, start=1):
            logger.debug(f"Synthesizing chunk {idx}/{len(chunks)}")

            chunk_result = await tts_engine.synthesize(chunk, settings)
            if sample_rate is None:
                sample_rate = chunk_result.sample_rate

            processed_audio = apply_audio_effects(
                chunk_result.audio_data,
                chunk_result.sample_rate,
                _config.audio if _config else None,
            )
            combined_audio.append(processed_audio)

            if auto_play and _audio_player:
                await asyncio.to_thread(
                    _audio_player.play,
                    processed_audio,
                    chunk_result.sample_rate,
                    blocking=True,
                    volume=settings.volume,
                )
                played_in_streaming = True

        audio_data = np.concatenate(combined_audio) if combined_audio else np.array([])
        result = TTSResult(
            audio_data=audio_data,
            sample_rate=sample_rate or 22050,
            duration_seconds=len(audio_data) / (sample_rate or 22050),
            voice_id=settings.voice,
            text=text,
            settings_used=settings,
        )
    else:
        result = await tts_engine.synthesize(text, settings)
        result.audio_data = apply_audio_effects(
            result.audio_data,
            result.sample_rate,
            _config.audio if _config else None,
        )

    logger.debug("Synthesis complete")

    response = result.to_dict()
    response["status"] = "success"

    # Play audio if requested
    if auto_play and _audio_player and not played_in_streaming:
        logger.debug("Playing synthesized audio...")
        logger.debug("Playing audio...")

        # Run playback in a thread to not block
        await asyncio.to_thread(
            _audio_player.play,
            result.audio_data,
            result.sample_rate,
            blocking=True,
            volume=settings.volume,
        )
        response["played"] = True

    # Save to file if requested
    if save_to_file and _config:
        output_path = generate_output_filename(text, _config.audio.output_directory)
        saved_path = save_audio(
            result.audio_data,
            result.sample_rate,
            output_path,
        )
        result.saved_path = saved_path
        response["saved_path"] = str(saved_path)
        logger.info(f"Audio saved to: {saved_path}")

    logger.debug("Synthesis complete")

    logger.info(f"[TOOL] speak_text complete: {result.duration_seconds:.2f}s audio")
    return response


@mcp.tool()
async def set_voice(
    voice: str,
    engine: Optional[str] = None,
) -> dict:
    """
    Set the default voice for subsequent TTS calls.

    Args:
        voice: Voice model identifier (use list_voices to see available options)
        engine: Engine identifier (fish, xtts, piper, system)

    Returns:
        Dictionary confirming the voice change
    """
    global _engine_manager, _config

    if _engine_manager is None:
        await initialize_server()

    logger.info(f"[TOOL] set_voice: {voice}")

    logger.info(f"Setting voice to: {voice}")

    engine_key = engine or (_config.tts.engine if _config else None)
    tts_engine = await _engine_manager.get_engine(engine_key, task="tts")

    # Verify voice exists
    voice_info = await tts_engine.get_voice(voice)
    if voice_info is None:
        logger.warning(f"Voice not found: {voice}")
        return {
            "status": "warning",
            "message": f"Voice '{voice}' not found in local models. It may need to be downloaded.",
            "voice": voice,
        }

    tts_engine.set_voice(voice)

    logger.info(f"Voice set to: {voice}")
    return {
        "status": "success",
        "voice": voice,
        "voice_info": voice_info.to_dict(),
    }


@mcp.tool()
async def set_emotion(
    emotion: str,
    intensity: float = 0.5,
    engine: Optional[str] = None,
) -> dict:
    """
    Set the emotional expression for TTS output.

    Args:
        emotion: Emotional tone (neutral, happy, sad, angry, excited, calm, fearful, surprised)
        engine: Engine identifier (fish, xtts, piper, system)
        intensity: Intensity of the emotion (0.0-1.0, default: 0.5)

    Returns:
        Dictionary confirming the emotion settings
    """
    global _engine_manager, _config

    if _engine_manager is None:
        await initialize_server()

    logger.info(f"[TOOL] set_emotion: {emotion} @ {intensity}")

    logger.info(f"Setting emotion to: {emotion} (intensity: {intensity})")

    try:
        emotion_enum = Emotion(emotion.lower())
    except ValueError:
        available = [e.value for e in Emotion]
        logger.warning(f"Unknown emotion '{emotion}'. Available: {available}")
        return {
            "status": "error",
            "message": f"Unknown emotion '{emotion}'",
            "available_emotions": available,
        }

    engine_key = engine or (_config.tts.engine if _config else None)
    tts_engine = await _engine_manager.get_engine(engine_key, task="tts")
    tts_engine.set_emotion(emotion_enum, max(0.0, min(1.0, intensity)))

    logger.info(f"Emotion set to: {emotion_enum.value} @ {intensity}")
    return {
        "status": "success",
        "emotion": emotion_enum.value,
        "intensity": intensity,
    }


@mcp.tool()
async def list_voices(
    engine: Optional[str] = None,
) -> list[dict]:
    """
    List all available voice models with their capabilities.

    Returns:
        List of voice information dictionaries
    """
    global _engine_manager, _config

    if _engine_manager is None:
        await initialize_server()

    logger.info("[TOOL] list_voices")

    logger.info("Listing available voices...")

    engine_key = engine or (_config.tts.engine if _config else None)
    tts_engine = await _engine_manager.get_engine(engine_key, task="tts")
    voices = await tts_engine.list_voices()
    result = [v.to_dict() for v in voices]

    logger.info(f"Found {len(result)} voices")
    return result


@mcp.tool()
async def clone_voice(
    audio_path: str,
    name: str,
    prompt_text: str = "Sample",
    language: Optional[str] = None,
    engine: Optional[str] = None,
) -> dict:
    """
    Add a voice reference for cloning.

    Args:
        audio_path: Path to reference audio file
        name: Reference voice id
        prompt_text: Transcript of the reference audio
        engine: Engine identifier (fish, xtts)

    Returns:
        Dictionary with status and reference details
    """
    global _engine_manager, _config

    if _engine_manager is None:
        await initialize_server()

    engine_key = engine or (_config.tts.engine if _config else None)
    tts_engine = await _engine_manager.get_engine(engine_key, task="clone")

    if not hasattr(tts_engine, "clone_voice"):
        return {
            "status": "error",
            "message": "Current engine does not support voice cloning",
        }

    reference_path = Path(audio_path)
    if not reference_path.exists():
        return {
            "status": "error",
            "message": f"Audio file not found: {audio_path}",
        }

    logger.info(f"Cloning voice '{name}' from {audio_path}")

    clone_kwargs = {
        "audio_path": reference_path,
        "name": name,
        "prompt_text": prompt_text,
    }
    try:
        if language and "language" in signature(tts_engine.clone_voice).parameters:
            clone_kwargs["language"] = language
    except Exception:
        pass

    result = await tts_engine.clone_voice(**clone_kwargs)
    return {
        "status": "success",
        "reference": result,
    }


@mcp.tool()
async def get_status() -> dict:
    """
    Get current TTS engine status and settings.

    Returns:
        Dictionary with engine status and current configuration
    """
    global _engine_manager, _config

    if _engine_manager is None:
        return {
            "status": "not_initialized",
            "message": "TTS engine not yet initialized",
        }

    # Reload config to pick up external changes
    _config = Config.load()

    logger.info("[TOOL] get_status")

    tts_engine = await _engine_manager.get_engine(
        _config.tts.engine if _config else None, task="tts"
    )
    settings = tts_engine.get_current_settings()

    gpu_info = detect_gpu()

    return {
        "status": "ready",
        "engine": {
            "type": tts_engine.engine_type.value,
            "name": tts_engine.name,
            "initialized": tts_engine.is_initialized,
            "loaded": _engine_manager.list_loaded(),
        },
        "gpu": gpu_info.to_dict() if gpu_info else None,
        "current_settings": {
            "voice": settings.voice,
            "engine": settings.engine,
            "speed": settings.speed,
            "pitch": settings.pitch,
            "emotion": settings.emotion.value,
            "emotion_intensity": settings.emotion_intensity,
            "volume": settings.volume,
        },
        "audio": {
            "auto_play": _config.audio.auto_play if _config else True,
            "sample_rate": _config.audio.sample_rate if _config else 22050,
        },
    }


@mcp.tool()
async def get_gpu_status() -> dict:
    """
    Get GPU availability and VRAM diagnostics.

    Returns:
        Dictionary with GPU info and CUDA availability
    """
    gpu_manager = get_gpu_manager()
    gpu_info = gpu_manager.refresh_vram_info()

    return {
        "status": "ready" if gpu_info else "unavailable",
        "cuda_available": gpu_manager.is_gpu_available,
        "gpu": gpu_info.to_dict() if gpu_info else None,
    }


@mcp.tool()
async def configure_tts(
    engine: Optional[str] = None,
    speed: Optional[float] = None,
    pitch: Optional[float] = None,
    volume: Optional[float] = None,
    auto_play: Optional[bool] = None,
) -> dict:
    """
    Configure TTS settings (all parameters optional).

    Args:
        engine: Engine identifier (fish, xtts, piper, system)
        speed: Speech rate multiplier (0.5-2.0)
        pitch: Pitch adjustment (-1.0 to 1.0)
        volume: Output volume (0.0-1.0)
        auto_play: Automatically play audio after synthesis

    Returns:
        Dictionary with updated configuration
    """
    global _engine_manager, _config

    if _engine_manager is None:
        await initialize_server()

    logger.info(
        f"[TOOL] configure_tts: speed={speed}, pitch={pitch}, volume={volume}, auto_play={auto_play}"
    )

    updates = {}

    if speed is not None:
        updates["speed"] = max(0.5, min(2.0, speed))
    if pitch is not None:
        updates["pitch"] = max(-1.0, min(1.0, pitch))
    if volume is not None:
        updates["volume"] = max(0.0, min(1.0, volume))

    engine_key = engine or (_config.tts.engine if _config else None)
    tts_engine = await _engine_manager.get_engine(engine_key, task="tts")
    if updates:
        tts_engine.update_settings(**updates)

    if auto_play is not None and _config:
        _config.audio.auto_play = auto_play
        _config.save()

    new_settings = tts_engine.get_current_settings()

    logger.info(f"TTS configured: {updates}")
    return {
        "status": "success",
        "updated": list(updates.keys()) + (["auto_play"] if auto_play is not None else []),
        "current_settings": {
            "speed": new_settings.speed,
            "pitch": new_settings.pitch,
            "volume": new_settings.volume,
            "engine": new_settings.engine,
            "auto_play": _config.audio.auto_play if _config else True,
        },
    }


# ============================================================================
# MCP RESOURCES
# ============================================================================


@mcp.resource("tts://voices")
async def get_voices_resource() -> str:
    """Available voice models and their attributes."""
    global _engine_manager, _config

    if _engine_manager is None:
        await initialize_server()

    logger.debug("[RESOURCE] tts://voices")
    tts_engine = await _engine_manager.get_engine(
        _config.tts.engine if _config else None, task="tts"
    )
    voices = await tts_engine.list_voices()
    return json.dumps([v.to_dict() for v in voices], indent=2)


@mcp.resource("tts://settings")
async def get_settings_resource() -> str:
    """Current TTS configuration."""
    global _engine_manager, _config

    if _engine_manager is None:
        await initialize_server()

    logger.debug("[RESOURCE] tts://settings")

    tts_engine = await _engine_manager.get_engine(
        _config.tts.engine if _config else None, task="tts"
    )
    settings = tts_engine.get_current_settings()

    data = {
        "voice": settings.voice,
        "engine": settings.engine,
        "speed": settings.speed,
        "pitch": settings.pitch,
        "emotion": settings.emotion.value,
        "emotion_intensity": settings.emotion_intensity,
        "volume": settings.volume,
        "audio": {
            "auto_play": _config.audio.auto_play if _config else True,
            "sample_rate": _config.audio.sample_rate if _config else 22050,
            "output_directory": str(_config.audio.output_directory) if _config else None,
        },
    }

    return json.dumps(data, indent=2)


@mcp.resource("tts://emotions")
async def get_emotions_resource() -> str:
    """Available emotional expressions and their descriptions."""
    logger.debug("[RESOURCE] tts://emotions")

    emotions = {
        "neutral": "Normal, balanced speech without strong emotion",
        "happy": "Cheerful, upbeat tone with higher pitch",
        "sad": "Slower, lower-pitched melancholic speech",
        "angry": "Intense, faster speech with emphasis",
        "excited": "Enthusiastic, fast, high-energy delivery",
        "calm": "Relaxed, slower, soothing voice",
        "fearful": "Tense, slightly faster, uncertain tone",
        "surprised": "Quick, higher-pitched exclamatory style",
    }

    return json.dumps(emotions, indent=2)


# ============================================================================
# SERVER LIFECYCLE
# ============================================================================


def run_server():
    """Run the MCP server (entry point for mcp-tts-server command)."""
    import logging

    # Set up verbose logging
    setup_logging(
        level=logging.DEBUG,
        verbose=True,
    )

    logger.info("Starting MCP TTS Server...")

    # Run with stdio transport (default for MCP)
    mcp.run()


if __name__ == "__main__":
    run_server()
