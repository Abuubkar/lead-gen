# sourcer for BritNova

A prospecting tool for BritNova's business development team. It finds
businesses in a trade and a market, reads each one's own website, and ranks
them by how well they fit what BritNova sells. Each point of a score names the
fact behind it, and each business says whether a rep may email it unprompted.

It covers the United Kingdom, Pakistan and the United States.

![A ranked list of HVAC businesses in Phoenix, each with its score broken into
three groups and a badge saying whether it may be emailed](docs/media/shortlist.png)

## Two modes

BritNova's case studies on [britnova.net/work](https://britnova.net/work) show
two kinds of client, and the tool has a mode for each. The trade a rep picks
decides the mode.

| Mode | Looks for | Example trades | BritNova case studies |
|---|---|---|---|
| Web & e-commerce | Local businesses that need a website, or a better one | Solicitors, restaurants, dental practices, salons | HI Legal (Newport solicitors), Wear To Fit (Lahore clothing) |
| AI, cloud & software | Companies that need engineers | Software companies, IT consultancies, data and hosting | PsychPlus, Meet Gabbi, Landit, the monolith migration |

## Quick start

```bash
uv sync
uv run uvicorn sourcer.main:app --port 8000
```

Open http://localhost:8000. A dataset ships with the repository and loads on
first boot, so there are scored results to look at before any search has run.

To search, pick a trade and a market. Results stream into the table and each
business is scored as soon as its website has been read. A search takes
minutes, because requests are spaced out on purpose and public Overpass servers
are slow.

To include Companies House, register for a free key at the
[Companies House developer hub](https://developer.company-information.service.gov.uk/)
and set it before starting:

```bash
COMPANIES_HOUSE_API_KEY=your-key uv run uvicorn sourcer.main:app --port 8000
```

### Command line

```bash
uv run sourcer init-db      # create or upgrade the database, then report it
uv run sourcer seed         # load the shipped dataset
uv run sourcer build-seed   # run live searches and rewrite the dataset
uv run sourcer export-seed  # write the database's finished runs as the dataset
uv run sourcer rescore      # score finished runs again under the current rubric
```

`rescore` re-reads each site with the current reader. Add `--no-refetch` to
rescore from stored data only; it is faster, but facts read from a site and
never stored, such as the copyright year, come back unresolved.

## Sources

Each source declares the countries it covers and only runs there.

| Source | Countries | Licence | Gives | Does not give |
|---|---|---|---|---|
| [Companies House](https://developer.company-information.service.gov.uk/) | UK | Open Government Licence v3.0 | SIC codes, company type, incorporation date, registered office | Phone, website, email |
| [Care Quality Commission](https://www.cqc.org.uk/about-us/transparency/using-cqc-data) care directory | England | Open Government Licence v3.0 | Every dentist and GP practice: name, address, phone, and the website where the practice gave one | Company type, age, email |
| [Food Standards Agency](https://api.ratings.food.gov.uk/help) | UK | Open Government Licence v3.0 | Every inspected food business: name, type, address, postcode | Phone, website, email |
| [NPI Registry](https://npiregistry.cms.hhs.gov/api-page) | US | Federal data disclosable under FOIA; no stated conditions | Every dental practice and clinic billing a health plan: name, practice address, phone, the official who acts for it | Website, age |
| [Seattle business licences](https://cos-data.seattle.gov/d/wnbq-64tb) | Seattle | Public Domain | Licensed businesses by NAICS code: name, address, phone, licence start date | Website |
| [Texas sales tax permits](https://data.texas.gov/d/jrea-zgmq) | Six Texas markets | Public Domain | Outlets that collect sales tax, by NAICS code: name, address, date of first sale | Phone, website; trades that do not collect sales tax |
| [New Orleans occupational licences](https://data.nola.gov/d/iqay-p646) | New Orleans | CC0 | Licensed businesses by type: name, address, phone, owner, start date | Website |
| [PSEB Tech Hub](https://techdestination.com/tech-hub-portal/) | Pakistan | No terms published; robots.txt disallows nothing | IT companies registered with PSEB: name, town, staff, years trading, areas of work, website | Phone, email |
| [Yellow Pages Pakistan](https://yellowpagespk.com/) | Pakistan | robots.txt disallows only admin pages; the disclaimer sets no conditions | About 2,200 self-written listings by category and city, with a phone or website where the text gives one | Age; quality varies |
| [Overture Maps](https://docs.overturemaps.org/guides/places/) places | UK, PK, US | CDLA Permissive 2.0, Apache 2.0 (Foursquare) or CC0, per record | About 72 million places merged from Meta, Microsoft, Foursquare and others: name, address, category, and a website and phone for most | Company type, age |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) (Overpass) | UK, PK, US | Open Database Licence | Name, address, often a website and phone | Company type, age, reviews |
| YellowPages | US | Robots permits the paths used | Name, phone, address, website, reviews | — |

Some facts behind those columns, measured while building this:

- The Food Standards Agency API has a phone field, but it was empty for all 500
  Norwich businesses sampled. A business found only there has no contact
  details until another source or its own website supplies them.
- Companies House returns the registered office, which is often an
  accountant's rather than where the business trades. It runs last, so a
  trading address from another source is kept.
- OpenStreetMap is searched by distance from each market's coordinates, not by
  the name of an administrative boundary. Pakistani boundaries are named in
  Urdu, so a name search for Lahore returned nothing; by distance it returns
  businesses with English names where they are tagged.
- Overture Maps is the Source that reliably returns businesses. In Norwich it
  lists 54 solicitors (51 with a website) where OpenStreetMap lists 16, and 182
  software companies in Lahore. It is published as files on Amazon S3 rather
  than behind a server, so it does not go down the way public Overpass servers
  do. The first search in a market downloads every place around it, which took
  between 11 seconds and two minutes in testing and about 300 MB of memory; the
  places are kept on disk, so later searches there read from it. Places Overture
  rates below 0.5 for still existing are left out.
- Pakistan's company registry, run by SECP, can look up a company you already
  know but cannot list companies by trade or place, so Pakistan relies on PSEB,
  one small directory and OpenStreetMap.
- PSEB's Tech Hub returns only the first page of results for a place, about
  twenty companies; its "load more" call drops the place filter. So a city is
  searched by name and by each of its administrative towns, as Wikipedia lists
  them. A town name used in more than one city, such as Iqbal Town, is skipped.
- The CQC directory is about 18 MB and renamed each week. It is downloaded at
  most once a week and kept in the data directory. The CQC API now needs a
  subscription key; the file does not.
- The US registers record when a licence or permit started, which is the latest
  a business can have begun trading. It is used as the founding year, so it can
  make a business look younger than it is, never older.
- NAICS codes come in two editions here: Seattle files under 2022 and Texas
  under 2017, which renumbered clothing stores and software publishers. Each
  trade lists its code from both, checked against Seattle's own descriptions and
  the Census Bureau's 2017 code file.

### Sources left out

| Source | Why |
|---|---|
| Yell | Its terms forbid using the site to build "customer lists or mailing lists", and Cloudflare blocks automated access, including to its robots.txt. |
| FreeIndex | Its [terms](https://www.freeindex.co.uk/terms.htm) state that using its data "as a source or target for direct marketing ... is strictly prohibited". |
| Thomson Local | Blocks automated access before robots.txt can be read. |
| Solicitors Regulation Authority API | Free and rich (phone, email, website for every firm), but its [terms](https://www.sra.org.uk/sra/how-we-work/privacy-data-information/data-sharing/terms-conditions/) forbid using the data "to transmit, or procure the sending of, any unsolicited or unauthorised advertising or promotional material". |
| FindPK | Its terms say "You may not scrape, copy or republish the directories in bulk". |
| BusinessList.pk | Its terms forbid access "through any automated means (including, without limitation, through the use of scripts or webcrawlers)". |
| "Yellow Pages of Pakistan" on opendata.com.pk | Labelled public domain, but it is a 2020 copy of FindPK made by an individual, who could not relicense FindPK's data. |
| TDLR licence list (Texas) | Lists electricians and air-conditioning contractors with phones, but the dataset states no licence. |
| Google Places API | Its terms allow caching only latitude and longitude, for 30 days, and its shared terms forbid "caching and exporting Google Maps Content and creating content from Google Maps Content". This tool stores every business and exports CSV. |
| HERE Geocoding and Search | HERE's own guidance caps storing results at 30 days without a paid add-on. |
| Geoapify Places | Its terms allow its free plan in production only "with some limitations", and its places are OpenStreetMap's, which the tool already reads. |
| Foursquare Open Source Places | Already inside Overture Maps, which merges it with other providers. |
| Better Business Bureau | Never returned a business: every request was refused at Cloudflare's edge, from a development network and from Render. Its terms also limit use to personal, non-commercial purposes. The adapter is kept in `bbb.py` and is not registered. See [ADR 0001](docs/adr/0001-robots-constrained-bbb-access.md). |

## How the score works

Each mode has its own rubric of a hundred points. A rule that could not be
evaluated is recorded as unresolved: it costs Confidence, not points.

**Web & e-commerce**

| Group | Points | Reads |
|---|---|---|
| Website need | 45 | No website, stale copyright, a consumer site builder or no HTTPS, no online booking |
| Established | 30 | Years trading, review count, a complete listing |
| Reachable | 25 | A phone number, an email on the site |

**AI, cloud & software**

| Group | Points | Reads |
|---|---|---|
| Technical fit | 55 | A software or IT SIC code, technology shared with BritNova's stack, AI or machine-learning work |
| Engineering investment | 20 | A careers page |
| Reachable | 25 | A phone number, an email on the site |

Three rules shape the numbers more than the weights do.

**Absence only counts when the source would have said so.** "No website" is the
largest award in the web rubric. Neither the Food Standards Agency nor
Companies House has a website field, and OpenStreetMap carried one for one in
fifty-seven of the businesses it alone found in a sample, so none of the three
can tell us a business has no site. A business found only through them shows
*website unknown*, not *no website*.

**A business needs evidence in its core group to be scored.** The core group is
Website need for web and Technical fit for tech. Without it, a business is left
unscored and its Confidence is still shown. Scoring on reachability alone had
ranked a restaurant we knew nothing else about as a perfect prospect.

**HTTPS is judged from the page a visitor reaches.** Directories often list
`http://` for a site that redirects to `https://`. Judging the listed address
marked six of eight sampled "no HTTPS" sites as insecure when they were not.

The full rubrics, weights included, are at `/api/rubric`.

![The drawer for one business: its facts, the rule for contacting it, and each
signal with the points it earned and where the fact came from](docs/media/evidence.png)

### Recognising a technology stack

The tech rubric reads a site's frameworks and hosting. Each fingerprint was
checked against a real site built on it:

| Recognised | From | Checked on |
|---|---|---|
| Next.js | `/_next/static/` in the page | nextjs.org, react.dev |
| Angular | `ng-version=`, `_ngcontent-` | angular.dev |
| Vue | `data-v-` with a hash | vuejs.org |
| Django | `csrfmiddlewaretoken` | djangoproject.com's login form |
| Shopify | `cdn.shopify.com` | a live Shopify store |
| Vercel, Netlify | the `server` header | nextjs.org; vuejs.org and britnova.net |
| Cloudflare | `server`, `cf-ray` | cloudflare.com |
| AWS | CloudFront in `via`, `x-amz-cf-pop` | aws.amazon.com |

React on its own cannot be recognised from served HTML: the usual markers are
set by the browser at runtime and matched nothing, even on react.dev. It is
recorded when a site uses Next.js or names `react-dom`. Django shows only on a
page with a form, so a Django site is often missed.

## Contact rules

Each business carries the rule for contacting it, shown on the row and in
detail in its drawer. It is reported beside the Score and never changes it: a
sole trader is not a worse prospect, only one a rep reaches differently.

| Country | Email | Phone |
|---|---|---|
| UK | A limited company, LLP, plc or Scottish partnership may be emailed without prior consent, if you say who you are and give an opt-out. A sole trader, a partnership or a business not found on Companies House needs consent first. | Screen the number against TPS and CTPS before calling. |
| US | May be emailed without prior consent. Each email needs accurate headers, an honest subject line, a physical postal address, a statement that it is an advertisement, and an opt-out honoured within ten business days. | Not covered. |
| Pakistan | No law in force requires consent. PECA 2016 section 25 makes spamming an offence where it is for wrongful gain. Include a way to unsubscribe. | Not covered. |

Sources: [ICO, business-to-business marketing](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/business-to-business-marketing/);
[FTC, CAN-SPAM compliance guide](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business);
[DLA Piper, electronic marketing in Pakistan](https://www.dlapiperdataprotection.com/index.html?t=electronic-marketing&c=PK).

![Norwich restaurants from the Food Standards Agency, each marked consent first
and website unknown](docs/media/uk-restaurants.png)

That run is the Food Standards Agency on its own. It lists every restaurant but
records no website, so none can be ranked on website need until OpenStreetMap
supplies their sites; each still says how it may be contacted.

This is guidance drawn from those published rules, not legal advice. Where a
UK business's company type is unusual or unknown, the tool follows the ICO's
instruction to treat it as an individual.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `COMPANIES_HOUSE_API_KEY` | unset | Enables Companies House. Without it the source reports "not configured". |
| `SOURCER_OVERPASS_URL` | Private.coffee, then VK Maps | Overpass servers to try in order, comma-separated. |
| `SOURCER_PROXIES` | unset | Comma-separated proxies, rotated when there is more than one. |
| `SOURCER_BROWSER` | off | Allows the headless-browser tier. Needs around a gigabyte of memory. |

The [OpenStreetMap wiki](https://wiki.openstreetmap.org/wiki/Overpass_API)
lists two public Overpass servers that any project may use, Private.coffee and
VK Maps, and the tool tries them in that order, asking each twice. Both fail at
times: Private.coffee answered most searches with a 500 error on the day the
tool was first opened to the team. The main server at overpass-api.de is left
out, because it asks commercial users to use a self-hosted or paid server. A
team running searches every day should point `SOURCER_OVERPASS_URL` at a paid
instance; the wiki lists several.

## Collection ethics

- **robots.txt is checked before every page fetch**, and a disallowed path
  raises rather than proceeding. The APIs used (Companies House, the Food
  Standards Agency and Overpass) are public endpoints rather than crawlable
  sites; each exemption is named in the code where it is taken.
- **One request at a time per host**, with a delay between.
- **Terms are read, not just robots.txt.** Robots.txt allows FreeIndex's
  listing pages; its terms forbid this use, so it is not a source.
- **No login-walled source.** No LinkedIn, Apollo or Crunchbase.
- **Company facts, not people.** Companies House is used for company records,
  not for the names of directors.
- **A refusal is recorded, never retried in a loop.** A source that refuses
  shows as blocked, one that never answered shows as unreachable, and one with
  no key shows as not configured, so an empty column is never mistaken for an
  empty market.

## Known limits

- **At most three searches run at once.** Others wait their turn, first come
  first served, and the page shows how many are ahead. Each search holds
  connections and pages in memory, and a free instance that runs out of its
  512 MB restarts, losing every search in progress.
- **Companies House needs a key a person registers for.** Its requests were
  checked against the live API with a deliberately invalid key, which it
  rejected as unauthorised, so the request is well formed; parsing of real
  results has not been checked without a key.
- **A UK business's email rule depends on a Companies House match.** Without a
  key, or for a business registered under a different name or address, UK
  businesses fall back to "consent first".
- **Pakistan is thin outside tech.** PSEB covers IT companies well; for local
  trades there is only OpenStreetMap and a small self-listed directory.
- **The US registers cover four of fifty-six US markets**: Seattle, New Orleans
  and, for trades that collect sales tax, the six Texas cities. Elsewhere in the
  US the sources are YellowPages, the NPI Registry and OpenStreetMap.
- **Public Overpass servers are slow and sometimes unreachable.** A query has
  taken over three minutes.
- **The careers check is approximate.** A link to an industry job board can
  count as a careers page; the drawer shows the evidence.

## Repository

| Path | What it is |
|---|---|
| `main.py` | ASGI entry point. Builds the app, applies the schema, loads the seed |
| `config.py` | Paths, environment flags, shared constants |
| `api/routes.py` | HTTP handlers for the pages and the JSON endpoints |
| `api/filters.py` | The query filters, shared by page, CSV and API |
| `api/export.py` | CSV generation |
| `api/templates/`, `api/static/` | Jinja templates and the single stylesheet |
| `db/schema.sql` | The data model in one readable file |
| `db/database.py` | Connection settings, transactions, schema and column upgrades |
| `db/repository.py` | Every read and write. No other module writes SQL |
| `db/seed.py` | Capturing and loading the shipped dataset |
| `scrapers/client.py` | Every outbound request: robots, rate limiting, both tiers |
| `scrapers/registry.py` | Which sources exist, which countries each covers |
| `scrapers/catalog.py` | Trades by mode, markets by country, per-source keys |
| `scrapers/companies_house.py`, `cqc.py`, `fsa.py`, `npi.py`, `overpass.py`, `overture.py`, `techhub.py`, `us_registers.py`, `yellowpages.py`, `yellowpagespk.py` | One module per source |
| `extractors/website.py` | Reading a business's own site by rule |
| `pipelines/dedup.py` | Normalisation and identity resolution |
| `pipelines/merge.py` | What changes when a second source reports the same business |
| `pipelines/scoring.py` | Both rubrics. Weights as plain data |
| `pipelines/compliance.py` | The contact rules per country |
| `services/llm.py` | Optional model step. Cannot produce a score |
| `workers/runner.py` | Running a search, and rescoring a finished one |
| `CONTEXT.md` | The domain glossary the code follows |
| `docs/adr/` | Decisions that were hard to reverse |

## API

```
GET /api/runs/{id}             the run and its ranked businesses, filters apply
GET /api/businesses/{id}       one business with contacts and grouped signals
GET /api/rubric                both rubrics and their weights
GET /runs/{id}/export.csv      the filtered view as CSV
GET /healthz
```

## Attribution

Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright),
available under the Open Database Licence. Contains public sector information
licensed under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/),
including Care Quality Commission information. Places from the
[Overture Maps Foundation](https://overturemaps.org), under CDLA Permissive 2.0,
Apache 2.0 and CC0; Foursquare data copyright 2024 Foursquare Labs, Inc., under
Apache 2.0. The Seattle and Texas registers
are in the public domain and the New Orleans register is under CC0; they are
credited here as a courtesy.

## Conventions

This project uses `uv`, adds a package only at the step that first imports it,
and carries no tests and no type hints, as recorded in [CLAUDE.md](CLAUDE.md).
Verification is done by hand and reported in the commit messages.
