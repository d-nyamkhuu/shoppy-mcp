# Project conventions

Follow the coding style of Tom Christie / Encode: small, explicit functions,
plain control flow, and abstractions that earn their place through actual use.

## Application code

- Construct dependencies directly and call their public methods. Do not add
  factories, generic dispatchers, or injection hooks without a real need.
- Declare concrete types and return validated data directly. Avoid generic
  result envelopes and handwritten projection frameworks.
- Keep closely related types together and import them directly, without
  module aliases.
- Expose the fields callers need. Flatten transport-only nesting at system
  boundaries. Keep meaningful totals, pagination, and null values.
- Base types on actual usage and observed data. When operations return
  different shapes, keep separate types for them.
- Handle nullable values where they occur. Use an early return when it reads
  better. Do not add a helper only to hide a `None` check.
- Do not catch broad exceptions and relabel them. Handle the specific errors
  you expect and let unexpected failures surface. Keep secrets and raw
  third-party payloads out of user-facing errors.
- Do not add speculative infrastructure (locks, caches, serialization
  layers, config options) before there is a demonstrated need.
- Put each piece of guidance or documentation in one place. Do not repeat it.
- Keep dependencies and extras limited to what the code uses.

## Tests

- Use direct imports and small fixtures that each have one clear purpose.
- Mock at public interface boundaries. Check argument forwarding, response
  shapes, and error behavior explicitly. Patch dependencies inside tests, not
  through hooks added to production code.
- Keep a few end-to-end tests that use scripted external responses. Test
  protocol contracts and failure sequences at the layer that owns them. Avoid
  elaborate stateful fakes for ordinary unit tests.
- Test helpers should only call code and unwrap results. Put schema checks and
  cross-cutting assertions in dedicated tests.
- Use small, explicit inputs in their final shape. Use sanitized captures for
  integration coverage. Never generate expected output from the code being
  tested.
- Give each test one coherent behavior. Parametrize independent cases so it is
  clear which one failed.
- Compare structured data directly. Serialize only when the test is about
  serialization.
- Keep useful coverage when simplifying tests: nulls, strict types, field
  selection, pagination, mutation targeting, and no automatic retries.
- Automated tests must not call real external services. Keep credentials and
  personal data out of fixtures.

## Cleanup scope

Prefer removing unnecessary layers over adding configurable replacements. Keep
changes scoped to the requested cleanup, update affected imports and docs, and
run the relevant existing tests. Avoid compatibility shims for internal helpers
that have no supported callers.
