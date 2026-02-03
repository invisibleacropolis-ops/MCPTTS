import os
import io
import zipfile
import urllib.request
from pathlib import Path

def install_piper():
    url = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"
    install_dir = Path(os.path.expanduser("~/.mcp-tts"))
    target_exe = install_dir / "piper" / "piper.exe"
    
    print(f"Target directory: {install_dir}")
    
    if target_exe.exists():
        print(f"Piper already installed at {target_exe}")
        return

    print(f"Downloading Piper from {url}...")
    try:
        with urllib.request.urlopen(url) as response:
            data = response.read()
            
        print(f"Download complete. Size: {len(data)} bytes")
        
        print("Extracting...")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            # The zip normally contains a 'piper' root folder
            z.extractall(install_dir)
            
        if target_exe.exists():
            print(f"Success! Piper installed at {target_exe}")
        else:
            print(f"Error: piper.exe not found at expected location after extraction: {target_exe}")
            # List what was extracted to help debug
            print("Contents of install dir:")
            for p in install_dir.rglob("*"):
                print(f" - {p}")
                
    except Exception as e:
        print(f"Failed to install Piper: {e}")
        raise

if __name__ == "__main__":
    install_piper()
