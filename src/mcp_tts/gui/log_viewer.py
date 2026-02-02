"""
Real-time log viewer widget for the MCP TTS GUI.

Features:
- Scrollable text display with auto-scroll
- Color-coded log levels
- Log level filtering
- Text search
- Export to file
"""

import tkinter as tk
from datetime import datetime
from multiprocessing import Queue
from queue import Empty
from typing import Optional, Callable

import customtkinter as ctk

from mcp_tts.utils.logging import get_logger

logger = get_logger("gui.log_viewer")


# Color scheme for log levels
LOG_COLORS = {
    "DEBUG": "#6B7280",     # Gray
    "INFO": "#10B981",      # Green
    "WARNING": "#F59E0B",   # Yellow/Orange
    "ERROR": "#EF4444",     # Red
    "CRITICAL": "#8B5CF6",  # Purple
}


class LogViewer(ctk.CTkFrame):
    """
    Real-time log viewer widget.
    
    Displays streaming log entries with filtering and search capabilities.
    """
    
    def __init__(
        self,
        parent,
        log_queue: Optional[Queue] = None,
        max_lines: int = 1000,
        auto_scroll: bool = True,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        
        self.log_queue = log_queue
        self.max_lines = max_lines
        self.auto_scroll = auto_scroll
        self._polling = False
        self._filter_level = "DEBUG"
        self._search_text = ""
        self._all_logs: list[dict] = []
        
        self._setup_ui()
        logger.debug("LogViewer initialized")
    
    def _setup_ui(self):
        """Set up the UI components."""
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # --- Toolbar ---
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 0))
        toolbar.grid_columnconfigure(2, weight=1)
        
        # Log level filter
        ctk.CTkLabel(toolbar, text="Filter:").grid(row=0, column=0, padx=(0, 5))
        
        self.level_var = ctk.StringVar(value="DEBUG")
        self.level_menu = ctk.CTkOptionMenu(
            toolbar,
            values=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            variable=self.level_var,
            command=self._on_level_change,
            width=100,
        )
        self.level_menu.grid(row=0, column=1, padx=5)
        
        # Search entry
        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            toolbar,
            placeholder_text="Search logs...",
            textvariable=self.search_var,
            width=200,
        )
        self.search_entry.grid(row=0, column=2, padx=5, sticky="ew")
        self.search_entry.bind("<KeyRelease>", self._on_search_change)
        
        # Auto-scroll toggle
        self.auto_scroll_var = ctk.BooleanVar(value=self.auto_scroll)
        self.auto_scroll_cb = ctk.CTkCheckBox(
            toolbar,
            text="Auto-scroll",
            variable=self.auto_scroll_var,
            command=self._on_auto_scroll_toggle,
            width=100,
        )
        self.auto_scroll_cb.grid(row=0, column=3, padx=10)
        
        # Clear button
        self.clear_btn = ctk.CTkButton(
            toolbar,
            text="Clear",
            command=self._clear_logs,
            width=70,
            fg_color="#EF4444",
            hover_color="#DC2626",
        )
        self.clear_btn.grid(row=0, column=4, padx=5)
        
        # Export button
        self.export_btn = ctk.CTkButton(
            toolbar,
            text="Export",
            command=self._export_logs,
            width=70,
        )
        self.export_btn.grid(row=0, column=5, padx=5)
        
        # Quick Save button (saves to Log.txt in project root)
        self.save_btn = ctk.CTkButton(
            toolbar,
            text="Save",
            command=self._quick_save_logs,
            width=70,
            fg_color="#10B981",
            hover_color="#059669",
        )
        self.save_btn.grid(row=0, column=6, padx=5)
        
        # --- Log display ---
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)
        
        # Text widget with scrollbar
        self.log_text = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
            state="disabled",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        
        # Configure text tags for colors
        # Note: CTkTextbox doesn't support tags directly, we'll use the internal text widget
        try:
            internal_text = self.log_text._textbox
            for level, color in LOG_COLORS.items():
                internal_text.tag_configure(level, foreground=color)
            internal_text.tag_configure("TIMESTAMP", foreground="#6B7280")
            internal_text.tag_configure("SEARCH_MATCH", background="#FBBF24", foreground="#000000")
        except AttributeError:
            logger.warning("Could not configure text tags - using default colors")
        
        # --- Status bar ---
        self.status_label = ctk.CTkLabel(
            self,
            text="0 entries",
            font=ctk.CTkFont(size=11),
            text_color="#6B7280",
        )
        self.status_label.grid(row=2, column=0, sticky="w", padx=10, pady=(0, 5))
    
    def start_polling(self, interval_ms: int = 100):
        """Start polling the log queue for new entries."""
        if self.log_queue is None:
            logger.warning("No log queue configured - polling disabled")
            return
        
        self._polling = True
        self._poll_queue(interval_ms)
        logger.debug(f"Started log polling at {interval_ms}ms interval")
    
    def stop_polling(self):
        """Stop polling the log queue."""
        self._polling = False
        logger.debug("Stopped log polling")
    
    def _poll_queue(self, interval_ms: int):
        """Poll the queue for new log entries."""
        if not self._polling:
            return
        
        # Process all available log entries
        entries_processed = 0
        while self.log_queue:
            try:
                log_entry = self.log_queue.get_nowait()
                self._add_log_entry(log_entry)
                entries_processed += 1
            except Empty:
                break
        
        # Note: Don't log processed entries here - it creates a self-referential loop
        # where logging about processing causes more processing
        
        # Schedule next poll
        self.after(interval_ms, lambda: self._poll_queue(interval_ms))
    
    def _add_log_entry(self, entry: dict):
        """Add a log entry to the display."""
        self._all_logs.append(entry)
        
        # Trim old logs if needed
        if len(self._all_logs) > self.max_lines * 2:
            self._all_logs = self._all_logs[-self.max_lines:]
        
        # Check if entry passes filter
        if not self._entry_passes_filter(entry):
            return
        
        self._display_entry(entry)
        self._update_status()
    
    def _entry_passes_filter(self, entry: dict) -> bool:
        """Check if an entry passes the current filters."""
        # Level filter
        level_order = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        entry_level = entry.get("level", "DEBUG").upper()
        
        # Handle unknown levels (e.g., TRACE, SUCCESS from loguru) - default to DEBUG priority
        try:
            entry_level_idx = level_order.index(entry_level)
        except ValueError:
            entry_level_idx = 0  # Treat unknown levels as DEBUG priority
        
        filter_level_idx = level_order.index(self._filter_level)
        
        if entry_level_idx < filter_level_idx:
            return False
        
        # Search filter
        if self._search_text:
            search_lower = self._search_text.lower()
            message = entry.get("message", "").lower()
            if search_lower not in message:
                return False
        
        return True
    
    def _display_entry(self, entry: dict):
        """Display a single log entry."""
        try:
            self.log_text.configure(state="normal")
            
            level = entry.get("level", "INFO")
            timestamp = entry.get("timestamp", datetime.now().isoformat())
            message = entry.get("message", "")
            
            # Format the log line
            log_line = f"[{timestamp}] [{level}] {message}\n"
            
            # Insert with appropriate tag
            try:
                internal_text = self.log_text._textbox
                start_idx = internal_text.index("end-1c")
                internal_text.insert("end", log_line)
                end_idx = internal_text.index("end-1c")
                internal_text.tag_add(level, start_idx, end_idx)
            except AttributeError:
                # Fallback for different CTkTextbox versions
                self.log_text.insert("end", log_line)
            
            # Auto-scroll
            if self.auto_scroll_var.get():
                self.log_text.see("end")
            
            self.log_text.configure(state="disabled")
            
        except Exception as e:
            logger.error(f"Error displaying log entry: {e}")
    
    def _refresh_display(self):
        """Refresh the log display with current filters."""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        
        for entry in self._all_logs:
            if self._entry_passes_filter(entry):
                self._display_entry(entry)
        
        self.log_text.configure(state="disabled")
        self._update_status()
    
    def _update_status(self):
        """Update the status bar."""
        visible = sum(1 for e in self._all_logs if self._entry_passes_filter(e))
        total = len(self._all_logs)
        
        if visible == total:
            self.status_label.configure(text=f"{total} entries")
        else:
            self.status_label.configure(text=f"{visible} of {total} entries (filtered)")
    
    def _on_level_change(self, new_level: str):
        """Handle log level filter change."""
        self._filter_level = new_level
        logger.debug(f"Log filter level changed to: {new_level}")
        self._refresh_display()
    
    def _on_search_change(self, event=None):
        """Handle search text change."""
        self._search_text = self.search_var.get()
        self._refresh_display()
    
    def _on_auto_scroll_toggle(self):
        """Handle auto-scroll toggle."""
        self.auto_scroll = self.auto_scroll_var.get()
        logger.debug(f"Auto-scroll: {self.auto_scroll}")
    
    def _clear_logs(self):
        """Clear all log entries."""
        self._all_logs.clear()
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._update_status()
        logger.info("Logs cleared")
    
    def _export_logs(self):
        """Export logs to a file."""
        from tkinter import filedialog
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")],
            title="Export Logs",
        )
        
        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    for entry in self._all_logs:
                        level = entry.get("level", "INFO")
                        timestamp = entry.get("timestamp", "")
                        message = entry.get("message", "")
                        f.write(f"[{timestamp}] [{level}] {message}\n")
                
                logger.info(f"Logs exported to: {filepath}")
            except Exception as e:
                logger.error(f"Failed to export logs: {e}")
    
    def _quick_save_logs(self):
        """Quick save logs to Log.txt in the project root."""
        from pathlib import Path
        
        # Find project root (go up from this file's location)
        project_root = Path(__file__).parent.parent.parent.parent
        filepath = project_root / "Log.txt"
        
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                for entry in self._all_logs:
                    level = entry.get("level", "INFO")
                    timestamp = entry.get("timestamp", "")
                    message = entry.get("message", "")
                    f.write(f"[{timestamp}] [{level}] {message}\n")
            
            logger.info(f"Logs saved to: {filepath}")
        except Exception as e:
            logger.error(f"Failed to save logs: {e}")
    
    def add_log(self, level: str, message: str):
        """Programmatically add a log entry (for testing/direct use)."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
        }
        self._add_log_entry(entry)
