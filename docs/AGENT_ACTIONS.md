# Agent Actions — FinanceBuy

Date: 2026-01-09

This document lists the edits and CI/agent work performed by the AI assistant during the current session. Use it to reproduce, verify, or roll back changes.

## Summary of changes

- Added repository guidance for AI agents: `.github/copilot-instructions.md` — explains architecture, key files, run/test/build commands, and repo-specific patterns.
- Added CI and lint configuration:
  - `.github/workflows/ci.yml` — GitHub Actions workflow with jobs: `lint`, `tests`, `build`, `tests-in-image`.
  - `pyproject.toml` — `black` and `ruff` basic settings.
- Implemented test support:
  - Added `/docker-compose` endpoint to `backend/app/main.py` to satisfy `backend/tests/test_health.py`.
  - Verified `docker compose exec app bash -lc "pytest -q"` runs locally in this environment.
- Created branch and PR work:
  - Branch: `ci/add-workflows-copilot-instructions` (pushed to `origin`).
  - The user merged changes; a tag `v0.1.0` was created and pushed.

## Files added / modified

- `.github/copilot-instructions.md` — guidance for AI coding agents (architecture, patterns, commands).
- `.github/workflows/ci.yml` — CI pipeline for linting, tests (service containers) and image build + tests-in-image job.
- `pyproject.toml` — lint/format config for `ruff` and `black`.
- `backend/app/main.py` — added `/docker-compose` endpoint used by tests.

## Commands to reproduce or verify locally

- Run the app (dev):

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/financebuy \
  uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Run services and tests inside container (matches CI `tests-in-image` job):

```bash
docker compose up --build -d
docker compose exec app bash -lc "pytest -q"
docker compose down
```

- Run linters locally:

```bash
pip install ruff black
ruff check .
black --check .
```

- Apply migrations (if models change):

```bash
alembic -c backend/alembic.ini revision --autogenerate -m "describe change"
alembic -c backend/alembic.ini upgrade head
```

## CI notes and troubleshooting

- `pyproject.toml` must be valid TOML for `ruff` to parse. If CI reports a parse error, validate the file formatting locally with `python -m tomllib` or re-open it for corrections.
- The `tests` job in CI uses service containers (Postgres + Redis). The `tests-in-image` job uses `docker compose` to build/run services and execute `pytest` inside the `app` container — this validates the Docker wheel-build path.
- The `gh` CLI was not available in the environment when attempting to open a PR; branch pushes were performed and a PR was created/merged manually by the user.

## Next recommended steps

- (Optional) Add format enforcement to CI: run `black --check` and `ruff check` in the same job that fails the PR if formatting is incorrect.
- (Optional) Harden tests: add a matrix job for Python versions, and run tests inside the built image in an isolated runner.
- (Optional) Add `pre-commit` hooks using `ruff` and `black` to catch issues early.

### Pre-commit setup

To enable local checks that run before each commit, install and enable `pre-commit` and the provided hooks:

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

This project provides `.pre-commit-config.yaml` with `black` and `ruff` hooks (the `ruff` hook is configured to attempt automatic fixes).

## Rollback / branch cleanup

- To delete the feature branch locally and remotely:

```bash
git checkout main
git pull
git branch -d ci/add-workflows-copilot-instructions
git push origin --delete ci/add-workflows-copilot-instructions
```

## Contact / follow-up

If anything in this summary is incomplete or you want the document expanded into a PR checklist, tell me which area to expand (CI, tests, migrations or docs) and I'll update this file.
