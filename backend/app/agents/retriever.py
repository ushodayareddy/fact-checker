"""Evidence Retriever: run the routed source adapters concurrently, dedupe, and rank.

Queries run in both the claim's language and English (local-language web content is thin).
A failing or timing-out adapter degrades the result instead of failing the pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import math

from ..config import get_settings
from ..llm import LLMError, OllamaClient
from ..models import Claim, Evidence
from ..sources.base import SourceAdapter
from ..state import PipelineState
from .router import ROUTES

log = logging.getLogger(__name__)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _lexical_overlap(query: str, text: str) -> float:
    q = {t for t in query.lower().split() if len(t) > 2}
    return len(q & set(text.lower().split())) / len(q) if q else 0.0


class RetrieverAgent:
    name = "evidence_retriever"

    def __init__(self, llm: OllamaClient, adapters: dict[str, SourceAdapter]):
        self.llm, self.adapters = llm, adapters

    def _queries(self, claim: Claim, lang: str) -> list[tuple[str, str]]:
        """(query, language) pairs: native first, then English if different."""
        queries = [(claim.text, lang)]
        if claim.text_en and lang != "en" and claim.text_en != claim.text:
            queries.append((claim.text_en, "en"))
        return queries

    async def _one(self, adapter: SourceAdapter, query: str, lang: str, claim_id: str, state: PipelineState):
        timeout = get_settings().http_timeout_s * 2
        try:
            return await asyncio.wait_for(adapter.search(query, lang, claim_id), timeout)
        except Exception as e:  # noqa: BLE001 - one bad source must not sink the run
            log.warning("source %s failed: %r", adapter.name, e)
            state.warnings.append(f"Source '{adapter.name}' failed: {type(e).__name__}")
            await state.emit(self.name, "error", f"{adapter.name} failed", source=adapter.name)
            return []

    async def _rank(self, claim: Claim, items: list[Evidence]) -> list[Evidence]:
        query = claim.text_en or claim.text
        try:
            vecs = await self.llm.embed([query] + [f"{e.title}. {e.snippet}" for e in items])
            for ev, v in zip(items, vecs[1:]):
                ev.relevance = round(max(0.0, _cosine(vecs[0], v)), 3)
        except LLMError:
            # Embedding model unavailable: fall back to lexical overlap rather than failing.
            for ev in items:
                ev.relevance = round(_lexical_overlap(query, f"{ev.title} {ev.snippet}"), 3)
        return sorted(items, key=lambda e: e.relevance, reverse=True)

    async def run(self, state: PipelineState) -> PipelineState:
        await state.emit(self.name, "started")
        lang = state.language.code if state.language else "en"
        limit = get_settings().max_evidence_per_claim

        for claim in state.claims:
            route = ROUTES[claim.claim_type]
            active = [self.adapters[n] for n in route if n in self.adapters and self.adapters[n].available()]
            skipped = [n for n in route if n not in self.adapters or not self.adapters[n].available()]
            if skipped:
                await state.emit(self.name, "progress", f"{claim.id}: skipping unavailable {skipped}")

            jobs = [
                self._one(a, q, ql, claim.id, state) for a in active for q, ql in self._queries(claim, lang)
            ]
            results = await asyncio.gather(*jobs)

            seen: dict[str, Evidence] = {}
            for batch in results:
                for ev in batch:
                    seen.setdefault(ev.url, ev)  # dedupe by URL, keep first (higher-priority source)
            ranked = await self._rank(claim, list(seen.values())) if seen else []
            state.evidence[claim.id] = ranked[:limit]
            await state.emit(
                self.name, "progress", f"{claim.id}: {len(state.evidence[claim.id])} evidence item(s)",
                claim_id=claim.id, sources=[a.name for a in active],
            )  # fmt: skip
        await state.emit(self.name, "done")
        return state
