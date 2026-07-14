import json
import httpx
from ..provider import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, cfg: dict):
        import os
        self.model = cfg.get("model", "gpt-4o")
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.base_url = "https://api.openai.com/v1"

    def _call(self, messages: list, json_mode: bool = False) -> str:
        body: dict = {"model": self.model, "messages": messages}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        r = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=body,
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def generate_structured(self, prompt: str, schema: dict) -> dict:
        schema_hint = json.dumps(schema, indent=2)
        full_prompt = f"{prompt}\n\nReturn valid JSON matching this schema:\n{schema_hint}"
        raw = self._call(
            [{"role": "user", "content": full_prompt}],
            json_mode=True,
        )
        return self._extract_json(raw, schema)

    def generate_text(self, prompt: str) -> str:
        return self._call([{"role": "user", "content": prompt}])

    def embed(self, text: str) -> list[float]:
        r = httpx.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": "text-embedding-3-small", "input": text},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]
