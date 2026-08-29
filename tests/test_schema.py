from __future__ import annotations

import pytest

from shufflebase.schema import (
    CircularForeignKeyError,
    ColumnInfo,
    ForeignKeyRef,
    SchemaGraph,
    TableInfo,
    introspect,
)


def test_introspect_detects_tables_columns_and_foreign_key(customers_orders_db):
    schema = introspect(customers_orders_db)

    assert set(schema.tables) == {"customers", "orders"}

    customers = schema.tables["customers"]
    assert customers.columns["id"].is_primary_key
    assert customers.columns["id"].is_referenced  # orders.customer_id points here
    assert customers.columns["email"].is_referenced  # orders.customer_email points here
    assert not customers.columns["name"].is_referenced

    orders = schema.tables["orders"]
    fk = orders.columns["customer_id"].references
    assert fk is not None
    assert fk.refers_to_table == "customers"
    assert fk.refers_to_columns == ("id",)
    assert orders.columns["amount"].references is None


def test_topological_order_puts_parents_before_children(customers_orders_db):
    schema = introspect(customers_orders_db)
    order = schema.topological_order()
    assert order.index("customers") < order.index("orders")


def test_self_referencing_table_is_not_a_cycle(self_referencing_db):
    schema = introspect(self_referencing_db)
    # Must not raise, and the table appears exactly once.
    order = schema.topological_order()
    assert order == ["employees"]
    fk = schema.tables["employees"].columns["manager_id"].references
    assert fk is not None
    assert fk.is_self_referencing


def _pk(name: str) -> ColumnInfo:
    return ColumnInfo(name=name, type_name="INTEGER", nullable=False, is_primary_key=True)


def _fk_column(name: str, fk: ForeignKeyRef) -> ColumnInfo:
    return ColumnInfo(name=name, type_name="INTEGER", nullable=True, references=fk)


def test_circular_foreign_key_across_tables_raises():
    fk_a_to_b = ForeignKeyRef(
        table="a", columns=("b_id",), refers_to_table="b", refers_to_columns=("id",)
    )
    fk_b_to_a = ForeignKeyRef(
        table="b", columns=("a_id",), refers_to_table="a", refers_to_columns=("id",)
    )
    graph = SchemaGraph(
        tables={
            "a": TableInfo(
                name="a",
                columns={"id": _pk("id"), "b_id": _fk_column("b_id", fk_a_to_b)},
                primary_key=("id",),
                foreign_keys=[fk_a_to_b],
            ),
            "b": TableInfo(
                name="b",
                columns={"id": _pk("id"), "a_id": _fk_column("a_id", fk_b_to_a)},
                primary_key=("id",),
                foreign_keys=[fk_b_to_a],
            ),
        }
    )
    with pytest.raises(CircularForeignKeyError):
        graph.topological_order()
