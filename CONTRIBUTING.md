# Contributing

Limen is licensed under the [EUPL-1.2](./LICENSE) and open to
contributions. Bug reports, feature PRs, documentation fixes — all
welcome. Code contributions require accepting the
[Contributor License Agreement](#contributor-license-agreement) below.

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

## Contributor License Agreement

Limen is distributed under the EUPL-1.2 and, for uses the copyleft does
not fit, under a separate commercial licence. Offering both requires the
maintainer to be able to license every line of the project, so each
code contribution is accepted under the following terms.

By submitting a contribution (code, documentation, configuration, data)
to this repository, you agree that:

1. **You keep the copyright.** This agreement grants a licence; it does
   not transfer ownership of your contribution.
2. **Copyright licence.** You grant Giuseppe Zileni, as maintainer of
   Limen, and any successor to whom the rights in the Limen project are
   transferred (the "Maintainer"), a perpetual, worldwide,
   non-exclusive, no-charge, royalty-free, irrevocable licence to
   reproduce, modify, prepare derivative works of, publicly display,
   publicly perform, sublicense and distribute your contribution and
   such derivative works, **under any licence terms, including the
   EUPL-1.2 and proprietary or commercial terms**.
3. **Patent licence.** You grant the Maintainer and recipients of the
   software a perpetual, worldwide, non-exclusive, no-charge,
   royalty-free, irrevocable patent licence to make, use, sell, offer
   for sale, import and otherwise transfer your contribution, limited to
   the patent claims you can license that are necessarily infringed by
   your contribution alone or combined with the project.
4. **You have the right to contribute.** The contribution is your
   original work, or you have the right to submit it under these terms.
   If your employer has rights to intellectual property you create, you
   have received permission to contribute on its behalf, or your
   employer has waived those rights for this contribution.
5. **The project stays open.** Every contribution accepted into the
   repository is also published under the EUPL-1.2.
6. **No warranty.** Unless required by law, you provide your
   contribution "as is", without warranties or conditions of any kind.

To accept, include this line in the description of your first pull
request:

```
I have read the Contributor License Agreement in CONTRIBUTING.md and I accept it.
```

The acceptance covers that pull request and every later contribution
you make to Limen. Pull requests without it are not merged.

## Code of conduct

Be respectful. Disagree with the idea, not the person. The
[Contributor Covenant 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/)
applies to all spaces (issues, PRs, discussions, chat).

## Releases

* Versions follow [SemVer](https://semver.org/).
* `CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/).
* Tagged releases trigger the CI image push to GHCR; deploys are
  manual via the `deploy-aruba` / `deploy-azure` workflows.
