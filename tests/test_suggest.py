from __future__ import annotations

from shufflebase.schema import ColumnInfo, ForeignKeyRef
from shufflebase.suggest import suggest_strategy


def col(name: str, **kwargs) -> ColumnInfo:
    return ColumnInfo(name=name, type_name="TEXT", nullable=True, **kwargs)


def test_key_columns_always_suggest_preserve_regardless_of_name():
    pk = col("email", is_primary_key=True)
    assert suggest_strategy(pk) == "preserve"

    fk = col(
        "customer_email",
        references=ForeignKeyRef(
            table="orders",
            columns=("customer_email",),
            refers_to_table="customers",
            refers_to_columns=("email",),
        ),
    )
    assert suggest_strategy(fk) == "preserve"


def test_email_pattern():
    assert suggest_strategy(col("email")) == "fake_email"
    assert suggest_strategy(col("work_email")) == "fake_email"
    assert suggest_strategy(col("contact_emails")) == "fake_email"


def test_name_patterns_prefer_more_specific_match():
    assert suggest_strategy(col("first_name")) == "fake_first_name"
    assert suggest_strategy(col("last_name")) == "fake_last_name"
    assert suggest_strategy(col("full_name")) == "fake_name"
    assert suggest_strategy(col("name")) == "fake_name"


def test_sensitive_columns_suggest_redact():
    assert suggest_strategy(col("password")) == "redact"
    assert suggest_strategy(col("ssn")) == "redact"
    assert suggest_strategy(col("credit_card_number")) == "redact"
    assert suggest_strategy(col("api_key")) == "redact"


def test_unrecognized_column_name_defaults_to_preserve():
    assert suggest_strategy(col("amount")) == "preserve"
    assert suggest_strategy(col("created_at")) == "preserve"
