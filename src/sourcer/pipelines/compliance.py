"""Whether a rep may email a business unprompted, and what a call needs first.

Reported beside the Score and never folded into it. A sole trader is not a
worse prospect than a limited company, only one a rep reaches differently, so
mixing the law into the ranking would bury good prospects for the wrong reason.

This is guidance drawn from each regulator's published rules, with the source
cited on every verdict. It is not legal advice, and it errs toward caution: where
the rules depend on a fact we do not have, it says so and treats the business as
the more protected case, which is what the UK regulator itself instructs.

Covered: email marketing in the UK, US and Pakistan, and telephone marketing in
the UK. Calls in the US and Pakistan were not researched, so nothing is said
about them rather than something guessed.
"""

ICO_B2B = (
    "https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-"
    "electronic-communications/business-to-business-marketing/"
)
FTC_CAN_SPAM = (
    "https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business"
)
DLA_PIPER_PK = "https://www.dlapiperdataprotection.com/index.html?t=electronic-marketing&c=PK"

# Companies House company types that are corporate bodies with their own legal
# personality, which PECR treats as corporate subscribers. The ICO's examples are
# "companies, limited liability partnerships, Scottish partnerships". Anything
# not listed is treated as an individual, per the ICO: "If you are unsure ...
# treat the details as belonging to an individual subscriber."
#
# limited-partnership is deliberately absent. An English, Welsh or Northern Irish
# limited partnership has no separate legal personality, and the ICO classes
# "other types of partnerships" with sole traders.
UK_CORPORATE_TYPES = frozenset(
    {
        "ltd",
        "plc",
        "llp",
        "old-public-company",
        "private-unlimited",
        "private-unlimited-nsc",
        "private-limited-guarant-nsc",
        "private-limited-guarant-nsc-limited-exemption",
        "private-limited-shares-section-30-exemption",
        "scottish-partnership",
    }
)

ALLOWED = "allowed"
CONSENT = "consent"


def _uk(business):
    company_type = business.get("company_type")
    phone = {
        "summary": "Screen the number against TPS and CTPS before calling.",
        "detail": "Applies to companies and sole traders alike. A number on either "
        "register cannot be called for marketing without the business's consent.",
    }
    if company_type in UK_CORPORATE_TYPES:
        return {
            "verdict": ALLOWED,
            "summary": "May be emailed without asking first",
            "basis": f"A {company_type.upper()} on Companies House is a corporate subscriber.",
            "must": [
                "Say who you are; do not disguise or conceal it.",
                "Give a valid address to opt out or unsubscribe.",
            ],
            "phone": phone,
            "source": ICO_B2B,
        }
    if company_type == "limited-partnership":
        basis = "A limited partnership is treated like a sole trader, as an individual."
    elif company_type:
        basis = (
            f"Company type {company_type} is not one the regulator names as corporate, "
            "so it is treated as an individual, as the regulator advises when unsure."
        )
    else:
        basis = (
            "Not matched to Companies House, where every limited company is listed. "
            "It is likely a sole trader or partnership, which count as individuals."
        )
    return {
        "verdict": CONSENT,
        "summary": "Email only with consent",
        "basis": basis,
        "must": [
            "Get specific consent before emailing, or rely on the soft opt-in "
            "only if they already bought from or negotiated with you.",
        ],
        "phone": phone,
        "source": ICO_B2B,
    }


def _us(business):
    return {
        "verdict": ALLOWED,
        "summary": "May be emailed without asking first",
        "basis": "CAN-SPAM needs no prior consent, and makes no exception for "
        "business-to-business email.",
        "must": [
            "Accurate From, To and Reply-To headers.",
            "A subject line that reflects the message.",
            "Your valid physical postal address.",
            "A clear statement that the message is an advertisement.",
            "A working opt-out, honoured within 10 business days.",
        ],
        "phone": None,
        "source": FTC_CAN_SPAM,
    }


def _pk(business):
    return {
        "verdict": ALLOWED,
        "summary": "May be emailed without asking first",
        "basis": "No law in force requires consent for commercial email. PECA 2016 "
        "section 25 makes spamming an offence where it is done for wrongful gain, "
        "and the Personal Data Protection Bill has not been enacted.",
        "must": [
            "Include a way to unsubscribe. Required for promotional texts, and the "
            "safe practice for email.",
        ],
        "phone": None,
        "source": DLA_PIPER_PK,
    }


RULES = {"GB": _uk, "US": _us, "PK": _pk}


def guidance(business, country):
    """The contact rules that apply to one business, or None for an unknown country."""
    rule = RULES.get(country or business.get("country"))
    return rule(business) if rule else None
