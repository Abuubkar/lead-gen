"""Filesystem locations, all overridable by environment variable.

The runtime directory holds the working database and the learned selector
fingerprint store, and is ignored by git. The seed directory holds the dataset
committed to the repository, which is copied into the runtime directory at boot
so a fresh deployment shows results immediately.
"""

import os
from pathlib import Path

DEFAULT_DATA_DIR = "data"
DEFAULT_SEED_DIR = "seed"


def data_dir():
    """Writable runtime directory. Created on first use."""
    path = Path(os.environ.get("SOURCER_DATA_DIR", DEFAULT_DATA_DIR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def seed_dir():
    """Committed seed data. Not created: it either ships or it does not."""
    return Path(os.environ.get("SOURCER_SEED_DIR", DEFAULT_SEED_DIR))


def db_path():
    """The working database."""
    override = os.environ.get("SOURCER_DB")
    if override:
        return Path(override)
    return data_dir() / "sourcer.db"


def selector_store_path():
    """Where Scrapling keeps relocatable selector fingerprints.

    Pointed inside the project on purpose. The library's default is a file
    inside its own installed package directory, which a reinstall would discard
    along with every selector learned so far. Used from step 4.
    """
    return data_dir() / "selectors.db"
