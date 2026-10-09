"""Local FastMCP interface for a single Shoppy account."""

import argparse
import os
from pathlib import Path

from dotenv import dotenv_values
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware

from .client import Shoppy, ShoppyError
from .models import (
    Cart,
    CartUpdate,
    Category,
    CheckoutOrder,
    DetailedProfile,
    Identifier,
    Listing,
    Order,
    Orders,
    PageSize,
    Positive,
    Profile,
    Quantity,
    SearchResults,
    SocialPayPayment,
    VariantStores,
)


class ShowShoppyErrors(Middleware):
    """Show expected client failures; FastMCP keeps masking every other error."""

    async def on_call_tool(self, context, call_next):
        try:
            return await call_next(context)
        except ToolError as exc:
            if isinstance(exc.__cause__, ShoppyError):
                raise ToolError(str(exc.__cause__)) from exc.__cause__
            raise


def load_credentials(env_file: str | Path | None = None) -> tuple[str, str]:
    """Read the account username and password from the environment or a dotenv file.

    Environment variables take precedence over values in the dotenv file.
    """
    values = {**dotenv_values(env_file), **os.environ} if env_file else os.environ
    username, password = values.get("SHOPPY_USERNAME"), values.get("SHOPPY_PASSWORD")
    if not username or not password:
        raise ValueError("Set SHOPPY_USERNAME and SHOPPY_PASSWORD.")
    return username, password


def create_server(username: str, password: str) -> FastMCP:
    """Initialize one authenticated client and register its shopping tools."""
    client = Shoppy()
    client.login(username, password)

    server = FastMCP(
        "Shoppy", mask_error_details=True, strict_input_validation=True,
        instructions=(
            "Search, inspect variants, and use the shopper's selection to manage the cart. "
            "Review checkout before creating a payment. "
            "After a failed mutation, inspect the cart or order before trying again; "
            "changes may already be saved. Do not automatically retry mutations."
        ),
        middleware=[ShowShoppyErrors()],
    )
    read = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}
    write = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True}
    additive = {**write, "destructiveHint": False}

    @server.tool(annotations=read)
    def search_products(
        query: str = "", category_id: Identifier | None = None,
        limit: PageSize = 30, offset: Quantity = 0,
    ) -> SearchResults:
        """Search in-stock products by relevance; pass a returned slug to get_product to choose a variant.

        Product IDs are not variant IDs. limit is the page size (at most 100);
        offset + limit cannot exceed 10000. total is {value, relation: "gte"} when
        more than 10000 products match.
        """
        hits = client.search_products(
            query, category_id=category_id, limit=limit, offset=offset,
        )["hits"]
        return SearchResults(
            total=hits["total"], products=[hit["_source"] for hit in hits["hits"]],
        )

    @server.tool(annotations=read)
    def get_categories(parent_id: Identifier | None = None) -> list[Category]:
        """List root categories, or the children of a category ID with their own subcategories.

        An unknown category ID returns an empty list.
        """
        return [Category.model_validate(category) for category in client.categories(parent_id)]

    @server.tool(annotations=read)
    def get_product(slug: Identifier) -> Listing | None:
        """Get product details, quantity limits and variants by slug, or null if the slug does not exist."""
        listing = client.product(slug)
        return Listing.model_validate(listing) if listing is not None else None

    @server.tool(annotations=read)
    def get_variant_stores(variant_id: Identifier) -> VariantStores | None:
        """Get stock levels and store locations for a variant, or null if the variant does not exist."""
        stores = client.variant_stores(variant_id)
        return VariantStores.model_validate(stores) if stores is not None else None

    @server.tool(annotations=read)
    def get_profile(detailed: bool = False) -> DetailedProfile | Profile:
        """Get the account profile, optionally including saved delivery addresses."""
        profile = client.profile(detailed=detailed)
        if detailed:
            return DetailedProfile.model_validate({
                **profile, "addresses": [node["address"] for node in profile["userAddresses"]["nodes"]],
            })
        return Profile.model_validate(profile)

    @server.tool(annotations=read)
    def get_orders(first: PageSize = 10, cursor: Identifier | None = None) -> Orders:
        """List orders, most recently updated first; the current cart can appear as an unfinished order.

        Pass pageInfo.endCursor unchanged as cursor for the next page; an
        unrecognized cursor restarts at the first page.
        """
        page = client.list_orders(
            first=first, cursor=cursor, sort={"field": "updated_at", "direction": "desc"},
        )
        return Orders(
            orders=[edge["node"] for edge in page["edges"]],
            totalCount=page["totalCount"], pageInfo=page["pageInfo"],
        )

    @server.tool(annotations=read)
    def get_order(number: Identifier) -> Order | None:
        """Get an order's payment and shipping status, or null if the order does not exist.

        Only paymentState "paid" confirms payment. A complete order can still have a
        balance due, and paidAt can be set on a failed payment.
        """
        order = client.order_status(number)
        return Order.model_validate(order) if order is not None else None

    @server.tool(annotations=read)
    def get_cart() -> Cart | None:
        """Get the current cart, line items and totals, or null if there is no cart."""
        cart = client.current_cart()
        return Cart.model_validate(cart) if cart is not None else None

    @server.tool(annotations=additive)
    def add_to_cart(variant_id: Identifier, quantity: Positive = 1) -> Cart:
        """Add the shopper's selected variant to the real account cart. Repeating adds more items.

        Listed stock can be stale; an out-of-stock refusal leaves the cart unchanged.
        """
        return Cart.model_validate(client.add_to_cart(variant_id, quantity=quantity))

    @server.tool(annotations=write)
    def update_cart_item(line_item_id: Identifier, quantity: Quantity) -> CartUpdate:
        """Set a cart line's quantity; zero removes it. Return updated lines and totals; get_cart provides full details."""
        return CartUpdate.model_validate(client.update_cart_item(line_item_id, quantity=quantity))

    @server.tool(annotations=write)
    def checkout() -> CheckoutOrder:
        """Save checkout details for the current cart using the account's addresses.

        Reuse the cart's address or the account's only saved address. If several
        addresses exist, select one for the cart on Shoppy before checkout.
        """
        return CheckoutOrder.model_validate(client.checkout())

    @server.tool(annotations=additive)
    def pay_with_socialpay(number: Identifier, send_to_phone: bool = False) -> SocialPayPayment:
        """Create a SocialPay attempt for an order number and return its url for the shopper to open.

        Set send_to_phone only when the shopper asks for a request on the account's
        mobile; it sends this attempt's invoice there. If the provider refuses,
        phoneError explains and url still works. Each call creates a new attempt
        and may send another notification. Check get_order paymentState afterward.
        """
        payment = client.initiate_payment(action="golomt_wallet", order_number=number)
        url = SocialPayPayment(url=payment["attributes"]["url"]).url
        if not send_to_phone:
            return SocialPayPayment(url=url)
        try:
            result = client.send_socialpay(url)
        except ShoppyError as exc:
            return SocialPayPayment(url=url, phoneError=str(exc))
        return SocialPayPayment(url=url, phoneRequest=result["status"])

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Shoppy FastMCP server.")
    parser.add_argument("--env-file", type=Path, help="dotenv file with SHOPPY_USERNAME and SHOPPY_PASSWORD")
    args = parser.parse_args()
    try:
        username, password = load_credentials(args.env_file)
    except ValueError as exc:
        parser.error(str(exc))
    create_server(username, password).run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
