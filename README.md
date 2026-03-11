# Fidloy Python SDK

Official Python SDK for the Fidloy API.

## Install

```bash
pip install fidloy
```

`from fidloy import Fidloy` stays the same.

## Quick Start

```python
from fidloy import Fidloy

client = Fidloy(api_key="YOUR_API_KEY")

transactions = client.list_transactions(business_id=2)

for txn in transactions:
    print("ID:", txn.get("id"), "Amount:", txn.get("amount"))

client.close()
```

`base_url` is optional and already defaults to the production API.

## Simplest 2 Examples

### Example 1: Show transactions

```python
from fidloy import Fidloy

client = Fidloy(api_key="YOUR_API_KEY")

for txn in client.list_transactions(business_id=2):
    print(txn.get("id"), txn.get("amount"))

client.close()
```

### Example 2: Show customers

```python
from fidloy import Fidloy

client = Fidloy(api_key="YOUR_API_KEY")

for customer in client.list_customers(business_id=2):
    print(customer.get("id"), customer.get("first_name"), customer.get("phone"))

client.close()
```

## Also Available (Direct Client)

```python
from fidloy_sdk import FidloyClient

client = FidloyClient(api_key="YOUR_API_KEY")
customer = client.create_customer(
    first_name="Alex",
    last_name="Bwana",
    business_id=2,
    phone="+250788000000",
)
print(customer)
client.close()
```

## Main Features

- API-key authenticated requests
- Very simple `Fidloy` facade for beginners
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
