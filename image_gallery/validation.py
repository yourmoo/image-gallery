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

Only `page` and `count` are validated here today. `size`, `grayscale`, and
`blur` arrive with the stages that render them; adding them now would mean
writing rules no test exercises.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
        """
        return f"invalid_{self.parameter}"


@dataclass
class Validated:
    """Validated parameters plus the record of what was rejected to get them."""

    page: int
    count: int
    rejections: list[Rejection] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.rejections


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

    An absent parameter is not a rejection — it is the default being used as
    intended. Only a value that was supplied and cannot be honoured is
    reported, so a first visit carries no notice.
    """
    if raw is None or not str(raw).strip():
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
    """
    if raw is None or not str(raw).strip():
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


def validate(
    params,
    *,
    page_sizes: tuple[int, ...],
    default_count: int,
    catalogue_size: int,
) -> Validated:
    """Validate a whole query string's worth of parameters.

    `count` is resolved first because it determines how many pages exist, and
    therefore what counts as a valid `page`. Validating them in the other order
    would judge `page` against the wrong bound whenever `count` was also
    supplied.
    """
    count, count_rejection = validate_count(
        params.get("count"), allowed=page_sizes, default=default_count
    )
    page, page_rejection = validate_page(
        params.get("page"), last_page=total_pages(catalogue_size, count)
    )

    rejections = [r for r in (count_rejection, page_rejection) if r is not None]
    return Validated(page=page, count=count, rejections=rejections)
