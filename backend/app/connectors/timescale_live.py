"""Reads schema and sample data from TimescaleDB (Postgres-compatible, hypertable-aware)."""
from __future__ import annotations

import os
import psycopg2
import psycopg2.extras


def _conn():
    return psycopg2.connect(
        host=os.environ.get("TIMESCALE_HOST", "localhost"),
        port=int(os.environ.get("TIMESCALE_PORT", "5432")),
        dbname=os.environ.get("TIMESCALE_DB", "tsdb"),
        user=os.environ.get("TIMESCALE_USER", "postgres"),
        password=os.environ.get("TIMESCALE_PASSWORD", "postgres"),
    )


def extract_schema() -> dict[str, list[dict]]:
    """Return columns for all user tables, tagged with whether they are hypertables."""
    col_sql = """
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
    """
    hyper_sql = """
        SELECT hypertable_name
        FROM timescaledb_information.hypertables
    """
    result: dict[str, list[dict]] = {}
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(col_sql)
            for row in cur.fetchall():
                tbl = row["table_name"]
                result.setdefault(tbl, []).append(
                    {
                        "column": row["column_name"],
                        "data_type": row["data_type"],
                        "nullable": row["is_nullable"] == "YES",
                    }
                )
        # tag hypertables (TimescaleDB extension — may not exist on plain Postgres)
        try:
            with conn.cursor() as cur:
                cur.execute(hyper_sql)
                hypertables = {r[0] for r in cur.fetchall()}
        except Exception:
            hypertables = set()

    for tbl in result:
        for col in result[tbl]:
            col["is_hypertable"] = tbl in hypertables

    return result


def sample_rows(table: str, limit: int = 5) -> list[dict]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # order by first timestamp-like column if present for time-series context
            cur.execute(f"SELECT * FROM {table} ORDER BY 1 DESC LIMIT %s", (limit,))
            return [dict(r) for r in cur.fetchall()]


def extract_all() -> dict:
    schema = extract_schema()
    samples = {tbl: sample_rows(tbl) for tbl in schema}
    return {"source": "timescaledb", "schema": schema, "samples": samples}
