# sourcer

Finds small businesses in a trade and a city, reads each one's own website, and
ranks them by how likely the owner is to sell. Every point of the score names
the fact behind it.

Built for the Caprae Capital AI-readiness pre-work challenge.

![The ranked shortlist: 31 HVAC businesses in Phoenix, scored out of 100, with
the four score groups broken out beside each one](docs/media/shortlist.png)

A silent screen recording of the same flow, end to end, is at
[`docs/media/walkthrough.webm`](docs/media/walkthrough.webm) (1:42). The
narration it is scripted against is in [VIDEO.md](./VIDEO.md).

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
uv run uvicorn sourcer.main:app --port 8000
```

Open http://localhost:8000. A dataset ships with the repository and loads on
first boot, so there is a ranked shortlist on screen immediately, with no
scraping and no browser stack.

![The search form, with the rubric's four groups and their weights in the
rail](docs/media/home.png)

To run a live search, pick a trade and a market on the home page. To enable the
browser tier, which some sources need, and which wants around a gigabyte of
memory:

```bash
uv run patchright install chromium
SOURCER_BROWSER=1 uv run uvicorn sourcer.main:app --port 8000
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

The plan also wanted a BBB letter grade to count towards demand proof. Only the
accreditation flag is read, because the grade is only available from the source
that ships disabled. That gap is a signal that resolves rarely rather than one
that is missing.

Two rules matter more than the weights.

**Every point traces to evidence.** Click any row and a drawer lists each
signal, the value observed, the points awarded, and where the fact came from.
Provenance is derived from which fields the rule actually read, so a signal built
on a directory listing cites the listing and one built on the business's own site
links to the page. A fact supplied by the optional model is labelled as such,
because a guess is weaker evidence than a page we read. A searcher has to defend
a shortlist to their investors, and a number nobody can audit is worth less than
a smaller number they can trace.

![The evidence drawer for one business: every signal with its points, the value
observed, and the source the fact came from](docs/media/evidence.png)

**Missing data never costs points.** A signal we could not evaluate is recorded
unresolved and excluded from the denominator, so a business scored on half the
rubric is compared fairly against one scored on all of it. Confidence reports
how much of the rubric was evaluable. The least digitally present businesses are
often the best targets, and a rubric that punished thin evidence would bury
them. The default view hides rows below a third of the rubric and says so, with
one click to show everything.

## Sources

| Source | Reachable from a home address | Carries |
|---|---|---|
| YellowPages | Intermittently; refusals are not tier-specific | Name, phone, address, website, rating, years trading |
| OpenStreetMap | Yes. No key, no anti-bot | Name, phone, website, address |
| Better Business Bureau | Disabled by default, see below | Owner name, date started, rating, accreditation |

**From a datacenter address, none of them.** Measured against the deployed
service on Render, every Source refuses, each in its own way: YellowPages
answers with Cloudflare's "Attention required!", an address-level block rather
than a challenge; BBB answers with Cloudflare's "Just a moment..." interstitial,
which is a challenge but needs the browser tier that the instance has too little
memory to run; and OpenStreetMap's Overpass endpoint refuses the TCP connection
outright in about thirty milliseconds, while answering from a home address at
the same moment. Outbound HTTPS from the instance is fine, which the first two
prove by returning real pages.

This is the ordinary condition of a scraper on shared hosting, and it is why the
dataset ships in the repository. The deployed demo serves that dataset in full
and cannot run a live search. Live discovery needs a residential or proxied
address, which `SOURCER_PROXIES` accepts.

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

- **robots.txt is checked before every page fetch**, and reading the policy
  itself waits its turn in the same per-host queue. A disallowed path raises
  rather than proceeding. The one exception is the OpenStreetMap Overpass
  endpoint, which is a public API rather than a crawlable site, and is called
  once per run; the exemption is named in the code where it is taken. A robots
  file we cannot read is not treated as permission, and not as refusal either:
  the site has told us nothing, so we proceed under our own rate limit rather
  than inventing rules.
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
| `main.py` | ASGI entry point. Builds the app, applies the schema, loads the seed |
| `config.py` | Paths, environment flags, shared constants |
| `api/routes.py` | HTTP handlers for the pages and the JSON endpoints |
| `api/filters.py` | The query filters, shared by page, CSV and API |
| `api/export.py` | CSV generation |
| `api/templates/`, `api/static/` | Jinja templates and the single stylesheet |
| `db/schema.sql` | Five tables, the whole data model in one readable file |
| `db/database.py` | Connection settings, transactions, schema application |
| `db/repository.py` | Every read and write. No other module writes SQL |
| `db/seed.py` | Capturing and loading the shipped dataset |
| `scrapers/client.py` | Every outbound request: robots, rate limiting, both tiers |
| `scrapers/registry.py` | Which scrapers exist and which run by default |
| `scrapers/catalog.py` | Trade to per-site keys |
| `scrapers/yellowpages.py`, `overpass.py`, `bbb.py` | One module per site |
| `extractors/website.py` | Reading a business's own site by rule |
| `pipelines/dedup.py` | Normalisation and identity resolution |
| `pipelines/merge.py` | What changes when a second source reports the same business |
| `pipelines/scoring.py` | The rubric. Weights as plain data |
| `services/llm.py` | Optional model step. Cannot produce a score |
| `workers/runner.py` | Orchestrating a run in the background |
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
