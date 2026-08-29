# Contributing

## Getting set up

```sh
git clone https://github.com/Laaaaksh/shufflebase.git
cd shufflebase
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,postgres,mysql,web]"
```

## Build / run / test / lint

```sh
make test    # unit tests (SQLite-backed, no external services needed)
make lint    # ruff + mypy
make format  # ruff --fix + format
make run     # start the web dashboard on http://127.0.0.1:8642
```

The Postgres and MySQL integration tests in `tests/test_integration_*.py`
are skipped unless `SHUFFLEBASE_TEST_POSTGRES_URL` / `SHUFFLEBASE_TEST_MYSQL_URL`
are set. To run them locally:

```sh
docker run --rm -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:16-alpine
docker run --rm -d -p 3306:3306 -e MYSQL_ROOT_PASSWORD=root mysql:8
export SHUFFLEBASE_TEST_POSTGRES_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres
export SHUFFLEBASE_TEST_MYSQL_URL=mysql+pymysql://root:root@127.0.0.1:3306/mysql
make test
```

CI runs all three (SQLite, Postgres, MySQL) on every PR via service
containers — see `.github/workflows/ci.yml`.

## Workflow

- `main` is protected. Every change lands through a pull request.
- Required checks (must be named exactly this in your PR): `test`, `lint`.
- Run `make lint` and `make test` locally before opening a PR — CI runs the
  same commands, so a failure there is a failure here first.
- Add a bullet to `CHANGELOG.md` under `## [Unreleased]` for any user-facing
  change (new strategy, CLI flag, behavior change, bug fix). Internal
  refactors with no user-visible effect don't need one.

## Code style

- `ruff` enforces formatting and import order; `make format` applies it.
- Every module and every non-obvious function has a docstring explaining
  *why*, not what — the code already says what. If you can't say why a line
  exists that a future reader would find non-obvious, don't add a comment for
  it.
- New masking strategies go in `strategies.py`'s `STRATEGIES` registry and
  must handle `None` (pass it through unchanged — see the existing
  strategies for the pattern). If the strategy could plausibly be applied to
  a primary key or a column another table's foreign key points at, think
  through whether it needs to be excluded from `KEY_SAFE_STRATEGIES` in the
  same file (anything that can't guarantee unique output per input, the way
  `redact` can't, does).
- Anything that touches `engine.py`'s remap/propagation logic needs a test
  that actually runs a mask and checks the *target database's* foreign keys
  resolve (see `tests/test_engine.py`) — not just that the code path was
  exercised. A masking tool's tests exist to catch silent data corruption;
  an assertion that doesn't check real output data isn't testing the thing
  that matters.

## Release procedure

1. Move the `## [Unreleased]` entries in `CHANGELOG.md` under a new
   `## [x.y.z] - YYYY-MM-DD` heading.
2. Bump the `version` in `pyproject.toml` to match.
3. Commit, merge to `main`.
4. Tag the merge commit `vx.y.z` and push the tag: `git tag vx.y.z && git push origin vx.y.z`.
5. `.github/workflows/release.yml` builds the package and publishes a GitHub
   Release with notes pulled from that version's `CHANGELOG.md` section. A
   tag with no matching changelog section fails the release rather than
   publishing empty notes.
