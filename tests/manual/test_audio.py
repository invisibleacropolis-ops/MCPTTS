import numpy as np
import time
from mcp_tts.tts.audio import AudioPlayer
import sounddevice as sd

def test_playback():
    print("Testing audio playback...")
    
    # 1. Test raw sounddevice
    print("1. Testing raw sounddevice (tone)...")
    fs = 44100
    seconds = 1
    t = np.linspace(0, seconds, seconds * fs, False)
    # Generate a 440 Hz sine wave
    note = np.sin(440 * t * 2 * np.pi)
    
    # Ensure float32
    audio = note.astype(np.float32)
    
    try:
        sd.play(audio, fs)
        sd.wait()
        print("Raw playback complete.")
    except Exception as e:
        print(f"Raw playback failed: {e}")

    # 2. Test AudioPlayer class
    print("\n2. Testing AudioPlayer class...")
    player = AudioPlayer()
    try:
        player.play(audio, fs)
        print("AudioPlayer playback complete.")
    except Exception as e:
        print(f"AudioPlayer playback failed: {e}")

if __name__ == "__main__":
    test_playback()
