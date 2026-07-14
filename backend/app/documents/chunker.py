"""Splits raw text into overlapping character-level chunks."""
from __future__ import annotations

from pathlib import Path

import yaml


def _cfg() -> dict:
    p = Path(__file__).parent.parent.parent / "config" / "llm_config.yaml"
    with open(p) as f:
        return yaml.safe_load(f).get("chunking", {})


def chunk_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    cfg = _cfg()
    size = chunk_size or cfg.get("chunk_size", 800)
    ov = overlap or cfg.get("overlap", 150)

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += size - ov
    return chunks
