# MCP TTS Server

A local-running MCP (Model Context Protocol) server that enables LLMs to convert text output to speech using modern neural TTS technology.

## Features

- 🎙️ **Neural TTS**: High-quality text-to-speech using Piper TTS
- 🎭 **Emotion Controls**: Engine-reported emotion availability (`native`, `simulated`, or `unavailable`) with simulated prosody support where available
- ⚡ **Real-time Controls**: Adjust speed, pitch, and emotion intensity on-the-fly
- 🖥️ **GUI Monitoring**: CustomTkinter-based GUI with real-time log viewer
- 🔧 **Extensive Logging**: Verbose debug output for easy troubleshooting
- 🔌 **MCP Compatible**: Works with Claude Desktop, MCP Inspector, and other MCP clients

## Installation

```bash
# Clone the repository
cd c:\GITHUB\MCPTTS

# Install with uv (recommended)
uv pip install -e .

# Or with pip
pip install -e .
```

## Quick Start

### Run with GUI (default)

```bash
mcp-tts
# or
python -m mcp_tts.main
```

### Run with GUI and CUDA

Double-click `Launch_MCP_TTS_CUDA.bat`, or run it from PowerShell/cmd. This uses
a separate `.venv-cuda` environment, installs `mcp-tts[full]`, installs
CUDA-enabled `torch`/`torchaudio`, sets `MCP_TTS_ENGINE=piper`, and prints a CUDA
visibility check before starting the GUI.

The launcher defaults to the PyTorch `cu128` wheel index. To use a different
CUDA wheel index, set `MCP_TTS_CUDA_INDEX_URL` before launching:

```bat
set MCP_TTS_CUDA_INDEX_URL=https://download.pytorch.org/whl/cu126
Launch_MCP_TTS_CUDA.bat
```

### Run Server Only (for MCP clients)

```bash
mcp-tts --server
# or
mcp-tts-server
```

### Connect from Claude Desktop

Add to your Claude Desktop MCP configuration:

```json
{
  "mcpServers": {
    "tts": {
      "command": "uv",
      "args": ["run", "mcp-tts", "--server"]
    }
  }
}
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `speak_text` | Convert text to speech with configurable parameters |
| `set_voice` | Set the default voice model |
| `set_emotion` | Set emotional expression and intensity when supported by the active voice |
| `list_voices` | List available voice models and emotion capabilities |
| `clone_voice` | Add a voice reference for cloning when an engine supports it |
| `get_status` | Get current TTS engine status |
| `get_gpu_status` | Get GPU availability and VRAM diagnostics |
| `configure_tts` | Update TTS settings (speed, pitch, volume) |

### Example Usage

```
// Speak with happy emotion when the active voice reports support
speak_text("Hello! I'm so glad to meet you!", emotion="happy", intensity=0.8)

// Auto-route for low latency
speak_text("Quick preview", engine="auto", task="fast")

// Change voice
set_voice("en_US-joe-medium")

// Adjust speed and pitch
configure_tts(speed=1.2, pitch=0.1)

// Add a cloned voice reference if the active engine supports cloning
clone_voice("C:/voices/sample.wav", name="demo", prompt_text="Sample line", language="en")

// Stream in chunks (long text)
speak_text("Long text...", streaming=true, chunk_size=220)
```

## Configuration

Configuration is stored at `~/.mcp-tts/config.json`:

```json
{
  "tts": {
    "voice": "en_US-amy-medium",
    "engine": "auto",
    "speed": 1.0,
    "pitch": 0.0,
    "emotion": "neutral",
    "emotion_intensity": 0.5
  },
  "audio": {
    "auto_play": true,
    "sample_rate": 22050,
    "effects_enabled": false,
    "normalize_audio": true,
    "compression_strength": 0.2,
    "reverb_wet": 0.1,
    "reverb_decay": 0.4
  }
}
```

Engine selection is controlled via environment variable:

```bash
set MCP_TTS_ENGINE=piper
```

Supported engine values: `auto`, `edge`, `piper`, `system`.

Emotion support is reported per voice in `list_voices`, `get_status`, and the
`tts://voices` / `tts://emotions` resources:

```json
{
  "emotion_support": "simulated",
  "emotion_support_reason": "Piper emotion is simulated with speed and pitch changes.",
  "supports_emotions": true,
  "supported_emotions": ["neutral", "happy", "sad"]
}
```

`supports_emotions` is retained for compatibility. New clients should prefer
`emotion_support`, which can be `native`, `simulated`, or `unavailable`.

You can also switch engines from the GUI settings panel or pass `engine` to `speak_text`.

### Audio Effects

Enable the audio pipeline by setting `effects_enabled` in config. Normalization can run even when effects are off.

### Streaming

Use `streaming=true` with `chunk_size` to stream long text in pieces for earlier playback start.

## Voice Models

Voice models are stored in `~/.mcp-tts/models/`. Download Piper voices from:
https://github.com/rhasspy/piper/releases

### Voice Cloning

The public MCP tool surface includes `clone_voice`, but the currently implemented
engines (`edge`, `piper`, and `system`) do not expose cloning. Calls return an
error unless a future engine implementation adds a real `clone_voice` method.

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
uv run pytest

# Run with verbose logging
mcp-tts --log-level DEBUG
```

## License

MIT
