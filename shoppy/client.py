"""Synchronous storefront client with explicit checkout and payment steps."""

from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from dotenv import dotenv_values

from . import queries
from .models import JSON


class Shoppy:
    """Access Shoppy using a Bearer token or :meth:`login`.

    A client owns one session and cart and is not intended for concurrent use.
    Failed requests are never retried automatically, especially mutations.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        search_auth: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(timeout=timeout, transport=transport)
        self._token = token.removeprefix("Bearer ") if token else None
        self._search_auth = search_auth
        self._number: str | None = None
        self._order_token: str | None = None

    def __enter__(self) -> "Shoppy":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        """Release pooled connections."""
        self._client.close()

    def _request(
        self, method: str, url: str, *, authenticated: bool = True,
        basic_auth: str | None = None,
        extra_headers: dict[str, str] | None = None,
        validate: Callable[[JSON], bool] | None = None,
        **kwargs: Any,
    ) -> Any:
        headers = {"Referer": "https://shoppy.mn/", "Origin": "https://shoppy.mn"}
        if authenticated and self._token and urlsplit(url).hostname == "api3.cody.mn":
            headers["Authorization"] = f"Bearer {self._token}"
        if self._search_auth and url.startswith("https://elastic.cody.mn/"):
            headers["Authorization"] = self._search_auth
        if basic_auth and url == "https://api3.cody.mn/oauth/token":
            headers["Authorization"] = basic_auth
        if extra_headers:
            headers.update(extra_headers)
        response = self._client.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("Expected a JSON object response.")
        if result.get("errors") or result.get("error"):
            raise ValueError("API reported an error.")
        if url.endswith("/graphql"):
            if not isinstance(result.get("data"), dict):
                raise ValueError("GraphQL response omitted data.")
            for value in result["data"].values():
                if isinstance(value, dict) and (value.get("errors") or value.get("error")):
                    raise ValueError("GraphQL operation reported an error.")
        if url.endswith("/oauth/token") and not result.get("access_token"):
            raise ValueError("Login response omitted access_token.")
        if validate is not None and not validate(result):
            raise ValueError("Payment provider returned an unsuccessful or incomplete response.")
        return result

    def _graphql(self, query: str, variables: JSON | None = None) -> JSON:
        return self._request(
            "POST", "https://api3.cody.mn/graphql",
            json={"query": query, "variables": variables or {}},
        )["data"]

    def check_login(self, login: str) -> JSON:
        return self._graphql(queries.CHECK_LOGIN, {"login": login, "no_token": True})["exists"]

    def login(self, username: str, password: str, *, basic_auth: str) -> JSON:
        """Authenticate and retain the access token; never persist credentials."""
        basic_auth = basic_auth.strip()
        if not basic_auth.startswith("Basic ") or not basic_auth[6:].strip():
            raise ValueError("basic_auth must be a Basic authorization header")
        result = self._request(
            "POST", "https://api3.cody.mn/oauth/token", authenticated=False,
            basic_auth=basic_auth,
            data={"username": username, "password": password, "grant_type": "password"},
        )
        self._token = result["access_token"]
        self._number = self._order_token = None
        return result

    def login_from_env(self, path: str | Path = ".env") -> JSON:
        """Read USER/PASS/SHOPPY_BASIC_AUTH from dotenv, ignoring shell USER."""
        values = dotenv_values(path)
        username, password = values.get("USER"), values.get("PASS")
        if not username or not password:
            raise ValueError("The dotenv file must contain USER and PASS.")
        basic_auth = values.get("SHOPPY_BASIC_AUTH")
        if not basic_auth:
            raise ValueError("The dotenv file must contain SHOPPY_BASIC_AUTH.")
        self._search_auth = values.get("SHOPPY_SEARCH_AUTH") or self._search_auth
        return self.login(username, password, basic_auth=basic_auth)

    def me(self, *, detailed: bool = False) -> JSON:
        return self._graphql(queries.DETAILED_ME if detailed else queries.ME)["me"]

    def search_products(
        self, query: str = "", *, category_id: str | None = None,
        limit: int = 30, offset: int = 0,
    ) -> JSON:
        """Return search hits and totals, optionally restricted to a category."""
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("limit must be 1..100 and offset must be nonnegative")
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
        return self._request("POST", "https://elastic.cody.mn/shoppy/_search", json={
            "query": {"bool": {"must": must}}, "size": limit, "from": offset,
            "sort": [{"_score": "desc"}],
        })

    def menus(self) -> list[JSON]:
        return self._graphql(queries.MENUS)["menus"]

    def flat_categories(self) -> Any:
        return self._graphql(queries.FLAT_TAXONS)["flatTaxon"]

    def categories(self, parent_id: str | None = None) -> list[JSON]:
        document = queries.ROOT_TAXONS if parent_id is None else queries.CHILD_TAXONS
        return self._graphql(document, {"parentId": parent_id})["taxons"]["nodes"]

    def product(self, slug: str) -> JSON | None:
        return self._graphql(queries.PRODUCT, {"slug": slug, "width": 120, "height": 0})["listing"]

    def variant_stores(self, variant_id: str) -> JSON | None:
        return self._graphql(queries.VARIANT_STORES, {"variantId": variant_id})["variant"]

    def _remember_order(self, order: JSON | None) -> JSON | None:
        if order:
            self._number = order.get("number", self._number)
            self._order_token = order.get("token", self._order_token)
        else:
            self._number = self._order_token = None
        return order

    def current_order(self, *, number: str | None = None, token: str | None = None) -> JSON | None:
        return self._remember_order(self._graphql(queries.CURRENT_ORDER, {
            "number": number if number is not None else self._number,
            "token": token if token is not None else self._order_token,
        })["currentOrder"])

    def add_to_cart(self, variant_id: str, *, quantity: int = 1) -> JSON:
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            raise ValueError("quantity must be a positive integer")
        if self._number is None:
            self.current_order()
        order = self._graphql(queries.ADD_TO_CART, {
            "number": self._number, "token": self._order_token,
            "batch": [{"variantId": variant_id, "quantity": quantity}],
        })["order"]
        self._remember_order(order)
        return order

    def update_cart_item(self, line_item_id: str, *, quantity: int) -> JSON:
        """Set quantity; zero removes the line item."""
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            raise ValueError("quantity must be a nonnegative integer")
        return self._graphql(queries.UPDATE_ITEM, {
            "input": {"id": line_item_id, "quantity": quantity},
        })["updateItem"]

    def _order_number(self, number: str | None) -> str:
        selected = number or self._number
        if not selected:
            raise ValueError("Provide an order number or load/add to a cart first.")
        return selected

    def checkout(
        self, *, email: str, billing_address: JSON, number: str | None = None,
        shipping_address: JSON | None = None, shipping_address_id: str | None = None,
        shipping_method_id: str | None = None,
        action: str = "qpay_merchant",
    ) -> JSON:
        """Save checkout details, then submit the order and initialize payment.

        Return updated order details under ``order`` and the submission result
        under ``paymentAction``. If submission fails, saved details remain;
        neither request is automatically retried.
        """
        if shipping_address is not None and shipping_address_id is not None:
            raise ValueError("Provide a shipping address or an address ID, not both.")
        variables: JSON = {"number": self._order_number(number), "params": {
            "email": email, "billAddressAttributes": billing_address,
        }}
        for key, value in [("shippingAddress", shipping_address),
                           ("shippingAddressId", shipping_address_id),
                           ("shippingMethodId", shipping_method_id)]:
            if value is not None:
                variables[key] = value
        order = self._graphql(queries.UPDATE_CHECKOUT, variables)["updateCheckoutOrder"]
        if not isinstance(order, dict) or not order:
            raise ValueError("Checkout update did not return an order.")
        self._remember_order(order)
        payment_action = self._graphql(queries.PAYMENT_ACTION, {
            "number": variables["number"], "action": action,
        })["paymentAction"]
        return {"order": order, "paymentAction": payment_action}

    def order(self, number: str) -> JSON | None:
        return self._graphql(queries.ORDER, {"number": number})["order"]

    def orders(
        self,
        *,
        first: int = 10,
        cursor: str | None = None,
        sort: JSON | None = None,
        status: str | None = None,
        filter: JSON | None = None,
    ) -> JSON:
        """Return one order page with edges, totalCount, and pageInfo.

        Defaults to most recently updated orders without status filters.
        Pass pageInfo.endCursor as cursor to fetch the next page when
        pageInfo.hasNextPage is true. Filter and status values use the API's
        OrderFilter and OrderStatus definitions.
        """
        if isinstance(first, bool) or not isinstance(first, int) or first < 1:
            raise ValueError("first must be a positive integer")
        variables: JSON = {
            "first": first,
            "sort": sort if sort is not None else {"field": "updated_at", "direction": "desc"},
        }
        for key, value in [("cursor", cursor), ("status", status), ("filter", filter)]:
            if value is not None:
                variables[key] = value
        return self._graphql(queries.ORDERS, variables)["orders"]

    def payment_methods(self) -> list[JSON]:
        return self._graphql(queries.PAYMENT_METHODS)["paymentMethods"]

    def initiate_payment(self, *, action: str = "m_bank_card", number: str | None = None) -> JSON:
        """Create a payment attempt; does not pay or retry the mutation."""
        return self._graphql(queries.ORDER_PAY, {"input": {
            "number": self._order_number(number), "action": action,
        }})["orderPay"]

    def initiate_socialpay(self, *, number: str | None = None) -> JSON:
        """Create a SocialPay attempt and return its hosted URL and deeplink."""
        return self.initiate_payment(action="golomt_wallet", number=number)

    def send_payment_to_mobile(
        self,
        payment: JSON,
        phone: str,
        *,
        bank_token: str | None = None,
    ) -> JSON:
        """Send a SocialPay payment request to a mobile number.

        Use the result of initiate_socialpay() as payment. The bank token is
        separate from Shoppy authentication. If payment details omit it, supply
        the token from the bank's browser session explicitly. This method sends
        a notification once and returns PENDING/refToken; it neither approves
        payment nor polls for completion. Only the captured new-session flow
        is supported.
        """
        normalized_phone = phone.replace(" ", "")
        if len(normalized_phone) != 8 or not normalized_phone.isascii() or not normalized_phone.isdigit():
            raise ValueError("phone must contain eight digits, optionally separated by spaces")
        url = payment.get("attributes", {}).get("url", "")
        parsed = urlsplit(url)
        parts = parsed.path.strip("/").split("/")
        if (
            parsed.scheme != "https" or parsed.netloc != "ecommerce.golomtbank.com"
            or parsed.query or parsed.fragment or len(parts) != 3
            or parts[0] != "socialpay" or parts[1] not in {"mn", "en"}
        ):
            raise ValueError("payment must contain a Golomt SocialPay invoice URL")
        try:
            invoice = str(UUID(parts[2]))
        except ValueError:
            raise ValueError("SocialPay invoice must be a UUID") from None

        def bank_request(
            path: str, payload: JSON, validator: Callable[[JSON], bool],
            token: str | None = None,
        ) -> JSON:
            headers = {"Origin": "https://ecommerce.golomtbank.com", "Referer": url}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            return self._request(
                "POST", f"https://ecommerce.golomtbank.com{path}",
                authenticated=False, extra_headers=headers, json=payload,
                validate=validator,
            )

        def has_response(result: JSON) -> bool:
            header, body = result.get("header"), result.get("body")
            return (
                isinstance(header, dict) and header.get("code") == 200
                and header.get("status") == "success"
                and isinstance(body, dict) and isinstance(body.get("response"), dict)
                and not body.get("error")
            )

        details = bank_request("/payment/get/details", {"invoice": invoice}, has_response)
        token = bank_token or details["body"]["response"].get("token")
        if not isinstance(token, str) or not token.strip().removeprefix("Bearer ").strip():
            raise ValueError("Payment details omitted the bank token; provide bank_token from the bank session.")
        token = token.strip().removeprefix("Bearer ").strip()
        prepared = bank_request(
            "/payment/prepare", {"phone": phone},
            lambda result: has_response(result)
            and isinstance(result["body"]["response"].get("data"), str)
            and bool(result["body"]["response"]["data"]),
            token=token,
        )
        bank_request(
            "/payment/newSpCheckSession", {"data": normalized_phone},
            lambda result: result.get("desc") == "Y",
        )
        return bank_request(
            "/payment/doSendNewSPPaymexTran",
            {"data": prepared["body"]["response"]["data"]},
            lambda result: result.get("status") == "PENDING"
            and isinstance(result.get("refToken"), str) and bool(result["refToken"]),
        )
