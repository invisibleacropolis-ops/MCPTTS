---
name: mcp-tts
description: How to use the MCP TTS Server tools to synthesize, play, and manage text-to-speech audio
---

# MCP TTS Server — Agent Skill Guide

This skill teaches you how to fluently use the **MCP TTS Server** to convert text to speech, manage voices, check emotion availability, and handle audio output. The server exposes its capabilities as MCP tools and resources.

---

## Quick Start

```
# Check the server is alive (lightweight, no engine init)
health_check()

# Speak immediately with defaults
speak_text(text="Hello, world!")

# Speak with full control
speak_text(
    text="Welcome back, Commander.",
    voice="en_US-amy-medium",
    speed=0.95,
    emotion="calm",
    emotion_intensity=0.7,
    auto_play=True
)
```

---

## Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│  MCP Client  │────▶│  MCP Server  │────▶│  Engine Manager   │
│ (you, agent) │     │  (FastMCP)   │     │  (fallback chain) │
└─────────────┘     └──────────────┘     └────┬────┬────┬────┘
                                              │    │    │
                                         Edge  Piper System
                                        (cloud)(local)(SAPI)
```

### Engine Priority & Fallback

The engine manager tries engines in priority order. If one fails, it falls through:

| Priority | Engine   | Type   | Quality   | Requires         |
|----------|----------|--------|-----------|------------------|
| 1        | `edge`   | Cloud  | Highest   | Internet access  |
| 2        | `piper`  | Local  | High      | Piper models     |
| 3        | `system` | Local  | Basic     | pyttsx3 (always) |

You generally do **not** need to specify an engine — the manager picks the best available one automatically. Use `engine="piper"` or `engine="system"` only when you have a specific reason (e.g., offline use, low latency).

---

## Tool Reference

### Core Synthesis

#### `speak_text` — The primary tool. Converts text to audio and optionally plays it.

| Parameter           | Type    | Default     | Range / Values                                       |
|---------------------|---------|-------------|------------------------------------------------------|
| `text`              | string  | **required**| The text to speak                                    |
| `voice`             | string  | current     | Voice ID (see voice list below)                      |
| `engine`            | string  | auto        | `edge`, `piper`, `system`, or omit for auto          |
| `task`              | string  | None        | `"quality"` or `"fast"` routing hint                 |
| `speed`             | float   | 1.0         | 0.5 (half) – 2.0 (double)                            |
| `pitch`             | float   | 0.0         | -1.0 (lower) – 1.0 (higher)                          |
| `emotion`           | string  | `"neutral"` | See Emotions table below                             |
| `emotion_intensity` | float   | 0.5         | 0.0 (subtle) – 1.0 (extreme)                         |
| `auto_play`         | bool    | true        | Play through speakers immediately                    |
| `save_to_file`      | bool    | false       | Save a WAV file to the output directory              |
| `streaming`         | bool    | false       | Chunk-by-chunk synthesis for long text               |
| `chunk_size`        | int     | 220         | Max chars per chunk (min 80), only used if streaming |

**When to use `streaming=True`:** For text longer than ~500 characters. The user hears the first chunk sooner while later chunks are still synthesizing.

**When to use `save_to_file=True`:** When the user needs a permanent audio file (e.g., for a podcast, voiceover, or further processing).

**Returns:** A dict with `status`, `duration_seconds`, `voice_id`, `sample_rate`, `played` (bool), and `saved_path` (if saved).

---

### Voice Management

#### `list_voices` — Discover available voices

```
list_voices()               # All voices for the current engine
list_voices(engine="piper")  # Only Piper voices
```

Returns a list of voice objects, each with: `id`, `name`, `language`, `gender`, `sample_rate`, `emotion_support`, `emotion_support_reason`, `supports_emotions`, `supported_emotions`.

#### `set_voice` — Change the default voice for all subsequent calls

```
set_voice(voice="en_US-lessac-high")
```

> [!TIP]
> You don't need to call `set_voice` if you pass `voice=` directly to `speak_text`. Use `set_voice` when you want to change the default for an ongoing conversation.

#### `clone_voice` — Add a custom voice from a reference audio file

```
clone_voice(
    audio_path="C:/path/to/reference.wav",
    name="custom_narrator",
    prompt_text="The transcript of the reference audio",
    language="en"
)
```

> [!IMPORTANT]
> Voice cloning requires an engine that supports it. Not all engines do — check the return value for errors. The reference audio should be a clear, clean recording.

---

### Emotion Control

#### `set_emotion` — Set the default emotion for all subsequent calls when available

```
set_emotion(emotion="excited", intensity=0.8)
```

Emotion support is voice/engine dependent. Check `list_voices()` or `get_status()` first:

| `emotion_support` | Meaning |
|-------------------|---------|
| `native` | The engine has real emotion/style controls |
| `simulated` | The engine simulates emotion with rate/pitch/prosody |
| `unavailable` | Non-neutral emotions are disabled/rejected |

#### Emotions Reference

| Emotion      | Effect                                        | Best For                          |
|--------------|-----------------------------------------------|-----------------------------------|
| `neutral`    | Normal, balanced speech                       | Default / informational           |
| `happy`      | Cheerful, upbeat, higher pitch                | Good news, greetings              |
| `sad`        | Slower, lower-pitched, melancholic            | Empathy, bad news                 |
| `angry`      | Intense, faster, emphatic                     | Urgency, warnings                 |
| `excited`    | Enthusiastic, fast, high-energy               | Celebrations, announcements       |
| `calm`       | Relaxed, slower, soothing                     | Instructions, bedtime stories     |
| `fearful`    | Tense, slightly faster, uncertain             | Suspense, caution                 |
| `surprised`  | Quick, higher-pitched, exclamatory            | Reactions, revelations            |

> [!TIP]
> Current engines report simulated or unavailable emotion support. Intensity controls how strongly simulated rate/pitch effects are applied — start with 0.5 and adjust.

---

### Configuration

#### `configure_tts` — Adjust global settings without switching tools

```
configure_tts(speed=1.1, pitch=0.1, volume=0.8, auto_play=True)
```

All parameters are optional. Only the ones you pass are updated.

| Parameter   | Type  | Range           |
|-------------|-------|-----------------|
| `engine`    | str   | `edge`/`piper`/`system` |
| `speed`     | float | 0.5 – 2.0      |
| `pitch`     | float | -1.0 – 1.0     |
| `volume`    | float | 0.0 – 1.0      |
| `auto_play` | bool  | true/false      |

#### `reload_config` — Reload settings from `~/.mcp-tts/config.json`

Use after the user manually edits the config file on disk.

---

### Diagnostics

#### `health_check` — Lightweight server health probe

Does **not** trigger engine initialization. Use this to verify the server is running before doing anything else.

**Returns:** `status`, `python_version`, `server_initialized`, `engines_loaded`, `dependencies`.

#### `get_status` — Full engine status and current settings

Use to inspect what engine is loaded, its current voice, speed, pitch, emotion, etc.

#### `get_gpu_status` — GPU/VRAM diagnostics

Returns CUDA availability, GPU name, total/used/available VRAM. Useful for deciding whether to use GPU-accelerated features.

---

## MCP Resources (Read-Only)

These are queryable via `read_resource`:

| URI              | Returns                                   |
|------------------|-------------------------------------------|
| `tts://voices`   | JSON array of all available voice models  |
| `tts://settings` | Current TTS configuration as JSON         |
| `tts://emotions` | Current voice emotion capability and emotion descriptions |

---

## Available Voices

Voice IDs follow the pattern: `{language}-{name}-{quality}`.

| Voice ID                              | Name                     | Language | Quality |
|---------------------------------------|--------------------------|----------|---------|
| `en_US-amy-medium`                    | Amy                      | en_US    | Medium  |
| `en_US-joe-medium`                    | Joe                      | en_US    | Medium  |
| `en_US-ryan-medium`                   | Ryan                     | en_US    | Medium  |
| `en_US-lessac-high`                   | Lessac                   | en_US    | High    |
| `en_US-libritts_r-medium`             | LibriTTS-R               | en_US    | Medium  |
| `en_GB-alan-medium`                   | Alan                     | en_GB    | Medium  |
| `en_GB-southern_english_female-low`   | Southern English Female  | en_GB    | Low     |

> [!NOTE]
> The voice list depends on which models are downloaded into `~/.mcp-tts/models/`. More Piper voices can be added by downloading `.onnx` model files from the [Piper voices repository](https://huggingface.co/rhasspy/piper-voices).

---

## Recommended Presets

Use these parameter combinations for common scenarios:

### Calm Assistant
```
speak_text(text="...", speed=0.95, emotion="calm", emotion_intensity=0.5)
```

### Fast Narrator
```
speak_text(text="...", speed=1.4, pitch=0.1, emotion="neutral")
```

### Slow Storyteller
```
speak_text(text="...", speed=0.8, pitch=-0.1, emotion="calm", emotion_intensity=0.7)
```

### Excited Announcer
```
speak_text(text="...", speed=1.2, pitch=0.2, emotion="excited", emotion_intensity=0.8)
```

---

## Best Practices

### 1. Always health-check first
Before any synthesis in a new session, call `health_check()` to verify the server is alive. This is instant and avoids confusing errors.

### 2. Omit parameters you don't need
Every parameter in `speak_text` has a sensible default. Don't pass `engine`, `speed`, `pitch`, etc. unless you actively want to change them. Less is more.

### 3. Use streaming for long text
For anything over ~500 characters, set `streaming=True`. The user hears audio sooner and the experience feels more responsive.

### 4. Match emotion to context when available
When reading the user's text aloud, first check that the selected voice reports `native` or `simulated` emotion support. Then pick an emotion that matches the content:
- Error messages → `"calm"` or `"neutral"` (not `"angry"`)
- Good results → `"happy"` at low intensity (0.3–0.5)
- Stories/narrative → vary between `"calm"`, `"excited"`, `"surprised"` per passage

### 5. Don't over-modulate
Keep emotion intensity at 0.3–0.6 for natural-sounding speech. Values above 0.8 sound exaggerated and are only appropriate for dramatic effect.

### 6. Prefer `auto_play=True`
Unless the user explicitly asks for a file or silent synthesis, always auto-play. The point of TTS is to hear it.

### 7. Save files only when asked
Set `save_to_file=True` only when the user wants to keep the audio. Files are saved to `~/.mcp-tts/output/`.

### 8. Check errors in return values
Every tool returns a `status` field. Check for `"success"`, `"error"`, or `"warning"` and act accordingly.

---

## Common Patterns

### Read a code explanation aloud
```
speak_text(
    text="The function iterates over each element and applies the transformation.",
    speed=0.9,
    emotion="calm"
)
```

### Announce a task completion
```
speak_text(
    text="Build complete. All 47 tests passed.",
    emotion="happy",
    emotion_intensity=0.4
)
```

### Read a long document with streaming
```
speak_text(
    text=long_document_text,
    streaming=True,
    chunk_size=200,
    speed=1.1,
    voice="en_US-lessac-high"
)
```

### Silent synthesis to file
```
speak_text(
    text="This will be saved but not played.",
    auto_play=False,
    save_to_file=True
)
```

### Switch voice mid-conversation
```
set_voice(voice="en_GB-alan-medium")
speak_text(text="Now speaking with a British accent.")
```

---

## Troubleshooting

| Symptom                        | Check                                               |
|--------------------------------|------------------------------------------------------|
| Server not responding          | `health_check()` — is the process running?           |
| No audio output                | `get_status()` — check `auto_play` and `volume`      |
| Wrong voice                    | `list_voices()` — verify the voice ID exists         |
| Engine failed to load          | Check logs — may need internet (Edge) or models (Piper) |
| Slow first synthesis           | Normal — engine loads on first use. Subsequent calls are fast. |
| GPU not detected               | `get_gpu_status()` — CUDA/torch may not be installed |

---

## Configuration File

The server reads `~/.mcp-tts/config.json` on startup. Key sections:

```json
{
  "tts": {
    "voice": "en_US-amy-medium",
    "engine": "auto",
    "speed": 1.0,
    "pitch": 0.0,
    "emotion": "neutral",
    "emotion_intensity": 0.5,
    "volume": 1.0
  },
  "audio": {
    "auto_play": true,
    "sample_rate": 22050,
    "normalize_audio": true,
    "effects_enabled": false
  },
  "server": {
    "transport": "stdio",
    "port": 8000
  }
}
```

After editing this file, call `reload_config()` to apply changes without restarting.

---

## Environment Variables

| Variable          | Effect                                    |
|-------------------|-------------------------------------------|
| `MCP_TTS_ENGINE`  | Override default engine (`edge`/`piper`/`system`) |
