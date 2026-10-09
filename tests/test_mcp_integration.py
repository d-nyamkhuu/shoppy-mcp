"""Exercise the MCP adapter and real client together using captured HTTP shapes."""

import json

import httpx
from fastmcp import Client

from shoppy import queries
from shoppy.client import LOGIN_AUTH, SEARCH_AUTH
from shoppy.mcp import create_server


async def test_shopping_payment_flow(mock_http, storefront):
    invoice = "00000000-0000-0000-0000-000000000001"
    url = f"https://ecommerce.golomtbank.com/socialpay/mn/{invoice}"
    payment = {"number": "PAYMENT-1", "attributes": {"url": url, "token": "bank-secret"}}
    cart = {**storefront["cart"], "digital": False, "billAddress": None, "shipAddress": None}
    steps = iter([
        ("/oauth/token", {"access_token": "shoppy-secret"}),
        ("/shoppy/_search", storefront["search"]),
        (queries.PRODUCT, {"data": {"listing": storefront["listing"]}}),
        (queries.CURRENT_ORDER, {"data": {"currentOrder": cart}}),
        (queries.ADD_TO_CART, {"data": {"order": cart}}),
        (queries.CURRENT_ORDER, {"data": {"currentOrder": cart}}),
        (queries.DETAILED_ME, {"data": {"me": storefront["detailed_profile"]}}),
        (queries.UPDATE_CHECKOUT, {"data": {"updateCheckoutOrder": storefront["checkout"]}}),
        (queries.ORDER_PAY, {"data": {"orderPay": payment}}),
        (queries.ORDER_PAY, {"data": {"orderPay": payment}}),
        (queries.ME, {"data": {"me": storefront["profile"]}}),
        ("/payment/get/details", {"header": {"code": 200, "status": "success"}, "body": {"response": {"token": "bank-secret"}}}),
        ("/payment/prepare", {"header": {"code": 200, "status": "success"}, "body": {"response": {"data": "opaque-secret"}}}),
        ("/payment/newSpCheckSession", {"desc": "Y"}),
        ("/payment/doSendNewSPPaymexTran", {"status": "PENDING", "refToken": "reference-secret"}),
        (queries.ORDER, {"data": {"order": storefront["order"]}}),
        (queries.ORDER, {"data": {"order": {
            **storefront["order"], "paymentState": "paid", "paidAt": "2026-09-11T01:00:00Z",
        }}}),
    ])
    requests = []

    def handle(request):
        requests.append(request)
        expected, response = next(steps)
        path = request.url.path
        operation = json.loads(request.content)["query"] if path == "/graphql" else path
        assert operation == expected
        if path == "/oauth/token":
            assert request.headers["Authorization"] == LOGIN_AUTH
        elif request.url.host == "elastic.cody.mn":
            assert request.headers["Authorization"] == SEARCH_AUTH
        elif path == "/graphql":
            assert request.headers["Authorization"] == "Bearer shoppy-secret"
        elif path == "/payment/prepare":
            assert request.headers["Authorization"] == "Bearer bank-secret"
        else:
            assert "Authorization" not in request.headers
        return httpx.Response(200, json=response)

    mock_http(handle)
    server = create_server("test-user", "test-password")
    assert len(requests) == 1  # Login happens at setup, once.
    async with Client(server) as client:
        search = await client.call_tool("search_products", {"query": "shoe"})
        slug = search.structured_content["products"][0]["slug"]
        product = await client.call_tool("get_product", {"slug": slug})
        variant = product.structured_content["result"]["product"]["variantsIncludingMaster"][0]["id"]
        await client.call_tool("add_to_cart", {"variant_id": variant, "quantity": 2})
        checkout = await client.call_tool("checkout", {})
        number = checkout.structured_content["number"]
        assert len(requests) == 8  # Checkout has not initialized payment.
        link = await client.call_tool("pay_with_socialpay", {"number": number})
        assert link.structured_content == {"url": url, "phoneRequest": None, "phoneError": None}
        assert len(requests) == 9  # An invoice link does not send a phone notification.
        sent = await client.call_tool("pay_with_socialpay", {"number": number, "send_to_phone": True})
        assert sent.structured_content == {"url": url, "phoneRequest": "PENDING", "phoneError": None}
        unpaid = await client.call_tool("get_order", {"number": number})
        assert unpaid.structured_content["result"]["state"] == "complete"
        assert unpaid.structured_content["result"]["paidAt"] is None
        paid = await client.call_tool("get_order", {"number": number})
        assert paid.structured_content["result"]["paymentState"] == "paid"
    assert list(steps) == []
    graphql = [json.loads(r.content) for r in requests if r.url.path == "/graphql"]
    addition = next(p["variables"] for p in graphql if p["query"] == queries.ADD_TO_CART)
    assert addition == {"number": "ORDER-1", "token": "cart-secret", "batch": [{"variantId": variant, "quantity": 2}]}
    checkout = next(p["variables"] for p in graphql if p["query"] == queries.UPDATE_CHECKOUT)
    assert checkout == {"number": "ORDER-1", "shippingAddressId": "ID-1", "params": {
        "email": "test@example.com", "billAddressAttributes": {
            "firstname": "example", "lastname": "example", "phone": "99112233", "isCompany": False,
        },
    }}
    for payload in graphql:
        if payload["query"] == queries.ORDER_PAY:
            assert payload["variables"]["input"] == {"number": "ORDER-1", "action": "golomt_wallet"}
    bank = {r.url.path: json.loads(r.content) for r in requests if r.url.host == "ecommerce.golomtbank.com"}
    assert bank == {
        "/payment/get/details": {"invoice": invoice}, "/payment/prepare": {"phone": "99112233"},
        "/payment/newSpCheckSession": {"data": "99112233"}, "/payment/doSendNewSPPaymexTran": {"data": "opaque-secret"},
    }
