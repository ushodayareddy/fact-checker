"""Claim Router: classify each claim and choose which evidence sources to query, in priority order.

Keyword rules run on the English rendering first (cheap, deterministic). Claims the rules can't
place with confidence go to the LLM. The routing table is the single source of truth for which
adapters run for each claim type.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from ..llm import LLMError, OllamaClient
from ..models import Claim, ClaimType
from ..state import PipelineState

ROUTES: dict[ClaimType, list[str]] = {
    ClaimType.STATISTICAL: ["govt", "wikidata", "web"],
    ClaimType.VIRAL: ["factcheck", "web", "govt"],
    ClaimType.ENTITY: ["wikipedia", "wikidata", "web"],
    ClaimType.BREAKING: ["web", "factcheck"],
    ClaimType.HEALTH: ["factcheck", "govt", "wikipedia"],
}

_RULES: list[tuple[ClaimType, re.Pattern]] = [
    (
        ClaimType.HEALTH,
        re.compile(
            r"\b(cure[sd]?|vaccine|vaccination|covid|cancer|diabetes|disease|virus|medicine|"
            r"doctor|hospital|symptom|treatment|health|ayush|icmr)\b", re.I),
    ),
    (
        ClaimType.STATISTICAL,
        re.compile(
            r"\b(gdp|budget|crore|lakh|percent|per cent|%|inflation|unemployment|census|"
            r"population|rupees?|rs\.?|tax|subsidy|scheme|rbi|repo rate|growth rate|"
            r"election commission|seats?|votes?|turnout)\b", re.I),
    ),
    (
        ClaimType.VIRAL,
        re.compile(
            r"\b(forward(ed)?|whatsapp|viral|share this|shocking|banned|free (recharge|data|gift)|"
            r"will be (shut|banned|cancelled)|nasa (says|confirmed)|unesco (declared|announced))\b", re.I),
    ),
    (
        ClaimType.BREAKING,
        re.compile(r"\b(today|yesterday|last night|this week|just now|breaking|announced|arrested)\b", re.I),
    ),
]  # fmt: skip


class _Classification(BaseModel):
    claim_type: ClaimType


SYSTEM = """Classify a factual claim into exactly one type:
- statistical: numbers, budgets, economic/government data, policy, elections results
- viral: rumours and forwards typical of WhatsApp/social media, miracle claims, hoaxes
- entity: general knowledge about a person, place, organisation, historical event
- breaking: a very recent news event
- health: medicine, disease, nutrition, science"""


def classify_by_rules(text: str) -> ClaimType | None:
    """Return a type only when exactly one rule family matches; ambiguous or none -> None."""
    hits = [ctype for ctype, pat in _RULES if pat.search(text)]
    return hits[0] if len(hits) == 1 else None


class RouterAgent:
    name = "claim_router"

    def __init__(self, llm: OllamaClient):
        self.llm = llm

    async def classify(self, claim: Claim) -> ClaimType:
        text = claim.text_en or claim.text
        by_rule = classify_by_rules(text)
        if by_rule is not None:
            return by_rule
        try:
            return (await self.llm.generate_json(_Classification, SYSTEM, text)).claim_type
        except LLMError:
            return ClaimType.ENTITY  # safest broad default: reference sources + web

    async def run(self, state: PipelineState) -> PipelineState:
        await state.emit(self.name, "started")
        for claim in state.claims:
            claim.claim_type = await self.classify(claim)
            await state.emit(
                self.name, "progress", f"{claim.id}: {claim.claim_type.value}",
                claim_id=claim.id, sources=ROUTES[claim.claim_type],
            )  # fmt: skip
        await state.emit(self.name, "done")
        return state
