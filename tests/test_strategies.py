from __future__ import annotations

from faker import Faker

from shufflebase.strategies import (
    FK_COLUMN_STRATEGIES,
    KEY_SAFE_STRATEGIES,
    STRATEGIES,
    PreserveStrategy,
    RedactStrategy,
)


def test_preserve_returns_value_unchanged():
    strategy = PreserveStrategy()
    faker = Faker()
    assert strategy(faker, "anything") == "anything"
    assert strategy(faker, None) is None


def test_redact_replaces_non_null_values_only():
    strategy = RedactStrategy()
    faker = Faker()
    assert strategy(faker, "secret") == "[REDACTED]"
    assert strategy(faker, None) is None


def test_faker_strategies_return_none_for_none_and_something_for_values():
    faker = Faker()
    faker.seed_instance(0)
    for name, strategy in STRATEGIES.items():
        if name == "preserve":
            continue
        assert strategy(faker, None) is None, f"{name} should pass NULL through"


def test_redact_excluded_from_key_safe_strategies():
    assert "redact" not in KEY_SAFE_STRATEGIES
    assert "preserve" in KEY_SAFE_STRATEGIES
    assert "shuffle" in KEY_SAFE_STRATEGIES
    assert "fake_email" in KEY_SAFE_STRATEGIES


def test_fk_column_strategies_are_only_preserve_and_shuffle():
    assert FK_COLUMN_STRATEGIES == frozenset({"preserve", "shuffle"})
