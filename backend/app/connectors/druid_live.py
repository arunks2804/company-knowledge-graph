"""Reads schema and sample data from Apache Druid via its SQL API."""
from __future__ import annotations

import os
import httpx


def _base() -> str:
    return os.environ.get("DRUID_URL", "http://localhost:8888")


def list_datasources() -> list[str]:
    r = httpx.get(f"{_base()}/druid/v2/datasources", timeout=10)
    r.raise_for_status()
    return r.json()


def _sql(query: str) -> list[dict]:
    r = httpx.post(
        f"{_base()}/druid/v2/sql",
        json={"query": query},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def extract_schema() -> dict[str, list[dict]]:
    """Return {datasource: [{column, data_type}]} for all Druid datasources."""
    rows = _sql(
        "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE "
        "FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = 'druid' "
        "ORDER BY TABLE_NAME, ORDINAL_POSITION"
    )
    result: dict[str, list[dict]] = {}
    for row in rows:
        ds = row["TABLE_NAME"]
        result.setdefault(ds, []).append(
            {"column": row["COLUMN_NAME"], "data_type": row["DATA_TYPE"]}
        )
    return result


def sample_rows(datasource: str, limit: int = 5) -> list[dict]:
    return _sql(f'SELECT * FROM "{datasource}" LIMIT {limit}')


def extract_all() -> dict:
    schema = extract_schema()
    samples = {}
    for ds in schema:
        try:
            samples[ds] = sample_rows(ds)
        except Exception:
            samples[ds] = []
    return {"source": "druid", "schema": schema, "samples": samples}
