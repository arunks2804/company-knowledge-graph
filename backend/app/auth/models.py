from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    read_only = "read_only"
    read_write = "read_write"


@dataclass
class Principal:
    principal_id: str
    name: str
    role: Role
    kind: str  # "user" | "api_key"
