"""Reading a Business's own website for what a listing cannot tell us.

A listing says a business exists. Its website says how long it has been going,
who runs it, and whether anyone has touched the site this decade. Those are the
facts a Searcher actually wants, and they are the ones no competitor surfaces.

Every rule here is deterministic. The language model at step 13 fills gaps these
rules leave and never replaces them, so the tool works fully with no API key.
"""

import re
from urllib.parse import urljoin, urlsplit

from sourcer.config import CURRENT_YEAR, EARLIEST_PLAUSIBLE_YEAR
from sourcer.scrapers.client import Blocked, Disallowed

# Three pages is enough. The homepage carries the tagline and the footer, and
# an about or contact page carries the founding year and the owner's name.
MAX_PAGES = 3
INTERESTING_PATH = re.compile(r"(about|our-story|our-team|meet|history|contact|staff)", re.I)

# Shared with the rubric, which is the other place a year has to be plausible.
# Older than the floor and a "since" date is more likely a street number or a
# phone fragment than a founding year.

FOUNDED = re.compile(
    r"(?:since|established|est\.?|serving\s+\w+\s+since|founded(?:\s+in)?|"
    r"family\s+owned\s+since|in\s+business\s+since)\s*:?\s*(1[89]\d{2}|20[0-2]\d)",
    re.I,
)
YEARS_OF = re.compile(
    r"(\d{1,3})\+?\s*years?\s+(?:of\s+)?(?:experience|service|in\s+business)", re.I
)

# Words that precede a role rather than ending a name: "Chris Knox, Project
# Owner" must not yield "Chris Knox Project". Stripped from the captured name.
ROLE_QUALIFIERS = (
    "project",
    "vice",
    "senior",
    "managing",
    "general",
    "co",
    "assistant",
    "deputy",
    "executive",
    "operations",
    "practice",
    "regional",
    "branch",
)
# Titles and roles that lead a name as often as they follow it, so that
# "CEO Matt Burns, President" does not yield a person called CEO Matt.
NAME_PREFIXES = (
    "ceo",
    "cfo",
    "coo",
    "president",
    "owner",
    "founder",
    "co-founder",
    "principal",
    "proprietor",
    "manager",
    "director",
    "dr",
    "mr",
    "mrs",
    "ms",
)
# A capitalised phrase is not a person if it contains trade or company words.
# Without this, "Green Building, Principal Partner" reads as someone called
# Building.
NOT_A_NAME = {
    "ste",
    "suite",
    "unit",
    "apt",
    "floor",
    "road",
    "street",
    "avenue",
    "drive",
    "building",
    "project",
    "company",
    "services",
    "service",
    "group",
    "inc",
    "llc",
    "construction",
    "plumbing",
    "heating",
    "air",
    "electric",
    "electrical",
    "roofing",
    "solutions",
    "systems",
    "contractors",
    "team",
    "the",
    "our",
    "about",
    "contact",
    "home",
    "commercial",
    "residential",
    "quality",
    "family",
    "customer",
    "emergency",
    "repair",
    "installation",
    "conditioning",
    "mechanical",
    "and",
}

OWNER_ROLE = re.compile(
    r"([A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+){1,3})\s*[,\-–—]\s*"
    r"(?:(?:Project|Vice|Senior|Managing|General|Executive)[\s-]+)?"
    r"(Owner|Founder|President|Co-?Founder|Principal|CEO|Proprietor|Manager)",
)
ROLE_FIRST = re.compile(
    r"(Owner|Founder|President|Proprietor)\s*[,:\-–—]?\s*"
    r"([A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+){1,2})",
)
# "owned by Gary Hacker", "founded by Gary Hacker".
OWNED_BY = re.compile(
    r"(?i:owned|founded|started|established)\s+(?i:by)\s+"
    r"(?:Dr\.?\s+)?([A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+){1,2})",
)
# A credentialled principal, which is how practices name theirs.
CREDENTIALLED = re.compile(
    r"\bDr\.?\s+([A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+){0,2})"
    r"(?:\s*,?\s*(DDS|DMD|DVM|MD|CPA|PE))?",
)
PRACTICE_PRINCIPAL = re.compile(
    r"(owner|founder|practice\s+owner|our\s+doctor|meet\s+(?:dr|the))", re.I
)

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"\(?\b\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")
COPYRIGHT_YEAR = re.compile(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?(\d{4})", re.I)

OWNERSHIP_WORDS = {
    "family_owned": re.compile(r"family[\s-]+(?:owned|run|operated|business)", re.I),
    "locally_owned": re.compile(r"locally[\s-]+(?:owned|operated)", re.I),
    "veteran_owned": re.compile(r"veteran[\s-]+owned", re.I),
    "second_generation": re.compile(r"(?:second|third|2nd|3rd)[\s-]+generation", re.I),
}
SUCCESSION_WORDS = re.compile(
    r"(retiring|retirement|business\s+for\s+sale|new\s+ownership|under\s+new\s+management)", re.I
)
FRANCHISE_WORDS = re.compile(
    r"(franchise|franchising|each\s+location\s+independently|independently\s+owned\s+and\s+operated)",
    re.I,
)
BOOKING_WORDS = re.compile(
    r"(book\s+(?:now|online|an?\s+appointment)|schedule\s+(?:online|service|now)|"
    r"request\s+(?:a\s+)?(?:quote|estimate)|get\s+(?:a\s+)?(?:quote|estimate))",
    re.I,
)
# A consumer site builder is a signal of digital underinvestment, not a fault.
BUILDERS = {
    "wix": re.compile(r"wix\.com|wixstatic", re.I),
    "squarespace": re.compile(r"squarespace", re.I),
    "godaddy": re.compile(r"godaddy|websitebuilder", re.I),
    "weebly": re.compile(r"weebly", re.I),
    "wordpress": re.compile(r"wp-content|wordpress", re.I),
}


def _year_or_none(value):
    year = int(value)
    return year if EARLIEST_PLAUSIBLE_YEAR <= year <= CURRENT_YEAR else None


def _pages_to_read(fetcher, home_url, response):
    """The homepage plus up to two pages that look like they say who we are."""
    pages = [(home_url, response)]
    host = urlsplit(home_url).netloc

    candidates = []
    for href in response.css("a::attr(href)").getall():
        if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        absolute = urljoin(home_url, href)
        if urlsplit(absolute).netloc != host or not INTERESTING_PATH.search(absolute):
            continue
        absolute = absolute.split("#")[0]
        if absolute not in candidates and absolute != home_url:
            candidates.append(absolute)

    for url in candidates[: MAX_PAGES - 1]:
        try:
            pages.append((url, fetcher.get(url, referer=home_url)))
        except Exception:
            # One unreadable inner page is not a failed enrichment.
            continue
    return pages


def _text_of(response):
    try:
        return " ".join(response.get_all_text(separator=" ", strip=True).split())
    except Exception:
        return ""


def _html_of(response):
    body = getattr(response, "body", b"")
    return body.decode("utf-8", "ignore") if isinstance(body, bytes) else str(body)


def _clean_person(name):
    """A captured phrase reduced to a plausible person's name, or nothing.

    Two failure modes seen on real sites. A role qualifier gets absorbed, so
    "Chris Knox, Project Owner" yields "Chris Knox Project". And a capitalised
    trade phrase matches, so "Green Building, Principal Partner" yields someone
    called Building.
    """
    if not name:
        return None
    words = name.strip().split()
    while words and words[-1].lower() in ROLE_QUALIFIERS:
        words.pop()
    # A role can lead as easily as follow: "CEO Matt Burns, President".
    while words and words[0].lower().strip(".,") in NAME_PREFIXES:
        words.pop(0)
    if not 2 <= len(words) <= 3:
        return None
    # A digit means an address or a suite number, not a person. "Ste C124"
    # otherwise passes every other check.
    if any(character.isdigit() for character in " ".join(words)):
        return None
    if any(word.lower().strip(".,") in NOT_A_NAME for word in words):
        return None
    return " ".join(words)


def _read_owner(text):
    match = OWNER_ROLE.search(text)
    if match:
        person = _clean_person(match.group(1))
        if person:
            return person, match.group(2).strip()
    match = ROLE_FIRST.search(text)
    if match:
        person = _clean_person(match.group(2))
        if person:
            return person, match.group(1).strip()
    match = OWNED_BY.search(text)
    if match:
        person = _clean_person(match.group(1))
        if person:
            return person, "Owner"
    # A titled name only counts when the page frames it as whose practice this
    # is. Otherwise a referral or a staff list would read as ownership.
    if PRACTICE_PRINCIPAL.search(text):
        match = CREDENTIALLED.search(text)
        if match:
            person = _clean_person(match.group(1))
            if person:
                return person, match.group(2) or "Principal"
    return None, None


def extract(text, html, url):
    """Every Signal-bearing fact the rules can find in one site's pages."""
    found = {"evidence_url": url}

    founded = FOUNDED.search(text)
    if founded:
        year = _year_or_none(founded.group(1))
        if year:
            found["founded_year"] = year
            found["years_in_business"] = CURRENT_YEAR - year
    elif YEARS_OF.search(text):
        years = int(YEARS_OF.search(text).group(1))
        if 0 < years < 150:
            found["years_in_business"] = years

    owner_name, owner_role = _read_owner(text)
    if owner_name:
        found["owner_name"] = owner_name
        found["owner_role"] = owner_role

    emails = [address for address in EMAIL.findall(html) if not address.endswith((".png", ".jpg"))]
    if emails:
        found["emails"] = sorted(set(emails))[:3]
    phones = PHONE.findall(text)
    if phones:
        found["phones"] = sorted(set(phones))[:3]

    copyright_year = COPYRIGHT_YEAR.search(html)
    if copyright_year:
        year = _year_or_none(copyright_year.group(1))
        if year:
            found["copyright_year"] = year

    found["ownership_language"] = [
        label for label, pattern in OWNERSHIP_WORDS.items() if pattern.search(text)
    ]
    found["succession_language"] = bool(SUCCESSION_WORDS.search(text))
    found["franchise_language"] = bool(FRANCHISE_WORDS.search(text))
    found["has_booking"] = bool(BOOKING_WORDS.search(text))
    found["site_builder"] = next(
        (label for label, pattern in BUILDERS.items() if pattern.search(html)), None
    )
    found["https"] = url.startswith("https://")
    return found


def enrich(fetcher, website_url):
    """Read a Business's own site. Returns what was found, and how it went.

    Never raises for an unreachable site: a Business we could not enrich must
    still reach the Searcher, scored on what we do know, with its Confidence
    reflecting the gap.
    """
    if not website_url:
        return {}, "skipped"

    home_url = website_url if "//" in website_url else f"https://{website_url}"
    try:
        response = fetcher.get(home_url)
    except Disallowed:
        return {}, "skipped"
    except Blocked:
        return {}, "failed"
    except Exception:
        return {}, "failed"

    pages = _pages_to_read(fetcher, home_url, response)
    text = " ".join(_text_of(page_response) for _, page_response in pages)
    html = " ".join(_html_of(page_response) for _, page_response in pages)
    found = extract(text, html, home_url)
    found["pages_read"] = len(pages)
    # Handed on for the optional model step, which would otherwise refetch.
    # Never stored: it has no column, and the Signals are what persist.
    found["site_text"] = text
    return found, "ok"
