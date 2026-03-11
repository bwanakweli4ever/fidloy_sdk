import inspect
from fidloy_sdk import (
    Fidloy, FidloyClient, FidloyError, FidloyAPIError,
    FidloyAuthenticationError, FidloyNotFoundError,
    FidloyRateLimitError, FidloyTransportError, FidloyConfigurationError,
)
from fidloy import Fidloy as FidloyAlias

# 1. Config error raised when no credentials
try:
    Fidloy()
    raise AssertionError("Expected FidloyConfigurationError")
except FidloyConfigurationError:
    pass

# 2. Bearer token auth
c = Fidloy(bearer_token="test.jwt")

# 3. Structured modules exist
assert hasattr(c, "transactions"), "transactions module missing"
assert hasattr(c, "customers"),    "customers module missing"
assert hasattr(c, "loyalty"),      "loyalty module missing"
assert hasattr(c, "receipts"),     "receipts module missing"
assert hasattr(c, "webhooks"),     "webhooks module missing"

# 4. Pagination methods are generators
assert inspect.isgeneratorfunction(c.transactions.paginate), "transactions.paginate not a generator"
assert inspect.isgeneratorfunction(c.customers.paginate),    "customers.paginate not a generator"

# 5. Error class hierarchy
assert issubclass(FidloyAuthenticationError, FidloyAPIError)
assert issubclass(FidloyNotFoundError,       FidloyAPIError)
assert issubclass(FidloyRateLimitError,      FidloyAPIError)
assert issubclass(FidloyAPIError,            FidloyError)
assert issubclass(FidloyTransportError,      FidloyError)

# 6. RateLimitError fields
r = FidloyRateLimitError(retry_after=10.0)
assert r.retry_after == 10.0, f"retry_after wrong: {r.retry_after}"
assert r.status_code == 429,  f"status_code wrong: {r.status_code}"

# 7. Alias import works
c2 = FidloyAlias(api_key="test")
assert isinstance(c2, Fidloy)

print("All Python SDK tests passed ✓")
