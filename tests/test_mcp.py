import json
import sys
from unittest.mock import Mock, create_autospec

import httpx
import jsonschema
import pytest
import pytest_asyncio
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from shoppy.client import NotFoundError, Shoppy, ShoppyError
from shoppy.mcp import create_server, load_credentials, main

INVOICE_URL = "https://ecommerce.golomtbank.com/socialpay/mn/00000000-0000-0000-0000-000000000001"
INVALID_PAYMENTS = [None, [], {}, {"attributes": None}, {"attributes": []}, {"attributes": {"url": 123}}] + [
    {"number": "PAYMENT-1", "attributes": {"url": url}} for url in [
        "javascript:alert(1)", INVOICE_URL.replace("ecommerce.golomtbank.com", "example.com"),
        INVOICE_URL.replace("https:", "http:"), INVOICE_URL.replace("/mn/", "/fr/"),
        INVOICE_URL.rsplit("/", 1)[0] + "/invalid", INVOICE_URL + "?token=private-secret",
        INVOICE_URL + "#private-secret", " " + INVOICE_URL, "\x00" + INVOICE_URL,
        INVOICE_URL.replace("golomtbank", "golomt\tbank"), INVOICE_URL + "\n", INVOICE_URL + "\x7f",
    ]
]


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("SHOPPY_USERNAME", raising=False)
    monkeypatch.delenv("SHOPPY_PASSWORD", raising=False)
    return monkeypatch


@pytest.fixture
def shop(monkeypatch):
    shop = create_autospec(Shoppy, instance=True)
    monkeypatch.setattr("shoppy.mcp.Shoppy", Mock(return_value=shop))
    return shop


@pytest_asyncio.fixture
async def client(shop):
    async with Client(create_server("test-user", "test-password")) as client:
        yield client


async def invoke(client, name, **arguments):
    result = await client.call_tool(name, arguments)
    if result.meta and result.meta.get("fastmcp", {}).get("wrap_result"):
        return result.structured_content["result"]
    return result.structured_content


async def test_tool_discovery(client):
    tools = {tool.name: tool for tool in await client.list_tools()}
    assert len(tools) == 12
    assert tools["checkout"].inputSchema["properties"] == {}
    assert set(tools["pay_with_socialpay"].inputSchema["properties"]) == {"number", "send_to_phone"}


async def test_tool_annotations(client):
    for tool in await client.list_tools():
        mutation = tool.name in {"checkout", "add_to_cart", "update_cart_item", "pay_with_socialpay"}
        destructive = tool.name in {"checkout", "update_cart_item"}
        assert tool.annotations.readOnlyHint is not mutation, tool.name
        assert tool.annotations.destructiveHint is destructive, tool.name
        assert tool.annotations.idempotentHint is not mutation, tool.name


async def test_output_schemas(client):
    tools = {tool.name: tool for tool in await client.list_tools()}
    for tool in tools.values():
        assert tool.outputSchema, tool.name
        assert '"additionalProperties": true' not in json.dumps(tool.outputSchema), tool.name
    assert set(tools["search_products"].outputSchema["properties"]) == {"total", "products"}
    assert set(tools["get_orders"].outputSchema["properties"]) == {"orders", "totalCount", "pageInfo"}
    assert "order" not in tools["checkout"].outputSchema["properties"]


async def test_responses_match_published_schemas(client, shop, storefront):
    shop.search_products.return_value = storefront["search"]
    shop.categories.return_value = storefront["child_categories"]
    shop.product.return_value = storefront["listing"]
    shop.variant_stores.return_value = storefront["variant_stores"]
    shop.profile.return_value = storefront["detailed_profile"]
    shop.list_orders.return_value = storefront["orders"]
    shop.order_status.return_value = storefront["order"]
    shop.current_cart.return_value = storefront["cart"]
    shop.add_to_cart.return_value = storefront["cart"]
    shop.update_cart_item.return_value = storefront["cart_update"]
    shop.checkout.return_value = storefront["checkout"]
    shop.initiate_payment.return_value = {"number": "PAYMENT-1", "attributes": {"url": INVOICE_URL}}
    shop.send_socialpay.return_value = {"status": "PENDING", "refToken": "reference-secret"}
    tools = {tool.name: tool for tool in await client.list_tools()}
    for name, arguments in [
        ("search_products", {}), ("get_categories", {}), ("get_product", {"slug": "shoe"}),
        ("get_variant_stores", {"variant_id": "V1"}), ("get_profile", {}), ("get_profile", {"detailed": True}),
        ("get_orders", {}), ("get_order", {"number": "ORDER-1"}), ("get_cart", {}),
        ("add_to_cart", {"variant_id": "V1"}), ("update_cart_item", {"line_item_id": "L1", "quantity": 0}),
        ("checkout", {}), ("pay_with_socialpay", {"number": "ORDER-1"}),
        ("pay_with_socialpay", {"number": "ORDER-1", "send_to_phone": True}),
    ]:
        result = await client.call_tool(name, arguments)
        jsonschema.validate(result.structured_content, tools[name].outputSchema)


@pytest.mark.parametrize("tool,method,arguments,key", [
    ("get_cart", "current_cart", {}, "cart"),
    ("add_to_cart", "add_to_cart", {"variant_id": "V1"}, "cart"),
    ("update_cart_item", "update_cart_item", {"line_item_id": "L1", "quantity": 0}, "cart_update"),
    ("get_order", "order_status", {"number": "ORDER-1"}, "order"),
    ("checkout", "checkout", {}, "checkout"),
])
async def test_order_tools_omit_private_fields(client, shop, storefront, tool, method, arguments, key):
    order = {
        **storefront[key], "token": "private-marker", "email": "private-marker",
        "billAddress": {"address1": "private-marker"}, "shipAddress": {"address1": "private-marker"},
    }
    getattr(shop, method).return_value = order
    result = await client.call_tool(tool, arguments)
    assert "private-marker" not in json.dumps(result.structured_content)
    assert "private-marker" not in str(result.content)


@pytest.mark.parametrize("detailed", [False, True])
async def test_profile_field_selection(client, shop, storefront, detailed):
    shop.profile.return_value = {**storefront["detailed_profile"], "birthday": "private-marker"}
    result = await invoke(client, "get_profile", detailed=detailed)
    shop.profile.assert_called_once_with(detailed=detailed)
    assert "private-marker" not in json.dumps(result)
    assert "userAddresses" not in result
    if detailed:
        address = result["addresses"][0]
        assert address["firstname"] is None
        assert not {"cdq", "company", "isCompany"} & address.keys()
    else:
        assert "addresses" not in result


@pytest.mark.parametrize("parent_id,key", [(None, "categories"), ("C1", "child_categories")])
async def test_categories(client, shop, storefront, parent_id, key):
    shop.categories.return_value = storefront[key]
    result = await invoke(client, "get_categories", parent_id=parent_id)
    shop.categories.assert_called_once_with(parent_id)
    assert result[0]["id"] == "ID-1"
    if parent_id:
        assert result[0]["children"][0]["hasChildren"] is False


@pytest.mark.parametrize("total", [0, 1, {"value": 1, "relation": "eq"}, {"value": 10000, "relation": "gte"}])
async def test_search_flattening_and_arguments(client, shop, storefront, total):
    products = [] if total == 0 else [storefront["search"]["hits"]["hits"][0]["_source"]]
    shop.search_products.return_value = {"hits": {
        "total": total, "hits": [{"_id": "unused", "_source": product} for product in products],
    }}
    result = await invoke(client, "search_products", query="shoe", category_id="C1", limit=2, offset=4)
    shop.search_products.assert_called_once_with("shoe", category_id="C1", limit=2, offset=4)
    assert result == {"total": total, "products": products}


@pytest.mark.parametrize("empty", [False, True])
async def test_orders_flattening_and_pagination(client, shop, empty):
    orders = [] if empty else [{
        "id": "O1", "number": "ORDER-1", "state": "complete", "paymentState": "balance_due",
        "shipmentState": None, "total": 100.0, "paidAt": None, "completedAt": None,
        "updatedAt": "2026-09-11T01:00:00Z", "lineItems": [{
            "id": "L1", "quantity": 2, "manifest": {"id": "V1", "name": "Shoe", "image": None},
        }],
    }]
    page_info = {"hasNextPage": not empty, "endCursor": None if empty else "C2"}
    shop.list_orders.return_value = {
        "edges": [{"node": order} for order in orders], "totalCount": 12, "pageInfo": page_info,
    }
    assert await invoke(client, "get_orders", first=1, cursor="C1") == {
        "orders": orders, "totalCount": 12, "pageInfo": page_info,
    }
    shop.list_orders.assert_called_once_with(
        first=1, cursor="C1", sort={"field": "updated_at", "direction": "desc"},
    )


async def test_checkout_does_not_start_payment(client, shop, storefront):
    shop.checkout.return_value = storefront["checkout"]
    result = await invoke(client, "checkout")
    shop.checkout.assert_called_once_with()
    assert result["number"] == "ORDER-1"
    shop.initiate_payment.assert_not_called()
    shop.send_socialpay.assert_not_called()


@pytest.mark.parametrize("tool,method,arguments,key", [
    ("get_product", "product", {"slug": "shoe"}, "listing"),
    ("get_variant_stores", "variant_stores", {"variant_id": "V1"}, "variant_stores"),
    ("get_order", "order_status", {"number": "ORDER-1"}, "order"),
    ("get_cart", "current_cart", {}, "cart"),
])
@pytest.mark.parametrize("missing", [False, True])
async def test_optional_objects(client, shop, storefront, tool, method, arguments, key, missing):
    operation = getattr(shop, method)
    operation.return_value = None if missing else storefront[key]
    result = await invoke(client, tool, **arguments)
    operation.assert_called_once_with(*arguments.values())
    assert (result is None) is missing


@pytest.mark.parametrize("tool,method,arguments,key,expected", [
    ("add_to_cart", "add_to_cart", {"variant_id": "V1", "quantity": 2}, "cart", "V1"),
    ("update_cart_item", "update_cart_item", {"line_item_id": "L1", "quantity": 0}, "cart_update", "L1"),
    ("update_cart_item", "update_cart_item", {"line_item_id": "L1", "quantity": 1}, "cart_update", "L1"),
])
async def test_cart_mutation_arguments(client, shop, storefront, tool, method, arguments, key, expected):
    operation = getattr(shop, method)
    operation.return_value = storefront[key]
    result = await invoke(client, tool, **arguments)
    operation.assert_called_once_with(expected, quantity=arguments["quantity"])
    assert result["id"] == "ID-1"


@pytest.mark.parametrize("tool,method,arguments", [
    ("add_to_cart", "add_to_cart", {"variant_id": "V1", "quantity": -1}),
    ("add_to_cart", "add_to_cart", {"variant_id": "V1", "quantity": "1"}),
    ("update_cart_item", "update_cart_item", {"line_item_id": "L1", "quantity": True}),
    ("checkout", "checkout", {"number": "ORDER-1"}),
    ("pay_with_socialpay", "initiate_payment", {"number": "ORDER-1", "unexpected": "value"}),
    ("pay_with_socialpay", "initiate_payment", {"number": " "}),
    ("pay_with_socialpay", "initiate_payment", {"number": "ORDER-1", "send_to_phone": "yes"}),
    ("get_product", "product", {"slug": ""}),
    ("search_products", "search_products", {"limit": 101}),
    ("get_orders", "list_orders", {"first": 0}),
])
async def test_invalid_inputs_do_not_call_client(client, shop, tool, method, arguments):
    result = await client.call_tool(tool, arguments, raise_on_error=False)
    assert result.is_error
    getattr(shop, method).assert_not_called()


@pytest.mark.parametrize("payment", INVALID_PAYMENTS)
async def test_malformed_payment_is_masked_and_never_sent(client, shop, payment):
    shop.initiate_payment.return_value = payment
    result = await client.call_tool(
        "pay_with_socialpay", {"number": "ORDER-1", "send_to_phone": True}, raise_on_error=False,
    )
    assert result.is_error
    assert "private-secret" not in str(result.content)
    shop.initiate_payment.assert_called_once_with(action="golomt_wallet", order_number="ORDER-1")
    shop.send_socialpay.assert_not_called()


@pytest.mark.parametrize("language", ["mn", "en"])
async def test_invoice_link_selection(client, shop, language):
    url = INVOICE_URL.replace("/mn/", f"/{language}/")
    shop.initiate_payment.return_value = {
        "number": "PAYMENT-1", "attributes": {"url": url, "token": "bank-secret"},
    }
    result = await invoke(client, "pay_with_socialpay", number="ORDER-1")
    assert result == {"url": url, "phoneRequest": None, "phoneError": None}
    shop.initiate_payment.assert_called_once_with(action="golomt_wallet", order_number="ORDER-1")
    shop.send_socialpay.assert_not_called()


async def test_phone_request_reuses_the_invoice(client, shop):
    shop.initiate_payment.return_value = {"number": "PAYMENT-1", "attributes": {"url": INVOICE_URL}}
    shop.send_socialpay.return_value = {"status": "PENDING", "refToken": "reference-secret"}
    result = await invoke(client, "pay_with_socialpay", number="ORDER-1", send_to_phone=True)
    assert result == {"url": INVOICE_URL, "phoneRequest": "PENDING", "phoneError": None}
    shop.initiate_payment.assert_called_once_with(action="golomt_wallet", order_number="ORDER-1")
    shop.send_socialpay.assert_called_once_with(INVOICE_URL)


async def test_phone_refusal_keeps_the_link(client, shop):
    shop.initiate_payment.return_value = {"number": "PAYMENT-1", "attributes": {"url": INVOICE_URL}}
    shop.send_socialpay.side_effect = ShoppyError("Payment provider rejected the SocialPay session.")
    result = await invoke(client, "pay_with_socialpay", number="ORDER-1", send_to_phone=True)
    assert result == {
        "url": INVOICE_URL, "phoneRequest": None,
        "phoneError": "Payment provider rejected the SocialPay session.",
    }
    shop.send_socialpay.assert_called_once_with(INVOICE_URL)


@pytest.mark.parametrize("tool,method,arguments", [
    ("checkout", "checkout", {}),
    ("pay_with_socialpay", "send_socialpay", {"number": "ORDER-1", "send_to_phone": True}),
])
async def test_mutation_timeouts_are_masked_without_retry(client, shop, tool, method, arguments):
    shop.initiate_payment.return_value = {"attributes": {"url": INVOICE_URL}}
    operation = getattr(shop, method)
    operation.side_effect = httpx.ReadTimeout("private-provider-secret")
    result = await client.call_tool(tool, arguments, raise_on_error=False)
    assert result.is_error and "private-provider-secret" not in str(result.content)
    operation.assert_called_once()
    shop.login.assert_called_once_with("test-user", "test-password")


@pytest.mark.parametrize("error", [
    ShoppyError("Cannot check out an empty order."),
    NotFoundError("Shoppy could not find the requested item."),
])
async def test_expected_client_errors_reach_the_agent(client, shop, error):
    shop.checkout.side_effect = error
    result = await client.call_tool("checkout", {}, raise_on_error=False)
    assert result.is_error
    assert result.content[0].text == str(error)
    shop.checkout.assert_called_once_with()


@pytest.mark.parametrize("error", [ValueError("private-provider-secret"), KeyError("private-provider-secret")])
async def test_unexpected_client_errors_stay_masked(client, shop, error):
    shop.current_cart.side_effect = error
    result = await client.call_tool("get_cart", {}, raise_on_error=False)
    assert result.is_error
    assert result.content[0].text == "Error calling tool 'get_cart'"


def test_setup_logs_in_once(shop):
    create_server("test-user", "test-password")
    shop.login.assert_called_once_with("test-user", "test-password")


@pytest.mark.parametrize("error", [
    httpx.HTTPStatusError("Unauthorized", request=httpx.Request("POST", "https://example.com"), response=httpx.Response(401)),
    httpx.ConnectError("Network unavailable"), RuntimeError("Unexpected bug"),
])
def test_startup_preserves_login_errors(shop, error):
    shop.login.side_effect = error
    with pytest.raises(type(error)) as exc:
        create_server("test-user", "test-password")
    assert exc.value is error
    shop.login.assert_called_once()


def test_credentials_are_read_from_environment(clean_env):
    clean_env.setenv("SHOPPY_USERNAME", "env-user")
    clean_env.setenv("SHOPPY_PASSWORD", "env-password")
    assert load_credentials() == ("env-user", "env-password")


def test_credentials_are_read_from_dotenv(clean_env, env_file):
    assert load_credentials(env_file) == ("test-user", "test-password")


def test_environment_overrides_dotenv(clean_env, env_file):
    clean_env.setenv("SHOPPY_PASSWORD", "env-password")
    assert load_credentials(env_file) == ("test-user", "env-password")


def test_missing_credentials_are_rejected(clean_env, env_file):
    env_file.write_text("SHOPPY_USERNAME=test-user\n")
    with pytest.raises(ValueError, match="SHOPPY_USERNAME and SHOPPY_PASSWORD"):
        load_credentials(env_file)


def test_cli_rejects_missing_credentials(clean_env, shop, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["shoppy-mcp"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert "SHOPPY_USERNAME and SHOPPY_PASSWORD" in capsys.readouterr().err
    shop.login.assert_not_called()


async def test_expired_auth_is_masked_without_relogin(client, shop):
    shop.current_cart.side_effect = httpx.HTTPStatusError(
        "private-api-secret", request=httpx.Request("POST", "https://example.com"), response=httpx.Response(401),
    )
    result = await client.call_tool("get_cart", {}, raise_on_error=False)
    assert result.is_error and "private-api-secret" not in str(result.content)
    shop.current_cart.assert_called_once()
    shop.login.assert_called_once()


async def test_stdio_discovery_and_structured_response(clean_env, env_file):
    script = env_file.parent / "smoke_server.py"
    script.write_text('''
from unittest.mock import patch
from shoppy.mcp import create_server, load_credentials, main
with patch("shoppy.mcp.Shoppy", autospec=True) as factory:
    factory.return_value.categories.return_value = [
        {"id": "C1", "name": "Shoes", "permalink": "shoes", "hasChildren": False},
    ]
    server = create_server(*load_credentials(".env"))
    factory.return_value.login.assert_called_once_with("test-user", "test-password")
    server.run(transport="stdio", show_banner=False)
''')
    transport = StdioTransport(sys.executable, [str(script)], cwd=str(env_file.parent))
    async with Client(transport) as client:
        await client.ping()
        assert len(await client.list_tools()) == 12
        assert (await invoke(client, "get_categories"))[0]["id"] == "C1"
        result = await client.call_tool("get_product", {"slug": ""}, raise_on_error=False)
        assert result.is_error
