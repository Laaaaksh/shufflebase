"""Command-line interface.

Three commands cover the whole workflow:

    shufflebase introspect --source <url> -o config.yaml
        Connect, detect tables/columns/foreign keys, write a config file
        pre-filled with suggested strategies for review.

    shufflebase run --config config.yaml --source <url> --target <url>
        Execute a masking run: read source, apply strategies, write target,
        validate every foreign key still resolves.

    shufflebase validate --target <url>
        Independently check an already-masked (or any) database's foreign
        keys resolve, without running a mask.

This is deliberately the same engine the web UI (``shufflebase serve``)
drives -- see ``shufflebase/web/api.py`` -- so a config produced by one works
with the other.
"""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.table import Table as RichTable
from sqlalchemy import create_engine

from .config import ConfigError, RunConfig
from .engine import MaskRun
from .schema import CircularForeignKeyError
from .schema import introspect as introspect_schema
from .validate import validate_referential_integrity

console = Console()
error_console = Console(stderr=True, style="bold red")


@click.group()
@click.version_option(package_name="shufflebase")
def main() -> None:
    """Database-aware synthetic test-data and masking, with referential
    integrity preserved across foreign keys."""


@main.command()
@click.option("--source", required=True, help="Source database URL to introspect.")
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(dir_okay=False),
    default=None,
    help="Write the generated config here instead of stdout.",
)
def introspect(source: str, output_path: str | None) -> None:
    """Detect tables, columns, and foreign keys, and print a config file
    pre-filled with suggested masking strategies."""
    engine = create_engine(source)
    try:
        schema = introspect_schema(engine)
    except CircularForeignKeyError as exc:
        error_console.print(str(exc))
        sys.exit(1)

    if not schema.tables:
        error_console.print(f"no tables found at {source!r}")
        sys.exit(1)

    _print_schema_summary(schema)

    config = RunConfig.from_schema(schema, source=source)
    yaml_text = config.to_yaml()
    if output_path:
        with open(output_path, "w") as f:
            f.write(yaml_text)
        console.print(f"\n[green]Wrote suggested config to {output_path}[/green]")
    else:
        console.print("\n" + yaml_text)


@main.command()
@click.option("--config", "config_path", required=True, type=click.Path(exists=True))
@click.option("--source", default=None, help="Override the config file's source URL.")
@click.option("--target", default=None, help="Override the config file's target URL.")
@click.option("--seed", type=int, default=None, help="Override the config file's random seed.")
def run(config_path: str, source: str | None, target: str | None, seed: int | None) -> None:
    """Run a masking pass from a source database to a target database."""
    config = RunConfig.from_file(config_path)
    source_url = source or config.source
    target_url = target or config.target
    if not source_url:
        error_console.print("no source URL given (pass --source or set 'source' in the config)")
        sys.exit(1)
    if not target_url:
        error_console.print("no target URL given (pass --target or set 'target' in the config)")
        sys.exit(1)

    source_engine = create_engine(source_url)
    target_engine = create_engine(target_url)
    mask_run = MaskRun(source_engine, target_engine, config, seed=seed)

    try:
        result = mask_run.execute()
    except (ConfigError, CircularForeignKeyError) as exc:
        error_console.print(str(exc))
        sys.exit(1)

    table = RichTable(title="Masking run complete")
    table.add_column("Table")
    table.add_column("Rows", justify="right")
    for t in result.tables:
        table.add_row(t.table, str(t.row_count))
    console.print(table)
    console.print(
        f"[bold]{result.total_rows}[/bold] rows written across {len(result.tables)} tables."
    )

    if not result.ok:
        error_console.print(
            f"\n{len(result.violations)} foreign key violation(s) found in the target database:"
        )
        for v in result.violations:
            error_console.print(f"  - {v}")
        sys.exit(1)

    console.print("[green]All foreign keys resolve correctly.[/green]")


@main.command()
@click.option("--target", required=True, help="Database URL to check.")
def validate(target: str) -> None:
    """Check that every foreign key in a database currently resolves."""
    engine = create_engine(target)
    schema = introspect_schema(engine)
    violations = validate_referential_integrity(engine, schema)
    if violations:
        error_console.print(f"{len(violations)} foreign key violation(s):")
        for v in violations:
            error_console.print(f"  - {v}")
        sys.exit(1)
    console.print("[green]All foreign keys resolve correctly.[/green]")


@main.command()
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8642, type=int)
def serve(host: str, port: int) -> None:
    """Start the web dashboard (requires the 'web' extra: pip install shufflebase[web])."""
    try:
        import uvicorn

        from .web.api import app
    except ImportError:
        error_console.print(
            "the web dashboard needs extra dependencies: pip install 'shufflebase[web]'"
        )
        sys.exit(1)
    uvicorn.run(app, host=host, port=port)


def _print_schema_summary(schema) -> None:
    from .suggest import suggest_strategy

    for table in schema.tables.values():
        rich_table = RichTable(title=table.name)
        rich_table.add_column("Column")
        rich_table.add_column("Type")
        rich_table.add_column("Key")
        rich_table.add_column("Suggested strategy")
        for column in table.columns.values():
            key_flags = []
            if column.is_primary_key:
                key_flags.append("PK")
            if column.references is not None:
                key_flags.append(f"FK -> {column.references.refers_to_table}")
            if column.is_referenced:
                key_flags.append("referenced")
            rich_table.add_row(
                column.name,
                column.type_name,
                ", ".join(key_flags),
                suggest_strategy(column),
            )
        console.print(rich_table)


if __name__ == "__main__":
    main()
