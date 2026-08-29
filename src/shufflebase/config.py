"""Run configuration: which strategy applies to which column, loaded from
YAML and validated against a reflected schema before any masking runs.

Validation happens up front and rejects the whole run rather than silently
producing a database with broken joins -- see ``validate()`` below and
``engine.py``'s use of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .schema import CircularForeignKeyError, SchemaGraph
from .strategies import ALL_STRATEGY_NAMES, FK_COLUMN_STRATEGIES, KEY_SAFE_STRATEGIES


class ConfigError(Exception):
    """Raised for a config file that is malformed or fails schema validation."""


@dataclass
class RunConfig:
    source: str | None = None
    target: str | None = None
    seed: int | None = None
    # table name -> column name -> strategy name
    tables: dict[str, dict[str, str]] = field(default_factory=dict)

    def strategy_for(self, table: str, column: str) -> str:
        return self.tables.get(table, {}).get(column, "preserve")

    def to_dict(self) -> dict:
        data: dict = {"tables": self.tables}
        if self.source is not None:
            data["source"] = self.source
        if self.target is not None:
            data["target"] = self.target
        if self.seed is not None:
            data["seed"] = self.seed
        return data

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), sort_keys=False)

    @classmethod
    def from_yaml(cls, text: str) -> RunConfig:
        try:
            raw = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"invalid YAML: {exc}") from exc
        if not isinstance(raw, dict):
            raise ConfigError("config file must be a YAML mapping at the top level")
        tables_raw = raw.get("tables", {})
        if not isinstance(tables_raw, dict):
            raise ConfigError("'tables' must be a mapping of table name -> columns")
        tables: dict[str, dict[str, str]] = {}
        for table_name, columns in tables_raw.items():
            if not isinstance(columns, dict):
                raise ConfigError(f"tables.{table_name} must be a mapping of column -> strategy")
            tables[table_name] = {str(k): str(v) for k, v in columns.items()}
        return cls(
            source=raw.get("source"),
            target=raw.get("target"),
            seed=raw.get("seed"),
            tables=tables,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> RunConfig:
        return cls.from_yaml(Path(path).read_text())

    @classmethod
    def from_schema(cls, schema: SchemaGraph, source: str | None = None) -> RunConfig:
        """Build a config pre-filled with suggested strategies for every
        column, for a user to review and edit before running."""
        from .suggest import suggest_strategy

        tables = {
            table.name: {col.name: suggest_strategy(col) for col in table.columns.values()}
            for table in schema.tables.values()
        }
        return cls(source=source, tables=tables)


def validate(config: RunConfig, schema: SchemaGraph) -> list[str]:
    """Check ``config`` against ``schema``. Returns a list of human-readable
    error strings; an empty list means the config is safe to run.

    This is deliberately called both before an interactive run and inside
    ``engine.MaskRun.execute()`` -- the engine never trusts a config it did
    not just re-validate against the live schema.
    """
    errors: list[str] = []

    for table_name, columns in config.tables.items():
        table = schema.tables.get(table_name)
        if table is None:
            errors.append(f"config references unknown table '{table_name}'")
            continue
        for column_name, strategy in columns.items():
            column = table.columns.get(column_name)
            if column is None:
                errors.append(f"config references unknown column '{table_name}.{column_name}'")
                continue
            if strategy not in ALL_STRATEGY_NAMES:
                errors.append(f"{table_name}.{column_name}: unknown strategy '{strategy}'")
                continue

            if column.references is not None:
                if strategy not in FK_COLUMN_STRATEGIES:
                    errors.append(
                        f"{table_name}.{column_name} is a foreign key to "
                        f"{column.references.refers_to_table} "
                        f"({', '.join(column.references.refers_to_columns)}); "
                        f"only {sorted(FK_COLUMN_STRATEGIES)} are allowed here, got '{strategy}'"
                    )
            elif column.is_key_column and strategy not in KEY_SAFE_STRATEGIES:
                errors.append(
                    f"{table_name}.{column_name} is a primary/referenced key column; "
                    f"'redact' would collapse its values and break uniqueness -- "
                    f"use 'preserve', 'shuffle', or a fake_* strategy instead"
                )

            is_composite = (
                (column.is_primary_key and table.has_composite_primary_key)
                or (column.references is not None and column.references.is_composite)
                or any(fk.is_composite for fk in column.referenced_by)
            )
            if is_composite and strategy not in FK_COLUMN_STRATEGIES:
                errors.append(
                    f"{table_name}.{column_name} is part of a composite primary/foreign "
                    f"key; shufflebase v1 only supports 'preserve' or 'shuffle' on "
                    f"composite keys, got '{strategy}'"
                )

    # Shuffling a foreign key column is only safe if its parent's referenced
    # column isn't being resynthesized underneath it (a remap would leave the
    # shuffled, pre-remap values pointing nowhere).
    for table_name, columns in config.tables.items():
        table = schema.tables.get(table_name)
        if table is None:
            continue
        for column_name, strategy in columns.items():
            column = table.columns.get(column_name)
            if column is None or column.references is None or strategy != "shuffle":
                continue
            fk = column.references
            parent_strategies = {
                config.strategy_for(fk.refers_to_table, c) for c in fk.refers_to_columns
            }
            if parent_strategies - {"preserve", "shuffle"}:
                errors.append(
                    f"{table_name}.{column_name}: cannot 'shuffle' this foreign key because "
                    f"{fk.refers_to_table}.{','.join(fk.refers_to_columns)} is being "
                    f"resynthesized ({sorted(parent_strategies)}); use 'preserve' to inherit "
                    "the new values instead"
                )

    try:
        schema.topological_order()
    except CircularForeignKeyError as exc:
        errors.append(str(exc))

    return errors
