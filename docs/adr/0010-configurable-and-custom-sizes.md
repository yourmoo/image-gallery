# 10. Configurable named sizes and bounded custom dimensions

## Context

The three named sizes were hardcoded at 200, 400, and 800 pixels. Two problems
follow.

First, brief line 96 asks for key parameters to be environment-driven and names
"default image size" among them. Hardcoded pixel values cannot be tuned per
deployment, and the numbers behind `large` are exactly the kind of thing a
deployment might want to change — a retina-oriented deployment wants bigger
images than a bandwidth-constrained one.

Second, three fixed sizes are a narrow vocabulary. A user who wants a specific
aspect ratio, or a size between medium and large, has no way to ask.

[ADR 9](0009-url-vocabularies.md) rejected exposing pixel dimensions in client
URLs, on the grounds that unbounded dimensions are an unbounded upstream fetch
multiplier. That objection is answered by a ceiling, not by refusing the
feature — and the ceiling is itself configuration.

**Measured provider behaviour changes the risk calculation.** picsum.dev does
not enforce its own documented limits:

| Request | Result |
| --- | --- |
| `1200/900` | 200, 59 KB |
| `1600/1600` | 200, 130 KB |
| `6000/6000` | 200, **970 KB** — despite documented max of 5000 |
| `0/0` | 200, 693 bytes — no error |

An unbounded custom size is therefore not a theoretical concern. Fifty tiles at
`6000x6000` is roughly 48 MB of upstream traffic for a single page view, and the
provider will serve it.

## Decision

**Named sizes become configuration.** Pixel dimensions move out of code:

    GALLERY_SIZE_SMALL=200x200
    GALLERY_SIZE_MEDIUM=400x400
    GALLERY_SIZE_LARGE=800x800

**Custom dimensions are accepted as a fourth form of the same `size`
parameter**, not as separate `w` and `h` parameters:

    /images/7?size=large        named
    /images/7?size=1200x900     custom

**A configurable ceiling and floor bound both forms:**

    GALLERY_MAX_DIMENSION=1600
    GALLERY_MIN_DIMENSION=16

The bounds apply to **named sizes as well as custom ones**, validated at
startup. Without that, an operator setting `GALLERY_SIZE_LARGE=5000x5000` would
make the ceiling decorative.

## Consequences

**One parameter, one validator, one cache-key component.** Accepting custom
dimensions through `size` rather than through separate `w`/`h` parameters avoids
three states — named only, custom only, and both specified — of which the third
has no obviously correct resolution.

**The allow-list requirement (line 155) still holds**, in a broader form: `size`
accepts three names plus a bounded numeric grammar. Anything else falls back to
the default and explains itself, exactly as
[ADR 6](0006-recover-and-explain.md) specifies. Out-of-range dimensions are an
invalid value, not a clamped one — silently serving 1600 when 6000 was asked for
would be a worse answer than saying the value was rejected.

**The ceiling sets the worst-case cache entry.** At 1600 that is roughly 130 KB,
about three times a `large` image. Raising the ceiling raises memory pressure
proportionally, which is the trade-off an operator is making when they change
it.

**The cache key space becomes unbounded in principle.** With named sizes alone
it was 66 variants per image. Custom dimensions make it
`catalogue × widths × heights × 2 × 11`, which at a 1600 ceiling is millions of
reachable keys. In practice the working set stays small because custom
dimensions are a rare path — but **a hostile client can evict the cache by
walking dimensions**, and that is a real cost of this decision rather than a
hypothetical one. Custom-dimension responses are cached normally; adding a
separate TTL or bypass for them was rejected as complicating the cache for a
rare path, but it is the obvious mitigation if eviction becomes a problem.

**A floor is required, not optional.** `0/0` returns 200 with a 693-byte
response rather than an error, so without `GALLERY_MIN_DIMENSION` a degenerate
size would produce a valid-looking but useless image.

**Provider independence narrows slightly.** `1200x900` is pixel vocabulary, so a
provider offering only named sizes could not honour a custom request without
mapping it to the nearest supported size. This is a deliberate narrowing of
[ADR 9](0009-url-vocabularies.md)'s abstraction, accepted because pixel
dimensions are near-universal among image providers, and named sizes remain the
primary vocabulary.

**CSS tokens and fetch dimensions decouple.** The design system's
`--image-small/medium/large` and the `--cell-*` grid floors are presentation
values governing layout; the configured pixel dimensions govern what the proxy
fetches. They are allowed to diverge, and deliberately are not generated from
settings — templating a stylesheet to keep them in step would couple the
rendering layer to deployment configuration for no user-visible gain.

**The UI exposes named sizes only.** The size control remains a three-option
select. Custom dimensions are a URL-level capability for someone who wants a
specific size, not a form field — a free-text dimension input would invite
exactly the traffic the ceiling exists to bound.

## Alternatives rejected

**Keep hardcoded named sizes.** Simplest, but contradicts line 96 and leaves the
definition of `large` unchangeable without a code change.

**Separate `w` and `h` parameters.** More conventional, but creates the
both-specified ambiguity and a second validator, and splits one concept across
two cache-key components.

**Unbounded custom dimensions.** Rejected outright: the provider serves 6000px
images despite documenting a 5000 limit, so the application would be the only
thing standing between a query string and 48 MB page loads.

**Clamp out-of-range dimensions to the ceiling.** Serving 1600 when 6000 was
requested is a silent substitution the user cannot detect. Falling back to the
default with a notice is consistent with every other invalid parameter.

**A free-text dimension control in the UI.** Would make custom sizes
discoverable, but invites the traffic pattern the ceiling exists to prevent and
adds a validation surface to the form for a rare need.
