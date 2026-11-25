"""Build the Jain University project report from the supplied template.

Keeps the template's cover, certificate, declaration, acknowledgement and styles, replaces every piece of the
previous team's content, and generates the table of contents, nomenclature, list of figures and chapters.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

import content as C
from refs import LITERATURE, REFS, Cite

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def ph(value: str, label: str, missing: list[str]) -> str:
    """Return value, or a visible [placeholder] (recorded for the end-of-build report)."""
    value = (value or "").strip()
    if value:
        return value
    missing.append(label)
    return f"[{label}]"


def set_text(p, text: str) -> None:
    """Replace a paragraph's text, keeping the first run's formatting."""
    runs = p.runs
    if not runs:
        p.add_run(text)
        return
    runs[0].text = text
    for r in runs[1:]:
        r._r.getparent().remove(r._r)


def all_text(el) -> str:
    return "".join(t.text or "" for t in el.iter(f"{{{W}}}t"))


def delete(el) -> None:
    el.getparent().remove(el)


def add_field(paragraph, instr: str) -> None:
    """Insert a Word field (TOC, PAGE...) that Word fills in when the document is opened or fields are updated."""
    for kind, text in (("begin", None), (None, instr), ("separate", None), (None, "Right-click here and choose Update Field to build the table of contents."), ("end", None)):
        r = paragraph.add_run()
        if kind:
            fc = OxmlElement("w:fldChar")
            fc.set(qn("w:fldCharType"), kind)
            r._r.append(fc)
        elif text == instr:
            it = OxmlElement("w:instrText")
            it.set(qn("xml:space"), "preserve")
            it.text = instr
            r._r.append(it)
        else:
            r._r.append(OxmlElement("w:t"))
            r._r[-1].text = text


def shade(cell, fill: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def set_borders(table, color: str = "7F7F7F", sz: int = 4) -> None:
    """Single-line borders on every edge; the Jain template defines no 'Table Grid' style."""
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(sz))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        borders.append(el)
    tblPr.append(borders)


def repeat_header(row) -> None:
    trPr = row._tr.get_or_add_trPr()
    h = OxmlElement("w:tblHeader")
    h.set(qn("w:val"), "true")
    trPr.append(h)


class Report:
    def __init__(self, template: Path, facts: dict, team: dict, results, fig_dir: Path):
        self.doc = Document(str(template))
        self.f, self.t, self.res, self.fig = facts, team, results, fig_dir
        self.cite = Cite()
        self.missing: list[str] = []
        self.figures: list[tuple[str, str]] = []  # (number, caption)
        self.tables: list[tuple[str, str]] = []
        self.chapter = 0

    # ---------- low-level body helpers ----------
    @property
    def body(self):
        return self.doc.element.body

    def para(self, text="", style="Body Text", align=None, bold=None, size=None, italic=None, keep_next=False, before=None, after=None):
        p = self.doc.add_paragraph(style=style)
        if text:
            r = p.add_run(self.cite.fmt(text))
            if bold is not None:
                r.bold = bold
            if italic is not None:
                r.italic = italic
            if size:
                r.font.size = Pt(size)
        if align is not None:
            p.alignment = align
        pf = p.paragraph_format
        if keep_next:
            pf.keep_with_next = True
        if before is not None:
            pf.space_before = Pt(before)
        pf.space_after = Pt(6 if after is None else after)
        pf.line_spacing = 1.15
        return p

    def body_text(self, text: str):
        return self.para(text, "Body Text", WD_ALIGN_PARAGRAPH.JUSTIFY)

    def bullets(self, items: list[str]):
        for it in items:
            p = self.para("", "List Paragraph", WD_ALIGN_PARAGRAPH.JUSTIFY, after=3)
            p.paragraph_format.left_indent = Inches(0.35)
            p.paragraph_format.first_line_indent = Inches(-0.2)
            p.add_run("•  " + self.cite.fmt(it))

    def numbered(self, items: list[str]):
        for i, it in enumerate(items, 1):
            p = self.para("", "List Paragraph", WD_ALIGN_PARAGRAPH.JUSTIFY, after=3)
            p.paragraph_format.left_indent = Inches(0.35)
            p.paragraph_format.first_line_indent = Inches(-0.28)
            p.add_run(f"{i}.  " + self.cite.fmt(it))

    def chapter_start(self, title: str):
        self.chapter += 1
        self.sub = 0
        self.page_break()
        self.para(f"Chapter {self.chapter}", "Heading 1", WD_ALIGN_PARAGRAPH.CENTER)
        self.para(title.upper(), "Heading 2", WD_ALIGN_PARAGRAPH.CENTER)

    def h(self, text: str, level=3):
        self.sub += 1
        number = f"{self.chapter}.{self.sub}  " if level == 3 else ""
        return self.para(number + text, f"Heading {level}", None, keep_next=True, before=10)

    def h_plain(self, text: str, level=4):
        return self.para(text, f"Heading {level}", None, keep_next=True, before=6)

    def page_break(self):
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def table(self, header: list[str], rows: list[list[str]], widths: list[float], caption: str, size=10, fills: dict | None = None):
        self.tcount = getattr(self, "tcount", {})
        key = getattr(self, "appendix_mode", None) or self.chapter
        self.tcount[key] = self.tcount.get(key, 0) + 1
        label = f"Table {key}.{self.tcount[key]}"
        self.tables.append((label, caption))
        cap = self.para(f"{label}: {caption}", "Heading 5", WD_ALIGN_PARAGRAPH.CENTER, keep_next=True, before=8)
        t = self.doc.add_table(rows=1, cols=len(header))
        set_borders(t)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        for i, hd in enumerate(header):
            c = t.rows[0].cells[i]
            c.text = ""
            r = c.paragraphs[0].add_run(hd)
            r.bold, r.font.size = True, Pt(size)
            shade(c, "D9E2F3")
        repeat_header(t.rows[0])
        for row in rows:
            cells = t.add_row().cells
            for i, val in enumerate(row):
                cells[i].text = ""
                p = cells[i].paragraphs[0]
                r = p.add_run(self.cite.fmt(str(val)))
                r.font.size = Pt(size)
                p.paragraph_format.space_after = Pt(0)
        scale = getattr(self, "usable", 6.0) / sum(widths)
        widths = [w * scale for w in widths]
        for row in t.rows:
            row.cells[0]._tc.get_or_add_tcPr()
            for i, wd in enumerate(widths):
                row.cells[i].width = Inches(wd)
            trPr = row._tr.get_or_add_trPr()
            cs = OxmlElement("w:cantSplit")
            cs.set(qn("w:val"), "true")
            trPr.append(cs)
        self.para("", "Body Text", after=4)
        return t

    def figure(self, path: Path, caption: str, width_in: float):
        self.fcount = getattr(self, "fcount", {})
        self.fcount[self.chapter] = self.fcount.get(self.chapter, 0) + 1
        label = f"Fig. {self.chapter}.{self.fcount[self.chapter]}"
        self.figures.append((label, caption))
        p = self.para("", "Body Text", WD_ALIGN_PARAGRAPH.CENTER, keep_next=True, before=6)
        p.add_run().add_picture(str(path), width=Inches(min(width_in, getattr(self, 'usable', 6.0))))
        self.para(f"{label}: {caption}", "Heading 5", WD_ALIGN_PARAGRAPH.CENTER, after=10)

    # ---------- template surgery ----------
    def front_matter(self):
        d, t, m = self.doc, self.t, self.missing
        title = t["project_title"]
        team = t["team"]
        names = [f"{ph(s['name'], f'Student {i + 1} name', m).upper()} ({ph(s['usn'], f'Student {i + 1} USN', m)})" for i, s in enumerate(team)]
        guide = ph(t["guide"]["name"], "Guide name", m)
        year = ph(t["academic_year"], "Academic year", m)
        sem = ph(t["semester"], "Semester", m)
        place = t["place"]
        date = t["date"] or ""
        if not date:
            m.append("Date")

        paras = d.paragraphs
        for p in paras:
            txt = p.text.strip()
            if txt == "2025-2026":
                set_text(p, year)
            elif txt == "(VII Semester)":
                set_text(p, f"({sem})")
            elif txt.startswith("An Advanced Emergency Response Platform") and p.style.name == "Heading 4":
                set_text(p, title)
            elif txt.startswith("SHREYASH JAIN (21BTRSE042) RACHITA"):
                set_text(p, "  ".join(names[:4]))
            elif txt.startswith("KANALA CHENNA KESHAVA REDDY (21BTRSE051)"):
                set_text(p, "  ".join(names[4:]) if len(names) > 4 else "")
            elif txt == "Dr.K.S.Arvind":
                set_text(p, guide)
            elif txt == "Associate Professor":
                set_text(p, t["guide"]["designation"])
            elif txt.startswith("This is to certify that the project work titled"):
                set_text(
                    p,
                    f"This is to certify that the project work titled {title} is carried out by "
                    + "; ".join(names)
                    + f", bonafide students of Bachelor of Technology at the School of Computer Science and Engineering - AIML, Faculty of Engineering & Technology, "
                    f"JAIN (Deemed-to-be University), Bangalore, in partial fulfilment for the award of the degree of Bachelor of Technology in Computer Science & Engineering - AIML, during the year {year}.",
                )
            elif txt.startswith("We , SHREYASH JAIN"):
                set_text(p, f"We, {'; '.join(names)}, students of B.Tech in Computer Science & Engineering - AIML, at School of Computer Science and Engineering,")
            elif txt.startswith("CHENNA KESHAVA REDDY (21BTRSE037) student of 8TH"):
                set_text(
                    p,
                    "Faculty of Engineering & Technology, JAIN (Deemed to-be University), hereby declare that the project work titled "
                    f"“{title}” has been carried out by us and submitted in partial fulfilment for the award of the degree of Bachelor of Technology in "
                    f"Computer Science & Engineering - AIML during the academic year {year}. Further, the matter presented in the work has not been submitted previously "
                    "by anybody for the award of any degree or any diploma to any other University, to the best of our knowledge and faith.",
                )
            elif txt.startswith("Place: Bangalore"):
                set_text(p, f"Place: {place}        Date: {date or '[Date]'}")
            elif txt.startswith("I would like to thank our guide Dr. K.S.Arvind"):
                set_text(
                    p,
                    f"I would like to thank our guide {guide}, {t['guide']['designation']}, Dept. of Computer Science & Engineering - AIML, for sparing valuable time to extend help "
                    "in every step of my work, which paved the way for smooth progress and fruitful culmination of the project.",
                )
            elif txt.startswith("I would like to thank our Project Coordinator"):
                set_text(p, f"I would like to thank our Project Coordinator {t['project_coordinator']}, and all the staff members of Computer Science & Engineering - AIML for their support.")
            elif txt.startswith("It is a matter of immense pleasure to express my sincere thanks to Dr. Somasekar J"):
                set_text(p, p.text.replace("Dr. Somasekar J", t["program_head"]))
            elif txt.startswith("I extend my sincere gratitude to Dr. Anu V R"):
                set_text(p, p.text.replace("Dr. Kamlesh Tiwari", t["head_of_department"]))
            elif txt.startswith("I am deeply thankful to several individuals") and "XXXXX" in txt:
                set_text(p, txt.replace(" I am also profoundly grateful to the honorable Vice Chancellor XXXXX, for their unwavering support.", " I am also profoundly grateful to the honourable Vice Chancellor for the unwavering support."))
            elif txt.startswith("Fire emergencies can happen without warning"):
                self.abstract_para = p

        # certificate signatories table
        sig = d.tables[0]
        for ci, nm in enumerate((guide, t["program_head"], t["head_of_department"])):
            set_text(sig.rows[0].cells[ci].paragraphs[0], nm)

        # declaration table (one name per row): rebuild rows to match team size
        decl = d.tables[1]
        base = copy.deepcopy(decl.rows[0]._tr)
        for r in list(decl.rows):
            decl._tbl.remove(r._tr)
        for nm in names:
            tr = copy.deepcopy(base)
            decl._tbl.append(tr)
        for row, nm in zip(decl.rows, names):
            cell = row.cells[0]
            ps = cell.paragraphs
            set_text(ps[0], nm)
            for extra in ps[1:]:
                extra._p.getparent().remove(extra._p)

        # signature block in acknowledgement
        sign_re = re.compile(r"^(Shreyash Jain|Rachita Nangalia|Sameer Patel|Fardeen Khan|Kanala Chenna Keshava Reddy|21BTRSE\d+)")
        first = True
        for p in list(d.paragraphs):
            if sign_re.match(p.text.strip()) and p.text.strip():
                if first:
                    lines = [f"{s['name'] or '[Name]'}  {s['usn'] or '[USN]'}" for s in team]
                    set_text(p, lines[0])
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    anchor = p
                    for extra in lines[1:]:
                        np_ = copy.deepcopy(anchor._p)
                        anchor._p.addnext(np_)
                        from docx.text.paragraph import Paragraph as _P
                        anchor = _P(np_, anchor._parent)
                        set_text(anchor, extra)
                    first = False
                else:
                    delete(p._p)

    def strip_old_body(self):
        """Delete everything from the abstract's heading to the end, keeping the last section's page setup and header/footer."""
        kids = list(self.body.iterchildren())
        start = None
        for i, el in enumerate(kids):
            if el.tag == f"{{{W}}}p" and all_text(el).strip() == "ABSTRACT":
                start = i
                break
        assert start is not None, "ABSTRACT heading not found in template"
        final_sect = kids[-1]
        assert final_sect.tag == f"{{{W}}}sectPr"
        # the information-regarding-students page at the end uses its own section; we drop it and rebuild nothing
        for el in kids[start:-1]:
            delete(el)
        return start

    # ---------- generated sections ----------
    def body_section(self):
        """Close the template's front matter and open a body section with sane A4 geometry.

        The template's last section belongs to its 'Information regarding students' page (0.3 in right margin,
        0 bottom margin); everything generated after the cut would otherwise inherit it.
        """
        sec = self.doc.sections[-1]
        new = self.doc.add_section(WD_SECTION.NEW_PAGE)
        new.page_width, new.page_height = Inches(8.27), Inches(11.69)
        new.left_margin, new.right_margin = Inches(1.18), Inches(1.0)
        new.top_margin, new.bottom_margin = Inches(1.0), Inches(0.9)
        new.header_distance, new.footer_distance = Inches(0.4), Inches(0.4)
        new.header.is_linked_to_previous = True
        new.footer.is_linked_to_previous = True
        self.usable = round(new.page_width.inches - new.left_margin.inches - new.right_margin.inches - 0.02, 2)

    def abstract(self, res_sentence: str):
        self.para("ABSTRACT", "Heading 1", WD_ALIGN_PARAGRAPH.CENTER)
        self.body_text(C.abstract(self.f, res_sentence))
        self.para("Keywords: " + C.KEYWORDS + ".", "Body Text", WD_ALIGN_PARAGRAPH.JUSTIFY, italic=True)

    def build_chapters(self):
        f, t = self.f, self.t
        # ---- Chapter 1
        self.chapter_start("Introduction")
        self.h("Background and Motivation")
        for ptxt in C.INTRO_PAR[:2]:
            self.body_text(ptxt)
        self.h("Problem Statement")
        self.body_text(C.PROBLEM_STATEMENT)
        self.h("Objectives")
        self.numbered(C.OBJECTIVES)
        self.h("Contributions")
        self.body_text(C.INTRO_PAR[2])
        self.numbered(C.contributions(f))
        self.h("Scope and Organisation of the Report")
        self.body_text(
            f"The system covers claims in {f['n_languages'] - 1} scheduled languages and English, text and article links only. Chapter 2 surveys related work. Chapter 3 "
            "describes the system design and the algorithms. Chapter 4 describes the implementation. Chapter 5 describes testing and the evaluation design and reports the "
            "status of results. Chapter 6 discusses limitations and future work."
        )

        # ---- Chapter 2
        self.chapter_start("Literature Survey")
        self.body_text(
            "Related work falls into three groups: English datasets and surveys that define the task, multilingual and Indian-language resources, and methods that combine "
            "retrieval with language models. Table 2.1 summarises them. Entries describe only what the cited paper reports."
        )
        rows = [[f"{i + 1}", f"{name} [@{k}]", str(y), scope, finding, gap] for i, (k, name, y, scope, finding, gap) in enumerate(LITERATURE)]
        self.table(["S. No", "Work", "Year", "Scope and size", "Key finding", "Limitation for this problem"], rows, [0.4, 0.9, 0.45, 1.6, 1.4, 1.35], "Summary of related work", size=8)
        self.h("Task Definition and Surveys")
        self.body_text(
            "Guo et al. [@guo2022] survey automated fact-checking as a pipeline of claim detection, evidence retrieval, verdict prediction and justification production, and identify "
            "the lack of explanation and of non-English coverage as open problems. This work follows that decomposition but makes each stage an explicit agent."
        )
        self.h("Multilingual and Indian-Language Resources")
        self.body_text(
            "X-FACT [@gupta2021] gathers short statements in 25 languages labelled by fact-checkers and reports that the best model reaches about 40% F-score, showing the task is hard "
            "across languages. Singhal et al. [@singhal2021] collect samples from Indian fact-checking sites, and Kazemi et al. [@kazemi2021] study claim matching across English, Hindi, "
            "Bengali, Malayalam and Tamil. These resources show demand and supply data, but they stop at datasets and classifiers."
        )
        self.h("Retrieval and Reasoning with Language Models")
        self.body_text(
            "Retrieval-augmented generation [@lewis2020] grounds a generator in a retrieved corpus, and ReAct [@yao2023] interleaves reasoning with actions such as looking up Wikipedia. "
            "Both inform the retrieval-then-judge structure used here. Neither provides a policy for weighing sources of different reliability or for refusing to answer."
        )
        self.h("Research Gap")
        self.body_text(
            "No work found in this survey combines (i) local, open models, (ii) coverage that targets all scheduled Indian languages, (iii) explicit source-credibility scoring, and (iv) a verdict "
            "policy that is computed rather than generated. This report addresses that combination. The survey is limited to the papers cited and does not claim that no other such system exists."
        )

        # ---- Chapter 3
        self.chapter_start("System Design")
        self.h("Overview")
        self.body_text(
            "The system is a pipeline of seven agents that share a typed state object. Each agent reads the state, adds its results and emits trace events that the interface shows live. "
            "Figure 3.1 shows the flow; agents drawn in blue use a generative language model and the others are ordinary code."
        )
        self.figure(self.fig / "architecture_wide.png", "System architecture: seven agents and the evidence sources", 6.3)
        self.table(["Agent", "Input", "Method", "Output"], [list(r) for r in C.agent_table(f)], [1.0, 1.0, 3.1, 1.1], "Responsibilities of the seven agents", size=8)
        self.h("Claim-Type Routing and Evidence Sources")
        self.body_text(
            "Different claims need different evidence: a budget figure belongs to government sources, a WhatsApp rumour is best checked against fact-check archives, and a fact about a landmark is "
            "in an encyclopaedia. The router assigns one of five claim types and each type has an ordered source list (Table 3.2). Adapters whose credentials are missing skip themselves."
        )
        self.table(["Claim type", "Sources queried"], [list(r) for r in C.routing_rows(f)], [1.6, 4.4], "Claim type to evidence source routing", size=9)
        self.table(["Source", "How it is queried", "Known limitation"], [list(r) for r in C.adapter_table()], [1.2, 2.6, 2.2], "Evidence adapters", size=8)
        self.h("Source Credibility")
        for ptxt in C.credibility_text(f):
            self.body_text(ptxt)
        st = f["source_tiers"]
        self.table(
            ["Tier", "Prior", "Examples"],
            [[k.replace("_", " "), f"{v['credibility']:.2f}", ", ".join(v["domains"][:5]) if v["domains"] else "any other domain"] for k, v in st.items()],
            [1.7, 0.6, 3.7], "Source credibility priors", size=9,
        )
        self.h("Quote-Grounded Stance Judgement")
        self.body_text(
            "For each evidence item the verifier asks the model whether the item supports, refutes or does not settle the claim, and requires an exact quote. The quote is normalised for case and whitespace "
            "and searched for in the item's title and text. If it is absent, the stance is replaced by neutral. This removes one form of hallucination: a confident judgement with an invented justification."
        )
        self.h("Verdict Policy")
        for ptxt in C.verdict_text(f):
            self.body_text(ptxt)
        self.figure(self.fig / "verdict_flow_report.png", "Decision flow from weighted stances to a verdict label", 4.4)
        self.h("Use Case and Data Flow")
        self.body_text(
            "A user pastes a claim or link in the web interface. The backend streams one trace event per agent step over Server-Sent Events so the user sees progress during the long local-model calls. "
            "When the run finishes, the interface shows each claim with its verdict, confidence, caveats, and the evidence list ordered with cited items first, each with its stance, quote, tier and credibility."
        )

        # ---- Chapter 4
        self.chapter_start("Implementation")
        self.h("Technology Stack")
        self.table(["Component", "Technology"], [list(r) for r in C.implementation_rows(f)], [1.4, 4.6], "Implementation stack", size=9)
        self.h("Structured Output from Local Models")
        self.body_text(
            "Local models differ in tool-calling support, so the agents do not rely on it. Each agent requests JSON constrained by a schema, validates the reply, and on failure sends the validation "
            "error back and retries. This keeps the code independent of the particular model."
        )
        self.h("Language Handling")
        lows = C.tier_names(f, "low")
        self.body_text(
            f"Languages are assigned a resource tier. High: {C.tier_names(f, 'high')}. Medium: {C.tier_names(f, 'medium')}. Low: {lows}. The tier decides the confidence cap, and a warning is shown for low-tier languages. "
            "Queries run in the claim's language and in English because indexed content in many Indian languages is thin."
        )
        self.h("Robustness")
        self.bullets(C.robustness_points())
        self.h("Windows Setup")
        self.body_text("The repository includes batch scripts to install dependencies and models, start the application, and run the evaluation and write a report file.")

        # ---- Chapter 5
        self.chapter_start("Testing and Evaluation")
        self.h("Automated Tests")
        tf = f["tests"]
        self.body_text(
            f"The backend has {tf['passed']} passing tests across {tf['files']} files and {tf['xfailed']} expected failure. Tests use scripted language-model replies and recorded response shapes, so they "
            "verify logic and failure handling but not model quality or live-source behaviour."
        )
        self.table(["Area covered", "Tests"], [list(r) for r in C.testing_rows(f)], [5.0, 1.0], "Automated tests by area", size=9)
        self.body_text(
            "The expected failure is deliberate: a correct Marathi sentence in the evaluation set is identified as Hindi by the language detector. It is marked as an expected failure so that the gap stays visible and the test suite flags it when the detector improves."
        )
        self.h("Evaluation Design")
        for ptxt in C.eval_design(f):
            self.body_text(ptxt)
        cc = f["case_counts"]
        self.table(
            ["Language", "Cases"],
            [[f["languages"][k].name if k in f["languages"] else k, str(v)] for k, v in sorted(cc["by_lang"].items(), key=lambda kv: -kv[1])],
            [2.5, 1.0], "Evaluation cases per language", size=9,
        )
        self.h("Results")
        if self.res:
            self.results_section()
        else:
            self.para(
                "RESULTS PENDING. The evaluation has not yet been run on a local model with live sources, so no accuracy figure is reported in this document. "
                "To produce results, run the evaluation script, place its JSON report at docs/data/eval_results.json, and rebuild the documents; this section then fills in automatically.",
                "Body Text", WD_ALIGN_PARAGRAPH.JUSTIFY, bold=True,
            )

        # ---- Chapter 6
        self.chapter_start("Conclusion and Future Work")
        self.h("Conclusion")
        self.body_text(
            "This work implements a seven-agent, locally hosted framework for fact-checking claims in Indian languages. Its distinguishing choices are a quote-grounded stance rule, a transparent "
            "source-credibility model, and a verdict policy computed by rules so that the language model explains a decision without making it. The implementation is covered by automated tests, "
            "and an evaluation set is in place. "
            + ("" if self.res else "The central open question, how accurate the system is with real models and live sources, is not answered by this document and is the first thing to measure next.")
        )
        self.h("Limitations")
        self.bullets(C.limitations())
        self.h("Future Work")
        self.bullets(C.future_work())

    def results_section(self):
        res = self.res
        ov = res["summary"]["overall"]
        self.body_text(C_results_sentence(res) + " These figures come from the evaluation report named in the appendix and are not adjusted.")
        rows = []
        for lang, c in res["summary"]["by_language"].items():
            acc = "n/a" if c["accuracy"] is None else f"{c['accuracy']:.0%}"
            rows.append([lang, str(c["total"]), str(c["pass"]), str(c["abstain"]), str(c["fail"]), str(c["error"]), acc])
        self.table(["Language", "Cases", "Pass", "Abstain", "Fail", "Error", "Accuracy"], rows, [1.2, 0.7, 0.7, 0.8, 0.7, 0.7, 0.9], "Evaluation results by language", size=9)
        fig = self.fig / "accuracy_by_language.png"
        if fig.exists():
            self.figure(fig, "Accuracy by language (answered cases)", 5.4)
        bad = [r for r in res["rows"] if r["status"] in ("fail", "error")]
        if bad:
            self.h_plain("Failures and errors")
            self.bullets([f"{r['id']} ({r['lang']}, {r['status']}): expected {', '.join(r['expect'])}, got {r.get('outcome') or r.get('error')}" for r in bad])

    def references(self):
        self.page_break()
        self.para("REFERENCES", "Heading 2", None)
        for n, text in self.cite.entries():
            p = self.para("", "List Paragraph", WD_ALIGN_PARAGRAPH.JUSTIFY, after=4)
            p.paragraph_format.left_indent = Inches(0.4)
            p.paragraph_format.first_line_indent = Inches(-0.4)
            p.add_run(f"[{n}]  ")
            for part in re.split(r"(\*[^*]+\*)", text):
                if part.startswith("*") and part.endswith("*"):
                    p.add_run(part[1:-1]).italic = True
                else:
                    p.add_run(part)

    def appendix(self):
        self.page_break()
        self.appendix_mode = "A"
        self.para("APPENDIX A: EVALUATION CASES", "Heading 2", None)
        self.body_text("The non-English claims were translated by an AI system and have not been reviewed by native speakers.")
        rows = [[c["id"], c["lang"], c["category"], ", ".join(c["expect"]), c["text"]] for c in self.f["cases"]]
        self.table(["ID", "Lang", "Category", "Expected", "Claim"], rows, [0.6, 0.45, 0.8, 0.8, 3.35], "The 50 labelled evaluation cases", size=8)

    def contents_pages(self):
        """Replace the template's hand-typed TOC / nomenclature / figure tables with generated ones."""
        d = self.doc
        # table of contents: fixed field, so page numbers are right once Word updates fields
        tocs = [t for t in d.tables if t.rows and t.rows[0].cells[0].text.strip() == "CERTIFICATE"]
        for t in tocs:
            anchor = t._tbl
            parent = anchor.getparent()
            p = OxmlElement("w:p")
            parent.insert(parent.index(anchor), p)
            from docx.text.paragraph import Paragraph

            par = Paragraph(p, d._body)
            add_field(par, r'TOC \o "1-3" \h \z \u')
            parent.remove(anchor)
        for t in [t for t in d.tables if t.rows and t.rows[0].cells[0].text.strip() == "References"]:
            t._tbl.getparent().remove(t._tbl)

    def nomenclature(self):
        d = self.doc
        terms = [
            ("LLM", "Large language model"), ("RAG", "Retrieval-augmented generation"), ("NLI", "Natural language inference"),
            ("IFCN", "International Fact-Checking Network"), ("SSE", "Server-Sent Events"), ("API", "Application programming interface"),
            ("CVD", "Color vision deficiency"), ("W_sup / W_ref", "Credibility-weighted weight of supporting / refuting sources"),
            ("Tier", "Language resource level (high, medium, low) used to cap confidence"), ("Stance", "Supports, refutes or neutral judgement of one source towards a claim"),
        ]
        tbl = next(t for t in d.tables if t.rows[0].cells[0].text.strip() == "Symbol/Term")
        for r in list(tbl.rows)[1:]:
            tbl._tbl.remove(r._tr)
        for a, b in terms:
            cells = tbl.add_row().cells
            cells[0].text, cells[1].text = a, b

    def list_of_figures(self):
        d = self.doc
        tbl = next(t for t in d.tables if t.rows[0].cells[0].text.strip() == "Figure No.")
        for r in list(tbl.rows)[1:]:
            tbl._tbl.remove(r._tr)
        for label, cap in self.figures:
            cells = tbl.add_row().cells
            cells[0].text, cells[1].text, cells[2].text = label, cap, ""
        for label, cap in self.tables:
            cells = tbl.add_row().cells
            cells[0].text, cells[1].text, cells[2].text = label, cap, ""


def C_results_sentence(res: dict) -> str:
    from facts import results_sentence

    return results_sentence(res)


def set_header_footer(doc: Document, short: str) -> None:
    """Rewrite header text, including text boxes.

    Works on the package's header parts directly: python-docx only exposes a header for sections that carry
    their own reference, and most sections of the template inherit one. The template splits words across
    runs ("FIRE", " ", "GUIDE") and repeats each text node in a Word/legacy fallback copy, so every copy is edited.
    """
    A = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"
    HDR = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/header"
    done = 0
    for rel in doc.part.rels.values():
        if rel.reltype != HDR:
            continue
        root = rel.target_part.element
        nodes = [n for n in root.iter() if n.tag in (f"{{{W}}}t", A)]
        texts = [(n.text or "").strip() for n in nodes]
        if "Project title" in texts or "FIRE" in texts:
            for n, t in zip(nodes, texts):
                if t in ("Project title", "FIRE"):
                    n.text = short
                elif t == "GUIDE":
                    n.text = ""
            done += 1
    print(f"  rewrote {done} header part(s)")


def prune_orphan_media(path: Path) -> int:
    """Remove images that no part references any more (the template's old figures stay in the zip otherwise)."""
    import re
    import zipfile

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}
    # A media file is kept if any relationship targets it AND the owning part's XML uses that relationship id
    # in any r:* attribute (embed, link, pict, id). Anything else is an orphan left by deleted template content.
    referenced = set()
    for n, b in data.items():
        if not n.endswith(".rels"):
            continue
        part = n.replace("_rels/", "").removesuffix(".rels")
        part_xml = data.get(part, b"")
        used_ids = set(re.findall(rb'r:[A-Za-z]+="([^"]+)"', part_xml))
        for rel in re.findall(rb"<Relationship [^>]*/>", b):
            rid = re.search(rb'Id="([^"]+)"', rel)
            tgt = re.search(rb'Target="([^"]+)"', rel)
            if rid and tgt and b"media/" in tgt.group(1) and rid.group(1) in used_ids:
                referenced.add("word/media/" + tgt.group(1).decode().split("media/")[-1])
    drop = [n for n in names if n.startswith("word/media/") and n not in referenced]
    if not drop:
        return 0
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
        for n in names:
            if n in drop:
                continue
            b = data[n]
            if n.endswith(".rels"):
                for d_ in drop:
                    b = re.sub(rb"<Relationship [^>]*Target=\"" + re.escape(d_.removeprefix("word/").encode()) + rb"\"[^>]*/>", b"", b)
            out.writestr(n, b)
    tmp.replace(path)
    return len(drop)


def _used_rel_ids(root) -> set[str]:
    """Every relationship id a part's XML refers to, whatever attribute carries it (id, embed, link, pict...)."""
    R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    return {v for el in root.iter() for k, v in el.attrib.items() if k.startswith(R)}


def drop_unused_links(doc: Document) -> int:
    """Remove hyperlink relationships that nothing refers to any more.

    Deleting template content leaves its relationships behind, so the old student e-mail links would still ship.
    Only hyperlinks are dropped here. python-docx's own _rel_ref_count looks at r:id alone, so it reports pictures
    (which use r:embed) as unused and deleting by it removes every image. Orphaned images are handled by
    prune_orphan_media instead.
    """
    NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
    used = _used_rel_ids(doc.element)
    for rel in doc.part.rels.values():
        if rel.reltype in (NS + "header", NS + "footer"):
            used |= _used_rel_ids(rel.target_part.element)
    dropped = 0
    for rId, rel in list(doc.part.rels.items()):
        if rel.reltype == NS + "hyperlink" and rId not in used:
            doc.part.drop_rel(rId)
            dropped += 1
    return dropped


def verify_images(path: Path) -> list[str]:
    """Fail loudly if any picture reference points at a missing relationship or a missing media file."""
    import posixpath
    import re
    import zipfile

    problems = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        for part in [n for n in names if n.startswith("word/") and n.endswith(".xml") and "/_rels/" not in n]:
            xml = z.read(part).decode("utf8", "ignore")
            ids = set(re.findall(r'r:(?:embed|link|pict)="([^"]+)"', xml))
            if not ids:
                continue
            rels_name = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
            rels = z.read(rels_name).decode("utf8", "ignore") if rels_name in names else ""
            targets = {}
            for rel in re.findall(r"<Relationship [^>]*/>", rels):
                rid = re.search(r'Id="([^"]+)"', rel)
                tgt = re.search(r'Target="([^"]+)"', rel)
                if rid and tgt:
                    targets[rid.group(1)] = tgt.group(1)
            for i in sorted(ids):
                if i not in targets:
                    problems.append(f"{part}: picture refers to {i}, which has no relationship")
                elif not targets[i].startswith("http"):
                    full = posixpath.normpath(posixpath.join(posixpath.dirname(part), targets[i]))
                    if full not in names:
                        problems.append(f"{part}: {i} -> {full} is missing from the package")
    return problems


def clear_metadata(doc: Document) -> None:
    """Strip author and tool metadata inherited from the template or python-docx."""
    cp = doc.core_properties
    cp.author = ""
    cp.last_modified_by = ""
    cp.comments = ""
    cp.keywords = ""
    cp.subject = ""
    cp.title = ""


def build(out: Path, facts: dict, team: dict, results, fig_dir: Path, template: Path) -> list[str]:
    rep = Report(template, facts, team, results, fig_dir)
    rep.front_matter()
    rep.strip_old_body()
    rep.body_section()
    res_sentence = C_results_sentence(results) if results else ""
    rep.abstract(res_sentence)
    rep.build_chapters()
    rep.references()
    rep.appendix()
    rep.contents_pages()
    rep.nomenclature()
    rep.list_of_figures()
    set_header_footer(rep.doc, team["short_title"])
    print(f'  dropped {drop_unused_links(rep.doc)} unused hyperlink relationship(s)')
    clear_metadata(rep.doc)
    # ask Word to refresh the TOC and page numbers when the file opens
    settings = rep.doc.settings.element
    upd = OxmlElement("w:updateFields")
    upd.set(qn("w:val"), "true")
    settings.append(upd)
    rep.doc.save(str(out))
    dropped = prune_orphan_media(out)
    print(f'  removed {dropped} orphaned template image(s)')
    problems = verify_images(out)
    if problems:
        raise SystemExit("Broken pictures in the report:\n  " + "\n  ".join(problems))
    print("  verified: every picture reference resolves to a file in the package")
    return rep.missing
