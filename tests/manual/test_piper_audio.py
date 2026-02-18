import asyncio
import numpy as np
from pathlib import Path
from mcp_tts.tts.piper import PiperTTSEngine
from mcp_tts.utils.config import Config

async def test_piper_generation():
    print("Testing Piper audio generation...")
    config = Config.load()
    engine = PiperTTSEngine(models_dir=config.models_directory)
    
    await engine.initialize()
    
    text = "This is a test of the Piper text to speech engine."
    print(f"Synthesizing: '{text}'")
    
    try:
        result = await engine.synthesize(text)
        
        print(f"Synthesis complete.")
        print(f"Sample Rate: {result.sample_rate}")
        print(f"Data shape: {result.audio_data.shape}")
        print(f"Data type: {result.audio_data.dtype}")
        print(f"Min value: {np.min(result.audio_data)}")
        print(f"Max value: {np.max(result.audio_data)}")
        print(f"Mean value: {np.mean(result.audio_data)}")
        
        # Save to file to verify
        import wave
        output_path = "test_piper_output.wav"
        
        # Convert to int16 for saving
        audio_int16 = (result.audio_data * 32767).astype(np.int16)
        
        with wave.open(output_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(result.sample_rate)
            wav_file.writeframes(audio_int16.tobytes())
            
        print(f"Saved to {output_path}")
        
        # Try playing with sounddevice directly
        import sounddevice as sd
        print("Playing generated audio...")
        sd.play(result.audio_data, result.sample_rate)
        sd.wait()
        print("Playback complete.")

    except Exception as e:
        print(f"Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_piper_generation())
