import wave
from pathlib import Path
from piper import PiperVoice

def main():
    models_dir = Path.home() / ".mcp-tts" / "models"
    model_path = models_dir / "en_US-libritts_r-medium.onnx"
    config_path = models_dir / "en_US-libritts_r-medium.onnx.json"
    
    print(f"Loading model from {model_path}")
    voice = PiperVoice.load(str(model_path), str(config_path))
    
    text = "This is a direct test of the piper library."
    output_path = "direct_test.wav"
    
    print("Synthesizing...")
    with wave.open(output_path, "wb") as wav_file:
         wav_file.setnchannels(1)
         wav_file.setsampwidth(2)
         wav_file.setframerate(voice.config.sample_rate)
         voice.synthesize(text, wav_file)
            
    print("Done.")
    
    # Check file size
    size = Path(output_path).stat().st_size
    print(f"Output file size: {size} bytes")

if __name__ == "__main__":
    main()
