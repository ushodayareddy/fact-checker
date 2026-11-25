import pytest

from app.agents.synthesizer import SynthesizerAgent, aggregate
from app.agents.verifier import VerifierAgent, _Judgment, quote_in_evidence
from app.languages import get_language
from app.llm import LLMError
from app.models import (
    Claim, Evidence, LanguageTier, SourceScore, Stance, StanceJudgment, VerdictLabel,
)  # fmt: skip
from app.state import PipelineState


def ev(id, url, snippet="text", title="t"):
    return Evidence(id=id, claim_id="c1", source="web", url=url, title=title, snippet=snippet)


def score(id, cred, tier="major_outlet"):
    return SourceScore(evidence_id=id, credibility=cred, tier=tier)


def judg(id, stance):
    return StanceJudgment(evidence_id=id, stance=stance, quote="q")


S, R, N = Stance.SUPPORTS, Stance.REFUTES, Stance.NEUTRAL
HIGH = LanguageTier.HIGH


def run(items, stances, tier=HIGH):
    evidence = [ev(i, u) for i, u, _ in items]
    scores = {i: score(i, c) for i, _, c in items}
    return aggregate(evidence, scores, [judg(i, s) for (i, _, _), s in zip(items, stances)], tier)


# ---------------- aggregate ----------------


def test_no_evidence_is_unverifiable_with_zero_confidence():
    label, conf, cites, caveats = aggregate([], {}, [], HIGH)
    assert (label, conf, cites) == (VerdictLabel.UNVERIFIABLE, 0.0, [])
    assert caveats


def test_all_neutral_is_unverifiable():
    label, *_ = run([("a", "https://a.com", 0.9), ("b", "https://b.com", 0.9)], [N, N])
    assert label == VerdictLabel.UNVERIFIABLE


def test_strong_agreement_is_true():
    label, conf, cites, _ = run(
        [("a", "https://pib.gov.in/1", 0.92), ("b", "https://thehindu.com/1", 0.72), ("c", "https://x.org/1", 0.6)],
        [S, S, S],
    )
    assert label == VerdictLabel.TRUE
    assert conf > 0.7
    assert cites[0] == "a"  # highest-credibility source cited first


def test_strong_refutation_is_false():
    label, *_ = run([("a", "https://boomlive.in/1", 0.88), ("b", "https://altnews.in/1", 0.88)], [R, R])
    assert label == VerdictLabel.FALSE


def test_single_weak_source_is_not_enough_for_a_firm_verdict():
    # One mediocre source supporting: weight 0.5 passes the floor but not the decisive-weight bar.
    label, conf, _, caveats = run([("a", "https://blog.example/1", 0.5)], [S])
    assert label == VerdictLabel.UNVERIFIABLE
    assert any("thin" in c for c in caveats)


def test_contested_with_factchecker_refutation_is_misleading():
    evidence = [ev("a", "https://thehindu.com/1"), ev("b", "https://boomlive.in/1")]
    scores = {"a": score("a", 0.72), "b": score("b", 0.88, tier="ifcn_factchecker")}
    label, _, cites, caveats = aggregate(evidence, scores, [judg("a", S), judg("b", R)], HIGH)
    assert label == VerdictLabel.MISLEADING
    assert set(cites) == {"a", "b"}  # both sides shown


def test_contested_without_factchecker_is_partly_true():
    label, *_ = run([("a", "https://a.com", 0.72), ("b", "https://b.com", 0.72)], [S, R])
    assert label == VerdictLabel.PARTLY_TRUE


def test_low_resource_language_caps_confidence():
    items = [("a", "https://pib.gov.in/1", 0.92), ("b", "https://thehindu.com/1", 0.9), ("c", "https://rbi.org.in/1", 0.92)]
    _, high_conf, *_ = run(items, [S, S, S], HIGH)
    _, low_conf, _, caveats = run(items, [S, S, S], LanguageTier.LOW)
    assert low_conf <= 0.6 < high_conf
    assert any("Low-resource" in c for c in caveats)


def test_neutral_and_unscored_stances_carry_no_weight():
    evidence = [ev("a", "https://a.com")]
    label, *_ = aggregate(evidence, {}, [judg("a", S), judg("ghost", R)], HIGH)  # no score -> ignored
    assert label == VerdictLabel.UNVERIFIABLE


def test_single_domain_caveat():
    _, _, _, caveats = run([("a", "https://a.com/1", 0.9), ("b", "https://a.com/2", 0.9)], [S, S])
    assert any("single domain" in c for c in caveats)


# ---------------- verifier ----------------


class StubLLM:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    async def generate_json(self, schema_cls, system, user, model=None):
        if self.error:
            raise self.error
        return self.result


def claim():
    return Claim(id="c1", text="Delhi is the capital", text_en="Delhi is the capital")


def test_quote_matching_ignores_case_and_whitespace():
    e = ev("a", "https://a.com", snippet="Delhi  is the\ncapital of India", title="Delhi")
    assert quote_in_evidence("delhi is the capital", e)
    assert not quote_in_evidence("Mumbai is the capital", e)
    assert not quote_in_evidence("", e)


async def test_verifier_keeps_stance_with_real_quote():
    e = ev("a", "https://a.com", snippet="New Delhi is the capital of India.")
    j = await VerifierAgent(StubLLM(_Judgment(stance=S, quote="Delhi is the capital of India"))).judge(claim(), e)
    assert j.stance == S


async def test_verifier_downgrades_fabricated_quote_to_neutral():
    e = ev("a", "https://a.com", snippet="New Delhi is the capital of India.")
    j = await VerifierAgent(StubLLM(_Judgment(stance=R, quote="Delhi was never the capital"))).judge(claim(), e)
    assert j.stance == N
    assert "verifiable quote" in j.rationale


async def test_verifier_downgrades_stance_with_empty_quote():
    e = ev("a", "https://a.com")
    j = await VerifierAgent(StubLLM(_Judgment(stance=S, quote=""))).judge(claim(), e)
    assert j.stance == N


async def test_verifier_treats_llm_failure_as_neutral():
    j = await VerifierAgent(StubLLM(error=LLMError("boom"))).judge(claim(), ev("a", "https://a.com"))
    assert j.stance == N


# ---------------- synthesizer ----------------


async def test_synthesizer_end_to_end_with_explanation_failure_fallback():
    state = PipelineState(raw_input="x")
    state.language = get_language("hi")
    state.claims = [claim()]
    state.evidence = {"c1": [ev("a", "https://pib.gov.in/1"), ev("b", "https://thehindu.com/1")]}
    state.scores = {"a": score("a", 0.92, "government"), "b": score("b", 0.72)}
    state.stances = {"c1": [judg("a", S), judg("b", S)]}
    await SynthesizerAgent(StubLLM(error=LLMError("down"))).run(state)
    v = state.verdicts[0]
    assert v.label == VerdictLabel.TRUE  # verdict does not depend on the LLM
    assert "could not be generated" in v.explanation


async def test_synthesizer_uses_llm_explanation_when_available():
    from app.agents.synthesizer import _Explanation

    state = PipelineState(raw_input="x")
    state.language = get_language("hi")
    state.claims = [claim()]
    state.evidence = {"c1": []}
    await SynthesizerAgent(StubLLM(_Explanation(explanation="पर्याप्त प्रमाण नहीं।"))).run(state)
    assert state.verdicts[0].label == VerdictLabel.UNVERIFIABLE
    assert state.verdicts[0].explanation == "पर्याप्त प्रमाण नहीं।"
