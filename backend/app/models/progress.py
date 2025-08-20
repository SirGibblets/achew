from typing import Protocol, Optional, Dict, Any
from .enums import Step


class ProgressCallback(Protocol):
    """Protocol for progress callback functions used throughout the application.

    This protocol defines the interface for progress reporting callbacks that are
    passed to various services for status updates during processing operations.
    """

    def __call__(
        self,
        step: Step,
        percent: float,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Report progress during processing operations.

        Args:
            step: The current processing step
            percent: Progress percentage (0.0 to 100.0)
            message: Optional progress message
            details: Optional additional details about the progress
        """
        ...
