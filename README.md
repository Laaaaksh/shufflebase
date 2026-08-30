<p align="center">
  <img src="docs/assets/banner.svg" alt="shufflebase" width="640" />
</p>

**shufflebase generates realistic, referentially-consistent staging data from a real Postgres or MySQL schema — masking or resynthesizing sensitive columns while keeping every foreign key valid, self-hosted with no data ever leaving your infrastructure.**

<p align="center">
  <a href="https://github.com/Laaaaksh/shufflebase/stargazers"><img src="https://img.shields.io/github/stars/Laaaaksh/shufflebase?style=for-the-badge&color=yellow&label=Star%20this%20repo" alt="Star this repo" /></a>
</p>

<p align="center">
  <a href="https://github.com/Laaaaksh/shufflebase/actions/workflows/ci.yml"><img src="https://github.com/Laaaaksh/shufflebase/actions/workflows/ci.yml/badge.svg" alt="CI status" /></a>
  <a href="https://github.com/Laaaaksh/shufflebase/releases"><img src="https://img.shields.io/github/v/release/Laaaaksh/shufflebase?include_prereleases" alt="Latest release" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/Laaaaksh/shufflebase" alt="License" /></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+" /></a>
  <a href="#requirements"><img src="https://img.shields.io/badge/database-postgres%20%7C%20mysql-336791" alt="Postgres and MySQL" /></a>
</p>

<p align="center">
  <a href="#demo">Demo</a> ·
  <a href="#install">Install</a> ·
  <a href="#usage">Usage</a> ·
  <a href="#configuration">Configuration</a> ·
  <a href="CHANGELOG.md">Changelog</a> ·
  <a href="CONTRIBUTING.md">Contributing</a> ·
  <a href="#license">License</a>
  <br />
  <a href="CODE_OF_CONDUCT.md">Code of conduct</a> ·
  <a href="SECURITY.md">Security</a>
</p>

## Demo

<p align="center">
  <img src="docs/assets/demo.gif" alt="Connecting shufflebase to a live Postgres database, reviewing suggested masking strategies, running a mask, and confirming referential integrity survived" width="720" />
</p>

The clip shows `shufflebase serve` against a live Postgres database with a `customers` → `orders` → `order_items` schema: introspecting the schema, reviewing (and hand-correcting) the suggested masking strategies, running a mask, and then the real before/after rows in both databases proving the masked emails/phones are unreadable while every foreign key still resolves.

Full quality: [docs/assets/demo.mp4](docs/assets/demo.mp4). Re-record it yourself with `make demo` (see [scripts/record-demo](scripts/record-demo/README.md)).

## What it does

- Reflects a Postgres or MySQL database's tables, columns, and foreign keys automatically — no manual schema re-entry.
- Suggests a masking strategy per column from its name (`email` → fake email, `ssn` → redact, an unrecognized column → left alone), pre-filled into an editable config.
- **Preserves referential integrity when a key changes.** Resynthesizing `customers.email` produces a stable remap applied to every other table's foreign key into it — `orders.customer_email` gets the exact same new value, not just "some fake email."
- Refuses to call a run successful without proof: after writing the target database, it queries that database directly to confirm every foreign key still resolves, and reports which ones don't rather than silently shipping a broken join.
- Runs from a CLI (scriptable into a "refresh staging from prod" pipeline) or a small self-hosted web dashboard for reviewing strategies by hand.
- Self-hosted only. Your database URL and its data never leave the process you run this in — there's no cloud service to opt out of.

## Why not just use Tonic.ai or a find-and-replace script?

Tonic Structural does this well, but it's quote-priced enterprise software, and it means giving a third party read access to (or a copy of) your production schema. A hand-rolled masking script is free but naive: it doesn't know that `orders.customer_id` needs to change in lockstep with `customers.id`, so the first schema with a real foreign key breaks it. [Microsoft Presidio](https://github.com/microsoft/presidio) is the mature open-source answer for redacting PII in free text, but that's a different problem — detecting a name inside a paragraph, not resynthesizing a whole relational schema's keys. Shufflebase is scoped narrowly to the piece those don't cover: schema-aware, referential-integrity-preserving masking of a real database, self-hosted.

## Requirements

- Python 3.10+
- A Postgres or MySQL database you can read from, and a database to write the masked copy to (a second database on the same server works fine)

## Install

From source (this is the only install path today — shufflebase isn't
published on PyPI yet, see [CONTRIBUTING.md](CONTRIBUTING.md#release-procedure)):

```sh
git clone https://github.com/Laaaaksh/shufflebase.git
cd shufflebase
pip install -e ".[postgres,mysql]"   # or just one of postgres/mysql
```

## Usage

No database handy? `examples/demo/seed.sql` creates the `customers`/`orders`/
`order_items` schema shown in the demo below — load it into a scratch
Postgres database and point the commands below at it to follow along with
real output.

Detect your schema and get a config pre-filled with suggested strategies:

```sh
shufflebase introspect --source postgresql+psycopg://user:pass@host/proddb -o config.yaml
```

(Use `mysql+pymysql://user:pass@host/proddb` for MySQL. The `+psycopg`/`+pymysql`
part tells SQLAlchemy which driver to use — it's what the `postgres`/`mysql`
extras above actually install; a bare `postgresql://` or `mysql://` URL falls
back to a driver that isn't installed and fails with a confusing
`ModuleNotFoundError`.)

Open `config.yaml`, adjust any strategy you don't like, then run it:

```sh
shufflebase run --config config.yaml --target postgresql+psycopg://user:pass@host/staging
```

```
Masking run complete
┏━━━━━━━━━━━┳━━━━━━┓
┃ Table     ┃ Rows ┃
┡━━━━━━━━━━━╇━━━━━━┩
│ customers │    3 │
│ orders    │    4 │
└───────────┴──────┘
7 rows written across 2 tables.
All foreign keys resolve correctly.
```

Check any database's foreign keys independently, at any time:

```sh
shufflebase validate --target postgresql+psycopg://user:pass@host/staging
```

Prefer a browser? `pip install -e ".[web]"` then `shufflebase serve` starts a dashboard on `http://127.0.0.1:8642` with the same connect → review → run flow shown in the GIF above. (Port 8642 needs to be free — if something else is already listening on it, stop that process or run `shufflebase serve --port <other-port>`.)

<p align="center">
  <img src="docs/assets/screenshot-result.png" alt="The dashboard's Run step: a completed masking run showing rows written per table and a green 'All foreign keys resolve correctly' confirmation." width="640" />
</p>

## Configuration

`config.yaml` maps each column to a strategy:

```yaml
source: postgresql+psycopg://user:pass@host/proddb
target: postgresql+psycopg://user:pass@host/staging
seed: 42   # optional, for reproducible fake data across runs
tables:
  customers:
    id: preserve
    email: fake_email
    full_name: fake_name
  orders:
    id: preserve
    customer_id: preserve   # a foreign key column; inherits customers.id automatically
```

**Strategies:** `preserve` (leave as-is), `redact` (fixed placeholder), `shuffle` (permute existing values across rows in the same column — keeps the real distribution, breaks the link to the original row), and a set of `fake_*` strategies (`fake_name`, `fake_email`, `fake_phone`, `fake_address`, `fake_company`, `fake_date_of_birth`, `fake_uuid`, `fake_credit_card`, ...) backed by [Faker](https://faker.readthedocs.io/).

**Rules the config validator enforces before any run starts** — these exist because they're exactly the ways a masking config can silently break joins:

- A foreign key column can only be `preserve` or `shuffle`; it inherits whatever its parent key does rather than being masked independently.
- A primary key or a column another table's foreign key points at can be anything except `redact` (collapsing every value to the same placeholder breaks the uniqueness a key relies on).
- You can't `shuffle` a foreign key column whose parent key is itself being resynthesized — that would leave shuffled values pointing at keys that no longer exist.
- Composite primary/foreign keys support `preserve` and `shuffle` only in v1 (see Limitations).

## Limitations (v1)

- **Postgres and MySQL only.** No NoSQL/document databases.
- **Loads each table into memory during a run.** Fine for a typical staging-sized database; not built for masking a multi-hundred-GB table in one pass yet.
- **Composite primary/foreign keys** support `preserve`/`shuffle` only — resynthesizing a composite key isn't implemented yet.
- **A foreign key cycle spanning more than one table** (A references B, B references A) is detected and rejected rather than guessed at; a table referencing itself (e.g. `employees.manager_id`) is fully supported.
- **Masks or resynthesizes from an existing schema + data** — it doesn't generate a plausible database from nothing.
- Unstructured text (a free-form `notes` column with a name buried in a sentence) isn't scanned for PII — pair this with [Presidio](https://github.com/microsoft/presidio) for that if you need it.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the dev setup, test/lint commands, and release process.

## Security

See [SECURITY.md](SECURITY.md). In short: this tool is meant to be run by a trusted operator against infrastructure they control, never exposed on a public network.

## Star this repo

If shufflebase saved you from either a Tonic.ai invoice or a broken staging database, a star helps other people find it: [github.com/Laaaaksh/shufflebase/stargazers](https://github.com/Laaaaksh/shufflebase/stargazers).

## License

[MIT](LICENSE)
