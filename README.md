# Fidloy Python SDK

Official Python SDK for the Fidloy API.

## Install

```bash
pip install fidloy-sdk
```

## Quick Start

```python
from fidloy_sdk import FidloyClient

client = FidloyClient(
    api_key="YOUR_API_KEY",
    base_url="https://api.fidloy.com/api"
)

history = client.get_rewards_history(
    business_id=1,
    customer_id=123,
    event_type="reward_redeemed",
    page=1,
    page_size=20,
)

print(history)

customer = client.create_customer(
    first_name="Alex",
    last_name="Bwana",
    email="alex@example.com",
    phone="+250788000000",
    business_id=1,
)

tx = client.create_transaction(
    customer_id=customer.get("id", 123),
    business_id=1,
    amount=15000,
    store_name="Main Branch",
    transaction_date="2026-03-11T12:00:00Z",
)

client.close()
```

## Main Features

- API-key authenticated requests
- Customer-in-business reward history helper methods
- Customer and transaction creation helpers
- Points and coupon redemption helpers
- Receipt and webhook creation helpers
- Typed, predictable exceptions
- Configurable timeout and headers

## Core Methods

- `get_rewards_history`
- `get_customer_rewards_history`
- `create_customer`
- `create_transaction`
- `create_receipt`
- `create_webhook`
- `redeem_points`
- `redeem_coupon`

## Publish to PyPI

### Recommended: Trusted Publishing (GitHub Actions)

Follow [PYPI_RELEASE_CHECKLIST.md](PYPI_RELEASE_CHECKLIST.md) to configure PyPI Trusted Publisher.

Then publish by creating a GitHub Release for your version tag.

### Manual upload (fallback)

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine upload dist/*
```

Use a PyPI token when uploading.
# fidloy_sdk
