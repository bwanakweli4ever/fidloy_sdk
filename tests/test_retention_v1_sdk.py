"""Retention /v1 SDK surface (mocked HTTP)."""
from fidloy import Fidloy


def test_customers_upsert_v1_path() -> None:
    client = Fidloy(api_key="test-key", base_url="https://api.example.com/api")
    captured = {}

    def fake_request(method, path, *, params=None, json=None):
        captured.update(method=method, path=path, json=json)
        return {"created": True}

    client._request = fake_request  # type: ignore[method-assign]
    client.customers.upsert(
        external_customer_id="cus_1",
        first_name="A",
        last_name="B",
    )
    assert captured["method"] == "POST"
    assert captured["path"] == "/v1/customers"
    assert captured["json"]["external_customer_id"] == "cus_1"
    client.close()


def test_events_track_v1() -> None:
    client = Fidloy(api_key="test-key", base_url="https://api.example.com/api")
    captured = {}

    def fake_request(method, path, *, params=None, json=None):
        captured.update(method=method, path=path, json=json)
        return {"created": True}

    client._request = fake_request  # type: ignore[method-assign]
    client.events.track(
        external_customer_id="cus_1",
        event_type="login",
        external_event_id="evt_1",
        occurred_at="2026-09-30T12:00:00Z",
    )
    assert captured["path"] == "/v1/events"
    assert captured["json"]["event_type"] == "login"
    client.close()


def test_transactions_create_v1() -> None:
    client = Fidloy(api_key="test-key", base_url="https://api.example.com/api")
    captured = {}

    def fake_request(method, path, *, params=None, json=None):
        captured.update(method=method, path=path, json=json)
        return {"transaction_id": 1}

    client._request = fake_request  # type: ignore[method-assign]
    client.transactions.create_v1(
        external_customer_id="cus_1",
        amount=50.0,
        transaction_date="2026-09-30T12:00:00Z",
    )
    assert captured["path"] == "/v1/transactions"
    assert captured["json"]["amount"] == 50.0
    client.close()


def test_feedback_submit_v1() -> None:
    client = Fidloy(api_key="test-key", base_url="https://api.example.com/api")
    captured = {}

    def fake_request(method, path, *, params=None, json=None):
        captured.update(method=method, path=path, json=json)
        return {"feedback_id": 1}

    client._request = fake_request  # type: ignore[method-assign]
    client.feedback.submit(external_customer_id="cus_1", rating=5)
    assert captured["path"] == "/v1/feedback"
    assert captured["json"]["rating"] == 5
    client.close()


def test_retention_rules_crud_paths() -> None:
    client = Fidloy(api_key="test-key", base_url="https://api.example.com/api")
    calls = []

    def fake_request(method, path, *, params=None, json=None):
        calls.append((method, path))
        if method == "GET" and path.endswith("/rules"):
            return {"rules": []}
        if method == "POST":
            return {"id": 9}
        if method == "PATCH":
            return {"id": 9, "name": "x"}
        return {"deleted": True}

    client._request = fake_request  # type: ignore[method-assign]
    client.retention_rules.list()
    client.retention_rules.create(
        name="r",
        trigger_kind="customer_state",
        action_kind="send_sms",
        trigger_config={"state": "AT_RISK"},
    )
    client.retention_rules.get(9)
    client.retention_rules.update(9, name="x")
    client.retention_rules.deactivate(9)
    assert calls[0] == ("GET", "/v1/retention/rules")
    assert calls[1] == ("POST", "/v1/retention/rules")
    assert calls[2] == ("GET", "/v1/retention/rules/9")
    assert calls[3] == ("PATCH", "/v1/retention/rules/9")
    assert calls[4] == ("DELETE", "/v1/retention/rules/9")
    client.close()
