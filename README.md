# sourcer

Finds small businesses in a trade and a city, reads each one's own website, and
ranks them by how likely the owner is to sell. Every point of the score names
the fact behind it.

Built for the Caprae Capital AI-readiness pre-work challenge.

## The thesis

SaaSquatch was built by a searcher who was tired of paying a thousand dollars a
month for lead lists. Its own marketing is split between "30+ entrepreneurs and
searchers" and "2,000+ sales teams", and the feature set serves the second
audience: filter by industry, size, location and tech stack, export a flat CSV,
rank nothing. Its navigation names "AI Company Scoring"; nothing sits behind it.

A searcher does not want a list of plumbers. They want the three plumbers most
likely to sell.

`sourcer` is that one feature, built properly: discovery across three sources,
enrichment from each business's own site, and a hundred-point acquisition score
with the evidence shown beside it.

## Quick start

```bash
uv sync
uv run uvicorn sourcer.web:app --port 8000
```

Open http://localhost:8000. A dataset ships with the repository and loads on
first boot, so there is a ranked shortlist on screen immediately, with no
scraping and no browser stack.

To run a live search, pick a trade and a market on the home page. To enable the
browser tier, which some sources need:

```bash
uv run patchright install chromium
SOURCER_BROWSER=1 uv run uvicorn sourcer.web:app --port 8000
```

### Command line

```bash
uv run sourcer init-db      # create or update the database, then report it
uv run sourcer seed         # load the shipped dataset
uv run sourcer build-seed   # run live searches and rewrite the dataset
```

## How the score works

A hundred points across four groups. Weights live in one module as plain data.

| Group | Points | What it reads |
|---|---|---|
| Succession likelihood | 30 | Years trading, a named owner, owner-operator language |
| Digital underinvestment | 25 | No website, stale copyright, consumer site builder, no online booking |
| Acquirability | 25 | Single location, no chain markers, small team, its own domain |
| Demand proof | 20 | Review volume, rating, BBB accreditation, listing completeness |

Two rules matter more than the weights.

**Every point traces to evidence.** Click any row and the panel lists each
signal, the value observed, the points awarded and a link to where it was seen.
A searcher has to defend a shortlist to their investors, and a number nobody can
audit is worth less than a smaller number they can trace.

**Missing data never costs points.** A signal we could not evaluate is recorded
unresolved and excluded from the denominator, so a business scored on half the
rubric is compared fairly against one scored on all of it. Confidence reports
how much of the rubric was evaluable. The least digitally present businesses are
often the best targets, and a rubric that punished thin evidence would bury
them. The default view hides rows below a third of the rubric and says so, with
one click to show everything.

## Sources

| Source | Reachable | Carries |
|---|---|---|
| YellowPages | Intermittently; refusals are not tier-specific | Name, phone, address, website, rating, years trading |
| OpenStreetMap | Always. No key, no anti-bot | Name, phone, website, address |
| Better Business Bureau | Disabled by default, see below | Owner name, date started, rating, accreditation |

**BBB is built and switched off.** Three separate reasons, recorded in
[ADR 0001](docs/adr/0001-robots-constrained-bbb-access.md). Its robots policy
disallows every URL with a query string, which rules out its search endpoint and
the JSON API behind it, so discovery would have to go through category directory
pages and profiles. Its terms of use license content for personal,
non-commercial use and separately forbid compiling a competing dataset, which is
exactly what a lead-sourcing tool does. And it refused every request from the
development network at the edge, with no challenge to solve, so it could not be
demonstrated anyway. The adapter exists because the analysis was worth doing;
the switch is off because the answer was no.

## Collection ethics

- **robots.txt is checked before every fetch.** A disallowed path raises rather
  than proceeding. A robots file we cannot read is not treated as permission,
  and not as refusal either: the site has told us nothing, so we proceed under
  our own rate limit rather than inventing rules.
- **One request at a time per host**, with a delay between, deliberately slower
  than necessary for a single page.
- **No login-walled source.** No LinkedIn, no Apollo, no Crunchbase.
- **Business contact information only.** No personal data beyond the owner's
  name and role where the business itself publishes them.
- **A refusal is recorded, never retried in a loop.** It appears on the run as a
  blocked source, so an empty column reads as a refusal and not as an empty
  market.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the stack, the data model, the
caching and concurrency story, and the deployment.

In short: one Python process. FastAPI routes, Jinja2 templates, HTMX for the
live parts from a CDN, so there is no build step. SQLite through the standard
library. A background thread per search run. One Docker container on Render.

## Repository

| Path | What it is |
|---|---|
| `src/sourcer/schema.sql` | Five tables, the whole data model in one readable file |
| `src/sourcer/identity.py` | Normalisation and the dedup key resolution |
| `src/sourcer/merge.py` | What changes when a second source reports the same business |
| `src/sourcer/store.py` | Every read and write. No other module writes SQL |
| `src/sourcer/fetch.py` | Every outbound request, robots, rate limiting, tiers |
| `src/sourcer/sources/` | One module per source, behind one small interface |
| `src/sourcer/enrich.py` | Reading a business's own site by rule |
| `src/sourcer/scoring.py` | The rubric. Weights as plain data |
| `src/sourcer/runner.py` | Orchestrating a run in the background |
| `src/sourcer/web.py` | Routes, filters, CSV export, JSON API |
| `src/sourcer/llm.py` | Optional model step. Never touches the score |
| `CONTEXT.md` | The domain glossary the code follows |
| `docs/adr/` | Decisions that were hard to reverse |
| `PLAN.md` | The plan this was built from |

## API

```
GET /api/runs/{id}             the run and its ranked businesses, filters apply
GET /api/businesses/{id}       one business with contacts and grouped signals
GET /api/rubric                the scoring rubric and its weights
GET /runs/{id}/export.csv      the filtered view as CSV
GET /healthz
```

Filters work identically on the page, the CSV and the API: `min_score`,
`min_confidence`, `min_years`, `no_website`, `owner_known`, `state`.

## Conventions

This project uses `uv`, adds a package only at the step that first imports it,
and carries no tests and no type hints. Those are deliberate constraints for a
time-boxed build, recorded in [CLAUDE.md](CLAUDE.md). Verification was done by
hand at each step and reported in the commit messages.
