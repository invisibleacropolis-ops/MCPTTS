"""
Reusable GUI widgets for MCP TTS.

- ToastBar: Slide-in notification bar (error/warning/success/info)
- StatusIndicator: Shows current activity (idle/synthesizing/playing/loading)
- EngineStatusPanel: Engine availability badges
- VoiceSelector: Voice + engine dropdown
- ProsodyControls: Speed/pitch/volume sliders
- EmotionPicker: Emotion radios + intensity slider
"""

from collections.abc import Callable

import customtkinter as ctk

from mcp_tts.utils.logging import get_logger

logger = get_logger("gui.widgets")


# ==========================================================================
# Toast Notification Bar (Item 9)
# ==========================================================================


class ToastBar(ctk.CTkFrame):
    """
    Bottom-anchored notification bar with auto-dismiss.

    Usage:
        toast = ToastBar(root)
        toast.show_error("Synthesis failed!")
        toast.show_success("Audio saved to disk")
    """

    # Color presets per level
    _COLORS = {
        "error":   {"bg": "#7F1D1D", "fg": "#FCA5A5", "icon": "✕"},
        "warning": {"bg": "#78350F", "fg": "#FDE68A", "icon": "⚠"},
        "success": {"bg": "#064E3B", "fg": "#6EE7B7", "icon": "✓"},
        "info":    {"bg": "#1E3A5F", "fg": "#93C5FD", "icon": "ℹ"},
    }

    def __init__(self, parent, dismiss_ms: int = 5000, **kwargs):
        super().__init__(parent, height=0, **kwargs)
        self._parent = parent
        self._dismiss_ms = dismiss_ms
        self._dismiss_job: str | None = None
        self._visible = False

        self.grid_columnconfigure(1, weight=1)

        # Icon
        self._icon_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=16, weight="bold"), width=28,
        )
        self._icon_label.grid(row=0, column=0, padx=(12, 4), pady=8)

        # Message
        self._msg_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=13), anchor="w",
        )
        self._msg_label.grid(row=0, column=1, sticky="ew", padx=4, pady=8)

        # Dismiss button
        self._close_btn = ctk.CTkButton(
            self, text="✕", width=28, height=28,
            fg_color="transparent", hover_color="#374151",
            command=self.dismiss,
        )
        self._close_btn.grid(row=0, column=2, padx=(4, 8), pady=8)

        # Start hidden
        self.grid_remove()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_error(self, msg: str) -> None:
        self._show("error", msg)

    def show_warning(self, msg: str) -> None:
        self._show("warning", msg)

    def show_success(self, msg: str) -> None:
        self._show("success", msg)

    def show_info(self, msg: str) -> None:
        self._show("info", msg)

    def dismiss(self) -> None:
        if self._dismiss_job:
            self.after_cancel(self._dismiss_job)
            self._dismiss_job = None
        self.grid_remove()
        self._visible = False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _show(self, level: str, msg: str) -> None:
        colors = self._COLORS.get(level, self._COLORS["info"])

        self.configure(fg_color=colors["bg"])
        self._icon_label.configure(text=colors["icon"], text_color=colors["fg"])
        self._msg_label.configure(text=msg, text_color=colors["fg"])

        # Cancel previous auto-dismiss
        if self._dismiss_job:
            self.after_cancel(self._dismiss_job)

        # Show
        self.grid()
        self._visible = True

        # Auto-dismiss
        self._dismiss_job = self.after(self._dismiss_ms, self.dismiss)


# ==========================================================================
# Status Indicator (Item 10)
# ==========================================================================


class StatusIndicator(ctk.CTkFrame):
    """
    Compact activity indicator: idle / synthesizing / playing / loading.

    Shows a colored dot + text label. The animation is tick-based via
    after() so it never blocks.
    """

    _STATES = {
        "idle":          {"color": "#6B7280", "text": "Idle"},
        "loading":       {"color": "#F59E0B", "text": "Loading engine…"},
        "synthesizing":  {"color": "#3B82F6", "text": "Synthesizing…"},
        "playing":       {"color": "#10B981", "text": "Playing audio…"},
        "error":         {"color": "#EF4444", "text": "Error"},
    }

    def __init__(self, parent, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(parent, **kwargs)

        self._state = "idle"
        self._anim_frame = 0
        self._anim_job: str | None = None

        self._dot = ctk.CTkLabel(
            self, text="●", font=ctk.CTkFont(size=12),
            text_color="#6B7280", width=20,
        )
        self._dot.pack(side="left", padx=(0, 6))

        self._label = ctk.CTkLabel(
            self, text="Idle",
            font=ctk.CTkFont(size=12),
            text_color="#9CA3AF",
        )
        self._label.pack(side="left")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_state(self, state: str, detail: str = "") -> None:
        """Set the indicator state. ``detail`` overrides default text."""
        cfg = self._STATES.get(state, self._STATES["idle"])
        self._state = state

        text = detail or cfg["text"]
        self._dot.configure(text_color=cfg["color"])
        self._label.configure(text=text, text_color=cfg["color"])

        # Start/stop animation
        if state in ("synthesizing", "loading", "playing"):
            self._start_anim()
        else:
            self._stop_anim()

    # ------------------------------------------------------------------
    # Animation
    # ------------------------------------------------------------------

    def _start_anim(self) -> None:
        if self._anim_job is not None:
            return
        self._anim_frame = 0
        self._tick_anim()

    def _stop_anim(self) -> None:
        if self._anim_job is not None:
            self.after_cancel(self._anim_job)
            self._anim_job = None
        self._dot.configure(text="●")

    def _tick_anim(self) -> None:
        frames = ["●", "◉", "○", "◉"]
        self._dot.configure(text=frames[self._anim_frame % len(frames)])
        self._anim_frame += 1
        self._anim_job = self.after(350, self._tick_anim)


# ==========================================================================
# Engine Status Panel (Item 11)
# ==========================================================================


class EngineStatusPanel(ctk.CTkFrame):
    """
    Shows engine availability with colored badges.

    🟢 loaded  🟡 loading  ⚪ available  🔴 unavailable
    """

    _BADGE = {
        "loaded":      ("🟢", "#10B981"),
        "loading":     ("🟡", "#F59E0B"),
        "available":   ("⚪", "#6B7280"),
        "unavailable": ("🔴", "#EF4444"),
    }

    ENGINE_NAMES = {
        "edge":   "Edge TTS",
        "piper":  "Piper",
        "system": "System",
    }

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="Engines",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(6, 4))

        self._rows: dict[str, ctk.CTkLabel] = {}
        for i, (key, name) in enumerate(self.ENGINE_NAMES.items(), start=1):
            lbl = ctk.CTkLabel(
                self, text=f"⚪ {name}",
                font=ctk.CTkFont(size=12),
                text_color="#6B7280",
                anchor="w",
            )
            lbl.grid(row=i, column=0, sticky="w", padx=14, pady=1)
            self._rows[key] = lbl

    def update_engines(self, loaded: list[str]) -> None:
        """Update badges from a list of loaded engine keys."""
        for key, lbl in self._rows.items():
            name = self.ENGINE_NAMES[key]
            if key in loaded:
                badge, color = self._BADGE["loaded"]
            else:
                badge, color = self._BADGE["available"]
            lbl.configure(text=f"{badge} {name}", text_color=color)


# ==========================================================================
# Voice Selector (Item 12 — settings sub-widget)
# ==========================================================================


class VoiceSelector(ctk.CTkFrame):
    """Voice + engine selection combo."""

    def __init__(
        self,
        parent,
        on_voice_change: Callable[[str], None] | None = None,
        on_engine_change: Callable[[str], None] | None = None,
        **kwargs,
    ):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(parent, **kwargs)
        self.grid_columnconfigure(1, weight=1)

        self._on_voice_change = on_voice_change
        self._on_engine_change = on_engine_change

        # Voice
        ctk.CTkLabel(self, text="Voice:").grid(row=0, column=0, sticky="w")
        self.voice_var = ctk.StringVar()
        self.voice_menu = ctk.CTkOptionMenu(
            self,
            values=["en_US-amy-medium", "en_US-joe-medium", "en_GB-alan-medium"],
            variable=self.voice_var,
            command=self._voice_changed,
        )
        self.voice_menu.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        # Engine
        ctk.CTkLabel(self, text="Engine:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.engine_var = ctk.StringVar()
        self.engine_menu = ctk.CTkOptionMenu(
            self,
            values=["auto", "edge", "piper", "system"],
            variable=self.engine_var,
            command=self._engine_changed,
        )
        self.engine_menu.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(8, 0))

        self.engine_hint = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11), text_color="gray",
        )
        self.engine_hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

    def _voice_changed(self, value: str) -> None:
        if self._on_voice_change:
            self._on_voice_change(value)

    def _engine_changed(self, value: str) -> None:
        self._update_hint()
        if self._on_engine_change:
            self._on_engine_change(value)

    def _update_hint(self) -> None:
        descriptions = {
            "auto":   "Auto-select best available engine",
            "edge":   "High-quality neural TTS (cloud, no API key)",
            "piper":  "Fast, lightweight, GPU optional",
            "system": "Basic fallback, CPU only",
        }
        self.engine_hint.configure(text=descriptions.get(self.engine_var.get(), ""))

    def update_voices(self, voices: list[str]) -> None:
        if not voices:
            self.voice_menu.configure(values=["No voices available"])
            self.voice_var.set("No voices available")
            return
        self.voice_menu.configure(values=voices)
        if self.voice_var.get() not in voices:
            self.voice_var.set(voices[0])


# ==========================================================================
# Prosody Controls (Item 12 — settings sub-widget)
# ==========================================================================


class ProsodyControls(ctk.CTkFrame):
    """Speed / pitch / volume sliders with value labels."""

    def __init__(
        self,
        parent,
        on_change: Callable[[], None] | None = None,
        **kwargs,
    ):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(parent, **kwargs)
        self.grid_columnconfigure(1, weight=1)
        self._on_change = on_change

        # Speed
        ctk.CTkLabel(self, text="Speed:").grid(row=0, column=0, sticky="w")
        self.speed_var = ctk.DoubleVar(value=1.0)
        self.speed_label = ctk.CTkLabel(self, text="1.0x", width=50)
        self.speed_label.grid(row=0, column=2, padx=(10, 0))
        ctk.CTkSlider(
            self, from_=0.5, to=2.0, variable=self.speed_var,
            command=self._on_speed,
        ).grid(row=0, column=1, sticky="ew", padx=10)

        # Pitch
        ctk.CTkLabel(self, text="Pitch:").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.pitch_var = ctk.DoubleVar(value=0.0)
        self.pitch_label = ctk.CTkLabel(self, text="0.0", width=50)
        self.pitch_label.grid(row=1, column=2, padx=(10, 0), pady=(10, 0))
        ctk.CTkSlider(
            self, from_=-1.0, to=1.0, variable=self.pitch_var,
            command=self._on_pitch,
        ).grid(row=1, column=1, sticky="ew", padx=10, pady=(10, 0))

        # Volume
        ctk.CTkLabel(self, text="Volume:").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.volume_var = ctk.DoubleVar(value=1.0)
        self.volume_label = ctk.CTkLabel(self, text="100%", width=50)
        self.volume_label.grid(row=2, column=2, padx=(10, 0), pady=(10, 0))
        ctk.CTkSlider(
            self, from_=0.0, to=1.0, variable=self.volume_var,
            command=self._on_volume,
        ).grid(row=2, column=1, sticky="ew", padx=10, pady=(10, 0))

    def _on_speed(self, val: float) -> None:
        self.speed_label.configure(text=f"{val:.1f}x")
        if self._on_change:
            self._on_change()

    def _on_pitch(self, val: float) -> None:
        self.pitch_label.configure(text=f"{val:+.1f}")
        if self._on_change:
            self._on_change()

    def _on_volume(self, val: float) -> None:
        self.volume_label.configure(text=f"{int(val * 100)}%")
        if self._on_change:
            self._on_change()

    def update_labels(self) -> None:
        self.speed_label.configure(text=f"{self.speed_var.get():.1f}x")
        self.pitch_label.configure(text=f"{self.pitch_var.get():+.1f}")
        self.volume_label.configure(text=f"{int(self.volume_var.get() * 100)}%")


# ==========================================================================
# Emotion Picker (Item 12 — settings sub-widget)
# ==========================================================================


class EmotionPicker(ctk.CTkFrame):
    """Emotion radio buttons + intensity slider."""

    def __init__(
        self,
        parent,
        emotions: list[str],
        on_change: Callable[[], None] | None = None,
        **kwargs,
    ):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(parent, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self._on_change = on_change
        self._radio_buttons: dict[str, ctk.CTkRadioButton] = {}

        # Emotion grid
        emotion_frame = ctk.CTkFrame(self, fg_color="transparent")
        emotion_frame.grid(row=0, column=0, sticky="ew")

        self.emotion_var = ctk.StringVar(value="neutral")
        for i, emotion in enumerate(emotions):
            rb = ctk.CTkRadioButton(
                emotion_frame, text=emotion.title(),
                variable=self.emotion_var, value=emotion,
                command=self._changed,
            )
            rb.grid(row=i // 4, column=i % 4, padx=5, pady=3, sticky="w")
            self._radio_buttons[emotion] = rb

        # Intensity
        intensity_frame = ctk.CTkFrame(self, fg_color="transparent")
        intensity_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        intensity_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(intensity_frame, text="Intensity:").grid(row=0, column=0, sticky="w")
        self.intensity_var = ctk.DoubleVar(value=0.5)
        self.intensity_label = ctk.CTkLabel(intensity_frame, text="50%", width=50)
        self.intensity_label.grid(row=0, column=2, padx=(10, 0))
        self.intensity_slider = ctk.CTkSlider(
            intensity_frame, from_=0.0, to=1.0, variable=self.intensity_var,
            command=self._on_intensity,
        )
        self.intensity_slider.grid(row=0, column=1, sticky="ew", padx=10)

        self.capability_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
        )
        self.capability_label.grid(row=2, column=0, sticky="w", pady=(4, 0))

    def _changed(self) -> None:
        if self._on_change:
            self._on_change()

    def _on_intensity(self, val: float) -> None:
        self.intensity_label.configure(text=f"{int(val * 100)}%")
        if self._on_change:
            self._on_change()

    def update_labels(self) -> None:
        self.intensity_label.configure(text=f"{int(self.intensity_var.get() * 100)}%")

    def set_capability(
        self,
        emotion_support: str,
        supported_emotions: list[str],
        reason: str,
    ) -> None:
        """Update emotion control state from engine/voice capability metadata."""
        available = emotion_support in ("native", "simulated")
        supported = set(supported_emotions)

        if not available:
            self.emotion_var.set("neutral")
            for rb in self._radio_buttons.values():
                rb.configure(state="disabled", text_color_disabled="#6B7280")
            self.intensity_slider.configure(state="disabled")
            self.capability_label.configure(
                text=f"Unavailable: {reason}",
                text_color="#9CA3AF",
            )
            return

        for emotion, rb in self._radio_buttons.items():
            state = "normal" if not supported or emotion in supported else "disabled"
            rb.configure(state=state)

        if supported and self.emotion_var.get() not in supported:
            self.emotion_var.set("neutral")

        self.intensity_slider.configure(state="normal")
        label = "Native" if emotion_support == "native" else "Simulated"
        self.capability_label.configure(
            text=f"{label}: {reason}",
            text_color="#9CA3AF" if emotion_support == "simulated" else "#10B981",
        )
