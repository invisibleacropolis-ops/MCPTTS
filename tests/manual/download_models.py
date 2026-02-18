"""
Script to download Piper TTS models.
"""
import asyncio
import argparse
import os
import sys
from pathlib import Path
from urllib import request

# Configuration
PIPER_VOICE_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
MODELS_DIR = Path.home() / ".mcp-tts" / "models"

# List of voices to download
# Format: id (language_COUNTRY-name-quality)
VOICES = [
    "en_US-amy-medium",
    "en_US-lessac-high",
    "en_US-libritts_r-medium",
    "en_US-ryan-medium",
    "en_US-joe-medium",
    "en_GB-alan-medium",
    "en_GB-southern_english_female-low",
]

def report_progress(block_num, block_size, total_size):
    """Show download progress."""
    downloaded = block_num * block_size
    if total_size > 0:
        percent = downloaded * 100 / total_size
        sys.stdout.write(f"\rDownloading: {percent:.1f}% ({downloaded / 1024 / 1024:.1f} MB)")
    else:
        sys.stdout.write(f"\rDownloading: {downloaded / 1024 / 1024:.1f} MB")
    sys.stdout.flush()

def download_voice(voice_id: str):
    """Download a single voice."""
    print(f"\nProcessing: {voice_id}")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    parts = voice_id.split("-")
    if len(parts) < 3:
        print(f"Skipping invalid ID: {voice_id}")
        return

    lang_code = parts[0]
    name = parts[1]
    quality = parts[2]
    lang_family = lang_code.split("_")[0]
    
    rel_path = f"{lang_family}/{lang_code}/{name}/{quality}/{voice_id}"
    
    files = {
        "model": f"{PIPER_VOICE_BASE_URL}/{rel_path}.onnx",
        "config": f"{PIPER_VOICE_BASE_URL}/{rel_path}.onnx.json"
    }

    for ftype, url in files.items():
        fname = f"{voice_id}.onnx" if ftype == "model" else f"{voice_id}.onnx.json"
        dest = MODELS_DIR / fname
        
        if dest.exists():
            print(f"  - {fname} already exists, skipping.")
            continue
            
        print(f"  - Fetching {fname}...")
        try:
            request.urlretrieve(url, dest, reporthook=report_progress)
            print() # Newline after progress
        except Exception as e:
            print(f"\n  ! Failed to download {url}: {e}")
            if dest.exists():
                dest.unlink()

def main():
    print(f"Piper Model Downloader")
    print(f"Target Directory: {MODELS_DIR}")
    print(f"========================================")
    
    for voice in VOICES:
        download_voice(voice)
        
    print(f"\n========================================")
    print("Download complete!")

if __name__ == "__main__":
    main()
