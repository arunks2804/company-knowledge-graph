"""Loads documents from the local filesystem and extracts plain text."""
from __future__ import annotations

import os
from pathlib import Path


def _read_txt(path: Path) -> str:
    return path.read_text(errors="replace")


def _read_pdf(path: Path) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    except ImportError:
        return f"[pdfplumber not installed — cannot read {path.name}]"


READERS = {
    ".txt": _read_txt,
    ".md": _read_txt,
    ".pdf": _read_pdf,
}


def extract_documents(directory: str | Path) -> list[dict]:
    """
    Walk `directory` recursively.
    Returns list of {path, name, text} dicts for supported file types.
    """
    root = Path(directory)
    docs = []
    for fp in sorted(root.rglob("*")):
        if not fp.is_file():
            continue
        reader = READERS.get(fp.suffix.lower())
        if reader is None:
            continue
        text = reader(fp)
        if text.strip():
            docs.append(
                {
                    "path": str(fp),
                    "name": fp.name,
                    "text": text,
                }
            )
    return docs
