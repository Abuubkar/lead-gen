# Architecture

The challenge asks for the backend in specifics: data storage, caching and
performance, hosting model, deployment, cloud provider, and the exact
technologies. This answers each one, and says where a choice was a trade-off
rather than an obvious default.

## Stack

| Layer | Choice | Why this one |
|---|---|---|
| Language | Python 3.13 | Pinned locally and in the image. Top of Scrapling's supported range |
| Packaging | `uv` with a committed lockfile | The image resolves from the same lockfile a developer uses |
| HTTP | Starlette, with FastAPI's response and template helpers, on Uvicorn | Async routes and a JSON API from the same app as the HTML. The app object is a plain Starlette one: nothing here needs request-body validation or generated OpenAPI, so the heavier layer would have earned nothing |
| Templates | Jinja2, server-rendered | No client state to synchronise, no hydration |
| Interactivity | HTMX 2 from a CDN | Live rows and a detail panel with no bundler and no build step |
| Styling | One hand-written stylesheet | Custom properties for the palette, no framework |
| Scraping | Scrapling 0.4 | TLS impersonation, a stealth browser tier, and adaptive selectors in one library |
| Database | SQLite via the standard library | See below |
| Model | Claude Haiku 4.5, optional | Fills gaps the rules left. Never scores |
| Container | Docker, `python:3.13-slim` | One image, one process |
| Host | Render, Docker web service | See below |

## Data storage

**SQLite, through the standard library, no ORM.**

A single-writer, single-tenant sourcing tool with five tables does not need a
server. An ORM would have added a dependency, a model layer and a migration tool
to a schema that fits on one screen and is reviewed as SQL by a human.

The schema lives in one readable file and is applied with `executescript` on
every open. Every statement is idempotent, so there is no migration tool and no
state where the code and the database disagree. Tables are `STRICT`, so SQLite
enforces the declared column types rather than silently coercing.

Five tables: a search run, a business, a contact, a signal, and a review state.

**Signals are rows, not columns.** This is the decision the product rests on. A
signal row carries its name, its group, the value observed, the points awarded,
the points available, whether it resolved, the source the fact came from, and a
URL to cite where there is one. That is
what makes the score auditable, lets confidence be computed from the database
alone, and means adding a signal needs no migration.

**Review state is keyed on the dedup key, not a business id.** Business rows are
scoped to a run, so keying a searcher's own notes and decisions to a business id
would discard them whenever the same search was re-run. It therefore has no
foreign key into `business`, deliberately.

**Identity** is resolved by one total function: normalised website domain, then
phone digits, then name plus street, falling back to name with city, then name,
then a digest of the record's own content. Total because the column is
`NOT NULL`. A business is matched against an existing row on any of its three
keys, not only the one that won, so a source supplying just a phone merges with
one that supplied just a domain.

**Postgres was considered and rejected.** It would be the right answer for
multiple concurrent searchers, and it is a one-file change behind the store
module if that day comes. For a demo it would have added a service to run, a
driver to install and a connection string to configure, in exchange for
concurrency this workload does not have.

## Caching and performance

- **Results are the cache.** Every discovered business, signal and contact is
  persisted, so a repeated search refetches nothing and the interface reads from
  disk.
- **One HTTP session per run**, so cookies and connections persist across pages
  of the same site. A fresh request per page discards both and looks like a new
  visitor each time, which is slower and more detectable.
- **Write-ahead logging** lets the worker thread write while a web request
  reads. A busy timeout stops the two colliding.
- **Counts and per-source outcomes are updated in SQL**, not read-modify-write
  in Python, so concurrent progress reports cannot lose an update. Outcomes
  merge through SQLite's own JSON functions.
- **Indexes** on the run, the three dedup keys, and run with score descending,
  which is the ordering the results table actually uses.
- **Enrichment is capped** at three pages per business and rate limited per host.
- **Adaptive selectors.** The YellowPages listing selector is saved on every
  successful parse and relocated by structure and text when the selector stops
  matching. Measured against a real page with the listing class renamed, the
  plain selector matched nothing and the adaptive one recovered seven of
  thirty-seven cards. That is partial recovery, not immunity: it turns a silent
  zero into a degraded run that still returns something and still signals that
  the markup moved. The fingerprint store is a project-local file, so a
  dependency reinstall does not discard what was learned.

The honest performance limit: a run is bounded by politeness, not by compute. A
hundred businesses takes minutes because we wait between requests on purpose.
That is why the run is a background thread and rows stream into the table.

## Concurrency

**A background thread per search run, and no queue.**

One container, one searcher, minute-long jobs. A broker would have added an
operational dependency that buys nothing at this scale, and would not fit a
single small instance. The request that starts a run returns immediately; the
page polls a fragment endpoint and rows appear as they land. Cancellation is a
flag checked between units of work.

If this became multi-tenant, the replacement is a real queue and a separate
worker, and the store layer would not change.

## Hosting

**A Docker web service on Render. Not static, not serverless.**

Serverless was ruled out by the workload, not by preference. A run holds a
browser session and an HTTP session open for minutes and writes continuously;
that is the opposite of a short stateless invocation. Static hosting cannot
scrape at all.

**The memory constraint is real and is designed around.** Headless Chromium
needs roughly half a gigabyte, more than Render's free instance allows. So the
browser tier is behind an environment flag and off in the deployed image. The
HTTP sources work without it, and the committed dataset always renders, so the
deployed demo is functional rather than broken. Raising the instance size and
setting one variable enables the browser tier. This is stated rather than hidden
because a reviewer will find it either way.

**Persistence.** A Render disk needs a paid instance. Without one, the working
database is ephemeral and the committed dataset reseeds on each deploy, which is
the right default for a demo. The blueprint carries the disk configuration
commented out, one edit away.

## Deployment

The repository contains a `Dockerfile` and a `render.yaml` blueprint. Deploying
is connecting the repository as a Blueprint on Render; auto-deploy is off by
default so a push does not surprise anyone.

The image installs dependencies from the lockfile before copying source, so a
code change does not reinstall the world. `/healthz` is the health check.

**Cloud provider: Render.** Chosen over AWS or GCP because the whole deployment
is one container with one health check, and a managed container host does that
in a file instead of a Terraform module. Nothing in the application is
Render-specific: the same image runs on Fly, Railway, Cloud Run or ECS.

## What the model does, and does not

The optional step calls Claude Haiku 4.5 once per business over the text already
fetched, to recover an owner name the rules missed, a founding year, a team-size
estimate, and a one-line outreach angle. Results persist, so a second pass costs
nothing.

**It cannot produce or adjust a score, and it can still move one.** Those are
different claims and the distinction matters. The reply is parsed, unexpected
keys are discarded and wrong-shaped values rejected, so a model that returned a
score or a confidence could not apply either. But a founding year or an owner
name it supplies is read by the rubric like any other fact, and those rules are
worth up to twenty-seven points. So every fact the model contributes is recorded
as model-derived, and the signals built on it say so in the detail panel. The
rule stays what ADR 0002 set out, which is that the arithmetic is ours and
auditable; the honest qualification is that the inputs are only as good as where
they came from, which is why the panel names the source of each one. Absent an
API key the step does nothing and the tool is unchanged. See
[ADR 0002](docs/adr/0002-deterministic-scoring.md).

## Testing

There are no automated tests. That was a deliberate constraint for a time-boxed
build, recorded in [CLAUDE.md](CLAUDE.md). Each step was verified by hand
against a written checklist and the results reported in its commit message,
including live requests against the real sources. Several real bugs were caught
that way: a shared fallback identity that collapsed unrelated businesses into
one row, an empty JSON column that could never be filled, a signal replacement
that only ever added, and robots policies that were never actually parsed
because a session object was stored instead of the object its context manager
returns.

The seam a test suite would use is the store module's public functions, and
above that the HTTP layer.
