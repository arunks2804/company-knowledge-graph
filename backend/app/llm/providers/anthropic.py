import json
import httpx
from ..provider import LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self, cfg: dict):
        import os
        self.model = cfg.get("model", "claude-sonnet-4-6")
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = "https://api.anthropic.com/v1"

    def _call(self, prompt: str) -> str:
        r = httpx.post(
            f"{self.base_url}/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"]

    def generate_structured(self, prompt: str, schema: dict) -> dict:
        schema_hint = json.dumps(schema, indent=2)
        full_prompt = f"{prompt}\n\nReturn valid JSON matching this schema:\n{schema_hint}\n\nReturn only JSON, no explanation."
        raw = self._call(full_prompt)
        return self._extract_json(raw, schema)

    def generate_text(self, prompt: str) -> str:
        return self._call(prompt)

    def embed(self, text: str) -> list[float]:
        # Anthropic does not yet have a public embeddings endpoint — fall back to Ollama
        import os
        base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        r = httpx.post(
            f"{base}/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": text},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["embedding"]
