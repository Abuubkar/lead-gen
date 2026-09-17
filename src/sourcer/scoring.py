"""How well a Business fits an acquisition thesis, and why.

A hundred points across four groups. Every point traces to a named Signal with
the value that produced it, so a Searcher can defend a shortlist rather than
quoting a number. No language model touches the Score. See ADR 0002.

Missing data never costs points. A Signal we could not evaluate is recorded
unresolved, excluded from the denominator, and reflected in Confidence instead.
That is deliberate: the least digitally present businesses are often the best
targets, and a rubric that punished thin evidence would bury them.

Weights are plain data in this module so they can be argued with and tuned
without touching the logic.
"""

# Web presences that are somebody else's platform rather than the business's
# own site. Having only one of these is itself a sign of underinvestment.
PLATFORM_DOMAINS = (
    "facebook.com", "instagram.com", "yelp.com", "linkedin.com", "nextdoor.com",
    "google.com", "business.site", "wixsite.com", "weebly.com", "squarespace.com",
    "angi.com", "thumbtack.com", "homeadvisor.com", "yellowpages.com",
)

STALE_COPYRIGHT_YEARS = 3
CURRENT_YEAR = 2026

GROUP_LABELS = {
    "succession": "Succession likelihood",
    "underinvestment": "Digital underinvestment",
    "acquirability": "Acquirability",
    "demand": "Demand proof",
}


def _years(context):
    years = context.get("years_in_business")
    if years is None and context.get("founded_year"):
        years = CURRENT_YEAR - context["founded_year"]
    return years


def _age(context):
    """Older is better: an owner twenty-five years in is closer to selling."""
    years = _years(context)
    if years is None:
        return None, None
    if years >= 25:
        return 14.0, f"{years} years in business"
    if years >= 15:
        return 9.0, f"{years} years in business"
    if years >= 8:
        return 4.0, f"{years} years in business"
    return 0.0, f"{years} years in business"


def _owner_named(context):
    name = context.get("owner_name")
    if name:
        role = context.get("owner_role")
        return 11.0, f"{name}{f', {role}' if role else ''}"
    # Absence is not evidence: we may simply not have read a page that says so.
    if context.get("enrichment_status") in ("ok",) or context.get("sources_include_bbb"):
        return 0.0, "no owner named"
    return None, None


def _owner_language(context):
    language = context.get("ownership_language")
    if language is None:
        return None, None
    if language:
        return 5.0, ", ".join(label.replace("_", " ") for label in language)
    return 0.0, "no owner-operator language"


def _no_website(context):
    """No website at all is the strongest underinvestment signal there is."""
    if context.get("website_url"):
        return 0.0, "has a website"
    return 12.0, "no website found"


def _stale_copyright(context):
    year = context.get("copyright_year")
    if year is None:
        return None, None
    age = CURRENT_YEAR - year
    if age >= STALE_COPYRIGHT_YEARS:
        return 7.0, f"copyright {year}, {age} years stale"
    return 0.0, f"copyright {year}"


def _weak_platform(context):
    if context.get("enrichment_status") == "skipped" and not context.get("website_url"):
        return None, None
    builder = context.get("site_builder")
    if not context.get("https", True):
        return 4.0, "no HTTPS"
    if builder:
        return 4.0, f"built on {builder}"
    if context.get("https") is None:
        return None, None
    return 0.0, "custom site over HTTPS"


def _no_booking(context):
    has_booking = context.get("has_booking")
    if has_booking is None:
        return None, None
    return (0.0, "takes bookings online") if has_booking else (2.0, "no online booking")


def _single_location(context):
    count = context.get("location_count")
    if count is not None:
        return (10.0, f"{count} location") if count <= 1 else (0.0, f"{count} locations")
    if context.get("street"):
        return 10.0, "one address listed"
    return None, None


def _not_a_chain(context):
    franchise = context.get("is_franchise") or context.get("franchise_language")
    if franchise:
        return 0.0, "franchise or chain markers"
    if context.get("enrichment_status") == "ok" or context.get("is_franchise") is not None:
        return 8.0, "no chain markers"
    return None, None


def _small_team(context):
    estimate = context.get("employee_estimate")
    if not estimate:
        return None, None
    digits = "".join(character for character in str(estimate) if character.isdigit())
    if not digits:
        return None, None
    headcount = int(digits)
    described = f"about {headcount} staff"
    return (4.0, described) if headcount <= 50 else (0.0, described)


def _own_domain(context):
    domain = (context.get("website_domain") or "").lower()
    if not context.get("website_url"):
        return 0.0, "no domain of its own"
    if any(platform in domain for platform in PLATFORM_DOMAINS):
        return 0.0, f"presence on {domain} only"
    return 3.0, f"own domain, {domain}"


def _reviews(context):
    count = context.get("public_review_count")
    if count is None:
        return None, None
    if count >= 20:
        return 8.0, f"{count} reviews"
    if count >= 5:
        return 5.0, f"{count} reviews"
    return 0.0, f"{count} reviews"


def _rating(context):
    value = context.get("public_rating")
    if value is None:
        return None, None
    return (6.0, f"rated {value}") if value >= 4.0 else (0.0, f"rated {value}")


def _accredited(context):
    accredited = context.get("bbb_accredited")
    if accredited is None:
        return None, None
    return (4.0, "BBB accredited") if accredited else (0.0, "not BBB accredited")


def _listing_complete(context):
    present = [
        field for field in ("phone_display", "street", "categories") if context.get(field)
    ]
    if len(present) == 3:
        return 2.0, "phone, address and categories all listed"
    return 0.0, f"listing has {len(present)} of 3 key fields"


# name, group, max points, rule. The four group totals are 30, 25, 25 and 20.
SIGNALS = (
    ("years_in_business", "succession", 14.0, _age),
    ("owner_named", "succession", 11.0, _owner_named),
    ("owner_operator_language", "succession", 5.0, _owner_language),
    ("no_website", "underinvestment", 12.0, _no_website),
    ("stale_copyright", "underinvestment", 7.0, _stale_copyright),
    ("weak_web_platform", "underinvestment", 4.0, _weak_platform),
    ("no_online_booking", "underinvestment", 2.0, _no_booking),
    ("single_location", "acquirability", 10.0, _single_location),
    ("not_a_chain", "acquirability", 8.0, _not_a_chain),
    ("small_team", "acquirability", 4.0, _small_team),
    ("own_domain", "acquirability", 3.0, _own_domain),
    ("review_volume", "demand", 8.0, _reviews),
    ("rating", "demand", 6.0, _rating),
    ("bbb_accredited", "demand", 4.0, _accredited),
    ("listing_complete", "demand", 2.0, _listing_complete),
)

TOTAL_POINTS = sum(max_points for _, _, max_points, _ in SIGNALS)


def group_totals():
    """Points available per group, for showing the rubric."""
    totals = {}
    for _, group, max_points, _ in SIGNALS:
        totals[group] = totals.get(group, 0.0) + max_points
    return totals


def evaluate(context):
    """Every Signal for one Business, resolved or not."""
    signals = []
    for name, group, max_points, rule in SIGNALS:
        try:
            points, raw_value = rule(context)
        except Exception:
            points, raw_value = None, None

        resolved = points is not None
        signals.append(
            {
                "name": name,
                "group_name": group,
                "raw_value": raw_value,
                "points": float(points) if resolved else 0.0,
                "max_points": max_points,
                "resolved": resolved,
                "source_url": context.get("evidence_url") if resolved else None,
            }
        )
    return signals


def score(signals):
    """The Score and Confidence implied by a set of Signals.

    The Score is normalised over what we could actually evaluate, so a Business
    scored on half the rubric is compared fairly against one scored on all of
    it. Confidence says how much of the rubric that was.
    """
    resolvable = sum(signal["max_points"] for signal in signals if signal["resolved"])
    awarded = sum(signal["points"] for signal in signals if signal["resolved"])

    if not resolvable:
        return None, 0.0
    return round(awarded / resolvable * 100, 1), round(resolvable / TOTAL_POINTS, 3)


def assess(context):
    """Signals, Score and Confidence for one Business."""
    signals = evaluate(context)
    computed_score, confidence = score(signals)
    return signals, computed_score, confidence
