"""GraphQL documents observed in the storefront HAR; no session data."""

CHECK_LOGIN = """
mutation authCheckLogin($login: String!, $no_token: Boolean) {
  exists: authCheckLogin(input: {login: $login, noToken: $no_token})
}
"""

ME = """
query me {
  me {
    id
    avatar
    firstName
    lastName
    nationality
    familyName
    createdAt
    login
    mobile
    unconfirmedMobile
    email
    gender
    birthday
    mobileConfirmedAt
    confirmedAt
    registerNum
    orderCount
    eTicketCount
    licenseCount
    userInvitationCode
    wallet
    segments {
      id
      code
      active
      __typename
    }
    __typename
  }
}
"""

CURRENT_ORDER = """
query currentOrder($number: String, $token: String) {
  currentOrder(number: $number, orderToken: $token) {
    ...currentOrder
    shipments {
      selectedShippingRate {
        shippingMethod {
          id
          name
          adminName
          __typename
        }
        __typename
      }
      __typename
    }
    allAdjustments {
      id
      label
      amount
      __typename
    }
    billAddress {
      id
      alias
      cdq
      address1
      phone
      firstname
      lastname
      districtName
      stateName
      quarterName
      company
      isCompany
      passportNumber
      __typename
    }
    shipAddress {
      id
      alias
      cdq
      address1
      phone
      firstname
      lastname
      districtName
      stateName
      quarterName
      __typename
    }
    shipperManifest {
      id
      name
      cost
      description
      phoneNumber
      email
      logo
      status
      shipments {
        id
        state
        digital
        cost
        selectedShippingRate {
          id
          name
          description
          __typename
        }
        lineItemManifest {
          id
          total
          lineItem {
            id
            price
            total
            data
            quantity
            adjustmentTotal
            preTaxAmount
            actn
            manifest {
              id
              name
              image
              slug
              price
              optionsText
              fulfillDuration
              totalOnHand
              canSupply
              maxQty
              ... on MovieTicketManifest {
                row
                column
                seat
                ticketType {
                  id
                  name
                  __typename
                }
                session {
                  id
                  date
                  time
                  __typename
                }
                __typename
              }
              __typename
            }
            __typename
          }
          product {
            id
            slug
            name
            title
            productCat
            brand {
              id
              name
              __typename
            }
            __typename
          }
          quantity
          states
          variant {
            id
            sku
            image
            optionsText
            __typename
          }
          __typename
        }
        __typename
      }
      __typename
    }
    __typename
  }
}

fragment currentOrder on Order {
  id
  number
  extraData
  token
  email
  digital
  paymentState
  shipmentState
  total
  shipmentTotal
  adjustmentTotal
  taxTotal
  paymentTypes
  totalQuantity
  itemCount
  totalAppliedStoreCredit
  totalAfterStoreCredit
  usableStoreCredit
  promotionIds
  updatedAt
  allAdjustments {
    id
    amount
    label
    __typename
  }
  lineItems {
    id
    quantity
    createdAt
    data
    isDigital
    listing {
      id
      shippingCategory {
        id
        name
        description
        __typename
      }
      __typename
    }
    manifest {
      id
      name
      image
      price
      slug
      price
      expireAt
      optionsText
      fulfillDuration
      totalOnHand
      canSupply
      maxQty
      ... on MovieTicketManifest {
        row
        column
        seat
        ticketType {
          id
          name
          __typename
        }
        session {
          id
          date
          time
          __typename
        }
        __typename
      }
      __typename
    }
    price
    total
    amount
    product {
      id
      slug
      sku
      name
      price
      sellingPrice
      productCat
      preferredEticketHideStock
      brand {
        id
        name
        __typename
      }
      productProperties {
        id
        position
        value
        property {
          id
          name
          presentation
          createdAt
          __typename
        }
        __typename
      }
      vendor {
        id
        name
        __typename
      }
      salePrices {
        id
        segmentId
        startAt
        expireAt
        amount
        __typename
      }
      listings {
        maxQty
        taxons {
          id
          name
          permalink
          __typename
        }
        __typename
      }
      __typename
    }
    variant {
      id
      sku
      image(size: product)
      price
      totalOnHand
      canSupply
      optionsText
      sellingPrice
      prices {
        id
        segmentId
        startAt
        expireAt
        amount
        __typename
      }
      __typename
    }
    __typename
  }
  __typename
}
"""

UPDATE_ITEM = """
mutation updateItem($input: updateItemInput!) {
  updateItem(input: $input) {
    id
    total
    totalAfterStoreCredit
    itemCount
    lineItems {
      ...CartLineItem
      __typename
    }
    allAdjustments {
      id
      amount
      __typename
    }
    promotionIds
    __typename
  }
}

fragment CartLineItem on LineItem {
  id
  quantity
  qty
  costPrice
  sku
  name
  total
  manifest {
    id
    expireAt
    __typename
  }
  __typename
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
      data
      hasChildren
      name
      permalink
      bannerLink
      position
      __typename
    }
    __typename
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
        __typename
      }
      __typename
    }
    __typename
  }
}

fragment Taxon on Taxon {
  id
  name
  permalink
  isDisabled
  listingsCount
  hasChildren
  __typename
}
"""

PRODUCT = """
query product($slug: String!, $format: ImageFormat, $height: Int!, $width: Int!) {
  listing(slug: $slug, impression: true) {
    id
    slug
    shippingCategoryId
    fulfillDuration
    maxQty
    minQty
    seoDescription
    seoKeywords
    seoTitle
    badges {
      id
      name
      priority
      attachment
      startAt
      expireAt
      active
      __typename
    }
    taxons {
      id
      name
      permalink
      isAdult
      __typename
    }
    product {
      id
      name
      averageRating
      availableOn
      availableUntil
      data
      info
      reviews(last: 5) {
        nodes {
          id
          comment
          createdAt
          rating
          user {
            avatar
            firstName
            lastName
            login
            id
            __typename
          }
          __typename
        }
        __typename
      }
      title
      description
      sku
      slug
      productCat
      preferredEticketHideStock
      price
      saleExpireAt
      sellingPrice
      sizingGuideId
      keyword {
        gpc
        name
        __typename
      }
      image
      images {
        id
        url
        __typename
      }
      optionTypes {
        id
        name
        presentation
        __typename
      }
      productProperties {
        id
        position
        value
        property {
          id
          name
          presentation
          createdAt
          __typename
        }
        __typename
      }
      master {
        id
        price
        sellingPrice
        totalOnHand
        canSupply
        __typename
      }
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
        saleStartDate
        saleEndDate
        image(size: mini)
        images {
          id
          url
          __typename
        }
        optionValues {
          id
          name
          optionTypeId
          presentation
          optionType {
            id
            name
            __typename
          }
          __typename
        }
        nutritionFact {
          servingQty
          servingUnit
          servingWeightGrams
          nfCalories
          fullNutrients
          __typename
        }
        salePrices {
          id
          amount
          startAt
          expireAt
          segmentId
          __typename
        }
        __typename
      }
      totalReviews
      promotionable
      brand {
        id
        code
        name
        logo
        officialLogo
        whiteLogo {
          id
          url(format: $format, height: $height, width: $width)
          __typename
        }
        blackLogo {
          id
          url(format: $format, height: $height, width: $width)
          __typename
        }
        averageRating
        follow {
          followersCount
          __typename
        }
        __typename
      }
      stage {
        id
        data
        __typename
      }
      __typename
    }
    __typename
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
      __typename
    }
    storeItems {
      countOnHand
      storeLocation {
        stockLocationIds
        departmentStore {
          address
          cover
          map
          title
          timeSheets
          winterTimeSheets
          __typename
        }
        address
        floor
        id
        map
        phone
        photo
        position
        timeSheets
        title
        winterTimeSheets
        __typename
      }
      __typename
    }
    __typename
  }
}
"""

ADD_TO_CART = """
mutation addToCart($batch: [CartItemInput!], $number: String, $token: String, $single: CartItemInput, $params: JSON) {
  order: addToCart(
    input: {batch: $batch, number: $number, single: $single, token: $token, params: $params}
  ) {
    ...currentOrder
    __typename
  }
}

fragment currentOrder on Order {
  id
  number
  extraData
  token
  email
  digital
  paymentState
  shipmentState
  total
  shipmentTotal
  adjustmentTotal
  taxTotal
  paymentTypes
  totalQuantity
  itemCount
  totalAppliedStoreCredit
  totalAfterStoreCredit
  usableStoreCredit
  promotionIds
  updatedAt
  allAdjustments {
    id
    amount
    label
    __typename
  }
  lineItems {
    id
    quantity
    createdAt
    data
    isDigital
    listing {
      id
      shippingCategory {
        id
        name
        description
        __typename
      }
      __typename
    }
    manifest {
      id
      name
      image
      price
      slug
      price
      expireAt
      optionsText
      fulfillDuration
      totalOnHand
      canSupply
      maxQty
      ... on MovieTicketManifest {
        row
        column
        seat
        ticketType {
          id
          name
          __typename
        }
        session {
          id
          date
          time
          __typename
        }
        __typename
      }
      __typename
    }
    price
    total
    amount
    product {
      id
      slug
      sku
      name
      price
      sellingPrice
      productCat
      preferredEticketHideStock
      brand {
        id
        name
        __typename
      }
      productProperties {
        id
        position
        value
        property {
          id
          name
          presentation
          createdAt
          __typename
        }
        __typename
      }
      vendor {
        id
        name
        __typename
      }
      salePrices {
        id
        segmentId
        startAt
        expireAt
        amount
        __typename
      }
      listings {
        maxQty
        taxons {
          id
          name
          permalink
          __typename
        }
        __typename
      }
      __typename
    }
    variant {
      id
      sku
      image(size: product)
      price
      totalOnHand
      canSupply
      optionsText
      sellingPrice
      prices {
        id
        segmentId
        startAt
        expireAt
        amount
        __typename
      }
      __typename
    }
    __typename
  }
  __typename
}
"""

DETAILED_ME = """
query detailedMe {
  me {
    id
    firstName
    lastName
    mobile
    unconfirmedMobile
    confirmationSentAt
    mobileConfirmationSentAt
    email
    unconfirmedEmail
    login
    avatar
    confirmedAt
    mobileConfirmedAt
    updatedAt
    gender
    birthday
    userAddresses(first: 10) {
      nodes {
        id
        address {
          ...address
          __typename
        }
        __typename
      }
      __typename
    }
    __typename
  }
}

fragment address on Address {
  id
  alias
  firstname
  lastname
  phone
  alternativePhone
  address1
  address2
  coordinate
  company
  isCompany
  passportNumber
  cdq
  state {
    id
    name
    __typename
  }
  district {
    id
    name
    __typename
  }
  quarter {
    id
    name
    __typename
  }
  __typename
}
"""

UPDATE_CHECKOUT = """
mutation updateCheckoutOrder($shippingAddress: AddressInput, $shippingAddressId: ID, $number: String!, $params: JSON!, $shippingMethodId: ID) {
  updateCheckoutOrder(
    input: {shippingAddress: $shippingAddress, shippingAddressId: $shippingAddressId, number: $number, params: $params, shippingMethodId: $shippingMethodId}
  ) {
    ...currentOrder
    outstandingBalance
    billAddress {
      id
      cdq
      address1
      phone
      firstname
      lastname
      isCompany
      company
      __typename
    }
    shipAddress {
      id
      cdq
      address1
      phone
      firstname
      lastname
      alias
      stateName
      districtName
      quarterName
      __typename
    }
    __typename
  }
}

fragment currentOrder on Order {
  id
  number
  extraData
  token
  email
  digital
  paymentState
  shipmentState
  total
  shipmentTotal
  adjustmentTotal
  taxTotal
  paymentTypes
  totalQuantity
  itemCount
  totalAppliedStoreCredit
  totalAfterStoreCredit
  usableStoreCredit
  promotionIds
  updatedAt
  allAdjustments {
    id
    amount
    label
    __typename
  }
  lineItems {
    id
    quantity
    createdAt
    data
    isDigital
    listing {
      id
      shippingCategory {
        id
        name
        description
        __typename
      }
      __typename
    }
    manifest {
      id
      name
      image
      price
      slug
      price
      expireAt
      optionsText
      fulfillDuration
      totalOnHand
      canSupply
      maxQty
      ... on MovieTicketManifest {
        row
        column
        seat
        ticketType {
          id
          name
          __typename
        }
        session {
          id
          date
          time
          __typename
        }
        __typename
      }
      __typename
    }
    price
    total
    amount
    product {
      id
      slug
      sku
      name
      price
      sellingPrice
      productCat
      preferredEticketHideStock
      brand {
        id
        name
        __typename
      }
      productProperties {
        id
        position
        value
        property {
          id
          name
          presentation
          createdAt
          __typename
        }
        __typename
      }
      vendor {
        id
        name
        __typename
      }
      salePrices {
        id
        segmentId
        startAt
        expireAt
        amount
        __typename
      }
      listings {
        maxQty
        taxons {
          id
          name
          permalink
          __typename
        }
        __typename
      }
      __typename
    }
    variant {
      id
      sku
      image(size: product)
      price
      totalOnHand
      canSupply
      optionsText
      sellingPrice
      prices {
        id
        segmentId
        startAt
        expireAt
        amount
        __typename
      }
      __typename
    }
    __typename
  }
  __typename
}
"""

PAYMENT_ACTION = """
mutation paymentAction($number: String!, $action: PaymentMethodKind!, $params: JSON) {
  paymentAction(input: {number: $number, action: $action, params: $params})
}
"""

ORDER = """
query OrderDetails($number: String!) {
  order(number: $number) {
    adjustmentTotal
    shipments {
      selectedShippingRate {
        shippingMethod {
          id
          name
          adminName
          __typename
        }
        __typename
      }
      __typename
    }
    allAdjustments {
      id
      amount
      label
      __typename
    }
    canceledAt
    cancellable
    completedAt
    driverTakenAt
    driver {
      id
      myReview {
        rating
        __typename
      }
      __typename
    }
    digital
    editable
    id
    itemCount
    email
    token
    itemTotal
    leaseBank
    leaseState
    number
    outstandingBalance
    paidAt
    paymentState
    paymentTotal
    posData
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
      variant {
        sku
        __typename
      }
      product {
        id
        productCat
        name
        __typename
      }
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
        ... on MovieTicketManifest {
          row
          column
          seat
          ticketType {
            id
            name
            __typename
          }
          session {
            id
            date
            time
            __typename
          }
          __typename
        }
        __typename
      }
      __typename
    }
    waitUntil
    updatedAt
    billAddress {
      ...address
      __typename
    }
    shipAddress {
      ...address
      __typename
    }
    user {
      id
      lastName
      firstName
      mobile
      email
      bankAccounts
      __typename
    }
    status {
      ...orderStatusFull
      __typename
    }
    shipperManifest {
      id
      name
      cost
      description
      phoneNumber
      email
      logo
      status
      shipments {
        id
        state
        digital
        cost
        selectedShippingRate {
          id
          name
          description
          __typename
        }
        lineItemManifest {
          id
          total
          lineItem {
            id
            price
            total
            data
            quantity
            adjustmentTotal
            preTaxAmount
            actn
            eTickets {
              id
              __typename
            }
            manifest {
              id
              name
              image
              slug
              price
              optionsText
              fulfillDuration
              totalOnHand
              canSupply
              maxQty
              ... on MovieTicketManifest {
                row
                column
                seat
                ticketType {
                  id
                  name
                  __typename
                }
                session {
                  id
                  date
                  time
                  __typename
                }
                __typename
              }
              __typename
            }
            __typename
          }
          product {
            id
            slug
            name
            title
            productCat
            brand {
              id
              name
              __typename
            }
            __typename
          }
          quantity
          states
          variant {
            id
            sku
            image
            optionsText
            __typename
          }
          __typename
        }
        __typename
      }
      __typename
    }
    __typename
  }
}

fragment address on Address {
  id
  alias
  firstname
  lastname
  phone
  alternativePhone
  address1
  address2
  coordinate
  company
  isCompany
  passportNumber
  cdq
  state {
    id
    name
    __typename
  }
  district {
    id
    name
    __typename
  }
  quarter {
    id
    name
    __typename
  }
  __typename
}

fragment orderStatusFull on OrderStatusType {
  id
  title
  description
  status
  isPaid
  isShipped
  isOutOfStock
  isCancelable
  isEditable
  isPayable
  isFeedbackEnabled
  __typename
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
      __typename
    }
    edges {
      node {
        ...orderForList
        __typename
      }
      __typename
    }
    __typename
  }
}

fragment orderForList on Order {
  id
  number
  leaseState
  state
  shipmentState
  paymentState
  total
  completedAt
  updatedAt
  waitUntil
  paidAt
  driverTakenAt
  ebarimt
  archived
  lineItems {
    id
    quantity
    qty
    actn
    variant {
      id
      name
      image
      __typename
    }
    manifest {
      id
      name
      image
      __typename
    }
    __typename
  }
  status {
    ...orderStatusListItem
    __typename
  }
  __typename
}

fragment orderStatusListItem on OrderStatusType {
  id
  title
  description
  status
  isPaid
  __typename
}
"""
