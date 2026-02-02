import os
import zipfile
import urllib.request
from pathlib import Path

def main():
    # Define paths
    base_dir = Path(os.path.expanduser("~/.mcp-tts"))
    base_dir.mkdir(parents=True, exist_ok=True)
    
    piper_dir = base_dir / "piper"
    zip_path = base_dir / "piper_windows_amd64.zip"
    
    url = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"
    
    print(f"Base directory: {base_dir}")
    
    # Download
    print(f"Downloading Piper binary from {url}...")
    try:
        urllib.request.urlretrieve(url, zip_path)
        print(f"Downloaded to {zip_path}")
    except Exception as e:
        print(f"Download failed: {e}")
        return

    # Extract
    print(f"Extracting to {base_dir}...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(base_dir)
        print("Extraction complete.")
    except Exception as e:
        print(f"Extraction failed: {e}")
        return
        
    # Verify
    exe_path = piper_dir / "piper.exe"
    if exe_path.exists():
        print(f"Verified piper.exe at {exe_path}")
    else:
        print(f"Warning: piper.exe not found at expected path {exe_path}")
        # List contents to help debug
        print(f"Contents of {piper_dir}:")
        for item in piper_dir.iterdir():
            print(f" - {item.name}")

if __name__ == "__main__":
    main()
