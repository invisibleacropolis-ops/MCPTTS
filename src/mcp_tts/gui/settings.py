"""
TTS Settings panel for the MCP TTS GUI.

Uses extracted sub-widgets from widgets.py for a cleaner layout:
- VoiceSelector: Voice + engine selection
- ProsodyControls: Speed, pitch, volume sliders
- EmotionPicker: Emotion radios + intensity slider
"""

from collections.abc import Callable
from tkinter import filedialog

import customtkinter as ctk

from mcp_tts.gui.widgets import EmotionPicker, ProsodyControls, VoiceSelector
from mcp_tts.utils.config import VOICE_PRESETS, Config, Emotion, TTSSettings
from mcp_tts.utils.logging import get_logger

logger = get_logger("gui.settings")


class SettingsPanel(ctk.CTkFrame):
    """
    TTS settings configuration panel.

    Composes VoiceSelector, ProsodyControls, EmotionPicker and adds
    preset buttons, preview, voice cloning, and playback mode.
    """

    def __init__(
        self,
        parent,
        config: Config | None = None,
        on_settings_change: Callable[[TTSSettings], None] | None = None,
        on_preview: Callable[[str], None] | None = None,
        on_clone_voice: Callable[[str, str, str, str], None] | None = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)

        self.config = config or Config.load()
        self.on_settings_change = on_settings_change
        self.on_preview = on_preview
        self.on_clone_voice = on_clone_voice
        self._voice_capabilities: dict[str, dict] = {}

        self._setup_ui()
        self._load_settings()
        logger.debug("SettingsPanel initialized")

    def _setup_ui(self):
        """Set up the UI components using extracted sub-widgets."""
        self.grid_columnconfigure(0, weight=1)

        # Title
        ctk.CTkLabel(
            self, text="TTS Settings",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, pady=(10, 20), sticky="w", padx=15)

        row = 1

        # --- Voice & Engine Selection ---
        self.voice_selector = VoiceSelector(
            self,
            on_voice_change=self._on_voice_change,
            on_engine_change=self._on_engine_change,
        )
        self.voice_selector.grid(row=row, column=0, sticky="ew", padx=15, pady=5)
        row += 1

        # --- Prosody Controls (Speed/Pitch/Volume) ---
        self.prosody = ProsodyControls(self, on_change=self._notify_change)
        self.prosody.grid(row=row, column=0, sticky="ew", padx=15, pady=10)
        row += 1

        # --- Emotion Selection ---
        ctk.CTkLabel(
            self, text="Emotion:",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(15, 5))
        row += 1

        self.emotion_picker = EmotionPicker(
            self,
            emotions=[e.value for e in Emotion],
            on_change=self._notify_change,
        )
        self.emotion_picker.grid(row=row, column=0, sticky="ew", padx=15, pady=5)
        row += 1

        # --- Presets ---
        ctk.CTkLabel(
            self, text="Presets:",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=row, column=0, sticky="w", padx=15, pady=(15, 5))
        row += 1

        presets_frame = ctk.CTkFrame(self, fg_color="transparent")
        presets_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=5)
        for i, preset_name in enumerate(VOICE_PRESETS.keys()):
            ctk.CTkButton(
                presets_frame,
                text=preset_name.replace("_", " ").title(),
                command=lambda p=preset_name: self._apply_preset(p),
                width=100, height=28,
            ).grid(row=0, column=i, padx=3, pady=3)
        row += 1

        # --- Preview Section ---
        preview_frame = ctk.CTkFrame(self)
        preview_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=15)
        preview_frame.grid_columnconfigure(0, weight=1)

        self.preview_entry = ctk.CTkEntry(
            preview_frame, placeholder_text="Enter text to preview...",
        )
        self.preview_entry.grid(row=0, column=0, sticky="ew", padx=(10, 5), pady=10)

        self.preview_btn = ctk.CTkButton(
            preview_frame, text="🔊 Preview",
            command=self._on_preview_click, width=100,
        )
        self.preview_btn.grid(row=0, column=1, padx=(5, 10), pady=10)
        row += 1

        # --- Voice Cloning ---
        clone_frame = ctk.CTkFrame(self)
        clone_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=(0, 10))
        clone_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            clone_frame, text="Voice Cloning",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(clone_frame, text="Name:").grid(row=1, column=0, sticky="w", padx=10)
        self.clone_name_var = ctk.StringVar()
        ctk.CTkEntry(clone_frame, textvariable=self.clone_name_var).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=10,
        )

        ctk.CTkLabel(clone_frame, text="Prompt Text:").grid(row=2, column=0, sticky="w", padx=10)
        self.clone_text_var = ctk.StringVar(value="Sample")
        ctk.CTkEntry(clone_frame, textvariable=self.clone_text_var).grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=10,
        )

        ctk.CTkLabel(clone_frame, text="Language:").grid(row=3, column=0, sticky="w", padx=10)
        self.clone_language_var = ctk.StringVar(value="")
        ctk.CTkEntry(clone_frame, textvariable=self.clone_language_var).grid(
            row=3, column=1, columnspan=2, sticky="ew", padx=10,
        )

        ctk.CTkLabel(clone_frame, text="Audio:").grid(row=4, column=0, sticky="w", padx=10)
        self.clone_audio_var = ctk.StringVar()
        ctk.CTkEntry(clone_frame, textvariable=self.clone_audio_var, state="readonly").grid(
            row=4, column=1, sticky="ew", padx=10,
        )
        ctk.CTkButton(
            clone_frame, text="Browse", width=90,
            command=self._on_clone_browse,
        ).grid(row=4, column=2, padx=(0, 10))

        ctk.CTkButton(
            clone_frame, text="Clone Voice",
            command=self._on_clone_submit,
        ).grid(row=5, column=0, columnspan=3, pady=(8, 12))
        row += 1

        # --- Playback Mode ---
        mode_frame = ctk.CTkFrame(self, fg_color="transparent")
        mode_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=5)
        mode_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(mode_frame, text="Playback Mode:").grid(row=0, column=0, sticky="w")
        self.direct_playback_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            mode_frame, text="Real-time (no file)",
            variable=self.direct_playback_var,
            command=self._on_playback_mode_change,
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.mode_label = ctk.CTkLabel(
            mode_frame, text="Direct playback - fastest, no files created",
            font=ctk.CTkFont(size=11), text_color="gray",
        )
        self.mode_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        row += 1

        # --- Action Buttons ---
        buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        buttons_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=15)
        buttons_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            buttons_frame, text="Apply Settings",
            command=self._apply_settings,
            fg_color="#10B981", hover_color="#059669",
        ).grid(row=0, column=0, padx=5, sticky="ew")

        ctk.CTkButton(
            buttons_frame, text="Reset to Default",
            command=self._reset_settings,
            fg_color="#6B7280", hover_color="#4B5563",
        ).grid(row=0, column=1, padx=5, sticky="ew")

    # ------------------------------------------------------------------
    # Settings load/save
    # ------------------------------------------------------------------

    def _load_settings(self):
        """Load settings from config into sub-widgets."""
        s = self.config.tts

        self.voice_selector.voice_var.set(s.voice)
        self.voice_selector.engine_var.set(s.engine)
        self.voice_selector._update_hint()

        self.prosody.speed_var.set(s.speed)
        self.prosody.pitch_var.set(s.pitch)
        self.prosody.volume_var.set(s.volume)
        self.prosody.update_labels()

        self.emotion_picker.emotion_var.set(s.emotion.value)
        self.emotion_picker.intensity_var.set(s.emotion_intensity)
        self.emotion_picker.update_labels()
        self._apply_voice_capability(s.voice)

        self.direct_playback_var.set(self.config.audio.use_direct_playback)
        if self.config.audio.use_direct_playback:
            self.mode_label.configure(text="Direct playback - fastest, no files created")
        else:
            self.mode_label.configure(text="File-based - creates WAV, allows saving")

        logger.debug(f"Settings loaded: {s}")

    def get_current_settings(self) -> TTSSettings:
        """Get the current settings from all sub-widgets."""
        try:
            emotion = Emotion(self.emotion_picker.emotion_var.get())
        except ValueError:
            emotion = Emotion.NEUTRAL

        return TTSSettings(
            voice=self.voice_selector.voice_var.get(),
            engine=self.voice_selector.engine_var.get(),
            speed=self.prosody.speed_var.get(),
            pitch=self.prosody.pitch_var.get(),
            volume=self.prosody.volume_var.get(),
            emotion=emotion,
            emotion_intensity=self.emotion_picker.intensity_var.get(),
        )

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_voice_change(self, value: str):
        logger.debug(f"Voice changed to: {value}")
        self._apply_voice_capability(value)
        self._notify_change()

    def _on_engine_change(self, value: str):
        logger.debug(f"Engine changed to: {value}")
        self._notify_change()

    def _on_playback_mode_change(self):
        is_direct = self.direct_playback_var.get()
        if is_direct:
            self.mode_label.configure(text="Direct playback - fastest, no files created")
        else:
            self.mode_label.configure(text="File-based - creates WAV, allows saving")
        self.config.audio.use_direct_playback = is_direct
        self.config.save()
        logger.info(f"Playback mode: {'Direct' if is_direct else 'File-based'}")

    def _on_preview_click(self):
        text = self.preview_entry.get().strip()
        if not text:
            text = "Hello! This is a preview of the text to speech settings."
        if self.on_preview:
            self.on_preview(text)

    def _on_clone_browse(self):
        path = filedialog.askopenfilename(
            title="Select voice sample",
            filetypes=[("Audio Files", "*.wav *.mp3 *.flac"), ("All Files", "*.*")],
        )
        if path:
            self.clone_audio_var.set(path)

    def _on_clone_submit(self):
        if not self.on_clone_voice:
            logger.warning("Voice cloning is not available")
            return
        name = self.clone_name_var.get().strip()
        audio_path = self.clone_audio_var.get().strip()
        prompt_text = self.clone_text_var.get().strip() or "Sample"
        language = self.clone_language_var.get().strip()

        if not name or not audio_path:
            logger.warning("Voice cloning requires a name and audio file")
            return
        self.on_clone_voice(audio_path, name, prompt_text, language)

    def _apply_preset(self, preset_name: str):
        if preset_name not in VOICE_PRESETS:
            return
        preset = VOICE_PRESETS[preset_name]
        self.prosody.speed_var.set(preset.speed)
        self.prosody.pitch_var.set(preset.pitch)
        self.prosody.update_labels()
        self.emotion_picker.emotion_var.set(preset.emotion.value)
        self.emotion_picker.intensity_var.set(preset.emotion_intensity)
        self.emotion_picker.update_labels()
        logger.info(f"Applied preset: {preset_name}")
        self._notify_change()

    def _apply_settings(self):
        self.config.tts = self.get_current_settings()
        self.config.save()
        logger.info("Settings applied and saved")
        self._notify_change()

    def _reset_settings(self):
        self.config.tts = TTSSettings()
        self._load_settings()
        logger.info("Settings reset to defaults")
        self._notify_change()

    def _notify_change(self):
        if self.on_settings_change:
            self.on_settings_change(self.get_current_settings())

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def update_voices(self, voices: list[str]):
        """Update the available voices list."""
        self.voice_selector.update_voices(voices)
        self._apply_voice_capability(self.voice_selector.voice_var.get())
        logger.debug(f"Updated voices list: {len(voices)} voices")

    def update_voice_infos(self, voices: list) -> None:
        """Update voice choices and emotion capability metadata."""
        self._voice_capabilities = {voice.id: voice.to_dict() for voice in voices}
        self.update_voices([voice.id for voice in voices])

    def _apply_voice_capability(self, voice_id: str) -> None:
        capability = self._voice_capabilities.get(voice_id)
        if capability is None:
            self.emotion_picker.set_capability(
                "unavailable",
                [],
                "Voice capability has not been loaded yet.",
            )
            return

        self.emotion_picker.set_capability(
            capability.get("emotion_support", "unavailable"),
            capability.get("supported_emotions", []),
            capability.get("emotion_support_reason", ""),
        )

    def set_engine_hint(self, engine_name: str):
        """Set the engine hint label."""
        self.voice_selector.engine_hint.configure(text=f"Active: {engine_name}")

    def enable_controls(self):
        """Enable all interactive controls."""
        pass  # All controls are enabled by default

    def disable_controls(self):
        """Disable all interactive controls."""
        pass  # Placeholder for future use

    def set_error(self, message: str):
        """Set error state on the panel."""
        logger.error(f"Settings panel error: {message}")
