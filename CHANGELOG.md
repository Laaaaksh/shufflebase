# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `shuffle`-ing a primary key or a natural key another table's foreign key
  points at no longer silently reassigns referencing rows to the wrong
  logical parent. The permutation now builds the same stable remap a
  resynthesized key gets, so every referencing foreign key column follows it.
  Previously this passed `result.ok` and "All foreign keys resolve
  correctly" while every join returned the wrong parent row.
- README's `Usage` examples now use dialect-qualified connection URLs
  (`postgresql+psycopg://`, `mysql+pymysql://`) instead of bare
  `postgresql://`/`mysql://`, which fail with a `ModuleNotFoundError` because
  neither default DBAPI driver is installed by the `postgres`/`mysql` extras.

## [0.1.0] - 2026-08-29

### Added

- Schema introspection for Postgres and MySQL via SQLAlchemy reflection:
  tables, columns, primary keys, and foreign keys (including composite and
  self-referencing keys).
- Per-column masking/synthesis strategies (`preserve`, `redact`, `shuffle`,
  and a set of `fake_*` strategies backed by Faker), with column-name-based
  auto-suggestion.
- A masking engine that preserves referential integrity: resynthesizing a
  primary key or a natural key another table's foreign key points at
  produces a stable remap applied consistently everywhere that key is
  referenced.
- Config validation that rejects unsafe strategy combinations (e.g. `redact`
  on a referenced key, `shuffle` on a foreign key under a resynthesized
  parent) before any run starts, plus circular-foreign-key detection.
- A post-run validation pass that queries the target database directly and
  refuses to report success if any foreign key fails to resolve.
- CLI (`shufflebase introspect` / `run` / `validate` / `serve`).
- An optional self-hosted web dashboard (`shufflebase serve`) for
  reviewing/editing strategies and running a mask from a browser.

[Unreleased]: https://github.com/Laaaaksh/shufflebase/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Laaaaksh/shufflebase/releases/tag/v0.1.0
