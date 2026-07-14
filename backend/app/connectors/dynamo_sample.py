"""Reads schema (inferred) and sample items from DynamoDB (or LocalStack)."""
from __future__ import annotations

import os
import boto3


def _client():
    endpoint = os.environ.get("DYNAMODB_ENDPOINT_URL")  # set for LocalStack
    return boto3.client(
        "dynamodb",
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        endpoint_url=endpoint,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    )


def list_tables() -> list[str]:
    client = _client()
    tables = []
    paginator = client.get_paginator("list_tables")
    for page in paginator.paginate():
        tables.extend(page["TableNames"])
    return tables


def _deserialize(item: dict) -> dict:
    from boto3.dynamodb.types import TypeDeserializer
    d = TypeDeserializer()
    return {k: d.deserialize(v) for k, v in item.items()}


def sample_items(table: str, limit: int = 10) -> list[dict]:
    client = _client()
    r = client.scan(TableName=table, Limit=limit)
    return [_deserialize(item) for item in r.get("Items", [])]


def infer_schema(items: list[dict]) -> list[dict]:
    """Walk sample items and collect all keys with their Python types."""
    seen: dict[str, set] = {}
    for item in items:
        for k, v in item.items():
            seen.setdefault(k, set()).add(type(v).__name__)
    return [{"column": k, "data_types": list(v)} for k, v in sorted(seen.items())]


def extract_all() -> dict:
    tables = list_tables()
    schema: dict[str, list] = {}
    samples: dict[str, list] = {}
    for tbl in tables:
        rows = sample_items(tbl)
        samples[tbl] = rows
        schema[tbl] = infer_schema(rows)
    return {"source": "dynamodb", "schema": schema, "samples": samples}
