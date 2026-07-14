"""FastAPI router for organisation endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .config import list_orgs, get_org, get_org_sources

router = APIRouter(prefix="/orgs", tags=["organisations"])


@router.get("")
def orgs_list():
    return list_orgs()


@router.get("/{org_id}")
def org_detail(org_id: str):
    org = get_org(org_id)
    if not org:
        raise HTTPException(status_code=404, detail=f"Org '{org_id}' not found")
    return org


@router.get("/{org_id}/sources")
def org_sources(org_id: str):
    sources = get_org_sources(org_id)
    if not sources:
        raise HTTPException(status_code=404, detail=f"Org '{org_id}' not found")
    return sources
