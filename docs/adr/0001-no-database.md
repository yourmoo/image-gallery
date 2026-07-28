# 1. No database

## Context

Django ships with a relational store configured and most Django applications
use one, so *not* having a database is the decision that needs justifying — not
the reverse.

The brief asks for "state model choice and rationale" (line 234), which is a
design question to answer rather than a mandate. Three constraints bear on it:

- Line 81 scopes image caching to "while the app is running" — persistence is
  explicitly limited to process lifetime.
- Line 17 forbids new external services, ruling out Redis and Memcached.
- There is no user-owned data anywhere in the brief: no accounts, uploads,
  favourites, or history.

Every piece of state the application holds is either **derivable from the URL**
(page, size, grayscale, blur, count) or **fetched from upstream** (image bytes).
Neither needs durable storage.

## Decision

`DATABASES = {}`. State lives in the URL and in a bounded in-process cache.

The contrib apps requiring a database — `admin`, `auth`, `sessions`,
`messages` — are not installed.

## Consequences

**No sessions, therefore no `django.contrib.messages`.** This is the
consequence with real reach: the brief requires a user-facing validation message
to survive a redirect (line 48). Without sessions there is no flash-message
mechanism, so the notice travels as a query parameter — see
[ADR 6](0006-recover-and-explain.md). That is a direct downstream cost of this
decision, not an independent choice.

**No migrations, no database container, no fixtures.** The application starts
with a single command and needs no setup step, which is what the brief asks for
(lines 199–200).

**The cache is per-process.** `LocMemCache` is not shared between gunicorn
workers, so two workers hold two copies and a cache hit depends on which worker
serves the request. This is a real cost, documented rather than accidental, and
it is one of the inputs to the still-open cache design.

**Tests need no database.** The suite runs in-process with no fixture setup,
which is why the fast tier stays fast.

## Alternatives rejected

**SQLite for cache overflow.** A database tier holding "cold" cache entries
would be slower than simply regenerating them — the payloads are recomputable
and small. It adds a migration story and a file to manage for no gain.

**Redis or Memcached.** Ruled out by line 17. They would also be the natural
answer to the per-worker cache split, which is worth stating plainly: the
constraint costs something real, and this is where.

**A database "just in case".** Unused infrastructure is not free — it invites
questions about migrations, connection pooling, and backup that the application
does not need to answer.
