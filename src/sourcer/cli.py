"""Command line entry point."""

import argparse

from sourcer.db import describe


def cmd_init_db(_args):
    summary = describe()
    print(f"database: {summary['path']}")
    for kind in ("tables", "indexes"):
        names = summary[kind]
        print(f"{kind} ({len(names)}): {', '.join(names)}")
    return 0


def main():
    parser = argparse.ArgumentParser(prog="sourcer", description="Acquisition target sourcing.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    init = subcommands.add_parser("init-db", help="Create or update the database, then report it.")
    init.set_defaults(handler=cmd_init_db)

    args = parser.parse_args()
    raise SystemExit(args.handler(args))
