"""Abstract LLM provider interface. All pipeline code calls this — never a provider SDK directly."""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml


def load_config() -> dict:
    cfg_path = Path(__file__).parent.parent.parent / "config" / "llm_config.yaml"
    with open(cfg_path) as f:
        return yaml.safe_load(f)


class LLMProvider(ABC):
    @abstractmethod
    def generate_structured(self, prompt: str, schema: dict) -> dict:
        """Return parsed JSON matching `schema`. Validates and retries on malformed output."""

    @abstractmethod
    def generate_text(self, prompt: str) -> str:
        """Return free-form text — used for NL descriptions and narrative synthesis."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Return an embedding vector for the given text."""

    def _extract_json(self, raw: str, schema: dict, retries: int = 2) -> dict:
        """Strip markdown fences and parse JSON, with basic schema key validation."""
        text = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        # find first { ... }
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned malformed JSON: {exc}\nRaw: {raw[:500]}") from exc
        return parsed


def get_provider() -> LLMProvider:
    cfg = load_config()
    p = cfg.get("provider", "ollama")
    if p == "ollama":
        from .providers.ollama import OllamaProvider
        return OllamaProvider(cfg)
    if p == "anthropic":
        from .providers.anthropic import AnthropicProvider
        return AnthropicProvider(cfg)
    if p == "openai":
        from .providers.openai import OpenAIProvider
        return OpenAIProvider(cfg)
    raise ValueError(f"Unknown provider: {p}")
