# 7. The detail view opens large, and the user may change it

> **Amended 2026-07-29.** This ADR originally decided the detail view renders
> at `large` *unconditionally* — size was not the user's to set there. It now
> renders large **by default** and offers a control to change it, at the user's
> direction. The reasoning below stands as the reason for the default; what
> changed is that the default is no longer a rule.
>
> See [Amendment](#amendment-size-becomes-a-control) at the end for what that
> costs and why it was judged acceptable.

## Context

The brief states two requirements for the detail page that conflict:

- **Line 71** — display a larger version of the image.
- **Line 72** — reflect all active transformations.

If size counts as a transformation, these contradict each other whenever the
user is browsing at `small`: "larger" says render big, "reflect all active
transformations" says render small. Both cannot hold.

## Decision

The detail view **opens** at `large`, or at the gallery's size if that is
already larger. Grayscale and blur carry over from the gallery. All three are
adjustable on the page — see the amendment below.

The parameters panel (line 73) reports the values **actually used**, so size
reads `large` even when the gallery was showing `small`.

The "or larger" clause exists because [ADR 10](0010-configurable-and-custom-sizes.md)
allows custom dimensions above the named `large`. Browsing at `1200x900` and
opening an image must not drop to 800×800 — that would make the detail view
*smaller* than the grid, the precise opposite of what line 71 asks for. The rule
is therefore "never smaller than the gallery, and never smaller than `large`".

## Consequences

**"Larger" is satisfied on arrival.** Opening any image from any gallery size
produces a larger image. Since the amendment the user may then choose a smaller
one, so the guarantee is about what the application *does*, not about what the
user is permitted to ask for.

**The conflict resolves by category, not by precedence.** Size is a
*presentation* choice belonging to its context — a grid wants small images so
many fit, a detail page wants a big one because it shows a single image. Blur
and grayscale are *content* choices describing how the image should look
anywhere. Read that way, "all active transformations" means the filters, and
"larger" governs size. Neither requirement is being overridden; they were
addressing different things.

**The parameters panel carries the honesty burden.** Because the detail view
silently changes one of the user's parameters on arrival, the panel showing
`large` is what keeps that from being a surprise. This is why line 73 matters
more than it first appears, and why the panel reports actual values rather than
requested ones. The amendment makes the panel the control as well as the
report, which strengthens rather than weakens that: a value you can see and
change is harder to be surprised by than one you can only see.

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

**This alternative was adopted on 2026-07-29**, at the user's direction. The
objection above was half right: it *is* scope the brief does not ask for. It
was wrong that the underlying question goes unanswered — the default is still
`large`, decided for exactly the reasons above, and the control changes what
happens *after* arrival rather than instead of it.

## Amendment: size becomes a control

Size, grayscale, and blur are all adjustable on the detail page. The page opens
at `large` with the gallery's filters, and the parameters panel becomes the
control surface rather than only a report.

**What this costs.** Brief line 71 — "display a larger version" — no longer
holds unconditionally. Choosing `small` on the detail page produces an image
smaller than the grid was showing. The line is satisfied by what the
application does on arrival, not by what it prevents the user from doing
afterwards.

That is a real weakening, and it is accepted deliberately. The reading is that
line 71 describes the *view's purpose* — you open an image to see it better —
rather than a constraint the application must enforce against its own user. An
application that refuses to show you a smaller image when you have asked twice,
once by choosing it and once by seeing the result, is not serving the
requirement; it is serving a literal reading of it.

**What is unchanged.** The default, and every reason for it. Arriving from a
`small` gallery still gives a `large` image, still reports `large` in the
panel, and the custom-size-above-large rule still applies to that default. A
user who touches nothing sees exactly what this ADR originally specified.

**What the panel becomes.** Both report and control. The honesty burden this
ADR placed on it is easier to carry, not harder: a value shown in a control the
user can operate is more discoverable than the same value shown as static text,
because changing it demonstrates what it means.

**The round trip is unaffected.** The back link still restores the *gallery's*
size, not the detail page's. A size chosen on the detail page belongs to that
page, in the same way the gallery's size belongs to the grid — otherwise
opening one image at `small` would silently re-render the whole grid on return.
