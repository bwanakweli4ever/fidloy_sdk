from __future__ import annotations

import time
from typing import Any, Dict, Iterator, List, Optional

import httpx

from .exceptions import (
    FidloyAPIError,
    FidloyAuthenticationError,
    FidloyConfigurationError,
    FidloyNotFoundError,
    FidloyRateLimitError,
    FidloyTransportError,
)

# ---------------------------------------------------------------------------
# Low-level HTTP client
# ---------------------------------------------------------------------------


class FidloyClient:
    """Synchronous HTTP client for the Fidloy API.

    Args:
        api_key:       Business API key (``X-API-Key`` header).
        bearer_token:  JWT bearer token (``Authorization: Bearer …`` header).
                       Either ``api_key`` or ``bearer_token`` must be provided.
        base_url:      Override the default API base URL.
        timeout:       Per-request timeout in seconds (default 30).
        max_retries:   How many times to retry on network errors, 5xx, or 429
                       (default 3).  Set to 0 to disable retries.
        retry_delay:   Initial back-off in seconds; doubles on every retry
                       (default 0.5).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        bearer_token: Optional[str] = None,
        base_url: str = "https://api.fidloy.com/api",
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 0.5,
    ) -> None:
        if not api_key and not bearer_token:
            raise FidloyConfigurationError("Either api_key or bearer_token is required")
        if not base_url:
            raise FidloyConfigurationError("base_url must not be empty")

        self._max_retries = max_retries
        self._retry_delay = retry_delay

        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if api_key:
            headers["X-API-Key"] = api_key
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"

        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers=headers,
        )

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> "FidloyClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Core request method (with retry + structured error handling)
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Send an HTTP request, retrying on transient failures.

        Retries:
        - Network / transport errors
        - HTTP 429  (respects ``Retry-After`` header)
        - HTTP 5xx  (exponential back-off)

        Raises:
            FidloyAuthenticationError: 401 / 403
            FidloyNotFoundError:       404
            FidloyRateLimitError:      429 after all retries
            FidloyAPIError:            other 4xx / 5xx after all retries
            FidloyTransportError:      network failure after all retries
        """
        last_exc: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.request(
                    method=method, url=path, params=params, json=json
                )
            except httpx.HTTPError as exc:
                last_exc = FidloyTransportError(str(exc))
                if attempt < self._max_retries:
                    time.sleep(self._retry_delay * (2 ** attempt))
                    continue
                raise last_exc from exc

            # ---- Rate limit (429) -----------------------------------------------
            if response.status_code == 429:
                raw_retry = response.headers.get("Retry-After")
                retry_after = float(raw_retry) if raw_retry else self._retry_delay * (2 ** attempt)
                if attempt < self._max_retries:
                    time.sleep(retry_after)
                    continue
                body = _safe_parse(response)
                raise FidloyRateLimitError(retry_after=retry_after, response_body=body)

            # ---- Server errors (5xx) — retry ------------------------------------
            if response.status_code >= 500 and attempt < self._max_retries:
                time.sleep(self._retry_delay * (2 ** attempt))
                continue

            # ---- Client / server errors — raise ---------------------------------
            if response.status_code >= 400:
                body = _safe_parse(response)
                message = (
                    body.get("detail", "API request failed")
                    if isinstance(body, dict)
                    else str(body)
                )
                if response.status_code in (401, 403):
                    raise FidloyAuthenticationError(response.status_code, message, body)
                if response.status_code == 404:
                    raise FidloyNotFoundError(response.status_code, message, body)
                raise FidloyAPIError(response.status_code, message, body)

            # ---- Success --------------------------------------------------------
            try:
                data = response.json()
            except ValueError as exc:
                raise FidloyAPIError(
                    response.status_code, "Invalid JSON response", response.text
                ) from exc

            return data if isinstance(data, (dict, list)) else {"data": data}

        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # High-level API methods
    # ------------------------------------------------------------------

    def get_rewards_history(
        self,
        business_id: int,
        *,
        customer_id: Optional[int] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        event_type: str = "reward_redeemed",
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"event_type": event_type, "page": page, "page_size": page_size}
        if customer_id is not None:
            params["customer_id"] = customer_id
        if phone:
            params["phone"] = phone
        if email:
            params["email"] = email
        return self._request("GET", f"/loyalty/accounts/{business_id}/rewards-history", params=params)

    def create_customer(
        self,
        *,
        first_name: str,
        last_name: str,
        business_id: int,
        email: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "first_name": first_name,
            "last_name": last_name,
            "business_id": business_id,
        }
        if email is not None:
            payload["email"] = email
        if phone is not None:
            payload["phone"] = phone
        return self._request("POST", "/customer/", json=payload)

    def create_transaction(
        self,
        *,
        customer_id: int,
        business_id: int,
        amount: float,
        store_name: str,
        transaction_date: str,
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/customer/transactions/",
            json={
                "customer_id": customer_id,
                "business_id": business_id,
                "amount": amount,
                "store_name": store_name,
                "transaction_date": transaction_date,
            },
        )

    def create_receipt(
        self,
        *,
        customer_id: int,
        business_id: int,
        store_name: str,
        total_amount: float,
        date: str,
        receipt_number: str,
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/receipt/create",
            json={
                "customer_id": customer_id,
                "business_id": business_id,
                "store_name": store_name,
                "total_amount": total_amount,
                "date": date,
                "receipt_number": receipt_number,
            },
        )

    def create_webhook(
        self,
        *,
        business_id: int,
        target_url: str,
        events: List[str],
        is_active: bool = True,
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/webhooks",
            json={
                "business_id": business_id,
                "target_url": target_url,
                "events": events,
                "is_active": is_active,
            },
        )

    def redeem_points(
        self,
        *,
        business_id: int,
        points: int,
        customer_id: Optional[int] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"business_id": business_id, "points": points}
        if customer_id is not None:
            payload["customer_id"] = customer_id
        if phone is not None:
            payload["phone"] = phone
        if email is not None:
            payload["email"] = email
        if description is not None:
            payload["description"] = description
        return self._request("POST", "/loyalty/points/redeem", json=payload)

    def redeem_coupon(
        self,
        *,
        coupon_code: str,
        business_id: int,
        customer_id: Optional[int] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        transaction_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"coupon_code": coupon_code, "business_id": business_id}
        if customer_id is not None:
            payload["customer_id"] = customer_id
        if phone is not None:
            payload["phone"] = phone
        if email is not None:
            payload["email"] = email
        if transaction_id is not None:
            payload["transaction_id"] = transaction_id
        return self._request("POST", "/loyalty/coupons/redeem", json=payload)

    def get_customer_rewards_history(
        self,
        business_id: int,
        customer_id: int,
        *,
        event_type: str = "reward_redeemed",
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        return self._request(
            "GET",
            f"/loyalty/accounts/{business_id}/customers/{customer_id}/rewards-history",
            params={"event_type": event_type, "page": page, "page_size": page_size},
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_parse(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _extract_list(data: Any) -> List[Dict[str, Any]]:
    """Normalise whatever the API returns into a plain list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "data", "transactions", "customers", "results"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


# ---------------------------------------------------------------------------
# Structured API resource modules
# ---------------------------------------------------------------------------


class _TransactionsResource:
    """``client.transactions`` — manage customer transactions."""

    def __init__(self, client: FidloyClient) -> None:
        self._c = client

    def list(
        self,
        *,
        business_id: int,
        limit: int = 100,
        skip: int = 0,
        customer_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return up to *limit* transactions (offset by *skip*)."""
        params: Dict[str, Any] = {"business_id": business_id, "limit": limit, "skip": skip}
        if customer_id is not None:
            params["customer_id"] = customer_id
        return _extract_list(self._c._request("GET", "/customer/transactions/", params=params))

    def paginate(
        self,
        *,
        business_id: int,
        page_size: int = 100,
        customer_id: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yield every transaction across all pages automatically.

        Example::

            for txn in client.transactions.paginate(business_id=2):
                print(txn["amount"])
        """
        skip = 0
        while True:
            page = self.list(
                business_id=business_id,
                limit=page_size,
                skip=skip,
                customer_id=customer_id,
            )
            if not page:
                break
            yield from page
            if len(page) < page_size:
                break
            skip += page_size

    def create(
        self,
        *,
        customer_id: int,
        business_id: int,
        amount: float,
        store_name: str,
        transaction_date: str,
    ) -> Dict[str, Any]:
        return self._c.create_transaction(
            customer_id=customer_id,
            business_id=business_id,
            amount=amount,
            store_name=store_name,
            transaction_date=transaction_date,
        )


class _CustomersResource:
    """``client.customers`` — manage customers."""

    def __init__(self, client: FidloyClient) -> None:
        self._c = client

    def list(
        self,
        *,
        business_id: int,
        limit: int = 100,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """Return up to *limit* customers (offset by *skip*)."""
        return _extract_list(
            self._c._request(
                "GET",
                "/customer/",
                params={"business_id": business_id, "limit": limit, "skip": skip},
            )
        )

    def paginate(
        self,
        *,
        business_id: int,
        page_size: int = 100,
    ) -> Iterator[Dict[str, Any]]:
        """Yield every customer across all pages automatically.

        Example::

            for customer in client.customers.paginate(business_id=2):
                print(customer["phone"])
        """
        skip = 0
        while True:
            page = self.list(business_id=business_id, limit=page_size, skip=skip)
            if not page:
                break
            yield from page
            if len(page) < page_size:
                break
            skip += page_size

    def create(
        self,
        *,
        first_name: str,
        last_name: str,
        business_id: int,
        email: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._c.create_customer(
            first_name=first_name,
            last_name=last_name,
            business_id=business_id,
            email=email,
            phone=phone,
        )


class _LoyaltyResource:
    """``client.loyalty`` — loyalty points and coupons."""

    def __init__(self, client: FidloyClient) -> None:
        self._c = client

    def redeem_points(
        self,
        *,
        business_id: int,
        points: int,
        customer_id: Optional[int] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._c.redeem_points(
            business_id=business_id,
            points=points,
            customer_id=customer_id,
            phone=phone,
            email=email,
            description=description,
        )

    def redeem_coupon(
        self,
        *,
        coupon_code: str,
        business_id: int,
        customer_id: Optional[int] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        transaction_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self._c.redeem_coupon(
            coupon_code=coupon_code,
            business_id=business_id,
            customer_id=customer_id,
            phone=phone,
            email=email,
            transaction_id=transaction_id,
        )

    def get_rewards_history(
        self,
        business_id: int,
        *,
        customer_id: Optional[int] = None,
        event_type: str = "reward_redeemed",
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        return self._c.get_rewards_history(
            business_id,
            customer_id=customer_id,
            event_type=event_type,
            page=page,
            page_size=page_size,
        )


class _ReceiptsResource:
    """``client.receipts`` — receipt management."""

    def __init__(self, client: FidloyClient) -> None:
        self._c = client

    def create(
        self,
        *,
        customer_id: int,
        business_id: int,
        store_name: str,
        total_amount: float,
        date: str,
        receipt_number: str,
    ) -> Dict[str, Any]:
        return self._c.create_receipt(
            customer_id=customer_id,
            business_id=business_id,
            store_name=store_name,
            total_amount=total_amount,
            date=date,
            receipt_number=receipt_number,
        )


class _WebhooksResource:
    """``client.webhooks`` — webhook subscriptions."""

    def __init__(self, client: FidloyClient) -> None:
        self._c = client

    def create(
        self,
        *,
        business_id: int,
        target_url: str,
        events: List[str],
        is_active: bool = True,
    ) -> Dict[str, Any]:
        return self._c.create_webhook(
            business_id=business_id,
            target_url=target_url,
            events=events,
            is_active=is_active,
        )


# ---------------------------------------------------------------------------
# Beginner-friendly facade
# ---------------------------------------------------------------------------


class Fidloy(FidloyClient):
    """Beginner-friendly Fidloy SDK facade.

    Provides structured sub-modules, automatic retries, pagination helpers,
    and a clean error hierarchy out of the box.

    Quick start::

        from fidloy import Fidloy

        client = Fidloy(api_key="fidl_...")

        # Structured modules
        for txn in client.transactions.paginate(business_id=2):
            print(txn["amount"])

        # Or flat shortcuts
        txns = client.list_transactions(business_id=2)

    Args:
        api_key:      Business API key.
        bearer_token: JWT bearer token (alternative to api_key).
        base_url:     Override the API base URL.
        timeout:      Request timeout in seconds (default 30).
        max_retries:  Retries on network / 5xx / 429 errors (default 3).
        retry_delay:  Initial back-off in seconds (default 0.5, doubles each retry).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        bearer_token: Optional[str] = None,
        base_url: str = "https://api.fidloy.com/api",
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 0.5,
    ) -> None:
        super().__init__(
            api_key=api_key,
            bearer_token=bearer_token,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )
        # Structured API modules
        self.transactions = _TransactionsResource(self)
        self.customers = _CustomersResource(self)
        self.loyalty = _LoyaltyResource(self)
        self.receipts = _ReceiptsResource(self)
        self.webhooks = _WebhooksResource(self)

    # ------------------------------------------------------------------
    # Flat shortcut methods (backwards compatible)
    # ------------------------------------------------------------------

    def list_transactions(
        self,
        business_id: int,
        limit: int = 100,
        skip: int = 0,
        customer_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return up to *limit* transactions. Use ``transactions.paginate()`` for all pages."""
        return self.transactions.list(
            business_id=business_id, limit=limit, skip=skip, customer_id=customer_id
        )

    def list_customers(
        self,
        business_id: int,
        limit: int = 100,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """Return up to *limit* customers. Use ``customers.paginate()`` for all pages."""
        return self.customers.list(business_id=business_id, limit=limit, skip=skip)


