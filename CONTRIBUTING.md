# Contributing

Limen is Apache-2.0 and open to contributions. Bug reports, feature
PRs, documentation fixes — all welcome.

## Dev setup

```bash
# Tooling: Python 3.12 + uv + Node 22 (frontend) + Docker (integration tests)
uv sync --all-groups
uv run pre-commit install

# Frontend
cd frontend && npm ci
```

## The gate before pushing

```bash
# Backend
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
uv run pytest --cov=limen -q

# Frontend
( cd frontend && npm run lint && npm test && npm run build )
```

CI runs the same gate on every PR (see
[`.github/workflows/ci.yml`](./.github/workflows/ci.yml)). Coverage
must stay ≥ 80%.

## Commit style

[Conventional Commits](https://www.conventionalcommits.org/), e.g.

```
feat(notifications): add Telegram dispatcher
fix(scoring): clamp soil-moisture sigmoid input to [0, 1]
docs(deployment): add Azure Container Apps walkthrough
test(scoring): cover the Caine excess monotonicity property
chore(deps): bump pydantic to 2.10
```

Conventional Commits is enforced by reviewer + the changelog
generator, not by a hook. Keep first line ≤ 72 chars; use the body
for context.

## What we *don't* accept

* New runtime dependencies without an explicit justification in the
  PR description.
* Changes to applied migration files. **Always add a new migration**
  — the migration runner verifies the SHA-256 checksum of every
  applied file.
* Magic numbers inside the scoring engine code (must land in
  [`regional_thresholds.yaml`](./src/limen/config/regional_thresholds.yaml)).
* Endpoints with business logic. Endpoints call workflows / repos.
* `print()` — use `structlog.get_logger(__name__)`.

## Architecture invariants

Skim [`docs/architecture.md`](./docs/architecture.md) and
[`CLAUDE.md`](./CLAUDE.md) before touching anything load-bearing.
The "Locked invariants" table in CLAUDE.md is the binding contract.

## Where to start

* Browse open issues tagged
  [`good first issue`](https://github.com/agent-engineering-studio/limen/labels/good%20first%20issue).
* Read [`docs/scoring-model.md`](./docs/scoring-model.md) to understand
  the V1 engine.
* Try `make demo` to bring the whole stack up locally.

## Code of conduct

Be respectful. Disagree with the idea, not the person. The
[Contributor Covenant 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/)
applies to all spaces (issues, PRs, discussions, chat).

## Releases

* Versions follow [SemVer](https://semver.org/).
* `CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/).
* Tagged releases trigger the CI image push to GHCR; deploys are
  manual via the `deploy-aruba` / `deploy-azure` workflows.
