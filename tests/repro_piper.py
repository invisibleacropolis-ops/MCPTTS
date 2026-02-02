
import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from mcp_tts.tts.piper import PiperTTSEngine
from mcp_tts.tts.engine import TTSSettings
from mcp_tts.utils.logging import setup_logging

async def main():
    setup_logging(verbose=True)
    logger = logging.getLogger("repro_piper")
    
    logger.info("Initializing Piper Engine...")
    engine = PiperTTSEngine()
    
    try:
        await engine.initialize()
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        return

    logger.info("Listing voices...")
    voices = await engine.list_voices()
    logger.info(f"Found {len(voices)} voices")
    for v in voices:
        logger.info(f"Voice: {v.name} ({v.id})")

    if not voices:
        logger.error("No voices found!")
        return

    # Use the known downloaded voice
    target_voice = "en_US-libritts_r-medium"
    logger.info(f"Synthesizing with voice: {target_voice}")
    
    settings = TTSSettings(voice=target_voice)
    
    try:
        result = await engine.synthesize(
            "Hello, this is a test of the Piper TTS engine.",
            settings=settings
        )
        logger.info(f"Synthesis successful! Duration: {result.duration_seconds:.2f}s")
        
        # Save output
        if result.audio_data is not None:
             import soundfile as sf
             output_file = Path("piper_output.wav")
             sf.write(output_file, result.audio_data, result.sample_rate)
             logger.info(f"Saved audio to {output_file}")
             
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
