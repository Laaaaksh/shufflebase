"""Integration tests against a real MySQL server.

Skipped unless SHUFFLEBASE_TEST_MYSQL_URL is set. CI provides this via a
`mysql:` service container (see .github/workflows/ci.yml); locally:

    docker run --rm -d -p 3306:3306 -e MYSQL_ROOT_PASSWORD=root mysql:8
    export SHUFFLEBASE_TEST_MYSQL_URL=mysql+pymysql://root:root@127.0.0.1:3306/mysql
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from shufflebase.config import RunConfig
from shufflebase.engine import MaskRun
from shufflebase.schema import introspect
from shufflebase.validate import validate_referential_integrity

BASE_URL = os.environ.get("SHUFFLEBASE_TEST_MYSQL_URL")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="SHUFFLEBASE_TEST_MYSQL_URL not set")

SRC_DB = "shufflebase_test_src"
TGT_DB = "shufflebase_test_tgt"


def _db_url(db_name: str) -> str:
    base = BASE_URL.rsplit("/", 1)[0]
    return f"{base}/{db_name}"


@pytest.fixture
def mysql_databases():
    admin = create_engine(BASE_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        for db in (SRC_DB, TGT_DB):
            conn.execute(text(f"DROP DATABASE IF EXISTS {db}"))
            conn.execute(text(f"CREATE DATABASE {db}"))

    src_engine = create_engine(_db_url(SRC_DB))
    with src_engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TABLE customers (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(255) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE orders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                customer_id INT NOT NULL,
                amount INT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
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


def test_mask_run_against_real_mysql(mysql_databases):
    src_engine, tgt_engine = mysql_databases

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
