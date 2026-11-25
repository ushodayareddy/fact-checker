from datetime import date

import pytest

from app.agents.retriever import RetrieverAgent
from app.agents.validator import ValidatorAgent, lookup_domain, score_evidence
from app.llm import LLMError
from app.models import Claim, ClaimType, Evidence
from app.languages import get_language
from app.state import PipelineState

TODAY = date(2026, 11, 24)


def ev(url, published=None, relevance=0.8, source="web", id=None, claim_id="c1"):
    return Evidence(id=id or url, claim_id=claim_id, source=source, url=url, title="t",
                    snippet="s", published=published, relevance=relevance)  # fmt: skip


@pytest.mark.parametrize(
    "url,tier",
    [
        ("https://pib.gov.in/PressReleasePage.aspx?PRID=1", "government"),
        ("https://www.rbi.org.in/x", "government"),
        ("https://some.dept.gov.in/page", "government"),  # gov.in suffix match
        ("https://www.boomlive.in/fact-check/1", "ifcn_factchecker"),
        ("https://hi.wikipedia.org/wiki/X", "reference"),  # subdomain match
        ("https://www.thehindu.com/news/a", "major_outlet"),
        ("https://www.facebook.com/post/1", "social_or_user_generated"),
        ("https://randomblog.example/post", "unknown"),
        ("https://notpib.gov.in.evil.com/x", "unknown"),  # suffix spoofing must not match
    ],
)
def test_domain_tiers(url, tier):
    assert lookup_domain(url)[0] == tier


def test_path_specific_entry_beats_domain_entry():
    assert lookup_domain("https://www.reuters.com/fact-check/x")[0] == "ifcn_factchecker"
    assert lookup_domain("https://www.reuters.com/world/x")[0] == "major_outlet"


def test_old_sources_are_penalised_but_reference_is_exempt():
    fresh = score_evidence(ev("https://www.thehindu.com/a", "2026-10-01"), TODAY)
    old = score_evidence(ev("https://www.thehindu.com/a", "2018-01-01"), TODAY)
    wiki_old = score_evidence(ev("https://en.wikipedia.org/wiki/A", "2015-01-01"), TODAY)
    assert old.credibility < fresh.credibility
    assert any("outdated" in r for r in old.reasons)
    assert wiki_old.credibility == pytest.approx(0.80)


def test_low_relevance_is_penalised_and_score_is_bounded():
    low = score_evidence(ev("https://pib.gov.in/x", "2026-01-01", relevance=0.1), TODAY)
    assert low.credibility < 0.92
    assert 0.0 <= low.credibility <= 1.0


def test_social_media_is_low_credibility():
    assert score_evidence(ev("https://x.com/u/status/1", "2026-11-01"), TODAY).credibility < 0.3


async def test_validator_scores_every_evidence_item():
    state = PipelineState(raw_input="x")
    state.evidence = {"c1": [ev("https://pib.gov.in/a", id="a"), ev("https://x.com/b", id="b")]}
    await ValidatorAgent().run(state)
    assert set(state.scores) == {"a", "b"}
    assert state.scores["a"].credibility > state.scores["b"].credibility


# ---------------- retriever ----------------


class StubAdapter:
    def __init__(self, name, results=None, error=None, is_available=True):
        self.name, self._results, self._error, self._avail = name, results or [], error, is_available
        self.queries: list[tuple[str, str]] = []

    def available(self):
        return self._avail

    async def search(self, query, lang, claim_id):
        self.queries.append((query, lang))
        if self._error:
            raise self._error
        return [e.model_copy(update={"claim_id": claim_id}) for e in self._results]


class StubLLM:
    def __init__(self, vectors=None, error=None):
        self.vectors, self.error = vectors, error

    async def embed(self, texts, model=None):
        if self.error:
            raise self.error
        return self.vectors(texts)


def make_state(claim_type=ClaimType.ENTITY, lang="hi"):
    state = PipelineState(raw_input="x")
    state.language = get_language(lang)
    state.claims = [Claim(id="c1", text="दिल्ली भारत की राजधानी है", text_en="Delhi is India's capital",
                          claim_type=claim_type)]  # fmt: skip
    return state


async def test_retriever_queries_native_and_english_and_dedupes_by_url():
    shared = ev("https://en.wikipedia.org/wiki/Delhi", id="w1", source="wikipedia")
    adapters = {
        "wikipedia": StubAdapter("wikipedia", [shared]),
        "wikidata": StubAdapter("wikidata", [shared.model_copy(update={"id": "dup"})]),
        "web": StubAdapter("web", []),
    }
    state = make_state()
    await RetrieverAgent(StubLLM(vectors=lambda t: [[1.0, 0.0]] * len(t)), adapters).run(state)
    assert adapters["wikipedia"].queries == [("दिल्ली भारत की राजधानी है", "hi"), ("Delhi is India's capital", "en")]
    assert len(state.evidence["c1"]) == 1  # same URL from two adapters collapses


async def test_failing_adapter_degrades_instead_of_failing():
    adapters = {
        "wikipedia": StubAdapter("wikipedia", error=TimeoutError()),
        "wikidata": StubAdapter("wikidata", [ev("https://wikidata.org/Q1", id="q1", source="wikidata")]),
        "web": StubAdapter("web", []),
    }
    state = make_state()
    await RetrieverAgent(StubLLM(vectors=lambda t: [[1.0]] * len(t)), adapters).run(state)
    assert [e.id for e in state.evidence["c1"]] == ["q1"]
    assert any("wikipedia" in w and "TimeoutError" in w for w in state.warnings)


async def test_unavailable_adapters_are_skipped_not_called():
    govt = StubAdapter("govt", [ev("https://pib.gov.in/a", id="g")], is_available=False)
    web = StubAdapter("web", [ev("https://example.com/a", id="w")])
    adapters = {"govt": govt, "web": web}
    state = make_state(ClaimType.STATISTICAL)
    await RetrieverAgent(StubLLM(vectors=lambda t: [[1.0]] * len(t)), adapters).run(state)
    assert govt.queries == []
    assert [e.id for e in state.evidence["c1"]] == ["w"]


async def test_embedding_failure_falls_back_to_lexical_ranking():
    relevant = Evidence(id="r", claim_id="c1", source="web", url="https://a.com", title="Delhi capital",
                        snippet="Delhi is India's capital city")  # fmt: skip
    irrelevant = Evidence(id="i", claim_id="c1", source="web", url="https://b.com", title="Cricket",
                          snippet="match scores yesterday")  # fmt: skip
    adapters = {"web": StubAdapter("web", [irrelevant, relevant])}
    state = make_state(ClaimType.BREAKING)
    await RetrieverAgent(StubLLM(error=LLMError("no embed model")), adapters).run(state)
    assert [e.id for e in state.evidence["c1"]][0] == "r"


async def test_no_evidence_yields_empty_list():
    state = make_state()
    await RetrieverAgent(StubLLM(vectors=lambda t: []), {"web": StubAdapter("web", [])}).run(state)
    assert state.evidence["c1"] == []
