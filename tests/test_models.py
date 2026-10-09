"""Validate selected response fields and the observed storefront types."""

import pytest
from pydantic import TypeAdapter, ValidationError

from shoppy.models import (
    Address,
    Adjustment,
    Cart,
    CartUpdate,
    Category,
    CheckoutOrder,
    DetailedProfile,
    Listing,
    Order,
    Orders,
    Profile,
    SearchProduct,
    SearchResults,
    SocialPayPayment,
    UpdatedLine,
    VariantStores,
)

INVOICE_URL = "https://ecommerce.golomtbank.com/socialpay/mn/00000000-0000-0000-0000-000000000001"


def add_unknown_fields(value):
    if isinstance(value, list):
        return [add_unknown_fields(item) for item in value]
    if isinstance(value, dict):
        return {**{key: add_unknown_fields(child) for key, child in value.items()},
                "token": "private-marker", "futureField": "private-marker"}
    return value


@pytest.mark.parametrize("fixture,model", [
    ("listing", Listing), ("categories", list[Category]), ("child_categories", list[Category]),
    ("variant_stores", VariantStores), ("profile", Profile), ("cart", Cart),
    ("cart_update", CartUpdate), ("checkout", CheckoutOrder), ("order", Order),
])
def test_captured_models_discard_unknown_nested_fields(storefront, fixture, model):
    adapter = TypeAdapter(model)
    result = adapter.validate_python(add_unknown_fields(storefront[fixture]))
    encoded = adapter.dump_json(result)
    assert b"private-marker" not in encoded
    assert b"cart-secret" not in encoded


@pytest.mark.parametrize("model,value", [
    (SearchResults, {"total": {"value": 1, "relation": "eq"}, "products": [{
        "id": 101, "slug": "shoe", "name": "Shoe", "title": "Shoe", "price": 100.0,
        "selling_price": 90.0, "total_on_hand": 2, "image": None,
    }]}),
    (DetailedProfile, {
        "id": "U1", "firstName": "Test", "lastName": None, "email": None, "mobile": None,
        "addresses": [{
            "id": "A1", "alias": "Home", "firstname": None, "lastname": None, "phone": None,
            "address1": "Street", "address2": None, "state": {"id": "S1", "name": "City"},
            "district": None, "quarter": None,
        }],
    }),
    (Orders, {"totalCount": 1, "pageInfo": {"hasNextPage": False, "endCursor": "C1"}, "orders": [{
        "id": "O1", "number": "ORDER-1", "state": "complete", "paymentState": "balance_due",
        "shipmentState": None, "total": 100.0, "paidAt": None, "completedAt": None,
        "updatedAt": "2026-09-11T01:00:00Z", "lineItems": [{
            "id": "L1", "quantity": 2, "manifest": {"id": "V1", "name": "Shoe", "image": None},
        }],
    }]}),
])
def test_flat_models_discard_unknown_nested_fields(model, value):
    assert model.model_validate(add_unknown_fields(value)).model_dump() == value


@pytest.mark.parametrize("value", [{"token": "private-marker"}, ["private-marker"], 1, True, None])
def test_order_numbers_require_strings(storefront, value):
    with pytest.raises(ValidationError):
        Cart.model_validate({**storefront["cart"], "number": value})


@pytest.mark.parametrize("field,value", [("quantity", True), ("quantity", "2"), ("price", "100"), ("price", False)])
def test_line_values_are_not_coerced(storefront, field, value):
    storefront["cart"]["lineItems"][0][field] = value
    with pytest.raises(ValidationError):
        Cart.model_validate(storefront["cart"])


def test_cart_requires_total(storefront):
    del storefront["cart"]["total"]
    with pytest.raises(ValidationError):
        Cart.model_validate(storefront["cart"])


def test_detailed_profile_requires_addresses(storefront):
    with pytest.raises(ValidationError):
        DetailedProfile.model_validate(storefront["profile"])


def test_search_product_ids_are_integers(storefront):
    product = SearchProduct.model_validate(storefront["search"]["hits"]["hits"][0]["_source"])
    assert type(product.id) is int


def test_listing_types_and_fields(storefront):
    listing = Listing.model_validate(storefront["listing"])
    variant = listing.product.variantsIncludingMaster[0]
    assert type(variant.id) is str
    assert type(variant.totalOnHand) is float
    assert listing.minQty is None and listing.maxQty is None
    assert set(listing.model_dump()) == {"slug", "minQty", "maxQty", "product"}
    assert not {"id", "sku", "slug"} & listing.product.model_dump().keys()


def test_cart_nulls_and_field_selection(storefront):
    cart = Cart.model_validate(storefront["cart"])
    assert cart.paymentState is None
    assert cart.lineItems[0].manifest.image is None
    assert not {"token", "billAddress", "shipAddress", "email", "usableStoreCredit"} & cart.model_dump().keys()
    assert "price" not in cart.lineItems[0].manifest.model_dump()


def test_address_nulls_and_field_selection(storefront):
    address = Address.model_validate(storefront["detailed_profile"]["userAddresses"]["nodes"][0]["address"])
    assert address.firstname is None and address.phone is None
    assert not {"cdq", "company", "isCompany", "alternativePhone"} & address.model_dump().keys()


def test_profile_strings_are_not_content_redacted(storefront):
    profile = Profile.model_validate({**storefront["profile"], "firstName": "literal token text"})
    assert profile.firstName == "literal token text"


def test_cart_update_omits_order_number_and_state(storefront):
    update = CartUpdate.model_validate(storefront["cart_update"])
    assert not {"number", "state"} & update.model_dump().keys()


def test_order_details_require_more_than_a_history_summary():
    with pytest.raises(ValidationError):
        Order.model_validate({
            "id": "O1", "number": "ORDER-1", "state": "complete", "paymentState": "balance_due",
            "shipmentState": None, "total": 100.0, "paidAt": None, "completedAt": None,
            "updatedAt": "2026-09-11T01:00:00Z", "lineItems": [],
        })


@pytest.mark.parametrize("total", [1, {"value": 1, "relation": "eq"}, {"value": 10000, "relation": "gte"}])
def test_search_total_shapes(total):
    assert SearchResults(total=total, products=[]).model_dump() == {"total": total, "products": []}


def test_nonempty_store_locations():
    stores = VariantStores.model_validate({
        "id": "V1", "stockItems": [], "storeItems": [{
            "countOnHand": 2, "storeLocation": {
                "id": "S1", "title": "Shop", "address": "Street", "floor": None,
                "phone": "11112222", "departmentStore": {"title": "Mall", "address": "Street"},
            },
        }],
    })
    assert stores.storeItems[0].storeLocation.phone == "11112222"


def test_updated_line_accepts_numeric_total():
    line = UpdatedLine(id="L1", quantity=2, sku="SKU-1", name="Shoe", total=100)
    assert line.total == 100.0


def test_adjustment_allows_discounts():
    adjustment = Adjustment(amount=-10, label="Discount")
    assert adjustment.amount == -10.0


def test_socialpay_payment_omits_provider_reference():
    result = SocialPayPayment.model_validate({
        "url": INVOICE_URL, "phoneRequest": "PENDING", "refToken": "private-marker",
    })
    assert result.model_dump() == {"url": INVOICE_URL, "phoneRequest": "PENDING", "phoneError": None}


def test_socialpay_phone_status_is_not_payment_confirmation():
    with pytest.raises(ValidationError):
        SocialPayPayment.model_validate({"url": INVOICE_URL, "phoneRequest": "PAID"})
