import pytest

from fidloy_sdk import Fidloy, FidloyClient, FidloyConfigurationError


def test_requires_api_key() -> None:
    with pytest.raises(FidloyConfigurationError):
        FidloyClient(api_key="")


def test_customer_rewards_history_path() -> None:
    client = FidloyClient(api_key="test-key", base_url="https://api.example.com")
    captured = {}

    def fake_request(method, path, *, params=None, json=None):
        captured["method"] = method
        captured["path"] = path
        captured["params"] = params
        captured["json"] = json
        return {"ok": True}

    client._request = fake_request
    result = client.get_customer_rewards_history(business_id=1, customer_id=99)

    assert result["ok"] is True
    assert captured["method"] == "GET"
    assert captured["path"] == "/loyalty/accounts/1/customers/99/rewards-history"
    assert captured["params"]["event_type"] == "reward_redeemed"
    client.close()


def test_create_customer_payload() -> None:
    client = FidloyClient(api_key="test-key", base_url="https://api.example.com")
    captured = {}

    def fake_request(method, path, *, params=None, json=None):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = json
        return {"id": 1}

    client._request = fake_request
    result = client.create_customer(
        first_name="Alex",
        last_name="Bwana",
        business_id=1,
        email="alex@example.com",
    )

    assert result["id"] == 1
    assert captured["method"] == "POST"
    assert captured["path"] == "/customer/"
    assert captured["json"]["first_name"] == "Alex"
    assert captured["json"]["business_id"] == 1
    client.close()


def test_simple_fidloy_transactions_list() -> None:
    client = Fidloy(api_key="test-key")
    captured = {}

    def fake_request(method, path, *, params=None, json=None):
        captured["method"] = method
        captured["path"] = path
        captured["params"] = params
        return {"items": [{"id": 1, "amount": 1000}]}

    client._request = fake_request
    items = client.transactions.list(business_id=2)

    assert items == [{"id": 1, "amount": 1000}]
    assert captured["method"] == "GET"
    assert captured["path"] == "/customer/transactions/"
    assert captured["params"]["business_id"] == 2
    client.close()
