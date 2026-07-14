"""Reads schema and sample data from Apache Iceberg via PyIceberg catalog."""
from __future__ import annotations

import os


def _catalog():
    from pyiceberg.catalog import load_catalog
    catalog_type = os.environ.get("ICEBERG_CATALOG_TYPE", "rest")
    uri = os.environ.get("ICEBERG_CATALOG_URI", "http://localhost:8181")
    warehouse = os.environ.get("ICEBERG_WAREHOUSE", "s3://warehouse")
    return load_catalog(
        "default",
        **{
            "type": catalog_type,
            "uri": uri,
            "warehouse": warehouse,
            "s3.endpoint": os.environ.get("ICEBERG_S3_ENDPOINT", "http://localhost:9000"),
            "s3.access-key-id": os.environ.get("AWS_ACCESS_KEY_ID", "admin"),
            "s3.secret-access-key": os.environ.get("AWS_SECRET_ACCESS_KEY", "password"),
        },
    )


def list_namespaces() -> list[str]:
    catalog = _catalog()
    return [".".join(ns) for ns in catalog.list_namespaces()]


def extract_schema() -> dict[str, list[dict]]:
    """Return {namespace.table: [{column, data_type, required}]} for all Iceberg tables."""
    catalog = _catalog()
    result: dict[str, list[dict]] = {}
    for ns_tuple in catalog.list_namespaces():
        ns = ".".join(ns_tuple)
        for tbl_id in catalog.list_tables(ns_tuple):
            key = f"{ns}.{tbl_id[-1]}"
            try:
                table = catalog.load_table(tbl_id)
                columns = []
                for field in table.schema().fields:
                    columns.append(
                        {
                            "column": field.name,
                            "data_type": str(field.field_type),
                            "required": field.required,
                        }
                    )
                result[key] = columns
            except Exception:
                result[key] = []
    return result


def sample_rows(table_identifier: str, limit: int = 5) -> list[dict]:
    """Scan up to `limit` rows from an Iceberg table."""
    catalog = _catalog()
    parts = table_identifier.split(".")
    table = catalog.load_table(tuple(parts))
    scan = table.scan(limit=limit)
    rows = []
    for batch in scan.to_arrow().to_batches():
        for i in range(batch.num_rows):
            rows.append({col: batch.column(col)[i].as_py() for col in batch.schema.names})
            if len(rows) >= limit:
                return rows
    return rows


def extract_all() -> dict:
    schema = extract_schema()
    samples = {}
    for tbl in schema:
        try:
            samples[tbl] = sample_rows(tbl)
        except Exception:
            samples[tbl] = []
    return {"source": "iceberg", "schema": schema, "samples": samples}
