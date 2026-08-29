"""Schema introspection: reflect a database into a dependency-ordered graph of
tables, columns, and foreign keys.

This is the "database-aware" half of the tool -- everything downstream (strategy
suggestion, masking, referential-integrity validation) operates on the
:class:`SchemaGraph` this module produces, never on raw SQLAlchemy reflection
objects directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Engine, ForeignKeyConstraint, MetaData, Table


class CircularForeignKeyError(Exception):
    """Raised when the FK graph has a cycle spanning more than one table.

    A single table referencing itself (e.g. ``employees.manager_id ->
    employees.id``) is fine and handled directly by the engine. A cycle across
    two or more tables cannot be given a single "parents before children"
    processing order, which the remap-propagation logic in ``engine.py``
    depends on -- so v1 refuses rather than guessing.
    """


@dataclass
class ForeignKeyRef:
    """One foreign key: a set of columns in ``table`` pointing at a set of
    columns in ``refers_to_table``, in matching order."""

    table: str
    columns: tuple[str, ...]
    refers_to_table: str
    refers_to_columns: tuple[str, ...]

    @property
    def is_composite(self) -> bool:
        return len(self.columns) > 1

    @property
    def is_self_referencing(self) -> bool:
        return self.table == self.refers_to_table


@dataclass
class ColumnInfo:
    name: str
    type_name: str
    nullable: bool
    is_primary_key: bool = False
    # Populated by SchemaGraph after all tables are read: FKs elsewhere that
    # point at this column (this column is a "parent"/referenced column).
    referenced_by: list[ForeignKeyRef] = field(default_factory=list)
    # Populated by SchemaGraph: the FK this column itself participates in, if
    # any (this column is a "child"/FK column). None if this column is not
    # part of any foreign key.
    references: ForeignKeyRef | None = None

    @property
    def is_referenced(self) -> bool:
        """True if some other table's foreign key points at this column."""
        return len(self.referenced_by) > 0

    @property
    def is_key_column(self) -> bool:
        """True if this column's *value domain* matters to other rows: it is
        a primary key or another table's foreign key points at it."""
        return self.is_primary_key or self.is_referenced


@dataclass
class TableInfo:
    name: str
    columns: dict[str, ColumnInfo]
    primary_key: tuple[str, ...]
    foreign_keys: list[ForeignKeyRef] = field(default_factory=list)

    @property
    def has_composite_primary_key(self) -> bool:
        return len(self.primary_key) > 1


@dataclass
class SchemaGraph:
    tables: dict[str, TableInfo]

    def topological_order(self) -> list[str]:
        """Tables in "parents before children" order: every table appears
        after every *other* table it has a foreign key into.

        Self-referencing foreign keys (a table pointing at itself) do not
        count as a dependency for this ordering -- they're resolved within a
        single table's own processing pass. A cycle spanning two or more
        distinct tables raises :class:`CircularForeignKeyError`, since no
        such order exists.
        """
        # Kahn's algorithm over the "depends on" edges (child -> parent),
        # excluding self-loops.
        deps: dict[str, set[str]] = {name: set() for name in self.tables}
        for table in self.tables.values():
            for fk in table.foreign_keys:
                if not fk.is_self_referencing:
                    deps[table.name].add(fk.refers_to_table)

        ordered: list[str] = []
        remaining = dict(deps)
        while remaining:
            ready = sorted(name for name, d in remaining.items() if not d)
            if not ready:
                cycle_tables = ", ".join(sorted(remaining))
                raise CircularForeignKeyError(
                    f"circular foreign key dependency detected among: {cycle_tables}. "
                    "shufflebase cannot compute a parents-before-children processing "
                    "order for these tables; strategies that resynthesize a key "
                    "(anything other than 'preserve' or 'shuffle') are not supported "
                    "on columns involved in this cycle."
                )
            for name in ready:
                ordered.append(name)
                del remaining[name]
            for d in remaining.values():
                d.difference_update(ready)
        return ordered

    def foreign_keys_into(self, table: str, column: str) -> list[ForeignKeyRef]:
        """All foreign keys (in any table) that reference ``table.column``."""
        return list(self.tables[table].columns[column].referenced_by)


def reflect_metadata(engine: Engine, schema: str | None = None) -> MetaData:
    """Reflect ``engine``'s database into raw SQLAlchemy :class:`MetaData`.

    Exposed separately from :func:`introspect` so callers that need the real
    ``Table`` objects for reading/writing rows (see ``engine.py``) don't pay
    for reflecting the database twice.
    """
    metadata = MetaData()
    metadata.reflect(bind=engine, schema=schema)
    return metadata


def build_schema_graph(metadata: MetaData) -> SchemaGraph:
    """Build a :class:`SchemaGraph` from already-reflected ``MetaData``."""
    tables: dict[str, TableInfo] = {}
    for table in metadata.tables.values():
        # SQLAlchemy reflects identifiers as `quoted_name`, a `str` subclass
        # PyYAML's exact-type representer dispatch doesn't recognize -- cast
        # to plain `str` here so every name downstream (config files, JSON
        # for the web UI) is a normal string.
        table_name = str(table.name)
        pk_columns = tuple(str(c.name) for c in table.primary_key.columns)
        columns = {
            str(col.name): ColumnInfo(
                name=str(col.name),
                type_name=str(col.type),
                nullable=col.nullable if col.nullable is not None else True,
                is_primary_key=str(col.name) in pk_columns,
            )
            for col in table.columns
        }
        fks = [_foreign_key_ref(table, constraint) for constraint in table.foreign_key_constraints]
        tables[table_name] = TableInfo(
            name=table_name,
            columns=columns,
            primary_key=pk_columns,
            foreign_keys=fks,
        )

    graph = SchemaGraph(tables=tables)
    _link_foreign_keys(graph)
    return graph


def introspect(engine: Engine, schema: str | None = None) -> SchemaGraph:
    """Reflect ``engine``'s database into a :class:`SchemaGraph`.

    Works uniformly across Postgres and MySQL via SQLAlchemy's reflection API;
    no per-database-engine code lives here or anywhere downstream.
    """
    return build_schema_graph(reflect_metadata(engine, schema))


def _foreign_key_ref(table: Table, constraint: ForeignKeyConstraint) -> ForeignKeyRef:
    local_cols = tuple(str(col.name) for col in constraint.columns)
    remote_cols = tuple(str(fk.column.name) for fk in constraint.elements)
    remote_table = str(constraint.referred_table.name)
    return ForeignKeyRef(
        table=str(table.name),
        columns=local_cols,
        refers_to_table=remote_table,
        refers_to_columns=remote_cols,
    )


def _link_foreign_keys(graph: SchemaGraph) -> None:
    """Cross-wire ColumnInfo.references / .referenced_by from each
    TableInfo.foreign_keys, so any column can answer "am I a key column"
    without walking the whole graph."""
    for table in graph.tables.values():
        for fk in table.foreign_keys:
            for local_col, remote_col in zip(fk.columns, fk.refers_to_columns, strict=True):
                table.columns[local_col].references = fk
                parent_table = graph.tables.get(fk.refers_to_table)
                if parent_table is not None and remote_col in parent_table.columns:
                    parent_table.columns[remote_col].referenced_by.append(fk)
