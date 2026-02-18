import asyncio
from mcp_tts.tts.edge import EdgeTTSEngine
from mcp_tts.utils.config import Config

async def test_edge_tts():
    print("Testing Edge TTS initialization...")
    config = Config.load()
    engine = EdgeTTSEngine(models_dir=config.models_directory)
    
    try:
        await engine.initialize()
        print("Initialization successful.")
        
        print("Listing voices...")
        voices = await engine.list_voices()
        print(f"Found {len(voices)} voices.")
        if len(voices) > 0:
            print(f"First voice: {voices[0].name}")

        text = "This is a test of Microsoft Edge Text to Speech."
        print(f"Synthesizing: '{text}'")
        result = await engine.synthesize(text)
        print(f"Synthesis complete: {len(result.audio_data)} samples.")
        
    except Exception as e:
        print(f"Edge TTS failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_edge_tts())
