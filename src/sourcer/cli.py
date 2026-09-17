"""Command line entry point."""

import argparse

from sourcer.db import index_names, init_db, table_names
from sourcer.paths import db_path


def cmd_init_db(_args):
    path = db_path()
    connection = init_db()
    try:
        tables = table_names(connection)
        indexes = index_names(connection)
    finally:
        connection.close()

    print(f"database: {path}")
    print(f"tables ({len(tables)}): {', '.join(tables)}")
    print(f"indexes ({len(indexes)}): {', '.join(indexes)}")
    return 0


def main():
    parser = argparse.ArgumentParser(prog="sourcer", description="Acquisition target sourcing.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    init = subcommands.add_parser("init-db", help="Create or update the database, then report it.")
    init.set_defaults(handler=cmd_init_db)

    args = parser.parse_args()
    raise SystemExit(args.handler(args))
