"""
MCP resource handlers for Text-to-Speech.

Exposes read-only resources at ``tts://`` URIs.
"""

import json

from mcp_tts.server import mcp
from mcp_tts.server.context import get_context
from mcp_tts.tts.engine import VoiceInfo, validate_emotion_available
from mcp_tts.utils.config import Emotion
from mcp_tts.utils.logging import get_logger

logger = get_logger("server.resources")


async def _resolve_voice_info(tts_engine, voice_id: str) -> VoiceInfo:
    voice_info = await tts_engine.get_voice(voice_id)
    if voice_info is not None:
        return voice_info

    voices = await tts_engine.list_voices()
    if voices:
        return voices[0]

    return VoiceInfo(
        id=voice_id,
        name=voice_id,
        language="unknown",
        emotion_support_reason="Voice capability is unknown because the voice was not found.",
    )


@mcp.resource("tts://voices")
async def get_voices_resource() -> str:
    """Available voice models and their attributes."""
    ctx = get_context()
    await ctx.ensure_initialized()

    logger.debug("resource tts://voices")
    tts_engine = await ctx.engine_manager.get_engine(
        ctx.config.tts.engine, task="tts"
    )
    voices = await tts_engine.list_voices()
    return json.dumps([v.to_dict() for v in voices], indent=2)


@mcp.resource("tts://settings")
async def get_settings_resource() -> str:
    """Current TTS configuration."""
    ctx = get_context()
    await ctx.ensure_initialized()

    logger.debug("resource tts://settings")

    tts_engine = await ctx.engine_manager.get_engine(
        ctx.config.tts.engine, task="tts"
    )
    settings = tts_engine.get_current_settings()
    voice_info = await _resolve_voice_info(tts_engine, settings.voice)
    emotion_validation = validate_emotion_available(voice_info, settings.emotion)

    data = {
        "voice": settings.voice,
        "engine": settings.engine,
        "speed": settings.speed,
        "pitch": settings.pitch,
        "emotion": settings.emotion.value,
        "emotion_intensity": settings.emotion_intensity,
        "volume": settings.volume,
        "emotion_capability": {
            "voice": voice_info.to_dict(),
            "emotion_support": emotion_validation.emotion_support.value,
            "supported_emotions": emotion_validation.supported_emotions,
            "emotion_message": emotion_validation.message,
        },
        "audio": {
            "auto_play": ctx.config.audio.auto_play,
            "sample_rate": ctx.config.audio.sample_rate,
            "output_directory": str(ctx.config.audio.output_directory),
        },
    }

    return json.dumps(data, indent=2)


@mcp.resource("tts://emotions")
async def get_emotions_resource() -> str:
    """Available emotional expressions and their descriptions."""
    ctx = get_context()
    await ctx.ensure_initialized()
    logger.debug("resource tts://emotions")

    tts_engine = await ctx.engine_manager.get_engine(
        ctx.config.tts.engine, task="tts"
    )
    settings = tts_engine.get_current_settings()
    voice_info = await _resolve_voice_info(tts_engine, settings.voice)
    neutral_validation = validate_emotion_available(voice_info, Emotion.NEUTRAL)

    emotions = {
        "neutral": {
            "description": "Normal, balanced speech without strong emotion",
            "available": True,
        },
        "happy": {
            "description": "Cheerful, upbeat tone with higher pitch",
            "available": "happy" in neutral_validation.supported_emotions,
        },
        "sad": {
            "description": "Slower, lower-pitched melancholic speech",
            "available": "sad" in neutral_validation.supported_emotions,
        },
        "angry": {
            "description": "Intense, faster speech with emphasis",
            "available": "angry" in neutral_validation.supported_emotions,
        },
        "excited": {
            "description": "Enthusiastic, fast, high-energy delivery",
            "available": "excited" in neutral_validation.supported_emotions,
        },
        "calm": {
            "description": "Relaxed, slower, soothing voice",
            "available": "calm" in neutral_validation.supported_emotions,
        },
        "fearful": {
            "description": "Tense, slightly faster, uncertain tone",
            "available": "fearful" in neutral_validation.supported_emotions,
        },
        "surprised": {
            "description": "Quick, higher-pitched exclamatory style",
            "available": "surprised" in neutral_validation.supported_emotions,
        },
    }

    return json.dumps(
        {
            "voice": voice_info.to_dict(),
            "emotion_support": neutral_validation.emotion_support.value,
            "emotion_support_reason": voice_info.emotion_support_reason,
            "supported_emotions": neutral_validation.supported_emotions,
            "emotions": emotions,
        },
        indent=2,
    )
