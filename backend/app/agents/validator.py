"""Source Validator: score each piece of evidence for credibility.

score = domain-tier prior, adjusted by recency and relevance. Everything is deterministic and
explainable; each adjustment is recorded in `reasons` so the UI can show why a source was trusted
or discounted.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import yaml

from ..models import Evidence, SourceScore
from ..state import PipelineState

_DATA = Path(__file__).parent.parent / "data" / "source_tiers.yaml"


@lru_cache
def _registry() -> tuple[list[tuple[str, float, str]], dict]:
    raw = yaml.safe_load(_DATA.read_text(encoding="utf-8"))
    entries = [
        (domain, tier["credibility"], name)
        for name, tier in raw["tiers"].items()
        for domain in tier["domains"]
    ]
    # Most specific (longest) domain first so reuters.com/fact-check beats reuters.com.
    entries.sort(key=lambda e: len(e[0]), reverse=True)
    return entries, raw["default"]


def lookup_domain(url: str) -> tuple[str, float]:
    """Return (tier name, prior credibility) for a URL."""
    entries, default = _registry()
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    host_and_path = host + parsed.path.lower()
    for domain, cred, tier in entries:
        if "/" in domain:
            if host_and_path.startswith(domain):
                return tier, cred
        elif host == domain or host.endswith("." + domain):
            return tier, cred
    return default["tier"], default["credibility"]


def _age_years(published: str | None, today: date) -> float | None:
    if not published:
        return None
    try:
        return (today - date.fromisoformat(published[:10])).days / 365.25
    except ValueError:
        return None


def score_evidence(ev: Evidence, today: date | None = None) -> SourceScore:
    today = today or date.today()
    tier, cred = lookup_domain(ev.url)
    reasons = [f"Domain tier: {tier} (prior {cred:.2f})"]

    age = _age_years(ev.published, today)
    if age is not None and age > 3 and tier != "reference":
        cred -= min(0.15, 0.03 * (age - 3))
        reasons.append(f"Published {age:.1f} years ago; may be outdated")
    elif age is None and tier in ("unknown", "major_outlet"):
        cred -= 0.03
        reasons.append("No publication date available")

    if ev.relevance and ev.relevance < 0.3:
        cred -= 0.1
        reasons.append(f"Low relevance to the claim ({ev.relevance:.2f})")

    return SourceScore(
        evidence_id=ev.id, credibility=max(0.0, min(1.0, round(cred, 3))), tier=tier, reasons=reasons
    )


class ValidatorAgent:
    name = "source_validator"

    async def run(self, state: PipelineState) -> PipelineState:
        await state.emit(self.name, "started")
        for claim_id, items in state.evidence.items():
            for ev in items:
                state.scores[ev.id] = score_evidence(ev)
        # Corroboration is judged in the synthesizer, after stances are known: retrieving many
        # domains says nothing about whether they agree.
        n = len(state.scores)
        await state.emit(self.name, "done", f"Scored {n} source(s)", count=n)
        return state
