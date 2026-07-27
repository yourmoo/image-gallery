# Docs

Project documentation that is too long or too specialised for the root
[README](../README.md).

Nothing has been moved here yet — the root README is still the single overview,
and all testing documentation lives in [tests/README.md](../tests/README.md).

## What belongs here

Longer-form material as it gets written, most of it corresponding to sections
the assignment brief requires:

| Topic | Belongs here when |
| --- | --- |
| API contract | Endpoints, accepted parameters, and error behaviour are defined |
| Design decisions | The rationale outgrows the root README's summary |
| Performance notes | There are targets, a measurement method, and observed numbers |
| Configuration reference | The env-var table needs more than one line per entry |
| Architecture | The service/provider/transformation split exists in code |

## What does not belong here

- **Testing docs** — those live in [tests/README.md](../tests/README.md).
- **Build and run instructions** — those stay in the root README, where someone
  cloning the repo will look first.
- **The assignment brief** — `django_image_gallery_assignment.md` stays at the
  root as the original source document.

## Convention

One topic per file, lowercase kebab-case names (`api-contract.md`). Add a row
to the table above when you add a file, so this stays an index rather than a
directory listing.
