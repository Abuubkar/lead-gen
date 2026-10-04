"""Command line entry point."""

import argparse

from sourcer.db.database import describe
from sourcer.db.seed import export_seed, load_seed, seed_runs


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
    print(
        f"loaded {count} Search Runs from the shipped seed"
        if count
        else "seed already present; pass --force to replace it"
    )
    return 0


def cmd_build_seed(args):
    """Run real searches and save the result as the shipped dataset."""
    runs = seed_runs(args.markets, args.trades, pages=args.pages)
    path = export_seed(runs)
    print(f"wrote {path}")
    return 0


def cmd_rescore(args):
    """Score finished runs again under the current rubric and site reader."""
    from sourcer.db.database import connect
    from sourcer.db.repository import list_runs
    from sourcer.workers.runner import rescore

    run_ids = args.runs
    if not run_ids:
        connection = connect()
        try:
            run_ids = [run["id"] for run in list_runs(connection, limit=10_000)]
        finally:
            connection.close()
    for run_id in run_ids:
        print(f"  rescoring run {run_id}{'' if args.refetch else ' (no refetch)'}", flush=True)
        if rescore(run_id, refetch=args.refetch) is None:
            print(f"  run {run_id} does not exist")
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
    build.add_argument(
        "--markets",
        nargs="+",
        default=["Norwich|England|GB", "Lahore|Punjab|PK", "Austin|TX|US"],
        help='Catalogue market keys, "City|Region|Country".',
    )
    build.add_argument("--trades", nargs="+", default=["solicitors", "restaurants", "software"])
    build.add_argument("--pages", type=int, default=2)
    build.set_defaults(handler=cmd_build_seed)

    again = subcommands.add_parser(
        "rescore", help="Score finished runs again under the current rubric."
    )
    again.add_argument("runs", nargs="*", type=int, help="Run ids. Every run if omitted.")
    again.add_argument(
        "--no-refetch",
        dest="refetch",
        action="store_false",
        help="Rescore from stored columns without re-reading websites. Faster, but "
        "site-derived Signals come back unresolved.",
    )
    again.set_defaults(handler=cmd_rescore)

    args = parser.parse_args()
    raise SystemExit(args.handler(args))
