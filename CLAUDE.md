# lead-gen (sourcer)

A sourcing tool for search-fund principals: it discovers small businesses in a trade and a city,
enriches them from their own websites, and ranks them as acquisition targets with the reasoning
shown. Built for the Caprae Capital pre-work challenge.

Read [PLAN.md](./PLAN.md) for the architecture, the scoring rubric and the build order.

## Ground rules

- `uv` manages the environment and the lockfile. Never install globally.
- Add a package at the step that first imports it, never in advance.
- No test files and no test framework.
- No type hints.
- `ruff` is the only development dependency.

## Agent skills

### Issue tracker

Issues live as GitHub issues in `Abuubkar/lead-gen`, driven through the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and one `docs/adr/` at the repo root. See `docs/agents/domain.md`.
