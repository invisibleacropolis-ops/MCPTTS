# MCP TTS Server

A local-running MCP (Model Context Protocol) server that enables LLMs to convert text output to speech using modern neural TTS technology.

## Features

- 🎙️ **Neural TTS**: High-quality text-to-speech using Piper TTS
- 🎭 **Emotional Expression**: Support for 8 emotional tones (neutral, happy, sad, angry, excited, calm, fearful, surprised)
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
| `set_emotion` | Set emotional expression and intensity |
| `list_voices` | List available voice models |
| `clone_voice` | Add a voice reference for cloning (Fish/XTTS) |
| `get_status` | Get current TTS engine status |
| `get_gpu_status` | Get GPU availability and VRAM diagnostics |
| `configure_tts` | Update TTS settings (speed, pitch, volume) |

### Example Usage

```
// Speak with happy emotion
speak_text("Hello! I'm so glad to meet you!", emotion="happy", intensity=0.8)

// Auto-route for low latency
speak_text("Quick preview", engine="auto", task="fast")

// Change voice
set_voice("en_US-joe-medium")

// Adjust speed and pitch
configure_tts(speed=1.2, pitch=0.1)

// Add a cloned voice reference (XTTS/Fish)
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
set MCP_TTS_ENGINE=fish
```

Supported engine values: `auto`, `fish`, `xtts`, `piper`, `system`.

You can also switch engines from the GUI settings panel or pass `engine` to `speak_text`.

### Audio Effects

Enable the audio pipeline by setting `effects_enabled` in config. Normalization can run even when effects are off.

### Streaming

Use `streaming=true` with `chunk_size` to stream long text in pieces for earlier playback start.

## Voice Models

Voice models are stored in `~/.mcp-tts/models/`. Download Piper voices from:
https://github.com/rhasspy/piper/releases

### Fish Speech (OpenAudio S1-mini)

Fish Speech uses a local HTTP API server for inference. Start it in a separate terminal:

```bash
python -m tools.api_server \
  --listen 127.0.0.1:8080 \
  --llama-checkpoint-path "checkpoints/openaudio-s1-mini" \
  --decoder-checkpoint-path "checkpoints/openaudio-s1-mini/codec.pth" \
  --decoder-config-name modded_dac_vq
```

Then point MCP TTS at the API with environment variables:

```bash
set FISH_SPEECH_API_URL=http://127.0.0.1:8080
```

You can also auto-launch the Fish Speech API when starting MCP TTS:

```bash
set FISH_SPEECH_REPO=C:\GITHUB\FishSpeechServer
mcp-tts
```

Or pass the repo path on the CLI:

```bash
mcp-tts --fish-repo C:\GITHUB\FishSpeechServer
```

### XTTS-v2 (Coqui TTS)

Install dependencies:

```bash
pip install -e ".[xtts,gpu]"
```

Set engine and optional language override:

```bash
set MCP_TTS_ENGINE=xtts
set XTTS_LANGUAGE=en
```

Use `clone_voice` to add a reference voice (XTTS requires a reference sample).

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
