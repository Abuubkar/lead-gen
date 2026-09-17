# sourcer

Finds small businesses in a trade and a city, enriches them from their own websites, and ranks
them as acquisition targets with the reasoning shown.

Built for the Caprae Capital pre-work challenge. See [PLAN.md](./PLAN.md) for the architecture and
the build order, and [CONTEXT.md](./CONTEXT.md) for the domain vocabulary.

## Quick start

```bash
uv sync
uv run sourcer init-db
```

The second command creates the database and prints the schema it applied. Running it again is
safe and changes nothing.

Full setup and deployment instructions land with step 14 of the build order.
