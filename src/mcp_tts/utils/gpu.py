"""
GPU utilities for MCP TTS Server.

Provides:
- GPU detection and capability checking
- VRAM monitoring
- Device selection helpers
- GPU availability warnings
"""

import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional

from mcp_tts.utils.logging import get_logger

logger = get_logger("utils.gpu")


class GPUStatus(StrEnum):
    """GPU availability status."""
    AVAILABLE = "available"
    BUSY = "busy"
    NOT_FOUND = "not_found"
    CUDA_NOT_AVAILABLE = "cuda_not_available"
    VRAM_LOW = "vram_low"


@dataclass
class GPUInfo:
    """Information about available GPU."""

    name: str
    total_vram_gb: float
    available_vram_gb: float
    used_vram_gb: float
    cuda_version: str | None
    device_id: int
    status: GPUStatus

    @property
    def vram_usage_percent(self) -> float:
        """Get VRAM usage as percentage."""
        if self.total_vram_gb == 0:
            return 0.0
        return (self.used_vram_gb / self.total_vram_gb) * 100

    def to_dict(self) -> dict:
        """Convert to dictionary for reporting."""
        return {
            "name": self.name,
            "total_vram_gb": round(self.total_vram_gb, 2),
            "available_vram_gb": round(self.available_vram_gb, 2),
            "used_vram_gb": round(self.used_vram_gb, 2),
            "vram_usage_percent": round(self.vram_usage_percent, 1),
            "cuda_version": self.cuda_version,
            "device_id": self.device_id,
            "status": self.status.value,
        }


class GPUManager:
    """
    Manager for GPU resources and monitoring.

    Thread-safe singleton for GPU state management.
    """

    _instance: Optional["GPUManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._torch_available = False
        self._cuda_available = False
        self._gpu_info: GPUInfo | None = None
        self._vram_threshold_gb = 1.0  # Warn if less than 1GB available

        self._detect_gpu()
        logger.debug("GPUManager initialized")

    def _detect_gpu(self) -> None:
        """Detect GPU and capabilities."""
        try:
            import torch
            self._torch_available = True
            self._cuda_available = torch.cuda.is_available()

            if self._cuda_available:
                device_id = torch.cuda.current_device()
                props = torch.cuda.get_device_properties(device_id)

                # Get memory info
                total_vram = props.total_memory / (1024**3)  # Convert to GB
                allocated = torch.cuda.memory_allocated(device_id) / (1024**3)
                reserved = torch.cuda.memory_reserved(device_id) / (1024**3)
                available = total_vram - reserved

                # Determine status
                if available < self._vram_threshold_gb:
                    status = GPUStatus.VRAM_LOW
                else:
                    status = GPUStatus.AVAILABLE

                self._gpu_info = GPUInfo(
                    name=props.name,
                    total_vram_gb=total_vram,
                    available_vram_gb=available,
                    used_vram_gb=allocated,
                    cuda_version=torch.version.cuda,
                    device_id=device_id,
                    status=status,
                )

                logger.info(f"GPU detected: {props.name} ({total_vram:.1f}GB VRAM)")
            else:
                logger.warning("CUDA not available - GPU acceleration disabled")
                self._gpu_info = GPUInfo(
                    name="None",
                    total_vram_gb=0,
                    available_vram_gb=0,
                    used_vram_gb=0,
                    cuda_version=None,
                    device_id=-1,
                    status=GPUStatus.CUDA_NOT_AVAILABLE,
                )

        except ImportError:
            logger.warning("PyTorch not installed - GPU acceleration unavailable")
            self._gpu_info = GPUInfo(
                name="None",
                total_vram_gb=0,
                available_vram_gb=0,
                used_vram_gb=0,
                cuda_version=None,
                device_id=-1,
                status=GPUStatus.NOT_FOUND,
            )

    @property
    def is_gpu_available(self) -> bool:
        """Check if GPU is available for use."""
        return (
            self._cuda_available
            and self._gpu_info is not None
            and self._gpu_info.status == GPUStatus.AVAILABLE
        )

    @property
    def gpu_info(self) -> GPUInfo | None:
        """Get current GPU info."""
        return self._gpu_info

    def refresh_vram_info(self) -> GPUInfo | None:
        """Refresh VRAM usage information."""
        if not self._cuda_available:
            return self._gpu_info

        try:
            import torch
            device_id = torch.cuda.current_device()

            total_vram = torch.cuda.get_device_properties(device_id).total_memory / (1024**3)
            allocated = torch.cuda.memory_allocated(device_id) / (1024**3)
            reserved = torch.cuda.memory_reserved(device_id) / (1024**3)
            available = total_vram - reserved

            if self._gpu_info:
                self._gpu_info.used_vram_gb = allocated
                self._gpu_info.available_vram_gb = available

                if available < self._vram_threshold_gb:
                    self._gpu_info.status = GPUStatus.VRAM_LOW
                else:
                    self._gpu_info.status = GPUStatus.AVAILABLE

            return self._gpu_info

        except Exception as e:
            logger.error(f"Failed to refresh VRAM info: {e}")
            return self._gpu_info

    def check_vram_available(self, required_gb: float) -> bool:
        """
        Check if enough VRAM is available.

        Args:
            required_gb: Required VRAM in gigabytes

        Returns:
            True if enough VRAM available
        """
        if not self._cuda_available:
            return False

        self.refresh_vram_info()
        if self._gpu_info is None:
            return False

        return self._gpu_info.available_vram_gb >= required_gb

    def get_device(self) -> str:
        """Get the device string for PyTorch."""
        if self.is_gpu_available:
            return f"cuda:{self._gpu_info.device_id}" if self._gpu_info else "cuda:0"
        return "cpu"

    def get_onnx_providers(self) -> list[str]:
        """Get ONNX Runtime execution providers in priority order."""
        if self._cuda_available:
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    def clear_vram_cache(self) -> None:
        """Clear PyTorch CUDA cache to free VRAM."""
        if not self._cuda_available:
            return

        try:
            import torch
            torch.cuda.empty_cache()
            logger.debug("VRAM cache cleared")
        except Exception as e:
            logger.warning(f"Failed to clear VRAM cache: {e}")


def get_gpu_manager() -> GPUManager:
    """Get the singleton GPUManager instance."""
    return GPUManager()


def detect_gpu() -> GPUInfo | None:
    """Quick function to detect GPU and return info."""
    return get_gpu_manager().gpu_info


def is_cuda_available() -> bool:
    """Check if CUDA is available."""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False
