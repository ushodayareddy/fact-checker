"""Build the IEEE conference-format paper (.docx).

Follows the standard IEEE conference layout: US Letter, two text columns after a single-column title block,
Times New Roman 10 pt, roman-numeral section headings, "Fig." / "TABLE" captions, bracketed numeric
references in order of first citation. This is a faithful approximation, not the official IEEE template;
if a venue supplies its own template, port the text into it.
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

import content as C
from facts import results_sentence
from refs import LITERATURE, Cite

FONT = "Times New Roman"
COL_W = 3.45  # usable column width in inches (8.5 - 2*0.625 margins, minus 0.25 gutter, over 2 columns)


def roman(n: int) -> str:
    out = ""
    for v, s in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out, n = out + s, n - v
    return out


def set_cols(section, num: int, space_in: float = 0.25) -> None:
    sectPr = section._sectPr
    for c in sectPr.findall(qn("w:cols")):
        sectPr.remove(c)
    cols = OxmlElement("w:cols")
    cols.set(qn("w:num"), str(num))
    cols.set(qn("w:space"), str(int(space_in * 1440)))
    sectPr.append(cols)


def font(run, size: float, bold=False, italic=False, small_caps=False) -> None:
    run.font.name = FONT
    run._r.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), FONT)
    run.font.size = Pt(size)
    run.bold, run.italic = bold, italic
    run.font.small_caps = small_caps


def borders(table, sz=4) -> None:
    pr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "bottom", "insideH"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(sz))
        el.set(qn("w:color"), "000000")
        b.append(el)
    pr.append(b)


class Paper:
    def __init__(self, facts, team, results, fig_dir):
        self.f, self.t, self.res, self.fig = facts, team, results, fig_dir
        self.doc = Document()
        self.cite = Cite()
        self.missing: list[str] = []
        self.sec_n = 0
        self.fig_n = 0
        self.tab_n = 0
        sec = self.doc.sections[0]
        sec.page_width, sec.page_height = Inches(8.5), Inches(11)
        sec.left_margin = sec.right_margin = Inches(0.625)
        sec.top_margin, sec.bottom_margin = Inches(0.75), Inches(1.0)
        normal = self.doc.styles["Normal"]
        normal.font.name, normal.font.size = FONT, Pt(10)
        normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)

    # --- primitives ---
    def p(self, text="", size=10, bold=False, italic=False, align=WD_ALIGN_PARAGRAPH.JUSTIFY, before=0, after=4, first_indent=None, keep_next=False):
        para = self.doc.add_paragraph()
        para.alignment = align
        pf = para.paragraph_format
        pf.space_before, pf.space_after, pf.line_spacing = Pt(before), Pt(after), 1.0
        if first_indent is not None:
            pf.first_line_indent = Inches(first_indent)
        pf.keep_with_next = keep_next
        if text:
            self.runs(para, self.cite.fmt(text), size, bold, italic)
        return para

    def runs(self, para, text, size=10, bold=False, italic=False):
        for part in re.split(r"(\*[^*]+\*)", text):
            if part.startswith("*") and part.endswith("*") and len(part) > 2:
                font(para.add_run(part[1:-1]), size, bold, True)
            elif part:
                font(para.add_run(part), size, bold, italic)

    def body(self, text):
        return self.p(text, first_indent=0.17)

    def h1(self, text):
        self.sec_n += 1
        self.sub_n = 0
        para = self.p("", align=WD_ALIGN_PARAGRAPH.CENTER, before=8, after=4, keep_next=True)
        font(para.add_run(f"{roman(self.sec_n)}. {text.upper()}"), 10, small_caps=False)
        return para

    def h1_unnumbered(self, text):
        """IEEE leaves Acknowledgment and References unnumbered."""
        para = self.p("", align=WD_ALIGN_PARAGRAPH.CENTER, before=8, after=4, keep_next=True)
        font(para.add_run(text.upper()), 10)
        return para

    def h2(self, text):
        self.sub_n += 1
        para = self.p("", align=WD_ALIGN_PARAGRAPH.LEFT, before=4, after=2, keep_next=True)
        font(para.add_run(f"{chr(64 + self.sub_n)}. {text}"), 10, italic=True)
        return para

    def bullets(self, items, numbered=False):
        for i, it in enumerate(items, 1):
            para = self.p("", after=2)
            para.paragraph_format.left_indent = Inches(0.22)
            para.paragraph_format.first_line_indent = Inches(-0.22)
            self.runs(para, (f"{i})  " if numbered else "•  ") + self.cite.fmt(it))

    def figure(self, path: Path, caption: str, width=COL_W, span=False):
        self.fig_n += 1
        para = self.p("", align=WD_ALIGN_PARAGRAPH.CENTER, before=4, after=2, keep_next=True)
        para.add_run().add_picture(str(path), width=Inches(width))
        cap = self.p("", align=WD_ALIGN_PARAGRAPH.CENTER, after=6)
        font(cap.add_run(f"Fig. {self.fig_n}. {caption}"), 8)

    def table(self, header, rows, widths, caption, size=8):
        self.tab_n += 1
        cap = self.p("", align=WD_ALIGN_PARAGRAPH.CENTER, before=4, after=2, keep_next=True)
        font(cap.add_run(f"TABLE {roman(self.tab_n)}"), 8)
        cap2 = self.p("", align=WD_ALIGN_PARAGRAPH.CENTER, after=3, keep_next=True)
        font(cap2.add_run(caption.upper()), 8)
        t = self.doc.add_table(rows=1, cols=len(header))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        borders(t)
        scale = COL_W / sum(widths)
        widths = [w * scale for w in widths]

        def fill(cell, text, bold=False):
            cell.text = ""
            para = cell.paragraphs[0]
            para.paragraph_format.space_after = Pt(0)
            para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            self.runs(para, self.cite.fmt(str(text)), size, bold)

        for i, h in enumerate(header):
            fill(t.rows[0].cells[i], h, True)
        for r in rows:
            cells = t.add_row().cells
            for i, v in enumerate(r):
                fill(cells[i], v)
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Inches(w)
            cs = OxmlElement("w:cantSplit")
            cs.set(qn("w:val"), "true")
            row._tr.get_or_add_trPr().append(cs)
        self.p("", after=4)

    # --- sections ---
    def title_block(self):
        d, t, m = self.doc, self.t, self.missing
        para = self.p("", align=WD_ALIGN_PARAGRAPH.CENTER, after=6)
        font(para.add_run(t["project_title"]), 22)
        names = []
        for i, s in enumerate(t["team"]):
            nm = s["name"].strip() or f"[Author {i + 1}]"
            if not s["name"].strip():
                m.append(f"Student {i + 1} name")
            names.append(nm)
        para = self.p("", align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
        font(para.add_run(", ".join(names)), 11)
        guide = t["guide"]["name"].strip() or "[Guide name]"
        if not t["guide"]["name"].strip():
            m.append("Guide name")
        para = self.p("", align=WD_ALIGN_PARAGRAPH.CENTER, after=0)
        font(para.add_run(f"Guide: {guide}"), 10, italic=True)
        para = self.p("", align=WD_ALIGN_PARAGRAPH.CENTER, after=0)
        font(para.add_run("Department of Computer Science & Engineering - AIML, School of Computer Science & Engineering"), 9, italic=True)
        para = self.p("", align=WD_ALIGN_PARAGRAPH.CENTER, after=8)
        font(para.add_run("Faculty of Engineering & Technology, JAIN (Deemed-to-be University), Bangalore, India"), 9, italic=True)
        # two-column body begins
        sec = d.add_section(WD_SECTION.CONTINUOUS)
        set_cols(sec, 2)

    def abstract(self, res_sentence):
        a = self.p("", after=2)
        a.paragraph_format.first_line_indent = Inches(0.17)
        font(a.add_run("Abstract—"), 9, bold=True, italic=True)
        self.runs(a, self.cite.fmt(C.abstract(self.f, res_sentence)), 9, bold=True)
        k = self.p("", after=6)
        k.paragraph_format.first_line_indent = Inches(0.17)
        font(k.add_run("Index Terms—"), 9, bold=True, italic=True)
        font(k.add_run(C.KEYWORDS.replace(";", ",") + "."), 9, bold=True)

    def content(self):
        f = self.f
        t = f["thresholds"]
        self.h1("Introduction")
        for x in C.INTRO_PAR:
            self.body(x)
        self.body("The contributions of this work are:")
        self.bullets(C.contributions(f), numbered=True)

        self.h1("Related Work")
        self.body(
            "Automated fact-checking is commonly decomposed into claim detection, evidence retrieval, verdict prediction and justification [@guo2022]. "
            "Table I summarises the datasets and methods most relevant to this work, using only what each paper reports."
        )
        rows = [[f"{name} [@{k}]", str(y), scope.split(";")[0], gap] for k, name, y, scope, finding, gap in LITERATURE]
        self.table(["Work", "Year", "Scope", "Gap for this problem"], rows, [0.85, 0.35, 1.15, 1.1], "Related work", size=7)
        self.body(
            "Of these, X-FACT [@gupta2021] is multilingual and the resources of Singhal et al. [@singhal2021] and Kazemi et al. [@kazemi2021] concern Indian languages, "
            "but all three are datasets or classifiers. Retrieval-augmented generation [@lewis2020] and ReAct [@yao2023] ground a language model in retrieved text but do not "
            "weigh sources by reliability or refuse to answer. To our knowledge from the papers surveyed, none combines local models, Indian-language coverage, explicit source "
            "credibility and a computed verdict policy; this survey is limited to the cited works."
        )

        self.h1("System Design")
        self.h2("Architecture")
        self.body(
            "The system is a pipeline of seven agents over a shared, typed state (Fig. 1). Each agent adds its results and emits a trace event that the interface shows live. "
            "Agents in blue use a generative language model; the others are ordinary code."
        )
        self.figure(self.fig / "architecture_tall.png", "Seven-agent pipeline and its evidence sources.", width=2.7)
        self.h2("Claim Routing and Evidence")
        self.body(
            "A claim is typed by keyword rules when exactly one rule family matches, and by the language model otherwise (defaulting to a general entity route if the model is unavailable). "
            "Each type has an ordered source list: " + "; ".join(f"{k}: {v}" for k, v in C.routing_rows(f)) + ". "
            "Queries run in the claim's language and in English, concurrently; results are de-duplicated by URL and ranked by multilingual embedding similarity [@chen2024]. "
            "A source that fails or times out is skipped with a warning."
        )
        self.h2("Source Credibility")
        for x in C.credibility_text(f):
            self.body(x)
        self.h2("Quote-Grounded Stances")
        self.body(
            "The verifier asks a local model [@yang2025] whether each evidence item supports, refutes or does not settle the claim, and requires an exact quote. "
            "The quote is normalised for case and whitespace and searched for in the item. If it is absent the stance becomes neutral, which removes confident judgements "
            "with invented justification."
        )
        self.h2("Verdict Policy")
        for x in C.verdict_text(f):
            self.body(x)
        self.figure(self.fig / "verdict_flow_paper.png", "Decision flow from weighted stances to a verdict label.", width=2.9)

        self.h1("Implementation")
        s, fe = f["settings"], f["frontend"]
        self.body(
            f"The backend is Python 3.12 with FastAPI and asynchronous I/O; agent progress streams to a React {fe['react']} interface over Server-Sent Events. "
            f"Models run through Ollama [@ollama]: {s['reasoning_model']} for reasoning, with {s['fallback_model']} [@gemma2025] as the configured alternative, and {s['embedding_model']} for embeddings. "
            "Because local models differ in tool-calling support, agents request schema-constrained JSON, validate it, and on failure return the validation error to the model and retry. "
            "Existing fact-checks are queried through the Fact Check Tools API when a key is configured [@googlefc]."
        )
        self.body(
            f"Languages carry a resource tier. High: {C.tier_names(f, 'high')}. Medium: {C.tier_names(f, 'medium')}. Low: {C.tier_names(f, 'low')}. "
            f"The tier caps confidence at {t['cap']['high']:.2f}, {t['cap']['medium']:.2f} and {t['cap']['low']:.2f}, and low-tier languages display a warning."
        )

        self.h1("Testing and Evaluation")
        tf = f["tests"]
        self.body(
            f"The backend has {tf['passed']} passing automated tests across {tf['files']} files and {tf['xfailed']} expected failure, using scripted model replies and recorded response shapes. "
            "They verify logic and failure handling, not model quality or live-source behaviour."
        )
        for x in C.eval_design(f):
            self.body(x)
        self.h2("Results")
        if self.res:
            self.results()
        else:
            para = self.p("", first_indent=0.17)
            font(para.add_run("Results pending. "), 10, bold=True)
            font(para.add_run(
                "The evaluation has not yet been run with a local model and live sources, so this paper reports no accuracy figure. "
                "Reporting numbers measured only with scripted models would not reflect real behaviour."), 10)

        self.h1("Limitations and Future Work")
        self.body("The following limitations apply.")
        self.bullets(C.limitations())
        self.body("Future work includes:")
        self.bullets(C.future_work())

        self.h1("Conclusion")
        self.body(
            "We presented a seven-agent, locally hosted framework for fact-checking claims in Indian languages, built around a quote-grounded stance rule, a transparent source-credibility "
            "model and a verdict policy computed by rules so that the language model explains a decision without making it. "
            + ("" if self.res else "Its accuracy with real models and live sources is not yet measured and is the first thing to evaluate.")
        )

    def results(self):
        ov = self.res["summary"]["overall"]
        self.body(results_sentence(self.res))
        rows = []
        for lang, c in self.res["summary"]["by_language"].items():
            a = "n/a" if c["accuracy"] is None else f"{c['accuracy']:.0%}"
            rows.append([lang, str(c["total"]), str(c["pass"]), str(c["abstain"]), str(c["fail"]), a])
        self.table(["Lang", "n", "Pass", "Abst.", "Fail", "Acc."], rows, [0.7, 0.4, 0.5, 0.5, 0.5, 0.6], "Results by language")

    def acknowledgment(self):
        self.h1_unnumbered("Acknowledgment")
        guide = self.t["guide"]["name"].strip() or "[Guide name]"
        self.body(f"The authors thank their guide, {guide}, and the Department of Computer Science & Engineering - AIML, JAIN (Deemed-to-be University), for their guidance and support.")

    def references(self):
        self.h1_unnumbered("References")
        for n, text in self.cite.entries():
            para = self.p("", after=2)
            para.paragraph_format.left_indent = Inches(0.3)
            para.paragraph_format.first_line_indent = Inches(-0.3)
            para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            self.runs(para, f"[{n}]  {text}", 8)


def build(out: Path, facts: dict, team: dict, results, fig_dir: Path) -> list[str]:
    pp = Paper(facts, team, results, fig_dir)
    pp.title_block()
    pp.abstract(results_sentence(results) if results else "")
    pp.content()
    pp.acknowledgment()
    pp.references()
    from build_report import clear_metadata, drop_unused_links, verify_images
    drop_unused_links(pp.doc)
    clear_metadata(pp.doc)
    pp.doc.save(str(out))
    problems = verify_images(out)
    if problems:
        raise SystemExit("Broken pictures in the paper:\n  " + "\n  ".join(problems))
    return pp.missing
