# Shoppy Python client

A synchronous, typed `Shoppy` client organized into client, query, and model modules. Implements the storefront operations observed in `shoppy.mn.har`; it is not a FastAPI server.

Install with `pip install -e .`. Python 3.10+ is required.

```python
from shoppy import Shoppy

with Shoppy() as shop:
    shop.login_from_env()  # Reads USER and PASS from .env, not the shell USER
    profile = shop.me()
    categories = shop.categories()
    children = shop.categories(parent_id=categories[0]["id"])
    results = shop.search_products("adidas", limit=20, offset=0)
    category_results = shop.search_products(category_id=categories[0]["id"])
    cart = shop.current_order()
```

Alternatively use `Shoppy(token="...")` or `shop.login(username, password, basic_auth="Basic ...")`.
Set `SHOPPY_BASIC_AUTH="Basic ..."` in `.env` alongside `USER` and `PASS`. The login Basic header is sent only to the OAuth token endpoint. Set `SHOPPY_SEARCH_AUTH="Basic ..."` for Elasticsearch search, or pass `Shoppy(search_auth="Basic ...")`. Search uses its own Basic header, never the API Bearer token.

Login retains the returned access token in memory and sends `Authorization: Bearer <token>` only to `api3.cody.mn`. Token refresh is not automatic; log in again when the token expires. Returned login data includes secrets: do not log it.

## Cart and checkout

Choose a product and variant explicitly. These calls change the real account's cart and create an unpaid order.

```python
with Shoppy() as shop:
    shop.login_from_env()
    listing = shop.product("your-product-slug")
    # Inspect listing["product"]["variantsIncludingMaster"] for the desired variant.
    cart = shop.add_to_cart("chosen-variant-id", quantity=1)
    # shop.update_cart_item(line_item_id, quantity=0) removes a line item.
    submitted = shop.checkout(
        email="your-email@example.com",
        billing_address={
            "firstname": "Your first name",
            "lastname": "Your last name",
            "phone": "Your phone",
            "isCompany": False,
        },
    )
    payment = shop.initiate_payment(action="m_bank_card")
    # payment contains provider handoff data for your application.
    order = shop.order(cart["number"])
```

`current_order(number=..., token=...)` can attach an existing cart. Cart handles are retained in memory after retrieval and additions. With no current cart, addition sends null handles; that path needs live validation because the HAR starts with an existing cart.

`checkout()` saves billing/shipping details and then submits the order, returning `{"order": ..., "paymentAction": ...}`. It also accepts `number`, `shipping_address`, `shipping_address_id`, `shipping_method_id`, and `action` (default `"qpay_merchant"`). Submission runs only after the update succeeds. These are two API requests: if submission fails, the saved details remain.

`payment_methods()` lists available providers. `initiate_payment(action=...)` returns the provider response, including the data your application needs to open the payment provider. For M Bank this includes a URL, SessionID, and OrderID for a POST form; SocialPay returns a GET URL. The client does not fetch or open payment pages.

Orders marked `complete` may still have `paymentState: balance_due`. Check `paidAt` and payment state rather than treating submission as payment success.

## Errors

HTTP and transport errors propagate directly from HTTPX. Invalid inputs and unsuccessful or malformed API responses raise standard `ValueError` exceptions. Requests are not automatically retried, and failures do not block subsequent calls.

`.env` is ignored by Git. Do not publish the HAR, tokens, returned bank session data, or payment-page HTML.

## List orders

`orders()` returns a GraphQL connection containing `edges`, `totalCount`, and `pageInfo`. It defaults to 10 orders sorted by `updated_at` descending, without status or shipment filters. It does not change the current cart.

```python
with Shoppy() as shop:
    shop.login_from_env()
    page = shop.orders(first=10)
    orders = [edge["node"] for edge in page["edges"]]
    if page["pageInfo"]["hasNextPage"]:
        next_page = shop.orders(first=10, cursor=page["pageInfo"]["endCursor"])

    # Optional filter and sort, using fields observed in the HAR:
    pending = shop.orders(
        filter={
            "state": {"in": ["complete", "resumed"]},
            "shipmentState": {"in": ["backorder", "partial", "pending", "ready"]},
        },
        sort={"field": "updated_at", "direction": "desc"},
    )
```

An optional `status` string is passed through as the API's `OrderStatus` enum; its allowed values were not captured. Each node includes order number, totals, payment/shipment states, timestamps, and line items. Use `order(number)` for full details.

## SocialPay mobile requests

The SocialPay capture initializes payment through the existing `orderPay` mutation with `action="golomt_wallet"`. `initiate_socialpay()` provides a named convenience method:

```python
with Shoppy() as shop:
    shop.login_from_env()
    payment = shop.initiate_socialpay(number="your-order-number")
    result = shop.send_payment_to_mobile(
        payment,
        phone="9911 2233",  # Replace with the intended recipient's number.
        bank_token="your-bank-session-token",
    )
```

`send_payment_to_mobile` sends a real payment request to the supplied phone. It fetches invoice details, prepares the mobile request, checks the new SocialPay session, and sends the returned opaque payload once. A successful send returns `status: PENDING` and `refToken`; that is not confirmation of payment. The client does not approve payment or poll for completion.

The bank Bearer token is separate from the Shoppy token. The method uses an explicitly supplied `bank_token`, or the token returned by `/payment/get/details`. In the capture, payment details contain an empty token; the bank JavaScript falls back to browser local storage. Supply that bank-session token when necessary. The client never substitutes Shoppy credentials for bank credentials.

Only the captured `newSpCheckSession` response `desc: Y` flow is implemented. A different session result stops before sending; the alternate legacy/WebSocket flow is not implemented. Provider errors raise standard exceptions with no automatic retries.
