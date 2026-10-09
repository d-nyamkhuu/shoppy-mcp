"""Check request documents independently of the canned HTTP responses."""

import pytest
from graphql import build_schema, parse, validate
from graphql.language.ast import FragmentDefinitionNode, FragmentSpreadNode, OperationDefinitionNode
from graphql.validation import (
    KnownFragmentNamesRule,
    NoFragmentCyclesRule,
    NoUndefinedVariablesRule,
    NoUnusedFragmentsRule,
    NoUnusedVariablesRule,
    UniqueFragmentNamesRule,
    UniqueVariableNamesRule,
)

from shoppy import queries

DOCUMENTS = {name: value for name, value in vars(queries).items() if name.isupper() and not name.startswith("_")}


def selections(document):
    ast = parse(document)
    fragments = {node.name.value: node for node in ast.definitions if isinstance(node, FragmentDefinitionNode)}

    def paths(selection, prefix=()):
        result = {}
        for node in selection.selections:
            if isinstance(node, FragmentSpreadNode):
                result.update(paths(fragments[node.name.value].selection_set, prefix))
            else:
                path = (*prefix, (node.alias or node.name).value)
                result[".".join(path)] = node
                if node.selection_set:
                    result.update(paths(node.selection_set, path))
        return result

    operation = next(node for node in ast.definitions if isinstance(node, OperationDefinitionNode))
    return paths(operation.selection_set)


@pytest.mark.parametrize("name,document", DOCUMENTS.items())
def test_documents_are_well_formed(name, document):
    # Only schema-independent rules: the provider's schema is not available.
    errors = validate(build_schema("type Query { unused: String }"), parse(document), rules=(
        KnownFragmentNamesRule, NoFragmentCyclesRule, NoUndefinedVariablesRule,
        NoUnusedFragmentsRule, NoUnusedVariablesRule, UniqueFragmentNamesRule,
        UniqueVariableNamesRule,
    ))
    assert not errors, (name, errors)


@pytest.mark.parametrize("name,root", [
    ("CURRENT_ORDER", "currentOrder"), ("ADD_TO_CART", "order"),
    ("UPDATE_CHECKOUT", "updateCheckoutOrder"),
])
def test_cart_queries_retain_handles_and_line_details(name, root):
    fields = selections(DOCUMENTS[name])
    required = "number token total paymentState lineItems.id lineItems.quantity lineItems.manifest.name lineItems.manifest.maxQty"
    assert {f"{root}.{path}" for path in required.split()} <= fields.keys()


@pytest.mark.parametrize("name,required", [
    ("PRODUCT", "listing.slug listing.minQty listing.maxQty listing.product.description listing.product.variantsIncludingMaster.id listing.product.variantsIncludingMaster.optionsText listing.product.variantsIncludingMaster.canSupply listing.product.variantsIncludingMaster.totalOnHand"),
    ("ORDER", "order.number order.paidAt order.paymentState order.shipmentState order.total order.lineItems.id order.lineItems.manifest.name"),
    ("ORDERS", "orders.totalCount orders.pageInfo.hasNextPage orders.pageInfo.endCursor orders.edges.node.number orders.edges.node.paidAt orders.edges.node.paymentState"),
    ("UPDATE_ITEM", "updateItem.total updateItem.lineItems.id updateItem.lineItems.quantity"),
    ("DETAILED_ME", "me.email me.mobile me.userAddresses.nodes.address.id me.userAddresses.nodes.address.cdq me.userAddresses.nodes.address.address1"),
])
def test_queries_retain_workflow_fields(name, required):
    assert set(required.split()) <= selections(DOCUMENTS[name]).keys()


@pytest.mark.parametrize("name", [name for name in DOCUMENTS if name not in {
    "CHECK_LOGIN", "MENUS", "FLAT_TAXONS", "PAYMENT_METHODS", "ORDER_PAY",
}])
def test_queries_omit_discarded_fields(name):
    removed = {
        "__typename", "data", "extraData", "passportNumber", "registerNum", "birthday",
        "avatar", "images", "master", "productProperties", "optionValues", "reviews",
        "shipperManifest", "qty", "amount", "isDigital",
    }
    for path, node in selections(DOCUMENTS[name]).items():
        if ".allAdjustments." in path:
            continue
        assert node.name.value not in removed, path
        if node.name.value in {"billAddress", "shipAddress"}:
            assert name == "CURRENT_ORDER"  # Checkout needs these internally.
        if ".lineItems." in path:
            assert node.name.value not in {"product", "variant"}, path
        if node.name.value == "token":
            assert name in {"CURRENT_ORDER", "ADD_TO_CART", "UPDATE_CHECKOUT"}


def test_product_keeps_image_size_without_unused_image_variables():
    ast = parse(queries.PRODUCT)
    assert [node.variable.name.value for node in ast.definitions[0].variable_definitions] == ["slug"]
    image = selections(queries.PRODUCT)["listing.product.variantsIncludingMaster.image"]
    assert [(arg.name.value, arg.value.value) for arg in image.arguments] == [("size", "mini")]


def test_python_only_queries_keep_provider_payloads():
    assert "menus.data" in selections(queries.MENUS)
    assert "paymentMethods.data" in selections(queries.PAYMENT_METHODS)
    assert selections(queries.ORDER_PAY)["orderPay"].selection_set is None
