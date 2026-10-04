"""How good a prospect a Business is for one of BritNova's two service lines.

Two rubrics, one per mode, a hundred points each. A Search Run is in exactly one
mode, so every Business in it is scored by one rubric.

web   A local business that needs a website, or a better one. BritNova builds
      these on WordPress and Shopify; the solicitors and retail case studies on
      britnova.net are this line.
tech  A company that needs engineers. BritNova's AI, DevOps, cloud and custom
      software work; most of its case studies are this line.

Every point traces to a named Signal with the value that produced it, so a rep
can say why a business is on the list. No language model touches the Score; see
ADR 0002.

Missing data never costs points. A Signal we could not evaluate is recorded
unresolved, excluded from the denominator, and reflected in Confidence instead.
The reverse also holds: absence is only evidence when a source that reports the
field listed the business, so a blank column from a source that never fills it
stays unresolved rather than scoring as a gap.

Whether a rep may email a business without asking first is deliberately not
part of the Score. A sole trader is not a worse prospect, only one to phone
rather than email, so that rule is reported beside the Score; see compliance.py.

Weights are plain data in this module. A rule returns the fraction of its
Signal's points it earns, so the tables below are the only place a weight lives
and both rubrics can share a rule at different weights.
"""

from sourcer.config import CURRENT_YEAR

DEFAULT_MODE = "web"

# Web presences that are somebody else's platform rather than the business's
# own site. A business present only on one of these has no site of its own.
PLATFORM_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "yelp.com",
    "linkedin.com",
    "nextdoor.com",
    "google.com",
    "business.site",
    "wixsite.com",
    "weebly.com",
    "squarespace.com",
    "angi.com",
    "thumbtack.com",
    "homeadvisor.com",
    "yellowpages.com",
)

STALE_COPYRIGHT_YEARS = 3

# Sources that report a field when the business has it, so their silence is
# evidence of absence. Anything else leaves the Signal unresolved.
#
# Websites: YellowPages carries one for most businesses it lists. OpenStreetMap
# carried one for one in fifty-seven of the businesses it alone found in a real
# run, and neither the Food Standards Agency nor Companies House has a website
# field at all, so none of the three can tell us a business has no site.
SOURCES_REPORTING_WEBSITE = ("yellowpages",)
# Phones: only YellowPages. The Food Standards Agency API has a Phone field, but
# it was empty for all 500 Norwich food businesses sampled, so it describes the
# API rather than the business and its silence is not evidence of anything.
SOURCES_REPORTING_PHONE = ("yellowpages",)

# Companies House SIC codes for software and IT services, from the official
# condensed list (SIC07_CH_condensed_list_en.csv on GOV.UK). 63910, news
# agencies, and 63990, other information services, are left out on purpose.
SOFTWARE_SIC_CODES = ("62011", "62012", "62020", "62030", "62090", "63110", "63120")
# The OpenStreetMap office tag for IT businesses.
SOFTWARE_OSM_TAGS = ("it",)

# BritNova's stack as its own site lists it, plus the frameworks its case
# studies name. Overlap with what a prospect runs is the strongest single sign
# that BritNova can start work there without a learning curve.
BRITNOVA_STACK = (
    "python",
    "django",
    "flask",
    "typescript",
    "node",
    "react",
    "next.js",
    "angular",
    "graphql",
    "postgres",
    "aws",
    "azure",
    "gcp",
    "kubernetes",
    "docker",
    "terraform",
    "vercel",
    "cloudflare",
    "openai",
    "langchain",
    "pytorch",
    # Named by the Wear To Fit case study. Vue and Netlify are recognised on
    # sites too but are left out: BritNova does not list either, and this
    # table is what BritNova claims, not what it could plausibly learn.
    "shopify",
)
# Three shared technologies is treated as a full match; more adds nothing.
STACK_OVERLAP_FOR_FULL_MARKS = 3


def _enrichment_attempted(context):
    """Whether we actually read this Business's own site."""
    return context.get("enrichment_status") == "ok"


def _website_known(context):
    """Whether we are entitled to an opinion about this Business's website.

    True when we have one, when we read the site ourselves, or when a Source
    that reports websites listed the Business and gave none.
    """
    if context.get("website_url") or _enrichment_attempted(context):
        return True
    sources = context.get("sources") or []
    return any(name in sources for name in SOURCES_REPORTING_WEBSITE)


def _years(context):
    years = context.get("years_in_business")
    if years is None and context.get("founded_year"):
        years = CURRENT_YEAR - context["founded_year"]
    return years


# --------------------------------------------------------------------------- #
# Website need: the web rubric's core
# --------------------------------------------------------------------------- #


def _no_website(context):
    """No site at all is the clearest case for a new one.

    Which is why it may not be inferred from a Source that does not report
    websites. It is the largest award in the web rubric, and paying it for a
    blank column turns a thin record into a strong lead.
    """
    if context.get("website_url"):
        return 0.0, "has a website"
    if not _website_known(context):
        return None, None
    return 1.0, "no website found"


def _stale_copyright(context):
    year = context.get("copyright_year")
    if year is None:
        return None, None
    age = CURRENT_YEAR - year
    if age >= STALE_COPYRIGHT_YEARS:
        return 1.0, f"copyright {year}, {age} years stale"
    return 0.0, f"copyright {year}"


def _weak_platform(context):
    if not context.get("website_url"):
        return None, None
    if not context.get("https", True):
        return 1.0, "no HTTPS"
    builder = context.get("site_builder")
    if builder:
        return 1.0, f"built on {builder}"
    if context.get("https") is None:
        return None, None
    return 0.0, "custom site over HTTPS"


def _no_booking(context):
    has_booking = context.get("has_booking")
    if has_booking is None:
        return None, None
    return (0.0, "takes bookings online") if has_booking else (1.0, "no online booking")


# --------------------------------------------------------------------------- #
# Established: can the business pay for the work
# --------------------------------------------------------------------------- #


def _established(context):
    years = _years(context)
    if years is None:
        return None, None
    label = f"{years} years trading"
    if years >= 10:
        return 1.0, label
    if years >= 5:
        return 0.6, label
    if years >= 2:
        return 0.3, label
    return 0.0, label


def _reviews(context):
    count = context.get("public_review_count")
    if count is None:
        return None, None
    if count >= 20:
        return 1.0, f"{count} reviews"
    if count >= 5:
        return 0.6, f"{count} reviews"
    return 0.0, f"{count} reviews"


def _listing_complete(context):
    present = [field for field in ("phone_display", "street", "categories") if context.get(field)]
    if len(present) == 3:
        return 1.0, "phone, address and categories all listed"
    return 0.0, f"listing has {len(present)} of 3 key fields"


# --------------------------------------------------------------------------- #
# Reachable: can a rep get to a person. Shared by both rubrics.
# --------------------------------------------------------------------------- #


def _has_phone(context):
    if context.get("phone_display"):
        return 1.0, "phone listed"
    sources = context.get("sources") or []
    if any(name in sources for name in SOURCES_REPORTING_PHONE):
        return 0.0, "no phone listed"
    return None, None


def _has_email(context):
    emails = context.get("emails") or []
    if emails:
        return 1.0, emails[0]
    if _enrichment_attempted(context):
        return 0.0, "no email on the site"
    return None, None


# --------------------------------------------------------------------------- #
# Technical fit and engineering investment: the tech rubric
# --------------------------------------------------------------------------- #


def _is_software_company(context):
    categories = context.get("categories") or []
    sic_codes = [entry[4:] for entry in categories if str(entry).startswith("sic:")]
    if any(code in SOFTWARE_SIC_CODES for code in sic_codes):
        return 1.0, "software or IT by SIC code"
    if any(tag in categories for tag in SOFTWARE_OSM_TAGS):
        return 1.0, "IT office"
    if sic_codes or categories:
        return 0.0, "not classed as software or IT"
    return None, None


def _britnova_stack(context):
    if not _enrichment_attempted(context):
        return None, None
    stack = [item for item in (context.get("tech_stack") or []) if item in BRITNOVA_STACK]
    if not stack:
        return 0.0, "no shared technology recognised"
    fraction = min(len(stack) / STACK_OVERLAP_FOR_FULL_MARKS, 1.0)
    return fraction, ", ".join(stack)


def _mentions_ai(context):
    mentions = context.get("mentions_ai")
    if mentions is None:
        return None, None
    return (1.0, "site mentions AI or machine learning") if mentions else (0.0, "no AI mention")


def _has_careers(context):
    careers = context.get("has_careers")
    if careers is None:
        return None, None
    return (1.0, "has a careers page") if careers else (0.0, "no careers page")


# --------------------------------------------------------------------------- #
# The rubrics
# --------------------------------------------------------------------------- #

# name, group, max points, rule, and the context keys the rule reads. The keys
# are what let a Signal cite where its fact actually came from instead of
# pointing at whichever page was enriched last.
WEB_SIGNALS = (
    ("no_website", "need", 18.0, _no_website, ("website_url", "sources")),
    ("stale_copyright", "need", 10.0, _stale_copyright, ("copyright_year",)),
    ("weak_web_platform", "need", 9.0, _weak_platform, ("site_builder", "https")),
    ("no_online_booking", "need", 8.0, _no_booking, ("has_booking",)),
    ("established", "established", 15.0, _established, ("years_in_business", "founded_year")),
    ("review_volume", "established", 10.0, _reviews, ("public_review_count",)),
    (
        "listing_complete",
        "established",
        5.0,
        _listing_complete,
        ("phone_display", "street", "categories"),
    ),
    ("has_phone", "reachable", 12.0, _has_phone, ("phone_display", "sources")),
    ("has_email", "reachable", 13.0, _has_email, ("emails",)),
)

TECH_SIGNALS = (
    ("software_company", "fit", 15.0, _is_software_company, ("categories",)),
    ("shared_stack", "fit", 25.0, _britnova_stack, ("tech_stack",)),
    ("mentions_ai", "fit", 15.0, _mentions_ai, ("mentions_ai",)),
    ("careers_page", "growth", 20.0, _has_careers, ("has_careers",)),
    ("has_phone", "reachable", 12.0, _has_phone, ("phone_display", "sources")),
    ("has_email", "reachable", 13.0, _has_email, ("emails",)),
)

RUBRICS = {
    "web": {
        "label": "Web & e-commerce",
        "signals": WEB_SIGNALS,
        "core": "need",
        "groups": {
            "need": "Website need",
            "established": "Established",
            "reachable": "Reachable",
        },
    },
    "tech": {
        "label": "AI, cloud & software",
        "signals": TECH_SIGNALS,
        "core": "fit",
        "groups": {
            "fit": "Technical fit",
            "growth": "Engineering investment",
            "reachable": "Reachable",
        },
    },
}

MODES = tuple(RUBRICS)


def rubric(mode):
    """The rubric for a mode, falling back to the default for an unknown one."""
    return RUBRICS.get(mode) or RUBRICS[DEFAULT_MODE]


def is_mode(mode):
    return mode in RUBRICS


def mode_choices():
    """Key and label for every mode, for a picker."""
    return [(key, entry["label"]) for key, entry in RUBRICS.items()]


def core_group(mode=DEFAULT_MODE):
    """The group a Business needs evidence in before it can be scored at all."""
    return rubric(mode)["core"]


def group_labels(mode=DEFAULT_MODE):
    return rubric(mode)["groups"]


def group_totals(mode=DEFAULT_MODE):
    """Points available per group, for showing the rubric."""
    totals = {}
    for _, group, max_points, _, _ in rubric(mode)["signals"]:
        totals[group] = totals.get(group, 0.0) + max_points
    return totals


def total_points(mode=DEFAULT_MODE):
    return sum(max_points for _, _, max_points, _, _ in rubric(mode)["signals"])


# Where a fact came from, worst case first: a model guess is weaker evidence
# than a page we read, which is weaker than nothing at all being claimed.
ORIGIN_MODEL = "ai"
ORIGIN_WEBSITE = "website"


def _provenance(context, reads):
    """Which Source a Signal's fact came from, and the page to cite for it.

    Derived from which context keys the rule actually read, so a listing-derived
    fact is never cited to a page where it was not observed.
    """
    model_keys = context.get("_model_keys") or ()
    website_keys = context.get("_website_keys") or ()

    used = [key for key in reads if context.get(key) not in (None, "", [], {})] or list(reads)
    if any(key in model_keys for key in used):
        return ORIGIN_MODEL, context.get("evidence_url")
    if any(key in website_keys for key in used):
        return ORIGIN_WEBSITE, context.get("evidence_url")

    sources = context.get("sources") or []
    return (sources[0] if sources else None), None


def evaluate(context, mode=DEFAULT_MODE):
    """Every Signal of a mode's rubric for one Business, resolved or not.

    A rule that raises is a bug in the rubric, and the rubric is the one thing
    here that has to be auditable, so it is not caught. Quietly returning
    "unresolved" would shrink Confidence's denominator and hide the fault.
    """
    signals = []
    for name, group, max_points, rule, reads in rubric(mode)["signals"]:
        fraction, raw_value = rule(context)
        resolved = fraction is not None
        source, source_url = _provenance(context, reads) if resolved else (None, None)

        signals.append(
            {
                "name": name,
                "group_name": group,
                "raw_value": raw_value,
                "points": round(max_points * fraction, 2) if resolved else 0.0,
                "max_points": max_points,
                "resolved": resolved,
                "source": source,
                "source_url": source_url,
            }
        )
    return signals


def score(signals, mode=DEFAULT_MODE):
    """The Score and Confidence implied by a set of Signals.

    The Score is normalised over what we could actually evaluate, so a Business
    scored on half the rubric is compared fairly against one scored on all of
    it. Confidence says how much of the rubric that was.
    """
    resolvable = sum(signal["max_points"] for signal in signals if signal["resolved"])
    awarded = sum(signal["points"] for signal in signals if signal["resolved"])
    confidence = round(resolvable / total_points(mode), 3)

    # Without one resolved Signal in the core group there is no evidence the
    # business needs what BritNova sells, only that it can be reached and could
    # pay. Normalising over those alone scored a restaurant with a phone number
    # and nothing else as a perfect prospect. Confidence is still reported, so a
    # rep can see how much is known.
    core = rubric(mode)["core"]
    if not resolvable or not any(s["resolved"] and s["group_name"] == core for s in signals):
        return None, confidence
    return round(awarded / resolvable * 100, 1), confidence


def assess(context, mode=DEFAULT_MODE):
    """Signals, Score and Confidence for one Business under one mode's rubric."""
    signals = evaluate(context, mode)
    computed_score, confidence = score(signals, mode)
    return signals, computed_score, confidence
