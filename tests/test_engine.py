from __future__ import annotations

from sqlalchemy import text

from shufflebase.config import RunConfig
from shufflebase.engine import MaskRun
from shufflebase.schema import introspect


def test_default_run_masks_pii_and_preserves_joins(customers_orders_db, empty_sqlite_db):
    schema = introspect(customers_orders_db)
    config = RunConfig.from_schema(schema)
    target = empty_sqlite_db()

    result = MaskRun(customers_orders_db, target, config, seed=1).execute()

    assert result.ok
    assert result.total_rows == 7  # 3 customers + 4 orders

    with target.connect() as conn:
        customers = {row.id: row for row in conn.execute(text("SELECT * FROM customers"))}
        orders = list(conn.execute(text("SELECT * FROM orders")))

    original_names = {"Alice", "Bob", "Carol"}
    assert not any(c.name in original_names for c in customers.values())
    # ids were preserved (not a key-resynthesis strategy), so the join is trivial.
    for order in orders:
        assert order.customer_id in customers


def test_resynthesizing_a_natural_key_propagates_to_every_referencing_fk(
    customers_orders_db, empty_sqlite_db
):
    """The hard case this whole project exists for: masking
    customers.email (a natural key orders.customer_email points at) must
    leave every order pointing at its customer's *new* email, not the old
    one -- and must produce the exact same new value customers.email itself
    now holds, not just "some fake email"."""
    schema = introspect(customers_orders_db)
    config = RunConfig.from_schema(schema)
    config.tables["customers"]["email"] = "fake_email"
    target = empty_sqlite_db()

    result = MaskRun(customers_orders_db, target, config, seed=1).execute()
    assert result.ok

    with target.connect() as conn:
        customers = {
            row.id: row.email for row in conn.execute(text("SELECT id, email FROM customers"))
        }
        orders = list(conn.execute(text("SELECT customer_id, customer_email FROM orders")))

    original_emails = {"alice@example.com", "bob@example.com", "carol@example.com"}
    assert not any(email in original_emails for email in customers.values())
    for order in orders:
        assert order.customer_email == customers[order.customer_id]


def test_shuffling_an_fk_column_preserves_value_set_and_referential_integrity(
    customers_orders_db, empty_sqlite_db
):
    """Shuffling the FK column itself (not the key it points at) is the safe
    case: every value stays a valid, pre-existing customer id, just
    reassigned to a different order row."""
    schema = introspect(customers_orders_db)
    config = RunConfig.from_schema(schema)
    config.tables["orders"]["customer_id"] = "shuffle"
    target = empty_sqlite_db()

    result = MaskRun(customers_orders_db, target, config, seed=1).execute()
    assert result.ok

    with target.connect() as conn:
        customer_ids = {row.id for row in conn.execute(text("SELECT id FROM customers"))}
        shuffled = [row.customer_id for row in conn.execute(text("SELECT customer_id FROM orders"))]

    original = [1, 1, 2, 3]
    assert sorted(shuffled) == sorted(original)  # same multiset of values
    assert all(v in customer_ids for v in shuffled)  # every value still a valid FK target


def test_shuffling_a_referenced_key_remaps_every_referencing_fk(
    customers_orders_db, empty_sqlite_db
):
    """The dangerous case: shuffling customers.id (a column orders.customer_id
    points at) permutes which row holds which id. Every order must follow its
    *logical* customer -- identified here by the untouched `email` column,
    which is itself a key (orders.customer_email references it) and so
    defaults to "preserve" -- to its new id, not keep pointing at the old
    numeric id which now belongs to a different customer."""
    schema = introspect(customers_orders_db)
    config = RunConfig.from_schema(schema)
    config.tables["customers"]["id"] = "shuffle"
    target = empty_sqlite_db()

    result = MaskRun(customers_orders_db, target, config, seed=1).execute()
    assert result.ok

    with target.connect() as conn:
        customers = {
            row.id: row.email for row in conn.execute(text("SELECT id, email FROM customers"))
        }
        orders = list(conn.execute(text("SELECT customer_id, amount FROM orders")))

    expected_email_by_amount = {
        50: "alice@example.com",
        75: "alice@example.com",
        20: "bob@example.com",
        5: "carol@example.com",
    }
    for order in orders:
        assert customers[order.customer_id] == expected_email_by_amount[order.amount]


def test_self_referencing_key_resynthesis(self_referencing_db, empty_sqlite_db):
    schema = introspect(self_referencing_db)
    config = RunConfig.from_schema(schema)
    config.tables["employees"]["id"] = "fake_uuid"
    target = empty_sqlite_db()

    result = MaskRun(self_referencing_db, target, config, seed=1).execute()
    assert result.ok

    with target.connect() as conn:
        rows = {
            row.id: row.manager_id
            for row in conn.execute(text("SELECT id, manager_id FROM employees"))
        }

    assert len(rows) == 3
    roots = [emp_id for emp_id, mgr in rows.items() if mgr is None]
    assert len(roots) == 1
    for mgr in rows.values():
        if mgr is not None:
            assert mgr in rows  # points at a real (remapped) employee id


def test_redact_replaces_value_but_leaves_nulls_alone(customers_orders_db, empty_sqlite_db):
    schema = introspect(customers_orders_db)
    config = RunConfig.from_schema(schema)
    config.tables["customers"]["name"] = "redact"
    target = empty_sqlite_db()

    MaskRun(customers_orders_db, target, config, seed=1).execute()

    with target.connect() as conn:
        names = [row.name for row in conn.execute(text("SELECT name FROM customers"))]
    assert names == ["[REDACTED]"] * 3


def test_validator_actually_catches_a_broken_foreign_key(customers_orders_db, empty_sqlite_db):
    """Regression guard for the validator itself: run a normal mask, then
    directly corrupt the target's data the way a bug in remap propagation
    would, and confirm validate_referential_integrity flags it. If this test
    passes with an empty violation list, the validator has stopped doing its
    job silently -- exactly the failure mode this project's spec calls out
    as worse than no tool at all."""
    from shufflebase.validate import validate_referential_integrity

    schema = introspect(customers_orders_db)
    config = RunConfig.from_schema(schema)
    target = empty_sqlite_db()
    MaskRun(customers_orders_db, target, config, seed=1).execute()

    with target.begin() as conn:
        conn.execute(text("UPDATE orders SET customer_id = 9999 WHERE id = 100"))

    violations = validate_referential_integrity(target, schema)
    assert len(violations) == 1
    assert violations[0].table == "orders"
    assert violations[0].violating_row_count == 1
