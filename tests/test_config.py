from __future__ import annotations

import pytest

from shufflebase.config import ConfigError, RunConfig, validate
from shufflebase.schema import introspect


def test_from_schema_suggests_preserve_for_keys_and_fake_for_pii(customers_orders_db):
    schema = introspect(customers_orders_db)
    config = RunConfig.from_schema(schema)
    assert config.tables["customers"]["id"] == "preserve"
    assert config.tables["customers"]["name"] == "fake_name"
    assert config.tables["orders"]["customer_id"] == "preserve"


def test_valid_config_has_no_errors(customers_orders_db):
    schema = introspect(customers_orders_db)
    config = RunConfig.from_schema(schema)
    assert validate(config, schema) == []


def test_redact_on_referenced_key_column_is_rejected(customers_orders_db):
    schema = introspect(customers_orders_db)
    config = RunConfig.from_schema(schema)
    config.tables["customers"]["email"] = "redact"
    errors = validate(config, schema)
    assert any("email" in e and "redact" in e.lower() for e in errors)


def test_fake_strategy_directly_on_foreign_key_column_is_rejected(customers_orders_db):
    schema = introspect(customers_orders_db)
    config = RunConfig.from_schema(schema)
    config.tables["orders"]["customer_email"] = "fake_email"
    errors = validate(config, schema)
    assert any("foreign key" in e for e in errors)


def test_shuffle_foreign_key_under_parent_remap_is_rejected(customers_orders_db):
    schema = introspect(customers_orders_db)
    config = RunConfig.from_schema(schema)
    config.tables["customers"]["email"] = "fake_email"
    config.tables["orders"]["customer_email"] = "shuffle"
    errors = validate(config, schema)
    assert any("shuffle" in e and "resynthesized" in e for e in errors)


def test_shuffle_foreign_key_is_fine_when_parent_key_is_preserved(customers_orders_db):
    schema = introspect(customers_orders_db)
    config = RunConfig.from_schema(schema)
    config.tables["orders"]["customer_id"] = "shuffle"
    assert validate(config, schema) == []


def test_unknown_table_column_and_strategy_are_all_reported(customers_orders_db):
    schema = introspect(customers_orders_db)
    config = RunConfig.from_schema(schema)
    config.tables["nope"] = {"x": "preserve"}
    config.tables["customers"]["ghost"] = "preserve"
    config.tables["customers"]["name"] = "not_a_real_strategy"
    errors = validate(config, schema)
    assert len(errors) == 3


def test_yaml_round_trip(customers_orders_db):
    schema = introspect(customers_orders_db)
    config = RunConfig.from_schema(schema, source="sqlite:///x.db")
    reloaded = RunConfig.from_yaml(config.to_yaml())
    assert reloaded.source == "sqlite:///x.db"
    assert reloaded.tables == config.tables


def test_from_yaml_rejects_non_mapping_top_level():
    with pytest.raises(ConfigError):
        RunConfig.from_yaml("- just\n- a\n- list\n")
