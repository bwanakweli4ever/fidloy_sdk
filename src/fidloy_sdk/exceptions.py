from typing import Any, Optional


class FidloyError(Exception):
    """Base exception for all Fidloy SDK errors."""


class FidloyAPIError(FidloyError):
    """Raised when the Fidloy API returns a non-success status code."""

    def __init__(
        self,
        status_code: int,
        message: str,
        response_body: Optional[Any] = None,
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.response_body = response_body
        super().__init__(f"[{status_code}] {message}")


class FidloyTransportError(FidloyError):
    """Raised when the HTTP request fails before receiving a response."""


class FidloyConfigurationError(FidloyError):
    """Raised when SDK configuration is invalid."""
