from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from .dependencies import require_read_only, require_read_write
from .models import Principal
from .store import (
    create_session,
    delete_api_key,
    delete_session,
    generate_api_key,
    get_user_by_username,
    list_api_keys,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateKeyRequest(BaseModel):
    name: str
    role: str = "read_only"


@router.post("/login")
def login(req: LoginRequest, response: Response):
    user = get_user_by_username(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_session(user["user_id"])
    response.set_cookie(
        "session", token,
        httponly=True, samesite="lax", max_age=86400 * 7,
    )
    return {"username": user["username"], "role": user["role"]}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("session")
    if token:
        delete_session(token)
    response.delete_cookie("session")
    return {"status": "logged_out"}


@router.get("/me")
def me(principal: Principal = Depends(require_read_only)):
    return {"name": principal.name, "role": principal.role, "kind": principal.kind}


@router.get("/api-keys")
def list_keys(principal: Principal = Depends(require_read_write)):
    return list_api_keys()


@router.post("/api-keys")
def create_key(req: CreateKeyRequest, principal: Principal = Depends(require_read_write)):
    if req.role not in ("read_only", "read_write"):
        raise HTTPException(status_code=400, detail="role must be read_only or read_write")
    raw, record = generate_api_key(req.name, req.role, principal.principal_id)
    return {
        "key_id": record["key_id"],
        "name": record["name"],
        "role": record["role"],
        "key": raw,  # shown once only — store it now
    }


@router.delete("/api-keys/{key_id}")
def revoke_key(key_id: str, principal: Principal = Depends(require_read_write)):
    delete_api_key(key_id)
    return {"status": "revoked", "key_id": key_id}
