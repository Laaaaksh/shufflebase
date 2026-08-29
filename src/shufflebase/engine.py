"""The masking engine: reads a source database, applies configured column
strategies, and writes a referentially-consistent copy to a target database.

The core idea that makes this more than a find-and-replace script: when a
strategy resynthesizes a column's *value domain* (a primary key, or a column
another table's foreign key points at), the engine builds a stable
old-value -> new-value remap once, then applies that exact same remap to
every foreign key column elsewhere that points at it. A masked
``orders.customer_id`` therefore still resolves to a masked row in
``customers`` -- see ``README.md``'s "How referential integrity is
preserved" section for the user-facing version of this explanation.

After writing the target database, ``execute()`` runs an independent
validation pass (``validate_referential_integrity`` in ``validate.py``)
against the *actual written data* -- not just this module's own bookkeeping
-- and raises rather than returning a database with broken joins.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from faker import Faker
from sqlalchemy import Engine, Table, insert, select

from .config import ConfigError, RunConfig
from .config import validate as validate_config
from .schema import build_schema_graph, reflect_metadata
from .strategies import STRATEGIES
from .validate import ForeignKeyViolation, validate_referential_integrity

# Batch size for streaming inserts into the target database.
_INSERT_BATCH = 1000
# How many candidate values to try before giving up on finding a unique
# replacement for a key column (see _build_remap).
_MAX_REMAP_ATTEMPTS = 100


@dataclass
class TableResult:
    table: str
    row_count: int


@dataclass
class RunResult:
    tables: list[TableResult] = field(default_factory=list)
    violations: list[ForeignKeyViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    @property
    def total_rows(self) -> int:
        return sum(t.row_count for t in self.tables)


class ReferentialIntegrityError(Exception):
    """Raised when a completed run would leave broken foreign keys. The
    target database is left in place for inspection but should not be
    treated as usable -- see the ``violations`` attribute for specifics."""

    def __init__(self, violations: list[ForeignKeyViolation]):
        self.violations = violations
        detail = "\n".join(f"  - {v}" for v in violations)
        super().__init__(f"run produced {len(violations)} broken foreign key(s):\n{detail}")


class MaskRun:
    """One masking run from ``source_engine`` to ``target_engine``, governed
    by ``config``. The target database's schema is (re)created to mirror the
    source; call against an empty/disposable target."""

    def __init__(
        self,
        source_engine: Engine,
        target_engine: Engine,
        config: RunConfig,
        seed: int | None = None,
    ):
        self.source_engine = source_engine
        self.target_engine = target_engine
        self.config = config
        self.seed = seed if seed is not None else config.seed

    def execute(self) -> RunResult:
        metadata = reflect_metadata(self.source_engine)
        schema = build_schema_graph(metadata)

        errors = validate_config(self.config, schema)
        if errors:
            raise ConfigError(
                "config failed validation against the source schema:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

        order = schema.topological_order()
        faker = Faker()
        rng = random.Random(self.seed)
        if self.seed is not None:
            faker.seed_instance(self.seed)

        metadata.create_all(self.target_engine)

        remaps: dict[tuple[str, str], dict[object, object]] = {}
        results: list[TableResult] = []

        with self.source_engine.connect() as source_conn, self.target_engine.begin() as target_conn:
            for table_name in order:
                table_info = schema.tables[table_name]
                sa_table: Table = metadata.tables[table_name]
                rows = [dict(row._mapping) for row in source_conn.execute(select(sa_table))]

                self._build_key_remaps(table_name, table_info, rows, faker, remaps)
                self._apply_shuffles(table_info, rows, rng)
                transformed = self._transform_rows(table_name, table_info, rows, faker, remaps)

                if transformed:
                    for start in range(0, len(transformed), _INSERT_BATCH):
                        batch = transformed[start : start + _INSERT_BATCH]
                        target_conn.execute(insert(sa_table), batch)
                results.append(TableResult(table=table_name, row_count=len(transformed)))

        violations = validate_referential_integrity(self.target_engine, schema)
        return RunResult(tables=results, violations=violations)

    def _build_key_remaps(
        self,
        table_name: str,
        table_info,
        rows: list[dict],
        faker: Faker,
        remaps: dict[tuple[str, str], dict[object, object]],
    ) -> None:
        """For every column in this table whose value domain matters
        elsewhere (primary key, or a column another table's FK points at)
        and whose configured strategy generates new values, build a stable
        old -> new mapping. Composite keys never reach here with a
        remap-requiring strategy -- config validation already rejects that
        combination, so every remap here is a single scalar column.
        """
        for column_name, column in table_info.columns.items():
            if column.references is not None:
                continue  # FK columns inherit their parent's remap; see _transform_rows.
            if not column.is_key_column:
                continue
            strategy_name = self.config.strategy_for(table_name, column_name)
            if strategy_name in ("preserve", "shuffle"):
                continue

            strategy_fn = STRATEGIES[strategy_name]
            distinct_values = {row[column_name] for row in rows}
            remaps[(table_name, column_name)] = _build_remap(faker, strategy_fn, distinct_values)

    def _apply_shuffles(self, table_info, rows: list[dict], rng: random.Random) -> None:
        """Permute each shuffle-strategy column's existing values across this
        table's rows in place. Safe on any column, including keys and FKs:
        the value *set* is unchanged, only which row holds which value."""
        for column_name in table_info.columns:
            strategy_name = self.config.strategy_for(table_info.name, column_name)
            if strategy_name != "shuffle" or not rows:
                continue
            values = [row[column_name] for row in rows]
            rng.shuffle(values)
            for row, new_value in zip(rows, values, strict=True):
                row[column_name] = new_value

    def _transform_rows(
        self,
        table_name: str,
        table_info,
        rows: list[dict],
        faker: Faker,
        remaps: dict[tuple[str, str], dict[object, object]],
    ) -> list[dict]:
        transformed = []
        for row in rows:
            new_row = dict(row)
            for column_name, column in table_info.columns.items():
                strategy_name = self.config.strategy_for(table_name, column_name)
                if strategy_name == "shuffle":
                    continue  # already applied in-place by _apply_shuffles

                if column.references is not None:
                    # FK column: propagate the parent's remap if it has one,
                    # regardless of this column's own (preserve-only) config.
                    # Index into the FK's column tuples to find the matching
                    # remote column -- correct for both single-column and
                    # (preserve/shuffle-only) composite foreign keys.
                    fk = column.references
                    remote_column = fk.refers_to_columns[fk.columns.index(column_name)]
                    parent_remap = remaps.get((fk.refers_to_table, remote_column))
                    if parent_remap is not None:
                        new_row[column_name] = parent_remap.get(row[column_name], row[column_name])
                    continue

                own_remap = remaps.get((table_name, column_name))
                if own_remap is not None:
                    new_row[column_name] = own_remap.get(row[column_name], row[column_name])
                    continue

                if strategy_name == "preserve":
                    continue
                new_row[column_name] = STRATEGIES[strategy_name](faker, row[column_name])
            transformed.append(new_row)
        return transformed


def _build_remap(faker: Faker, strategy_fn, values: set) -> dict[object, object]:
    remap: dict[object, object] = {}
    used: set[object] = set()
    for old_value in values:
        if old_value is None:
            remap[old_value] = None
            continue
        for _ in range(_MAX_REMAP_ATTEMPTS):
            candidate = strategy_fn(faker, old_value)
            if candidate not in used:
                used.add(candidate)
                remap[old_value] = candidate
                break
        else:
            raise RuntimeError(
                f"could not generate a unique replacement value after "
                f"{_MAX_REMAP_ATTEMPTS} attempts; this column has more distinct "
                "values than this strategy can generate without collisions"
            )
    return remap
