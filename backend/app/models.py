from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ClaimType(StrEnum):
    STATISTICAL = "statistical"  # numbers, budgets, policy, government data
    VIRAL = "viral"  # WhatsApp/social-media style rumours
    ENTITY = "entity"  # general knowledge about people, places, events
    BREAKING = "breaking"  # recent news
    HEALTH = "health"  # health / science


class Stance(StrEnum):
    SUPPORTS = "supports"
    REFUTES = "refutes"
    NEUTRAL = "neutral"


class VerdictLabel(StrEnum):
    TRUE = "true"
    FALSE = "false"
    MISLEADING = "misleading"
    PARTLY_TRUE = "partly_true"
    UNVERIFIABLE = "unverifiable"


class LanguageTier(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Language(BaseModel):
    code: str
    name: str
    native_name: str
    script: str
    tier: LanguageTier
    wiki_code: str | None = None
    indictrans_code: str | None = None


class Claim(BaseModel):
    id: str
    text: str  # in the original language
    text_en: str | None = None  # English rendering used for English-language retrieval
    claim_type: ClaimType | None = None


class Evidence(BaseModel):
    id: str
    claim_id: str
    source: str  # adapter name: wikipedia, govt, factcheck, web, ...
    url: str
    title: str
    snippet: str
    lang: str | None = None
    published: str | None = None  # ISO date when known
    relevance: float = 0.0


class SourceScore(BaseModel):
    evidence_id: str
    credibility: float = Field(ge=0.0, le=1.0)
    tier: str  # e.g. "government", "ifcn_factchecker", "major_outlet", "reference", "unknown"
    reasons: list[str] = Field(default_factory=list)


class StanceJudgment(BaseModel):
    evidence_id: str
    stance: Stance
    quote: str = ""
    rationale: str = ""


class Verdict(BaseModel):
    claim_id: str
    label: VerdictLabel
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str  # in the user's language
    citations: list[str] = Field(default_factory=list)  # evidence ids
    caveats: list[str] = Field(default_factory=list)


class TraceEvent(BaseModel):
    agent: str
    status: str  # started | progress | done | error
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
