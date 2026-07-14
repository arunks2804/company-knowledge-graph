"""Reads schema and sample data from a live Postgres database."""
from __future__ import annotations

import os
import psycopg2
import psycopg2.extras


def _conn():
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "retail_db"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
    )


def extract_schema() -> dict[str, list[dict]]:
    """Return {table: [{column, data_type, is_nullable, column_default}]} for all user tables."""
    sql = """
        SELECT table_name, column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
    """
    result: dict[str, list[dict]] = {}
    with _conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        for row in cur.fetchall():
            tbl = row["table_name"]
            result.setdefault(tbl, []).append(
                {
                    "column": row["column_name"],
                    "data_type": row["data_type"],
                    "nullable": row["is_nullable"] == "YES",
                }
            )
    return result


def sample_rows(table: str, limit: int = 5) -> list[dict]:
    """Return up to `limit` rows from `table` as plain dicts."""
    with _conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT * FROM {table} LIMIT %s", (limit,))
        return [dict(r) for r in cur.fetchall()]


def extract_all() -> dict:
    """Return schema + sample rows for every table."""
    schema = extract_schema()
    samples = {tbl: sample_rows(tbl) for tbl in schema}
    return {"source": "postgres", "schema": schema, "samples": samples}
