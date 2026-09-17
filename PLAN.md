# sourcer — build plan

## 1. Thesis

SaaSquatch was built by a searcher who was tired of paying a thousand dollars a month for lead
lists. Its own marketing is split between "30+ entrepreneurs and searchers" and "2,000+ sales
teams", and its feature set serves the second audience. It filters on industry, size, location
and tech stack, exports a flat CSV, and ranks nothing.

A Searcher does not want a list of plumbers. They want the three plumbers most likely to sell.

`sourcer` discovers Businesses in a trade and a city, enriches each from its own website, and
scores it against an acquisition thesis where every point is traceable to an observed Signal.
It is the feature SaaSquatch names in its navigation as "AI Company Scoring" and does not ship.

**The one-line pitch for the video**: same raw leads, ranked by who is most likely to sell, with
the reasoning shown.

## 2. Scope

**In scope**
- Discovery across three Sources behind one adapter seam
- Enrichment from each Business's own website
- A hundred-point Score with per-Signal evidence and a Confidence figure
- A ranked, filterable table with a detail panel, CSV export and a Review State
- A JSON endpoint, a Dockerfile, a Render deployment and a seeded database in the repo

**Explicitly out of scope**
- Any login-walled source. No LinkedIn, no Apollo, no Crunchbase.
- Email sending, outreach sequencing, CRM sync
- Multi-user accounts or auth
- The business-understanding essays and the video recording itself

## 3. Ground rules

- `uv` manages the environment and the lockfile. Nothing is installed globally.
- A package is added at the step that first imports it, never before. Each step below names its
  exact `uv add`. Most steps add nothing.
- No test files and no test framework.
- No type hints anywhere.
- `ruff` is the only development dependency.
- Every step ends with something runnable.

## 4. Architecture

Single Python process. FastAPI serves both the HTML and the JSON. Jinja2 renders server-side.
HTMX drives the interactions, loaded from a CDN, so there is no build step, no bundler and no
JavaScript toolchain. SQLite through the standard library is the only datastore.

```
  browser (HTMX)
        │
   FastAPI ── Jinja2 templates
        │
   ┌────┴─────────────────────────┐
   │ run manager (background      │
   │ thread per Search Run)       │
   └────┬─────────────────────────┘
        │
   ┌────┴────┐   ┌──────────┐   ┌─────────┐
   │discovery│──▶│enrichment│──▶│ scoring │
   └────┬────┘   └────┬─────┘   └────┬────┘
        │             │              │
   source adapters    │              │
   (overpass,         │              │
    yellowpages,      │              │
    bbb)              │              │
        └─────────────┴──────────────┘
                      │
                  SQLite
```

A Search Run is started by an HTTP POST, which spawns a thread and returns immediately. The
thread writes Businesses to SQLite as it resolves them. The page polls a fragment endpoint with
HTMX and rows appear as they land. No queue, no worker process, no broker.

**Why not a queue**: one container, one user, minutes-long jobs. A broker would add an operational
dependency that buys nothing at this scale and would not fit a single Render instance.

## 5. Data model

Five tables, created from a plain SQL schema file at startup if absent.

| Table | Holds |
|---|---|
| `search_run` | trade, city, state, started, finished, status, counts, per-source outcome |
| `business` | identity and firmographics, dedup keys, score, confidence, run reference |
| `contact` | name, role, email, phone, source, confidence, business reference |
| `signal` | name, group, raw value, points awarded, source URL, observed time |
| `review` | Review State and notes per business, set by the Searcher |

Signals are rows, not columns. That is what makes the Score auditable and lets a new Signal ship
without a migration.

**Dedup identity**, applied in order: normalised website domain, then normalised phone digits,
then normalised name plus street. First match wins and the record is merged, not duplicated.
Merging keeps the highest-confidence value per field and records both Sources.

## 6. Sources

Verified by probe on 2026-09-17. Each adapter exposes one function taking a trade and a place and
returning Business records, plus a declared preferred fetch tier.

| Source | Reachable from dev network | Preferred tier | Fields it carries |
|---|---|---|---|
| Overpass (OpenStreetMap) | Yes, no anti-bot, no key | HTTP | name, phone, website, address, hours |
| YellowPages | Yes, browser only | Browser | name, phone, address, website, years in business, rating, review count |
| BBB | No, blocked at the edge | HTTP | name, address, phone, owner name, date started, rating, accreditation |

**Overpass** is the floor. It never blocks and it never needs a browser, so the deployed demo can
always return something. Coverage is strong for storefront trades and thin for home services.

**YellowPages** is the primary. Its category path returns thirty organic listings per page and
paginates cleanly through one persistent headless browser session with a referer chain. Its
plain-HTTP path gets blocked after roughly ten requests from one address, which is why the
adapter declares the browser tier.

**BBB** is the richest and the most constrained. Its robots policy disallows query strings, so
discovery goes through the category directory path and never the search endpoint. Its terms of
use license content for personal, non-commercial use and forbid compiling a competing dataset.
The adapter is built, defaulted off, and documented as evaluated and declined. See ADR 0001.

## 7. Fetching and politeness

One module owns all outbound requests. Every fetch passes through it.

- **Tier one, HTTP.** A persistent session with Chrome TLS impersonation. Cookies and connections
  persist across a Search Run, and the referer chains from the previous page. The library's
  default of attaching a Google referer to every request is overridden after the entry page,
  because a real visitor reaches page two from page one.
- **Tier two, browser.** One persistent headless session per Search Run. Escalated to only when a
  block is detected, and only when enabled by environment flag.
- **Block detection**: status 403, 429 or 503, or a response title matching known block pages.
  A detected block ends that Source for the run and records the outcome rather than retrying.
- **Politeness**: robots checked before every fetch using the robots parser the scraping library
  already depends on, one request at a time per domain, a delay between requests, a capped page
  count per Search Run, and results cached in SQLite so a repeated search refetches nothing.
- **Proxy support**: a proxy list supplied by environment variable enables rotation. Absent by
  default.

## 8. Enrichment

For each discovered Business with a website: fetch the homepage, then up to two internal pages
whose href matches about, contact, team or our-story. Three pages maximum, robots checked, HTTP
tier only.

Extracted by rule from the combined text:
- emails and phone numbers
- founding year, from "since", "established", "serving since" and "family owned since" patterns
- owner and principal names, from role words near a person's name
- family-owned, locally-owned and veteran-owned wording
- retirement and business-for-sale wording
- copyright year, HTTPS availability, and the site builder from generator markup
- social profile links
- franchise, chain and multi-location markers

## 9. Scoring

A hundred points across four groups. A Business is scored only over the Signals that resolved,
normalised to a hundred, and Confidence reports what share of the available points were
resolvable. Missing data never costs points.

**Succession likelihood, 30**

| Signal | Points |
|---|---|
| Years in business, 25 or more | 14 |
| Years in business, 15 to 24 | 9 |
| Years in business, 8 to 14 | 4 |
| A named owner or principal was found | 11 |
| Family-owned or locally-owned language | 5 |

**Digital underinvestment, 25**

| Signal | Points |
|---|---|
| No website at all | 12 |
| Copyright year three or more years stale | 7 |
| No HTTPS, or a consumer site builder | 4 |
| No online booking or quote form | 2 |

**Acquirability, 25**

| Signal | Points |
|---|---|
| Single location | 10 |
| No franchise, chain or roll-up markers | 8 |
| Small employee count indicated | 4 |
| Local area code matching the searched city | 3 |

**Demand proof, 20**

| Signal | Points |
|---|---|
| Twenty or more reviews | 8 |
| Five to nineteen reviews | 5 |
| Rating of four or better | 6 |
| BBB accredited, or rated A minus or better | 4 |
| Listing carries phone, address and categories | 2 |

Weights live in one module as plain data so they can be tuned without touching logic. Adjustable
weights in the interface are a stretch goal, not a commitment.

## 10. Interface

Four screens, all server-rendered.

- **Start a run.** Trade dropdown from the curated catalogue, city and state, source toggles.
- **Results.** A ranked table: score with a coloured band, confidence, name, location, years in
  business, owner, website presence, phone. Sort and filter without a page reload. A progress
  strip while the run is live, showing what each Source is doing.
- **Detail panel.** Opens beside the table. Lists every Signal, its observed value, its points and
  a link to where it was seen. Contacts, notes, and the Review State control.
- **Export.** CSV of the current filtered view, not the whole table.

Design: one accent colour, a neutral grey scale, a single typeface at three sizes, generous row
spacing, score bands carrying both colour and a number so the table is readable without relying
on colour alone.

**Trade catalogue**: roughly a dozen trades a searcher actually buys, each carrying its
YellowPages slug, its Overpass tags and its BBB category. Plumbing, HVAC, electrical, roofing,
landscaping, auto repair, pest control, commercial cleaning, dental, veterinary, accounting,
machine shops.

## 11. Deployment

Docker container on Render. The seeded SQLite file ships in the repository and is copied to a
writable path at boot, so the interface works the moment the service starts and a redeploy
reseeds.

The free instance caps memory below what headless Chromium needs, so the browser tier is disabled
there by environment flag. Overpass and BBB need only the HTTP tier, so the deployed demo remains
functional and the BBB reachability test can run from Render's address. If the browser tier is
wanted in the cloud, the instance moves up a tier and the flag flips. This constraint is stated
in the README rather than hidden.

## 12. Build steps

Each step is runnable on its own. The five-hour line falls after step 10.

| # | Step | Adds | Time |
|---|---|---|---|
| 1 | Project skeleton, `uv init`, ruff config, gitignore, schema file | `--dev ruff` | 10m |
| 2 | Database layer: connection, schema creation, insert and query helpers | none | 20m |
| 3 | Fetch module and the Source seam. Overpass adapter end to end. | `scrapling[fetchers]` | 35m |
| 4 | YellowPages adapter: category paths, pagination, organic-vs-paid filtering, browser tier | none | 40m |
| 5 | Enrichment crawler: robots gate, page selection, rule-based extraction | none | 45m |
| 6 | Scoring engine: signal definitions, weights, normalisation, confidence | none | 30m |
| 7 | Dedup and merge across sources | none | 20m |
| 8 | Run manager: background thread, progress state, cancellation | none | 20m |
| 9 | Interface: FastAPI app, templates, results table, live progress, detail panel | `fastapi uvicorn jinja2 python-multipart` | 60m |
| 10 | CSV export, Review State, JSON endpoint | none | 25m |
| — | **five-hour line** | | **5h05m** |
| 11 | Seed the shipped dataset across three cities and three trades | none | 20m |
| 12 | BBB adapter, defaulted off, with the reachability check | none | 30m |
| 13 | Optional language-model enrichment behind an API key | `anthropic` | 20m |
| 14 | Dockerfile, Render config, README, architecture write-up, video outline | none | 40m |

Steps 11 through 14 are the polish that wins the documentation and creativity points. Step 13 is
the first to cut if time runs short, and nothing depends on it.

**The language model step**, when a key is present: one call per Business over the crawled text,
using Claude Haiku 4.5, extracting an owner name the rules missed, an employee-count estimate,
and a one-sentence outreach angle. Results cached in the database so reruns cost nothing. It
never touches the Score. See ADR 0002.

## 13. Adaptive selectors

The scraping library can relocate an element after a site redesign by matching on structure and
text rather than a fixed path. The YellowPages adapter saves its selectors on first success and
relocates on later runs, with its fingerprint store pointed at a project path rather than the
library's install directory. This is the honest answer to the rubric's demand for adapting to
changing websites, and it is demonstrable: change a class name in a saved page and watch the
selector still resolve.

## 14. Risks

| Risk | Mitigation |
|---|---|
| YellowPages blocks the browser tier too | Overpass fallback always returns rows; block is recorded per source, not fatal |
| Render free instance cannot run the browser | Browser tier flagged off; HTTP sources still work; seeded data always renders |
| BBB unreachable from Render as well | Adapter is off by default and documented as declined; nothing depends on it |
| Enrichment is slow on large runs | Page cap per business, results stream to the table, cache prevents refetching |
| Five hours runs out | Cut line drawn after step 10; steps 11 to 14 are additive |

## 15. Open items

- Confirm at deployment whether Render's address reaches BBB. This is a test, not a blocker.
- Decide whether to enable the BBB adapter at all, given its terms of use. Default is off.
