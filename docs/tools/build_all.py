"""Build the report, IEEE paper and slides.

    uv run --project ../../backend --with matplotlib --with python-docx --with python-pptx \
        python build_all.py --report-template "/path/to/Report_Template.docx"

Outputs go to docs/build/. Placeholders for missing team details are listed at the end.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import yaml

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import facts  # noqa: E402
import figures  # noqa: E402

DOCS = facts.DOCS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-template", required=True, type=Path)
    ap.add_argument("--only", choices=["report", "paper", "slides"], action="append")
    args = ap.parse_args()
    want = set(args.only or ["report", "paper", "slides"])

    team = yaml.safe_load((DOCS / "data" / "team.yaml").read_text(encoding="utf-8"))
    f = facts.load_facts()
    results, rpath = facts.load_results()
    print(f"facts: {f['tests']['passed']} tests passed, {f['case_counts']['total']} cases, {f['n_languages']} languages")
    print("eval results:", rpath if rpath else "none found -> results sections will say PENDING")

    fig_dir = DOCS / "figures"
    figures.build_all(fig_dir, results)
    out = DOCS / "build"
    out.mkdir(exist_ok=True)

    missing: list[str] = []
    if "report" in want:
        import build_report

        tpl = out / "_template_copy.docx"
        shutil.copyfile(args.report_template, tpl)
        missing += build_report.build(out / "Project_Report.docx", f, team, results, fig_dir, tpl)
        tpl.unlink()
        print("wrote", out / "Project_Report.docx")
    if "paper" in want:
        import build_paper

        missing += build_paper.build(out / "IEEE_Paper.docx", f, team, results, fig_dir)
        print("wrote", out / "IEEE_Paper.docx")
    if "slides" in want:
        import build_slides

        missing += build_slides.build(out / "Presentation.pptx", f, team, results, fig_dir)
        print("wrote", out / "Presentation.pptx")

    if missing:
        uniq = sorted(set(missing))
        print(f"\n{len(uniq)} placeholder(s) still to fill in docs/data/team.yaml:")
        for m in uniq:
            print("  -", m)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
