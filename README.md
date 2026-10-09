# shoppy-mcp

An MCP server and typed Python client for shopping on [Shoppy.mn](https://shoppy.mn):
search products, manage the cart, check out, and pay with SocialPay.

> **Unofficial.** This project is not affiliated with or endorsed by Shoppy.mn, Cody, or
> Golomt Bank. It uses the endpoints the public storefront web app calls, which may change
> without notice. Cart, checkout, and payment calls act on your **real account**.

## MCP server

Requires [uv](https://docs.astral.sh/uv/). Add the server to any MCP client that accepts an
`mcpServers` configuration:

```json
{
  "mcpServers": {
    "shoppy": {
      "command": "uvx",
      "args": ["shoppy-mcp"],
      "env": {
        "SHOPPY_USERNAME": "your-shoppy-login",
        "SHOPPY_PASSWORD": "your-shoppy-password"
      }
    }
  }
}
```

Credentials can also come from a dotenv file (see [`.env.example`](.env.example)):

```bash
uvx shoppy-mcp --env-file /absolute/path/to/.env
```

Environment variables take precedence over the file. The server logs in once at startup and
exits if credentials are missing or login fails. Tokens are not refreshed; restart the server
when the session expires.

### Tools

| Tool | Purpose |
| --- | --- |
| `search_products`, `get_categories` | Find in-stock products by text and category, with pagination. |
| `get_product`, `get_variant_stores` | Inspect a product by slug, choose a variant, check store stock. |
| `get_profile` | Account contact details; `detailed=true` adds saved delivery addresses. |
| `get_cart`, `add_to_cart`, `update_cart_item` | Read or change the cart; quantity zero removes a line. |
| `checkout` | Save checkout details for the current cart using the account's addresses. |
| `get_orders`, `get_order` | Order history (most recently updated first) and payment/shipping status. |
| `pay_with_socialpay` | Create a SocialPay payment for an order and return its invoice URL; optionally send it to the account's mobile. |

A typical flow:

1. `search_products(query="adidas")`, then `get_product(slug=...)` to pick a variant.
2. `add_to_cart(variant_id=..., quantity=1)` and review with `get_cart()`.
3. `checkout()`. If the account has several saved addresses and none is selected for the cart,
   select one on Shoppy first.
4. `pay_with_socialpay(number=...)` and open the returned `url`. Pass `send_to_phone=true` to
   also send the invoice to the account's mobile.
5. `get_order(number=...)` and check `paymentState`.

Things to know:

- **Only `paymentState: "paid"` confirms payment.** `phoneRequest: "PENDING"` means the request was
  sent, a `complete` order can still have a balance due, and `paidAt` can be set on a failed payment.
- **Nothing is retried automatically.** Each `pay_with_socialpay` call creates a new attempt. After a
  failed mutation, inspect the cart or order before trying again; changes may already be saved.
- Tool annotations mark read and write tools, but nothing enforces shopper confirmation.
- Responses are validated Pydantic models (`shoppy/models.py`) with the fields needed for shopping.
  Cart tokens, provider tokens, opaque payment data, and personal identifiers are omitted.
- Expected storefront failures are reported to the agent; other error details are masked.

## Python client

```bash
pip install shoppy-mcp
```

```python
from shoppy import Shoppy

shop = Shoppy()                      # or Shoppy(token="...")
shop.login("your-username", "your-password")

results = shop.search_products("adidas", limit=20)
listing = shop.product("product-slug")  # choose from listing["product"]["variantsIncludingMaster"]
cart = shop.add_to_cart("variant-id", quantity=1)
order = shop.checkout()
payment = shop.initiate_payment(order_number=order["number"], action="golomt_wallet")
shop.send_socialpay(payment["attributes"]["url"])  # optional: notify the account's mobile
status = shop.order_status(order["number"])
```

Other methods: `profile()`, `categories()`, `menus()`, `flat_categories()`, `variant_stores()`,
`current_cart()`, `update_cart_item()`, `list_orders()`, `payment_methods()`, `check_login()`.
The client returns the storefront's JSON as dictionaries.

- `checkout()` takes no arguments. It uses the account email, the cart's billing details (or the
  profile name and mobile), and the cart's shipping address or the account's only saved address.
  It saves checkout details and does not start a payment.
- `send_socialpay(url)` sends an existing SocialPay invoice to the account's mobile number, which
  must have eight digits. A `PENDING` result is not a payment confirmation.
- The access token is kept in memory and sent only to the Shoppy API. Login responses contain
  secrets; do not log them.
- A client holds one account and is not meant for concurrent use.

### Errors

- `ShoppyError` (a `ValueError`) for invalid input and unsuccessful storefront or bank responses.
  Its messages are safe to show.
- `NotFoundError` (a `ShoppyError`) when the storefront reports a missing resource. `product()`,
  `variant_stores()`, and `order_status()` return `None` instead.
- HTTP and transport errors propagate from HTTPX.

## Development

```bash
uv venv && uv pip install -e '.[dev]'
uv run pytest -q
uv run ruff check .
```

Tests use mocked HTTP and never contact Shoppy or payment services. See [AGENTS.md](AGENTS.md)
for coding and test conventions.

Releases are published to PyPI from GitHub releases by
[`.github/workflows/publish.yml`](.github/workflows/publish.yml) using trusted publishing.

## License

[MIT](LICENSE)
