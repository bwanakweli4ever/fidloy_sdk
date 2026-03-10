from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from .exceptions import (
    FidloyAPIError,
    FidloyConfigurationError,
    FidloyTransportError,
)


class FidloyClient:
    """Simple synchronous client for the Fidloy API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.fidloy.com/api",
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise FidloyConfigurationError("api_key is required")
        if not base_url:
            raise FidloyConfigurationError("base_url is required")

        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={
                "X-API-Key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "FidloyClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            response = self._client.request(method=method, url=path, params=params, json=json)
        except httpx.HTTPError as exc:
            raise FidloyTransportError(str(exc)) from exc

        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text
            message = payload.get("detail", "API request failed") if isinstance(payload, dict) else str(payload)
            raise FidloyAPIError(response.status_code, message, payload)

        try:
            data = response.json()
        except ValueError as exc:
            raise FidloyAPIError(response.status_code, "Invalid JSON response", response.text) from exc

        if not isinstance(data, dict):
            return {"data": data}
        return data

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
        params: Dict[str, Any] = {
            "event_type": event_type,
            "page": page,
            "page_size": page_size,
        }
        if customer_id is not None:
            params["customer_id"] = customer_id
        if phone:
            params["phone"] = phone
        if email:
            params["email"] = email

        return self._request(
            "GET",
            f"/loyalty/accounts/{business_id}/rewards-history",
            params=params,
        )

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
        payload: Dict[str, Any] = {
            "customer_id": customer_id,
            "business_id": business_id,
            "amount": amount,
            "store_name": store_name,
            "transaction_date": transaction_date,
        }
        return self._request("POST", "/customer/transactions/", json=payload)

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
        payload: Dict[str, Any] = {
            "customer_id": customer_id,
            "business_id": business_id,
            "store_name": store_name,
            "total_amount": total_amount,
            "date": date,
            "receipt_number": receipt_number,
        }
        return self._request("POST", "/receipt/create", json=payload)

    def create_webhook(
        self,
        *,
        business_id: int,
        target_url: str,
        events: list[str],
        is_active: bool = True,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "business_id": business_id,
            "target_url": target_url,
            "events": events,
            "is_active": is_active,
        }
        return self._request("POST", "/webhooks", json=payload)

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
        payload: Dict[str, Any] = {
            "business_id": business_id,
            "points": points,
        }
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
        payload: Dict[str, Any] = {
            "coupon_code": coupon_code,
            "business_id": business_id,
        }
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
        params: Dict[str, Any] = {
            "event_type": event_type,
            "page": page,
            "page_size": page_size,
        }

        return self._request(
            "GET",
            f"/loyalty/accounts/{business_id}/customers/{customer_id}/rewards-history",
            params=params,
        )
