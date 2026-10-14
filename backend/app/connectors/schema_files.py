"""
Reads schema definitions dropped into the schemas/ folder.
Supports three formats:
  - .sql  → parses CREATE TABLE DDL (works with Postgres, Snowflake, MySQL, etc.)
  - .json → expects {"source": "name", "tables": {"table": [{column, data_type}]}}
  - .yaml → same structure as JSON
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

_SCHEMAS_DIR = Path(__file__).parent.parent.parent.parent / "schemas"


def _parse_sql(text: str, filename: str) -> dict[str, list[dict]]:
    """Extract columns from CREATE TABLE statements in a SQL DDL file."""
    tables: dict[str, list[dict]] = {}
    # find each CREATE TABLE ... ( ... );
    for match in re.finditer(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s(]+)\s*\(([^;]+)\);",
        text,
        re.IGNORECASE | re.DOTALL,
    ):
        raw_name = match.group(1).strip().strip('"').strip("`")
        # take last part of qualified name (SCHEMA.PUBLIC.TABLE → TABLE)
        table_name = raw_name.split(".")[-1]
        body = match.group(2)
        columns = []
        for line in body.splitlines():
            line = line.strip().rstrip(",")
            if not line:
                continue
            # skip constraints
            if re.match(r"(PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE|CHECK|CONSTRAINT|INDEX)", line, re.IGNORECASE):
                continue
            # column definition: name type [rest...]
            parts = line.split()
            if len(parts) >= 2:
                col_name = parts[0].strip('"').strip("`")
                col_type = parts[1].rstrip(",")
                columns.append({"column": col_name, "data_type": col_type})
        if columns:
            tables[table_name] = columns
    return tables


def _parse_json(text: str) -> tuple[str, dict[str, list[dict]]]:
    data = json.loads(text)
    source = data.get("source", "unknown")
    return source, data.get("tables", {})


def _parse_yaml(text: str) -> tuple[str, dict[str, list[dict]]]:
    data = yaml.safe_load(text)
    source = data.get("source", "unknown")
    return source, data.get("tables", {})


def extract_all(schemas_dir: str | Path | None = None) -> list[dict]:
    """
    Walk schemas/ directory, parse every .sql / .json / .yaml file,
    return a list of source dicts compatible with the ingest pipeline:
    [{"source": "...", "schema": {...}, "samples": {}}]
    """
    root = Path(schemas_dir) if schemas_dir else _SCHEMAS_DIR
    results = []

    for fp in sorted(root.rglob("*")):
        if not fp.is_file() or fp.name.startswith("."):
            continue
        suffix = fp.suffix.lower()
        text = fp.read_text(errors="replace")

        try:
            if suffix == ".sql":
                tables = _parse_sql(text, fp.name)
                source_name = fp.stem
                if tables:
                    results.append({"source": f"schema_file:{source_name}", "schema": tables, "samples": {}, "file": str(fp.resolve())})

            elif suffix == ".json":
                source_name, tables = _parse_json(text)
                if tables:
                    results.append({"source": f"schema_file:{source_name}", "schema": tables, "samples": {}, "file": str(fp.resolve())})

            elif suffix in (".yaml", ".yml"):
                source_name, tables = _parse_yaml(text)
                if tables:
                    results.append({"source": f"schema_file:{source_name}", "schema": tables, "samples": {}, "file": str(fp.resolve())})

        except Exception as exc:
            results.append({"source": f"schema_file:{fp.name}", "error": str(exc), "schema": {}, "samples": {}, "file": str(fp.resolve())})

    return results
