# 7. The detail view always renders large

## Context

The brief states two requirements for the detail page that conflict:

- **Line 71** — display a larger version of the image.
- **Line 72** — reflect all active transformations.

If size counts as a transformation, these contradict each other whenever the
user is browsing at `small`: "larger" says render big, "reflect all active
transformations" says render small. Both cannot hold.

## Decision

The detail view renders at `large`, or at the gallery's size if that is already
larger. Grayscale and blur carry over from the gallery.

The parameters panel (line 73) reports the values **actually used**, so size
reads `large` even when the gallery was showing `small`.

The "or larger" clause exists because [ADR 10](0010-configurable-and-custom-sizes.md)
allows custom dimensions above the named `large`. Browsing at `1200x900` and
opening an image must not drop to 800×800 — that would make the detail view
*smaller* than the grid, the precise opposite of what line 71 asks for. The rule
is therefore "never smaller than the gallery, and never smaller than `large`".

## Consequences

**"Larger" is satisfied unconditionally.** Opening any image from any gallery
size produces a larger image. The requirement holds in every case rather than in
most.

**The conflict resolves by category, not by precedence.** Size is a
*presentation* choice belonging to its context — a grid wants small images so
many fit, a detail page wants a big one because it shows a single image. Blur
and grayscale are *content* choices describing how the image should look
anywhere. Read that way, "all active transformations" means the filters, and
"larger" governs size. Neither requirement is being overridden; they were
addressing different things.

**The parameters panel carries the honesty burden.** Because the detail view
silently changes one of the user's parameters, the panel showing `large` is what
keeps that from being a surprise. This is why line 73 matters more than it first
appears, and why the panel reports actual values rather than requested ones.

**Filters must survive the round trip.** Gallery → detail → back must preserve
page, size, grayscale, and blur. The tile link carries the active query, and the
back link restores it. The Gherkin asserts the full round trip.

**Out-of-range image ids return 404**, unlike invalid transformations which
recover ([ADR 6](0006-recover-and-explain.md)). A bad transformation has a
sensible default; a request for image 101 in a 100-image catalogue does not.
Showing image 1 instead would be a worse answer than saying it does not exist.
This is a deliberate inconsistency between two kinds of bad input.

## Alternatives rejected

**Step up one size** — small→medium, medium→large, large→large. Preserves the
user's size choice as a relative notion, which is appealing. Rejected because
`large` has nowhere to go, so the rule needs a special case, and because "one
size larger than what you were browsing" is a rule users must infer rather than
observe.

**Keep the requested size, display it at full width.** The purest reading of
"reflect all active transformations" — the detail view changes nothing. Rejected
because a `small` image displayed at full width is an upscaled 200px image: it
is larger on screen and worse to look at, which satisfies line 71 in letter and
fails it in spirit.

**Make detail size a user control.** Sidesteps the conflict by letting the user
choose. Rejected as scope the brief does not ask for, and it leaves the
underlying question — what happens by default — unanswered.
