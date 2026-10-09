import json
from urllib.parse import parse_qs

import httpx
import pytest

from shoppy import Shoppy, queries
from shoppy.client import LOGIN_AUTH, SEARCH_AUTH, NotFoundError, ShoppyError


@pytest.mark.parametrize("total", [2, {"value": 2, "relation": "eq"}])
def test_search_requests_only_product_summary_fields_and_omits_scores(total, mock_http):
    def handle(request):
        body = json.loads(request.content)
        assert set(body["_source"]) == {"id", "slug", "name", "title", "price", "selling_price", "total_on_hand", "image"}
        assert body["sort"] == [{"_score": "desc"}]
        assert body["size"] == 2 and body["from"] == 4
        assert request.headers["Authorization"] == SEARCH_AUTH
        return httpx.Response(200, json={"took": 1, "hits": {"total": total, "max_score": 3, "hits": [
            {"_id": "P1", "_score": 3, "_index": "shoppy", "_source": {"slug": "shoe", "image": None}},
            {"_id": "P2", "_score": 2, "_source": {"slug": "boot"}},
        ]}})

    mock_http(handle)
    shop = Shoppy(token="api-secret")
    assert shop.search_products("shoe", limit=2, offset=4) == {"hits": {"total": total, "hits": [
        {"_id": "P1", "_source": {"slug": "shoe", "image": None}},
        {"_id": "P2", "_source": {"slug": "boot"}},
    ]}}


@pytest.mark.parametrize("response, exception", [
    ({}, KeyError), ({"hits": None}, TypeError), ({"hits": {}}, KeyError),
    ({"hits": {"total": None, "hits": None}}, TypeError),
])
def test_search_rejects_malformed_responses(response, exception, mock_http):
    mock_http(lambda request: httpx.Response(200, json=response))
    with pytest.raises(exception):
        Shoppy().search_products()


def test_product_request_has_no_unused_image_variables(mock_http):
    def handle(request):
        assert json.loads(request.content)["variables"] == {"slug": "shoe"}
        return httpx.Response(200, json={"data": {"listing": None}})

    mock_http(handle)
    assert Shoppy().product("shoe") is None


def test_login_uses_fixed_auth_without_retaining_cookies(mock_http):
    requests = []

    def handle(request):
        requests.append(request)
        assert request.extensions["timeout"]["read"] == 12.0
        assert "cookie" not in request.headers
        if request.url.path == "/oauth/token":
            assert request.headers["Authorization"] == LOGIN_AUTH
            assert parse_qs(request.content.decode()) == {
                "username": ["shopper"], "password": ["password"], "grant_type": ["password"],
            }
            return httpx.Response(200, json={"access_token": "new-token"}, headers={"Set-Cookie": "session=ignored"})
        assert request.headers["Authorization"] == "Bearer new-token"
        assert json.loads(request.content)["variables"] is None
        return httpx.Response(200, json={"data": {"currentOrder": None}})

    mock_http(handle)
    shop = Shoppy(token="old-token", timeout=12.0)
    assert shop.login("shopper", "password") == {"access_token": "new-token"}
    assert shop.current_cart() is None
    assert len(requests) == 2


@pytest.mark.parametrize("status, body, exception", [
    (400, {"error": "invalid_grant", "error_description": "Invalid credentials"}, httpx.HTTPStatusError),
    (200, {}, KeyError),
    (200, {"access_token": ""}, ShoppyError),
])
def test_failed_login_preserves_account(status, body, exception, mock_http):
    mock_http(lambda request: httpx.Response(status, json=body))
    shop = Shoppy(token="old-token")
    with pytest.raises(exception):
        shop.login("shopper", "password")
    assert shop._token == "old-token"


@pytest.mark.parametrize("invoice", ["00000000-0000-0000-0000-000000000001", "provider-invoice-id"])
@pytest.mark.parametrize("fail_at", [None, "/payment/prepare", "/payment/doSendNewSPPaymexTran"])
def test_send_socialpay_sends_existing_invoice_once(invoice, fail_at, mock_http):
    requests = []
    url = f"https://ecommerce.golomtbank.com/socialpay/mn/{invoice}"

    def handle(request):
        requests.append(request.url.path)
        body = json.loads(request.content)
        if request.url.path == "/graphql":
            assert request.headers["Authorization"] == "Bearer shoppy-token"
            assert body["query"] == queries.ME
            return httpx.Response(200, json={"data": {"me": {"mobile": "9911 2233"}}})
        assert request.url.host == "ecommerce.golomtbank.com"
        assert request.headers["Referer"] == url
        assert request.headers["Origin"] == "https://ecommerce.golomtbank.com"
        if request.url.path == "/payment/prepare":
            assert request.headers["Authorization"] == "Bearer bank-token"
        else:
            assert "Authorization" not in request.headers
        if request.url.path == fail_at:
            raise httpx.ReadTimeout("Timed out", request=request)
        if request.url.path == "/payment/get/details":
            assert body == {"invoice": invoice}
            result = {"header": {"code": 200, "status": "success"}, "body": {"response": {"token": "bank-token"}}}
        elif request.url.path == "/payment/prepare":
            assert body == {"phone": "9911 2233"}
            result = {"header": {"code": 200, "status": "success"}, "body": {"response": {"data": "prepared"}}}
        elif request.url.path == "/payment/newSpCheckSession":
            assert body == {"data": "99112233"}
            result = {"desc": "Y"}
        else:
            assert body == {"data": "prepared"}
            result = {"status": "PENDING", "refToken": "reference"}
        return httpx.Response(200, json=result)

    mock_http(handle)
    shop = Shoppy(token="shoppy-token")
    if fail_at:
        with pytest.raises(httpx.ReadTimeout):
            shop.send_socialpay(url)
    else:
        assert shop.send_socialpay(url) == {"status": "PENDING", "refToken": "reference"}
    expected = ["/graphql", "/payment/get/details", "/payment/prepare", "/payment/newSpCheckSession", "/payment/doSendNewSPPaymexTran"]
    assert requests == (expected[:expected.index(fail_at) + 1] if fail_at else expected)


@pytest.mark.parametrize("phone", ["123", "abcdefgh", "９９１１２２３３"])
def test_send_socialpay_validates_phone_before_bank_requests(phone, mock_http):
    def handle(request):
        assert json.loads(request.content)["query"] == queries.ME
        return httpx.Response(200, json={"data": {"me": {"mobile": phone}}})

    mock_http(handle)
    with pytest.raises(ShoppyError, match="eight digits"):
        Shoppy().send_socialpay("https://ecommerce.golomtbank.com/socialpay/mn/test-invoice")


@pytest.mark.parametrize("body", [
    {"errors": [{"message": "Invalid variable", "extensions": {"problems": []}}]},
    {"errors": [{"message": "Partial failure"}], "data": {"listing": {"id": "partial"}}},
    {"errors": [{"message": "Resource not found with id: missing"}, {"message": "Partial failure"}]},
])
def test_graphql_rejects_observed_errors_including_partial_data(body, mock_http):
    mock_http(lambda request: httpx.Response(200, json=body))
    with pytest.raises(ShoppyError, match="GraphQL reported an error"):
        Shoppy().product("missing")


@pytest.mark.parametrize("operation, path", [
    (lambda shop: shop.product("missing"), "listing"),
    (lambda shop: shop.variant_stores("missing"), "variant"),
    (lambda shop: shop.order_status("missing"), "order"),
])
def test_observed_not_found_errors_return_none(operation, path, mock_http):
    requests = []
    mock_http(lambda request: requests.append(request) or httpx.Response(200, json={
        "errors": [{"message": "Resource not found with id: missing", "path": [path]}], "data": None,
    }))
    assert operation(Shoppy()) is None
    assert len(requests) == 1


def test_not_found_mutation_raises(mock_http):
    mock_http(lambda request: httpx.Response(200, json={
        "errors": [{"message": "Order not found", "path": ["orderPay"]}], "data": {"orderPay": None},
    }))
    with pytest.raises(NotFoundError, match="could not find"):
        Shoppy().initiate_payment(order_number="missing", action="golomt_wallet")


def test_out_of_stock_addition_raises_safe_error(mock_http):
    def handler(request):
        if json.loads(request.content)["query"] == queries.CURRENT_ORDER:
            return httpx.Response(200, json={"data": {"currentOrder": None}})
        return httpx.Response(200, json={
            "errors": [{"message": "\"Notebook\" хувилбар нь барааны үлдэгдэлгүй байна", "path": ["order"]}],
            "data": {"order": None},
        })

    mock_http(handler)
    with pytest.raises(ShoppyError, match="out of stock"):
        Shoppy().add_to_cart("V1")


@pytest.mark.parametrize("limit, offset", [(1, 10000), (100, 9901)])
def test_search_beyond_result_window_makes_no_request(limit, offset, mock_http):
    requests = []
    mock_http(lambda request: requests.append(request) or httpx.Response(500))
    with pytest.raises(ShoppyError, match="offset \\+ limit"):
        Shoppy().search_products("shoe", limit=limit, offset=offset)
    assert requests == []


@pytest.mark.parametrize("operation, status, body", [
    (lambda shop: shop.profile(), 401, {"errors": [{"message": "Unauthorized"}]}),
    (lambda shop: shop.search_products(limit=-1), 400, {
        "error": {"type": "illegal_argument_exception", "reason": "size must be non-negative"}, "status": 400,
    }),
])
def test_http_errors_preserve_provider_response(operation, status, body, mock_http):
    mock_http(lambda request: httpx.Response(status, json=body))
    with pytest.raises(httpx.HTTPStatusError) as caught:
        operation(Shoppy())
    assert caught.value.response.status_code == status
    assert caught.value.response.json() == body


@pytest.mark.parametrize("header", [{"code": 400, "status": "failed"}, {"code": 200, "status": "failed"}])
def test_bank_uses_header_and_body_error_contract(header):
    body = {"header": header, "body": {"error": {"errorDesc": "error.notfound.invoice", "errorType": "NotFound"}}}
    with pytest.raises(ShoppyError, match="error.notfound.invoice"):
        Shoppy._check_bank_header(body)


@pytest.mark.parametrize("failure, exception, last_path", [
    ("details_rejected", ShoppyError, "/payment/get/details"),
    ("empty_token", ShoppyError, "/payment/get/details"),
    ("missing_token", KeyError, "/payment/get/details"),
    ("prepare_rejected", ShoppyError, "/payment/prepare"),
    ("empty_data", ShoppyError, "/payment/prepare"),
    ("session_rejected", ShoppyError, "/payment/newSpCheckSession"),
    ("send_rejected", ShoppyError, "/payment/doSendNewSPPaymexTran"),
    ("empty_reference", ShoppyError, "/payment/doSendNewSPPaymexTran"),
])
def test_socialpay_stops_at_provider_failure(failure, exception, last_path, mock_http):
    requests = []

    def handle(request):
        path = request.url.path
        requests.append(path)
        if path == "/graphql":
            assert json.loads(request.content)["query"] == queries.ME
            body = {"data": {"me": {"mobile": "99112233"}}}
        elif path == "/payment/get/details":
            response = {"token": "bank-token"}
            if failure == "empty_token":
                response["token"] = ""
            elif failure == "missing_token":
                response = {}
            body = {"header": {"code": 200, "status": "success"}, "body": {"response": response}}
            if failure == "details_rejected":
                body = {"header": {"code": 400, "status": "failed"}, "body": {"error": {
                    "errorDesc": "error.notfound.invoice", "errorType": "NotFound",
                }}}
        elif path == "/payment/prepare":
            body = {"header": {"code": 200, "status": "success"}, "body": {"response": {
                "data": "" if failure == "empty_data" else "opaque-payload", "action": "newSP",
            }}}
            if failure == "prepare_rejected":
                body = {"header": {"code": 400, "status": "failed"}, "body": {"error": {
                    "errorDesc": "error.invalid.token", "errorType": "InvalidToken",
                }}}
        elif path == "/payment/newSpCheckSession":
            body = {"desc": "N" if failure == "session_rejected" else "Y"}
        else:
            assert path == "/payment/doSendNewSPPaymexTran"
            body = {
                "status": "FAILED" if failure == "send_rejected" else "PENDING",
                "refToken": "" if failure == "empty_reference" else "reference",
            }
        return httpx.Response(200, json=body)

    mock_http(handle)
    with pytest.raises(exception):
        Shoppy(token="shoppy-token").send_socialpay("https://ecommerce.golomtbank.com/socialpay/mn/test-invoice")
    expected = ["/graphql", "/payment/get/details", "/payment/prepare",
                "/payment/newSpCheckSession", "/payment/doSendNewSPPaymexTran"]
    assert requests == expected[:expected.index(last_path) + 1]


@pytest.mark.parametrize("operation", [
    lambda shop: shop.add_to_cart("variant", quantity=0),
    lambda shop: shop.add_to_cart("variant", quantity=-1),
    lambda shop: shop.update_cart_item("line", quantity=-1),
])
def test_invalid_quantity_never_changes_cart(operation, mock_http):
    def handle(request):
        pytest.fail("Invalid quantities must be rejected before contacting the provider.")

    mock_http(handle)
    with pytest.raises(ShoppyError, match="Quantity"):
        operation(Shoppy())


def test_add_to_cart_without_existing_cart(mock_http):
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        if body["query"] == queries.CURRENT_ORDER:
            return httpx.Response(200, json={"data": {"currentOrder": None}})
        assert body["variables"] == {
            "number": None, "token": None, "batch": [{"variantId": "variant", "quantity": 1}],
        }
        return httpx.Response(200, json={"data": {"order": {"number": "NEW-ORDER"}}})

    mock_http(handle)
    assert Shoppy().add_to_cart("variant") == {"number": "NEW-ORDER"}
    assert len(requests) == 2


def test_zero_quantity_removes_cart_line(mock_http):
    def handle(request):
        assert json.loads(request.content) == {
            "query": queries.UPDATE_ITEM, "variables": {"input": {"id": "line", "quantity": 0}},
        }
        return httpx.Response(200, json={"data": {"updateItem": {"lineItems": [], "itemCount": 0}}})

    mock_http(handle)
    assert Shoppy().update_cart_item("line", quantity=0)["itemCount"] == 0


@pytest.mark.parametrize("reject_update", [False, True])
@pytest.mark.parametrize("digital, selected_address, expected_address", [
    (False, None, "saved-address"),
    (False, {"id": "cart-address"}, "cart-address"),
    (True, None, None),
])
def test_checkout_saves_details_without_payment(reject_update, digital, selected_address, expected_address, mock_http):
    requests = []
    order = {
        "number": "CURRENT-ORDER", "lineItems": [{"id": "line"}], "digital": digital,
        "billAddress": None, "shipAddress": selected_address,
    }
    profile = {
        "email": "shopper@example.com", "firstName": "First", "lastName": "Last", "mobile": "99112233",
        "userAddresses": {"nodes": [{"address": {"id": "saved-address"}}]},
    }

    def handle(request):
        body = json.loads(request.content)
        query = body["query"]
        requests.append(query)
        if query == queries.CURRENT_ORDER:
            result = {"data": {"currentOrder": order}}
        elif query == queries.DETAILED_ME:
            result = {"data": {"me": profile}}
        elif query == queries.UPDATE_CHECKOUT:
            expected_variables = {
                "number": "CURRENT-ORDER", "params": {
                    "email": "shopper@example.com", "billAddressAttributes": {
                        "firstname": "First", "lastname": "Last", "phone": "99112233", "isCompany": False,
                    },
                },
            }
            if expected_address is not None:
                expected_variables["shippingAddressId"] = expected_address
            assert body["variables"] == expected_variables
            result = {"errors": [{"message": "Rejected"}]} if reject_update else {"data": {"updateCheckoutOrder": order}}
        else:
            pytest.fail("Checkout must not initialize payment.")
        return httpx.Response(200, json=result)

    mock_http(handle)
    if reject_update:
        with pytest.raises(ShoppyError, match="GraphQL"):
            Shoppy().checkout()
    else:
        assert Shoppy().checkout() == order
    assert requests == [queries.CURRENT_ORDER, queries.DETAILED_ME, queries.UPDATE_CHECKOUT]


@pytest.mark.parametrize("addresses, message", [
    ([], "Save a shipping address"),
    ([{"address": {"id": "first"}}, {"address": {"id": "second"}}], "Multiple saved addresses"),
])
def test_checkout_requires_unambiguous_shipping_address(addresses, message, mock_http):
    def handle(request):
        query = json.loads(request.content)["query"]
        if query == queries.CURRENT_ORDER:
            result = {"currentOrder": {
                "lineItems": [{"id": "line"}], "digital": False,
                "billAddress": {}, "shipAddress": None,
            }}
        elif query == queries.DETAILED_ME:
            result = {"me": {"email": "shopper@example.com", "userAddresses": {"nodes": addresses}}}
        else:
            pytest.fail("Checkout must not change the order without a shipping address.")
        return httpx.Response(200, json={"data": result})

    mock_http(handle)
    with pytest.raises(ShoppyError, match=message):
        Shoppy().checkout()
