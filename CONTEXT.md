# Lead Sourcing

A sourcing tool for search-fund principals: it finds small businesses in a market, enriches them with public signals, and ranks them as acquisition targets.

## People

**Searcher**:
The user of the tool: a search-fund principal or analyst looking for a small business to acquire.
_Avoid_: user, sales rep, SDR

**Contact**:
A named person reachable at a Business, usually the owner. A Business has zero or more Contacts.
_Avoid_: lead, person, decision-maker

## The target

**Business**:
A single company that could be an acquisition target. The unit of work; every other record hangs off it.
_Avoid_: lead, company, prospect, account

**Succession**:
The likelihood that a Business needs a new owner soon, inferred from its age and from whether one named owner still runs it.
_Avoid_: retirement, exit

**Underinvestment**:
Visible neglect of a Business's online presence, read as room for a new operator to grow it rather than as a defect.
_Avoid_: bad website, low quality

## Sourcing

**Source**:
One place Businesses are discovered, with its own coverage, fields and access rules. Each Source is reachable or not independently of the others.
_Avoid_: site, provider, scraper

**Discovery**:
Finding which Businesses exist in a market. Distinct from Enrichment, and usually from a different place.
_Avoid_: search, scraping

**Enrichment**:
Reading a Business's own website to learn what a Source does not carry.
_Avoid_: scraping, crawling

**Search Run**:
One Searcher request for a trade in a city, and everything discovered under it. Results persist after it ends.
_Avoid_: job, query, session

**Run Status**:
Where a Search Run is in its lifecycle: pending, running, done, failed or cancelled.
_Avoid_: state, stage, phase

**Progress Note**:
The single human-readable line shown while a Search Run is still working.
_Avoid_: stage, step, message

## Judgement

**Signal**:
One observed fact about a Business that moves its Score, carrying its own value, contribution, and where it came from.
_Avoid_: feature, attribute, field

**Score**:
How well a Business fits an acquisition thesis, computed only from resolved Signals.
_Avoid_: rating, rank, grade

**Confidence**:
How much of the Score rests on Signals we actually resolved. Reported beside the Score, never folded into it.
_Avoid_: accuracy, certainty

**Reputation**:
The public rating and review count a Source reports for a Business. Feeds the demand-proof Signals; it is not itself the Score.
_Avoid_: rating, score, reviews

**Review State**:
What the Searcher has decided about a Business so far, and their notes on it.
_Avoid_: status, stage, pipeline
