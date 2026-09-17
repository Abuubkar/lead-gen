"""CSV export of the filtered view.

What is on screen is what exports, because the filter table is shared with the
page and the API rather than reimplemented here.
"""

import csv
import io

EXPORT_COLUMNS = (
    "score",
    "confidence",
    "name",
    "owner_name",
    "phone_display",
    "website_url",
    "street",
    "city",
    "state",
    "postal_code",
    "years_in_business",
    "founded_year",
    "public_rating",
    "public_review_count",
    "categories",
    "sources",
    "review_state",
    "review_notes",
    "key_rule",
)


def _row(business):
    """One row, with list columns flattened to something a spreadsheet shows."""
    flattened = {}
    for column in EXPORT_COLUMNS:
        value = business.get(column)
        flattened[column] = ", ".join(map(str, value)) if isinstance(value, list) else value
    return flattened


def to_csv(businesses):
    """The filtered Businesses as CSV text."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for business in businesses:
        writer.writerow(_row(business))
    return buffer.getvalue()


def filename_for(run):
    """A filename that says what the export is, not just when it happened."""
    stem = f"sourcer-{run['trade']}-{run['city']}-{run['id']}"
    return f"{stem}.csv".replace(" ", "-").lower()
