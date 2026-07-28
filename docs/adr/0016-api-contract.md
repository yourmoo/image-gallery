# 16. The API contract is hand-written Markdown, enforced by tests

## Context

Brief line 227 requires documenting "endpoints, accepted parameters, and
response/error behaviour". [ADR 2](0002-client-side-rendering.md) makes the JSON
API the primary interface, so this is a substantive deliverable.

A hand-written document has one fatal property: nothing stops it drifting. It is
true when written and decays silently from the first change — worse than absent,
because a reader trusts it.

Three approaches were tried before this one, and the failures are the reason for
the decision.

**A generator over view-declared metadata.** A module walked the URLconf and
collected an `openapi` dict from each view, emitting `docs/openapi.yaml`. It
worked, but plain Django views expose almost nothing to introspection: paths and
route names are recoverable, while query parameters live inside method bodies as
`request.GET.get(...)` calls. The parameters therefore had to be declared in a
dict beside the code that read them — **the contract written twice**, with only
a test to notice divergence. It also put a documentation script inside the
application package.

**django-ninja.** This genuinely solves the duplication: parameters come from
typed function signatures, schemas from `Schema` classes, and the OpenAPI
description is derived at request time with nothing written twice. It was built
and worked. Rejected on proportionality — a runtime dependency, pydantic in the
container, and a second framework's idioms alongside Django's, to describe a
handful of read-only endpoints.

**Asking an assistant to keep `openapi.yaml` current.** Rejected outright: a
hand-maintained document by another name, accurate only when someone remembers
to ask. A stale spec that looks generated is worse than honest prose.

## Decision

**`docs/api-contract.md`, hand-written, with `tests/unit/test_api_contract.py`
parsing it and failing on drift.**

The document's Endpoints table is machine-readable by construction:

    | Route name | Path | Method | Response |
    | `healthz`  | `/healthz` | GET | `application/json` |

The test parses that table and asserts, against the live URLconf:

| Check | Catches |
| --- | --- |
| Every documented route exists | A promise nothing keeps |
| Every route is documented | An endpoint added without documenting it |
| Documented path == `reverse(name)` | A path that changed under the document |
| Documented content types are served | A response type that quietly changed |
| No provider vocabulary in the description | [ADR 9](0009-url-vocabularies.md) violations |

A "Planned endpoints" table holds routes that are specified but not yet served.
It is deliberately excluded from enforcement — otherwise the build would fail
for work not yet started.

**No OpenAPI description is published.** For three read-only endpoints with no
authentication, a clear parameter table and an error-behaviour table serve a
reader better than a schema document, and cost no dependency.

## Consequences

**Drift is a build failure.** Verified by tampering, in three directions: adding
a route without documenting it, documenting a route that is not served, and
changing a documented path. Each fails, and each passes again once corrected.
The guard is not vacuous.

**Prose carries the behaviour, which is where the value is.** The interesting
parts of this contract are behavioural — invalid parameters recover with a
notice rather than erroring, out-of-range dimensions are rejected rather than
clamped, degraded responses are still `200`. A generated schema would emit
`type: string` for these and leave the explanation to a hand-written description
anyway.

**Views are class-based** ([ADR 13](0013-module-structure.md)), which the earlier
attempts had already introduced for their own reasons and which stands on its
own: the gallery views share a parameter-parsing prologue that belongs in a
mixin.

**Zero new dependencies.** `django-ninja`, `pydantic`, `pyyaml`, and
`openapi-spec-validator` were all installed during the attempts above and have
been removed.

**The parsing itself needs a guard.** A formatting change could silently empty
the table and make every comparison trivially pass, so a test asserts the table
parses to a non-empty set of `/`-prefixed paths.

**Accepted values stay out of the document.** The `count` allow-list, the pixel
bounds, and the catalogue size are deployment configuration rather than
interface: publishing them would make the contract differ per deployment. A
rejected value names what is accepted, which is discoverable at runtime and
always correct.

## Alternatives rejected

Covered in Context: a metadata-driven generator (contract written twice),
django-ninja (disproportionate runtime dependency), and assistant-maintained
YAML (hand-maintained by another name).

**Django REST Framework with `drf-spectacular`.** The conventional answer, and
heavier than django-ninja for the same reasons — ViewSets, routers, serializers,
permissions, and throttling that this application does not use.

**No document at all, endpoints described in the root README.** Adequate for two
endpoints today. Rejected because the brief asks for an API contract section,
and because the README would then be the hand-tracked document this decision
exists to avoid.
