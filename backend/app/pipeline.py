"""Pipeline orchestrator: wires the agents together and streams trace events."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from .agents.extractor import ExtractorAgent
from .agents.language import LanguageAgent
from .agents.retriever import RetrieverAgent
from .agents.router import RouterAgent
from .agents.synthesizer import SynthesizerAgent
from .agents.validator import ValidatorAgent
from .agents.verifier import VerifierAgent
from .llm import LLMError, OllamaClient
from .models import TraceEvent
from .sources.base import SourceAdapter
from .sources.factcheck import make_factcheck_source
from .sources.govt import make_govt_source
from .sources.web import WebSearch
from .sources.wiki import WikidataSource, WikipediaSource
from .state import PipelineState

log = logging.getLogger(__name__)


def build_adapters() -> dict[str, SourceAdapter]:
    web = WebSearch()
    adapters = [WikipediaSource(), WikidataSource(), make_govt_source(web), make_factcheck_source(web), web]
    return {a.name: a for a in adapters}


class Pipeline:
    def __init__(self, llm: OllamaClient, adapters: dict[str, SourceAdapter] | None = None):
        self.llm = llm
        adapters = adapters if adapters is not None else build_adapters()
        self.agents = [
            ExtractorAgent(llm),
            LanguageAgent(),  # runs after extraction so URL inputs are detected from article text
            RouterAgent(llm),
            RetrieverAgent(llm, adapters),
            ValidatorAgent(),
            VerifierAgent(llm),
            SynthesizerAgent(llm),
        ]

    async def run(self, state: PipelineState) -> PipelineState:
        for agent in self.agents:
            await agent.run(state)
            if agent.name == "claim_extractor" and not state.claims:
                break  # nothing to check; downstream agents have no work
        return state

    async def stream(self, raw_input: str) -> AsyncIterator[dict]:
        """Yield {"event": "trace"|"result"|"error", "data": dict} as the pipeline runs."""
        queue: asyncio.Queue[TraceEvent | None] = asyncio.Queue()

        async def sink(e: TraceEvent) -> None:
            await queue.put(e)

        state = PipelineState(raw_input=raw_input, trace=sink)
        error: Exception | None = None

        async def worker() -> None:
            nonlocal error
            try:
                await self.run(state)
            except Exception as e:  # noqa: BLE001 - surfaced to the client as an error event
                log.exception("pipeline failed")
                error = e
            finally:
                await queue.put(None)

        task = asyncio.create_task(worker())
        try:
            while (item := await queue.get()) is not None:
                yield {"event": "trace", "data": item.model_dump()}
            await task
            if error is not None:
                msg = str(error) if isinstance(error, (LLMError, ValueError)) else "Internal error while checking the claim."
                yield {"event": "error", "data": {"message": msg}}
                return
            yield {"event": "result", "data": result_payload(state)}
        finally:
            if not task.done():
                task.cancel()  # client disconnected mid-run


def result_payload(state: PipelineState) -> dict:
    return {
        "language": state.language.model_dump() if state.language else None,
        "claims": [c.model_dump() for c in state.claims],
        "evidence": {cid: [e.model_dump() for e in items] for cid, items in state.evidence.items()},
        "scores": {eid: s.model_dump() for eid, s in state.scores.items()},
        "stances": {cid: [j.model_dump() for j in js] for cid, js in state.stances.items()},
        "verdicts": [v.model_dump() for v in state.verdicts],
        "warnings": state.warnings,
    }
