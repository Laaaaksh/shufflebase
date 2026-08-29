"""Integration tests against a real Postgres server.

Skipped unless SHUFFLEBASE_TEST_POSTGRES_URL is set. CI provides this via a
`postgres:` service container (see .github/workflows/ci.yml); locally, point
it at a disposable database, e.g.:

    docker run --rm -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:16-alpine
    export SHUFFLEBASE_TEST_POSTGRES_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres

The test creates its own source/target databases on the given server and
drops them afterwards -- it never touches an existing database's tables.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from shufflebase.config import RunConfig
from shufflebase.engine import MaskRun
from shufflebase.schema import introspect
from shufflebase.validate import validate_referential_integrity

BASE_URL = os.environ.get("SHUFFLEBASE_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="SHUFFLEBASE_TEST_POSTGRES_URL not set")

SRC_DB = "shufflebase_test_src"
TGT_DB = "shufflebase_test_tgt"


def _admin_engine():
    return create_engine(BASE_URL, isolation_level="AUTOCOMMIT")


def _db_url(db_name: str) -> str:
    base = BASE_URL.rsplit("/", 1)[0]
    return f"{base}/{db_name}"


@pytest.fixture
def pg_databases():
    admin = _admin_engine()
    with admin.connect() as conn:
        for db in (SRC_DB, TGT_DB):
            conn.execute(text(f"DROP DATABASE IF EXISTS {db}"))
            conn.execute(text(f"CREATE DATABASE {db}"))

    src_engine = create_engine(_db_url(SRC_DB))
    with src_engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE customers (
                id SERIAL PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE orders (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER NOT NULL REFERENCES customers(id),
                amount NUMERIC NOT NULL
            )
        """)
        )
        conn.execute(
            text(
                "INSERT INTO customers (email, name) VALUES "
                "('alice@example.com', 'Alice'), ('bob@example.com', 'Bob')"
            )
        )
        conn.execute(
            text("INSERT INTO orders (customer_id, amount) VALUES (1, 50), (1, 75), (2, 20)")
        )

    tgt_engine = create_engine(_db_url(TGT_DB))
    yield src_engine, tgt_engine

    src_engine.dispose()
    tgt_engine.dispose()
    with admin.connect() as conn:
        for db in (SRC_DB, TGT_DB):
            conn.execute(text(f"DROP DATABASE IF EXISTS {db}"))


def test_mask_run_against_real_postgres(pg_databases):
    src_engine, tgt_engine = pg_databases

    schema = introspect(src_engine)
    config = RunConfig.from_schema(schema)
    config.tables["customers"]["email"] = "fake_email"

    result = MaskRun(src_engine, tgt_engine, config, seed=1).execute()
    assert result.ok
    assert result.total_rows == 5

    with tgt_engine.connect() as conn:
        customers = {
            row.id: row.email for row in conn.execute(text("SELECT id, email FROM customers"))
        }
        names = [row.name for row in conn.execute(text("SELECT name FROM customers"))]

    assert set(customers.values()).isdisjoint({"alice@example.com", "bob@example.com"})
    assert set(names).isdisjoint({"Alice", "Bob"})

    tgt_schema = introspect(tgt_engine)
    assert validate_referential_integrity(tgt_engine, tgt_schema) == []
