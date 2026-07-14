from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from .models import Principal, Role
from .store import get_api_key_by_token, get_session_user_id, get_user_by_id


def get_optional_principal(request: Request) -> Principal | None:
    # Agents: Authorization: Bearer sk_...
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        raw_key = auth[7:]
        record = get_api_key_by_token(raw_key)
        if not record:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return Principal(
            principal_id=record["key_id"],
            name=record["name"],
            role=Role(record["role"]),
            kind="api_key",
        )

    # Humans: session cookie
    token = request.cookies.get("session")
    if token:
        user_id = get_session_user_id(token)
        if not user_id:
            raise HTTPException(status_code=401, detail="Session expired — please log in again")
        user = get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return Principal(
            principal_id=user["user_id"],
            name=user["username"],
            role=Role(user["role"]),
            kind="user",
        )

    return None


def require_read_only(principal: Principal | None = Depends(get_optional_principal)) -> Principal:
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return principal


def require_read_write(principal: Principal | None = Depends(get_optional_principal)) -> Principal:
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if principal.role != Role.read_write:
        raise HTTPException(status_code=403, detail="Read-write role required")
    return principal
