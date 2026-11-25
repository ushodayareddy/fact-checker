from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from .models import Claim, Evidence, Language, SourceScore, StanceJudgment, TraceEvent, Verdict

TraceSink = Callable[[TraceEvent], Awaitable[None]]


async def _noop(_: TraceEvent) -> None:
    return None


@dataclass
class PipelineState:
    """Mutable state threaded through the agents. Each agent reads and extends it."""

    raw_input: str
    input_url: str | None = None
    text: str = ""  # article text when input was a URL, else raw_input
    language: Language | None = None
    claims: list[Claim] = field(default_factory=list)
    evidence: dict[str, list[Evidence]] = field(default_factory=dict)  # claim_id -> evidence
    scores: dict[str, SourceScore] = field(default_factory=dict)  # evidence_id -> score
    stances: dict[str, list[StanceJudgment]] = field(default_factory=dict)  # claim_id -> judgments
    verdicts: list[Verdict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trace: TraceSink = _noop

    async def emit(self, agent: str, status: str, message: str = "", **data) -> None:
        await self.trace(TraceEvent(agent=agent, status=status, message=message, data=data))
