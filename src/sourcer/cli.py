"""Command line entry point."""

import argparse

from sourcer.db import describe
from sourcer.seed import export_seed, load_seed, seed_runs


def cmd_init_db(_args):
    summary = describe()
    print(f"database: {summary['path']}")
    for kind in ("tables", "indexes"):
        names = summary[kind]
        print(f"{kind} ({len(names)}): {', '.join(names)}")
    return 0


def cmd_seed(args):
    """Fill the working database with the dataset shipped in the repository."""
    count = load_seed(force=args.force)
    print(f"loaded {count} Search Runs from the shipped seed" if count
          else "seed already present; pass --force to replace it")
    return 0


def cmd_build_seed(args):
    """Run real searches and save the result as the shipped dataset."""
    runs = seed_runs(args.markets, args.trades, pages=args.pages)
    path = export_seed(runs)
    print(f"wrote {path}")
    return 0


def main():
    parser = argparse.ArgumentParser(prog="sourcer", description="Acquisition target sourcing.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    init = subcommands.add_parser("init-db", help="Create or update the database, then report it.")
    init.set_defaults(handler=cmd_init_db)

    seed = subcommands.add_parser("seed", help="Load the shipped dataset into the database.")
    seed.add_argument("--force", action="store_true", help="Replace existing rows.")
    seed.set_defaults(handler=cmd_seed)

    build = subcommands.add_parser(
        "build-seed", help="Run live searches and write the shipped dataset."
    )
    build.add_argument("--markets", nargs="+", default=["Austin,TX", "Phoenix,AZ", "Columbus,OH"])
    build.add_argument("--trades", nargs="+", default=["plumbing", "hvac", "dental"])
    build.add_argument("--pages", type=int, default=2)
    build.set_defaults(handler=cmd_build_seed)

    args = parser.parse_args()
    raise SystemExit(args.handler(args))
