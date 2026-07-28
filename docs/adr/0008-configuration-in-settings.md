# 8. `settings.py` alone reads the environment

## Context

Brief line 96 asks for key parameters to be environment-driven: default image
size, default count per page, cache settings, and retry/timeout behaviour.

The default Django habit is to call `os.environ.get` wherever a value is needed.
That spreads the configuration surface across the codebase, so no single file
answers "what can be configured?", and it makes tests reach for
`patch.dict(os.environ)` — which is process-global, order-dependent, and easy to
leak between tests.

## Decision

**`image_gallery/settings.py` is the only module that reads `os.environ`.**
Every environment variable is resolved there into a named module-level setting;
application code reads it through `django.conf.settings`.

This is enforced by `test_only_settings_reads_the_environment`, which AST-parses
every module in the package and fails if any non-exempt file touches
`os.environ` or `os.getenv`. It is an invariant, not a convention.

Two permanent exemptions, both bootstrap-only: `wsgi.py` and `manage.py` set
`DJANGO_SETTINGS_MODULE`, which is what points Django at the settings module in
the first place and therefore cannot live inside it.

## Consequences

**The whole configuration surface is auditable in one file.** Answering "what
is configurable?" means reading one module.

**Tests use `override_settings`** rather than patching the environment. It is
scoped, reversible, and cannot leak into another test.

**Values must be named module-level settings, not inline reads.** This is the
non-obvious part, and it was learned the hard way: three cache variables were
originally read inline inside the `CACHES` dictionary literal. They were
configurable, but service code could not reach them — `settings.CACHES` exposed
a nested dict rather than a named value. They are now named settings referenced
by `CACHES`, and a test asserts the two stay wired together.

**Type coercion happens once, at the boundary.** Helpers turn environment
strings into `bool`, `int`, and `float` in settings, so application code
receives real types and never parses a string.

**Test-harness configuration stays out.** `E2E_BASE_URL` in `tests/conftest.py`
tells Playwright which server to drive. The application never reads it, so it
does not belong in settings or in the shipped package.

**New configuration has one obvious home**, which is what keeps the invariant
from eroding.

## Alternatives rejected

**Read `os.environ` where needed.** Conventional and convenient. Rejected
because it disperses the configuration surface and pushes tests toward global
environment patching.

**`django-environ` or a similar library.** Adds type coercion and `.env` parsing
for a handful of variables. The hand-rolled helpers are about fifteen lines and
add no dependency; the library's value would come with a much larger
configuration surface than this application has.

**A separate `config.py` module.** Another indirection that would then need its
own rule about who may read it. Django already designates a settings module —
using it as intended is simpler than layering something over it.

**Convention without enforcement.** A documented rule with no test decays at the
first deadline. The AST test makes the invariant self-defending.
