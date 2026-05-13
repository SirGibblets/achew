"""
ASR Service Providers

This package contains all ASR service implementations that auto-register
themselves with the ASR service registry.
"""

# Import all provider modules to trigger auto-registration
from . import parakeet_mlx_service, parakeet_service, whisper_cpp_service, whisper_mlx_service

__all__ = [
    "parakeet_service",
    "whisper_cpp_service",
    "parakeet_mlx_service",
    "whisper_mlx_service",
]
