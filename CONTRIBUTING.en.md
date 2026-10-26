# Contributing

> Last updated: 2026-10-26 · 简体中文: [CONTRIBUTING.md](CONTRIBUTING.md)

## Development Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
make install
cp config.local.example .env.local
```

Python 3.12+; dependencies follow `requirements.txt` / `requirements.lock`.
See [QUICKSTART.en.md](QUICKSTART.en.md) for details.

## Pre-Submit Checks

Run **`make gates`** before merging (single chain, not concurrently with other pytest runs).
It chains:

- `make lint` / `make format` / `make typecheck`
- `make test` (same caliber as CI)
- `make docs-check` / `make doc-commands` / `make baseline-check`
- Registry, flag effectiveness, repository hygiene, and bibliography gates

A subset is not sufficient evidence: the gates depend on each other (for example, the gate
count and flag-instance count must agree).

## Documentation Conventions

- **One source for numbers**: test, coverage, and static-check readings live in
  `BASELINE.yaml`; other documents point to it instead of copying counts.
- **Archive superseded content; do not annotate in place**: move historical narrative to
  `docs/history/` and keep current documents concise.
- **Bilingual pairs**: `foo.md` ↔ `foo.en.md`; the `最后更新 / Last updated` dates must match
  and the section counts may differ by at most 2.
- **Commands in code blocks must exist**: `make` targets and `scripts/*.py` paths are checked
  by `make doc-commands`.
- Do not put a bare `|` inside inline code in a table row (GFM splits the cell and silently
  drops content).

## Pull Requests

- One concern per PR; state the change type in the title (feat / fix / docs / test / chore).
- Behavior changes need tests; bug fixes start with a reproduction test.
- Do not commit keys, `.env.local`, private directories, or run residue; run
  `make repo-hygiene` before submitting.
- In the PR description, state the motivation, what changed, and how it was verified
  (commands and readings).
