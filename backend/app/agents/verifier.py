"""Claim Verifier: judge, per evidence item, whether it supports, refutes or is neutral to the claim.

The model must back any supports/refutes judgment with a quote copied from the evidence. A quote
that does not appear in the evidence is treated as a hallucination and the stance is downgraded
to neutral rather than trusted.
"""

from __future__ import annotations

import asyncio
import re

from pydantic import BaseModel, Field

from ..llm import LLMError, OllamaClient
from ..models import Claim, Evidence, Stance, StanceJudgment
from ..state import PipelineState

_CONCURRENCY = 2  # local models serialise anyway; more just adds queueing latency


class _Judgment(BaseModel):
    stance: Stance
    quote: str = Field(default="", description="Exact text copied from the evidence that justifies the stance")
    rationale: str = Field(default="", description="One sentence, in English")


SYSTEM = """You judge whether a piece of evidence supports or refutes a factual claim.
- supports: the evidence directly states or clearly implies the claim is true.
- refutes: the evidence directly states or clearly implies the claim is false (including a fact-checker's
  rating such as False / Misleading / Fake).
- neutral: related but does not settle the claim, is about something different, or is too vague.
Rules:
- Judge only from the evidence text given. Do not use outside knowledge.
- For supports or refutes, `quote` MUST be copied verbatim from the evidence. If you cannot quote it, answer neutral.
- Pay attention to numbers, dates, places and negation: a claim with a different number than the evidence is not supported."""

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip().lower()


def quote_in_evidence(quote: str, ev: Evidence) -> bool:
    q = _norm(quote)
    return bool(q) and q in _norm(f"{ev.title} {ev.snippet}")


class VerifierAgent:
    name = "claim_verifier"

    def __init__(self, llm: OllamaClient):
        self.llm = llm

    async def judge(self, claim: Claim, ev: Evidence) -> StanceJudgment:
        user = (
            f"CLAIM: {claim.text_en or claim.text}\n"
            f"(original wording: {claim.text})\n\n"
            f"EVIDENCE TITLE: {ev.title}\nEVIDENCE SOURCE: {ev.url}\nEVIDENCE TEXT: {ev.snippet}"
        )
        try:
            j = await self.llm.generate_json(_Judgment, SYSTEM, user)
        except LLMError as e:
            return StanceJudgment(evidence_id=ev.id, stance=Stance.NEUTRAL, rationale=f"Judgment failed: {e}")

        if j.stance != Stance.NEUTRAL and not quote_in_evidence(j.quote, ev):
            return StanceJudgment(
                evidence_id=ev.id, stance=Stance.NEUTRAL,
                rationale="Model gave a stance without a verifiable quote; ignored.",
            )  # fmt: skip
        return StanceJudgment(evidence_id=ev.id, stance=j.stance, quote=j.quote, rationale=j.rationale)

    async def run(self, state: PipelineState) -> PipelineState:
        await state.emit(self.name, "started")
        sem = asyncio.Semaphore(_CONCURRENCY)

        async def bounded(claim: Claim, ev: Evidence) -> StanceJudgment:
            async with sem:
                return await self.judge(claim, ev)

        for claim in state.claims:
            items = state.evidence.get(claim.id, [])
            state.stances[claim.id] = list(await asyncio.gather(*(bounded(claim, e) for e in items)))
            counts = {s.value: sum(1 for j in state.stances[claim.id] if j.stance == s) for s in Stance}
            await state.emit(self.name, "progress", f"{claim.id}: {counts}", claim_id=claim.id, counts=counts)
        await state.emit(self.name, "done")
        return state
