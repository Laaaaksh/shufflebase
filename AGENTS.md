# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Dev setup, test/lint commands, and release procedure: see [CONTRIBUTING.md](CONTRIBUTING.md) — don't duplicate them here.
- Product spec and scope decisions: `README.md`'s "Why not just use Tonic.ai" and "Limitations (v1)" sections carry the reasoning; this file is for things not already written down there.

## Architecture

- `src/shufflebase/schema.py` reflects a live database into a `SchemaGraph` (tables, columns, FKs) via SQLAlchemy. `reflect_metadata()`/`build_schema_graph()` are split out so `engine.py` can reuse the same reflected `MetaData` for actual row I/O instead of reflecting twice.
- `strategies.py` holds the `STRATEGIES` registry (name -> callable) plus the two "which strategies are safe here" sets: `KEY_SAFE_STRATEGIES` (no `redact` — collapsing values breaks uniqueness) and `FK_COLUMN_STRATEGIES` (`preserve`/`shuffle` only — a foreign key column always inherits its parent, never masks independently).
- `config.py`'s `validate()` is the single source of truth for which strategy/column combinations are legal; both the CLI and the web API call it, and `engine.py` calls it again right before running (never trust a config it didn't just re-validate against the live schema).
- `engine.py`'s `MaskRun` is the only place remap propagation happens: resynthesizing a key builds a stable old->new dict once, then every FK column pointing at that key gets the same dict applied, regardless of that FK column's own (preserve-only) config. Self-referencing FKs work because a table's own remap is built before its own rows are transformed, in the same pass.
- `validate.py` re-queries the *target database itself* for FK integrity after a run — it does not trust `engine.py`'s bookkeeping. This is deliberate: a bug in remap logic should still get caught by asking the database directly.
- The web UI (`src/shufflebase/web/`) is hand-written vanilla JS/CSS served as static files by FastAPI, not a separate Node build — this keeps `pip install shufflebase[web]` + `shufflebase serve` a single self-hosted command with no build step. `cli.py`'s `serve` command imports it lazily so the CLI works without the `web` extra installed.

## Sharp edges (bugs already hit once — don't reintroduce)

- SQLAlchemy reflects identifiers as `quoted_name` (a `str` subclass). PyYAML's exact-type dispatch can't represent it and fails with a confusing `RepresenterError`. `schema.py` casts every reflected name to plain `str` at the source — do this for any new reflected identifier, don't rely on `str` subclassing behaving like `str`.
- A self-referencing foreign key (parent and child are the *same* `Table` object) breaks a naive correlated `EXISTS` subquery: SQLAlchemy's auto-correlation collapses it into comparing each row against itself. `validate.py` aliases the parent table (`.alias()`) specifically to avoid this — keep that alias if touching that query.
- Composite primary/foreign keys are deliberately restricted to `preserve`/`shuffle` in `config.py`'s `validate()` (remapping a tuple key isn't implemented). If you add composite-key remap support, the composite-only checks in `validate()` and the single-column assumption in `engine.py`'s `_build_key_remaps`/`_transform_rows` both need updating together.

## Testing

- `tests/test_integration_postgres.py` and `tests/test_integration_mysql.py` are real-database tests, skipped unless `SHUFFLEBASE_TEST_POSTGRES_URL`/`SHUFFLEBASE_TEST_MYSQL_URL` are set (CI sets them via service containers; see `.github/workflows/ci.yml`). Everything else runs against file-backed SQLite via `tests/conftest.py` fixtures.
- Any change to `engine.py`'s remap/propagation logic needs a test that reads back the *target database's* actual rows and checks FK values match, not just that `result.ok` is true — `tests/test_engine.py::test_validator_actually_catches_a_broken_foreign_key` exists specifically to guard against the validator itself going quiet.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
