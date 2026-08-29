"""FastAPI backend for the web dashboard.

Two endpoints do the whole job, mirroring the CLI's ``introspect`` and
``run`` commands exactly -- this is the same :mod:`shufflebase.engine`
underneath, just driven from a browser instead of a config file. A config
file produced by ``shufflebase introspect -o config.yaml`` and one built by
clicking through this dashboard are interchangeable.

This dashboard connects to whatever database URL a caller gives it and runs
queries against it -- that is the tool's entire job, not a vulnerability in
this code, but it does mean this process must never be exposed on a public
network. See SECURITY.md.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine

from ..config import ConfigError, RunConfig
from ..config import validate as validate_config
from ..engine import MaskRun
from ..schema import CircularForeignKeyError, SchemaGraph
from ..schema import introspect as introspect_schema
from ..strategies import ALL_STRATEGY_NAMES, FK_COLUMN_STRATEGIES, KEY_SAFE_STRATEGIES
from ..suggest import suggest_strategy

app = FastAPI(title="Shufflebase")

_STATIC_DIR = Path(__file__).parent / "static"


class IntrospectRequest(BaseModel):
    url: str


class RunRequest(BaseModel):
    source: str
    target: str
    seed: int | None = None
    tables: dict[str, dict[str, str]]


def _allowed_strategies(column) -> list[str]:
    if column.references is not None:
        return sorted(FK_COLUMN_STRATEGIES)
    if column.is_key_column:
        return sorted(KEY_SAFE_STRATEGIES)
    return sorted(ALL_STRATEGY_NAMES)


def _schema_to_json(schema: SchemaGraph) -> dict:
    tables = []
    for table in schema.tables.values():
        columns = []
        for column in table.columns.values():
            columns.append(
                {
                    "name": column.name,
                    "type": column.type_name,
                    "nullable": column.nullable,
                    "is_primary_key": column.is_primary_key,
                    "is_referenced": column.is_referenced,
                    "foreign_key": (
                        {
                            "table": column.references.refers_to_table,
                            "columns": list(column.references.refers_to_columns),
                        }
                        if column.references is not None
                        else None
                    ),
                    "suggested_strategy": suggest_strategy(column),
                    "allowed_strategies": _allowed_strategies(column),
                }
            )
        tables.append({"name": table.name, "columns": columns})
    return {"tables": tables}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


@app.post("/api/introspect")
def introspect(req: IntrospectRequest) -> dict:
    engine = create_engine(req.url)
    try:
        schema = introspect_schema(engine)
    except CircularForeignKeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface any connection/driver error to the UI
        raise HTTPException(status_code=400, detail=f"could not connect: {exc}") from exc
    finally:
        engine.dispose()

    if not schema.tables:
        raise HTTPException(status_code=400, detail="no tables found at that URL")
    return _schema_to_json(schema)


@app.post("/api/run")
def run(req: RunRequest) -> dict:
    config = RunConfig(source=req.source, target=req.target, seed=req.seed, tables=req.tables)
    source_engine = create_engine(req.source)
    target_engine = create_engine(req.target)

    try:
        schema = introspect_schema(source_engine)
        errors = validate_config(config, schema)
        if errors:
            raise HTTPException(status_code=400, detail=errors)
        result = MaskRun(source_engine, target_engine, config, seed=req.seed).execute()
    except (ConfigError, CircularForeignKeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        source_engine.dispose()
        target_engine.dispose()

    return {
        "ok": result.ok,
        "total_rows": result.total_rows,
        "tables": [{"table": t.table, "rows": t.row_count} for t in result.tables],
        "violations": [str(v) for v in result.violations],
    }


app.mount("/", StaticFiles(directory=_STATIC_DIR), name="static")
