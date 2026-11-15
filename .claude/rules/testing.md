---
paths:
  - "tests/**"
  - ".github/**"
  - "Makefile"
  - "pyproject.toml"
---

# Quality gate e test

Testo completo degli invarianti di cui `CLAUDE.md` tiene solo la riga breve:
la regola e il perché (misure, incidenti, issue). Vincolanti quanto la tabella.

| Topic | Rule |
|-------|------|
| Quality gates | `ruff check` + `ruff format` clean, `mypy --strict` clean, `pytest` green before commit. **The gate is `make check`** (lint + typecheck + `pytest --cov=limen`, coverage ≥ 80 %); in CI it is split so a slow suite cannot hide a lint failure (#90): `backend` runs lint + types + `tests/unit` as the fast gate on every PR, `integration` runs the whole suite with the coverage threshold, and `slow` runs the national-seed tests on `main` only. Tests marked `slow` are **deselected by default** (`addopts` carries `-m 'not slow'`) — run them with `make test-slow`. An integration test that needs an AOI seeds **one** with `run_seed(only=[SEED_SMALL_AOI])`: seeding the twenty regions is ~312,000 cells and twenty minutes, and it is what kept the CI red from July to September without a single test actually failing. |
