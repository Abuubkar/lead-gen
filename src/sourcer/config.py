"""Filesystem locations, all overridable by environment variable.

The runtime directory holds the working database and the learned selector
fingerprint store, and is ignored by git.
"""

import os
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_DATA_DIRNAME = "data"
DEFAULT_SEED_DIRNAME = "seed"


def project_root():
    """The directory holding pyproject.toml, found by walking up from this file.

    Falls back to the working directory when there is none, which is the case
    for an installed wheel. Deployments set SOURCER_DATA_DIR explicitly rather
    than relying on that fallback.
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return Path.cwd()


def data_dir():
    """Writable runtime directory, anchored to the project rather than the
    working directory, so the same files are found whatever directory the
    process was started from. Created on first use."""
    override = os.environ.get("SOURCER_DATA_DIR")
    path = Path(override) if override else project_root() / DEFAULT_DATA_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def seed_dir():
    """The dataset committed to the repository. Not created: it ships or it does not."""
    override = os.environ.get("SOURCER_SEED_DIR")
    return Path(override) if override else project_root() / DEFAULT_SEED_DIRNAME


def db_path():
    """The working database."""
    override = os.environ.get("SOURCER_DB")
    return Path(override) if override else data_dir() / "sourcer.db"


def selector_store_path():
    """Where Scrapling keeps relocatable selector fingerprints.

    Anchored inside the project on purpose. The library's default is a file
    inside its own installed package directory, which a reinstall would discard
    along with every selector learned so far. Used from step 4.
    """
    return data_dir() / "selectors.db"


# --------------------------------------------------------------------------- #
# Shared constants
# --------------------------------------------------------------------------- #

# Derived, not hard-coded. A literal year silently rots: every age Signal would
# drift by one on 1 January and nobody would notice.
CURRENT_YEAR = datetime.now(UTC).year

# Older than this and a "since" date is more likely a street number or a phone
# fragment than a founding year.
EARLIEST_PLAUSIBLE_YEAR = 1850


# --------------------------------------------------------------------------- #
# Feature flags
# --------------------------------------------------------------------------- #


def browser_enabled():
    """Whether the browser tier may be used.

    Off by default. Headless Chromium measured 920 MB to 1.5 GB of resident
    memory, against 512 MB on the smallest deployment tiers, and the
    HTTP-only Sources must keep working there.
    """
    return os.environ.get("SOURCER_BROWSER", "").strip().lower() in ("1", "true", "yes")


def proxies():
    """A rotation list from the environment, empty when none is configured."""
    raw = os.environ.get("SOURCER_PROXIES", "")
    return [entry.strip() for entry in raw.split(",") if entry.strip()]
