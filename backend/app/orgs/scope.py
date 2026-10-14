"""Request-scoped organisation selection. Every graph read/write is partitioned by org_id."""
from __future__ import annotations

from fastapi import Header, HTTPException

from .config import get_org


def require_org(x_org_id: str = Header(..., alias="X-Org-Id")) -> str:
    """Resolve the org for this request from the X-Org-Id header; 400 if missing, 404 if unknown."""
    if not get_org(x_org_id):
        raise HTTPException(status_code=404, detail=f"Org '{x_org_id}' not found")
    return x_org_id
