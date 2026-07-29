"""The client-vocabulary edge: raw query values in, validated values out.

This module is where an invalid parameter stops. It never resolves a name to
pixels and never names the provider — that is `provider.py`'s vocabulary
(docs/adr/0013-module-structure.md). It imports nothing from the rest of the
package, which is what keeps it testable without Django or a request.

Validation **returns** rejections rather than raising them. Both callers need
the recovered value *and* the record of what was rejected: the shell view
redirects to a corrected URL carrying a notice, and the image endpoints report
the rejection as a 400. An exception would unwind past the fallback that both
of them require (docs/adr/0019-validation-errors-carry-a-usable-payload.md).

`page`, `count`, and `size` are validated here. `grayscale` and `blur` arrive
with the stage that renders them.

**A parameter supplied as an empty string is a rejection, not an absence.**
`?page=` is a value the user gave that cannot be honoured, where omitting
`page` entirely is the default working as intended. Conflating the two leaves
`?page=` sitting in the address bar, uncorrected and unexplained — the dead end
docs/adr/0006-recover-and-explain.md exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote


@dataclass(frozen=True)
class Rejection:
    """One parameter that could not be honoured, and what happened instead.

    `accepted` describes the allow-list in the client's own terms so a caller
    can correct itself. It is deliberately a runtime value rather than
    something published in the contract: the allow-lists are deployment
    configuration (docs/adr/0016-api-contract.md).
    """

    parameter: str
    value: str
    applied: object
    accepted: str

    def as_dict(self) -> dict:
        """The shape the API's `errors` array carries.

        `applied` is deliberately absent: it is what the *browser* client needs
        in order to explain itself, while a programmatic caller is told what
        would be accepted and left to choose.
        """
        return {
            "parameter": self.parameter,
            "value": self.value,
            "accepted": self.accepted,
        }

    @property
    def notice(self) -> str:
        """The token carried in `?notice=` across the shell view's redirect.

        A token rather than a sentence: the wording belongs to the UI, and
        prose in a URL would be both unwieldy and untranslatable.

        The rejected value rides along after a colon, percent-encoded, because
        F3.6 asks the application to *explain* the fallback — a banner saying
        only "that size isn't valid" leaves the user guessing which of their
        parameters was ignored. The client decodes it and inserts it as text,
        never as markup.
        """
        return f"invalid_{self.parameter}:{quote(str(self.value), safe='')}"


@dataclass
class Validated:
    """Validated parameters plus the record of what was rejected to get them."""

    page: int
    count: int
    size: str = "medium"
    grayscale: bool = False
    blur: int = 0
    rejections: list[Rejection] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.rejections

    def variations(self) -> dict:
        """The parameters that change how an image looks, without `page` and
        `count`, which change only which images are shown."""
        return {"size": self.size, "grayscale": self.grayscale, "blur": self.blur}


def _as_int(raw: str | None) -> int | None:
    """Parse an ASCII decimal integer, treating anything else as absent.

    Deliberately stricter than `int()`, which accepts Unicode decimal digits —
    `int("٣")` is 3. Those round-trip through no other part of the system, and
    no control in the UI can produce one, so accepting them would let a request
    through that only a hand-edited URL could make.

    A missing value and an unparseable one are the same case for the caller:
    there is no usable value, so the default applies. They differ only in
    whether the substitution is worth reporting, which is decided above.
    """
    if raw is None:
        return None

    text = str(raw).strip()
    if not text:
        return None

    sign, digits = ("-", text[1:]) if text.startswith("-") else ("", text)
    if not digits.isascii() or not digits.isdigit():
        return None

    return int(sign + digits)


def validate_count(
    raw: str | None, allowed: tuple[int, ...], default: int
) -> tuple[int, Rejection | None]:
    """Resolve the per-page image count against its allow-list.

    An **absent** parameter is not a rejection — it is the default being used
    as intended, so a first visit carries no notice. A parameter supplied as
    an empty string is different: the user expressed an intent the application
    cannot honour, and `?count=` left uncorrected in the address bar with no
    explanation is exactly the dead end ADR 6 exists to prevent.
    """
    if raw is None:
        return default, None

    parsed = _as_int(raw)
    if parsed is not None and parsed in allowed:
        return parsed, None

    return default, Rejection(
        parameter="count",
        value=str(raw),
        applied=default,
        accepted=", ".join(str(n) for n in allowed),
    )


def total_pages(catalogue_size: int, count: int) -> int:
    """How many pages a catalogue of this size yields at this page size.

    At least 1: an empty catalogue still has a page 1 to render, and returning
    0 would make every page number invalid including the default. A count of 0
    is guarded rather than allowed to divide — validation should have rejected
    it, but this must not raise if something slips through.
    """
    if count <= 0:
        return 1
    return max(1, -(-catalogue_size // count))


def validate_page(raw: str | None, last_page: int) -> tuple[int, Rejection | None]:
    """Resolve the requested page against the catalogue's real bounds.

    Out of range is a rejection like any other bad value, so `?page=0`,
    `?page=abc`, and `?page=999` all recover to page 1 and explain themselves.
    The bound is real because the catalogue is bounded by configuration
    (docs/adr/0004-bounded-catalogue.md).

    `?page=` — supplied but empty — is a rejection rather than an absence, for
    the reason given on `validate_count`.
    """
    if raw is None:
        return 1, None

    parsed = _as_int(raw)
    if parsed is not None and 1 <= parsed <= last_page:
        return parsed, None

    return 1, Rejection(
        parameter="page",
        value=str(raw),
        applied=1,
        accepted=f"1 to {last_page}",
    )


NAMED_SIZES = ("small", "medium", "large")


def validate_size(
    raw: str | None, *, default: str, minimum: int, maximum: int
) -> tuple[str, Rejection | None]:
    """Resolve `size`: one of the three names, or `WxH` within the bounds.

    This module owns the *grammar* and never resolves a name to pixels — that
    is provider vocabulary (docs/adr/0013-module-structure.md). It returns the
    size as the client expressed it, normalised to lower case.

    **Out-of-range dimensions are rejected, never clamped.** Silently serving
    1600px when 6000 was requested would be undetectable to the caller
    (docs/adr/0010-configurable-and-custom-sizes.md), and picsum does not
    enforce its own documented limit, so this ceiling is the only thing
    bounding upstream traffic.
    """
    accepted = f"{', '.join(NAMED_SIZES)}, or WxH between {minimum} and {maximum}"

    if raw is None:
        return default, None

    text = str(raw).strip().lower()
    if text in NAMED_SIZES:
        return text, None

    width_text, separator, height_text = text.partition("x")
    width, height = _as_int(width_text), _as_int(height_text)

    if separator and width is not None and height is not None:
        if minimum <= width <= maximum and minimum <= height <= maximum:
            return text, None

    return default, Rejection(
        parameter="size", value=str(raw), applied=default, accepted=accepted
    )


TRUTHY = {"1", "true", "on", "yes"}
FALSY = {"0", "false", "off", "no", ""}


def validate_grayscale(raw: str | None) -> tuple[bool, Rejection | None]:
    """Resolve `grayscale` to a boolean.

    Several spellings are honoured because several producers exist: an unticked
    checkbox sends nothing, a ticked one sends `on`, and a hand-written URL is
    likelier to say `1` or `true`. They are one intent, so they get one answer.

    An absent parameter is off — the F3.3 default — and not a rejection.
    """
    if raw is None:
        return False, None

    text = str(raw).strip().lower()
    if text in TRUTHY:
        return True, None
    if text in FALSY:
        return False, None

    return False, Rejection(
        parameter="grayscale",
        value=str(raw),
        applied=False,
        accepted="on or off",
    )


def validate_blur(raw: str | None, *, maximum: int) -> tuple[int, Rejection | None]:
    """Resolve `blur` to an integer within its range.

    Unlike `size`, this bound is fixed by the contract rather than by
    deployment configuration, so it is part of the published interface
    (docs/api-contract.md).
    """
    if raw is None:
        return 0, None

    parsed = _as_int(raw)
    if parsed is not None and 0 <= parsed <= maximum:
        return parsed, None

    return 0, Rejection(
        parameter="blur",
        value=str(raw),
        applied=0,
        accepted=f"an integer from 0 to {maximum}",
    )


def validate(
    params,
    *,
    page_sizes: tuple[int, ...],
    default_count: int,
    catalogue_size: int,
    default_size: str = "medium",
    minimum_dimension: int = 16,
    maximum_dimension: int = 1600,
    maximum_blur: int = 10,
) -> Validated:
    """Validate a whole query string's worth of parameters.

    One call for all five, because the shell view and the image views both need
    the complete set — validating them piecemeal is how two callers end up
    disagreeing about what a request meant.

    `count` is resolved first because it determines how many pages exist, and
    therefore what counts as a valid `page`. Validating them in the other order
    would judge `page` against the wrong bound whenever `count` was also
    supplied.

    Each parameter is judged on its own, so **one bad value never discards a
    good one beside it** — `?size=enormous&blur=6` renders at the default size
    with blur 6 applied, and explains only the size
    (docs/adr/0006-recover-and-explain.md).
    """
    count, count_rejection = validate_count(
        params.get("count"), allowed=page_sizes, default=default_count
    )
    page, page_rejection = validate_page(
        params.get("page"), last_page=total_pages(catalogue_size, count)
    )
    size, size_rejection = validate_size(
        params.get("size"),
        default=default_size,
        minimum=minimum_dimension,
        maximum=maximum_dimension,
    )
    grayscale, grayscale_rejection = validate_grayscale(params.get("grayscale"))
    blur, blur_rejection = validate_blur(params.get("blur"), maximum=maximum_blur)

    rejections = [
        rejection
        for rejection in (
            count_rejection,
            page_rejection,
            size_rejection,
            grayscale_rejection,
            blur_rejection,
        )
        if rejection is not None
    ]

    return Validated(
        page=page,
        count=count,
        size=size,
        grayscale=grayscale,
        blur=blur,
        rejections=rejections,
    )
