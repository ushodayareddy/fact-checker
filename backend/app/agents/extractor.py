"""Claim Extractor: turn input (text or URL) into atomic, checkable claims."""

from __future__ import annotations

import re

import httpx
import trafilatura
from pydantic import BaseModel, Field

from ..config import get_settings
from ..llm import OllamaClient
from ..models import Claim
from ..state import PipelineState

_URL_RE = re.compile(r"^https?://\S+$")
_MAX_CHARS = 6000  # keep prompts inside a local model's comfortable context


class _ExtractedClaim(BaseModel):
    text: str = Field(description="One atomic, self-contained, verifiable factual claim, in the ORIGINAL language")
    text_en: str = Field(description="Faithful English translation of the claim")


class _Extraction(BaseModel):
    claims: list[_ExtractedClaim]


SYSTEM = """You extract checkable factual claims from text for a fact-checking system.
Rules:
- Each claim must be atomic (one fact), self-contained (resolve pronouns and context), and verifiable.
- Skip opinions, predictions, questions, greetings and rhetoric.
- Keep `text` in the original language of the input; give a faithful English translation in `text_en`.
- Do not add facts that are not in the input. Do not correct the claim, even if you think it is wrong.
- Return at most {max_claims} claims, most check-worthy first. Return an empty list if there are none."""


def is_url(text: str) -> bool:
    return bool(_URL_RE.match(text.strip()))


async def fetch_article(url: str, client: httpx.AsyncClient | None = None) -> str:
    own = client is None
    client = client or httpx.AsyncClient(timeout=get_settings().http_timeout_s, follow_redirects=True)
    try:
        r = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (fact-checker)"})
        r.raise_for_status()
    finally:
        if own:
            await client.aclose()
    text = trafilatura.extract(r.text, url=url, favor_recall=True)
    if not text:
        raise ValueError(f"Could not extract readable text from {url}")
    return text


class ExtractorAgent:
    name = "claim_extractor"

    def __init__(self, llm: OllamaClient, http: httpx.AsyncClient | None = None):
        self.llm = llm
        self.http = http

    async def run(self, state: PipelineState) -> PipelineState:
        await state.emit(self.name, "started")
        raw = state.raw_input.strip()
        if is_url(raw):
            state.input_url = raw
            await state.emit(self.name, "progress", f"Fetching {raw}")
            state.text = await fetch_article(raw, self.http)
        else:
            state.text = raw

        max_claims = get_settings().max_claims
        result = await self.llm.generate_json(
            _Extraction,
            SYSTEM.format(max_claims=max_claims),
            state.text[:_MAX_CHARS],
        )
        claims = [c for c in result.claims if c.text.strip()][:max_claims]
        state.claims = [
            Claim(id=f"c{i + 1}", text=c.text.strip(), text_en=c.text_en.strip() or None)
            for i, c in enumerate(claims)
        ]
        if not state.claims:
            state.warnings.append("No checkable factual claims were found in the input.")
        await state.emit(
            self.name, "done", f"Extracted {len(state.claims)} claim(s)",
            claims=[c.model_dump() for c in state.claims],
        )  # fmt: skip
        return state
