"""
MCP resource handlers for Text-to-Speech.

Exposes read-only resources at ``tts://`` URIs.
"""

import json

from mcp_tts.server import mcp
from mcp_tts.server.context import get_context
from mcp_tts.utils.config import Emotion
from mcp_tts.utils.logging import get_logger

logger = get_logger("server.resources")


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

    data = {
        "voice": settings.voice,
        "engine": settings.engine,
        "speed": settings.speed,
        "pitch": settings.pitch,
        "emotion": settings.emotion.value,
        "emotion_intensity": settings.emotion_intensity,
        "volume": settings.volume,
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
    logger.debug("resource tts://emotions")

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
