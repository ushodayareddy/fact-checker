"""Facts about the system, read from the real code, tests and eval files so the documents cannot drift.

Anything quoted in prose that is not importable (numeric constants inside functions) is guarded by
`guard()`, which aborts the build if the source no longer contains the snippet the prose relies on.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import yaml

TOOLS = Path(__file__).resolve().parent
DOCS = TOOLS.parent
ROOT = DOCS.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def guard(path: Path, *snippets: str) -> None:
    src = path.read_text(encoding="utf-8")
    missing = [s for s in snippets if s not in src]
    if missing:
        raise SystemExit(f"Docs are out of sync with {path.relative_to(ROOT)}: no longer contains {missing}")


def _pytest(*args: str) -> str:
    r = subprocess.run([sys.executable, "-m", "pytest", *args], cwd=BACKEND, capture_output=True, text=True)
    return r.stdout + r.stderr


def test_facts() -> dict:
    out = _pytest("-q", "-p", "no:cacheprovider")
    count = lambda word: int(m.group(1)) if (m := re.search(rf"(\d+) {word}", out)) else 0  # noqa: E731
    collected = _pytest("--collect-only", "-q", "-p", "no:cacheprovider")
    per_file = Counter(line.split("::")[0].removeprefix("tests/") for line in collected.splitlines() if "::" in line)
    return {
        "passed": count("passed"), "failed": count("failed"), "xfailed": count("xfailed"),
        "per_file": dict(per_file), "files": len(per_file),
    }  # fmt: skip


def load_facts() -> dict:
    sys.path.insert(0, str(BACKEND))
    from app.agents import synthesizer as syn
    from app.agents.router import ROUTES
    from app.config import Settings
    from app.languages import load_languages

    # numeric rules quoted in the prose
    guard(BACKEND / "app/agents/validator.py", "age > 3", "0.03 * (age - 3)", "min(0.15", "cred -= 0.1", "cred -= 0.03", "relevance < 0.3")
    guard(BACKEND / "app/agents/verifier.py", "_CONCURRENCY = 2")
    guard(BACKEND / "app/agents/extractor.py", "_MAX_CHARS = 6000")
    guard(BACKEND / "app/agents/retriever.py", "http_timeout_s * 2", "setdefault(ev.url")
    guard(BACKEND / "app/agents/synthesizer.py", "0.5 + 0.35 * min(1.0, win_w / 2.0) + 0.1 * win_share", "0.4 + 0.2 * share", "base = 0.3")
    guard(BACKEND / "app/main.py", "MAX_INPUT_CHARS = 10_000")
    guard(BACKEND / "app/llm.py", '"think": False')

    langs = load_languages()
    tiers = {t: [l for l in langs.values() if l.tier.value == t] for t in ("high", "medium", "low")}
    defaults = {k: v.default for k, v in Settings.model_fields.items()}
    tiers_yaml = yaml.safe_load((BACKEND / "app/data/source_tiers.yaml").read_text(encoding="utf-8"))
    cases = yaml.safe_load((BACKEND / "eval/cases.yaml").read_text(encoding="utf-8"))["cases"]
    pkg = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    ver = lambda name: pkg["dependencies"].get(name, pkg["devDependencies"].get(name, "?")).lstrip("^~")  # noqa: E731

    return {
        "routes": {k.value: v for k, v in ROUTES.items()},
        "languages": langs, "tiers": tiers, "n_languages": len(langs),
        "settings": defaults,
        "thresholds": {
            "min_total": syn.MIN_TOTAL_WEIGHT, "decisive_share": syn.DECISIVE_SHARE,
            "min_decisive": syn.MIN_DECISIVE_WEIGHT, "mixed_share": syn.MIXED_MIN_SHARE,
            "corroboration": syn.CORROBORATION_BONUS,
            "cap": {k.value: v for k, v in syn.CONFIDENCE_CAP.items()},
        },
        "source_tiers": {
            name: {"credibility": t["credibility"], "domains": t["domains"]} for name, t in tiers_yaml["tiers"].items()
        } | {"unknown": {"credibility": tiers_yaml["default"]["credibility"], "domains": []}},
        "cases": cases,
        "case_counts": {
            "total": len(cases),
            "by_lang": dict(Counter(c["lang"] for c in cases)),
            "by_category": dict(Counter(c["category"] for c in cases)),
            "by_expect": dict(Counter(c["expect"][0] for c in cases)),
        },
        "tests": test_facts(),
        "frontend": {"react": ver("react"), "vite": ver("vite"), "typescript": ver("typescript")},
    }


def load_results() -> tuple[dict | None, Path | None]:
    for p in (DOCS / "data" / "eval_results.json", BACKEND / "eval" / "results" / "latest.json"):
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8")), p
    return None, None


def results_sentence(res: dict | None) -> str:
    """One neutral sentence for abstracts, computed from real results only."""
    if not res:
        return ""
    ov = res["summary"]["overall"]
    acc = "n/a" if ov["accuracy"] is None else f"{ov['accuracy']:.0%}"
    return (
        f"On the {ov['total']}-case evaluation set the system produced {ov['pass']} correct outcomes, "
        f"{ov['abstain']} abstentions (unverifiable) and {ov['fail']} confidently wrong verdicts, with "
        f"{ov['error']} errors (accuracy {acc} over answered cases)."
    )


if __name__ == "__main__":
    f = load_facts()
    print({k: f[k] for k in ("n_languages", "thresholds", "case_counts", "tests", "frontend")})
