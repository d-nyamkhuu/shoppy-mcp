"""Synchronous storefront client with explicit checkout and payment steps."""

from typing import Any
from urllib.parse import urlsplit

import httpx

from . import queries
from .models import JSON

# Public client headers sent by the shoppy.mn web app; they do not identify an account.
LOGIN_AUTH = "Basic MmI1ZWYyYWQ3ODE0MGMzMTJkYTZjODdhM2ZmMTk3MDJkM2ZjOTk1ODM4NTFjMmU0NDBiMTAyNDA5ZDQ4NmFiMDozMzljYTdiMDg4YjBkYWIwN2E0NDNmMDM1NTZlZDdiYmNmMzEwMTUxNDI4NmY0ODQ0MzI4Yzg4N2JkODQ2ZGE4"
SEARCH_AUTH = "Basic Z3Vlc3Q6U2hvcHB5R3Vlc3Q="
SHOPPY_HEADERS = {"Referer": "https://shoppy.mn/", "Origin": "https://shoppy.mn"}
SEARCH_WINDOW = 10000


class ShoppyError(ValueError):
    """An expected storefront or payment failure whose message is safe to show."""


class NotFoundError(ShoppyError):
    """The storefront reported that a requested resource does not exist."""


class Shoppy:
    """Access Shoppy using a Bearer token or :meth:`login`.

    A client retains one account and is not intended for concurrent use.
    Failed requests are never retried automatically, especially mutations.
    """

    def __init__(self, *, token: str | None = None, timeout: float = 30.0) -> None:
        """Configure authentication and the timeout for each request."""
        self._timeout = timeout
        self._token = token.removeprefix("Bearer ") if token else None

    def _graphql(self, query: str, variables: JSON | None = None) -> JSON:
        """Execute a GraphQL operation and return its data."""
        headers = dict(SHOPPY_HEADERS)
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        response = httpx.post(
            "https://api3.cody.mn/graphql", headers=headers, timeout=self._timeout,
            json={"query": query, "variables": variables},
        )
        response.raise_for_status()
        result = response.json()
        errors = result.get("errors")
        if errors:
            messages = [error.get("message", "") for error in errors]
            if all("not found" in message for message in messages):
                raise NotFoundError("Shoppy could not find the requested item.")
            if all("үлдэгдэлгүй" in message for message in messages):
                raise ShoppyError("Shoppy reports the selected variant is out of stock.")
            raise ShoppyError("GraphQL reported an error.")
        return result["data"]

    def _search(self, body: JSON) -> JSON:
        """Search the product index and return the JSON response."""
        headers = {**SHOPPY_HEADERS, "Authorization": SEARCH_AUTH}
        response = httpx.post(
            "https://elastic.cody.mn/shoppy/_search",
            headers=headers, json=body, timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()

    def _bank_request(self, path: str, payload: JSON, *, url: str, token: str | None = None) -> JSON:
        """Send a bank request and return the JSON response."""
        headers = {"Origin": "https://ecommerce.golomtbank.com", "Referer": url}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = httpx.post(
            f"https://ecommerce.golomtbank.com{path}",
            headers=headers, json=payload, timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _check_bank_header(result: JSON) -> None:
        """Reject a bank response whose header reports a failure."""
        if result["header"]["code"] != 200 or result["header"]["status"] != "success":
            error = result["body"]["error"]
            raise ShoppyError(f"Payment provider reported an error: {error['errorDesc']}")

    def check_login(self, login: str) -> JSON:
        """Check whether a login identifier is registered."""
        return self._graphql(queries.CHECK_LOGIN, {"login": login, "no_token": True})["exists"]

    def login(self, username: str, password: str) -> JSON:
        """Authenticate and retain the access token; never persist credentials."""
        response = httpx.post(
            "https://api3.cody.mn/oauth/token",
            headers={**SHOPPY_HEADERS, "Authorization": LOGIN_AUTH},
            data={"username": username, "password": password, "grant_type": "password"},
            timeout=self._timeout,
        )
        response.raise_for_status()
        result = response.json()
        if not result["access_token"]:
            raise ShoppyError("Login response omitted access_token.")
        self._token = result["access_token"]
        return result

    def profile(self, *, detailed: bool = False) -> JSON:
        """Return the account profile, optionally including saved addresses."""
        return self._graphql(queries.DETAILED_ME if detailed else queries.ME)["me"]

    def search_products(
        self, query: str = "", *, category_id: str | None = None,
        limit: int = 30, offset: int = 0,
    ) -> JSON:
        """Return search hits and totals, optionally restricted to a category."""
        if offset + limit > SEARCH_WINDOW:
            raise ShoppyError(f"Search covers only the first {SEARCH_WINDOW} results; offset + limit must not exceed {SEARCH_WINDOW}.")
        must: list[JSON] = [
            {"range": {"selling_price": {"gt": 1}}},
            {"range": {"total_on_hand": {"gt": 0}}},
            {"range": {"available_on": {"lte": "now"}}},
            {"exists": {"field": "image"}},
        ]
        if query:
            fields = ["sku^10", "store.name^9", "keyword.name^8", "keyword.mn^7",
                      "keyword.alias^7", "title_latin^6", "title^4", "name^2",
                      "gendric^1", "description^1"]
            must.append({"bool": {"minimum_should_match": 1, "should": [
                {"simple_query_string": {"query": query, "fields": fields}},
                {"multi_match": {"query": query, "type": "phrase_prefix", "fields": fields[1:]}},
            ]}})
        if category_id:
            must.append({"nested": {"path": "taxonomy", "query": {
                "term": {"taxonomy.id": category_id},
            }}})
        result = self._search({
            "query": {"bool": {"must": must}}, "size": limit, "from": offset,
            "sort": [{"_score": "desc"}],
            "_source": ["id", "slug", "name", "title", "price", "selling_price", "total_on_hand", "image"],
        })
        return {"hits": {
            "total": result["hits"]["total"],
            "hits": [
                {key: value for key, value in hit.items() if key in {"_id", "_source"}}
                for hit in result["hits"]["hits"]
            ],
        }}

    def menus(self) -> list[JSON]:
        """Return the storefront navigation menus."""
        return self._graphql(queries.MENUS)["menus"]

    def flat_categories(self) -> Any:
        """Return the flat category listing."""
        return self._graphql(queries.FLAT_TAXONS)["flatTaxon"]

    def categories(self, parent_id: str | None = None) -> list[JSON]:
        """Return root categories or the children of a selected category."""
        document = queries.ROOT_TAXONS if parent_id is None else queries.CHILD_TAXONS
        return self._graphql(document, {"parentId": parent_id})["taxons"]["nodes"]

    def product(self, slug: str) -> JSON | None:
        """Return a product listing and its variants by slug."""
        try:
            return self._graphql(queries.PRODUCT, {"slug": slug})["listing"]
        except NotFoundError:
            return None

    def variant_stores(self, variant_id: str) -> JSON | None:
        """Return stock levels and store locations for a variant."""
        try:
            return self._graphql(queries.VARIANT_STORES, {"variantId": variant_id})["variant"]
        except NotFoundError:
            return None

    def current_cart(self) -> JSON | None:
        """Return the account's active cart, or None if no cart exists."""
        return self._graphql(queries.CURRENT_ORDER)["currentOrder"]

    def add_to_cart(self, variant_id: str, *, quantity: int = 1) -> JSON:
        """Add a variant to the current cart and return the updated cart."""
        if quantity < 1:
            raise ShoppyError("Quantity must be at least one when adding to the cart.")
        order = self.current_cart()
        return self._graphql(queries.ADD_TO_CART, {
            "number": order["number"] if order else None,
            "token": order["token"] if order else None,
            "batch": [{"variantId": variant_id, "quantity": quantity}],
        })["order"]

    def update_cart_item(self, line_item_id: str, *, quantity: int) -> JSON:
        """Set quantity; zero removes the line item."""
        if quantity < 0:
            raise ShoppyError("Quantity must be zero or greater when updating the cart.")
        return self._graphql(queries.UPDATE_ITEM, {
            "input": {"id": line_item_id, "quantity": quantity},
        })["updateItem"]

    def checkout(self) -> JSON:
        """Save checkout details using the current cart and account addresses."""
        order = self.current_cart()
        if not order or not order["lineItems"]:
            raise ShoppyError("Cannot check out an empty order.")
        profile = self.profile(detailed=True)
        if not profile["email"]:
            raise ShoppyError("The account needs an email address before checkout.")
        billing_address = order["billAddress"]
        if billing_address is None:
            billing_address = {
                "firstname": profile["firstName"], "lastname": profile["lastName"],
                "phone": profile["mobile"], "isCompany": False,
            }
        shipping_address_id = None
        if not order["digital"]:
            if order["shipAddress"] is not None:
                shipping_address_id = order["shipAddress"]["id"]
            else:
                addresses = profile["userAddresses"]["nodes"]
                if not addresses:
                    raise ShoppyError("Save a shipping address on Shoppy before checkout.")
                if len(addresses) > 1:
                    raise ShoppyError("Multiple saved addresses; select a shipping address for the cart on Shoppy before checkout.")
                shipping_address_id = addresses[0]["address"]["id"]
        variables: JSON = {"number": order["number"], "params": {
            "email": profile["email"],
            "billAddressAttributes": {
                key: value for key, value in billing_address.items()
                if key in {"id", "firstname", "lastname", "phone", "company", "isCompany"}
            },
        }}
        if shipping_address_id is not None:
            variables["shippingAddressId"] = shipping_address_id
        order = self._graphql(queries.UPDATE_CHECKOUT, variables)["updateCheckoutOrder"]
        if not order or not order["lineItems"]:
            raise ShoppyError("Checkout update did not return a nonempty order.")
        return order

    def order_status(self, order_number: str) -> JSON | None:
        """Return order details, including payment and shipping status."""
        try:
            return self._graphql(queries.ORDER, {"number": order_number})["order"]
        except NotFoundError:
            return None

    def list_orders(
        self,
        *,
        first: int = 10,
        cursor: str | None = None,
        sort: JSON | None = None,
        status: str | None = None,
        filter: JSON | None = None,
    ) -> JSON:
        """Return a page of orders with totals and pagination information."""
        variables: JSON = {"first": first}
        for key, value in [("cursor", cursor), ("sort", sort), ("status", status), ("filter", filter)]:
            if value is not None:
                variables[key] = value
        return self._graphql(queries.ORDERS, variables)["orders"]

    def payment_methods(self) -> list[JSON]:
        """Return the active payment methods."""
        return self._graphql(queries.PAYMENT_METHODS)["paymentMethods"]

    def initiate_payment(self, *, order_number: str, action: str = "qpay_merchant") -> JSON:
        """Create a payment attempt for the order and return the provider's response."""
        return self._graphql(queries.ORDER_PAY, {"input": {
            "number": order_number, "action": action,
        }})["orderPay"]

    def send_socialpay(self, url: str) -> JSON:
        """Send an existing SocialPay invoice to the account's mobile for approval."""
        phone = self.profile()["mobile"]
        if not phone:
            raise ShoppyError("The account needs a mobile number before sending SocialPay.")
        normalized_phone = phone.replace(" ", "")
        if len(normalized_phone) != 8 or not normalized_phone.isascii() or not normalized_phone.isdigit():
            raise ShoppyError("The account mobile number must contain eight digits.")
        invoice = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]

        details = self._bank_request("/payment/get/details", {"invoice": invoice}, url=url)
        self._check_bank_header(details)
        bank_token = details["body"]["response"]["token"]
        if bank_token:
            bank_token = bank_token.strip().removeprefix("Bearer ").strip()
        if not bank_token:
            raise ShoppyError("Payment details omitted the bank session token; SocialPay cannot be sent.")
        prepared = self._bank_request(
            "/payment/prepare", {"phone": phone}, url=url, token=bank_token,
        )
        self._check_bank_header(prepared)
        data = prepared["body"]["response"]["data"]
        if not data:
            raise ShoppyError("Payment provider did not prepare the payment.")
        session = self._bank_request(
            "/payment/newSpCheckSession", {"data": normalized_phone}, url=url,
        )
        if session["desc"] != "Y":
            raise ShoppyError("Payment provider rejected the SocialPay session.")
        result = self._bank_request(
            "/payment/doSendNewSPPaymexTran", {"data": data}, url=url,
        )
        if result["status"] != "PENDING" or not result["refToken"]:
            raise ShoppyError("Payment provider did not accept the SocialPay request.")
        return result