"""Validates the eval dataset itself and the runner's scoring/parsing, without a live backend."""

import json
from collections import Counter

import httpx
import pytest
from httpx import ASGITransport

from app.agents.language import detect_language
from app.languages import load_languages
from eval.run_eval import load_cases, outcome_of, parse_sse, run_case, score, summarize

CASES = load_cases()
VALID_EXPECT = {"true", "false", "misleading", "partly_true", "unverifiable", "no_claims"}


def test_there_are_exactly_50_cases():
    assert len(CASES) == 50


def test_ids_are_unique():
    assert [i for i, n in Counter(c["id"] for c in CASES).items() if n > 1] == []


def test_every_case_has_required_fields_and_valid_labels():
    for c in CASES:
        assert {"id", "lang", "category", "expect", "text"} <= c.keys(), c["id"]
        assert c["text"].strip(), c["id"]
        assert c["lang"] in load_languages(), c["id"]
        assert c["expect"] and set(c["expect"]) <= VALID_EXPECT, c["id"]


def test_dataset_is_balanced_enough_to_be_informative():
    expected = Counter(tuple(c["expect"]) for c in CASES)
    assert expected[("true",)] >= 15 and expected[("false",)] >= 15
    assert expected[("no_claims",)] >= 3
    assert len({c["lang"] for c in CASES}) >= 12


# Real detector limits, not dataset errors: lingua scores Hindi 0.53 vs Marathi 0.47 on this
# correct Marathi sentence. strict=True makes the suite flag it when the detector improves.
KNOWN_LANGID_GAPS = {"mr-03": "lingua near-tie between Hindi and Marathi"}


def _langid_params():
    for c in CASES:
        marks = [pytest.mark.xfail(reason=KNOWN_LANGID_GAPS[c["id"]], strict=True)] if c["id"] in KNOWN_LANGID_GAPS else []
        yield pytest.param(c, id=c["id"], marks=marks)


@pytest.mark.parametrize("case", list(_langid_params()))
def test_case_text_is_detected_as_its_declared_language(case):
    """Catches mislabelled or wrongly-scripted cases, and surfaces real language-ID gaps."""
    assert detect_language(case["text"]).code == case["lang"]


# ---------------- runner ----------------


@pytest.mark.parametrize(
    "expect,outcome,status",
    [
        (["true"], "true", "pass"),
        (["true"], "false", "fail"),  # confidently wrong
        (["true"], "unverifiable", "abstain"),
        (["false"], "partly_true", "fail"),
        (["no_claims"], "no_claims", "pass"),
        (["no_claims"], "true", "fail"),  # extracted a claim from an opinion
        (["no_claims"], "unverifiable", "fail"),
    ],
)
def test_score(expect, outcome, status):
    assert score(expect, outcome) == status


def test_outcome_of():
    assert outcome_of({"verdicts": []}) == "no_claims"
    assert outcome_of({"verdicts": [{"label": "false"}, {"label": "true"}]}) == "false"


async def _lines(text):
    for line in text.split("\n"):
        yield line


async def test_parse_sse_handles_multiple_events_and_crlf_free_lines():
    stream = 'event: trace\ndata: {"a": 1}\n\nevent: result\ndata: {"b": 2}\n\n'
    got = [e async for e in parse_sse(_lines(stream.rstrip("\n")))]
    assert got == [("trace", '{"a": 1}'), ("result", '{"b": 2}')]


def test_summarize_counts_and_accuracy_exclude_errors():
    rows = [
        {"status": "pass", "lang": "hi", "category": "entity", "lang_ok": True},
        {"status": "fail", "lang": "hi", "category": "entity", "lang_ok": True},
        {"status": "abstain", "lang": "en", "category": "health", "lang_ok": False},
        {"status": "error", "lang": "en", "category": "health"},
    ]
    s = summarize(rows)
    assert s["overall"]["total"] == 4 and s["overall"]["accuracy"] == round(1 / 3, 3)
    assert s["by_language"]["hi"]["accuracy"] == 0.5
    assert s["language_id_accuracy"] == round(2 / 3, 3)


@pytest.fixture
async def live_app_client():
    """The real FastAPI app wired to the scripted pipeline from test_pipeline_api (no Ollama needed)."""
    from app.main import app
    from tests.test_pipeline_api import make_pipeline

    app.state.pipeline = make_pipeline()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_run_case_end_to_end_pass_and_fail(live_app_client):
    # The scripted pipeline always concludes "true" for a Delhi-capital claim.
    text = "भारत की राजधानी दिल्ली है"
    ok = await run_case(live_app_client, {"id": "x1", "lang": "hi", "category": "entity", "expect": ["true"], "text": text})
    assert ok["status"] == "pass" and ok["outcome"] == "true" and ok["lang_ok"] is True
    assert ok["n_evidence"] > 0 and ok["confidence"] > 0

    wrong = await run_case(live_app_client, {"id": "x2", "lang": "hi", "category": "entity", "expect": ["false"], "text": text})
    assert wrong["status"] == "fail"


async def test_run_case_reports_http_errors_as_error_status(live_app_client):
    row = await run_case(live_app_client, {"id": "x3", "lang": "en", "category": "entity", "expect": ["true"], "text": "   "})
    assert row["status"] == "error" and "422" in row["error"]
    json.dumps(row)  # rows must be JSON-serialisable for the report


# ---------------- markdown report ----------------


def test_render_markdown_has_headline_tables_and_failure_list():
    from eval.run_eval import render_markdown

    rows = [
        {"id": "en-01", "lang": "en", "category": "entity", "status": "pass", "expect": ["true"], "outcome": "true",
         "confidence": 0.9, "n_evidence": 5, "latency_s": 40.1, "explanation": "ok | with pipe", "text": "t1", "lang_ok": True},
        {"id": "hi-02", "lang": "hi", "category": "entity", "status": "fail", "expect": ["false"], "outcome": "true",
         "confidence": 0.8, "n_evidence": 3, "latency_s": 52.0, "explanation": "wrong", "text": "भारत की राजधानी मुंबई है।", "lang_ok": True},
        {"id": "ta-01", "lang": "ta", "category": "entity", "status": "error", "expect": ["true"], "outcome": None,
         "error": "HTTP 500", "latency_s": 1.0, "text": "t3"},
    ]
    md = render_markdown(summarize(rows), rows, {"when": "2026-11-24 10:00", "reasoning_model": "qwen3:14b"})
    assert "`qwen3:14b`" in md and "**fail 1**" in md and "error 1" in md
    assert "| hi |" in md and "## Failures and errors" in md
    assert "भारत की राजधानी मुंबई है।" in md  # failed claim text is shown for review
    assert "ok \\| with pipe" in md  # pipes must not break the table
    assert "HTTP 500" in md
