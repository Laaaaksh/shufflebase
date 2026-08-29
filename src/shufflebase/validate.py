"""Post-run referential-integrity validation.

This queries the *actual written target database* -- it does not trust the
engine's own in-memory remap bookkeeping. That distinction matters: a bug in
``engine.py`` could silently produce broken joins even if its own logic
believes it preserved them, so the last word on "is this database safe to
use" always comes from asking the database itself whether every foreign key
value has a match in its parent table.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, MetaData, and_, func, select

from .schema import SchemaGraph


@dataclass
class ForeignKeyViolation:
    table: str
    columns: tuple[str, ...]
    refers_to_table: str
    refers_to_columns: tuple[str, ...]
    violating_row_count: int

    def __str__(self) -> str:
        cols = ",".join(self.columns)
        rcols = ",".join(self.refers_to_columns)
        return (
            f"{self.table}({cols}) -> {self.refers_to_table}({rcols}): "
            f"{self.violating_row_count} row(s) reference a value with no matching parent row"
        )


def validate_referential_integrity(
    engine: Engine, schema: SchemaGraph
) -> list[ForeignKeyViolation]:
    """Check every foreign key in ``schema`` against the data actually
    present in ``engine``'s database. Returns an empty list if every foreign
    key resolves; otherwise one :class:`ForeignKeyViolation` per broken
    constraint, with a count of how many rows are affected.
    """
    metadata = MetaData()
    metadata.reflect(bind=engine)

    violations: list[ForeignKeyViolation] = []
    with engine.connect() as conn:
        for table in schema.tables.values():
            if table.name not in metadata.tables:
                continue
            child = metadata.tables[table.name]
            for fk in table.foreign_keys:
                if fk.refers_to_table not in metadata.tables:
                    continue
                # Alias the parent even when it's a different table: a
                # self-referencing FK (fk.is_self_referencing) makes parent
                # and child the *same* Table object, and without an alias
                # SQLAlchemy's subquery auto-correlation collapses the
                # correlated EXISTS into comparing each row against itself
                # instead of against every other row.
                parent = metadata.tables[fk.refers_to_table].alias()
                child_cols = [child.c[c] for c in fk.columns]
                parent_cols = [parent.c[c] for c in fk.refers_to_columns]

                not_null = and_(*[c.isnot(None) for c in child_cols])
                has_match = (
                    select(1)
                    .select_from(parent)
                    .where(
                        and_(*[pc == cc for pc, cc in zip(parent_cols, child_cols, strict=True)])
                    )
                    .exists()
                )
                count_stmt = (
                    select(func.count()).select_from(child).where(and_(not_null, ~has_match))
                )
                violating_count = conn.execute(count_stmt).scalar_one()
                if violating_count:
                    violations.append(
                        ForeignKeyViolation(
                            table=fk.table,
                            columns=fk.columns,
                            refers_to_table=fk.refers_to_table,
                            refers_to_columns=fk.refers_to_columns,
                            violating_row_count=violating_count,
                        )
                    )
    return violations
