"""Verdict Synthesizer: aggregate stances into a verdict, then explain it in the user's language.

Label and confidence are computed deterministically from credibility-weighted stances so they are
auditable and testable. The LLM only writes the natural-language explanation, and is told the
verdict rather than asked to decide it.
"""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import BaseModel

from ..llm import LLMError, OllamaClient
from ..models import (
    Claim, Evidence, LanguageTier, Language, SourceScore, Stance, StanceJudgment, Verdict, VerdictLabel,
)  # fmt: skip
from ..state import PipelineState

# Tunable thresholds. Chosen conservatively: it is worse to confidently mislabel than to say "unverifiable".
MIN_TOTAL_WEIGHT = 0.5  # below this much credible stance weight we don't have enough to judge
DECISIVE_SHARE = 0.75  # one side must hold this share of stance weight to win outright
MIN_DECISIVE_WEIGHT = 0.7  # ...and have at least this much absolute weight behind it
MIXED_MIN_SHARE = 0.25  # both sides above this share -> contested
CORROBORATION_BONUS = 0.05  # per extra independent agreeing domain, capped
CONFIDENCE_CAP = {LanguageTier.HIGH: 0.95, LanguageTier.MEDIUM: 0.8, LanguageTier.LOW: 0.6}
TIER_FACTCHECK = "ifcn_factchecker"


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def aggregate(
    evidence: list[Evidence],
    scores: dict[str, SourceScore],
    stances: list[StanceJudgment],
    tier: LanguageTier,
) -> tuple[VerdictLabel, float, list[str], list[str]]:
    """Return (label, confidence, citation ids, caveats)."""
    by_id = {e.id: e for e in evidence}
    weight = {Stance.SUPPORTS: 0.0, Stance.REFUTES: 0.0}
    domains: dict[Stance, set[str]] = {Stance.SUPPORTS: set(), Stance.REFUTES: set()}
    cites: dict[Stance, list[tuple[float, str]]] = {Stance.SUPPORTS: [], Stance.REFUTES: []}
    factcheck_refutes = False

    for j in stances:
        if j.stance == Stance.NEUTRAL or j.evidence_id not in scores or j.evidence_id not in by_id:
            continue
        cred = scores[j.evidence_id].credibility
        weight[j.stance] += cred
        domains[j.stance].add(_domain(by_id[j.evidence_id].url))
        cites[j.stance].append((cred, j.evidence_id))
        if j.stance == Stance.REFUTES and scores[j.evidence_id].tier == TIER_FACTCHECK:
            factcheck_refutes = True

    sup, ref = weight[Stance.SUPPORTS], weight[Stance.REFUTES]
    total = sup + ref
    caveats: list[str] = []

    def ranked(stance: Stance) -> list[str]:
        return [eid for _, eid in sorted(cites[stance], reverse=True)]

    if total < MIN_TOTAL_WEIGHT:
        return VerdictLabel.UNVERIFIABLE, 0.0, [], ["Not enough credible evidence to judge this claim."]

    sup_share, ref_share = sup / total, ref / total
    if ref_share >= MIXED_MIN_SHARE and sup_share >= MIXED_MIN_SHARE:
        if factcheck_refutes:
            label, winner = VerdictLabel.MISLEADING, Stance.REFUTES
            caveats.append("Credible sources disagree; an established fact-checker rates the claim against it.")
        else:
            label, winner = VerdictLabel.PARTLY_TRUE, Stance.SUPPORTS if sup >= ref else Stance.REFUTES
            caveats.append("Credible sources disagree; the claim may be only partly accurate.")
        share = max(sup_share, ref_share)
        base = 0.4 + 0.2 * share
        citations = ranked(Stance.SUPPORTS)[:2] + ranked(Stance.REFUTES)[:2]
    else:
        winner = Stance.SUPPORTS if sup_share >= DECISIVE_SHARE else Stance.REFUTES
        win_w, win_share = (sup, sup_share) if winner == Stance.SUPPORTS else (ref, ref_share)
        if win_share < DECISIVE_SHARE or win_w < MIN_DECISIVE_WEIGHT:
            caveats.append("Evidence leans one way but is thin; treat as tentative.")
            label = VerdictLabel.UNVERIFIABLE
            base = 0.3
        else:
            label = VerdictLabel.TRUE if winner == Stance.SUPPORTS else VerdictLabel.FALSE
            base = min(0.95, 0.5 + 0.35 * min(1.0, win_w / 2.0) + 0.1 * win_share)
        citations = ranked(winner)[:4]

    extra = max(0, len(domains[winner]) - 1)
    base += min(0.1, CORROBORATION_BONUS * extra)
    conf = round(min(base, CONFIDENCE_CAP[tier]), 2)
    if tier == LanguageTier.LOW:
        caveats.append("Low-resource language: confidence is capped.")
    if len({_domain(e.url) for e in evidence}) < 2:
        caveats.append("Evidence comes from a single domain.")
    return label, conf, citations, caveats


class _Explanation(BaseModel):
    explanation: str


SYSTEM = """You write the explanation for a fact-check verdict that has ALREADY been decided.
- Write in {language} ({native}). Keep it to 2-4 sentences a general reader understands.
- State the verdict plainly, then the main reason, citing sources by their bracketed ids like [wikipedia:ab12].
- Use only the evidence provided. Do not add facts or soften or change the verdict.
- If the verdict is unverifiable, say what is missing instead of guessing."""


class SynthesizerAgent:
    name = "verdict_synthesizer"

    def __init__(self, llm: OllamaClient):
        self.llm = llm

    async def _explain(self, claim: Claim, label: VerdictLabel, citations: list[str],
                       evidence: list[Evidence], stances: list[StanceJudgment], lang: Language) -> str:  # fmt: skip
        by_id = {e.id: e for e in evidence}
        quotes = {j.evidence_id: j for j in stances}
        lines = [
            f"[{cid}] {by_id[cid].title} ({_domain(by_id[cid].url)}): "
            f"{quotes[cid].stance.value}; \"{quotes[cid].quote}\""
            for cid in citations if cid in by_id and cid in quotes
        ]  # fmt: skip
        user = f"CLAIM: {claim.text}\nVERDICT: {label.value}\nEVIDENCE:\n" + ("\n".join(lines) or "(none)")
        try:
            out = await self.llm.generate_json(
                _Explanation, SYSTEM.format(language=lang.name, native=lang.native_name), user
            )
            return out.explanation.strip()
        except LLMError:
            return f"Verdict: {label.value}. (An explanation could not be generated; see the cited sources.)"

    async def run(self, state: PipelineState) -> PipelineState:
        await state.emit(self.name, "started")
        lang = state.language
        for claim in state.claims:
            evidence = state.evidence.get(claim.id, [])
            label, conf, citations, caveats = aggregate(
                evidence, state.scores, state.stances.get(claim.id, []), lang.tier
            )
            explanation = await self._explain(
                claim, label, citations, evidence, state.stances.get(claim.id, []), lang
            )
            state.verdicts.append(
                Verdict(claim_id=claim.id, label=label, confidence=conf, explanation=explanation,
                        citations=citations, caveats=caveats)
            )  # fmt: skip
            await state.emit(self.name, "progress", f"{claim.id}: {label.value} ({conf:.2f})", claim_id=claim.id)
        await state.emit(self.name, "done")
        return state
