"""Auto-suggest a masking strategy for a column from its name (and, for key
columns, its role in the schema).

This is intentionally simple pattern-matching, not machine learning: the goal
is a reasonable starting point a human reviews and adjusts, not a guess the
tool is confident enough to run unattended.
"""

from __future__ import annotations

import re

from .schema import ColumnInfo

# Ordered: first matching pattern wins, so put more specific patterns first.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(^|_)email(s)?($|_)"), "fake_email"),
    (re.compile(r"(^|_)(first[_-]?name)($|_)"), "fake_first_name"),
    (re.compile(r"(^|_)(last[_-]?name|surname)($|_)"), "fake_last_name"),
    (re.compile(r"(^|_)(full[_-]?name|name)($|_)"), "fake_name"),
    (re.compile(r"(^|_)username($|_)"), "fake_username"),
    (re.compile(r"(^|_)(phone|mobile|telephone)(number)?($|_)"), "fake_phone"),
    (re.compile(r"(^|_)(street|address)(line\d)?($|_)"), "fake_address"),
    (re.compile(r"(^|_)city($|_)"), "fake_city"),
    (re.compile(r"(^|_)country($|_)"), "fake_country"),
    (re.compile(r"(^|_)(company|employer|organization)($|_)"), "fake_company"),
    (re.compile(r"(^|_)(dob|date[_-]?of[_-]?birth|birth[_-]?date)($|_)"), "fake_date_of_birth"),
    (re.compile(r"(^|_)(ip|ip[_-]?address)($|_)"), "fake_ipv4"),
    (re.compile(r"(^|_)(credit[_-]?card|card[_-]?number|cc[_-]?num)($|_)"), "redact"),
    (re.compile(r"(^|_)(ssn|social[_-]?security)($|_)"), "redact"),
    (re.compile(r"(^|_)(password|passwd|pwd)($|_)"), "redact"),
    (re.compile(r"(^|_)(token|secret|api[_-]?key|access[_-]?key)($|_)"), "redact"),
]


def suggest_strategy(column: ColumnInfo) -> str:
    """Suggest a strategy name for ``column``.

    Key columns (primary keys, or columns another table's foreign key points
    at) default to "preserve" regardless of name -- resynthesizing a key is a
    deliberate choice with real referential-integrity consequences, not
    something to auto-suggest. Foreign key columns likewise default to
    "preserve" so they inherit whatever their parent does.
    """
    if column.is_key_column or column.references is not None:
        return "preserve"

    name = column.name.lower()
    for pattern, strategy in _PATTERNS:
        if pattern.search(name):
            return strategy
    return "preserve"
