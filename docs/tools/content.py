"""Single source of prose for the report, the IEEE paper and the slides.

Written once so the three documents cannot contradict each other. Citations are [@key] markers resolved
per document. Numbers come from `facts` (the real code, tests and eval files); nothing here states a
measured accuracy. Where evaluation results are absent, builders insert an explicit "pending" notice.
"""

from __future__ import annotations

TITLE = "Agentic Fact-Checking for Indian Languages: A Multi-Agent Framework for Evidence Retrieval, Claim Verification and Source Validation"


def tier_names(f: dict, tier: str) -> str:
    return ", ".join(l.name for l in f["tiers"][tier])


def abstract(f: dict, results_sentence: str) -> str:
    t, c = f["thresholds"], f["case_counts"]
    base = (
        "Misinformation spreads in Indian languages faster than it can be checked, yet most automated fact-checking "
        "research targets English and most deployed tools depend on a closed, hosted language model. This work presents "
        f"a multi-agent framework that checks claims written in any of the {f['n_languages'] - 1} scheduled languages of India, "
        "or in English, using only locally hosted models. Seven cooperating agents extract atomic claims, identify the "
        "language, route each claim to suitable evidence sources, retrieve and rank evidence in the claim's language and in "
        "English, score every source for credibility, judge whether each source supports or refutes the claim, and "
        "synthesise a verdict explained in the user's own language. Two design decisions make the verdicts auditable. A "
        "stance counts only when the model backs it with a quote that actually appears in the evidence; otherwise it is "
        "discarded. The verdict label and confidence are computed by explicit rules from credibility-weighted stances, so "
        "the language model explains a decision but does not make it, and confidence is capped for languages where "
        "local models are weakest. "
        f"The system comes with {f['tests']['passed']} automated tests and a labelled evaluation set of {c['total']} claims in "
        f"{len(c['by_lang'])} languages. "
    )
    tail = results_sentence or (
        "Accuracy results from the evaluation set are not yet available and are reported as pending; no accuracy figure is claimed."
    )
    return base + tail


KEYWORDS = "fact-checking; Indian languages; multi-agent systems; retrieval-augmented generation; source credibility; large language models; multilingual NLP"

INTRO_PAR = [
    "False and misleading claims travel quickly through messaging apps and social media in India, where content circulates in "
    "dozens of languages and professional fact-checkers are few. Fact-checking organisations such as those indexed by the "
    "Google Fact Check Tools service publish their conclusions, but a reader who meets a claim in Tamil, Bengali or Odia "
    "usually cannot find out whether it has already been checked, and cannot judge how far to trust whatever source they do find [@googlefc].",
    "Automated fact-checking has been studied extensively. Surveys describe a pipeline of claim detection, evidence retrieval and "
    "verdict prediction [@guo2022], and datasets such as FEVER [@thorne2018], MultiFC [@augenstein2019] and AVeriTeC [@schlichtkrull2023] "
    "drive progress, almost entirely in English. Multilingual work exists, notably X-FACT [@gupta2021] across 25 languages and "
    "resources built from Indian fact-checking sites [@singhal2021; @kazemi2021], but these are datasets and classifiers. They do not "
    "provide a deployable system that finds fresh evidence, decides how much each source deserves to be trusted, and explains its answer "
    "in the user's language.",
    "This work builds that system. It is organised as seven agents with narrow responsibilities, it runs entirely on local models so "
    "that no claim leaves the user's machine and no per-query fee applies, and it treats trust as a first-class output: every "
    "verdict lists its evidence, the credibility of each source, and the exact quote that justified each judgement.",
]

def contributions(f: dict) -> list[str]:
    return [
        "A seven-agent architecture for Indian-language fact-checking that separates claim extraction, language identification, routing, "
        "retrieval, source validation, claim verification and verdict synthesis, with a claim-type router that selects evidence sources.",
        "A quote-grounding rule for stance judgements: a supports or refutes judgement is kept only if its supporting quote occurs in the evidence text.",
        "A rule-based verdict policy in which the label and confidence are computed from credibility-weighted stances, with confidence capped by language-resource tier.",
        "A transparent source-credibility model built from a domain-tier registry with recency and relevance adjustments, each recorded as a reason shown to the user.",
        f"An open implementation covering {f['n_languages'] - 1} scheduled languages and English, with {f['tests']['passed']} automated tests and a {f['case_counts']['total']}-case labelled evaluation set.",
    ]

OBJECTIVES = [
    "Accept a claim or an article link in any scheduled Indian language or English, and return a verdict with cited evidence.",
    "Retrieve evidence from sources appropriate to the kind of claim, in the claim's language and in English.",
    "Estimate how trustworthy each source is and show the reasons, instead of treating all sources equally.",
    "Make the verdict reproducible: the same judgements must always produce the same label and confidence.",
    "Run on a single consumer machine using open models, and degrade safely when a source or the model is unavailable.",
    "Be honest about weak languages: warn the user and lower confidence where the models are least reliable.",
]

PROBLEM_STATEMENT = (
    "Given a claim c written in one of the scheduled Indian languages or English, produce a verdict v drawn from "
    "{true, false, misleading, partly true, unverifiable}, a confidence p in [0, 1], and a set of cited evidence items, such that "
    "every cited item was actually retrieved, every stance rests on text present in the item, and p is never higher than the "
    "reliability of the language allows. The system must answer unverifiable, and say what is missing, when credible evidence is absent."
)


def agent_table(f: dict) -> list[tuple[str, str, str, str]]:
    """(agent, input, method, output)."""
    return [
        ("Claim Extractor", "Text or article URL", f"Fetches and cleans article text; a local LLM returns up to {f['settings']['max_claims']} atomic, self-contained, checkable claims with an English rendering; opinions are skipped", "Claims (original + English)"),
        ("Language ID", "Claim text", "Script detection by Unicode character names, then the lingua detector for languages that share a script; defaults to the script's main language", "Language code, resource tier, warnings"),
        ("Claim Router", "English claim", "Keyword rules classify the claim only when exactly one rule family matches; ambiguous claims go to the LLM, which falls back to 'entity' if unavailable", "Claim type and ordered source list"),
        ("Evidence Retriever", "Claim, source list", f"Queries each routed adapter in the claim's language and in English, concurrently; de-duplicates by URL; ranks by embedding similarity; keeps the top {f['settings']['max_evidence_per_claim']}", "Ranked evidence items"),
        ("Source Validator", "Evidence items", "Domain-tier prior, minus penalties for age and low relevance; every adjustment is recorded as a reason", "Credibility 0 to 1, tier, reasons"),
        ("Claim Verifier", "Claim, evidence item", "LLM judges supports, refutes or neutral and must quote the evidence; a stance without a verifiable quote is downgraded to neutral", "Stance, quote, rationale"),
        ("Verdict Synthesizer", "Stances, credibility, language tier", "Rules compute label and confidence; the LLM only writes the explanation, in the user's language", "Verdict, confidence, citations, caveats"),
    ]


def routing_rows(f: dict) -> list[tuple[str, str]]:
    names = {"govt": "government", "factcheck": "fact-check archives", "web": "web search", "wikipedia": "Wikipedia", "wikidata": "Wikidata"}
    return [(k, " → ".join(names.get(s, s) for s in v)) for k, v in f["routes"].items()]


def adapter_table() -> list[tuple[str, str, str]]:
    return [
        ("Wikipedia", "MediaWiki API in the claim's language edition", "Skipped for languages with no edition; the English query still runs"),
        ("Wikidata", "Entity search API", "Grounds entities only; property and SPARQL queries are not implemented"),
        ("Government", "Domain-restricted web search over official sites", "No first-party API is integrated; data.gov.in dataset lookup is not implemented"),
        ("Fact-check archives", "Google Fact Check Tools API when a key is set, otherwise domain-restricted search", "Depends on the claim having been checked before"),
        ("Web search", "Tavily, SearXNG or DuckDuckGo HTML, in that order of preference", "Scraping DuckDuckGo is fragile; a keyed search service is more reliable"),
    ]


def credibility_text(f: dict) -> list[str]:
    st = f["source_tiers"]
    pri = ", ".join(f"{k.replace('_', ' ')} {v['credibility']:.2f}" for k, v in st.items())
    return [
        f"Each source starts from a prior set by its domain tier: {pri}. Matching uses the longest matching domain or path, so a fact-check section "
        "of a news site outranks the news site itself, and a look-alike host such as a government name embedded in an unrelated domain does not match.",
        "The prior is then adjusted. A non-reference source older than three years loses 0.03 per further year, up to 0.15; a source with no publication "
        "date and an unknown or news-outlet tier loses 0.03; a source whose relevance to the claim is below 0.3 loses 0.1. Each adjustment is stored "
        "as a human-readable reason and shown on hover in the interface. The registry is a hand-written prior and should be reviewed by domain experts.",
    ]


def verdict_text(f: dict) -> list[str]:
    t = f["thresholds"]
    return [
        f"For each claim the synthesizer sums the credibility of sources that support the claim (W_sup) and that refute it (W_ref); neutral and unscored items carry no weight. "
        f"If W_sup + W_ref is below {t['min_total']}, the verdict is unverifiable with zero confidence.",
        f"If both sides hold at least {t['mixed_share']:.0%} of the weight, credible sources disagree. The verdict is misleading when an established fact-checker is among the refuters, "
        "and partly true otherwise; both sides are cited. Otherwise one side wins. It must carry weight of at least "
        f"{t['min_decisive']} to give a firm true or false; below that the evidence is treated as thin and the verdict is unverifiable.",
        f"Confidence grows with the winning weight and its share, gains {t['corroboration']:.2f} for each additional independent agreeing domain (at most 0.10), and is capped by language tier at "
        f"{t['cap']['high']:.2f} (high), {t['cap']['medium']:.2f} (medium) and {t['cap']['low']:.2f} (low). A single-domain evidence set adds a caveat. "
        "These thresholds were chosen conservatively, because confidently mislabelling a claim is worse than abstaining, and have not yet been tuned on data.",
    ]


def implementation_rows(f: dict) -> list[tuple[str, str]]:
    s, fe = f["settings"], f["frontend"]
    return [
        ("Backend", "Python 3.12, FastAPI, Pydantic v2, httpx, asyncio; Server-Sent Events stream the agent trace"),
        ("Local LLM", f"Ollama; reasoning model {s['reasoning_model']} with {s['fallback_model']} as the configured alternative; structured JSON output validated against a schema, with retries that feed the validation error back"),
        ("Embeddings", f"{s['embedding_model']} through Ollama; falls back to lexical overlap if embeddings are unavailable"),
        ("Language ID", "Unicode script analysis and the lingua detector"),
        ("Article extraction", "trafilatura"),
        ("Frontend", f"React {fe['react']}, TypeScript {fe['typescript']}, Vite {fe['vite']}; live agent trace, verdict cards, evidence with credibility badges, dark mode"),
        ("Packaging", "uv for the Python environment; Windows setup, run and evaluation batch scripts"),
        ("Limits", f"Input capped at 10,000 characters; extraction reads the first 6,000; up to {s['max_claims']} claims per input"),
    ]


def robustness_points() -> list[str]:
    return [
        "A failing or slow evidence source is skipped and noted as a warning; the pipeline continues with the remaining sources.",
        "If embeddings are unavailable, evidence is ranked by lexical overlap instead of failing.",
        "If the language model returns invalid JSON, the validation error is sent back and the call retried; after the retries are exhausted the error is shown to the user.",
        "If the router's LLM call fails, the claim defaults to the general entity route; if the explanation call fails, the verdict is still shown with its computed label and a plain notice.",
        "If the extractor finds no checkable claim, the pipeline stops early and says so instead of inventing a claim.",
        "If Ollama is not running, the interface shows how to start it, and the error message names the address it tried.",
    ]


def testing_rows(f: dict) -> list[tuple[str, str]]:
    names = {
        "test_llm.py": "Ollama client: JSON validation, retry with error feedback, connection errors, health check",
        "test_languages.py": "All 22 scheduled languages plus English present; tiers; Wikipedia availability",
        "test_language_agent.py": "Script and language detection on sample sentences; low-resource warning",
        "test_extractor_router.py": "URL handling, article extraction, rule-based routing and LLM fallback",
        "test_sources.py": "Each evidence adapter against recorded response shapes; domain allow-listing",
        "test_validator_retriever.py": "Domain tiers, spoofed-domain rejection, age and relevance penalties; concurrent retrieval, de-duplication, failure isolation, ranking fallback",
        "test_verifier_synthesizer.py": "Quote grounding, fabricated-quote rejection, every verdict branch, confidence cap",
        "test_pipeline_api.py": "End-to-end run with scripted model, streaming endpoint, input validation, error events",
        "test_eval_cases.py": "Evaluation dataset integrity, scoring rules, report generation",
    }
    return [(names.get(k, k), str(v)) for k, v in sorted(f["tests"]["per_file"].items())]


def limitations() -> list[str]:
    return [
        "No accuracy has been measured yet on real model and live sources; every capability above is verified only with scripted models and recorded responses until the evaluation is run.",
        "Local models are weaker in low-resource languages, which is why confidence is capped; evidence in those languages is also scarce.",
        "Language identification separates languages that share a script only for those the lingua detector supports. A correct Marathi sentence in the evaluation set is identified as Hindi (scores 0.53 against 0.47), and Maithili, Konkani and Dogri are likely to default to Hindi.",
        "The English rendering of a non-English claim comes from the extraction model, not a dedicated translation system; IndicTrans2 [@gala2023] is the natural replacement.",
        "Government and fact-check sources use domain-restricted web search, not first-party APIs; numeric claims therefore depend on the figure appearing in page text. Wikidata is used for entity grounding only.",
        "The credibility registry and the verdict thresholds are hand-set and untuned.",
        "Non-English evaluation claims were translated by an AI system and have not been reviewed by native speakers; Odia has one case and the eight lowest-resource scheduled languages have none.",
        "The system judges claims against retrieved text; it does not detect manipulated images or video, and it cannot check claims that no indexed source discusses.",
    ]


def future_work() -> list[str]:
    return [
        "Run the full evaluation on local models, tune the verdict thresholds on held-out data, and report per-language results.",
        "Adopt IndicTrans2 for translation and add a language identifier that covers Maithili, Konkani, Dogri, Bodo and the other languages the current detector cannot separate.",
        "Integrate first-party data sources (data.gov.in, Wikidata properties) so that numerical claims can be checked against the figure itself.",
        "Add image and video claims through reverse-image search and metadata checks.",
        "Collect native-speaker review of the evaluation claims and extend the set to every scheduled language and to time-sensitive claims.",
    ]


def eval_design(f: dict) -> list[str]:
    c = f["case_counts"]
    langs = ", ".join(sorted(c["by_lang"]))
    return [
        f"The evaluation set contains {c['total']} labelled inputs in {len(c['by_lang'])} languages ({langs}): {c['by_expect']['true']} true claims, {c['by_expect']['false']} false claims, "
        f"and {c['by_expect']['no_claims']} inputs with nothing checkable, which the extractor should reject. Facts were chosen to be stable over time, such as capitals, landmarks and well-known myths; "
        "no time-sensitive statistics are included.",
        "Each case is scored pass (the verdict is among the expected labels), abstain (the system answered unverifiable on a true or false case, which is unhelpful but not wrong), "
        "fail (the verdict contradicts the expectation, the costly outcome) or error (the request failed). Accuracy is pass over answered cases, with errors excluded, and is reported overall, by language and by category.",
    ]
