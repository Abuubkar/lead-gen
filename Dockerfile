# One container: the web app, the worker thread and the database file.
#
# Pinned to the Python the project pins locally, which is the top of Scrapling's
# officially supported range. Matching the two removes a whole class of "works
# on my machine".
FROM python:3.13-slim

# uv, so the image resolves from the same lockfile a developer uses.
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_FROZEN=1 \
    PYTHONUNBUFFERED=1 \
    SOURCER_DATA_DIR=/data \
    SOURCER_SEED_DIR=/app/seed

WORKDIR /app

# Dependencies first, so a source change does not reinstall the world.
# README.md is declared as the project readme, so the wheel build needs it.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-install-project --no-dev

COPY src ./src
COPY seed ./seed
RUN uv sync --no-dev

# The working database lives on its own volume. Without one, a redeploy
# reseeds from the committed dataset, which is a fine default for a demo.
RUN mkdir -p /data
VOLUME ["/data"]

# The browser tier is off here on purpose. Headless Chromium needs more memory
# than a small instance has, and the HTTP sources work without it. To enable it,
# move up an instance size, set SOURCER_BROWSER=1, and add the browser install
# below.
#   RUN uv run patchright install --with-deps chromium
ENV SOURCER_BROWSER=0

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "sourcer.web:app", "--host", "0.0.0.0", "--port", "8000"]
