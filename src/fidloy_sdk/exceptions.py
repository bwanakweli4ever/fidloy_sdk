from typing import Any, Optional


class FidloyError(Exception):
    """Base exception for all Fidloy SDK errors."""


class FidloyConfigurationError(FidloyError):
    """Raised when SDK configuration is invalid (e.g. missing api_key)."""


class FidloyTransportError(FidloyError):
    """Raised when the HTTP request fails before a response is received (network error)."""


class FidloyAPIError(FidloyError):
    """Raised when the Fidloy API returns a non-success HTTP status code.

    Attributes:
        status_code: The HTTP status code returned by the API.
        message:     Human-readable error description.
        response_body: Raw parsed response body (dict or str).
    """

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


class FidloyAuthenticationError(FidloyAPIError):
    """Raised on 401 Unauthorized or 403 Forbidden.
    Check your api_key or bearer_token.
    """


class FidloyNotFoundError(FidloyAPIError):
    """Raised on 404 Not Found."""


class FidloyRateLimitError(FidloyAPIError):
    """Raised on 429 Too Many Requests after all retries are exhausted.

    Attributes:
        retry_after: Seconds to wait before retrying, if provided by the server.
    """

    def __init__(
        self,
        retry_after: Optional[float] = None,
        response_body: Optional[Any] = None,
    ) -> None:
        self.retry_after = retry_after
        msg = "Rate limit exceeded"
        if retry_after is not None:
            msg += f". Retry after {retry_after:.1f}s"
        super().__init__(429, msg, response_body)
