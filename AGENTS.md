# Project conventions

Follow the coding style of Tom Christie / Encode: small, explicit functions,
plain control flow, and abstractions that earn their place through actual use.

## Application code

- Initialize `Shoppy()` directly in MCP setup and call its public methods from
  tools. Do not add a `client_factory` or a generic operation-dispatch function.
- Declare concrete response types and return validated models directly. Do not
  introduce a generic `Result[T]` envelope or handwritten projection framework.
- Keep the shared JSON type and Pydantic models together in `shoppy/models.py`.
  Import model classes directly; avoid aliases such as `models as schema`.
- Expose fields needed for shopping. Flatten transport-only nesting such as
  `edges[].node`, `hits.hits[]._source`, and `userAddresses.nodes[].address` at the
  MCP boundary. Preserve meaningful totals, pagination, and null values.
- Base response types on the client queries and observed responses. Keep distinct
  models where operations return different fields, such as cart updates and
  full orders. Keep explicit validation and nested field selection.
- Keep nullable-response handling local. Use an early return when it improves
  readability; do not add a helper solely to hide a `None` check.
- Do not catch every exception and relabel it as a configuration or credential
  error. Preserve unexpected failures and handle specific expected errors where
  needed. Keep credentials and provider payloads out of public error messages.
- The current personal MCP adapter intentionally has no lock or custom
  serialization layer. Do not reintroduce one as speculative infrastructure.
  This is a project choice, not a claim that stdio guarantees sequential calls.
- Put general workflow guidance in server instructions and operation-specific
  guidance in tool descriptions. Avoid repeating the same instructions in both.
- Keep dependencies limited to what the code uses. Do not retain unused extras
  such as `pydantic[email]`.

## Tests

- Use direct imports and small fixtures with one clear purpose.
- Test MCP behavior with focused mocks of the public client methods. Assert
  argument forwarding, response shapes, and relevant error behavior explicitly.
  Patch dependencies in tests without adding injection hooks to production code.
- Keep a full MCP-to-client test with scripted HTTP responses and a stdio smoke
  test. Test HTTP contracts and provider failure sequences in client tests.
  Avoid building a stateful fake shopping service for ordinary adapter tests.
- Keep call helpers limited to calling and unwrapping results. Put schema
  validation and private-field exclusion in dedicated tests; do not rediscover
  every tool and rerun unrelated assertions on every helper call.
- Use small, explicit model inputs in their final response shape. Use sanitized
  captures for integration coverage. Do not duplicate the adapter's conversion
  pipeline in a model-test fixture or generate expected output from the code
  being tested.
- Give each test one coherent behavior. Split unrelated scenarios, and
  parameterize independent cases when it makes failures easier to identify.
- Compare dictionaries with `model_dump()` when testing fields. Serialize only
  when testing serialization or wire output; avoid dump/load round trips.
- Preserve useful coverage when simplifying tests. Keep checks for nulls, strict
  types, field selection, pagination, mutation targeting, and no automatic retries.
- Automated tests must not contact real shopping or payment services. Keep
  credentials, account details, and live provider payloads out of fixtures.

## Cleanup scope

Prefer removing unnecessary layers over adding configurable replacements. Keep
changes scoped to the requested cleanup, update affected imports and docs, and
run the relevant existing tests. Avoid compatibility shims for internal helpers
that have no supported callers.
