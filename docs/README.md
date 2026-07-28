# Docs

Project documentation that is too long or too specialised for the root
[README](../README.md).

The root README is still the overview, and all testing documentation lives in
[tests/README.md](../tests/README.md).

## Contents

| File | Topic |
| --- | --- |
| [api-contract.md](api-contract.md) | Endpoints, parameters, and error behaviour — **test-enforced**, so it cannot drift |
| [core-features.md](core-features.md) | The 22 Core Requirements as features F1–F5, and the decisions shaping them |
| [ui/](ui/) | The visual layer — design brief, tokens, and components |
| [adr/](adr/) | Architecture decision records — one file per decision, with alternatives rejected |

## What belongs here

Longer-form material as it gets written, most of it corresponding to sections
the assignment brief requires:

| Topic | Belongs here when |
| --- | --- |
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

A topic gets its own subdirectory once it needs more than one file — `adr/` and
`ui/` each carry their own README indexing what is inside, so the table above
lists the directory rather than growing a row per file.
