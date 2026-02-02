"""
Main GUI application for MCP TTS Server.

Features:
- Three-panel layout: Settings, Log Viewer, Controls
- Server process management
- Real-time log streaming
- Settings persistence
"""

import asyncio
import subprocess
import sys
import threading
from multiprocessing import Process, Queue
from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk

from mcp_tts.gui.log_viewer import LogViewer
from mcp_tts.gui.settings import SettingsPanel
from mcp_tts.utils.config import Config, TTSSettings
from mcp_tts.utils.logging import setup_logging, get_logger
from mcp_tts.utils.gpu import get_gpu_manager
from mcp_tts.tts.engine import TTSEngine, TTSEngineType
from mcp_tts.tts.manager import EngineManager
from mcp_tts.tts.audio import AudioPlayer, apply_audio_effects

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
        """Set status to running."""
        self.status_label.configure(text="● Running", text_color="#10B981")

    def set_stopped(self):
        """Set status to stopped."""
        self.status_label.configure(text="● Stopped", text_color="#EF4444")

    def set_starting(self):
        """Set status to starting."""
        self.status_label.configure(text="● Starting...", text_color="#F59E0B")

    def set_error(self, message: str = "Error"):
        """Set status to error."""
        self.status_label.configure(text=f"● {message}", text_color="#EF4444")


class ControlPanel(ctk.CTkFrame):
    """Server control panel with start/stop buttons and status."""

    def __init__(
        self,
        parent,
        on_start: Optional[Callable[[], None]] = None,
        on_stop: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)

        self.on_start = on_start
        self.on_stop = on_stop

        self._setup_ui()

    def _setup_ui(self):
        """Set up the control panel UI."""
        self.grid_columnconfigure(0, weight=1)

        # Title
        title = ctk.CTkLabel(
            self,
            text="Server Controls",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.grid(row=0, column=0, columnspan=2, pady=(10, 15), sticky="w", padx=15)

        # Status indicator
        self.status = ServerStatusIndicator(self, fg_color="transparent")
        self.status.grid(row=1, column=0, columnspan=2, sticky="w", padx=15, pady=5)

        # Start/Stop buttons
        buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        buttons_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=15, pady=15)
        buttons_frame.grid_columnconfigure((0, 1), weight=1)

        self.start_btn = ctk.CTkButton(
            buttons_frame,
            text="▶ Start Server",
            command=self._on_start_click,
            fg_color="#10B981",
            hover_color="#059669",
            height=40,
        )
        self.start_btn.grid(row=0, column=0, padx=5, sticky="ew")

        self.stop_btn = ctk.CTkButton(
            buttons_frame,
            text="■ Stop Server",
            command=self._on_stop_click,
            fg_color="#EF4444",
            hover_color="#DC2626",
            height=40,
            state="disabled",
        )
        self.stop_btn.grid(row=0, column=1, padx=5, sticky="ew")

        # Server info
        info_frame = ctk.CTkFrame(self)
        info_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=15, pady=10)

        ctk.CTkLabel(
            info_frame,
            text="Transport: stdio (for MCP clients)",
            font=ctk.CTkFont(size=12),
            text_color="#6B7280",
        ).pack(anchor="w", padx=10, pady=5)

        ctk.CTkLabel(
            info_frame,
            text="Connect via: Claude Desktop, MCP Inspector",
            font=ctk.CTkFont(size=12),
            text_color="#6B7280",
        ).pack(anchor="w", padx=10, pady=5)

        # GPU status
        gpu_frame = ctk.CTkFrame(self)
        gpu_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=15, pady=10)
        gpu_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            gpu_frame,
            text="GPU Status",
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
        test_frame.grid(row=5, column=0, columnspan=2, sticky="ew", padx=15, pady=10)
        test_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            test_frame,
            text="Quick Test:",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))

        self.test_entry = ctk.CTkEntry(
            test_frame,
            placeholder_text="Enter text to speak...",
        )
        self.test_entry.grid(row=1, column=0, sticky="ew", padx=(0, 5))

        self.speak_btn = ctk.CTkButton(
            test_frame,
            text="🔊 Speak",
            width=80,
            state="disabled",
        )
        self.speak_btn.grid(row=1, column=1)

    def _on_start_click(self):
        """Handle start button click."""
        if self.on_start:
            self.on_start()

    def _on_stop_click(self):
        """Handle stop button click."""
        if self.on_stop:
            self.on_stop()

    def set_server_running(self, running: bool):
        """Update UI based on server state."""
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
        self.server_process: Optional[subprocess.Popen] = None

        # TTS engine for preview (lazy initialized)
        self._tts_engine: Optional[TTSEngine] = None
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
        # Configure grid
        self.grid_columnconfigure(0, weight=1, minsize=320)  # Settings
        self.grid_columnconfigure(1, weight=3)  # Log viewer
        self.grid_columnconfigure(2, weight=1, minsize=300)  # Controls
        self.grid_rowconfigure(0, weight=1)

        # Left panel: Settings
        self.settings_panel = SettingsPanel(
            self,
            config=self.config,
            on_settings_change=self._on_settings_change,
            on_preview=self._on_preview,
            on_clone_voice=self._on_clone_voice,
        )
        self.settings_panel.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)

        # Center panel: Log viewer
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=10)
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        log_title = ctk.CTkLabel(
            log_frame,
            text="Server Logs",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        log_title.grid(row=0, column=0, sticky="w", padx=15, pady=(10, 0))

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

        # Start log polling
        self.log_viewer.start_polling(interval_ms=100)

    def _bind_events(self):
        """Bind window events."""
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_settings_change(self, settings: TTSSettings):
        """Handle settings change from panel."""
        logger.debug(f"Settings changed: {settings}")
        self.config.tts = settings
        self.config.save()

        if settings.engine != self._current_engine_key:
            self._init_tts_engine(settings.engine)

    def _init_tts_engine(self, preferred_engine: Optional[str] = None):
        """Initialize TTS engine in background thread."""
        if self._tts_engine_initializing:
            return

        self._tts_engine_initializing = True
        engine_key = preferred_engine or self.config.tts.engine

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
                    logger.info(f"TTS engine initialized successfully: {engine.name}")
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"Failed to initialize TTS engine {engine_key}: {e}")
            finally:
                self._tts_engine_initializing = False

        thread = threading.Thread(target=init_engine, daemon=True)
        thread.start()

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

                voice_ids = [voice.id for voice in voices]
                self.after(0, lambda: self.settings_panel.update_voices(voice_ids))
            except Exception as e:
                logger.warning(f"Failed to refresh voice list: {e}")

        threading.Thread(target=load_voices, daemon=True).start()

    def _on_preview(self, text: str):
        """Handle preview request - synthesize and play audio."""
        if not text.strip():
            logger.warning("Preview requested with empty text")
            return

        logger.info(f"Preview requested: '{text}'")

        if self._tts_engine is None:
            if self._tts_engine_initializing:
                logger.warning("TTS engine still initializing, please wait...")
                self.log_viewer.add_log("WARNING", "TTS engine still initializing, please wait...")
            else:
                logger.error("TTS engine not available")
                self.log_viewer.add_log("ERROR", "TTS engine not available - check logs")
            return

        engine = self._tts_engine

        # Check playback mode from config
        use_direct_playback = self.config.audio.use_direct_playback

        # Run synthesis in background thread
        def run_preview():
            try:
                logger.debug(f"Starting TTS synthesis (direct={use_direct_playback})...")

                # Get current settings from settings panel
                settings = self.settings_panel.get_current_settings()

                # Run async synthesis
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        engine.synthesize(text, settings, use_direct_playback=use_direct_playback)
                    )
                    logger.info(f"Synthesis complete: {result.duration_seconds:.2f}s")

                    # In direct mode, audio was already played by pyttsx3
                    # In file mode, play through AudioPlayer
                    if not use_direct_playback and len(result.audio_data) > 0:
                        result.audio_data = apply_audio_effects(
                            result.audio_data,
                            result.sample_rate,
                            self.config.audio,
                        )
                        logger.debug("Playing audio via AudioPlayer...")
                        self._audio_player.play(
                            result.audio_data,
                            result.sample_rate,
                            blocking=True,
                            volume=settings.volume if hasattr(settings, "volume") else 1.0,
                        )
                        logger.info("Audio playback complete")
                finally:
                    loop.close()

            except Exception as e:
                logger.error(f"Preview failed: {e}")
                self.after(0, lambda: self.log_viewer.add_log("ERROR", f"Preview failed: {e}"))

        thread = threading.Thread(target=run_preview, daemon=True)
        thread.start()

    def _on_clone_voice(self, audio_path: str, name: str, prompt_text: str, language: str) -> None:
        if self._tts_engine is None:
            logger.warning("TTS engine not available for voice cloning")
            return

        engine = self._tts_engine
        if not hasattr(engine, "clone_voice"):
            logger.warning("Current engine does not support voice cloning")
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
                logger.info(f"Voice '{name}' cloned successfully")
            except Exception as e:
                logger.error(f"Voice cloning failed: {e}")
                self.after(
                    0, lambda: self.log_viewer.add_log("ERROR", f"Voice cloning failed: {e}")
                )

        threading.Thread(target=run_clone, daemon=True).start()

    def _start_server(self):
        """Start the MCP server process."""
        logger.info("Starting MCP TTS Server...")
        self.control_panel.status.set_starting()

        try:
            # Start server as subprocess
            server_script = Path(__file__).parent.parent / "server.py"

            self.server_process = subprocess.Popen(
                [sys.executable, str(server_script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            # Start thread to read server output
            self._start_output_reader()

            self.control_panel.set_server_running(True)
            logger.info("MCP TTS Server started successfully")

        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            self.control_panel.status.set_error("Start failed")

    def _start_output_reader(self):
        """Start a thread to read server output."""

        def read_output():
            if self.server_process and self.server_process.stdout:
                for line in self.server_process.stdout:
                    line = line.strip()
                    if line:
                        # Determine log level from line content
                        level = "INFO"
                        if "ERROR" in line or "Error" in line:
                            level = "ERROR"
                        elif "WARNING" in line or "Warning" in line:
                            level = "WARNING"
                        elif "DEBUG" in line:
                            level = "DEBUG"

                        self.log_viewer.add_log(level, f"[SERVER] {line}")

            # Server has stopped
            if self.server_process:
                self.after(0, lambda: self.control_panel.set_server_running(False))

        thread = threading.Thread(target=read_output, daemon=True)
        thread.start()

    def _stop_server(self):
        """Stop the MCP server process."""
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
        logger.info("MCP TTS Server stopped")

    def _on_close(self):
        """Handle window close."""
        logger.info("Closing MCP TTS GUI...")

        # Stop log polling
        self.log_viewer.stop_polling()

        # Stop server if running
        if self.server_process:
            self._stop_server()

        # Save configuration
        self.config.save()

        self.destroy()


def run_gui():
    """Run the GUI application."""
    app = MCPTTSApp()
    app.mainloop()


if __name__ == "__main__":
    run_gui()
