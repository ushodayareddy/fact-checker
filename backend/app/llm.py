"""Thin async Ollama client with schema-validated JSON output.

Agents never rely on native tool calling (uneven across local models). Instead they request
JSON constrained by a Pydantic schema via Ollama's `format` parameter, validate it, and retry
with the validation error fed back to the model.
"""

from __future__ import annotations

import json
import logging
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import Settings, get_settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._client = client or httpx.AsyncClient(
            base_url=self.settings.ollama_url, timeout=self.settings.llm_timeout_s
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> dict:
        """Return {ok, models}; never raises so /api/health can report Ollama being down."""
        try:
            r = await self._client.get("/api/tags", timeout=3.0)
            r.raise_for_status()
            return {"ok": True, "models": [m["name"] for m in r.json().get("models", [])]}
        except httpx.HTTPError as e:
            return {"ok": False, "error": str(e), "models": []}

    async def chat(self, messages: list[dict], model: str | None = None, schema: dict | None = None) -> str:
        payload: dict = {
            "model": model or self.settings.reasoning_model,
            "messages": messages,
            "stream": False,
            "think": False,  # structured output + reasoning traces interact badly on some models
            "options": {"temperature": self.settings.llm_temperature},
        }
        if schema is not None:
            payload["format"] = schema
        try:
            r = await self._client.post("/api/chat", json=payload)
            r.raise_for_status()
        except httpx.ConnectError as e:
            raise LLMError(f"Cannot reach Ollama at {self.settings.ollama_url}. Is it running?") from e
        except httpx.HTTPStatusError as e:
            raise LLMError(f"Ollama error {e.response.status_code}: {e.response.text[:300]}") from e
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama request failed: {e}") from e
        return r.json()["message"]["content"]

    async def generate_json(
        self, schema_cls: type[T], system: str, user: str, model: str | None = None
    ) -> T:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        schema = schema_cls.model_json_schema()
        last_err: Exception | None = None
        for attempt in range(self.settings.llm_json_retries + 1):
            raw = await self.chat(messages, model=model, schema=schema)
            try:
                return schema_cls.model_validate_json(raw)
            except ValidationError as e:
                last_err = e
                log.warning("LLM JSON invalid (attempt %d): %s", attempt + 1, e.errors()[:2])
                messages += [
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": "That output failed validation: "
                        f"{json.dumps(e.errors(include_url=False, include_context=False))[:600]}. "
                        "Return corrected JSON only.",
                    },
                ]
        raise LLMError(f"No valid JSON after {self.settings.llm_json_retries + 1} attempts: {last_err}")

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        try:
            r = await self._client.post(
                "/api/embed", json={"model": model or self.settings.embedding_model, "input": texts}
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMError(f"Embedding request failed: {e}") from e
        return r.json()["embeddings"]
