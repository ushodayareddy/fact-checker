import json

import httpx
import pytest
from httpx import ASGITransport

from app.agents import extractor as ex
from app.agents import router
from app.agents import synthesizer as syn
from app.agents import verifier as ver
from app.llm import LLMError
from app.models import ClaimType, Evidence, Stance
from app.pipeline import Pipeline


class ScriptedLLM:
    """Dispatches on the requested schema, like a deterministic fake model."""

    def __init__(self, fail_extraction=False):
        self.fail_extraction = fail_extraction

    async def generate_json(self, schema_cls, system, user, model=None):
        if schema_cls is ex._Extraction:
            if self.fail_extraction:
                raise LLMError("Cannot reach Ollama at http://localhost:11434. Is it running?")
            return ex._Extraction(claims=[ex._ExtractedClaim(
                text="भारत की राजधानी दिल्ली है", text_en="India's capital is Delhi")])  # fmt: skip
        if schema_cls is router._Classification:
            return router._Classification(claim_type=ClaimType.ENTITY)
        if schema_cls is ver._Judgment:
            return ver._Judgment(stance=Stance.SUPPORTS, quote="capital of India")
        if schema_cls is syn._Explanation:
            return syn._Explanation(explanation="दावा सही है।")
        raise AssertionError(f"unexpected schema {schema_cls}")

    async def embed(self, texts, model=None):
        return [[1.0, 0.0]] * len(texts)


class FixedAdapter:
    def __init__(self, name, urls):
        self.name, self.urls = name, urls

    def available(self):
        return True

    async def search(self, query, lang, claim_id):
        return [Evidence(id=f"{self.name}:{i}", claim_id=claim_id, source=self.name, url=u, title="Delhi",
                         snippet="New Delhi is the capital of India.", published="2026-01-01")
                for i, u in enumerate(self.urls)]  # fmt: skip


def make_pipeline(llm=None):
    adapters = {
        "wikipedia": FixedAdapter("wikipedia", ["https://hi.wikipedia.org/wiki/Delhi"]),
        "wikidata": FixedAdapter("wikidata", ["https://www.wikidata.org/entity/Q987"]),
        "web": FixedAdapter("web", ["https://www.thehindu.com/delhi", "https://pib.gov.in/delhi"]),
    }
    return Pipeline(llm or ScriptedLLM(), adapters)


async def collect(pipeline, text):
    return [item async for item in pipeline.stream(text)]


async def test_full_pipeline_streams_trace_then_result():
    events = await collect(make_pipeline(), "भारत की राजधानी दिल्ली है")
    kinds = [e["event"] for e in events]
    assert kinds[-1] == "result" and set(kinds[:-1]) == {"trace"}
    agents_seen = [e["data"]["agent"] for e in events if e["event"] == "trace"]
    for agent in ["claim_extractor", "language_id", "claim_router", "evidence_retriever",
                  "source_validator", "claim_verifier", "verdict_synthesizer"]:  # fmt: skip
        assert agent in agents_seen
    result = events[-1]["data"]
    assert result["language"]["code"] == "hi"
    assert result["verdicts"][0]["label"] == "true"
    assert result["verdicts"][0]["explanation"] == "दावा सही है।"
    assert result["verdicts"][0]["citations"]


async def test_pipeline_error_becomes_error_event_with_actionable_message():
    events = await collect(make_pipeline(ScriptedLLM(fail_extraction=True)), "anything")
    assert events[-1]["event"] == "error"
    assert "Is it running" in events[-1]["data"]["message"]


async def test_no_claims_short_circuits_downstream_agents():
    class NoClaims(ScriptedLLM):
        async def generate_json(self, schema_cls, system, user, model=None):
            return ex._Extraction(claims=[])

    events = await collect(make_pipeline(NoClaims()), "What a lovely day")
    agents_seen = {e["data"]["agent"] for e in events if e["event"] == "trace"}
    assert "evidence_retriever" not in agents_seen
    result = events[-1]["data"]
    assert result["verdicts"] == [] and any("No checkable" in w for w in result["warnings"])


# ---------------- HTTP layer ----------------


@pytest.fixture
async def client():
    from app.main import app

    app.state.llm = type("L", (), {"health": staticmethod(lambda: None)})()
    app.state.pipeline = make_pipeline()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_languages_endpoint_lists_23(client):
    r = await client.get("/api/languages")
    assert r.status_code == 200 and len(r.json()) == 23


async def test_check_streams_sse(client):
    r = await client.post("/api/check", json={"input": "भारत की राजधानी दिल्ली है"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    body = r.text
    assert "event: trace" in body and "event: result" in body
    result_line = body.split("event: result")[1].split("data: ", 1)[1].split("\n", 1)[0]
    assert json.loads(result_line)["verdicts"][0]["label"] == "true"


@pytest.mark.parametrize("payload", [{"input": ""}, {"input": "x" * 10_001}, {}])
async def test_check_rejects_invalid_input(client, payload):
    assert (await client.post("/api/check", json=payload)).status_code == 422
