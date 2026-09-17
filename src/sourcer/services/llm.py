"""Optional language-model enrichment.

Two jobs, and only two. It fills facts the deterministic rules missed, and it
drafts a one-line outreach angle. It never produces or adjusts a Score: see
ADR 0002. A Searcher has to defend a shortlist, and a number nobody can audit is
worth less than a smaller number they can trace.

Entirely optional. With no API key the tool works exactly as before, which is
what keeps a reviewer's local run from breaking. Results are cached on the
Business row, so a second pass over the same market costs nothing.
"""

import json
import os

from sourcer.config import CURRENT_YEAR, EARLIEST_PLAUSIBLE_YEAR

MODEL = "claude-haiku-4-5-20251001"
MAX_CHARS = 6000
MAX_TOKENS = 400

PROMPT = """You are helping a search-fund buyer assess a small business as an \
acquisition target. Below is text scraped from the business's own website.

Extract only what the text actually supports. Use null for anything absent. Do \
not guess, and do not infer a person's role from a job title alone.

Return JSON with exactly these keys:
  "owner_name": the owner, founder or principal's full name, or null
  "owner_role": their stated role, or null
  "founded_year": four-digit year the business started, or null
  "employee_estimate": a number if the text states or strongly implies team \
size, else null
  "outreach_angle": one sentence a buyer could open a call with, naming \
something specific from the text. No greeting, no sign-off, under 25 words.

Business name: {name}
Website text:
{text}"""


def available():
    """Whether the language-model step can run at all."""
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def _client():
    from anthropic import Anthropic

    return Anthropic()


def _parse(raw):
    """Read the model's reply, tolerating fenced code and surrounding prose."""
    text = raw.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(text[start : end + 1])
    except ValueError:
        return {}


ALLOWED = ("owner_name", "owner_role", "founded_year", "employee_estimate", "outreach_angle")


def _clean(parsed):
    """Keep only the expected keys, and only values of a plausible shape."""
    found = {}
    for key in ALLOWED:
        value = parsed.get(key)
        if value in (None, "", "null"):
            continue
        if key == "founded_year":
            try:
                year = int(value)
            except (TypeError, ValueError):
                continue
            if EARLIEST_PLAUSIBLE_YEAR <= year <= CURRENT_YEAR:
                found[key] = year
            continue
        if key == "employee_estimate":
            found[key] = str(value)[:40]
            continue
        found[key] = str(value).strip()[:300]
    return found


def read_site(name, site_text):
    """What a model can add beyond the rules. Empty dict on any failure.

    A model that is slow, rate-limited or absent must never fail a Search Run,
    so every error here is swallowed and the Business keeps its rule-derived
    Signals.
    """
    if not available() or not site_text:
        return {}

    try:
        message = _client().messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[
                {
                    "role": "user",
                    "content": PROMPT.format(name=name, text=site_text[:MAX_CHARS]),
                }
            ],
        )
        raw = "".join(block.text for block in message.content if block.type == "text")
        return _clean(_parse(raw))
    except Exception:
        return {}
