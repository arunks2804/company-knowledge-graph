"""Loads and manages organisation config files from the orgs/ directory."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

_ORGS_DIR = Path(__file__).parent.parent.parent.parent / "orgs"
_ORG_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

ALL_CONNECTORS = ["postgres", "timescaledb", "druid", "dynamodb", "iceberg"]


def list_orgs() -> list[dict]:
    orgs = []
    if not _ORGS_DIR.exists():
        return orgs
    for cfg_path in sorted(_ORGS_DIR.rglob("config.yaml")):
        try:
            with open(cfg_path) as f:
                data = yaml.safe_load(f)
            orgs.append({
                "id": data.get("id", cfg_path.parent.name),
                "name": data.get("name", cfg_path.parent.name),
                "apps": data.get("apps", []),
            })
        except Exception:
            continue
    return orgs


def org_dir(org_id: str) -> Path:
    """Directory holding an org's config and generated artefacts. Rejects ids that could escape orgs/."""
    if not _ORG_ID_RE.match(org_id or ""):
        raise ValueError(f"Invalid org id: {org_id!r}")
    return _ORGS_DIR / org_id


def get_org(org_id: str) -> dict | None:
    try:
        cfg_path = org_dir(org_id) / "config.yaml"
    except ValueError:
        return None
    if not cfg_path.exists():
        return None
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def get_org_sources(org_id: str) -> dict:
    """
    Return sources for this org with full enabled/disabled status for all connectors,
    and file listings for schema folders and document folders.
    """
    org = get_org(org_id)
    if not org:
        return {}

    sources = org.get("sources", {})

    # build connector list — all known connectors, enabled state from config
    configured = {c["name"]: c["enabled"] for c in sources.get("live_connectors", [])}
    connectors = [
        {
            "name": c,
            "enabled": configured.get(c, False),
            "supported": True,
        }
        for c in ALL_CONNECTORS
    ]

    # resolve schema files from configured folders
    schema_files = []
    for folder in sources.get("schema_folders", []):
        folder_path = _ORGS_DIR.parent / folder["path"]
        if folder_path.exists():
            for fp in sorted(folder_path.rglob("*")):
                if fp.is_file() and fp.suffix.lower() in (".sql", ".json", ".yaml", ".yml") and not fp.name.startswith("."):
                    schema_files.append({
                        "name": fp.name,
                        "path": str(fp),
                        "folder": folder["path"],
                        "description": folder.get("description", ""),
                    })

    # resolve document files from configured folders
    doc_files = []
    for folder in sources.get("document_folders", []):
        folder_path = _ORGS_DIR.parent / folder["path"]
        if folder_path.exists():
            for fp in sorted(folder_path.rglob("*")):
                if fp.is_file() and fp.suffix.lower() in (".txt", ".md", ".pdf") and not fp.name.startswith("."):
                    doc_files.append({
                        "name": fp.name,
                        "path": str(fp),
                        "folder": folder["path"],
                        "description": folder.get("description", ""),
                    })

    return {
        "connectors": connectors,
        "schema_files": schema_files,
        "documents": doc_files,
    }
