"""Filesystem locations, all overridable by environment variable.

The runtime directory holds the working database and the learned selector
fingerprint store, and is ignored by git.
"""

import os
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
