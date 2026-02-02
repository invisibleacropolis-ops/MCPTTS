"""
TTS Settings panel for the MCP TTS GUI.

Features:
- Voice selection with preview
- Speed/pitch sliders
- Emotion selection
- Volume control
- Settings persistence
"""

from typing import Callable, Optional
from tkinter import filedialog

import customtkinter as ctk

from mcp_tts.utils.config import Config, Emotion, TTSSettings, VOICE_PRESETS
from mcp_tts.utils.logging import get_logger

logger = get_logger("gui.settings")


class SettingsPanel(ctk.CTkFrame):
    """
    TTS settings configuration panel.

    Allows real-time modification of TTS parameters with preview capability.
    """

    def __init__(
        self,
        parent,
        config: Optional[Config] = None,
        on_settings_change: Optional[Callable[[TTSSettings], None]] = None,
        on_preview: Optional[Callable[[str], None]] = None,
        on_clone_voice: Optional[Callable[[str, str, str, str], None]] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)

        self.config = config or Config.load()
        self.on_settings_change = on_settings_change
        self.on_preview = on_preview
        self.on_clone_voice = on_clone_voice

        self._setup_ui()
        self._load_settings()
        logger.debug("SettingsPanel initialized")

    def _setup_ui(self):
        """Set up the UI components."""
        self.grid_columnconfigure(0, weight=1)

        # Title
        title = ctk.CTkLabel(
            self,
            text="TTS Settings",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.grid(row=0, column=0, pady=(10, 20), sticky="w", padx=15)

        row = 1

        # --- Voice Selection ---
        voice_frame = ctk.CTkFrame(self, fg_color="transparent")
        voice_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=5)
        voice_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(voice_frame, text="Voice:").grid(row=0, column=0, sticky="w")

        self.voice_var = ctk.StringVar()
        self.voice_menu = ctk.CTkOptionMenu(
            voice_frame,
            values=["en_US-amy-medium", "en_US-joe-medium", "en_GB-alan-medium"],
            variable=self.voice_var,
            command=self._on_voice_change,
        )
        self.voice_menu.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        row += 1

        # --- Engine Selection ---
        engine_frame = ctk.CTkFrame(self, fg_color="transparent")
        engine_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=5)
        engine_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(engine_frame, text="Engine:").grid(row=0, column=0, sticky="w")

        self.engine_var = ctk.StringVar()
        self.engine_menu = ctk.CTkOptionMenu(
            engine_frame,
            values=["auto", "edge", "piper", "system"],
            variable=self.engine_var,
            command=self._on_engine_change,
        )
        self.engine_menu.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        self.engine_hint = ctk.CTkLabel(
            engine_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.engine_hint.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        row += 1

        # --- Speed Slider ---
        speed_frame = ctk.CTkFrame(self, fg_color="transparent")
        speed_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=10)
        speed_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(speed_frame, text="Speed:").grid(row=0, column=0, sticky="w")

        self.speed_label = ctk.CTkLabel(speed_frame, text="1.0x", width=50)
        self.speed_label.grid(row=0, column=2, padx=(10, 0))

        self.speed_var = ctk.DoubleVar(value=1.0)
        self.speed_slider = ctk.CTkSlider(
            speed_frame,
            from_=0.5,
            to=2.0,
            variable=self.speed_var,
            command=self._on_speed_change,
        )
        self.speed_slider.grid(row=0, column=1, sticky="ew", padx=10)
        row += 1

        # --- Pitch Slider ---
        pitch_frame = ctk.CTkFrame(self, fg_color="transparent")
        pitch_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=10)
        pitch_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(pitch_frame, text="Pitch:").grid(row=0, column=0, sticky="w")

        self.pitch_label = ctk.CTkLabel(pitch_frame, text="0.0", width=50)
        self.pitch_label.grid(row=0, column=2, padx=(10, 0))

        self.pitch_var = ctk.DoubleVar(value=0.0)
        self.pitch_slider = ctk.CTkSlider(
            pitch_frame,
            from_=-1.0,
            to=1.0,
            variable=self.pitch_var,
            command=self._on_pitch_change,
        )
        self.pitch_slider.grid(row=0, column=1, sticky="ew", padx=10)
        row += 1

        # --- Volume Slider ---
        volume_frame = ctk.CTkFrame(self, fg_color="transparent")
        volume_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=10)
        volume_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(volume_frame, text="Volume:").grid(row=0, column=0, sticky="w")

        self.volume_label = ctk.CTkLabel(volume_frame, text="100%", width=50)
        self.volume_label.grid(row=0, column=2, padx=(10, 0))

        self.volume_var = ctk.DoubleVar(value=1.0)
        self.volume_slider = ctk.CTkSlider(
            volume_frame,
            from_=0.0,
            to=1.0,
            variable=self.volume_var,
            command=self._on_volume_change,
        )
        self.volume_slider.grid(row=0, column=1, sticky="ew", padx=10)
        row += 1

        # --- Emotion Selection ---
        emotion_label = ctk.CTkLabel(
            self,
            text="Emotion:",
            font=ctk.CTkFont(weight="bold"),
        )
        emotion_label.grid(row=row, column=0, sticky="w", padx=15, pady=(15, 5))
        row += 1

        emotion_frame = ctk.CTkFrame(self, fg_color="transparent")
        emotion_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=5)

        self.emotion_var = ctk.StringVar(value="neutral")

        emotions = [e.value for e in Emotion]
        for i, emotion in enumerate(emotions):
            rb = ctk.CTkRadioButton(
                emotion_frame,
                text=emotion.title(),
                variable=self.emotion_var,
                value=emotion,
                command=self._on_emotion_change,
            )
            rb.grid(row=i // 4, column=i % 4, padx=5, pady=3, sticky="w")
        row += 1

        # --- Emotion Intensity ---
        intensity_frame = ctk.CTkFrame(self, fg_color="transparent")
        intensity_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=10)
        intensity_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(intensity_frame, text="Intensity:").grid(row=0, column=0, sticky="w")

        self.intensity_label = ctk.CTkLabel(intensity_frame, text="50%", width=50)
        self.intensity_label.grid(row=0, column=2, padx=(10, 0))

        self.intensity_var = ctk.DoubleVar(value=0.5)
        self.intensity_slider = ctk.CTkSlider(
            intensity_frame,
            from_=0.0,
            to=1.0,
            variable=self.intensity_var,
            command=self._on_intensity_change,
        )
        self.intensity_slider.grid(row=0, column=1, sticky="ew", padx=10)
        row += 1

        # --- Presets ---
        presets_label = ctk.CTkLabel(
            self,
            text="Presets:",
            font=ctk.CTkFont(weight="bold"),
        )
        presets_label.grid(row=row, column=0, sticky="w", padx=15, pady=(15, 5))
        row += 1

        presets_frame = ctk.CTkFrame(self, fg_color="transparent")
        presets_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=5)

        for i, preset_name in enumerate(VOICE_PRESETS.keys()):
            btn = ctk.CTkButton(
                presets_frame,
                text=preset_name.replace("_", " ").title(),
                command=lambda p=preset_name: self._apply_preset(p),
                width=100,
                height=28,
            )
            btn.grid(row=0, column=i, padx=3, pady=3)
        row += 1

        # --- Preview Section ---
        preview_frame = ctk.CTkFrame(self)
        preview_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=15)
        preview_frame.grid_columnconfigure(0, weight=1)

        self.preview_entry = ctk.CTkEntry(
            preview_frame,
            placeholder_text="Enter text to preview...",
        )
        self.preview_entry.grid(row=0, column=0, sticky="ew", padx=(10, 5), pady=10)

        self.preview_btn = ctk.CTkButton(
            preview_frame,
            text="🔊 Preview",
            command=self._on_preview_click,
            width=100,
        )
        self.preview_btn.grid(row=0, column=1, padx=(5, 10), pady=10)
        row += 1

        # --- Voice Cloning ---
        clone_frame = ctk.CTkFrame(self)
        clone_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=(0, 10))
        clone_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            clone_frame,
            text="Voice Cloning",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(clone_frame, text="Name:").grid(row=1, column=0, sticky="w", padx=10)
        self.clone_name_var = ctk.StringVar()
        self.clone_name_entry = ctk.CTkEntry(clone_frame, textvariable=self.clone_name_var)
        self.clone_name_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=10)

        ctk.CTkLabel(clone_frame, text="Prompt Text:").grid(row=2, column=0, sticky="w", padx=10)
        self.clone_text_var = ctk.StringVar(value="Sample")
        self.clone_text_entry = ctk.CTkEntry(clone_frame, textvariable=self.clone_text_var)
        self.clone_text_entry.grid(row=2, column=1, columnspan=2, sticky="ew", padx=10)

        ctk.CTkLabel(clone_frame, text="Language:").grid(row=3, column=0, sticky="w", padx=10)
        self.clone_language_var = ctk.StringVar(value="")
        self.clone_language_entry = ctk.CTkEntry(clone_frame, textvariable=self.clone_language_var)
        self.clone_language_entry.grid(row=3, column=1, columnspan=2, sticky="ew", padx=10)

        ctk.CTkLabel(clone_frame, text="Audio:").grid(row=4, column=0, sticky="w", padx=10)
        self.clone_audio_var = ctk.StringVar()
        self.clone_audio_entry = ctk.CTkEntry(
            clone_frame, textvariable=self.clone_audio_var, state="readonly"
        )
        self.clone_audio_entry.grid(row=4, column=1, sticky="ew", padx=10)

        self.clone_browse_btn = ctk.CTkButton(
            clone_frame,
            text="Browse",
            width=90,
            command=self._on_clone_browse,
        )
        self.clone_browse_btn.grid(row=4, column=2, padx=(0, 10))

        self.clone_submit_btn = ctk.CTkButton(
            clone_frame,
            text="Clone Voice",
            command=self._on_clone_submit,
        )
        self.clone_submit_btn.grid(row=5, column=0, columnspan=3, pady=(8, 12))
        row += 1

        # --- Playback Mode ---
        mode_frame = ctk.CTkFrame(self, fg_color="transparent")
        mode_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=5)
        mode_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(mode_frame, text="Playback Mode:").grid(row=0, column=0, sticky="w")

        self.direct_playback_var = ctk.BooleanVar(value=True)
        self.direct_playback_switch = ctk.CTkSwitch(
            mode_frame,
            text="Real-time (no file)",
            variable=self.direct_playback_var,
            command=self._on_playback_mode_change,
        )
        self.direct_playback_switch.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.mode_label = ctk.CTkLabel(
            mode_frame,
            text="Direct playback - fastest, no files created",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.mode_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        row += 1

        # --- Action Buttons ---
        buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        buttons_frame.grid(row=row, column=0, sticky="ew", padx=15, pady=15)
        buttons_frame.grid_columnconfigure((0, 1), weight=1)

        self.apply_btn = ctk.CTkButton(
            buttons_frame,
            text="Apply Settings",
            command=self._apply_settings,
            fg_color="#10B981",
            hover_color="#059669",
        )
        self.apply_btn.grid(row=0, column=0, padx=5, sticky="ew")

        self.reset_btn = ctk.CTkButton(
            buttons_frame,
            text="Reset to Default",
            command=self._reset_settings,
            fg_color="#6B7280",
            hover_color="#4B5563",
        )
        self.reset_btn.grid(row=0, column=1, padx=5, sticky="ew")

    def _load_settings(self):
        """Load settings from config."""
        settings = self.config.tts

        self.voice_var.set(settings.voice)
        self.engine_var.set(settings.engine)
        self.speed_var.set(settings.speed)
        self.pitch_var.set(settings.pitch)
        self.volume_var.set(settings.volume)
        self.emotion_var.set(settings.emotion.value)
        self.intensity_var.set(settings.emotion_intensity)

        # Load playback mode from audio config
        self.direct_playback_var.set(self.config.audio.use_direct_playback)
        if self.config.audio.use_direct_playback:
            self.mode_label.configure(text="Direct playback - fastest, no files created")
        else:
            self.mode_label.configure(text="File-based - creates WAV, allows saving")

        # Update labels
        self._update_labels()
        self._update_engine_hint()

        logger.debug(f"Settings loaded: {settings}")

    def _update_labels(self):
        """Update slider value labels."""
        self.speed_label.configure(text=f"{self.speed_var.get():.1f}x")
        self.pitch_label.configure(text=f"{self.pitch_var.get():+.1f}")
        self.volume_label.configure(text=f"{int(self.volume_var.get() * 100)}%")
        self.intensity_label.configure(text=f"{int(self.intensity_var.get() * 100)}%")

    def _update_engine_hint(self) -> None:
        descriptions = {
            "auto": "Auto-select based on task and VRAM",
            "fish": "Best quality, multilingual, needs API server",
            "xtts": "Voice cloning specialist, local model",
            "piper": "Fast, lightweight, GPU optional",
            "system": "Basic fallback, CPU only",
        }
        self.engine_hint.configure(text=descriptions.get(self.engine_var.get(), ""))

    def _on_voice_change(self, value: str):
        """Handle voice selection change."""
        logger.debug(f"Voice changed to: {value}")
        self._notify_change()

    def _on_engine_change(self, value: str):
        """Handle engine selection change."""
        logger.debug(f"Engine changed to: {value}")
        self._update_engine_hint()
        self._notify_change()

    def _on_speed_change(self, value: float):
        """Handle speed slider change."""
        self.speed_label.configure(text=f"{value:.1f}x")
        self._notify_change()

    def _on_pitch_change(self, value: float):
        """Handle pitch slider change."""
        self.pitch_label.configure(text=f"{value:+.1f}")
        self._notify_change()

    def _on_volume_change(self, value: float):
        """Handle volume slider change."""
        self.volume_label.configure(text=f"{int(value * 100)}%")
        self._notify_change()

    def _on_emotion_change(self):
        """Handle emotion selection change."""
        logger.debug(f"Emotion changed to: {self.emotion_var.get()}")
        self._notify_change()

    def _on_intensity_change(self, value: float):
        """Handle intensity slider change."""
        self.intensity_label.configure(text=f"{int(value * 100)}%")
        self._notify_change()

    def _on_playback_mode_change(self):
        """Handle playback mode toggle."""
        is_direct = self.direct_playback_var.get()
        if is_direct:
            self.mode_label.configure(text="Direct playback - fastest, no files created")
        else:
            self.mode_label.configure(text="File-based - creates WAV, allows saving")

        # Update config immediately
        self.config.audio.use_direct_playback = is_direct
        self.config.save()
        logger.info(f"Playback mode changed to: {'Direct' if is_direct else 'File-based'}")

    def _on_preview_click(self):
        """Handle preview button click."""
        text = self.preview_entry.get().strip()
        if not text:
            text = "Hello! This is a preview of the text to speech settings."

        if self.on_preview:
            self.on_preview(text)
        else:
            logger.info(f"Preview requested: {text}")

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
        """Apply a voice preset."""
        if preset_name not in VOICE_PRESETS:
            logger.warning(f"Unknown preset: {preset_name}")
            return

        preset = VOICE_PRESETS[preset_name]

        self.speed_var.set(preset.speed)
        self.pitch_var.set(preset.pitch)
        self.emotion_var.set(preset.emotion.value)
        self.intensity_var.set(preset.emotion_intensity)

        self._update_labels()
        logger.info(f"Applied preset: {preset_name}")
        self._notify_change()

    def _apply_settings(self):
        """Apply current settings to config and save."""
        self.config.tts = self.get_current_settings()
        self.config.save()
        logger.info("Settings applied and saved")
        self._notify_change()

    def _reset_settings(self):
        """Reset to default settings."""
        self.config.tts = TTSSettings()
        self._load_settings()
        logger.info("Settings reset to defaults")
        self._notify_change()

    def _notify_change(self):
        """Notify callback of settings change."""
        if self.on_settings_change:
            settings = self.get_current_settings()
            self.on_settings_change(settings)

    def get_current_settings(self) -> TTSSettings:
        """Get the current settings from UI."""
        try:
            emotion = Emotion(self.emotion_var.get())
        except ValueError:
            emotion = Emotion.NEUTRAL

        return TTSSettings(
            voice=self.voice_var.get(),
            engine=self.engine_var.get(),
            speed=self.speed_var.get(),
            pitch=self.pitch_var.get(),
            volume=self.volume_var.get(),
            emotion=emotion,
            emotion_intensity=self.intensity_var.get(),
        )

    def update_voices(self, voices: list[str]):
        """Update the available voices list."""
        if not voices:
            self.voice_menu.configure(values=["No voices available"])
            self.voice_var.set("No voices available")
            return

        self.voice_menu.configure(values=voices)
        
        # Check if current selection is valid
        current = self.voice_var.get()
        if current not in voices:
            self.voice_var.set(voices[0])
            self._on_voice_change(voices[0])
            
        logger.debug(f"Updated voices list: {len(voices)} voices")
