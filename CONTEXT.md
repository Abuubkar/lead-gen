# Prospecting for BritNova

A prospecting tool for BritNova's business development team: it finds businesses in a market, reads their own websites, and ranks them by how well they fit one of BritNova's two service lines. It covers the United Kingdom, Pakistan and the United States.

## People

**Rep**:
The user of the tool: a member of BritNova's business development team looking for businesses to approach.
_Avoid_: user, searcher, SDR

**Contact**:
A named person or address reachable at a Business, read from its own website. A Business has zero or more Contacts.
_Avoid_: lead, person, decision-maker

## The target

**Business**:
A single company that could become a BritNova client. The unit of work; every other record hangs off it. User-facing headings may call it a prospect, the plain word a Rep uses, but code and data say Business.
_Avoid_: lead, company, account

**Mode**:
Which of BritNova's service lines a Search Run looks for, and so which rubric scores it. *Web* finds local businesses that need a website; *tech* finds companies that need engineers. A trade belongs to exactly one Mode, so the trade a Rep picks decides it.
_Avoid_: type, category, line

**Market**:
A city searched for Businesses, with its region, its country and the coordinates a Source searches around. The country decides which Sources run and which Contact Rule applies.
_Avoid_: location, area, city

**Website Need**:
How much a Business would benefit from a new or better website: no site, a stale one, a consumer site builder, no HTTPS, no online booking. The core of the web rubric.
_Avoid_: bad website, underinvestment, low quality

## Sourcing

**Source**:
One place Businesses are discovered, with its own coverage, fields and access rules. Each declares the countries it covers and is reachable or not independently of the others.
_Avoid_: site, provider, scraper

**Discovery**:
Finding which Businesses exist in a Market. Distinct from Enrichment, and usually from a different place.
_Avoid_: search, scraping

**Enrichment**:
Reading a Business's own website to learn what a Source does not carry.
_Avoid_: scraping, crawling

**Search Run**:
One Rep request for a trade in a Market, and everything discovered under it. Results persist after it ends.
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
How well a Business fits the service line of its Search Run's Mode, computed only from resolved Signals.
_Avoid_: rating, rank, grade

**Core Group**:
The group of Signals a Business needs at least one resolved Signal in before it is scored at all: Website Need for web, technical fit for tech. Without one there is no evidence it needs what BritNova sells, and it is left unscored rather than ranked on reachability alone.
_Avoid_: required group, gate

**Confidence**:
How much of the rubric rests on Signals we actually resolved. Reported beside the Score, never folded into it.
_Avoid_: accuracy, certainty

**Reputation**:
The public rating and review count a Source reports for a Business. Feeds the established Signals; it is not itself the Score.
_Avoid_: rating, score, reviews

**Contact Rule**:
Whether a Rep may email a Business without asking first, and what a call or email must include, under the law of the Business's country. Reported beside the Score and never part of it. Guidance from the regulator's published rules, not legal advice.
_Avoid_: compliance score, permission, eligibility

**Review State**:
What the Rep has decided about a Business so far, and their notes on it.
_Avoid_: status, stage, pipeline
