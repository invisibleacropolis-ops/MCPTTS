"""
Main GUI application for MCP TTS Server.

Features:
- Three-panel layout: Settings, Log Viewer, Controls
- Server process management
- Real-time log streaming
- Toast notifications for errors/success
- Engine status badges
- Synthesis activity indicator
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
from multiprocessing import Queue
from pathlib import Path

import customtkinter as ctk

from mcp_tts.gui.log_viewer import LogViewer
from mcp_tts.gui.settings import SettingsPanel
from mcp_tts.gui.widgets import EngineStatusPanel, StatusIndicator, ToastBar
from mcp_tts.tts.audio import AudioPlayer, apply_audio_effects
from mcp_tts.tts.engine import TTSEngine
from mcp_tts.tts.manager import EngineManager
from mcp_tts.utils.config import Config, TTSSettings
from mcp_tts.utils.gpu import get_gpu_manager
from mcp_tts.utils.logging import get_logger, setup_logging

# Configure appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

logger = get_logger("gui.app")


class ServerStatusIndicator(ctk.CTkFrame):
    """Status indicator widget showing server state."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.status_label = ctk.CTkLabel(
            self,
            text="● Stopped",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#EF4444",
        )
        self.status_label.pack(side="left", padx=10)

    def set_running(self):
        self.status_label.configure(text="● Running", text_color="#10B981")

    def set_stopped(self):
        self.status_label.configure(text="● Stopped", text_color="#EF4444")

    def set_starting(self):
        self.status_label.configure(text="● Starting...", text_color="#F59E0B")

    def set_error(self, message: str = "Error"):
        self.status_label.configure(text=f"● {message}", text_color="#EF4444")


class ControlPanel(ctk.CTkFrame):
    """Server control panel with start/stop buttons, GPU status, and engine badges."""

    def __init__(
        self,
        parent,
        on_start: callable | None = None,
        on_stop: callable | None = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.on_start = on_start
        self.on_stop = on_stop
        self._setup_ui()

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)

        # Title
        ctk.CTkLabel(
            self, text="Server Controls",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, pady=(10, 15), sticky="w", padx=15)

        # Status indicator
        self.status = ServerStatusIndicator(self, fg_color="transparent")
        self.status.grid(row=1, column=0, columnspan=2, sticky="w", padx=15, pady=5)

        # Start/Stop buttons
        buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        buttons_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=15, pady=15)
        buttons_frame.grid_columnconfigure((0, 1), weight=1)

        self.start_btn = ctk.CTkButton(
            buttons_frame, text="▶ Start Server",
            command=self._on_start_click,
            fg_color="#10B981", hover_color="#059669", height=40,
        )
        self.start_btn.grid(row=0, column=0, padx=5, sticky="ew")

        self.stop_btn = ctk.CTkButton(
            buttons_frame, text="■ Stop Server",
            command=self._on_stop_click,
            fg_color="#EF4444", hover_color="#DC2626", height=40,
            state="disabled",
        )
        self.stop_btn.grid(row=0, column=1, padx=5, sticky="ew")

        # Server info
        info_frame = ctk.CTkFrame(self)
        info_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=15, pady=10)

        ctk.CTkLabel(
            info_frame, text="Transport: stdio (for MCP clients)",
            font=ctk.CTkFont(size=12), text_color="#6B7280",
        ).pack(anchor="w", padx=10, pady=5)

        ctk.CTkLabel(
            info_frame, text="Connect via: Claude Desktop, MCP Inspector",
            font=ctk.CTkFont(size=12), text_color="#6B7280",
        ).pack(anchor="w", padx=10, pady=5)

        # Engine status badges
        self.engine_panel = EngineStatusPanel(self)
        self.engine_panel.grid(row=4, column=0, columnspan=2, sticky="ew", padx=15, pady=5)

        # GPU status
        gpu_frame = ctk.CTkFrame(self)
        gpu_frame.grid(row=5, column=0, columnspan=2, sticky="ew", padx=15, pady=10)
        gpu_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            gpu_frame, text="GPU Status",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 2))

        self.gpu_name_label = ctk.CTkLabel(gpu_frame, text="GPU: Detecting...")
        self.gpu_name_label.grid(row=1, column=0, sticky="w", padx=10)

        self.gpu_vram_label = ctk.CTkLabel(gpu_frame, text="VRAM: --")
        self.gpu_vram_label.grid(row=2, column=0, sticky="w", padx=10)

        self.gpu_engine_label = ctk.CTkLabel(gpu_frame, text="Engine: --")
        self.gpu_engine_label.grid(row=3, column=0, sticky="w", padx=10, pady=(0, 4))

        # Quick test
        test_frame = ctk.CTkFrame(self, fg_color="transparent")
        test_frame.grid(row=6, column=0, columnspan=2, sticky="ew", padx=15, pady=10)
        test_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            test_frame, text="Quick Test:",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))

        self.test_entry = ctk.CTkEntry(
            test_frame, placeholder_text="Enter text to speak...",
        )
        self.test_entry.grid(row=1, column=0, sticky="ew", padx=(0, 5))

        self.speak_btn = ctk.CTkButton(
            test_frame, text="🔊 Speak", width=80, state="disabled",
        )
        self.speak_btn.grid(row=1, column=1)

    def _on_start_click(self):
        if self.on_start:
            self.on_start()

    def _on_stop_click(self):
        if self.on_stop:
            self.on_stop()

    def set_server_running(self, running: bool):
        if running:
            self.status.set_running()
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
            self.speak_btn.configure(state="normal")
        else:
            self.status.set_stopped()
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self.speak_btn.configure(state="disabled")

    def update_gpu_status(self, name: str, vram: str, engine: str) -> None:
        self.gpu_name_label.configure(text=f"GPU: {name}")
        self.gpu_vram_label.configure(text=f"VRAM: {vram}")
        self.gpu_engine_label.configure(text=f"Engine: {engine}")


class MCPTTSApp(ctk.CTk):
    """
    Main MCP TTS Server GUI Application.

    Three-panel layout:
    - Left: TTS Settings
    - Center: Real-time Log Viewer
    - Right: Server Controls
    - Bottom: Toast notification bar
    """

    def __init__(self):
        super().__init__()

        self.title("MCP TTS Server")
        self.geometry("1400x800")
        self.minsize(1000, 600)

        # Load configuration
        self.config = Config.load()

        # Set up logging with GUI queue
        self.log_queue: Queue = Queue()
        setup_logging(gui_queue=self.log_queue, verbose=True)

        # Server process reference
        self.server_process: subprocess.Popen | None = None

        # TTS engine for preview (lazy initialized)
        self._tts_engine: TTSEngine | None = None
        self._tts_engine_initializing = False
        self._audio_player = AudioPlayer()
        self._gpu_manager = get_gpu_manager()
        self._engine_manager = EngineManager(models_dir=self.config.models_directory)
        self._current_engine_key = self.config.tts.engine

        self._setup_ui()
        self._bind_events()

        # Initialize TTS engine in background
        self._init_tts_engine()
        self._start_gpu_polling()

        logger.info("MCP TTS GUI Application started")

    def _setup_ui(self):
        """Set up the main UI layout."""
        # Configure grid — 3 columns + 1 row for panels, 1 row for toast
        self.grid_columnconfigure(0, weight=1, minsize=320)  # Settings
        self.grid_columnconfigure(1, weight=3)  # Log viewer
        self.grid_columnconfigure(2, weight=1, minsize=300)  # Controls
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)  # Toast bar

        # Left panel: Settings
        self.settings_panel = SettingsPanel(
            self,
            config=self.config,
            on_settings_change=self._on_settings_change,
            on_preview=self._on_preview,
            on_clone_voice=self._on_clone_voice,
        )
        self.settings_panel.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)

        # Center panel: Log viewer + status indicator
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=10)
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        # Header with title + status indicator
        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.grid(row=0, column=0, sticky="ew", padx=15, pady=(10, 0))
        log_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            log_header, text="Server Logs",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        self.status_indicator = StatusIndicator(log_header)
        self.status_indicator.grid(row=0, column=1, sticky="e", padx=(10, 0))

        self.log_viewer = LogViewer(
            log_frame,
            log_queue=self.log_queue,
            max_lines=self.config.gui.log_max_lines,
            auto_scroll=self.config.gui.auto_scroll,
        )
        self.log_viewer.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        # Right panel: Controls
        self.control_panel = ControlPanel(
            self,
            on_start=self._start_server,
            on_stop=self._stop_server,
        )
        self.control_panel.grid(row=0, column=2, sticky="nsew", padx=(5, 10), pady=10)

        # Bottom: Toast notification bar
        self.toast = ToastBar(self, dismiss_ms=5000)
        self.toast.grid(row=1, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 5))

        # Start log polling
        self.log_viewer.start_polling(interval_ms=100)

    def _bind_events(self):
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_settings_change(self, settings: TTSSettings):
        logger.debug(f"Settings changed: {settings}")
        self.config.tts = settings
        self.config.save()

        if settings.engine != self._current_engine_key:
            self._init_tts_engine(settings.engine)

    def _init_tts_engine(self, preferred_engine: str | None = None):
        """Initialize TTS engine in background thread."""
        if self._tts_engine_initializing:
            return

        self._tts_engine_initializing = True
        engine_key = preferred_engine or self.config.tts.engine

        # Show loading state
        self.after(0, lambda: self.status_indicator.set_state("loading", f"Loading {engine_key}…"))

        def init_engine():
            try:
                logger.info("Initializing TTS engine for preview...")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    engine = loop.run_until_complete(self._engine_manager.get_engine(engine_key))
                    self._tts_engine = engine
                    self._current_engine_key = engine_key
                    self._refresh_voice_list()
                    logger.info(f"TTS engine initialized: {engine.name}")

                    # Update UI on main thread
                    self.after(0, lambda: self.status_indicator.set_state("idle"))
                    self.after(0, lambda: self.toast.show_success(f"Engine loaded: {engine.name}"))
                    self.after(0, lambda: self.control_panel.engine_panel.update_engines(
                        self._engine_manager.list_loaded()
                    ))
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"Failed to initialize TTS engine {engine_key}: {e}")
                self.after(0, lambda: self.status_indicator.set_state("error", "Engine failed"))
                error_message = str(e)
                self.after(
                    0,
                    lambda msg=error_message: self.toast.show_error(
                        f"Engine '{engine_key}' failed: {msg}"
                    ),
                )
            finally:
                self._tts_engine_initializing = False

        threading.Thread(target=init_engine, daemon=True).start()

    def _start_gpu_polling(self):
        self._refresh_gpu_status()
        self.after(1500, self._start_gpu_polling)

    def _refresh_gpu_status(self):
        gpu_info = self._gpu_manager.refresh_vram_info()

        if gpu_info:
            vram = f"{gpu_info.used_vram_gb:.2f}GB / {gpu_info.total_vram_gb:.2f}GB"
            name = f"{gpu_info.name} ({gpu_info.status.value})"
        else:
            vram = "--"
            name = "Not detected"

        engine_name = "None"
        device = "cpu"
        if self._tts_engine:
            engine_name = self._tts_engine.name
            device = getattr(self._tts_engine, "active_device", device)

        engine_label = f"{engine_name} on {device}"
        self.control_panel.update_gpu_status(name=name, vram=vram, engine=engine_label)

        # Update engine badges
        self.control_panel.engine_panel.update_engines(self._engine_manager.list_loaded())

    def _refresh_voice_list(self):
        engine = self._tts_engine
        if engine is None:
            return

        def load_voices():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    voices = loop.run_until_complete(engine.list_voices())
                finally:
                    loop.close()

                self.after(0, lambda: self.settings_panel.update_voice_infos(voices))
            except Exception as e:
                logger.warning(f"Failed to refresh voice list: {e}")

        threading.Thread(target=load_voices, daemon=True).start()

    def _on_preview(self, text: str):
        """Handle preview request — synthesize and play audio."""
        if not text.strip():
            self.toast.show_warning("Enter some text to preview")
            return

        if self._tts_engine is None:
            if self._tts_engine_initializing:
                self.toast.show_info("Engine still loading, please wait…")
            else:
                self.toast.show_error("No TTS engine available — check logs")
            return

        engine = self._tts_engine
        use_direct_playback = self.config.audio.use_direct_playback

        # Show synthesizing status
        self.status_indicator.set_state("synthesizing")

        def run_preview():
            try:
                settings = self.settings_panel.get_current_settings()

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        engine.synthesize(text, settings, use_direct_playback=use_direct_playback)
                    )

                    if len(result.audio_data) > 0:
                        result.audio_data = apply_audio_effects(
                            result.audio_data, result.sample_rate, self.config.audio,
                        )
                        self.after(0, lambda: self.status_indicator.set_state("playing"))
                        self._audio_player.play(
                            result.audio_data, result.sample_rate,
                            blocking=True, volume=settings.volume,
                        )
                finally:
                    loop.close()

                self.after(0, lambda: self.status_indicator.set_state("idle"))
                self.after(0, lambda: self.toast.show_success(
                    f"Played {result.duration_seconds:.1f}s audio"
                ))

            except Exception as e:
                logger.error(f"Preview failed: {e}")
                self.after(0, lambda: self.status_indicator.set_state("error"))
                error_message = str(e)
                self.after(
                    0,
                    lambda msg=error_message: self.toast.show_error(f"Preview failed: {msg}"),
                )

        threading.Thread(target=run_preview, daemon=True).start()

    def _on_clone_voice(self, audio_path: str, name: str, prompt_text: str, language: str) -> None:
        if self._tts_engine is None:
            self.toast.show_warning("TTS engine not available for voice cloning")
            return

        engine = self._tts_engine
        if not hasattr(engine, "clone_voice"):
            self.toast.show_warning("Current engine does not support voice cloning")
            return

        def run_clone():
            try:
                logger.info(f"Cloning voice '{name}' from {audio_path}")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    clone_kwargs = {
                        "audio_path": Path(audio_path),
                        "name": name,
                        "prompt_text": prompt_text,
                    }
                    if language:
                        clone_kwargs["language"] = language
                    loop.run_until_complete(engine.clone_voice(**clone_kwargs))
                finally:
                    loop.close()

                self._refresh_voice_list()
                self.after(
                    0,
                    lambda: self.toast.show_success(f"Voice '{name}' cloned successfully"),
                )
            except Exception as e:
                logger.error(f"Voice cloning failed: {e}")
                error_message = str(e)
                self.after(
                    0,
                    lambda msg=error_message: self.toast.show_error(
                        f"Voice cloning failed: {msg}"
                    ),
                )

        threading.Thread(target=run_clone, daemon=True).start()

    def _start_server(self):
        """Start the MCP server process."""
        logger.info("Starting MCP TTS Server...")
        self.control_panel.status.set_starting()

        try:
            self.server_process = subprocess.Popen(
                [sys.executable, "-m", "mcp_tts.server.lifecycle"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            self._start_output_reader()
            self.control_panel.set_server_running(True)
            self.toast.show_success("MCP TTS Server started")

        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            self.control_panel.status.set_error("Start failed")
            self.toast.show_error(f"Server start failed: {e}")

    def _start_output_reader(self):
        def read_output():
            if self.server_process and self.server_process.stdout:
                for line in self.server_process.stdout:
                    line = line.strip()
                    if line:
                        level = "INFO"
                        if "ERROR" in line or "Error" in line:
                            level = "ERROR"
                        elif "WARNING" in line or "Warning" in line:
                            level = "WARNING"
                        elif "DEBUG" in line:
                            level = "DEBUG"
                        self.log_viewer.add_log(level, f"[SERVER] {line}")

            if self.server_process:
                self.after(0, lambda: self.control_panel.set_server_running(False))

        threading.Thread(target=read_output, daemon=True).start()

    def _stop_server(self):
        logger.info("Stopping MCP TTS Server...")

        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
            finally:
                self.server_process = None

        self.control_panel.set_server_running(False)
        self.toast.show_info("Server stopped")

    def _on_close(self):
        logger.info("Closing MCP TTS GUI...")
        self.log_viewer.stop_polling()
        if self.server_process:
            self._stop_server()
        self.config.save()
        self.destroy()


def run_gui():
    """Run the GUI application."""
    app = MCPTTSApp()
    app.mainloop()


if __name__ == "__main__":
    run_gui()
