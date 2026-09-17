"""Turning messy Source records into a stable Business identity.

Every Source spells a business differently, so the dedup keys are computed here
and nowhere else. The three key normalisers return None when their input is
unusable rather than guessing, because a wrong key merges two different
Businesses, which is worse than failing to merge two records for the same one.
The text helpers below them return an empty string instead, since "no
distinctive words left" is a normal outcome rather than a failure.
"""

import hashlib
import json
import re
from urllib.parse import urlsplit

# The dedup key columns, strongest identity first. Declared once: this order is
# the resolution order, and store.py imports it rather than restating it.
DEDUP_RULES = ("website_domain", "phone_digits", "name_street_key")

# Dropped from the end of a name before comparing, so "Clarke Kent Plumbing LLC"
# and "Clarke Kent Plumbing, Inc." resolve to the same key. Multi-word entries
# are matched as trailing phrases, not as single tokens.
COMPANY_SUFFIXES = (
    "and sons",
    "l l c",
    "llc",
    "inc",
    "incorporated",
    "co",
    "company",
    "corp",
    "corporation",
    "ltd",
    "limited",
    "llp",
    "lp",
    "pllc",
    "pc",
    "plc",
    "group",
)
LEADING_ARTICLES = ("the ",)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_HOSTLIKE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def slug(text):
    """A URL path segment: lowercase, punctuation collapsed to hyphens.

    Lives here rather than in each adapter, where it was byte-identical twice.
    """
    return _NON_ALNUM.sub("-", (text or "").strip().lower()).strip("-")


def website_domain(url):
    """The bare host of a website, lowercased and without a leading "www.".

    The most stable identity a small business has: it survives a rename, a
    phone change and a move.
    """
    if not url:
        return None
    candidate = str(url).strip()
    if not candidate:
        return None
    # urlsplit only finds a host when there is a scheme.
    if "//" not in candidate:
        candidate = "//" + candidate
    host = (urlsplit(candidate).hostname or "").lower().strip(".")
    if not host or not _HOSTLIKE.match(host):
        return None
    if host.startswith("www."):
        host = host[4:]
    return host or None


def phone_digits(phone):
    """Exactly ten digits of a North American number, or nothing.

    Sources render the same number a dozen ways. Anything that is not a
    plausible ten-digit number is discarded rather than half-matched.
    """
    if not phone:
        return None
    digits = re.sub(r"\D", "", str(phone))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def _normalise_words(text):
    """Lowercase, strip punctuation, collapse whitespace. Empty string if none."""
    if not text:
        return ""
    return _NON_ALNUM.sub(" ", str(text).lower()).strip()


def normalise_name(name):
    """A company name reduced to its distinctive words.

    Suffixes are stripped repeatedly and longest first, so "Kent and Sons Co"
    loses both the trailing "co" and the trailing phrase "and sons".
    """
    words = _normalise_words(name)
    for article in LEADING_ARTICLES:
        if words.startswith(article):
            words = words[len(article) :]

    changed = True
    while changed and words:
        changed = False
        for suffix in sorted(COMPANY_SUFFIXES, key=lambda s: -len(s.split())):
            if words == suffix:
                return ""
            if words.endswith(" " + suffix):
                words = words[: -(len(suffix) + 1)].strip()
                changed = True
                break
    return words


def name_street_key(name, street):
    """The weakest of the three keys: a normalised name plus a street.

    Needs both halves. A name alone is not an identity, because a city can hold
    two unrelated businesses called Austin Plumbing.
    """
    cleaned_name = normalise_name(name)
    cleaned_street = _normalise_words(street)
    if not cleaned_name or not cleaned_street:
        return None
    return f"{cleaned_name}|{cleaned_street}"


def dedup_keys(record):
    """The three candidate keys for a record, strongest first.

    Returned whole so a caller can match an existing Business on any of them,
    not only on the one that won.
    """
    return {
        "website_domain": website_domain(record.get("website_url")),
        "phone_digits": phone_digits(record.get("phone_display")),
        "name_street_key": name_street_key(record.get("name"), record.get("street")),
    }


def _content_key(record):
    """A digest of everything the record actually says.

    The last resort, for a record with no website, no phone, no street and no
    name. It must not be a shared constant: a UNIQUE (run_id, dedup_key) would
    then collapse every unidentifiable record into a single row, losing all but
    the first. Hashing the content keeps genuinely identical records together
    and everything else apart.
    """
    material = {
        key: str(value) for key, value in sorted(record.items()) if value not in (None, "", [], {})
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
    return f"content:{digest[:16]}"


def resolve_dedup_key(record, keys=None):
    """Pick the identity for a record, and say which rule produced it.

    Total by construction: the dedup_key column is NOT NULL, so a Business with
    no website, no phone and no street still needs an identity. The later rules
    exist for exactly that case, and naming the rule that won means a weak
    identity is visible rather than implied.
    """
    keys = keys if keys is not None else dedup_keys(record)
    for rule in DEDUP_RULES:
        if keys.get(rule):
            return keys[rule], rule

    name = normalise_name(record.get("name"))
    city = _normalise_words(record.get("city"))
    if name and city:
        return f"{name}|{city}", "name_city"
    if name:
        return name, "name"
    return _content_key(record), "content"


def key_rule_of(business):
    """Which rule produced a stored Business's key, inferred from its columns.

    Computed on read rather than stored, so a weak identity is visible in the
    interface without the schema change this step's spec rules out.
    """
    key = business.get("dedup_key")
    if not key:
        return None
    for rule in DEDUP_RULES:
        if business.get(rule) and business[rule] == key:
            return rule
    if key.startswith("content:"):
        return "content"
    return "name_city" if "|" in key else "name"
