import httpx
import pytest
import respx

from app.agents.extractor import ExtractorAgent, fetch_article, is_url
from app.agents.router import ROUTES, RouterAgent, classify_by_rules
from app.config import Settings
from app.llm import LLMError, OllamaClient
from app.models import Claim, ClaimType
from app.state import PipelineState


class FakeLLM:
    """Stands in for OllamaClient.generate_json; returns a canned object or raises."""

    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, 0

    async def generate_json(self, schema_cls, system, user, model=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def test_is_url():
    assert is_url("https://example.com/a?b=1")
    assert not is_url("see https://example.com for details")
    assert not is_url("India's GDP grew 8%")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("India's GDP grew 8 percent last year", ClaimType.STATISTICAL),
        ("Drinking hot water cures cancer", ClaimType.HEALTH),
        ("Forwarded: free recharge for everyone", ClaimType.VIRAL),
        ("The Taj Mahal is located in Agra", None),  # no rule fires -> LLM fallback
        ("Government announced a new vaccine scheme", None),  # health + statistical -> ambiguous
    ],
)
def test_rule_classifier(text, expected):
    assert classify_by_rules(text) == expected


def test_every_claim_type_has_a_route():
    assert set(ROUTES) == set(ClaimType)


async def test_router_skips_llm_when_rule_matches():
    llm = FakeLLM()
    claim = Claim(id="c1", text="x", text_en="India's inflation rose to 6 percent")
    assert await RouterAgent(llm).classify(claim) == ClaimType.STATISTICAL
    assert llm.calls == 0


async def test_router_falls_back_to_entity_when_llm_fails():
    claim = Claim(id="c1", text="x", text_en="The Taj Mahal is in Agra")
    assert await RouterAgent(FakeLLM(error=LLMError("down"))).classify(claim) == ClaimType.ENTITY


@respx.mock
async def test_extractor_text_input_limits_and_numbers_claims(monkeypatch):
    from app.agents import extractor as mod

    out = mod._Extraction(
        claims=[
            mod._ExtractedClaim(text="भारत की राजधानी दिल्ली है", text_en="India's capital is Delhi"),
            mod._ExtractedClaim(text="  ", text_en=""),  # blank claims are dropped
        ]
    )
    state = PipelineState(raw_input="भारत की राजधानी दिल्ली है")
    await ExtractorAgent(FakeLLM(result=out)).run(state)
    assert [c.id for c in state.claims] == ["c1"]
    assert state.claims[0].text_en == "India's capital is Delhi"


async def test_extractor_warns_when_no_claims():
    from app.agents import extractor as mod

    state = PipelineState(raw_input="What a lovely day!")
    await ExtractorAgent(FakeLLM(result=mod._Extraction(claims=[]))).run(state)
    assert state.claims == []
    assert any("No checkable" in w for w in state.warnings)


@respx.mock
async def test_fetch_article_extracts_main_text():
    html = "<html><body><article><p>" + "The reservoir level rose sharply after heavy rain. " * 10 + "</p></article></body></html>"
    respx.get("https://news.test/a").mock(return_value=httpx.Response(200, text=html))
    async with httpx.AsyncClient() as client:
        text = await fetch_article("https://news.test/a", client)
    assert "reservoir level" in text


@respx.mock
async def test_fetch_article_raises_on_unreadable_page():
    respx.get("https://news.test/empty").mock(return_value=httpx.Response(200, text="<html></html>"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="Could not extract"):
            await fetch_article("https://news.test/empty", client)
