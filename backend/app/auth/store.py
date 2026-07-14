"""File-backed user and API key store. Sessions are kept in-memory."""
from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path

import bcrypt

_AUTH_PATH = Path(__file__).parent.parent.parent / "config" / "auth.json"

# token -> user_id (in-memory, cleared on restart)
_sessions: dict[str, str] = {}


# ── helpers ───────────────────────────────────────────────────────────────────

def _load() -> dict:
    if not _AUTH_PATH.exists():
        return {"users": [], "api_keys": []}
    return json.loads(_AUTH_PATH.read_text())


def _save(data: dict) -> None:
    _AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    _AUTH_PATH.write_text(json.dumps(data, indent=2))


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ── users ─────────────────────────────────────────────────────────────────────

def get_user_by_username(username: str) -> dict | None:
    for u in _load()["users"]:
        if u["username"] == username:
            return u
    return None


def get_user_by_id(user_id: str) -> dict | None:
    for u in _load()["users"]:
        if u["user_id"] == user_id:
            return u
    return None


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def create_user(username: str, password: str, role: str) -> dict:
    data = _load()
    user = {
        "user_id": secrets.token_hex(8),
        "username": username,
        "password_hash": _hash_password(password),
        "role": role,
    }
    data["users"].append(user)
    _save(data)
    return user


def has_users() -> bool:
    return bool(_load()["users"])


# ── sessions ──────────────────────────────────────────────────────────────────

def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = user_id
    return token


def get_session_user_id(token: str) -> str | None:
    return _sessions.get(token)


def delete_session(token: str) -> None:
    _sessions.pop(token, None)


# ── API keys ──────────────────────────────────────────────────────────────────

def generate_api_key(name: str, role: str, created_by: str) -> tuple[str, dict]:
    """Returns (raw_key, stored_record). raw_key is shown once and never stored."""
    raw = f"sk_{secrets.token_urlsafe(32)}"
    record = {
        "key_id": secrets.token_hex(8),
        "name": name,
        "key_hash": _hash_key(raw),
        "role": role,
        "created_by": created_by,
    }
    data = _load()
    data["api_keys"].append(record)
    _save(data)
    return raw, record


def get_api_key_by_token(raw: str) -> dict | None:
    key_hash = _hash_key(raw)
    for k in _load()["api_keys"]:
        if k["key_hash"] == key_hash:
            return k
    return None


def list_api_keys() -> list[dict]:
    return [
        {k: v for k, v in rec.items() if k != "key_hash"}
        for rec in _load()["api_keys"]
    ]


def delete_api_key(key_id: str) -> None:
    data = _load()
    data["api_keys"] = [k for k in data["api_keys"] if k["key_id"] != key_id]
    _save(data)
