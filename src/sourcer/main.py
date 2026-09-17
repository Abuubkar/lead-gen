"""ASGI entry point.

    uv run uvicorn sourcer.main:app

Builds the application: apply the schema, load the shipped dataset if the
database is empty, then serve. Kept apart from the handlers so importing a
route does not start a database.
"""

import logging

from starlette.applications import Starlette

from sourcer.api.routes import routes
from sourcer.db.database import init_db
from sourcer.db.seed import load_seed

log = logging.getLogger("sourcer")


def build():
    init_db().close()
    try:
        load_seed()
    except Exception:
        # A malformed seed must never stop the application booting, but it must
        # not vanish either: an empty table would otherwise look like a design.
        log.exception("could not load the shipped dataset")
    return Starlette(routes=routes)


app = build()
