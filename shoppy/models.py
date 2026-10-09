"""Shared JSON type and selected storefront response models.

Models follow the client selections and captured response types. Unknown fields
are ignored at every object boundary, including tokens and provider metadata.
"""

from typing import Annotated, Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

JSON = dict[str, Any]

Identifier = Annotated[str, Field(strict=True, min_length=1, pattern=r"\S")]
Positive = Annotated[int, Field(strict=True, ge=1)]
Quantity = Annotated[int, Field(strict=True, ge=0)]
PageSize = Annotated[int, Field(strict=True, ge=1, le=100)]


class ResponseModel(BaseModel):
    model_config = ConfigDict(
        extra="ignore", strict=True, hide_input_in_errors=True,
    )


class Named(ResponseModel):
    id: str
    name: str


class Category(Named):
    permalink: str
    hasChildren: bool
    children: list["Category"] | None = None


class SearchProduct(ResponseModel):
    id: int
    slug: str
    name: str
    title: str
    price: float
    selling_price: float
    total_on_hand: int
    image: str | None


class SearchTotal(ResponseModel):
    value: int
    relation: Literal["eq", "gte"]


class SearchResults(ResponseModel):
    total: int | SearchTotal
    products: list[SearchProduct]


class Variant(ResponseModel):
    id: str
    sku: str
    isMaster: bool
    backorderable: bool
    price: float
    sellingPrice: float
    canSupply: bool
    optionsText: str
    totalOnHand: float
    image: str | None


class Product(ResponseModel):
    name: str
    title: str
    description: str | None
    price: float
    sellingPrice: float
    image: str | None
    brand: Named | None
    variantsIncludingMaster: list[Variant]


class Listing(ResponseModel):
    slug: str
    minQty: int | None
    maxQty: int | None
    product: Product


class DepartmentStore(ResponseModel):
    title: str
    address: str | None


class StoreLocation(ResponseModel):
    id: str
    title: str
    address: str | None
    floor: str | None
    phone: str | None
    departmentStore: DepartmentStore | None


class StoreItem(ResponseModel):
    countOnHand: int
    storeLocation: StoreLocation


class StockItem(ResponseModel):
    id: str
    countOnHand: int


class VariantStores(ResponseModel):
    id: str
    stockItems: list[StockItem]
    storeItems: list[StoreItem]


class Address(ResponseModel):
    id: str
    alias: str | None
    firstname: str | None
    lastname: str | None
    phone: str | None
    address1: str | None
    address2: str | None
    state: Named | None
    district: Named | None
    quarter: Named | None


class Profile(ResponseModel):
    id: str
    firstName: str | None
    lastName: str | None
    email: str | None
    mobile: str | None


class DetailedProfile(Profile):
    addresses: list[Address]


class ItemSummary(ResponseModel):
    id: str
    name: str
    image: str | None


class ItemDetails(ItemSummary):
    optionsText: str
    canSupply: bool
    totalOnHand: int
    maxQty: int | None


class OrderLine(ResponseModel):
    id: str
    quantity: int
    price: float
    manifest: ItemDetails


class CartLine(OrderLine):
    total: float


class Adjustment(ResponseModel):
    amount: float
    label: str | None


class Cart(ResponseModel):
    id: str
    number: str
    digital: bool
    paymentState: str | None
    shipmentState: str | None
    total: float
    shipmentTotal: float
    adjustmentTotal: float
    taxTotal: float
    totalAppliedStoreCredit: float
    totalAfterStoreCredit: float
    itemCount: int
    lineItems: list[CartLine]
    allAdjustments: list[Adjustment]


class UpdatedLine(ResponseModel):
    id: str
    quantity: int
    sku: str
    name: str
    total: float


class CartUpdate(ResponseModel):
    """The smaller response returned by updateItem, without an order number."""

    id: str
    total: float
    totalAfterStoreCredit: float
    itemCount: int
    lineItems: list[UpdatedLine]


class CheckoutOrder(Cart):
    outstandingBalance: float


class OrderSummary(ResponseModel):
    id: str
    number: str
    state: str
    paymentState: str | None
    shipmentState: str | None
    total: float
    paidAt: str | None
    completedAt: str | None
    updatedAt: str


class Order(OrderSummary):
    digital: bool
    editable: bool
    cancellable: bool
    canceledAt: str | None
    shippedAt: str | None
    itemTotal: float
    paymentTotal: float
    shipmentTotal: float
    adjustmentTotal: float
    outstandingBalance: float
    totalAppliedStoreCredit: float
    totalAfterStoreCredit: float
    lineItems: list[OrderLine]
    allAdjustments: list[Adjustment]


class OrderSummaryLine(ResponseModel):
    id: str
    quantity: int
    manifest: ItemSummary


class OrderListItem(OrderSummary):
    lineItems: list[OrderSummaryLine]


class PageInfo(ResponseModel):
    hasNextPage: bool
    endCursor: str | None


class Orders(ResponseModel):
    orders: list[OrderListItem]
    totalCount: int
    pageInfo: PageInfo


class SocialPayPayment(ResponseModel):
    """One SocialPay attempt; the provider's payment-attempt number is omitted."""

    url: str = Field(description="SocialPay invoice for the shopper to open.")
    phoneRequest: Literal["PENDING"] | None = Field(
        default=None,
        description="PENDING means the request was sent to the phone, not that the order is paid.",
    )
    phoneError: str | None = Field(
        default=None, description="Why the phone request was not sent; url still works.",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        """Expose only the captured SocialPay HTTPS invoice handoff."""
        if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Invalid SocialPay URL.")
        parsed = urlsplit(value)
        parts = parsed.path.strip("/").split("/")
        if (
            parsed.scheme != "https" or parsed.netloc != "ecommerce.golomtbank.com"
            or parsed.query or parsed.fragment or len(parts) != 3
            or parts[0] != "socialpay" or parts[1] not in {"mn", "en"}
        ):
            raise ValueError("Invalid SocialPay URL.")
        UUID(parts[2])
        return value
