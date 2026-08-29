from __future__ import annotations

import pytest
from sqlalchemy import Engine, create_engine, text


@pytest.fixture
def make_sqlite_db(tmp_path):
    """Factory fixture: make_sqlite_db(name, ddl_and_data_sql) -> Engine.

    Each call gets its own file-backed SQLite database under tmp_path, so
    source and target databases in the same test are genuinely independent.
    """
    counter = {"n": 0}

    def _make(statements: list[str]) -> Engine:
        counter["n"] += 1
        path = tmp_path / f"db_{counter['n']}.sqlite"
        engine = create_engine(f"sqlite:///{path}")
        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys=ON"))
            for stmt in statements:
                conn.execute(text(stmt))
        return engine

    return _make


@pytest.fixture
def empty_sqlite_db(tmp_path):
    """A fresh, empty SQLite database file for use as a masking target."""
    counter = {"n": 0}

    def _make() -> Engine:
        counter["n"] += 1
        path = tmp_path / f"target_{counter['n']}.sqlite"
        return create_engine(f"sqlite:///{path}")

    return _make


CUSTOMERS_ORDERS_SCHEMA = [
    """
    CREATE TABLE customers (
        id INTEGER PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE orders (
        id INTEGER PRIMARY KEY,
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        customer_email TEXT NOT NULL REFERENCES customers(email),
        amount INTEGER NOT NULL
    )
    """,
    "INSERT INTO customers (id, email, name) VALUES (1, 'alice@example.com', 'Alice')",
    "INSERT INTO customers (id, email, name) VALUES (2, 'bob@example.com', 'Bob')",
    "INSERT INTO customers (id, email, name) VALUES (3, 'carol@example.com', 'Carol')",
    "INSERT INTO orders (id, customer_id, customer_email, amount) "
    "VALUES (100, 1, 'alice@example.com', 50)",
    "INSERT INTO orders (id, customer_id, customer_email, amount) "
    "VALUES (101, 1, 'alice@example.com', 75)",
    "INSERT INTO orders (id, customer_id, customer_email, amount) "
    "VALUES (102, 2, 'bob@example.com', 20)",
    "INSERT INTO orders (id, customer_id, customer_email, amount) "
    "VALUES (103, 3, 'carol@example.com', 5)",
]


@pytest.fixture
def customers_orders_db(make_sqlite_db):
    return make_sqlite_db(CUSTOMERS_ORDERS_SCHEMA)


SELF_REFERENCING_SCHEMA = [
    """
    CREATE TABLE employees (
        id TEXT PRIMARY KEY,
        manager_id TEXT REFERENCES employees(id),
        name TEXT NOT NULL
    )
    """,
    "INSERT INTO employees (id, manager_id, name) VALUES ('e1', NULL, 'Carol')",
    "INSERT INTO employees (id, manager_id, name) VALUES ('e2', 'e1', 'Dave')",
    "INSERT INTO employees (id, manager_id, name) VALUES ('e3', 'e1', 'Eve')",
]


@pytest.fixture
def self_referencing_db(make_sqlite_db):
    return make_sqlite_db(SELF_REFERENCING_SCHEMA)
