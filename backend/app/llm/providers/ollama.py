import json
import httpx
from ..provider import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(self, cfg: dict):
        self.model = cfg.get("model", "llama3.1")
        self.embed_model = cfg.get("embedding_model", "nomic-embed-text")
        self.base_url = cfg.get("ollama_base_url", "http://localhost:11434")

    def _chat(self, prompt: str) -> str:
        r = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",
            },
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["message"]["content"]

    def generate_structured(self, prompt: str, schema: dict) -> dict:
        schema_hint = json.dumps(schema, indent=2)
        full_prompt = f"{prompt}\n\nReturn valid JSON matching this schema:\n{schema_hint}"
        raw = self._chat(full_prompt)
        return self._extract_json(raw, schema)

    def generate_text(self, prompt: str) -> str:
        r = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["message"]["content"]

    def embed(self, text: str) -> list[float]:
        r = httpx.post(
            f"{self.base_url}/api/embeddings",
            json={"model": self.embed_model, "prompt": text},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["embedding"]
