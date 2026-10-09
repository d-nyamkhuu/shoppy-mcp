"""GraphQL selections for shopping workflows observed in the storefront HAR."""

_CURRENT_ORDER = """
fragment currentOrder on Order {
  id
  number
  token
  digital
  paymentState
  shipmentState
  total
  shipmentTotal
  adjustmentTotal
  taxTotal
  totalQuantity
  itemCount
  totalAppliedStoreCredit
  totalAfterStoreCredit
  usableStoreCredit
  updatedAt
  allAdjustments {
    id
    amount
    label
  }
  lineItems {
    id
    quantity
    manifest {
      id
      name
      image
      price
      slug
      expireAt
      optionsText
      fulfillDuration
      totalOnHand
      canSupply
      maxQty
    }
    price
    total
  }
}
"""


CHECK_LOGIN = """
mutation authCheckLogin($login: String!, $no_token: Boolean) {
  exists: authCheckLogin(input: {login: $login, noToken: $no_token})
}
"""

ME = """
query me {
  me {
    id
    firstName
    lastName
    mobile
    email
  }
}
"""

CURRENT_ORDER = """
query currentOrder {
  currentOrder {
    ...currentOrder
    billAddress {
      id
      firstname
      lastname
      phone
      company
      isCompany
    }
    shipAddress {
      id
    }
    shipments {
      selectedShippingRate {
        shippingMethod {
          id
          name
        }
      }
    }
  }
}
""" + _CURRENT_ORDER

UPDATE_ITEM = """
mutation updateItem($input: updateItemInput!) {
  updateItem(input: $input) {
    id
    total
    totalAfterStoreCredit
    itemCount
    lineItems {
      id
      quantity
      sku
      name
      total
      manifest {
        id
        expireAt
      }
    }
    allAdjustments {
      id
      amount
    }
  }
}
"""

MENUS = """
query menus {
  menus {
    id
    title
    data
    __typename
  }
}
"""

FLAT_TAXONS = """
query flatTaxon {
  flatTaxon
}
"""

ROOT_TAXONS = """
query rootTaxons {
  taxons(filter: {depth: {eq: 0}}, sort: {direction: asc, field: "position"}) {
    nodes {
      id
      hasChildren
      name
      permalink
    }
  }
}
"""

CHILD_TAXONS = """
query taxonNodes($parentId: ID) {
  taxons(
    filter: {parentId: {eq: $parentId}, listingsCount: {gt: 0}}
    sort: {field: "position", direction: asc}
  ) {
    nodes {
      ...Taxon
      children {
        ...Taxon
      }
    }
  }
}

fragment Taxon on Taxon {
  id
  name
  permalink
  hasChildren
}
"""

PRODUCT = """
query product($slug: String!) {
  listing(slug: $slug, impression: true) {
    id
    slug
    shippingCategoryId
    fulfillDuration
    maxQty
    minQty
    taxons {
      id
      name
      permalink
    }
    product {
      id
      name
      title
      description
      sku
      slug
      price
      sellingPrice
      image
      variantsIncludingMaster {
        id
        isMaster
        backorderable
        sku
        price
        sellingPrice
        canSupply
        optionsText
        totalOnHand
        image(size: mini)
      }
      brand {
        id
        name
      }
    }
  }
}
"""

VARIANT_STORES = """
query variantStores($variantId: ID!) {
  variant(id: $variantId) {
    id
    stockItems {
      id
      countOnHand
    }
    storeItems {
      countOnHand
      storeLocation {
        departmentStore {
          address
          title
        }
        address
        floor
        id
        phone
        title
      }
    }
  }
}
"""

ADD_TO_CART = """
mutation addToCart($batch: [CartItemInput!], $number: String, $token: String, $single: CartItemInput, $params: JSON) {
  order: addToCart(
    input: {batch: $batch, number: $number, single: $single, token: $token, params: $params}
  ) {
    ...currentOrder
  }
}
""" + _CURRENT_ORDER

DETAILED_ME = """
query detailedMe {
  me {
    id
    firstName
    lastName
    mobile
    email
    userAddresses(first: 10) {
      nodes {
        id
        address {
          id
          alias
          firstname
          lastname
          phone
          alternativePhone
          address1
          address2
          company
          isCompany
          cdq
          state {
            id
            name
          }
          district {
            id
            name
          }
          quarter {
            id
            name
          }
        }
      }
    }
  }
}
"""

UPDATE_CHECKOUT = """
mutation updateCheckoutOrder($shippingAddress: AddressInput, $shippingAddressId: ID, $number: String!, $params: JSON!, $shippingMethodId: ID) {
  updateCheckoutOrder(
    input: {shippingAddress: $shippingAddress, shippingAddressId: $shippingAddressId, number: $number, params: $params, shippingMethodId: $shippingMethodId}
  ) {
    ...currentOrder
    outstandingBalance
  }
}
""" + _CURRENT_ORDER

ORDER = """
query OrderDetails($number: String!) {
  order(number: $number) {
    adjustmentTotal
    shipments {
      selectedShippingRate {
        shippingMethod {
          id
          name
        }
      }
    }
    allAdjustments {
      id
      amount
      label
    }
    canceledAt
    cancellable
    completedAt
    digital
    editable
    id
    itemCount
    itemTotal
    number
    outstandingBalance
    paidAt
    paymentState
    paymentTotal
    shipmentState
    shipmentTotal
    shippedAt
    state
    total
    totalAfterStoreCredit
    totalAppliedStoreCredit
    lineItems {
      id
      price
      name
      quantity
      manifest {
        id
        name
        image
        price
        optionsText
        fulfillDuration
        totalOnHand
        canSupply
        maxQty
      }
    }
    updatedAt
  }
}
"""

PAYMENT_METHODS = """
query paymentMethods {
  paymentMethods(active: true) {
    id
    active
    name
    position
    methodType
    description
    data
    __typename
  }
}
"""

ORDER_PAY = """
mutation orderPay($input: orderPayInput!) {
  orderPay(input: $input)
}
"""

ORDERS = """
query myOrders($first: Int, $cursor: String, $sort: SortFilter, $status: OrderStatus, $filter: OrderFilter) {
  orders(
    first: $first
    after: $cursor
    sort: $sort
    status: $status
    filter: $filter
  ) {
    totalCount
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        number
        state
        shipmentState
        paymentState
        total
        completedAt
        updatedAt
        paidAt
        lineItems {
          id
          quantity
          manifest {
            id
            name
            image
          }
        }
      }
    }
  }
}
"""
