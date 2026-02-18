"""
MCP tool handlers for Text-to-Speech.

All @mcp.tool() registrations live here.
"""

import asyncio
import numpy as np
from inspect import signature
from pathlib import Path
from typing import Optional

from mcp_tts.server import mcp
from mcp_tts.server.context import get_context
from mcp_tts.tts.engine import TTSResult
from mcp_tts.tts.audio import apply_audio_effects, save_audio, generate_output_filename
from mcp_tts.utils.config import Emotion, TTSSettings
from mcp_tts.utils.gpu import detect_gpu, get_gpu_manager
from mcp_tts.utils.logging import get_logger

logger = get_logger("server.tools")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_text(text: str, max_chars: int) -> list[str]:
    """Split text into chunks on word boundaries."""
    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
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


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


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
        engine: Engine identifier (auto, edge, piper, system)
        task: Routing hint (quality, fast)
        speed: Speech rate multiplier (0.5-2.0, default: 1.0)
        pitch: Pitch adjustment (-1.0 to 1.0, default: 0.0)
        emotion: Emotional expression (neutral, happy, sad, angry, excited, calm, fearful, surprised)
        emotion_intensity: Intensity of emotion (0.0-1.0, default: 0.5)
        auto_play: Automatically play the audio (default: True)
        save_to_file: Save audio to a file (default: False)
        streaming: If True, split text into chunks and synthesize/play incrementally (default: False)
        chunk_size: Maximum characters per chunk when streaming (default: 220, minimum: 80)

    Returns:
        Dictionary with synthesis results including duration and file path if saved
    """
    ctx = get_context()
    await ctx.ensure_initialized()

    logger.info(f"speak_text: '{text[:50]}…' engine={engine} speed={speed} emotion={emotion}")

    # Resolve emotion
    try:
        emotion_enum = Emotion(emotion.lower())
    except ValueError:
        logger.warning(f"Unknown emotion '{emotion}', falling back to neutral")
        emotion_enum = Emotion.NEUTRAL

    # Get engine
    engine_key = engine or ctx.config.tts.engine
    tts_engine = await ctx.engine_manager.get_engine(engine_key, task=task)

    # Build settings — volume lives only on TTSSettings
    settings = TTSSettings(
        voice=voice or tts_engine.get_current_settings().voice,
        engine=tts_engine.engine_type.value,
        speed=max(0.5, min(2.0, speed)),
        pitch=max(-1.0, min(1.0, pitch)),
        emotion=emotion_enum,
        emotion_intensity=max(0.0, min(1.0, emotion_intensity)),
    )

    # Synthesize
    played_in_streaming = False
    if streaming:
        chunks = _split_text(text, max(80, chunk_size))
        combined_audio: list[np.ndarray] = []
        sample_rate: Optional[int] = None

        for idx, chunk in enumerate(chunks, start=1):
            logger.debug(f"Synthesizing chunk {idx}/{len(chunks)}")
            chunk_result = await tts_engine.synthesize(chunk, settings)
            if sample_rate is None:
                sample_rate = chunk_result.sample_rate

            processed = apply_audio_effects(
                chunk_result.audio_data,
                chunk_result.sample_rate,
                ctx.config.audio,
            )
            combined_audio.append(processed)

            if auto_play and ctx.audio_player:
                await asyncio.to_thread(
                    ctx.audio_player.play,
                    processed,
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
            ctx.config.audio,
        )

    response = result.to_dict()
    response["status"] = "success"

    # Play audio
    if auto_play and ctx.audio_player and not played_in_streaming:
        await asyncio.to_thread(
            ctx.audio_player.play,
            result.audio_data,
            result.sample_rate,
            blocking=True,
            volume=settings.volume,
        )
        response["played"] = True

    # Save to file
    if save_to_file:
        output_path = generate_output_filename(text, ctx.config.audio.output_directory)
        saved_path = save_audio(result.audio_data, result.sample_rate, output_path)
        result.saved_path = saved_path
        response["saved_path"] = str(saved_path)

    logger.info(f"speak_text complete: {result.duration_seconds:.2f}s audio")
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
        engine: Engine identifier (edge, piper, system)

    Returns:
        Dictionary confirming the voice change
    """
    ctx = get_context()
    await ctx.ensure_initialized()

    logger.info(f"set_voice: {voice}")

    engine_key = engine or ctx.config.tts.engine
    tts_engine = await ctx.engine_manager.get_engine(engine_key, task="tts")

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
        intensity: Intensity of the emotion (0.0-1.0, default: 0.5)
        engine: Engine identifier (edge, piper, system)

    Returns:
        Dictionary confirming the emotion settings
    """
    ctx = get_context()
    await ctx.ensure_initialized()

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

    engine_key = engine or ctx.config.tts.engine
    tts_engine = await ctx.engine_manager.get_engine(engine_key, task="tts")
    tts_engine.set_emotion(emotion_enum, max(0.0, min(1.0, intensity)))

    logger.info(f"Emotion set: {emotion_enum.value} @ {intensity}")
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
    ctx = get_context()
    await ctx.ensure_initialized()

    engine_key = engine or ctx.config.tts.engine
    tts_engine = await ctx.engine_manager.get_engine(engine_key, task="tts")
    voices = await tts_engine.list_voices()
    result = [v.to_dict() for v in voices]

    logger.info(f"list_voices: {len(result)} voices found")
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
        engine: Engine identifier (requires an engine that supports cloning)

    Returns:
        Dictionary with status and reference details
    """
    ctx = get_context()
    await ctx.ensure_initialized()

    engine_key = engine or ctx.config.tts.engine
    tts_engine = await ctx.engine_manager.get_engine(engine_key, task="clone")

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

    clone_kwargs: dict = {
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
    return {"status": "success", "reference": result}


@mcp.tool()
async def get_status() -> dict:
    """
    Get current TTS engine status and settings.

    Returns:
        Dictionary with engine status and current configuration
    """
    ctx = get_context()
    if not ctx.is_ready:
        return {
            "status": "not_initialized",
            "message": "TTS engine not yet initialized",
        }

    tts_engine = await ctx.engine_manager.get_engine(
        ctx.config.tts.engine, task="tts"
    )
    settings = tts_engine.get_current_settings()
    gpu_info = detect_gpu()

    return {
        "status": "ready",
        "engine": {
            "type": tts_engine.engine_type.value,
            "name": tts_engine.name,
            "initialized": tts_engine.is_initialized,
            "loaded": ctx.engine_manager.list_loaded(),
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
            "auto_play": ctx.config.audio.auto_play,
            "sample_rate": ctx.config.audio.sample_rate,
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
        engine: Engine identifier (edge, piper, system)
        speed: Speech rate multiplier (0.5-2.0)
        pitch: Pitch adjustment (-1.0 to 1.0)
        volume: Output volume (0.0-1.0)
        auto_play: Automatically play audio after synthesis

    Returns:
        Dictionary with updated configuration
    """
    ctx = get_context()
    await ctx.ensure_initialized()

    logger.info(f"configure_tts: speed={speed} pitch={pitch} volume={volume} auto_play={auto_play}")

    updates: dict = {}
    if speed is not None:
        updates["speed"] = max(0.5, min(2.0, speed))
    if pitch is not None:
        updates["pitch"] = max(-1.0, min(1.0, pitch))
    if volume is not None:
        updates["volume"] = max(0.0, min(1.0, volume))

    engine_key = engine or ctx.config.tts.engine
    tts_engine = await ctx.engine_manager.get_engine(engine_key, task="tts")
    if updates:
        tts_engine.update_settings(**updates)

    if auto_play is not None:
        ctx.config.audio.auto_play = auto_play
        ctx.config.save()

    new_settings = tts_engine.get_current_settings()
    return {
        "status": "success",
        "updated": list(updates.keys()) + (["auto_play"] if auto_play is not None else []),
        "current_settings": {
            "speed": new_settings.speed,
            "pitch": new_settings.pitch,
            "volume": new_settings.volume,
            "engine": new_settings.engine,
            "auto_play": ctx.config.audio.auto_play,
        },
    }


@mcp.tool()
async def health_check() -> dict:
    """
    Check MCP TTS server health.

    Returns server status, loaded engines, and memory info without
    triggering engine initialization.

    Returns:
        Dictionary with health status
    """
    import sys

    ctx = get_context()

    health: dict = {
        "status": "healthy",
        "python_version": sys.version,
        "server_initialized": ctx.is_ready,
        "engines_loaded": [],
        "config_loaded": ctx.is_ready,
    }

    if ctx.is_ready:
        health["engines_loaded"] = ctx.engine_manager.list_loaded()
        health["current_engine"] = (
            ctx.engine_manager.current_engine.value
            if ctx.engine_manager.current_engine
            else None
        )

    # Check optional dependencies
    deps: dict = {}
    for mod in ["edge_tts", "pyttsx3", "sounddevice", "miniaudio", "pydub", "torch"]:
        try:
            __import__(mod)
            deps[mod] = True
        except ImportError:
            deps[mod] = False
    health["dependencies"] = deps

    logger.info(f"health_check: {health['status']}")
    return health


@mcp.tool()
async def reload_config() -> dict:
    """
    Reload configuration from disk.

    Use this after manually editing ``~/.mcp-tts/config.json`` to pick
    up changes without restarting the server.

    Returns:
        Dictionary with the reloaded configuration summary
    """
    ctx = get_context()
    await ctx.ensure_initialized()

    config = ctx.reload_config()
    logger.info("Config reloaded via tool")

    return {
        "status": "success",
        "tts": {
            "voice": config.tts.voice,
            "engine": config.tts.engine,
            "speed": config.tts.speed,
            "pitch": config.tts.pitch,
            "emotion": config.tts.emotion.value,
        },
        "audio": {
            "auto_play": config.audio.auto_play,
            "sample_rate": config.audio.sample_rate,
        },
    }
