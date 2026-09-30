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

    def get_points_balance(
        self,
        *,
        business_id: int,
        customer_id: int,
    ) -> Dict[str, Any]:
        """Get a customer's points balance for a specific business."""
        return self._request(
            "GET",
            f"/loyalty/points/business/{business_id}/customer/{customer_id}/points",
        )

    def list_point_rules(
        self,
        *,
        business_id: int,
        rule_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List active point rules for a business."""
        params: Dict[str, Any] = {"business_id": business_id}
        if rule_type:
            params["rule_type"] = rule_type
        return _extract_list(self._request("GET", "/loyalty/points/rules", params=params))

    def list_point_rules_categorized(
        self,
        *,
        business_id: int,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """List active point rules grouped by category for a business."""
        data = self._request(
            "GET",
            "/loyalty/points/rules/categorized",
            params={"business_id": business_id},
        )
        if isinstance(data, dict):
            return data
        return {}

    def validate_coupon(
        self,
        *,
        business_id: int,
        code: str,
        amount: float,
        customer_id: Optional[int] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate coupon code applicability and discount outcome."""
        payload: Dict[str, Any] = {
            "code": code,
            "amount": amount,
        }
        if customer_id is not None:
            payload["customer_id"] = customer_id
        if phone is not None:
            payload["phone"] = phone
        if email is not None:
            payload["email"] = email

        return self._request(
            "POST",
            "/loyalty/coupons/validate",
            params={"business_id": business_id},
            json=payload,
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

    def create_v1(
        self,
        *,
        external_customer_id: str,
        amount: float,
        transaction_date: str,
        currency: str = "RWF",
        store_name: Optional[str] = None,
        description: Optional[str] = None,
        receipt_id: Optional[str] = None,
        provider: str = "default",
        business_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Record a purchase via ``POST /v1/transactions`` (external customer id)."""
        payload: Dict[str, Any] = {
            "external_customer_id": external_customer_id,
            "provider": provider,
            "amount": amount,
            "currency": currency,
            "transaction_date": transaction_date,
        }
        if business_id is not None:
            payload["business_id"] = business_id
        if store_name is not None:
            payload["store_name"] = store_name
        if description is not None:
            payload["description"] = description
        if receipt_id is not None:
            payload["receipt_id"] = receipt_id
        return self._c._request("POST", "/v1/transactions", json=payload)


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

    def upsert(
        self,
        *,
        external_customer_id: str,
        first_name: str,
        last_name: str,
        business_id: Optional[int] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        provider: str = "default",
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "external_customer_id": external_customer_id,
            "provider": provider,
            "first_name": first_name,
            "last_name": last_name,
        }
        if business_id is not None:
            payload["business_id"] = business_id
        if email is not None:
            payload["email"] = email
        if phone is not None:
            payload["phone"] = phone
        return self._c._request("POST", "/v1/customers", json=payload)

    def retention(
        self,
        external_customer_id: str,
        *,
        provider: str = "default",
        business_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        from urllib.parse import quote

        path = f"/v1/customers/{quote(external_customer_id, safe='')}/retention"
        params: Dict[str, Any] = {"provider": provider}
        if business_id is not None:
            params["business_id"] = business_id
        return self._c._request("GET", path, params=params)


class _EventsResource:
    """``client.events`` — retention event tracking (/v1/events)."""

    def __init__(self, client: FidloyClient) -> None:
        self._c = client

    def track(
        self,
        *,
        external_customer_id: str,
        event_type: str,
        external_event_id: str,
        occurred_at: str,
        amount: Optional[float] = None,
        currency: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        provider: str = "default",
        business_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "external_customer_id": external_customer_id,
            "provider": provider,
            "external_event_id": external_event_id,
            "event_type": event_type,
            "occurred_at": occurred_at,
        }
        if business_id is not None:
            payload["business_id"] = business_id
        if amount is not None:
            payload["amount"] = amount
        if currency is not None:
            payload["currency"] = currency
        if properties is not None:
            payload["properties"] = properties
        return self._c._request("POST", "/v1/events", json=payload)


class _FeedbackResource:
    """``client.feedback`` — programmatic customer feedback (``POST /v1/feedback``)."""

    def __init__(self, client: FidloyClient) -> None:
        self._c = client

    def submit(
        self,
        *,
        external_customer_id: str,
        rating: int,
        comment: Optional[str] = None,
        provider: str = "default",
        business_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "external_customer_id": external_customer_id,
            "provider": provider,
            "rating": rating,
        }
        if business_id is not None:
            payload["business_id"] = business_id
        if comment is not None:
            payload["comment"] = comment
        return self._c._request("POST", "/v1/feedback", json=payload)


class _RetentionRulesResource:
    """``client.retention_rules`` — tenant retention rule CRUD (``/v1/retention/rules``)."""

    def __init__(self, client: FidloyClient) -> None:
        self._c = client

    def list(
        self,
        *,
        business_id: Optional[int] = None,
        include_inactive: bool = False,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"include_inactive": include_inactive}
        if business_id is not None:
            params["business_id"] = business_id
        return self._c._request("GET", "/v1/retention/rules", params=params)

    def create(
        self,
        *,
        name: str,
        trigger_kind: str,
        action_kind: str,
        trigger_config: Optional[Dict[str, Any]] = None,
        action_config: Optional[Dict[str, Any]] = None,
        is_active: bool = True,
        business_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": name,
            "trigger_kind": trigger_kind,
            "action_kind": action_kind,
            "trigger_config": trigger_config or {},
            "action_config": action_config or {},
            "is_active": is_active,
        }
        if business_id is not None:
            payload["business_id"] = business_id
        return self._c._request("POST", "/v1/retention/rules", json=payload)

    def get(
        self,
        rule_id: int,
        *,
        business_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if business_id is not None:
            params["business_id"] = business_id
        return self._c._request("GET", f"/v1/retention/rules/{rule_id}", params=params or None)

    def update(
        self,
        rule_id: int,
        *,
        name: Optional[str] = None,
        trigger_kind: Optional[str] = None,
        trigger_config: Optional[Dict[str, Any]] = None,
        action_kind: Optional[str] = None,
        action_config: Optional[Dict[str, Any]] = None,
        is_active: Optional[bool] = None,
        business_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if business_id is not None:
            payload["business_id"] = business_id
        if name is not None:
            payload["name"] = name
        if trigger_kind is not None:
            payload["trigger_kind"] = trigger_kind
        if trigger_config is not None:
            payload["trigger_config"] = trigger_config
        if action_kind is not None:
            payload["action_kind"] = action_kind
        if action_config is not None:
            payload["action_config"] = action_config
        if is_active is not None:
            payload["is_active"] = is_active
        return self._c._request("PATCH", f"/v1/retention/rules/{rule_id}", json=payload)

    def deactivate(
        self,
        rule_id: int,
        *,
        business_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if business_id is not None:
            params["business_id"] = business_id
        return self._c._request(
            "DELETE",
            f"/v1/retention/rules/{rule_id}",
            params=params or None,
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

    def get_points_balance(
        self,
        *,
        business_id: int,
        customer_id: int,
    ) -> Dict[str, Any]:
        return FidloyClient.get_points_balance(
            self._c,
            business_id=business_id,
            customer_id=customer_id,
        )

    def list_point_rules(
        self,
        *,
        business_id: int,
        rule_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return FidloyClient.list_point_rules(
            self._c,
            business_id=business_id,
            rule_type=rule_type,
        )

    def list_point_rules_categorized(
        self,
        *,
        business_id: int,
    ) -> Dict[str, List[Dict[str, Any]]]:
        return FidloyClient.list_point_rules_categorized(
            self._c,
            business_id=business_id,
        )

    def validate_coupon(
        self,
        *,
        business_id: int,
        code: str,
        amount: float,
        customer_id: Optional[int] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        return FidloyClient.validate_coupon(
            self._c,
            business_id=business_id,
            code=code,
            amount=amount,
            customer_id=customer_id,
            phone=phone,
            email=email,
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
        self.events = _EventsResource(self)
        self.feedback = _FeedbackResource(self)
        self.retention_rules = _RetentionRulesResource(self)
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

    def get_points_balance(
        self,
        *,
        business_id: int,
        customer_id: int,
    ) -> Dict[str, Any]:
        """Shortcut for ``loyalty.get_points_balance``."""
        return self.loyalty.get_points_balance(
            business_id=business_id,
            customer_id=customer_id,
        )

    def list_point_rules(
        self,
        *,
        business_id: int,
        rule_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Shortcut for ``loyalty.list_point_rules``."""
        return self.loyalty.list_point_rules(
            business_id=business_id,
            rule_type=rule_type,
        )

    def list_point_rules_categorized(
        self,
        *,
        business_id: int,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Shortcut for ``loyalty.list_point_rules_categorized``."""
        return self.loyalty.list_point_rules_categorized(business_id=business_id)

    def validate_coupon(
        self,
        *,
        business_id: int,
        code: str,
        amount: float,
        customer_id: Optional[int] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Shortcut for ``loyalty.validate_coupon``."""
        return self.loyalty.validate_coupon(
            business_id=business_id,
            code=code,
            amount=amount,
            customer_id=customer_id,
            phone=phone,
            email=email,
        )


