"""Per-column masking/synthesis strategies.

A strategy is a small callable wrapper: given a Faker instance and an original
value, produce a replacement. The engine decides *when* a strategy needs a
consistent remap (because the column's value domain matters elsewhere, via a
primary key or a foreign key pointing at it) -- strategies themselves are
stateless per call.

``shuffle`` is the one exception: it permutes an entire column's existing
values across rows rather than generating new ones, so it is handled directly
by the engine rather than through :data:`STRATEGIES`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from faker import Faker


class Strategy(Protocol):
    def __call__(self, faker: Faker, value: object) -> object: ...


@dataclass
class PreserveStrategy:
    """Leave the value exactly as-is."""

    def __call__(self, faker: Faker, value: object) -> object:
        return value


@dataclass
class RedactStrategy:
    """Replace the value with a fixed placeholder.

    Defaults to the string ``"[REDACTED]"`` rather than NULL, since the
    columns this strategy targets (passwords, tokens, SSNs, card numbers --
    see suggest.py) are almost always non-nullable string columns; NULL would
    just fail the column's constraint. A non-nullable non-string column
    configured with "redact" will still fail at insert time -- use a fake_*
    strategy for those instead.
    """

    replacement: object = "[REDACTED]"

    def __call__(self, faker: Faker, value: object) -> object:
        if value is None:
            return None
        return self.replacement


@dataclass
class FakerStrategy:
    """Generate a value via a Faker provider method, independent of the
    original value. Used both for row-independent masking and, when the
    engine determines a remap is needed, as the generator behind that remap.
    """

    generate: Callable[[Faker], object]

    def __call__(self, faker: Faker, value: object) -> object:
        if value is None:
            return None
        return self.generate(faker)


# Registry of strategy names understood by config files and the web UI.
# "preserve" and "shuffle" are handled by name directly in engine.py because
# they need row/column context a single-value callable doesn't have; they are
# listed here too so config validation and the UI can present one source of
# truth for valid strategy names.
STRATEGIES: dict[str, Strategy] = {
    "preserve": PreserveStrategy(),
    "redact": RedactStrategy(),
    "fake_name": FakerStrategy(lambda f: f.name()),
    "fake_first_name": FakerStrategy(lambda f: f.first_name()),
    "fake_last_name": FakerStrategy(lambda f: f.last_name()),
    "fake_email": FakerStrategy(lambda f: f.email()),
    "fake_username": FakerStrategy(lambda f: f.user_name()),
    "fake_phone": FakerStrategy(lambda f: f.phone_number()),
    "fake_address": FakerStrategy(lambda f: f.address().replace("\n", ", ")),
    "fake_city": FakerStrategy(lambda f: f.city()),
    "fake_country": FakerStrategy(lambda f: f.country()),
    "fake_company": FakerStrategy(lambda f: f.company()),
    "fake_date_of_birth": FakerStrategy(lambda f: f.date_of_birth().isoformat()),
    "fake_date": FakerStrategy(lambda f: f.date()),
    "fake_ipv4": FakerStrategy(lambda f: f.ipv4()),
    "fake_uuid": FakerStrategy(lambda f: f.uuid4()),
    "fake_credit_card": FakerStrategy(lambda f: f.credit_card_number()),
    "fake_text": FakerStrategy(lambda f: f.sentence()),
}

# Strategies allowed on a column whose value domain other rows depend on
# (a primary key, or a column another table's foreign key points at).
# "redact" is excluded: collapsing every value to the same placeholder (or
# NULL) breaks the uniqueness a primary/referenced key relies on.
KEY_SAFE_STRATEGIES = frozenset({"preserve", "shuffle", *STRATEGIES.keys()} - {"redact"})

# Strategies allowed on a column that is itself a foreign key. Anything other
# than "preserve" or "shuffle" would mask the FK independently of its parent,
# which the engine cannot reconcile with referential-integrity propagation --
# see engine.py's remap-propagation logic.
FK_COLUMN_STRATEGIES = frozenset({"preserve", "shuffle"})

ALL_STRATEGY_NAMES = frozenset({"preserve", "shuffle", *STRATEGIES.keys()})
